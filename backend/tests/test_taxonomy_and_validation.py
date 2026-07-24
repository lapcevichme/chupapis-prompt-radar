"""Unit tests for taxonomy labels and ML /statistics validation."""

import pytest

from core.errors import StatisticsSchemaInvalidError
from domain.taxonomy import TAXONOMY_VERSION, label
from service.ml.statistics_validation import validate_statistics


def test_known_labels() -> None:
    assert label("data_analysis") == "Анализ данных"
    assert label("code_help") == "Помощь с кодом"
    assert TAXONOMY_VERSION == "v1"


def test_unknown_and_none_fall_back() -> None:
    assert label(None) == "Не уверены"
    assert label("") == "Не уверены"
    assert label("unknown") == "Не уверены"
    # any out-of-taxonomy value -> "Другое"
    assert label("some_new_class") == "Другое"


def _valid_stats() -> dict:
    return {
        "schema_version": "v1",
        "generated_at": "2026-07-25T10:00:00Z",
        "totals": {"records_total": 10},
        "tasks_distribution": [{"task_type": "data_analysis", "count": 5}],
    }


def test_valid_statistics_passes() -> None:
    payload = _valid_stats()
    assert validate_statistics(payload) is payload


def test_missing_required_field_raises() -> None:
    payload = _valid_stats()
    del payload["totals"]
    with pytest.raises(StatisticsSchemaInvalidError):
        validate_statistics(payload)


def test_totals_without_records_total_raises() -> None:
    payload = _valid_stats()
    payload["totals"] = {}
    with pytest.raises(StatisticsSchemaInvalidError):
        validate_statistics(payload)


def test_bad_tasks_distribution_item_raises() -> None:
    payload = _valid_stats()
    payload["tasks_distribution"] = [{"task_type": "data_analysis"}]  # no count
    with pytest.raises(StatisticsSchemaInvalidError):
        validate_statistics(payload)


def test_non_dict_payload_raises() -> None:
    with pytest.raises(StatisticsSchemaInvalidError):
        validate_statistics(["not", "a", "dict"])
