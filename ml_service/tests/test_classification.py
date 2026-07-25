"""Unit tests for taxonomy + CatBoost classifier fallbacks (PR C / ТЗ §8.3)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.domain.taxonomy import CORE_TASK_TYPES, Taxonomy
from app.pipeline.classification.catboost_classifier import (
    CatBoostClassifier,
    ClassifierNotAvailable,
    resolve_model_path,
)
from eval.classification_eval import (
    dry_run_report,
    evaluate_classification,
    extract_gold_labels,
)

TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "docs" / "taxonomy" / "taxonomy_v1.md"


def _tax() -> Taxonomy:
    return Taxonomy(TAXONOMY_PATH if TAXONOMY_PATH.is_file() else None)


def _clf(**kwargs) -> CatBoostClassifier:
    defaults = {
        "model_path": "/nonexistent/model.cbm",
        "taxonomy": _tax(),
        "config": {"fallback_mode": "keyword", "confidence_threshold": 0.6},
    }
    defaults.update(kwargs)
    if "config" in kwargs and "config" in defaults:
        # already merged via update; ensure nested config is the provided one
        pass
    return CatBoostClassifier(**defaults)


# --------------------------------------------------------------------------- taxonomy
def test_taxonomy_load():
    taxonomy = _tax()
    assert "text_generation" in taxonomy.taxonomy
    assert "code_help" in taxonomy.taxonomy
    assert "unknown" in taxonomy.taxonomy
    assert "other" in taxonomy.taxonomy
    assert taxonomy.get_label("data_analysis") == "Анализ данных"
    assert set(taxonomy.get_core_labels()) == set(CORE_TASK_TYPES)
    assert taxonomy.is_valid("code_help")
    assert taxonomy.is_valid("unknown")
    assert not taxonomy.is_valid("unknown", allow_unknown=False)
    assert taxonomy.normalize("Data Analysis") is None or taxonomy.normalize("data_analysis") == "data_analysis"
    assert taxonomy.normalize("data_analysis") == "data_analysis"
    assert taxonomy.normalize("  CODE_HELP ") == "code_help"


def test_taxonomy_get_labels():
    tax = _tax()
    labels = tax.get_labels()
    assert len(labels) >= 7
    assert "task_management" in labels


# --------------------------------------------------------------------------- init / paths
def test_classifier_init():
    classifier = _clf(
        config={"fallback_mode": "fail_fast", "confidence_threshold": 0.6},
    )
    assert classifier.fallback_mode == "fail_fast"
    assert classifier.confidence_threshold == 0.6
    assert classifier.labels_ is not None
    assert classifier.model_available is False
    assert classifier.is_ready is False
    status = classifier.readiness_status()
    assert status["status"] == "degraded"
    assert status["code"] == "CLASSIFIER_NOT_AVAILABLE"


def test_resolve_model_path_explicit_and_auto():
    """Explicit path is sticky; empty/None auto-discovers shipped artifact."""
    p = resolve_model_path("/totally/missing/x.cbm")
    assert str(p).replace("\\", "/").endswith("x.cbm")
    # auto: should find app/models/catboost_task_classifier.cbm when present
    auto = resolve_model_path(None)
    repo_model = Path(__file__).resolve().parents[1] / "app" / "models" / "catboost_task_classifier.cbm"
    if repo_model.is_file():
        assert auto.is_file()
        assert auto.name.endswith(".cbm")


def test_fallback_modes_accepted():
    for mode in ["fail_fast", "llm", "embedding_centroid", "keyword"]:
        clf = _clf(config={"fallback_mode": mode})
        assert clf.fallback_mode == mode


# --------------------------------------------------------------------------- keyword (test-only)
def test_predict_keyword_paths():
    classifier = _clf(config={"fallback_mode": "keyword", "confidence_threshold": 0.5})

    result = classifier.predict_with_confidence("Напиши SQL запрос для Excel отчета")
    assert result["task_type"] == "data_analysis"
    assert result["classification_confidence"] >= 0.5
    assert result["source"] == "keyword"

    result2 = classifier.predict_with_confidence("простой текст без ключевых слов")
    # confidence 0.55 with threshold 0.5 → other; with 0.6 would be unknown
    assert result2["task_type"] in ("other", "unknown")


def test_confidence_threshold_unknown():
    classifier = _clf(config={"fallback_mode": "keyword", "confidence_threshold": 0.90})
    # keyword other has conf 0.55 → unknown
    result = classifier.predict_with_confidence("hello world random")
    assert result["task_type"] == "unknown"
    assert result["classification_confidence"] < 0.90


def test_fail_fast_raises():
    classifier = _clf(config={"fallback_mode": "fail_fast", "confidence_threshold": 0.5})
    with pytest.raises(ClassifierNotAvailable) as ei:
        classifier.predict_with_confidence("anything")
    assert ei.value.code == "CLASSIFIER_NOT_AVAILABLE"


# --------------------------------------------------------------------------- LLM fallback (mocked)
def test_llm_fallback_mocked():
    def fake_llm(text: str, labels):
        assert "code_help" in labels
        return json.dumps({"task_type": "code_help", "confidence": 0.91})

    classifier = CatBoostClassifier(
        model_path="/nonexistent/model.cbm",
        taxonomy=_tax(),
        config={"fallback_mode": "llm", "confidence_threshold": 0.5},
        llm_fn=fake_llm,
    )
    result = classifier.predict_with_confidence("fix this Python stacktrace please")
    assert result["task_type"] == "code_help"
    assert result["classification_confidence"] == pytest.approx(0.91)
    assert result["source"] == "llm_fallback"


def test_llm_fallback_invalid_label_normalized():
    def fake_llm(text: str, labels):
        return '{"task_type": "not_a_real_class", "confidence": 0.99}'

    classifier = CatBoostClassifier(
        model_path="/nonexistent/model.cbm",
        taxonomy=_tax(),
        config={"fallback_mode": "llm", "confidence_threshold": 0.5},
        llm_fn=fake_llm,
    )
    result = classifier.predict_with_confidence("zzz")
    # invalid → other (or unknown if conf forced low); parser maps bad to other@0.4
    assert result["task_type"] in ("other", "unknown")


def test_llm_fallback_error_soft_degrade():
    def boom(text: str, labels):
        raise RuntimeError("network down")

    classifier = CatBoostClassifier(
        model_path="/nonexistent/model.cbm",
        taxonomy=_tax(),
        config={"fallback_mode": "llm", "confidence_threshold": 0.99},
        llm_fn=boom,
    )
    result = classifier.predict_with_confidence("query")
    # low conf after error → unknown due to threshold
    assert result["task_type"] == "unknown"
    assert result["source"] == "llm_fallback_error"


# --------------------------------------------------------------------------- embedding_centroid
def test_embedding_centroid_fallback():
    dim = 8
    centroids = {
        "code_help": np.ones(dim),
        "data_analysis": -np.ones(dim),
        "other": np.zeros(dim),
    }
    # make other a small orthogonal-ish vector
    centroids["other"] = np.array([1.0, 0, 0, 0, 0, 0, 0, 0])
    centroids["code_help"] = np.array([0, 1.0, 0, 0, 0, 0, 0, 0])
    centroids["data_analysis"] = np.array([0, 0, 1.0, 0, 0, 0, 0, 0])

    classifier = CatBoostClassifier(
        model_path="/nonexistent/model.cbm",
        taxonomy=_tax(),
        config={"fallback_mode": "embedding_centroid", "confidence_threshold": 0.1},
        class_centroids=centroids,
    )
    emb = np.array([0, 0.99, 0.01, 0, 0, 0, 0, 0], dtype=np.float32)
    result = classifier.predict_with_confidence("code-ish", embedding=emb)
    assert result["task_type"] == "code_help"
    assert result["source"] == "embedding_centroid"


def test_embedding_centroid_empty_centroids():
    classifier = CatBoostClassifier(
        model_path="/nonexistent/model.cbm",
        taxonomy=_tax(),
        config={"fallback_mode": "embedding_centroid", "confidence_threshold": 0.1},
    )
    emb = np.ones(4, dtype=np.float32)
    result = classifier.predict_with_confidence("x", embedding=emb)
    assert result["task_type"] in CORE_TASK_TYPES or result["task_type"] == "unknown"


# --------------------------------------------------------------------------- real .cbm if present
def test_load_real_cbm_if_present():
    """Load shipped CatBoost artifact; embedding models need a vector of matching dim."""
    repo_model = (
        Path(__file__).resolve().parents[1] / "app" / "models" / "catboost_task_classifier.cbm"
    )
    if not repo_model.is_file():
        pytest.skip("no .cbm artifact in repo")
    clf = CatBoostClassifier(
        model_path=str(repo_model),
        taxonomy=_tax(),
        config={"fallback_mode": "keyword", "confidence_threshold": 0.5},
    )
    assert clf.model_available is True
    assert clf.is_ready is True
    assert set(clf.model_classes_) == set(CORE_TASK_TYPES) or len(clf.model_classes_) == 7

    if clf.model_input_kind == "text":
        out = clf.predict(["SELECT * FROM t JOIN excel_sales WHERE region = 'RU'"])
        assert out[0]["task_type"] in list(CORE_TASK_TYPES) + ["unknown"]
        assert out[0]["source"] == "catboost"
        one = clf.predict_with_confidence("Напиши unit-тесты на Python для parse_csv")
        assert one["task_type"] in list(CORE_TASK_TYPES) + ["unknown"]
        assert one["source"] == "catboost"
        return

    # embedding model: unit vector in raw embedding space (PCA applied inside clf)
    if clf._pca_mean is not None:
        n_raw = int(clf._pca_mean.shape[0])
    else:
        n_raw = int(clf.catboost_model.feature_count())
    emb = np.zeros((1, n_raw), dtype=np.float32)
    emb[0, 0] = 1.0
    out = clf.predict(["SELECT * FROM t"], embeddings=emb)
    assert out[0]["task_type"] in list(CORE_TASK_TYPES) + ["unknown"]
    assert out[0]["source"] == "catboost"
    one = clf.predict_with_confidence("unit tests for parse_csv", embedding=emb[0])
    assert one["task_type"] in list(CORE_TASK_TYPES) + ["unknown"]
    assert one["source"] == "catboost"


# --------------------------------------------------------------------------- eval skeleton
def test_extract_gold_and_eval_metrics():
    records = [
        {"request_id": "1", "query_text": "a", "metadata": {"gold_category": "code_help"}},
        {"request_id": "2", "query_text": "b", "metadata": {"gold_category": "data_analysis"}},
        {"request_id": "3", "query_text": "c", "category": "education"},
        {"request_id": "4", "query_text": "d"},  # no gold
    ]
    golds = extract_gold_labels(records)
    assert golds == ["code_help", "data_analysis", "education", None]

    preds = ["code_help", "code_help", "education", "unknown"]
    metrics = evaluate_classification(golds, preds)
    assert metrics.n == 4
    assert metrics.n_with_gold == 3
    assert metrics.accuracy == pytest.approx(2 / 3)
    assert 0.0 <= metrics.macro_f1 <= 1.0
    assert metrics.unknown_rate == pytest.approx(0.25)
    d = metrics.as_dict()
    assert "per_class" in d

    dry = dry_run_report(
        records,
        [{"task_type": p} for p in preds],
    )
    assert dry.accuracy == metrics.accuracy


def test_eval_no_gold():
    m = evaluate_classification([None, None], ["other", "unknown"])
    assert m.n_with_gold == 0
    assert m.unknown_rate == pytest.approx(0.5)
    assert "no gold" in m.notes
