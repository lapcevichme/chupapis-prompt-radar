# PR C — Full classification path (ТЗ §8.3)

## Goal
Production-ready task-type classification: real CatBoost artifact, confidence → `unknown`,
explicit fallbacks, taxonomy v1 hardening, eval skeleton. **No fake CatBoost training on a micro-dataset.**

## Delivered

| Piece | Path |
|-------|------|
| Classifier + fallbacks | `app/pipeline/classification/catboost_classifier.py` |
| Taxonomy v1 harden | `app/domain/taxonomy.py` |
| Classifier settings | `app/core/config.py` → `ClassifierSettings` |
| Wire-up / readiness | `app/main.py` (`/health/ready`, `pipeline_metadata`) |
| Embed-once helper | `app/pipeline/online_pipeline.py` → `prepare_embedding` |
| Eval skeleton | `eval/classification_eval.py` |
| Unit tests (mocked LLM) | `tests/test_classification.py` |

## Behaviour

1. **Load `.cbm`** from (first hit wins):
   - constructor `model_path` / `CLASSIFIER_MODEL_PATH`
   - `ml_service/app/models/catboost_task_classifier.cbm` ← **shipped artifact**
   - `ml_service/catboost_embedding_model.cbm` (legacy alias)
2. **Predict** on embedding features (model trained on qwen3-embedding vectors, dim≈2560).
3. **`confidence < confidence_threshold`** (default `0.60`) → per-record `task_type = unknown`.
4. **If model missing / predict fails**, `fallback_mode`:
   - `fail_fast` → `ClassifierNotAvailable` (`CLASSIFIER_NOT_AVAILABLE`), readiness `degraded`
   - `llm` → OpenRouter chat with taxonomy labels; response parsed + validated; **`llm_fn` injectable for tests**
   - `embedding_centroid` → nearest in-memory class centroid (cosine)
   - `keyword` → **test-only** keyword heuristic (not a prod path)

## Artifact path (do not retrain fake models)

| Artifact | Location |
|----------|----------|
| Primary classifier | `ml_service/app/models/catboost_task_classifier.cbm` |
| Legacy / training output | `ml_service/catboost_embedding_model.cbm` |
| Training script (real data + Ollama embeds) | `ml_service/catboost/train_catboost.py` |

Env: `CLASSIFIER_MODEL_PATH`, `CLASSIFIER_FALLBACK_MODE`, `CLASSIFIER_CONFIDENCE_THRESHOLD`,
`OPENROUTER_API_KEY`, `OPENROUTER_CHAT_URL`, `OPENROUTER_CHAT_MODEL`.

**Training note:** CatBoost must be trained offline on full embeddings (`category` labels from the
dataset), then the `.cbm` copied to `app/models/`. Runtime never fits a model.

## Taxonomy
Canonical 7 classes from `docs/taxonomy/taxonomy_v1.md` (+ service `unknown`).  
`Taxonomy.normalize()` maps free-form LLM output to a core label.

## Eval dry-run
```python
from eval.classification_eval import evaluate_classification, extract_gold_labels
# gold: metadata.gold_category (see log.schema / backend-ml contract)
metrics = evaluate_classification(y_true, y_pred)
# → accuracy, macro_f1, unknown_rate, per_class, confusion
```

## Tests
```bash
cd ml_service
pytest tests/test_classification.py -q
```

## pipeline_metadata fields added
`classifier_fallback_mode`, `classifier_confidence_threshold`, `classifier_model_available`,
`classifier_status`.
