"""Unit tests for phase 3: embeddings, chunking, cosine online clustering."""
from __future__ import annotations

import numpy as np
import pytest

from app.pipeline.clustering_online.cosine_clusterer import CosineClusterer, cosine_sim
from app.pipeline.embeddings.adapter import MockEmbeddingAdapter, create_embedding_adapter
from app.pipeline.long_text.chunking import prepare_for_embedding, split_text_into_chunks
from app.pipeline.online_pipeline import OnlinePipeline
from app.core.config import EmbeddingsSettings, Settings, OnlineClusteringSettings, LongTextSettings


@pytest.mark.asyncio
async def test_mock_embedding_deterministic():
    adapter = MockEmbeddingAdapter(dim=64)
    a = await adapter.embed_one("hello world")
    b = await adapter.embed_one("hello world")
    c = await adapter.embed_one("other text")
    assert len(a) == 64
    assert a == b
    assert a != c
    # unit-ish L2 norm
    norm = sum(x * x for x in a) ** 0.5
    assert abs(norm - 1.0) < 1e-5


@pytest.mark.asyncio
async def test_create_embedding_adapter_mock():
    adapter = create_embedding_adapter(EmbeddingsSettings(provider="mock", dim=32))
    vecs = await adapter.embed(["a", "b"])
    assert len(vecs) == 2
    assert len(vecs[0]) == 32
    await adapter.close()


def test_chunking_overlap():
    words = " ".join(f"w{i}" for i in range(100))
    chunks = split_text_into_chunks(words, max_tokens=20, overlap=5)
    assert len(chunks) > 1
    # first chunk has 20 words
    assert len(chunks[0].split()) == 20
    # empty input
    assert split_text_into_chunks("   ") == []


def test_prepare_for_embedding_direct_vs_chunk():
    short = prepare_for_embedding("short query", max_direct_tokens=100)
    assert short.strategy == "direct"
    assert short.chunks_processed == 0

    long_text = "word " * 9000
    long_res = prepare_for_embedding(
        long_text,
        max_direct_tokens=100,
        chunk_size_tokens=50,
        chunk_overlap_tokens=10,
    )
    assert long_res.strategy == "chunk_summary"
    assert long_res.chunks_processed > 0
    assert long_res.representation


def test_cosine_clusterer_new_and_merge():
    clusterer = CosineClusterer(similarity_threshold=0.85, recompute_centroid=True)
    base = np.ones(16, dtype=np.float64)
    base = base / np.linalg.norm(base)

    r1 = clusterer.assign(base, "data_analysis")
    assert r1.is_new_cluster
    assert r1.scenario_id == "data_analysis:cluster_0"

    # nearly same vector → same cluster
    near = base + np.random.default_rng(0).normal(0, 1e-4, size=16)
    near = near / np.linalg.norm(near)
    r2 = clusterer.assign(near, "data_analysis")
    assert not r2.is_new_cluster
    assert r2.scenario_id == "data_analysis:cluster_0"
    assert r2.similarity >= 0.85

    # orthogonal-ish → new cluster
    other = np.zeros(16, dtype=np.float64)
    other[0] = 1.0
    r3 = clusterer.assign(other, "data_analysis")
    assert r3.is_new_cluster
    assert r3.scenario_id == "data_analysis:cluster_1"

    # different task_type never merges
    r4 = clusterer.assign(base, "code_help")
    assert r4.is_new_cluster
    assert r4.scenario_id == "code_help:cluster_0"

    assert clusterer.cluster_count("data_analysis") == 2
    assert clusterer.cluster_count("code_help") == 1


def test_cosine_sim_bounds():
    a = np.array([1.0, 0.0])
    b = np.array([1.0, 0.0])
    c = np.array([0.0, 1.0])
    assert abs(cosine_sim(a, b) - 1.0) < 1e-9
    assert abs(cosine_sim(a, c)) < 1e-9


@pytest.mark.asyncio
async def test_online_pipeline_end_to_end():
    cfg = Settings(
        embeddings=EmbeddingsSettings(provider="mock", dim=48),
        long_text=LongTextSettings(max_direct_tokens=50, chunk_size_tokens=20, chunk_overlap_tokens=5),
        online_clustering=OnlineClusteringSettings(similarity_threshold=0.9),
    )
    pipeline = OnlinePipeline(settings=cfg)
    r1 = await pipeline.process(
        request_id="req_1",
        query_text="export crm report for last month",
        task_type="data_analysis",
    )
    r2 = await pipeline.process(
        request_id="req_2",
        query_text="export crm report for last month",
        task_type="data_analysis",
    )
    assert r1.scenario_id == r2.scenario_id
    assert r1.is_new_cluster and not r2.is_new_cluster
    assert r1.long_text.strategy == "direct"

    long_q = "analyze " * 200
    r3 = await pipeline.process(
        request_id="req_3",
        query_text=long_q,
        task_type="data_analysis",
    )
    assert r3.long_text.strategy == "chunk_summary"
    await pipeline.close()
