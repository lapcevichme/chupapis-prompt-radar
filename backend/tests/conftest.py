import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Ensure `src/` is importable regardless of how pytest resolves pythonpath.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from service.roi.calculator import RoiConfig, RoiRecord  # noqa: E402


@pytest.fixture
def roi_config() -> RoiConfig:
    """Default ROI config mirroring config.py defaults."""
    return RoiConfig(
        fte_hourly_rate_rub=1200.0,
        token_cost_per_1k_rub=0.015,
        coeff_short=0.3,
        coeff_medium=1.0,
        coeff_long=2.0,
        short_max_tokens=4000,
        long_min_tokens=30000,
    )


@pytest.fixture
def make_record():
    """Factory-as-fixture: build a RoiRecord with sensible defaults."""

    def _make(
        *,
        status: str | None = "success",
        tokens: int = 10000,
        manual_time_minutes: float = 30.0,
        tools_used: list | None = None,
        task_type: str | None = "data_analysis",
        scenario_id: str | None = "data_analysis:cluster_01",
        scenario_name: str | None = "Экспорт отчётов CRM",
    ) -> RoiRecord:
        return RoiRecord(
            status=status,
            tokens=tokens,
            manual_time_minutes=manual_time_minutes,
            tools_used=tools_used if tools_used is not None else ["CRM"],
            task_type=task_type,
            scenario_id=scenario_id,
            scenario_name=scenario_name,
        )

    return _make


@pytest.fixture
def normalize_settings() -> SimpleNamespace:
    """Duck-typed Settings for the pure normalizer (no env needed)."""
    return SimpleNamespace(
        NORMALIZE_SYNTHESIZE_TIMESTAMPS=True,
        NORMALIZE_TIMESTAMP_SPAN_DAYS=14,
    )


@pytest.fixture
def ml_settings() -> SimpleNamespace:
    """Duck-typed Settings for MlClient."""
    return SimpleNamespace(
        ML_SERVICE_URL="http://ml-service:8000",
        ML_SERVICE_TOKEN="test-token",
        ML_HTTP_TIMEOUT_SEC=30,
        ML_INGEST_BATCH_SIZE=2,
    )
