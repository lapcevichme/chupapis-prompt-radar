import pytest
from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.domain.taxonomy import Taxonomy
from app.pipeline.classification.catboost_classifier import CatBoostClassifier


def test_taxonomy_load():
    """Test taxonomy loading from v1.md."""
    taxonomy = Taxonomy(Path(__file__).parent.parent.parent / "docs/taxonomy/taxonomy_v1.md")
    assert "text_generation" in taxonomy.taxonomy
    assert "code_help" in taxonomy.taxonomy
    assert "unknown" in taxonomy.taxonomy
    assert "other" in taxonomy.taxonomy
    assert taxonomy.get_label("data_analysis") == "Анализ данных"


def test_classifier_init():
    """Test CatBoost classifier initialization with fallback."""
    taxonomy = Taxonomy(Path(__file__).parent.parent.parent / "docs/taxonomy/taxonomy_v1.md")
    classifier = CatBoostClassifier(
        model_path="/nonexistent/model.cbm",
        taxonomy=taxonomy.taxonomy,
        config={"fallback_mode": "fail_fast", "confidence_threshold": 0.6}
    )
    assert classifier.fallback_mode == "fail_fast"
    assert classifier.confidence_threshold == 0.6
    assert classifier.labels_ is not None


def test_predict_with_confidence_mock():
    """Test mock prediction for various queries."""
    taxonomy = Taxonomy(Path(__file__).parent.parent.parent / "docs/taxonomy/taxonomy_v1.md")
    classifier = CatBoostClassifier(
        model_path="/nonexistent/model.cbm",
        taxonomy=taxonomy.taxonomy,
        config={"fallback_mode": "llm", "confidence_threshold": 0.5}
    )
    
    # Test data analysis
    result = classifier.predict_with_confidence("Напиши SQL запрос для Excel отчета")
    assert result["task_type"] in taxonomy.taxonomy
    assert "classification_confidence" in result
    assert result["classification_confidence"] >= 0.0
    
    # Test unknown if low conf (but mock has high)
    # For mock, it should classify based on keywords
    result2 = classifier.predict_with_confidence("простой текст без ключевых слов")
    assert result2["task_type"] in ["other", "unknown"]


def test_fallback_modes():
    """Test different fallback modes."""
    taxonomy = Taxonomy()
    for mode in ["fail_fast", "llm", "embedding_centroid"]:
        clf = CatBoostClassifier(
            model_path=None,
            taxonomy=taxonomy.taxonomy,
            config={"fallback_mode": mode}
        )
        assert clf.fallback_mode == mode


def test_taxonomy_get_labels():
    tax = Taxonomy()
    labels = tax.get_labels()
    assert len(labels) >= 7
    assert "task_management" in labels
