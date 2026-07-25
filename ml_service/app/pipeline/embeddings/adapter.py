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
        busy: bool = False,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.code = code
        # True when provider is overloaded / rate-limited (scale concurrency down)
        self.busy = bool(busy) or (
            retryable
            and any(
                t in (message or "").lower()
                for t in (
                    "429",
                    "model busy",
                    "engine_overloaded",
                    "overloaded",
                    "rate limit",
                    "retry later",
                )
            )
        )


class AdaptiveConcurrency:
    """Dynamic concurrency gate: scale down on busy, recover on success streak.

    Classic AIMD-ish control for OpenRouter "model busy" / 429:
      - busy  → limit = max(min_limit, limit // 2)
      - N successes in a row → limit = min(max_limit, limit + 1)
    """

    def __init__(
        self,
        max_limit: int = 4,
        *,
        min_limit: int = 1,
        recover_every: int = 8,
    ):
        self.max_limit = max(1, int(max_limit))
        self.min_limit = max(1, min(int(min_limit), self.max_limit))
        self.recover_every = max(1, int(recover_every))
        self._limit = self.max_limit
        self._in_flight = 0
        self._success_streak = 0
        self._busy_events = 0
        self._lock = asyncio.Lock()
        self._cond = asyncio.Condition(self._lock)

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def in_flight(self) -> int:
        return self._in_flight

    async def acquire(self) -> None:
        async with self._cond:
            while self._in_flight >= self._limit:
                await self._cond.wait()
            self._in_flight += 1

    async def release(self, *, success: bool = False, busy: bool = False) -> None:
        async with self._cond:
            self._in_flight = max(0, self._in_flight - 1)
            if busy:
                self._busy_events += 1
                self._success_streak = 0
                old = self._limit
                self._limit = max(self.min_limit, self._limit // 2)
                if self._limit != old:
                    logger.warning(
                        "Adaptive concurrency ↓ %s → %s (busy/rate-limit, in_flight=%s)",
                        old,
                        self._limit,
                        self._in_flight,
                    )
            elif success:
                self._success_streak += 1
                if (
                    self._success_streak >= self.recover_every
                    and self._limit < self.max_limit
                ):
                    self._limit += 1
                    self._success_streak = 0
                    logger.info(
                        "Adaptive concurrency ↑ → %s (after successes, in_flight=%s)",
                        self._limit,
                        self._in_flight,
                    )
            self._cond.notify_all()

    def snapshot(self) -> dict:
        return {
            "limit": self._limit,
            "max_limit": self.max_limit,
            "min_limit": self.min_limit,
            "in_flight": self._in_flight,
            "success_streak": self._success_streak,
            "busy_events": self._busy_events,
        }


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
    """HTTP-backed adapter with batching, timeout, retries, adaptive concurrency."""

    def __init__(self, cfg: EmbeddingsSettings, cache: Optional[EmbeddingCache] = None):
        self.cfg = cfg
        self._session: Optional[aiohttp.ClientSession] = None
        self._dim: Optional[int] = None
        self._session_lock = asyncio.Lock()
        # Adaptive gate shared across all concurrent embed() / workers
        self._limiter = AdaptiveConcurrency(
            max_limit=max(1, int(cfg.max_concurrency)),
            min_limit=1,
            recover_every=8,
        )
        # back-compat alias used by older tests/code
        self._sem = self._limiter
        self._cache = cache

    @property
    def dimension(self) -> Optional[int]:
        return self._dim

    @property
    def provider_name(self) -> str:
        return (self.cfg.provider or "unknown").lower()

    @property
    def concurrency_limit(self) -> int:
        """Current adaptive concurrency limit."""
        return self._limiter.limit

    def concurrency_snapshot(self) -> dict:
        return self._limiter.snapshot()

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

        # Concurrent batches; AdaptiveConcurrency gate inside retry path
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
            await self._limiter.acquire()
            try:
                result = await self._embed_batch(texts)
            except EmbeddingError as e:
                last_err = e
                busy = bool(getattr(e, "busy", False))
                # Always free the slot; scale down if provider is overloaded
                await self._limiter.release(success=False, busy=busy)
                if not e.retryable or attempt >= self.cfg.max_retries:
                    raise
                base = 2.0 if busy else 1.0
                delay = min(45.0, base * (2**attempt))
                logger.warning(
                    "Embedding retryable error (attempt %s/%s, sleep=%.1fs, "
                    "concurrency=%s, busy=%s): %s",
                    attempt + 1,
                    attempts,
                    delay,
                    self._limiter.limit,
                    busy,
                    e,
                )
                await asyncio.sleep(delay)
                continue
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                await self._limiter.release(success=False, busy=True)
                if attempt >= self.cfg.max_retries:
                    raise EmbeddingError(
                        f"Embedding provider unavailable: {e}",
                        retryable=True,
                        busy=True,
                        code="EMBEDDING_PROVIDER_UNAVAILABLE",
                    ) from e
                delay = min(45.0, 1.5 * (2**attempt))
                logger.warning(
                    "Embedding transport error (attempt %s/%s, sleep=%.1fs, concurrency=%s): %s",
                    attempt + 1,
                    attempts,
                    delay,
                    self._limiter.limit,
                    e,
                )
                await asyncio.sleep(delay)
                continue
            else:
                await self._limiter.release(success=True, busy=False)
                return result
        raise EmbeddingError(str(last_err), retryable=True, busy=True) from last_err

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
        # Empty inputs: return empty vectors without calling the API.
        if not texts:
            return []
        # Prefer single-input calls under load — some OpenRouter models return
        # partial/empty `data` for multi-input batches.
        if len(texts) > 1:
            try:
                return await self._openrouter_request(texts)
            except EmbeddingError as e:
                if "unexpected embeddings count" not in str(e) and "empty embeddings" not in str(e):
                    raise
                logger.warning(
                    "OpenRouter batch size=%s failed (%s); falling back to one-by-one",
                    len(texts),
                    e,
                )
                out: List[List[float]] = []
                for t in texts:
                    out.extend(await self._openrouter_request([t]))
                return out
        return await self._openrouter_request(texts)

    @staticmethod
    def _openrouter_payload_error(data: object) -> Optional[str]:
        """OpenRouter sometimes returns HTTP 200 with ``{"error": {...}}`` body."""
        if not isinstance(data, dict) or "error" not in data:
            return None
        err = data.get("error")
        if isinstance(err, dict):
            msg = str(err.get("message") or err)
            code = err.get("code")
            return f"code={code} {msg}"
        return str(err)

    @staticmethod
    def _is_busy_or_rate_limit(status: int, message: str) -> bool:
        m = (message or "").lower()
        if status == 429 or status >= 500:
            return True
        return any(
            tok in m
            for tok in (
                "429",
                "rate limit",
                "rate-limit",
                "model busy",
                "engine_overloaded",
                "overloaded",
                "try again",
                "retry later",
                "temporarily",
            )
        )

    async def _openrouter_request(self, texts: List[str]) -> List[List[float]]:
        session = await self._session_get()
        headers = {
            "Authorization": f"Bearer {self.cfg.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        # OpenAI-compatible API: single string or list of strings
        payload_input: object = texts[0] if len(texts) == 1 else texts
        payload = {"model": self.cfg.openrouter_model, "input": payload_input}
        async with session.post(
            self.cfg.openrouter_url, headers=headers, json=payload
        ) as resp:
            body = await resp.text()
            status = int(resp.status)
            try:
                data = await resp.json(content_type=None) if body else {}
            except Exception:  # noqa: BLE001
                data = {}

            payload_err = self._openrouter_payload_error(data)
            combined = payload_err or body[:300]

            if status != 200 or payload_err:
                retryable = self._is_busy_or_rate_limit(status, combined)
                raise EmbeddingError(
                    f"OpenRouter {status}: {combined[:240]}",
                    retryable=retryable,
                    busy=retryable,
                    code=(
                        "EMBEDDING_PROVIDER_UNAVAILABLE"
                        if retryable
                        else "EMBEDDING_REQUEST_FAILED"
                    ),
                )

        items = data.get("data") if isinstance(data, dict) else None
        if items is None:
            # rare alt shape: {"embeddings": [[...]]}
            alt = data.get("embeddings") if isinstance(data, dict) else None
            if isinstance(alt, list) and alt and isinstance(alt[0], (list, tuple)):
                items = [{"index": i, "embedding": v} for i, v in enumerate(alt)]
            else:
                items = []

        if not items:
            raise EmbeddingError(
                f"OpenRouter empty embeddings payload (expected {len(texts)}): {str(data)[:200]}",
                retryable=True,
                busy=True,
                code="EMBEDDING_PROVIDER_UNAVAILABLE",
            )

        items = sorted(items, key=lambda x: x.get("index", 0) if isinstance(x, dict) else 0)
        embeddings: List[List[float]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            emb = item.get("embedding")
            if emb is None:
                continue
            # Some providers wrap as {"embedding": {"values": [...]}}
            if isinstance(emb, dict):
                emb = emb.get("values") or emb.get("embedding") or emb.get("vector")
            if not isinstance(emb, (list, tuple)):
                continue
            embeddings.append(list(emb))

        if len(embeddings) != len(texts):
            raise EmbeddingError(
                f"OpenRouter returned unexpected embeddings count "
                f"(got {len(embeddings)}, expected {len(texts)}, raw_items={len(items)})",
                retryable=True,  # transient partial responses under rate limit
                busy=True,
                code="EMBEDDING_PROVIDER_UNAVAILABLE",
            )
        return embeddings


def create_embedding_adapter(
    cfg: Optional[EmbeddingsSettings] = None,
    *,
    cache: Optional[EmbeddingCache] = None,
) -> EmbeddingAdapter:
    """Factory from mode/provider.

    - mode=offline → Ollama ``qwen3-embedding:4b``
    - mode=online  → OpenRouter ``qwen/qwen3-embedding-4b``
    - mode=mock    → deterministic hash vectors (tests)
    """
    cfg = cfg or default_settings.embeddings
    raw = (cfg.provider or "").lower()
    known = {"mock", "ollama", "openrouter", ""}
    # explicit unknown provider string → hard fail (unit tests / misconfig)
    if raw and raw not in known:
        raise ValueError(f"Unknown embeddings provider: {raw}")
    # If caller set provider=mock explicitly, force mock mode
    if raw == "mock":
        cfg.mode = "mock"

    provider = (
        cfg.resolve_provider()
        if hasattr(cfg, "resolve_provider")
        else (cfg.provider or "mock").lower()
    )
    # keep cfg.provider in sync for HttpEmbeddingAdapter branching
    cfg.provider = provider

    if cache is None and cfg.cache_enabled:
        cache = EmbeddingCache(max_size=cfg.cache_max_size)
    elif not cfg.cache_enabled:
        cache = None

    if provider == "mock":
        return MockEmbeddingAdapter(dim=cfg.dim, cache=cache)
    if provider in ("ollama", "openrouter"):
        return HttpEmbeddingAdapter(cfg, cache=cache)
    raise ValueError(f"Unknown embeddings provider: {provider}")
