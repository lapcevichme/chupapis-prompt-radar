"""UMAP + HDBSCAN batch clustering with small-group fallback."""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from umap import UMAP
    from hdbscan import HDBSCAN

    _HAS_UMAP_HDBSCAN = True
except ImportError:  # pragma: no cover
    UMAP = None  # type: ignore
    HDBSCAN = None  # type: ignore
    _HAS_UMAP_HDBSCAN = False


def make_scenario_id(task_type: str, cluster_n: int) -> str:
    """Stable scenario id: {task_type}:cluster_{n}."""
    return f"{task_type}:cluster_{cluster_n}"


def run_umap_hdbscan(
    embeddings: list[list[float]],
    *,
    task_type: str = "unknown",
    random_state: int = 42,
    min_cluster_size: int = 5,
    min_samples: int = 3,
    n_neighbors: int = 15,
    n_components: int = 10,
) -> dict[str, Any]:
    """
    Cluster embeddings with UMAP → HDBSCAN.

    Returns dict:
      labels: list[int]  (-1 = outlier)
      is_outlier: list[bool]
      scenario_ids: list[str | None]  (None for outliers)
      centroids: dict[str, list[float]]  scenario_id → mean embedding (original space)
      statistical_reliability: "high" | "low"
      fallback_used: str
      metadata: params used
    """
    n = len(embeddings)
    umap_params = {
        "n_neighbors": n_neighbors,
        "n_components": n_components,
        "min_dist": 0.0,
        "metric": "cosine",
        "random_state": random_state,
    }
    hdbscan_params = {
        "min_cluster_size": min_cluster_size,
        "min_samples": min_samples,
        "metric": "euclidean",
        "cluster_selection_method": "eom",
    }
    base_meta = {"umap": umap_params, "hdbscan": hdbscan_params}

    if n == 0:
        return {
            "labels": [],
            "is_outlier": [],
            "scenario_ids": [],
            "centroids": {},
            "statistical_reliability": "low",
            "fallback_used": "empty",
            "metadata": base_meta,
        }

    X = np.asarray(embeddings, dtype=np.float64)
    if X.ndim != 2:
        raise ValueError("embeddings must be 2D")

    # Small-group fallback: not enough points for HDBSCAN
    if n < min_cluster_size or not _HAS_UMAP_HDBSCAN:
        scenario_id = make_scenario_id(task_type, 0)
        centroid = X.mean(axis=0).tolist()
        return {
            "labels": [0] * n,
            "is_outlier": [False] * n,
            "scenario_ids": [scenario_id] * n,
            "centroids": {scenario_id: centroid},
            "statistical_reliability": "low",
            "fallback_used": "small_group_centroid" if n < min_cluster_size else "libs_unavailable",
            "metadata": base_meta,
        }

    # Adaptive n_neighbors / n_components for small-but-valid sets
    eff_neighbors = max(2, min(n_neighbors, n - 1))
    eff_components = max(2, min(n_components, n - 2, X.shape[1]))
    umap_params = {**umap_params, "n_neighbors": eff_neighbors, "n_components": eff_components}
    base_meta["umap"] = umap_params

    reducer = UMAP(
        n_neighbors=eff_neighbors,
        n_components=eff_components,
        min_dist=0.0,
        metric="cosine",
        random_state=random_state,
    )
    reduced = reducer.fit_transform(X)

    clusterer = HDBSCAN(
        min_cluster_size=min(min_cluster_size, max(2, n // 2)),
        min_samples=min(min_samples, max(1, n // 3)),
        metric="euclidean",
        cluster_selection_method="eom",
    )
    raw_labels = clusterer.fit_predict(reduced)
    labels = [int(x) for x in raw_labels]

    # Remap positive labels to stable 0..k-1 (sorted by first appearance order of original label)
    positive = sorted({lb for lb in labels if lb >= 0})
    label_map = {old: new for new, old in enumerate(positive)}

    remapped: list[int] = []
    is_outlier: list[bool] = []
    scenario_ids: list[str | None] = []
    for lb in labels:
        if lb < 0:
            remapped.append(-1)
            is_outlier.append(True)
            scenario_ids.append(None)
        else:
            new_lb = label_map[lb]
            remapped.append(new_lb)
            is_outlier.append(False)
            scenario_ids.append(make_scenario_id(task_type, new_lb))

    # Centroids in original embedding space
    centroids: dict[str, list[float]] = {}
    for new_lb in sorted(label_map.values()):
        mask = np.array([r == new_lb for r in remapped])
        if mask.any():
            sid = make_scenario_id(task_type, new_lb)
            centroids[sid] = X[mask].mean(axis=0).tolist()

    # All noise → single fallback cluster
    if not centroids:
        scenario_id = make_scenario_id(task_type, 0)
        centroids[scenario_id] = X.mean(axis=0).tolist()
        remapped = [0] * n
        is_outlier = [False] * n
        scenario_ids = [scenario_id] * n
        return {
            "labels": remapped,
            "is_outlier": is_outlier,
            "scenario_ids": scenario_ids,
            "centroids": centroids,
            "statistical_reliability": "low",
            "fallback_used": "all_outliers_collapsed",
            "metadata": base_meta,
        }

    return {
        "labels": remapped,
        "is_outlier": is_outlier,
        "scenario_ids": scenario_ids,
        "centroids": centroids,
        "statistical_reliability": "high",
        "fallback_used": "none",
        "metadata": base_meta,
    }


def assign_new_or_existing_cluster(
    embedding: list[float],
    centroids: list[list[float]],
    threshold: float = 0.85,
) -> int:
    """Online assign: closest centroid if cosine >= threshold, else new index."""
    if not centroids:
        return 0
    emb = np.asarray(embedding, dtype=np.float64)
    norm = float(np.linalg.norm(emb))
    if norm == 0.0:
        return 0
    sims: list[float] = []
    for c in centroids:
        c_arr = np.asarray(c, dtype=np.float64)
        c_norm = float(np.linalg.norm(c_arr))
        if c_norm == 0.0:
            sims.append(0.0)
        else:
            sims.append(float(np.dot(emb, c_arr) / (norm * c_norm)))
    max_idx = int(np.argmax(sims))
    if sims[max_idx] >= threshold:
        return max_idx
    return len(centroids)


def technical_scenario_name(task_type: str, cluster_n: int) -> str:
    """LLM-naming fallback (phase 5 will replace with structured LLM)."""
    return f"Сценарий {task_type} {cluster_n}"
