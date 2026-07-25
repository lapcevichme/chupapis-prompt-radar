"""Qdrant vector store with offline mock fallback."""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
    )

    _HAS_QDRANT = True
except ImportError:  # pragma: no cover
    QdrantClient = None  # type: ignore
    Distance = None  # type: ignore
    PointStruct = None  # type: ignore
    VectorParams = None  # type: ignore
    Filter = None  # type: ignore
    FieldCondition = None  # type: ignore
    MatchValue = None  # type: ignore
    _HAS_QDRANT = False


def _force_inmemory() -> bool:
    return os.getenv("ALLOW_INMEMORY_STORE", "").lower() in ("1", "true", "yes")


def _require_qdrant() -> bool:
    """When true, never silently fall back to mock — fail closed for Docker."""
    return os.getenv("QDRANT_REQUIRED", "").lower() in ("1", "true", "yes")


class QdrantStore:
    """
    Point per request_id. Payload:
      request_id, task_type, scenario_id, timestamp, source_id,
      is_outlier, has_failure_signals, failure_signals[]
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        vector_size: int = 384,
    ):
        config = config or {}
        self.url = (
            os.getenv("QDRANT_URL")
            or config.get("qdrant_url")
            or "http://localhost:6333"
        )
        self.collection = (
            os.getenv("QDRANT_COLLECTION")
            or config.get("qdrant_collection")
            or "prompt_radar_vectors"
        )
        self.vector_size = int(config.get("vector_size") or vector_size)
        self.client: Any = None
        self._mock = True
        # mock: request_id -> {vector, payload}
        self._vectors: Dict[str, Dict[str, Any]] = {}

        if _force_inmemory():
            logger.info("QdrantStore: ALLOW_INMEMORY_STORE=true → mock mode")
            return
        if not _HAS_QDRANT:
            msg = "qdrant-client not installed"
            if _require_qdrant():
                raise RuntimeError(f"{msg} and QDRANT_REQUIRED=true")
            logger.warning("%s → mock mode", msg)
            return

        # Docker compose: qdrant may need a few seconds after healthcheck
        attempts = int(os.getenv("QDRANT_CONNECT_RETRIES", "15"))
        timeout = float(os.getenv("QDRANT_TIMEOUT_SEC", "5"))
        last_exc: Optional[BaseException] = None
        for attempt in range(1, max(1, attempts) + 1):
            try:
                try:
                    self.client = QdrantClient(
                        url=self.url, timeout=timeout, check_compatibility=False
                    )
                except TypeError:
                    self.client = QdrantClient(url=self.url, timeout=timeout)
                # cheap ping when available (real client); FakeClient tests may omit it
                if hasattr(self.client, "get_collections"):
                    self.client.get_collections()
                self.ensure_collection(self.vector_size)
                self._mock = False
                logger.info(
                    "QdrantStore connected url=%s collection=%s dim=%s attempt=%s",
                    self.url,
                    self.collection,
                    self.vector_size,
                    attempt,
                )
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self.client = None
                self._mock = True
                logger.warning(
                    "Qdrant connect attempt %s/%s failed (%s)",
                    attempt,
                    attempts,
                    exc,
                )
                if attempt < attempts:
                    import time

                    time.sleep(min(2.0, 0.3 * attempt))

        if _require_qdrant():
            raise RuntimeError(
                f"Qdrant required but unreachable at {self.url}: {last_exc}"
            )
        logger.warning("Qdrant unreachable after %s attempts → mock mode", attempts)

    @property
    def is_mock(self) -> bool:
        return self._mock

    def ensure_collection(self, vector_size: Optional[int] = None) -> None:
        size = int(vector_size or self.vector_size)
        self.vector_size = size
        # During __init__ the store remains in mock mode until the connection and
        # collection are both ready. A real client is sufficient to bootstrap it.
        if self.client is None:
            return
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=size, distance=Distance.COSINE),
            )

    def upsert(
        self,
        request_id: str,
        vector: Sequence[float],
        payload: Optional[Dict[str, Any]] = None,
        *,
        wait: bool = False,
    ) -> None:
        payload = dict(payload or {})
        payload.setdefault("request_id", request_id)
        vec = [float(x) for x in vector]
        if self._mock or self.client is None:
            self._vectors[str(request_id)] = {"vector": vec, "payload": payload}
            return
        point = PointStruct(
            id=_point_id(request_id),
            vector=vec,
            payload=payload,
        )
        self.client.upsert(
            collection_name=self.collection, points=[point], wait=wait
        )

    def upsert_batch(
        self,
        points: List[Dict[str, Any]],
        *,
        batch_size: int = 64,
        wait: bool = False,
    ) -> int:
        """Real multi-point upsert (not N×HTTP). Returns number written."""
        if not points:
            return 0
        batch_size = max(1, int(batch_size))
        prepared: List[Dict[str, Any]] = []
        for p in points:
            rid = p.get("request_id") or p.get("id")
            if not rid:
                continue
            vector = p.get("vector") or p.get("embedding") or []
            payload = p.get("payload")
            if payload is None:
                payload = {
                    k: v
                    for k, v in p.items()
                    if k not in ("vector", "embedding", "id", "request_id")
                }
            payload = dict(payload or {})
            payload.setdefault("request_id", str(rid))
            prepared.append(
                {
                    "request_id": str(rid),
                    "vector": [float(x) for x in vector],
                    "payload": payload,
                }
            )

        if self._mock or self.client is None:
            for item in prepared:
                self._vectors[item["request_id"]] = {
                    "vector": item["vector"],
                    "payload": item["payload"],
                }
            return len(prepared)

        written = 0
        for i in range(0, len(prepared), batch_size):
            chunk = prepared[i : i + batch_size]
            structs = [
                PointStruct(
                    id=_point_id(item["request_id"]),
                    vector=item["vector"],
                    payload=item["payload"],
                )
                for item in chunk
            ]
            self.client.upsert(
                collection_name=self.collection, points=structs, wait=wait
            )
            written += len(structs)
        return written

    def search(
        self,
        vector: Sequence[float],
        limit: int = 10,
        *,
        score_threshold: Optional[float] = None,
        task_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        vec = [float(x) for x in vector]
        if self._mock or self.client is None:
            return self._mock_search(vec, limit, score_threshold, task_type)

        query_filter = None
        if task_type and Filter is not None:
            query_filter = Filter(
                must=[FieldCondition(key="task_type", match=MatchValue(value=task_type))]
            )
        hits = self.client.search(
            collection_name=self.collection,
            query_vector=vec,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=query_filter,
        )
        return [
            {
                "id": h.id,
                "score": float(h.score),
                "payload": dict(h.payload or {}),
                "request_id": (h.payload or {}).get("request_id"),
            }
            for h in hits
        ]

    def get(self, request_id: str) -> Optional[Dict[str, Any]]:
        if self._mock or self.client is None:
            return self._vectors.get(str(request_id))
        try:
            points = self.client.retrieve(
                collection_name=self.collection,
                ids=[_point_id(request_id)],
                with_vectors=True,
                with_payload=True,
            )
            if not points:
                return None
            p = points[0]
            return {
                "vector": list(p.vector) if p.vector is not None else [],
                "payload": dict(p.payload or {}),
            }
        except Exception:  # noqa: BLE001
            return None

    def get_all(self) -> List[Dict[str, Any]]:
        """All points for recompute (mock always; real uses scroll)."""
        if self._mock or self.client is None:
            out = []
            for rid, item in self._vectors.items():
                out.append(
                    {
                        "request_id": rid,
                        "vector": item["vector"],
                        "payload": item.get("payload") or {},
                    }
                )
            return out

        results: List[Dict[str, Any]] = []
        offset = None
        while True:
            records, offset = self.client.scroll(
                collection_name=self.collection,
                limit=256,
                offset=offset,
                with_vectors=True,
                with_payload=True,
            )
            for p in records:
                payload = dict(p.payload or {})
                rid = payload.get("request_id") or str(p.id)
                results.append(
                    {
                        "request_id": rid,
                        "vector": list(p.vector) if p.vector is not None else [],
                        "payload": payload,
                    }
                )
            if offset is None:
                break
        return results

    def get_count(self) -> int:
        if self._mock or self.client is None:
            return len(self._vectors)
        return int(self.client.count(self.collection).count)

    def delete(self, request_id: str) -> None:
        if self._mock or self.client is None:
            self._vectors.pop(str(request_id), None)
            return
        self.client.delete(
            collection_name=self.collection,
            points_selector=[_point_id(request_id)],
        )

    def _mock_search(
        self,
        vector: List[float],
        limit: int,
        score_threshold: Optional[float],
        task_type: Optional[str],
    ) -> List[Dict[str, Any]]:
        scored: List[Dict[str, Any]] = []
        for rid, item in self._vectors.items():
            payload = item.get("payload") or {}
            if task_type and payload.get("task_type") != task_type:
                continue
            other = item.get("vector") or []
            score = _cosine(vector, other)
            if score_threshold is not None and score < score_threshold:
                continue
            scored.append(
                {
                    "id": rid,
                    "score": score,
                    "payload": payload,
                    "request_id": rid,
                }
            )
        scored.sort(key=lambda x: -x["score"])
        return scored[:limit]


def _point_id(request_id: str) -> str:
    """Deterministic UUID from request_id (Qdrant accepts UUID or int)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"prompt-radar:{request_id}"))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))
