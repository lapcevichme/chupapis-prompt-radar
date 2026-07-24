"""Embeddings adapters: mock (tests), Ollama, OpenRouter.

PR D (§8.4): common interface, timeout+retry, retryable/non-retryable errors,
batching, concurrency limit, dimension from response, optional hash→vector cache.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import List, Optional, Sequence, Tuple

import aiohttp

from app.core.config import EmbeddingsSettings, settings as default_settings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Base embedding error with retry classification."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        code: str = "EMBEDDING_REQUEST_FAILED",
    ):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


class EmbeddingAdapter(ABC):
    """Common interface for embedding providers."""

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Return one embedding vector per input text."""

    async def embed_one(self, text: str) -> List[float]:
        vectors = await self.embed([text])
        return vectors[0]

    @property
    def dimension(self) -> Optional[int]:
        return None

    @property
    def provider_name(self) -> str:
        return "unknown"

    async def close(self) -> None:
        return None


class EmbeddingCache:
    """Optional LRU cache: sha256(normalized text) → vector (demo / re-ingest)."""

    def __init__(self, max_size: int = 10_000):
        self.max_size = max(1, max_size)
        self._store: OrderedDict[str, List[float]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key_for(text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    def get(self, text: str) -> Optional[List[float]]:
        k = self.key_for(text)
        if k not in self._store:
            self.misses += 1
            return None
        self._store.move_to_end(k)
        self.hits += 1
        return list(self._store[k])

    def put(self, text: str, vector: Sequence[float]) -> None:
        k = self.key_for(text)
        if k in self._store:
            self._store.move_to_end(k)
        self._store[k] = list(vector)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return len(self._store)


class MockEmbeddingAdapter(EmbeddingAdapter):
    """Deterministic hash-based embeddings for unit tests / offline MVP."""

    def __init__(self, dim: int = 384, cache: Optional[EmbeddingCache] = None):
        self._dim = dim
        self._cache = cache

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def provider_name(self) -> str:
        return "mock"

    async def embed(self, texts: Sequence[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for t in texts:
            if self._cache is not None:
                hit = self._cache.get(t)
                if hit is not None:
                    out.append(hit)
                    continue
            vec = self._vectorize(t)
            if self._cache is not None:
                self._cache.put(t, vec)
            out.append(vec)
        return out

    def _vectorize(self, text: str) -> List[float]:
        # Stable pseudo-embedding from sha256 of normalized text.
        seed = hashlib.sha256(text.strip().lower().encode("utf-8")).digest()
        buf = seed
        while len(buf) < self._dim * 4:
            buf += hashlib.sha256(buf).digest()
        vec: List[float] = []
        for i in range(self._dim):
            b = buf[i % len(buf)]
            vec.append((b / 127.5) - 1.0)
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]


class HttpEmbeddingAdapter(EmbeddingAdapter):
    """HTTP-backed adapter with batching, timeout, retries, concurrency limit."""

    def __init__(self, cfg: EmbeddingsSettings, cache: Optional[EmbeddingCache] = None):
        self.cfg = cfg
        self._session: Optional[aiohttp.ClientSession] = None
        self._dim: Optional[int] = None
        self._session_lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(max(1, cfg.max_concurrency))
        self._cache = cache

    @property
    def dimension(self) -> Optional[int]:
        return self._dim

    @property
    def provider_name(self) -> str:
        return (self.cfg.provider or "unknown").lower()

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            async with self._session_lock:
                if self._session is None or self._session.closed:
                    timeout = aiohttp.ClientTimeout(total=self.cfg.timeout_sec)
                    self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def embed(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []

        # Resolve cache hits; fetch only misses (preserve order).
        n = len(texts)
        results: List[Optional[List[float]]] = [None] * n
        miss_indices: List[int] = []
        miss_texts: List[str] = []

        for i, t in enumerate(texts):
            if self._cache is not None:
                hit = self._cache.get(t)
                if hit is not None:
                    results[i] = hit
                    continue
            miss_indices.append(i)
            miss_texts.append(t)

        if miss_texts:
            fetched = await self._embed_batches(miss_texts)
            for j, vec in enumerate(fetched):
                idx = miss_indices[j]
                results[idx] = vec
                if self._cache is not None:
                    self._cache.put(miss_texts[j], vec)

        # type: ignore — all slots filled
        return [r if r is not None else [] for r in results]

    async def _embed_batches(self, texts: List[str]) -> List[List[float]]:
        batch_size = max(1, self.cfg.batch_size)
        batches: List[Tuple[int, List[str]]] = []
        for i in range(0, len(texts), batch_size):
            batches.append((i, list(texts[i : i + batch_size])))

        # Concurrent batches, limited by semaphore inside _embed_batch_with_retry
        async def _one(offset: int, batch: List[str]) -> Tuple[int, List[List[float]]]:
            vectors = await self._embed_batch_with_retry(batch)
            return offset, vectors

        parts = await asyncio.gather(*[_one(off, b) for off, b in batches])
        out: List[List[float]] = [[] for _ in texts]
        for offset, vectors in parts:
            for j, v in enumerate(vectors):
                out[offset + j] = v
        return out

    async def _embed_batch_with_retry(self, texts: List[str]) -> List[List[float]]:
        last_err: Optional[Exception] = None
        attempts = self.cfg.max_retries + 1
        for attempt in range(attempts):
            try:
                async with self._sem:
                    return await self._embed_batch(texts)
            except EmbeddingError as e:
                last_err = e
                if not e.retryable or attempt >= self.cfg.max_retries:
                    raise
                delay = min(4.0, 0.5 * (2**attempt))
                logger.warning(
                    "Embedding retryable error (attempt %s/%s): %s",
                    attempt + 1,
                    attempts,
                    e,
                )
                await asyncio.sleep(delay)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                if attempt >= self.cfg.max_retries:
                    raise EmbeddingError(
                        f"Embedding provider unavailable: {e}",
                        retryable=True,
                        code="EMBEDDING_PROVIDER_UNAVAILABLE",
                    ) from e
                delay = min(4.0, 0.5 * (2**attempt))
                logger.warning(
                    "Embedding transport error (attempt %s/%s): %s",
                    attempt + 1,
                    attempts,
                    e,
                )
                await asyncio.sleep(delay)
        raise EmbeddingError(str(last_err), retryable=True) from last_err

    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        provider = (self.cfg.provider or "").lower()
        if provider == "ollama":
            embeddings = await self._ollama(texts)
        elif provider == "openrouter":
            embeddings = await self._openrouter(texts)
        else:
            raise EmbeddingError(
                f"Unknown provider: {self.cfg.provider}",
                retryable=False,
                code="EMBEDDING_PROVIDER_UNAVAILABLE",
            )
        self._set_dim_from(embeddings)
        return embeddings

    def _set_dim_from(self, embeddings: List[List[float]]) -> None:
        if not embeddings:
            return
        dim = len(embeddings[0])
        if self._dim is None:
            self._dim = dim
        elif dim != self._dim:
            raise EmbeddingError(
                f"Embedding dimension mismatch: got {dim}, expected {self._dim}",
                retryable=False,
                code="EMBEDDING_REQUEST_FAILED",
            )

    async def _ollama(self, texts: List[str]) -> List[List[float]]:
        session = await self._session_get()
        url = self.cfg.ollama_url.rstrip("/") + "/api/embed"
        payload = {"model": self.cfg.ollama_model, "input": texts}
        async with session.post(url, json=payload) as resp:
            body = await resp.text()
            if resp.status == 429 or resp.status >= 500:
                raise EmbeddingError(
                    f"Ollama {resp.status}: {body[:200]}",
                    retryable=True,
                    code="EMBEDDING_PROVIDER_UNAVAILABLE",
                )
            if resp.status != 200:
                raise EmbeddingError(
                    f"Ollama {resp.status}: {body[:200]}",
                    retryable=False,
                    code="EMBEDDING_REQUEST_FAILED",
                )
            data = await resp.json(content_type=None)

        embeddings = data.get("embeddings")
        if embeddings is None and "embedding" in data:
            embeddings = [data["embedding"]]
        if not embeddings or len(embeddings) != len(texts):
            raise EmbeddingError(
                "Ollama returned unexpected embeddings payload",
                retryable=False,
                code="EMBEDDING_REQUEST_FAILED",
            )
        return embeddings

    async def _openrouter(self, texts: List[str]) -> List[List[float]]:
        if not self.cfg.openrouter_api_key:
            raise EmbeddingError(
                "OPENROUTER_API_KEY is not set",
                retryable=False,
                code="EMBEDDING_PROVIDER_UNAVAILABLE",
            )
        session = await self._session_get()
        headers = {
            "Authorization": f"Bearer {self.cfg.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.cfg.openrouter_model, "input": texts}
        async with session.post(
            self.cfg.openrouter_url, headers=headers, json=payload
        ) as resp:
            body = await resp.text()
            if resp.status >= 500 or resp.status == 429:
                raise EmbeddingError(
                    f"OpenRouter {resp.status}: {body[:200]}",
                    retryable=True,
                    code="EMBEDDING_PROVIDER_UNAVAILABLE",
                )
            if resp.status != 200:
                raise EmbeddingError(
                    f"OpenRouter {resp.status}: {body[:200]}",
                    retryable=False,
                    code="EMBEDDING_REQUEST_FAILED",
                )
            data = await resp.json(content_type=None)

        items = data.get("data") or []
        items = sorted(items, key=lambda x: x.get("index", 0))
        embeddings = [item["embedding"] for item in items]
        if len(embeddings) != len(texts):
            raise EmbeddingError(
                "OpenRouter returned unexpected embeddings count",
                retryable=False,
                code="EMBEDDING_REQUEST_FAILED",
            )
        return embeddings


def create_embedding_adapter(
    cfg: Optional[EmbeddingsSettings] = None,
    *,
    cache: Optional[EmbeddingCache] = None,
) -> EmbeddingAdapter:
    """Factory: mock | ollama | openrouter.

    Mock only when ``provider=mock`` (default for tests/offline). Production
    sets provider via config/env (``EMBEDDINGS_PROVIDER``).
    """
    cfg = cfg or default_settings.embeddings
    provider = (cfg.provider or "mock").lower()

    if cache is None and cfg.cache_enabled:
        cache = EmbeddingCache(max_size=cfg.cache_max_size)
    elif not cfg.cache_enabled:
        cache = None

    if provider == "mock":
        return MockEmbeddingAdapter(dim=cfg.dim, cache=cache)
    if provider in ("ollama", "openrouter"):
        return HttpEmbeddingAdapter(cfg, cache=cache)
    raise ValueError(f"Unknown embeddings provider: {provider}")
