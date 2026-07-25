from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.config import get_settings
from domain.analytics import ModelsAnalyticsResponse, UsersAnalyticsResponse
from service.analytics import AnalyticsService


def _service(rows: list) -> AnalyticsService:
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.all.return_value = rows
    mock_session.execute.return_value = mock_res
    return AnalyticsService(mock_session, get_settings())


def _row(**kw):
    base = dict(
        request_id="r1",
        query_text="q",
        gold_category=None,
        user_id="u1",
        user_name="User One",
        department="IT",
        tokens=1000,
        manual_time_minutes=30.0,
        tools_used=[],
        status="success",
        timestamp=datetime.now(UTC),
        task_type="code_help",
        is_outlier=False,
        has_failure_signals=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_analytics_service_empty_returns_valid_structure():
    service = _service([])

    users_res = await service.get_users_analytics({})
    assert isinstance(users_res, UsersAnalyticsResponse)
    assert users_res.summary.total_users == 0
    assert users_res.users == []

    models_res = await service.get_models_analytics({})
    assert isinstance(models_res, ModelsAnalyticsResponse)
    assert models_res.summary.status == "not_available"
    assert models_res.summary.total_models_detected == 0
    assert models_res.models == []


@pytest.mark.asyncio
async def test_models_not_reported_without_model_metadata():
    """Records carrying no model field must not be attributed to a guessed model."""
    rows = [_row(request_id=f"r{i}", tools_used=["Jira", "Excel"]) for i in range(50)]

    res = await _service(rows).get_models_analytics({})

    assert res.summary.status == "not_available"
    assert res.summary.total_models_detected == 0
    assert res.models == []


@pytest.mark.asyncio
async def test_models_reported_only_from_real_model_metadata():
    rows = [
        _row(request_id="r1", tools_used=["model:gpt-4o"], tokens=1000),
        _row(request_id="r2", tools_used=["model:gpt-4o"], tokens=500),
        _row(request_id="r3", tools_used=["Jira"]),  # no model -> excluded
    ]

    res = await _service(rows).get_models_analytics({})

    assert res.summary.status == "available"
    assert res.summary.total_models_detected == 1
    assert res.summary.total_queries_with_model == 2
    assert res.summary.total_tokens == 1500
    assert res.models[0].model_id == "gpt-4o"
    assert res.models[0].share_percentage == 100.0


@pytest.mark.asyncio
async def test_active_users_window_excludes_stale_users():
    now = datetime.now(UTC)
    rows = [
        _row(request_id="r1", user_id="recent", timestamp=now),
        _row(request_id="r2", user_id="stale", timestamp=now - timedelta(days=30)),
    ]

    res = await _service(rows).get_users_analytics({})

    assert res.summary.total_users == 2
    assert res.summary.active_users_l7 == 1
    assert res.summary.active_window_days == 7


@pytest.mark.asyncio
async def test_persona_distribution_does_not_collapse_to_one_bucket():
    """A mixed cohort must not be labelled 100% super_user (regression)."""
    rows = []
    # Heavy code specialist
    for i in range(60):
        rows.append(_row(request_id=f"c{i}", user_id="coder", task_type="code_help"))
    # Broad, high-volume user across 5 categories
    spread = [
        "code_help",
        "data_analysis",
        "education",
        "task_management",
        "text_generation",
    ] * 12
    for i, tt in enumerate(spread):
        rows.append(_row(request_id=f"s{i}", user_id="super", task_type=tt))
    # Very light user
    rows.append(_row(request_id="l1", user_id="light", task_type="education"))

    res = await _service(rows).get_users_analytics({})

    personas = {u.user_id: u.persona for u in res.users}
    assert personas["coder"] == "code_craftsman"
    assert personas["super"] == "super_user"
    assert personas["light"] == "casual"
    assert len(res.summary.personas_distribution) >= 3


@pytest.mark.asyncio
async def test_saved_hours_follow_roi_methodology():
    """Failed records save nothing; successful ones scale by the session coefficient."""
    rows = [
        # 1000 tokens -> short session -> coeff 0.3 -> 60 * 0.3 = 18 min
        _row(request_id="ok", status="success", manual_time_minutes=60.0, tokens=1000),
        _row(
            request_id="bad",
            status="error_tool",
            manual_time_minutes=60.0,
            tokens=1000,
        ),
    ]

    res = await _service(rows).get_users_analytics({})

    assert res.users[0].saved_hours == pytest.approx(0.3, abs=0.05)
