"""Unit tests for PR D: embeddings, chunking, cosine online clustering, pipeline."""
from __future__ import annotations

from typing import List
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from app.core.config import (
    EmbeddingsSettings,
    LongTextSettings,
    OnlineClusteringSettings,
    Settings,
)
from app.pipeline.clustering_online.cosine_clusterer import CosineClusterer, cosine_sim
from app.pipeline.embeddings.adapter import (
    EmbeddingCache,
    EmbeddingError,
    HttpEmbeddingAdapter,
    MockEmbeddingAdapter,
    create_embedding_adapter,
)
from app.pipeline.long_text.chunking import prepare_for_embedding, split_text_into_chunks
from app.pipeline.online_pipeline import OnlinePipeline, preprocess_query


@pytest.mark.asyncio
async def test_mock_embedding_deterministic():
    adapter = MockEmbeddingAdapter(dim=64)
    a = await adapter.embed_one("hello world")
    b = await adapter.embed_one("hello world")
    c = await adapter.embed_one("other text")
    assert len(a) == 64
    assert a == b
    assert a != c
    norm = sum(x * x for x in a) ** 0.5
    assert abs(norm - 1.0) < 1e-5
    assert adapter.provider_name == "mock"
    assert adapter.dimension == 64


@pytest.mark.asyncio
async def test_create_embedding_adapter_mock():
    adapter = create_embedding_adapter(
        EmbeddingsSettings(provider="mock", dim=32, cache_enabled=False)
    )
    vecs = await adapter.embed(["a", "b"])
    assert len(vecs) == 2
    assert len(vecs[0]) == 32
    await adapter.close()


@pytest.mark.asyncio
async def test_embedding_cache_hits():
    cache = EmbeddingCache(max_size=100)
    adapter = MockEmbeddingAdapter(dim=16, cache=cache)
    v1 = await adapter.embed_one("same text")
    v2 = await adapter.embed_one("same text")
    assert v1 == v2
    assert cache.hits >= 1
    assert len(cache) == 1

    # batch with mixed hits/misses
    out = await adapter.embed(["same text", "new text", "same text"])
    assert out[0] == out[2] == v1
    assert len(out[1]) == 16
    assert cache.hits >= 2


def test_embedding_cache_lru_eviction():
    cache = EmbeddingCache(max_size=2)
    cache.put("a", [1.0])
    cache.put("b", [2.0])
    cache.put("c", [3.0])  # evicts a
    assert cache.get("a") is None
    assert cache.get("b") == [2.0]
    assert cache.get("c") == [3.0]


@pytest.mark.asyncio
async def test_http_adapter_batches_and_dim_from_response():
    cfg = EmbeddingsSettings(
        provider="ollama",
        batch_size=2,
        max_concurrency=2,
        max_retries=0,
        cache_enabled=False,
    )
    adapter = HttpEmbeddingAdapter(cfg)

    async def fake_ollama(texts: List[str]) -> List[List[float]]:
        # dim discovered from response
        return [[float(i + 1)] * 8 for i, _ in enumerate(texts)]

    with patch.object(adapter, "_ollama", side_effect=fake_ollama):
        vecs = await adapter.embed(["t0", "t1", "t2"])  # 2 batches
        assert len(vecs) == 3
        assert adapter.dimension == 8
        assert all(len(v) == 8 for v in vecs)
    await adapter.close()


@pytest.mark.asyncio
async def test_http_adapter_retry_on_retryable():
    cfg = EmbeddingsSettings(
        provider="ollama",
        batch_size=8,
        max_retries=2,
        max_concurrency=1,
        cache_enabled=False,
        timeout_sec=5.0,
    )
    adapter = HttpEmbeddingAdapter(cfg)
    calls = {"n": 0}

    async def flaky(texts: List[str]) -> List[List[float]]:
        calls["n"] += 1
        if calls["n"] < 3:
            raise EmbeddingError("temporary", retryable=True, code="EMBEDDING_PROVIDER_UNAVAILABLE")
        return [[0.1] * 4 for _ in texts]

    with patch.object(adapter, "_ollama", side_effect=flaky):
        with patch("app.pipeline.embeddings.adapter.asyncio.sleep", new_callable=AsyncMock):
            vecs = await adapter.embed(["x"])
    assert calls["n"] == 3
    assert len(vecs[0]) == 4
    await adapter.close()


@pytest.mark.asyncio
async def test_http_adapter_non_retryable_fails_fast():
    cfg = EmbeddingsSettings(
        provider="ollama",
        max_retries=3,
        cache_enabled=False,
    )
    adapter = HttpEmbeddingAdapter(cfg)

    async def bad(texts: List[str]) -> List[List[float]]:
        raise EmbeddingError("bad request", retryable=False)

    with patch.object(adapter, "_ollama", side_effect=bad):
        with pytest.raises(EmbeddingError) as ei:
            await adapter.embed(["x"])
    assert ei.value.retryable is False
    await adapter.close()


