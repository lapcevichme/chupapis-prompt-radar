"""Embeddings adapters: mock (tests), Ollama, OpenRouter."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

import aiohttp

from app.core.config import EmbeddingsSettings, settings as default_settings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Base embedding error."""

    def __init__(self, message: str, *, retryable: bool = False, code: str = "EMBEDDING_REQUEST_FAILED"):
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

    async def close(self) -> None:
        return None


class MockEmbeddingAdapter(EmbeddingAdapter):
    """Deterministic hash-based embeddings for unit tests / offline MVP."""

    def __init__(self, dim: int = 384):
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._vectorize(t) for t in texts]

    def _vectorize(self, text: str) -> List[float]:
        # Stable pseudo-embedding from sha256 of normalized text.
        seed = hashlib.sha256(text.strip().lower().encode("utf-8")).digest()
        # Expand seed if needed
        buf = seed
        while len(buf) < self._dim * 4:
            buf += hashlib.sha256(buf).digest()
        vec: List[float] = []
        for i in range(self._dim):
            # map bytes to [-1, 1]
            b = buf[i % len(buf)]
            vec.append((b / 127.5) - 1.0)
        # L2 normalize
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]


class HttpEmbeddingAdapter(EmbeddingAdapter):
    """HTTP-backed adapter with batching, timeout and retries."""

    def __init__(self, cfg: EmbeddingsSettings):
        self.cfg = cfg
        self._session: Optional[aiohttp.ClientSession] = None
        self._dim: Optional[int] = None
        self._lock = asyncio.Lock()

    @property
    def dimension(self) -> Optional[int]:
        return self._dim

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            async with self._lock:
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
        out: List[List[float]] = []
        batch_size = max(1, self.cfg.batch_size)
        for i in range(0, len(texts), batch_size):
            batch = list(texts[i : i + batch_size])
            vectors = await self._embed_batch_with_retry(batch)
            out.extend(vectors)
        return out

    async def _embed_batch_with_retry(self, texts: List[str]) -> List[List[float]]:
        last_err: Optional[Exception] = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                return await self._embed_batch(texts)
            except EmbeddingError as e:
                last_err = e
                if not e.retryable or attempt >= self.cfg.max_retries:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                if attempt >= self.cfg.max_retries:
                    raise EmbeddingError(
                        f"Embedding provider unavailable: {e}",
                        retryable=True,
                        code="EMBEDDING_PROVIDER_UNAVAILABLE",
                    ) from e
                await asyncio.sleep(0.5 * (attempt + 1))
        raise EmbeddingError(str(last_err), retryable=True) from last_err

    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        if self.cfg.provider == "ollama":
            return await self._ollama(texts)
        if self.cfg.provider == "openrouter":
            return await self._openrouter(texts)
        raise EmbeddingError(
            f"Unknown provider: {self.cfg.provider}",
            retryable=False,
            code="EMBEDDING_PROVIDER_UNAVAILABLE",
        )

    async def _ollama(self, texts: List[str]) -> List[List[float]]:
        session = await self._session_get()
        url = self.cfg.ollama_url.rstrip("/") + "/api/embed"
        # Ollama /api/embed accepts model + input (str or list)
        payload = {"model": self.cfg.ollama_model, "input": texts}
        async with session.post(url, json=payload) as resp:
            body = await resp.text()
            if resp.status >= 500:
                raise EmbeddingError(
                    f"Ollama {resp.status}: {body[:200]}",
                    retryable=True,
                    code="EMBEDDING_PROVIDER_UNAVAILABLE",
                )
            if resp.status != 200:
                raise EmbeddingError(
                    f"Ollama {resp.status}: {body[:200]}",
                    retryable=False,
                )
            data = await resp.json(content_type=None)
        # Response: {"embeddings": [[...], ...]} or single embedding
        embeddings = data.get("embeddings")
        if embeddings is None and "embedding" in data:
            embeddings = [data["embedding"]]
        if not embeddings or len(embeddings) != len(texts):
            raise EmbeddingError("Ollama returned unexpected embeddings payload")
        if embeddings and self._dim is None:
            self._dim = len(embeddings[0])
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
        async with session.post(self.cfg.openrouter_url, headers=headers, json=payload) as resp:
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
                )
            data = await resp.json(content_type=None)
        items = data.get("data") or []
        # OpenAI-compatible: sort by index
        items = sorted(items, key=lambda x: x.get("index", 0))
        embeddings = [item["embedding"] for item in items]
        if len(embeddings) != len(texts):
            raise EmbeddingError("OpenRouter returned unexpected embeddings count")
        if embeddings and self._dim is None:
            self._dim = len(embeddings[0])
        return embeddings


def create_embedding_adapter(cfg: Optional[EmbeddingsSettings] = None) -> EmbeddingAdapter:
    """Factory: mock | ollama | openrouter."""
    cfg = cfg or default_settings.embeddings
    provider = (cfg.provider or "mock").lower()
    if provider == "mock":
        return MockEmbeddingAdapter(dim=cfg.dim)
    if provider in ("ollama", "openrouter"):
        return HttpEmbeddingAdapter(cfg)
    raise ValueError(f"Unknown embeddings provider: {provider}")
