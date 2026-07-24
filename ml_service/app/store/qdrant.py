"""Qdrant adapter with offline mock when client/service unavailable."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams

    _HAS_QDRANT = True
except ImportError:  # pragma: no cover
    QdrantClient = None  # type: ignore
    _HAS_QDRANT = False


class QdrantStore:
    def __init__(self, config: Optional[Dict] = None):
        config = config or {}
        self.url = config.get("qdrant_url", "http://localhost:6333")
        self.collection = config.get("qdrant_collection", "prompt_radar_vectors")
        self.client = None
        self._mock = True
        self._vectors: Dict[str, Any] = {}
        if not _HAS_QDRANT:
            return
        try:
            self.client = QdrantClient(url=self.url, timeout=2.0)
            if not self.client.collection_exists(self.collection):
                self.client.create_collection(
                    collection_name=self.collection,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                )
            self._mock = False
        except Exception:  # noqa: BLE001
            self.client = None
            self._mock = True

    def upsert(self, points: List[Dict]) -> None:
        if self.client is None:
            for p in points:
                rid = p.get("request_id") or p.get("id")
                if rid:
                    self._vectors[str(rid)] = p
            return

    def search(self, vector: List[float], limit: int = 10) -> List[Any]:
        if self.client is None:
            return []
        return []

    def get_count(self) -> int:
        if self.client is None:
            return len(self._vectors)
        return int(self.client.count(self.collection).count)