@pytest.mark.asyncio
async def test_create_adapter_unknown_provider():
    with pytest.raises(ValueError, match="Unknown"):
        create_embedding_adapter(EmbeddingsSettings(provider="nope"))


def test_chunking_overlap():
    words = " ".join(f"w{i}" for i in range(100))
    chunks = split_text_into_chunks(words, max_tokens=20, overlap=5)
    assert len(chunks) > 1
    assert len(chunks[0].split()) == 20
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
    # no silent full-doc drop: strategy flag + chunks_processed recorded
    assert long_res.original_tokens > 100


def test_preprocess_query_normalizes_ws():
    original, normalized = preprocess_query("  hello\n\t world  ")
    assert "\n" in original or original.startswith(" ")
    assert normalized == "hello world"


def test_cosine_clusterer_new_and_merge():
    clusterer = CosineClusterer(similarity_threshold=0.85, recompute_centroid=True)
    base = np.ones(16, dtype=np.float64)
    base = base / np.linalg.norm(base)

    r1 = clusterer.assign(base, "data_analysis")
    assert r1.is_new_cluster
    assert r1.scenario_id == "data_analysis:cluster_0"

    near = base + np.random.default_rng(0).normal(0, 1e-4, size=16)
    near = near / np.linalg.norm(near)
    r2 = clusterer.assign(near, "data_analysis")
    assert not r2.is_new_cluster
    assert r2.scenario_id == "data_analysis:cluster_0"
    assert r2.similarity >= 0.85

    other = np.zeros(16, dtype=np.float64)
    other[0] = 1.0
    r3 = clusterer.assign(other, "data_analysis")
    assert r3.is_new_cluster
    assert r3.scenario_id == "data_analysis:cluster_1"

    r4 = clusterer.assign(base, "code_help")
    assert r4.is_new_cluster
    assert r4.scenario_id == "code_help:cluster_0"

    assert clusterer.cluster_count("data_analysis") == 2
    assert clusterer.cluster_count("code_help") == 1


def test_cosine_clusterer_dump_load_roundtrip():
    c1 = CosineClusterer(similarity_threshold=0.9)
    v = np.array([1.0, 0.0, 0.0])
    c1.assign(v, "code_help")
    dumped = c1.dump_centroids()
    assert len(dumped) == 1
    assert dumped[0]["scenario_id"] == "code_help:cluster_0"

    c2 = CosineClusterer(similarity_threshold=0.9)
    c2.load_centroids(dumped)
    # near-identical vector must join existing cluster
    near = np.array([0.999, 0.001, 0.0])
    near = near / np.linalg.norm(near)
    r = c2.assign(near, "code_help")
    assert not r.is_new_cluster
    assert r.scenario_id == "code_help:cluster_0"


def test_cosine_clusterer_no_centroid_update_when_disabled():
    c = CosineClusterer(similarity_threshold=0.5, recompute_centroid=False)
    v1 = np.array([1.0, 0.0])
    c.assign(v1, "t")
    before = c.get_centroid("t:cluster_0").copy()
    v2 = np.array([0.8, 0.2])
    v2 = v2 / np.linalg.norm(v2)
    c.assign(v2, "t")
    after = c.get_centroid("t:cluster_0")
    np.testing.assert_allclose(before, after)


def test_cosine_sim_bounds():
    a = np.array([1.0, 0.0])
    b = np.array([1.0, 0.0])
    c = np.array([0.0, 1.0])
    assert abs(cosine_sim(a, b) - 1.0) < 1e-9
    assert abs(cosine_sim(a, c)) < 1e-9


@pytest.mark.asyncio
async def test_online_pipeline_end_to_end():
    cfg = Settings(
        embeddings=EmbeddingsSettings(provider="mock", dim=48, cache_enabled=True),
        long_text=LongTextSettings(
            max_direct_tokens=50, chunk_size_tokens=20, chunk_overlap_tokens=5
        ),
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
    assert r1.long_text_strategy == "direct"
    assert r1.chunks_processed == 0
    assert "long_text_strategy" in r1.metrics
    storage = r1.to_storage_dict()
    assert storage["scenario_id"] == r1.scenario_id
    assert "embedding" in storage

    long_q = "analyze " * 200
    r3 = await pipeline.process(
        request_id="req_3",
        query_text=long_q,
        task_type="data_analysis",
    )
    assert r3.long_text_strategy == "chunk_summary"
    assert r3.chunks_processed > 0
    await pipeline.close()


@pytest.mark.asyncio
async def test_online_pipeline_preprocess_ws():
    cfg = Settings(
        embeddings=EmbeddingsSettings(provider="mock", dim=16, cache_enabled=False),
    )
    pipeline = OnlinePipeline(settings=cfg)
    r = await pipeline.process(
        request_id="r",
        query_text="  multi\n  line\t query  ",
        task_type="other",
    )
    assert r.normalized_text == "multi line query"
    assert r.original_text.startswith(" ")
    await pipeline.close()
