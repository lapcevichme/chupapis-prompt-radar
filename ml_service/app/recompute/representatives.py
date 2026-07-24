"""Select representative query texts for scenario summarization (ТЗ §8.9)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np


def _cosine_sims(centroid: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    c_norm = float(np.linalg.norm(centroid))
    if c_norm == 0.0:
        return np.zeros(matrix.shape[0], dtype=np.float64)
    row_norms = np.linalg.norm(matrix, axis=1)
    row_norms = np.where(row_norms == 0.0, 1.0, row_norms)
    dots = matrix @ centroid
    return dots / (row_norms * c_norm)


def select_representatives(
    records: Sequence[dict[str, Any]],
    *,
    centroid: Optional[List[float]] = None,
    count: int = 10,
    boundary_count: int = 2,
) -> List[str]:
    """
    Pick ~count representative texts for a cluster.

    Strategy:
      - If embeddings + centroid available: KNN nearest to centroid + a few
        boundary (farthest) samples, deduped.
      - Else: first non-empty query_text samples (stable order).
    """
    count = max(1, int(count))
    texts_with_emb: List[tuple[str, Optional[List[float]]]] = []
    for r in records:
        text = (r.get("query_text") or r.get("text") or "").strip()
        if not text:
            continue
        emb = r.get("embedding")
        texts_with_emb.append((text, emb if isinstance(emb, list) else None))

    if not texts_with_emb:
        return []

    # Dedup by exact text, preserve first occurrence
    seen: set[str] = set()
    unique: List[tuple[str, Optional[List[float]]]] = []
    for t, e in texts_with_emb:
        if t in seen:
            continue
        seen.add(t)
        unique.append((t, e))

    if len(unique) <= count:
        return [t for t, _ in unique]

    # Prefer KNN if we have centroid and embeddings
    if centroid is not None:
        usable_idx = [i for i, (_, e) in enumerate(unique) if e is not None]
        if usable_idx:
            mat = np.asarray([unique[i][1] for i in usable_idx], dtype=np.float64)
            c = np.asarray(centroid, dtype=np.float64)
            sims = _cosine_sims(c, mat)
            order = np.argsort(-sims)  # nearest first
            knn_n = max(1, count - max(0, boundary_count))
            chosen_local: List[int] = []
            for j in order[:knn_n]:
                chosen_local.append(usable_idx[int(j)])
            # boundary: farthest among remaining
            if boundary_count > 0 and len(order) > knn_n:
                far = order[::-1]
                for j in far:
                    li = usable_idx[int(j)]
                    if li in chosen_local:
                        continue
                    chosen_local.append(li)
                    if len(chosen_local) >= count:
                        break
            # fill if needed
            for i in range(len(unique)):
                if len(chosen_local) >= count:
                    break
                if i not in chosen_local:
                    chosen_local.append(i)
            return [unique[i][0] for i in chosen_local[:count]]

    # Fallback: evenly spaced samples
    step = max(1, len(unique) // count)
    idxs = list(range(0, len(unique), step))[:count]
    if len(idxs) < count:
        for i in range(len(unique)):
            if i not in idxs:
                idxs.append(i)
            if len(idxs) >= count:
                break
    return [unique[i][0] for i in idxs[:count]]


def select_representatives_via_qdrant(
    qdrant: Any,
    centroid: List[float],
    *,
    scenario_id: Optional[str] = None,
    count: int = 10,
) -> List[str]:
    """
    Optional KNN via Qdrant search. Returns texts from payload if available.
    Falls back to empty list when store is mock/unavailable.
    """
    if qdrant is None:
        return []
    try:
        hits = qdrant.search(vector=centroid, limit=count)
    except Exception:  # noqa: BLE001
        return []
    texts: List[str] = []
    seen: set[str] = set()
    for h in hits or []:
        payload = getattr(h, "payload", None) or (h if isinstance(h, dict) else {})
        if isinstance(payload, dict):
            if scenario_id and payload.get("scenario_id") not in (None, scenario_id):
                continue
            t = (payload.get("query_text") or payload.get("text") or "").strip()
            if t and t not in seen:
                seen.add(t)
                texts.append(t)
    return texts
