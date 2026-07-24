"""Stabilize scenario_id across recompute by matching centroids (cosine)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _parse_cluster_n(scenario_id: str) -> int:
    try:
        return int(scenario_id.rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        return 0


def stabilize_scenario_ids(
    new_centroids: Dict[str, List[float]],
    old_centroids: Dict[str, List[float]],
    *,
    task_type: str,
    match_threshold: float = 0.75,
) -> Dict[str, str]:
    """
    Map temporary new scenario_id → stable scenario_id.

    Greedy bipartite match: for each new centroid (sorted by size of id),
    pick best unused old centroid of same task_type with cosine ≥ threshold.
    Unmatched new clusters get free indices starting from 0 without colliding
    with reused ids.
    """
    if not new_centroids:
        return {}

    # Filter old centroids for this task_type
    old_same = {
        sid: c
        for sid, c in (old_centroids or {}).items()
        if sid.startswith(f"{task_type}:")
    }

    new_ids = sorted(new_centroids.keys(), key=_parse_cluster_n)
    if not old_same:
        # First recompute for this type — keep sequential ids as produced
        return {sid: sid for sid in new_ids}

    old_vecs = {
        sid: np.asarray(vec, dtype=np.float64) for sid, vec in old_same.items()
    }
    used_old: set[str] = set()
    mapping: Dict[str, str] = {}

    # Score matrix then greedy assign best pairs first
    pairs: List[Tuple[float, str, str]] = []
    for new_sid in new_ids:
        nv = np.asarray(new_centroids[new_sid], dtype=np.float64)
        for old_sid, ov in old_vecs.items():
            sim = cosine_similarity(nv, ov)
            if sim >= match_threshold:
                pairs.append((sim, new_sid, old_sid))
    pairs.sort(key=lambda x: -x[0])

    claimed_new: set[str] = set()
    for sim, new_sid, old_sid in pairs:
        if new_sid in claimed_new or old_sid in used_old:
            continue
        mapping[new_sid] = old_sid
        claimed_new.add(new_sid)
        used_old.add(old_sid)

    # Assign free indices to unmatched
    used_ns = {_parse_cluster_n(sid) for sid in mapping.values()}
    used_ns |= {_parse_cluster_n(sid) for sid in used_old}
    next_n = 0

    def take_free() -> int:
        nonlocal next_n
        while next_n in used_ns:
            next_n += 1
        n = next_n
        used_ns.add(n)
        next_n += 1
        return n

    for new_sid in new_ids:
        if new_sid not in mapping:
            n = take_free()
            mapping[new_sid] = f"{task_type}:cluster_{n}"

    return mapping


def apply_id_mapping(
    scenario_ids: List[Optional[str]],
    mapping: Dict[str, str],
) -> List[Optional[str]]:
    """Remap list of scenario_ids (None for outliers stays None)."""
    out: List[Optional[str]] = []
    for sid in scenario_ids:
        if sid is None:
            out.append(None)
        else:
            out.append(mapping.get(sid, sid))
    return out


def remap_centroids(
    centroids: Dict[str, List[float]],
    mapping: Dict[str, str],
) -> Dict[str, List[float]]:
    """Apply mapping to centroid keys; later write wins on collision (should not happen)."""
    remapped: Dict[str, List[float]] = {}
    for old_key, vec in centroids.items():
        remapped[mapping.get(old_key, old_key)] = vec
    return remapped
