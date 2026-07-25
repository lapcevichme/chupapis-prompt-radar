"""Task-type classifier: CatBoost .cbm on raw text + confidence/unknown + fallbacks (ТЗ §8.3).

Primary path: CatBoost text_features (query_text) — no embeddings required.
Embeddings are only used by the optional embedding_centroid fallback.

fallback_mode:
  - fail_fast            — no model → error / CLASSIFIER_NOT_AVAILABLE
  - llm                  — OpenRouter chat over taxonomy labels (injectable)
  - embedding_centroid   — nearest in-memory class centroid
  - keyword              — test-only keyword heuristic (not for prod)

Never trains a fake CatBoost on a micro-dataset.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

import numpy as np

from app.domain.taxonomy import CORE_TASK_TYPES, Taxonomy

logger = logging.getLogger(__name__)

try:
    import catboost as cb
    import pandas as pd

    _HAS_CATBOOST = True
except ImportError:  # pragma: no cover
    cb = None  # type: ignore
    pd = None  # type: ignore
    _HAS_CATBOOST = False

# Optional LLM callable: (query_text, allowed_labels) -> raw response string
LlmFn = Callable[[str, Sequence[str]], str]

DEFAULT_MODEL_NAME = "catboost_task_classifier.cbm"
TEXT_FEATURE_NAME = "query_text"
VALID_FALLBACK_MODES = frozenset(
    {"fail_fast", "llm", "embedding_centroid", "keyword"}
)


class ClassifierNotAvailable(Exception):
    """Raised when model is missing and fallback_mode=fail_fast."""

    code = "CLASSIFIER_NOT_AVAILABLE"

    def __init__(self, message: str = "Classifier model not available"):
        super().__init__(message)
        self.code = "CLASSIFIER_NOT_AVAILABLE"


def resolve_model_path(explicit: Optional[str] = None) -> Path:
    """Resolve .cbm path.

    - If ``explicit`` is a non-empty string: use *only* that path (no auto-discovery).
      Missing file → returned as-is so callers can degrade via fallback_mode.
    - If ``explicit`` is None/empty: CLASSIFIER_MODEL_PATH → app/models/ → cwd scan.
    """
    if explicit is not None and str(explicit).strip():
        return Path(explicit)

    candidates: List[Path] = []
    env = os.getenv("CLASSIFIER_MODEL_PATH")
    if env and env.strip():
        candidates.append(Path(env))

    pkg_root = Path(__file__).resolve().parents[2]  # ml_service/app
    ml_root = Path(__file__).resolve().parents[3]  # ml_service
    candidates.extend(
        [
            pkg_root / "models" / DEFAULT_MODEL_NAME,
            ml_root / "models" / DEFAULT_MODEL_NAME,
            ml_root / "app" / "models" / DEFAULT_MODEL_NAME,
            ml_root / DEFAULT_MODEL_NAME,
            ml_root / "catboost" / "catboost_task_classifier.cbm",
            Path.cwd() / "app" / "models" / DEFAULT_MODEL_NAME,
            Path.cwd() / "models" / DEFAULT_MODEL_NAME,
            Path.cwd() / DEFAULT_MODEL_NAME,
        ]
    )
    for p in candidates:
        if p and p.is_file():
            return p
    if env and env.strip():
        return Path(env)
    return pkg_root / "models" / DEFAULT_MODEL_NAME


def _extract_json(text: str) -> Any:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class CatBoostClassifier:
    """CatBoost task-type classifier with confidence threshold and fallbacks."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        taxonomy: Optional[Union[Dict, Taxonomy]] = None,
        config: Optional[Dict] = None,
        *,
        llm_fn: Optional[LlmFn] = None,
        class_centroids: Optional[Dict[str, np.ndarray]] = None,
    ):
        self.config = dict(config or {})
        raw_mode = self.config.get("fallback_mode", "llm")
        self.fallback_mode = raw_mode if raw_mode in VALID_FALLBACK_MODES else "llm"
        self.confidence_threshold = float(self.config.get("confidence_threshold", 0.60))
        self.taxonomy_version = self.config.get("taxonomy_version", "v1")

        # Taxonomy object or plain dict
        if isinstance(taxonomy, Taxonomy):
            self._taxonomy_obj: Optional[Taxonomy] = taxonomy
            self.taxonomy: Dict[str, Dict] = taxonomy.taxonomy
        elif isinstance(taxonomy, dict) and taxonomy:
            self._taxonomy_obj = None
            self.taxonomy = taxonomy
        else:
            self._taxonomy_obj = Taxonomy()
            self.taxonomy = self._taxonomy_obj.taxonomy

        self.labels_ = list(CORE_TASK_TYPES)
        self.class_labels = list(CORE_TASK_TYPES)  # no unknown for LLM/centroid

        self.model_path = str(resolve_model_path(model_path))
        self.catboost_model = None
        self.model_classes_: List[str] = []
        self.model_available = False
        # "text" = CatBoost text_features on query_text; "embedding" = legacy float matrix
        self.model_input_kind: str = "text"
        self.text_feature_name: str = TEXT_FEATURE_NAME
        self._llm_fn = llm_fn
        self._class_centroids: Dict[str, np.ndarray] = {}
        if class_centroids:
            self.set_class_centroids(class_centroids)

        # OpenRouter settings (used when llm_fn is None and mode=llm)
        self.openrouter_api_key = self.config.get(
            "openrouter_api_key", os.getenv("OPENROUTER_API_KEY", "")
        )
        self.openrouter_chat_url = self.config.get(
            "openrouter_chat_url",
            os.getenv(
                "OPENROUTER_CHAT_URL",
                "https://openrouter.ai/api/v1/chat/completions",
            ),
        )
        self.llm_model = self.config.get(
            "llm_model",
            os.getenv("OPENROUTER_CHAT_MODEL", "google/gemma-4-26b-a4b-it"),
        )

        self._load_model()
        logger.info(
            "Initialized CatBoostClassifier path=%s fallback=%s has_model=%s threshold=%.2f",
            self.model_path,
            self.fallback_mode,
            self.model_available,
            self.confidence_threshold,
        )

    # ------------------------------------------------------------------ load
    def _load_model(self) -> None:
        path = Path(self.model_path)
        if not _HAS_CATBOOST:
            logger.warning("catboost not installed — classifier will use fallback_mode=%s", self.fallback_mode)
            return
        if not path.is_file():
            logger.warning(
                "No model at %s — fallback_mode=%s (no fake training)",
                path,
                self.fallback_mode,
            )
            return
        try:
            model = cb.CatBoostClassifier()
            model.load_model(str(path))
            self.catboost_model = model
            self.model_available = True
            classes = getattr(model, "classes_", None)
            if classes is not None:
                self.model_classes_ = [str(c) for c in classes]
            self.model_input_kind, self.text_feature_name = self._detect_model_input(model, path)
            logger.info(
                "Loaded CatBoost model from %s classes=%s input=%s",
                path,
                self.model_classes_,
                self.model_input_kind,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to load CatBoost model from %s: %s", path, e)
            self.catboost_model = None
            self.model_available = False

    def _detect_model_input(self, model: Any, path: Path) -> tuple[str, str]:
        """Prefer text CatBoost; fall back to embedding matrix for legacy .cbm."""
        text_name = TEXT_FEATURE_NAME
        meta_path = path.with_suffix(".meta.json")
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("embeddings") is False or meta.get("input") == "text":
                    return "text", str(meta.get("text_feature") or TEXT_FEATURE_NAME)
                if meta.get("input") == "embedding" or meta.get("embeddings") is True:
                    return "embedding", text_name
            except Exception:  # noqa: BLE001
                pass

        names = list(getattr(model, "feature_names_", None) or [])
        if names:
            lowered = [str(n).lower() for n in names]
            if any(n in ("query_text", "text") for n in lowered):
                for n in names:
                    if str(n).lower() in ("query_text", "text"):
                        return "text", str(n)
                return "text", str(names[0])
            # Dense emb models: emb_0.. or hundreds of numeric cols
            if len(names) >= 64:
                return "embedding", text_name

        try:
            n_feat = int(model.feature_count_)
            if n_feat >= 64:
                return "embedding", text_name
            if n_feat <= 8:
                return "text", text_name
        except Exception:  # noqa: BLE001
            pass
        # Default for new pipeline
        return "text", text_name

    @property
    def is_ready(self) -> bool:
        """True if model loaded OR a non-fail_fast fallback can serve."""
        if self.model_available:
            return True
        return self.fallback_mode != "fail_fast"

    def readiness_status(self) -> Dict[str, Any]:
        if self.model_available:
            return {"status": "ok", "model_path": self.model_path, "fallback_mode": self.fallback_mode}
        if self.fallback_mode == "fail_fast":
            return {
                "status": "degraded",
                "code": "CLASSIFIER_NOT_AVAILABLE",
                "model_path": self.model_path,
                "fallback_mode": self.fallback_mode,
            }
        return {
            "status": "degraded",
            "code": "CLASSIFIER_USING_FALLBACK",
            "model_path": self.model_path,
            "fallback_mode": self.fallback_mode,
        }

    # ---------------------------------------------------------- centroids API
    def set_class_centroids(self, centroids: Dict[str, Any]) -> None:
        """Set/replace in-memory class centroids (label → 1d vector)."""
        self._class_centroids = {}
        for k, v in centroids.items():
            if k not in CORE_TASK_TYPES and k != "unknown":
                continue
            if k == "unknown":
                continue
            arr = np.asarray(v, dtype=np.float64).ravel()
            if arr.size == 0:
                continue
            self._class_centroids[k] = arr

    def update_class_centroid(self, task_type: str, embedding: np.ndarray, *, alpha: float = 0.1) -> None:
        """Online mean update for a class centroid (optional)."""
        if task_type not in CORE_TASK_TYPES:
            return
        vec = np.asarray(embedding, dtype=np.float64).ravel()
        if task_type not in self._class_centroids:
            self._class_centroids[task_type] = vec.copy()
            return
        prev = self._class_centroids[task_type]
        if prev.shape != vec.shape:
            self._class_centroids[task_type] = vec.copy()
            return
        self._class_centroids[task_type] = (1.0 - alpha) * prev + alpha * vec

    # -------------------------------------------------------------- prediction
    def predict(
        self,
        texts: List[str],
        embeddings: Optional[np.ndarray] = None,
    ) -> List[Dict[str, Any]]:
        """Classify texts. Embeddings optional (only for legacy emb models / centroid fallback)."""
        if not texts:
            return []

        if self.model_available and self.catboost_model is not None:
            try:
                if self.model_input_kind == "text":
                    return self._predict_catboost_text(texts)
                if embeddings is not None:
                    return self._predict_catboost_embeddings(embeddings)
                logger.warning(
                    "Legacy embedding CatBoost loaded but no embeddings provided — fallback"
                )
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "CatBoost prediction error: %s — using fallback_mode=%s",
                    e,
                    self.fallback_mode,
                )

        return [
            self._apply_fallback(t, self._row_emb(embeddings, i)) for i, t in enumerate(texts)
        ]

    def _row_emb(self, embeddings: Optional[np.ndarray], i: int) -> Optional[np.ndarray]:
        if embeddings is None:
            return None
        arr = np.asarray(embeddings)
        if arr.ndim == 1:
            return arr if i == 0 else None
        if i < arr.shape[0]:
            return arr[i]
        return None

    def _pack_predictions(self, preds: Any, probs: Any, n: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for i in range(n):
            p = preds[i]
            label = str(p[0] if isinstance(p, (list, np.ndarray)) else p)
            conf = float(np.max(probs[i])) if probs is not None else 0.5
            label = self._normalize_label(label) or "other"
            out.append(
                {
                    "task_type": label,
                    "confidence": conf,
                    "source": "catboost",
                }
            )
        return out

    def _predict_catboost_text(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Primary path: CatBoost text_features on query_text."""
        assert self.catboost_model is not None and pd is not None and cb is not None
        col = self.text_feature_name
        df = pd.DataFrame({col: [(t or "") for t in texts]})
        pool = cb.Pool(df, text_features=[col])
        preds = self.catboost_model.predict(pool)
        probs = self.catboost_model.predict_proba(pool)
        return self._pack_predictions(preds, probs, len(texts))

    def _predict_catboost_embeddings(self, embeddings: np.ndarray) -> List[Dict[str, Any]]:
        """Legacy path: dense float features from an embedding model."""
        assert self.catboost_model is not None
        X = np.asarray(embeddings, dtype=np.float32)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        preds = self.catboost_model.predict(X)
        probs = self.catboost_model.predict_proba(X)
        return self._pack_predictions(preds, probs, X.shape[0])

    def _normalize_label(self, raw: str) -> Optional[str]:
        if self._taxonomy_obj is not None:
            return self._taxonomy_obj.normalize(raw)
        s = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
        if s in CORE_TASK_TYPES:
            return s
        return None

    def _apply_fallback(
        self, text: str, embedding: Optional[np.ndarray]
    ) -> Dict[str, Any]:
        mode = self.fallback_mode
        if mode == "fail_fast":
            raise ClassifierNotAvailable(
                f"No CatBoost model at {self.model_path} and fallback_mode=fail_fast"
            )
        if mode == "llm":
            return self._llm_fallback(text)
        if mode == "embedding_centroid":
            return self._embedding_centroid_fallback(text, embedding)
        if mode == "keyword":
            return self._keyword_heuristic(text)
        # unknown mode → keyword as last resort for tests
        return self._keyword_heuristic(text)

    # ------------------------------------------------------------ LLM fallback
    def _build_llm_prompt(self, text: str, labels: Sequence[str]) -> str:
        lines = []
        for tt in labels:
            meta = self.taxonomy.get(tt, {})
            lab = meta.get("label", tt) if isinstance(meta, dict) else tt
            desc = meta.get("description", "") if isinstance(meta, dict) else ""
            lines.append(f"- {tt}: {lab} — {desc}")
        labels_block = "\n".join(lines)
        return f"""Ты — классификатор корпоративных запросов к ИИ-агентам.
Выбери РОВНО один task_type из списка.

Допустимые task_type:
{labels_block}

Запрос пользователя:
\"\"\"{text[:4000]}\"\"\"

Ответь строго JSON:
{{"task_type": "<один из списка>", "confidence": 0.0-1.0}}
Без пояснений вне JSON.
"""

    def _parse_llm_response(self, raw: str) -> Dict[str, Any]:
        task_type: Optional[str] = None
        confidence = 0.55
        try:
            parsed = _extract_json(raw)
            if isinstance(parsed, dict):
                task_type = self._normalize_label(str(parsed.get("task_type", "")))
                try:
                    confidence = float(parsed.get("confidence", 0.55))
                except (TypeError, ValueError):
                    confidence = 0.55
        except Exception:  # noqa: BLE001
            # free text: first matching label token
            task_type = self._normalize_label(raw)
            if task_type is None:
                for lab in self.class_labels:
                    if lab in raw.lower():
                        task_type = lab
                        break
        if task_type is None:
            task_type = "other"
            confidence = 0.4
        confidence = max(0.0, min(1.0, confidence))
        return {
            "task_type": task_type,
            "confidence": confidence,
            "source": "llm_fallback",
        }

    def _llm_fallback(self, text: str) -> Dict[str, Any]:
        """LLM classify via ChatOpenRouter.with_structured_output(Pydantic)."""
        labels = self.class_labels
        try:
            if self._llm_fn is not None:
                return self._parse_llm_response(self._llm_fn(text, labels))

            from pydantic import BaseModel, Field

            from app.adapters.llm import chat_openrouter

            class LlmClassOut(BaseModel):
                task_type: str = Field(description="One allowed task_type label")
                confidence: float = Field(description="Confidence 0..1", ge=0.0, le=1.0)

            if not self.openrouter_api_key:
                raise RuntimeError("OPENROUTER_API_KEY not set for llm fallback")

            chat = chat_openrouter(
                model=self.llm_model,
                api_key=self.openrouter_api_key,
                temperature=0.1,
            )
            structured = chat.with_structured_output(LlmClassOut)
            out = structured.invoke(self._build_llm_prompt(text, labels))
            if isinstance(out, dict):
                out = LlmClassOut.model_validate(out)
            task_type = self._normalize_label(out.task_type) or "other"
            conf = max(0.0, min(1.0, float(out.confidence)))
            return {
                "task_type": task_type,
                "confidence": conf,
                "source": "llm_fallback",
            }
        except Exception as e:  # noqa: BLE001
            logger.error("LLM fallback failed: %s", e)
            return {
                "task_type": "other",
                "confidence": 0.3,
                "source": "llm_fallback_error",
            }

    # ------------------------------------------------- embedding_centroid
    def _embedding_centroid_fallback(
        self, text: str, embedding: Optional[np.ndarray]
    ) -> Dict[str, Any]:
        if embedding is None or not self._class_centroids:
            logger.warning(
                "embedding_centroid fallback needs embedding + centroids; falling to keyword"
            )
            # test-friendly soft degrade
            if self.fallback_mode == "embedding_centroid" and not self._class_centroids:
                return {
                    "task_type": "other",
                    "confidence": 0.35,
                    "source": "embedding_centroid_empty",
                }
            return self._keyword_heuristic(text)

        emb = np.asarray(embedding, dtype=np.float64).ravel()
        best_label = "other"
        best_sim = -1.0
        for lab, cent in self._class_centroids.items():
            if emb.shape != np.asarray(cent).ravel().shape:
                continue
            sim = _cosine(emb, cent)
            if sim > best_sim:
                best_sim = sim
                best_label = lab
        # map cosine [-1,1] ~ [0,1] for confidence-ish score
        conf = max(0.0, min(1.0, (best_sim + 1.0) / 2.0)) if best_sim >= 0 else 0.4
        # if best_sim is typical cosine in [0,1], use as confidence directly when >=0
        if best_sim >= 0:
            conf = float(best_sim)
        return {
            "task_type": best_label,
            "confidence": conf,
            "source": "embedding_centroid",
        }

    # -------------------------------------------------------- keyword (test)
    def _keyword_heuristic(self, text: str) -> Dict[str, Any]:
        text_lower = (text or "").lower()
        if any(w in text_lower for w in ("sql", "database", "excel", "отчет", "отчёт", "таблиц")):
            task_type, confidence = "data_analysis", 0.85
        elif any(w in text_lower for w in ("code", "function", "debug", "python", "код", "javascript")):
            task_type, confidence = "code_help", 0.85
        elif any(
            w in text_lower
            for w in ("письмо", "email", "почта", "найти", "search", "confluence", "crm")
        ):
            task_type, confidence = "information_search", 0.8
        elif any(w in text_lower for w in ("задача", "jira", "план", "управлен", "встреч", "календар")):
            task_type, confidence = "task_management", 0.8
        elif any(
            w in text_lower
            for w in ("генерац", "написать письмо", "черновик", "пост для", "напиши текст")
        ):
            task_type, confidence = "text_generation", 0.8
        elif any(w in text_lower for w in ("объясни", "обучен", "урок", "как работает", "что значит")):
            task_type, confidence = "education", 0.8
        else:
            task_type, confidence = "other", 0.55
        return {
            "task_type": task_type,
            "confidence": confidence,
            "source": "keyword",
        }

    # ------------------------------------------------ predict_with_confidence
    def predict_with_confidence(
        self,
        text: str,
        embedding: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Classify one text; confidence < threshold → task_type=unknown.

        ``embedding`` is unused for text CatBoost models; kept for centroid fallback
        and legacy embedding-based .cbm files.
        """
        emb = None
        if embedding is not None:
            emb = np.asarray(embedding, dtype=np.float32)
            if emb.ndim == 1:
                emb = emb.reshape(1, -1)

        try:
            pred = self.predict([text], emb)[0]
        except ClassifierNotAvailable:
            raise
        except Exception as e:  # noqa: BLE001
            logger.error("predict_with_confidence failed: %s", e)
            pred = {"task_type": "other", "confidence": 0.0, "source": "error"}

        confidence = float(pred.get("confidence", 0.0))
        task_type = str(pred.get("task_type", "other"))
        source = pred.get("source", "unknown")

        # Validate label
        if task_type not in CORE_TASK_TYPES and task_type != "unknown":
            normalized = self._normalize_label(task_type)
            task_type = normalized or "other"

        # Threshold → unknown (per-record, ТЗ §8.3)
        if confidence < self.confidence_threshold:
            task_type = "unknown"

        tax = self.taxonomy.get(task_type, {}) if isinstance(self.taxonomy, dict) else {}
        label = tax.get("label", task_type) if isinstance(tax, dict) else task_type
        return {
            "task_type": task_type,
            "classification_confidence": confidence,
            "task_type_label": label,
            "source": source,
        }
