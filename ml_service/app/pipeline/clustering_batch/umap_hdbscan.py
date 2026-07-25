"""UMAP + HDBSCAN batch clustering with small-group fallback and cluster cap."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    from umap import UMAP
    from hdbscan import HDBSCAN

    _HAS_UMAP_HDBSCAN = True
except ImportError as _imp_err:  # pragma: no cover
    UMAP = None  # type: ignore
    HDBSCAN = None  # type: ignore
    _HAS_UMAP_HDBSCAN = False
    logger.warning(
        "umap-learn/hdbscan not available (%s) — recompute will use "
        "single-centroid fallback per task_type. Install: pip install umap-learn hdbscan",
        _imp_err,
    )


def make_scenario_id(task_type: str, cluster_n: int) -> str:
    """Stable scenario id: {task_type}:cluster_{n}."""
    return f"{task_type}:cluster_{cluster_n}"


def _cap_clusters(
    X: np.ndarray,
    remapped: list[int],
    is_outlier: list[bool],
    scenario_ids: list[str | None],
    centroids: dict[str, list[float]],
    *,
    task_type: str,
    max_clusters: int,
) -> tuple[list[int], list[bool], list[str | None], dict[str, list[float]]]:
    """Keep largest ``max_clusters``; reassign smaller by nearest centroid."""
    if max_clusters <= 0 or len(centroids) <= max_clusters:
        return remapped, is_outlier, scenario_ids, centroids

    sizes: dict[int, int] = {}
    for lb in remapped:
        if lb >= 0:
            sizes[lb] = sizes.get(lb, 0) + 1
    keep_labels = {
        lb
        for lb, _ in sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0]))[:max_clusters]
    }
    keep_sorted = sorted(keep_labels)
    label_remap = {old: new for new, old in enumerate(keep_sorted)}
    kept_centroids_arr = {
        new: np.asarray(centroids[make_scenario_id(task_type, old)], dtype=np.float64)
        for old, new in label_remap.items()
    }

    new_remapped: list[int] = []
    new_outliers: list[bool] = []
    new_sids: list[str | None] = []
    for i, lb in enumerate(remapped):
        if is_outlier[i] or lb < 0:
            new_remapped.append(-1)
            new_outliers.append(True)
            new_sids.append(None)
            continue
        if lb in label_remap:
            nl = label_remap[lb]
        else:
            emb = X[i]
            best_nl, best_sim = 0, -2.0
            nrm = float(np.linalg.norm(emb)) or 1.0
            for nl, cent in kept_centroids_arr.items():
                cn = float(np.linalg.norm(cent)) or 1.0
                sim = float(np.dot(emb, cent) / (nrm * cn))
                if sim > best_sim:
                    best_sim = sim
                    best_nl = nl
            nl = best_nl
        new_remapped.append(nl)
        new_outliers.append(False)
        new_sids.append(make_scenario_id(task_type, nl))

    new_centroids: dict[str, list[float]] = {}
    for nl in sorted(set(new_remapped) - {-1}):
        mask = np.array([r == nl for r in new_remapped])
        if mask.any():
            new_centroids[make_scenario_id(task_type, nl)] = X[mask].mean(axis=0).tolist()

    logger.info(
        "UMAP+HDBSCAN cap clusters task_type=%s %s → %s (max=%s)",
        task_type,
        len(centroids),
        len(new_centroids),
        max_clusters,
    )
    return new_remapped, new_outliers, new_sids, new_centroids


def run_umap_hdbscan(
    embeddings: list[list[float]],
    *,
    task_type: str = "unknown",
    random_state: int = 42,
    min_cluster_size: int = 10,
    min_samples: int = 4,
    n_neighbors: int = 15,
    n_components: int = 10,
    max_clusters: int = 5,
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
        "max_clusters": max_clusters,
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

    if n < min_cluster_size:
        scenario_id = make_scenario_id(task_type, 0)
        centroid = X.mean(axis=0).tolist()
        return {
            "labels": [0] * n,
            "is_outlier": [False] * n,
            "scenario_ids": [scenario_id] * n,
            "centroids": {scenario_id: centroid},
            "statistical_reliability": "low",
            "fallback_used": "small_group_centroid",
            "metadata": base_meta,
        }

    if not _HAS_UMAP_HDBSCAN:
        logger.error(
            "UMAP/HDBSCAN unavailable — single centroid for task_type=%s n=%s",
            task_type,
            n,
        )
        scenario_id = make_scenario_id(task_type, 0)
        centroid = X.mean(axis=0).tolist()
        return {
            "labels": [0] * n,
            "is_outlier": [False] * n,
            "scenario_ids": [scenario_id] * n,
            "centroids": {scenario_id: centroid},
            "statistical_reliability": "low",
            "fallback_used": "libs_unavailable",
            "metadata": base_meta,
        }

    eff_neighbors = max(2, min(n_neighbors, n - 1))
    eff_components = max(2, min(n_components, n - 2, X.shape[1]))
    eff_min_cluster = max(2, min(min_cluster_size, max(2, n // 3)))
    eff_min_samples = max(1, min(min_samples, eff_min_cluster))
    umap_params = {**umap_params, "n_neighbors": eff_neighbors, "n_components": eff_components}
    hdbscan_params = {
        **hdbscan_params,
        "min_cluster_size": eff_min_cluster,
        "min_samples": eff_min_samples,
    }
    base_meta["umap"] = umap_params
    base_meta["hdbscan"] = hdbscan_params

    logger.info(
        "UMAP+HDBSCAN start task_type=%s n=%s dim=%s n_neighbors=%s n_components=%s "
        "min_cluster_size=%s min_samples=%s",
        task_type,
        n,
        X.shape[1],
        eff_neighbors,
        eff_components,
        eff_min_cluster,
        eff_min_samples,
    )

    reducer = UMAP(
        n_neighbors=eff_neighbors,
        n_components=eff_components,
        min_dist=0.0,
        metric="cosine",
        random_state=random_state,
    )
    reduced = reducer.fit_transform(X)

    clusterer = HDBSCAN(
        min_cluster_size=eff_min_cluster,
        min_samples=eff_min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    raw_labels = clusterer.fit_predict(reduced)
    labels = [int(x) for x in raw_labels]

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

    centroids: dict[str, list[float]] = {}
    for new_lb in sorted(label_map.values()):
        mask = np.array([r == new_lb for r in remapped])
        if mask.any():
            sid = make_scenario_id(task_type, new_lb)
            centroids[sid] = X[mask].mean(axis=0).tolist()

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

    if max_clusters > 0 and len(centroids) > max_clusters:
        remapped, is_outlier, scenario_ids, centroids = _cap_clusters(
            X,
            remapped,
            is_outlier,
            scenario_ids,
            centroids,
            task_type=task_type,
            max_clusters=max_clusters,
        )

    n_outliers = sum(1 for x in is_outlier if x)
    logger.info(
        "UMAP+HDBSCAN done task_type=%s clusters=%s outliers=%s/%s fallback=none",
        task_type,
        len(centroids),
        n_outliers,
        n,
    )
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
