"""Task-type classifier: CatBoost artifact when present, keyword fallback for MVP."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import catboost as cb

    _HAS_CATBOOST = True
except ImportError:  # pragma: no cover
    cb = None  # type: ignore
    _HAS_CATBOOST = False

DEFAULT_LABELS = [
    "text_generation",
    "code_help",
    "data_analysis",
    "education",
    "information_search",
    "task_management",
    "other",
]


class CatBoostClassifier:
    """CatBoost classifier for task type classification with fallback modes."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        taxonomy: Optional[Any] = None,
        config: Optional[Dict] = None,
    ):
        self.model_path = model_path or os.getenv(
            "CLASSIFIER_MODEL_PATH", "/app/models/catboost_task_classifier.cbm"
        )
        self.taxonomy = taxonomy or {}
        self.config = config or {}
        self.fallback_mode = self.config.get("fallback_mode", "llm")
        self.confidence_threshold = float(self.config.get("confidence_threshold", 0.60))
        self.catboost_model = None
        self.labels_ = list(self.taxonomy.keys()) if self.taxonomy else list(DEFAULT_LABELS)
        if "unknown" not in self.labels_:
            self.labels_.append("unknown")
        self._load_or_create_model()
        logger.info(
            "Initialized CatBoostClassifier model=%s fallback=%s has_model=%s",
            self.model_path,
            self.fallback_mode,
            self.catboost_model is not None,
        )

    def _load_or_create_model(self) -> None:
        model_path = Path(self.model_path)
        if _HAS_CATBOOST and model_path.exists():
            logger.info("Loading CatBoost model from %s", model_path)
            self.catboost_model = cb.CatBoostClassifier()
            self.catboost_model.load_model(str(model_path))
            return
        if not model_path.exists():
            logger.warning(
                "No model at %s — using keyword heuristic (fallback_mode=%s)",
                model_path,
                self.fallback_mode,
            )
        elif not _HAS_CATBOOST:
            logger.warning("catboost not installed — using keyword heuristic")

    def _heuristic(self, text: str) -> Dict[str, Any]:
        text_lower = text.lower()
        if any(w in text_lower for w in ("sql", "database", "excel", "отчет", "таблиц")):
            task_type, confidence = "data_analysis", 0.85
        elif any(w in text_lower for w in ("code", "function", "debug", "python", "код")):
            task_type, confidence = "code_help", 0.85
        elif any(w in text_lower for w in ("письмо", "email", "почта", "найти", "search")):
            task_type, confidence = "information_search", 0.8
        elif any(w in text_lower for w in ("задача", "jira", "план", "управлен")):
            task_type, confidence = "task_management", 0.8
        elif any(w in text_lower for w in ("генерац", "написать письмо", "черновик", "пост для")):
            task_type, confidence = "text_generation", 0.8
        elif any(w in text_lower for w in ("объясни", "обучен", "урок", "как работает")):
            task_type, confidence = "education", 0.8
        else:
            task_type, confidence = "other", 0.55
        return {"task_type": task_type, "confidence": confidence}

    def predict(
        self, texts: List[str], embeddings: Optional[np.ndarray] = None
    ) -> List[Dict[str, Any]]:
        if not texts:
            return []
        if self.catboost_model is None:
            return [self._heuristic(t) for t in texts]
        try:
            # Real .cbm path expects numeric features; MVP falls back on failure
            if embeddings is not None:
                preds = self.catboost_model.predict(embeddings)
                probs = self.catboost_model.predict_proba(embeddings)
                out: List[Dict[str, Any]] = []
                for i, p in enumerate(preds):
                    conf = float(np.max(probs[i])) if probs is not None else 0.5
                    label = str(p[0] if isinstance(p, (list, np.ndarray)) else p)
                    out.append({"task_type": label, "confidence": conf})
                return out
        except Exception as e:  # noqa: BLE001
            logger.error("CatBoost prediction error: %s. Using heuristic.", e)
        return [self._heuristic(t) for t in texts]

    def predict_with_confidence(
        self, text: str, embedding: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        emb = None
        if embedding is not None:
            emb = np.asarray(embedding).reshape(1, -1)
        pred = self.predict([text], emb)[0]
        confidence = float(pred.get("confidence", 0.0))
        task_type = pred["task_type"]
        if confidence < self.confidence_threshold:
            task_type = "unknown"
        tax = self.taxonomy.get(task_type, {}) if isinstance(self.taxonomy, dict) else {}
        label = tax.get("label", task_type) if isinstance(tax, dict) else task_type
        return {
            "task_type": task_type,
            "classification_confidence": confidence,
            "task_type_label": label,
        }
