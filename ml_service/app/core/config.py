"""Minimal settings for embeddings + online clustering (phase 3)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class EmbeddingsSettings:
    provider: str = "mock"  # mock | ollama | openrouter
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3-embedding:4b"
    openrouter_url: str = "https://openrouter.ai/api/v1/embeddings"
    openrouter_model: str = "qwen/qwen3-embedding-4b"
    openrouter_api_key: str = ""
    batch_size: int = 32
    timeout_sec: float = 30.0
    max_retries: int = 2
    dim: int = 384  # used by mock; real dim comes from provider response


@dataclass
class LongTextSettings:
    max_direct_tokens: int = 8000
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64


@dataclass
class OnlineClusteringSettings:
    similarity_threshold: float = 0.85
    recompute_centroid: bool = True


@dataclass
class Settings:
    embeddings: EmbeddingsSettings = field(default_factory=EmbeddingsSettings)
    long_text: LongTextSettings = field(default_factory=LongTextSettings)
    online_clustering: OnlineClusteringSettings = field(default_factory=OnlineClusteringSettings)


def load_settings() -> Settings:
    """Load settings from env with safe defaults (no pydantic-settings required)."""
    emb = EmbeddingsSettings(
        provider=os.getenv("EMBEDDINGS_PROVIDER", "mock"),
        ollama_url=os.getenv("OLLAMA_URL", "http://ollama:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3-embedding:4b"),
        openrouter_url=os.getenv(
            "OPENROUTER_EMBEDDINGS_URL", "https://openrouter.ai/api/v1/embeddings"
        ),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "qwen/qwen3-embedding-4b"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        batch_size=int(os.getenv("EMBEDDINGS_BATCH_SIZE", "32")),
        timeout_sec=float(os.getenv("EMBEDDINGS_TIMEOUT_SEC", "30")),
        max_retries=int(os.getenv("EMBEDDINGS_MAX_RETRIES", "2")),
        dim=int(os.getenv("EMBEDDINGS_DIM", "384")),
    )
    lt = LongTextSettings(
        max_direct_tokens=int(os.getenv("MAX_DIRECT_TOKENS", "8000")),
        chunk_size_tokens=int(os.getenv("CHUNK_SIZE_TOKENS", "512")),
        chunk_overlap_tokens=int(os.getenv("CHUNK_OVERLAP_TOKENS", "64")),
    )
    oc = OnlineClusteringSettings(
        similarity_threshold=float(os.getenv("ONLINE_SIMILARITY_THRESHOLD", "0.85")),
        recompute_centroid=os.getenv("RECOMPUTE_CENTROID", "true").lower() != "false",
    )
    return Settings(embeddings=emb, long_text=lt, online_clustering=oc)


settings = load_settings()
