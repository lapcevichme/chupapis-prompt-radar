"""Online path (PR D): preprocess → long_text → embed → cosine assign.

Returns a full result suitable for Qdrant + meta storage (embedding, scenario_id,
long-text metrics). Classification (task_type) is supplied by the caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from app.core.config import Settings, settings as default_settings
from app.pipeline.clustering_online.cosine_clusterer import (
    AssignmentResult,
    CosineClusterer,
)
from app.pipeline.embeddings.adapter import EmbeddingAdapter, create_embedding_adapter
from app.pipeline.long_text.chunking import LongTextResult, prepare_for_embedding


_WS_RE = re.compile(r"\s+")


def preprocess_query(text: str) -> tuple[str, str]:
    """
    §8.1 preprocessing: normalize whitespace; keep original + normalized.

    Does not strip technical tokens; does not alter request_id (caller owns it).
    """
    original = text if text is not None else ""
    normalized = _WS_RE.sub(" ", original).strip()
    return original, normalized


@dataclass
class OnlinePipelineResult:
    """Full online-path result for storage / metrics."""

    request_id: str
    task_type: str
    scenario_id: str
    similarity: float
    is_new_cluster: bool
    embedding: list[float]
    long_text: LongTextResult
    original_text: str = ""
    normalized_text: str = ""
    # Explicit metrics aliases (ТЗ: long_text_strategy, chunks_processed)
    long_text_strategy: str = "direct"
    chunks_processed: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_storage_dict(self) -> Dict[str, Any]:
        """Payload fragment for Qdrant point + meta assignment."""
        return {
            "request_id": self.request_id,
            "task_type": self.task_type,
            "scenario_id": self.scenario_id,
            "similarity": self.similarity,
            "is_new_cluster": self.is_new_cluster,
            "embedding": self.embedding,
            "long_text_strategy": self.long_text_strategy,
            "chunks_processed": self.chunks_processed,
            "original_tokens": self.long_text.original_tokens,
            "metrics": self.metrics,
        }


class OnlinePipeline:
    """Orchestrates embeddings + online clustering for a single log record."""

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        embedder: Optional[EmbeddingAdapter] = None,
        clusterer: Optional[CosineClusterer] = None,
    ):
        self.settings = settings or default_settings
        self.embedder = embedder or create_embedding_adapter(self.settings.embeddings)
        self.clusterer = clusterer or CosineClusterer(
            similarity_threshold=self.settings.online_clustering.similarity_threshold,
            recompute_centroid=self.settings.online_clustering.recompute_centroid,
        )

    async def process(
        self,
        *,
        request_id: str,
        query_text: str,
        task_type: str,
        embedding: Optional[list[float]] = None,
        long_text: Optional[LongTextResult] = None,
        original_text: Optional[str] = None,
        normalized_text: Optional[str] = None,
    ) -> OnlinePipelineResult:
        # 1) preprocess
        if original_text is not None and normalized_text is not None:
            original, normalized = original_text, normalized_text
        else:
            original, normalized = preprocess_query(query_text)

        # 2) long-text strategy (no silent truncate of whole doc)
        if long_text is not None:
            lt = long_text
        else:
            lt = prepare_for_embedding(
                normalized,
                max_direct_tokens=self.settings.long_text.max_direct_tokens,
                chunk_size_tokens=self.settings.long_text.chunk_size_tokens,
                chunk_overlap_tokens=self.settings.long_text.chunk_overlap_tokens,
            )

        # 3) embed summary / direct representation (reuse if provided — CatBoost needs same vector)
        if embedding is not None:
            emb_list = list(embedding)
        else:
            emb_list = await self.embedder.embed_one(lt.representation)

        # 4) online assign within task_type
        assignment: AssignmentResult = self.clusterer.assign(
            np.asarray(emb_list, dtype=np.float64),
            task_type,
        )

        metrics = {
            "long_text_strategy": lt.strategy,
            "chunks_processed": lt.chunks_processed,
            "original_tokens": lt.original_tokens,
            "embedding_dim": len(emb_list),
            "embedding_provider": getattr(self.embedder, "provider_name", "unknown"),
            "similarity": assignment.similarity,
            "is_new_cluster": assignment.is_new_cluster,
        }

        return OnlinePipelineResult(
            request_id=request_id,
            task_type=task_type,
            scenario_id=assignment.scenario_id,
            similarity=assignment.similarity,
            is_new_cluster=assignment.is_new_cluster,
            embedding=emb_list,
            long_text=lt,
            original_text=original,
            normalized_text=normalized,
            long_text_strategy=lt.strategy,
            chunks_processed=lt.chunks_processed,
            metrics=metrics,
        )

    async def embed_query(self, query_text: str) -> tuple[str, str, LongTextResult, list[float]]:
        """Preprocess + long-text + embed once (for CatBoost → cluster reuse)."""
        original, normalized = preprocess_query(query_text)
        lt = prepare_for_embedding(
            normalized,
            max_direct_tokens=self.settings.long_text.max_direct_tokens,
            chunk_size_tokens=self.settings.long_text.chunk_size_tokens,
            chunk_overlap_tokens=self.settings.long_text.chunk_overlap_tokens,
        )
        emb = await self.embedder.embed_one(lt.representation)
        return original, normalized, lt, list(emb)

    async def close(self) -> None:
        await self.embedder.close()
