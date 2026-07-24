"""Minimal phase-3 pipeline: long-text → embed → online cosine assign."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.core.config import Settings, settings as default_settings
from app.pipeline.clustering_online.cosine_clusterer import AssignmentResult, CosineClusterer
from app.pipeline.embeddings.adapter import EmbeddingAdapter, create_embedding_adapter
from app.pipeline.long_text.chunking import LongTextResult, prepare_for_embedding


@dataclass
class OnlinePipelineResult:
    request_id: str
    task_type: str
    scenario_id: str
    similarity: float
    is_new_cluster: bool
    embedding: list[float]
    long_text: LongTextResult


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
    ) -> OnlinePipelineResult:
        lt = prepare_for_embedding(
            query_text,
            max_direct_tokens=self.settings.long_text.max_direct_tokens,
            chunk_size_tokens=self.settings.long_text.chunk_size_tokens,
            chunk_overlap_tokens=self.settings.long_text.chunk_overlap_tokens,
        )
        embedding = await self.embedder.embed_one(lt.representation)
        assignment: AssignmentResult = self.clusterer.assign(
            np.asarray(embedding, dtype=np.float64),
            task_type,
        )
        return OnlinePipelineResult(
            request_id=request_id,
            task_type=task_type,
            scenario_id=assignment.scenario_id,
            similarity=assignment.similarity,
            is_new_cluster=assignment.is_new_cluster,
            embedding=list(embedding),
            long_text=lt,
        )

    async def close(self) -> None:
        await self.embedder.close()
