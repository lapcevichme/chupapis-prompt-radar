"""Long-text strategy: overlapping word chunks → summary representation for embed/classify."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


def estimate_tokens(text: str) -> int:
    """Rough token estimate (words). Good enough for MVP gating."""
    return max(1, len(text.split())) if text.strip() else 0


def split_text_into_chunks(
    text: str,
    *,
    max_tokens: int = 512,
    overlap: int = 64,
) -> List[str]:
    """
    Split text into overlapping word-windows.

    - max_tokens: target chunk size in words
    - overlap: words carried into the next chunk
    Empty / whitespace-only input → [].
    """
    words = text.split()
    if not words:
        return []
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    overlap = max(0, min(overlap, max_tokens - 1))

    chunks: List[str] = []
    step = max(1, max_tokens - overlap)
    for start in range(0, len(words), step):
        window = words[start : start + max_tokens]
        if not window:
            break
        chunks.append(" ".join(window))
        if start + max_tokens >= len(words):
            break
    return chunks


@dataclass
class LongTextResult:
    """Result of long-text preparation."""

    representation: str
    strategy: str  # "direct" | "chunk_summary"
    chunks_processed: int
    original_tokens: int


def prepare_for_embedding(
    text: str,
    *,
    max_direct_tokens: int = 8000,
    chunk_size_tokens: int = 512,
    chunk_overlap_tokens: int = 64,
    max_summary_chunks: int = 8,
) -> LongTextResult:
    """
    If text is short enough → use as-is.
    If long → chunk, take first N chunks + last chunk as a compact representation
    (no silent truncation of the whole document without marking strategy).
    """
    cleaned = (text or "").strip()
    original_tokens = estimate_tokens(cleaned)
    if original_tokens <= max_direct_tokens:
        return LongTextResult(
            representation=cleaned,
            strategy="direct",
            chunks_processed=0,
            original_tokens=original_tokens,
        )

    chunks = split_text_into_chunks(
        cleaned,
        max_tokens=chunk_size_tokens,
        overlap=chunk_overlap_tokens,
    )
    if not chunks:
        return LongTextResult(
            representation=cleaned[: max_direct_tokens * 5],  # fallback chars
            strategy="chunk_summary",
            chunks_processed=0,
            original_tokens=original_tokens,
        )

    # Keep head + tail so intent and closing instructions are preserved
    if len(chunks) <= max_summary_chunks:
        selected = chunks
    else:
        head_n = max_summary_chunks - 1
        selected = chunks[:head_n] + [chunks[-1]]

    # Lightweight extractive summary: first ~40 words of each selected chunk
    parts: List[str] = []
    for ch in selected:
        words = ch.split()
        parts.append(" ".join(words[:40]))
    representation = " [...] ".join(parts)

    return LongTextResult(
        representation=representation,
        strategy="chunk_summary",
        chunks_processed=len(chunks),
        original_tokens=original_tokens,
    )


def join_chunk_embeddings(embeddings: Sequence[Sequence[float]]) -> List[float]:
    """Mean-pool chunk embeddings into one vector (L2-normalized)."""
    if not embeddings:
        return []
    dim = len(embeddings[0])
    acc = [0.0] * dim
    for vec in embeddings:
        for i, v in enumerate(vec):
            acc[i] += float(v)
    n = float(len(embeddings))
    mean = [x / n for x in acc]
    norm = sum(x * x for x in mean) ** 0.5 or 1.0
    return [x / norm for x in mean]
