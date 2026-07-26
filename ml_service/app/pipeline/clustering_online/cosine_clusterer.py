"""Online clustering: assign embeddings to centroids by cosine similarity (per task_type).

PR D (§8.5):
  1) embed
  2) max cosine to centroids of same task_type
  3) if ≥ threshold → assign + optional running-mean centroid update
  4) else → new scenario_id ``{task_type}:cluster_{n}``

Centroid state is in-memory; `app.main._hydrate_online_clusterer` reloads it from
the meta store `clusters` table on startup and after each recompute.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors."""
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


@dataclass
class AssignmentResult:
    scenario_id: str
    similarity: float
    is_new_cluster: bool
    is_outlier: bool = False  # online path does not mark HDBSCAN outliers


@dataclass
class ClusterState:
    scenario_id: str
    task_type: str
    centroid: np.ndarray
    count: int = 1


class CosineClusterer:
    """
    Online assignment within each task_type:
      1) max cosine to existing centroids of the same task_type
      2) if >= threshold → assign + optionally update centroid
      3) else → new scenario_id `{task_type}:cluster_{n}`
    """

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        recompute_centroid: bool = True,
    ):
        if not 0.0 <= similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be in [0, 1]")
        self.similarity_threshold = similarity_threshold
        self.recompute_centroid = recompute_centroid
        # scenario_id -> ClusterState
        self._clusters: Dict[str, ClusterState] = {}
        # task_type -> next free cluster index
        self._next_index: Dict[str, int] = {}

    def load_centroid(
        self,
        scenario_id: str,
        task_type: str,
        centroid: np.ndarray | Sequence[float],
        count: int = 1,
    ) -> None:
        """Hydrate a single centroid from meta-store (after recompute / restart)."""
        vec = np.asarray(centroid, dtype=np.float64).reshape(-1)
        self._clusters[scenario_id] = ClusterState(
            scenario_id=scenario_id,
            task_type=task_type,
            centroid=vec,
            count=max(1, count),
        )
        # keep next index above loaded ones
        try:
            n = int(scenario_id.rsplit("_", 1)[-1])
            self._next_index[task_type] = max(self._next_index.get(task_type, 0), n + 1)
        except ValueError:
            pass

    def load_centroids(self, rows: Sequence[Dict[str, Any]]) -> int:
        """
        Bulk hydrate from a list of dicts:
          {scenario_id, task_type, centroid, count?}
        """
        n = 0
        for row in rows:
            self.load_centroid(
                scenario_id=row["scenario_id"],
                task_type=row["task_type"],
                centroid=row["centroid"],
                count=int(row.get("count", 1)),
            )
            n += 1
        return n

    def dump_centroids(self, task_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Export centroids for persistence into the meta store `clusters` table.
        """
        out: List[Dict[str, Any]] = []
        for state in self._clusters.values():
            if task_type is not None and state.task_type != task_type:
                continue
            out.append(
                {
                    "scenario_id": state.scenario_id,
                    "task_type": state.task_type,
                    "centroid": state.centroid.astype(float).tolist(),
                    "count": state.count,
                }
            )
        return out

    def assign(
        self,
        vector: np.ndarray | List[float],
        task_type: str,
    ) -> AssignmentResult:
        """Assign embedding to a cluster of the same task_type."""
        vec = np.asarray(vector, dtype=np.float64).reshape(-1)
        if vec.size == 0:
            raise ValueError("empty embedding vector")
        if not task_type:
            raise ValueError("task_type is required")

        best_id: Optional[str] = None
        best_sim = -1.0
        for state in self._clusters.values():
            if state.task_type != task_type:
                continue
            sim = cosine_sim(vec, state.centroid)
            if sim > best_sim:
                best_sim = sim
                best_id = state.scenario_id

        if best_id is not None and best_sim >= self.similarity_threshold:
            if self.recompute_centroid:
                self._update_centroid(best_id, vec)
            return AssignmentResult(
                scenario_id=best_id,
                similarity=best_sim,
                is_new_cluster=False,
            )

        # new cluster
        idx = self._next_index.get(task_type, 0)
        scenario_id = f"{task_type}:cluster_{idx}"
        self._next_index[task_type] = idx + 1
        self._clusters[scenario_id] = ClusterState(
            scenario_id=scenario_id,
            task_type=task_type,
            centroid=vec.copy(),
            count=1,
        )
        return AssignmentResult(
            scenario_id=scenario_id,
            similarity=1.0,
            is_new_cluster=True,
        )

    # backward-compatible alias used by earlier tests
    def assign_to_cluster(
        self,
        vector: np.ndarray | List[float],
        task_type: str,
    ) -> Tuple[str, Optional[np.ndarray]]:
        result = self.assign(vector, task_type)
        state = self._clusters[result.scenario_id]
        return result.scenario_id, state.centroid.copy()

    def _update_centroid(self, scenario_id: str, vec: np.ndarray) -> None:
        state = self._clusters[scenario_id]
        n = state.count
        state.centroid = (state.centroid * n + vec) / (n + 1)
        state.count = n + 1

    def get_centroid(self, scenario_id: str) -> Optional[np.ndarray]:
        state = self._clusters.get(scenario_id)
        return None if state is None else state.centroid.copy()

    def get_all_scenarios(self, task_type: Optional[str] = None) -> List[str]:
        if task_type is None:
            return list(self._clusters.keys())
        return [s for s, st in self._clusters.items() if st.task_type == task_type]

    def cluster_count(self, task_type: Optional[str] = None) -> int:
        return len(self.get_all_scenarios(task_type))

    def clear(self) -> None:
        """Drop all in-memory centroids (tests / recompute replace)."""
        self._clusters.clear()
        self._next_index.clear()
