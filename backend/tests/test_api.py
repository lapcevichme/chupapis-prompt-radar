"""API-level contract / smoke tests (ASGI, no real DB or ML)."""

from datetime import UTC, datetime

import io
import zipfile

import httpx
import pytest

from api.v1.deps import get_current_user, get_roi_service
from main import create_app
from service.roi.calculator import RoiConfig, RoiRecord, compute_roi


def _canned_roi():
    config = RoiConfig(
        fte_hourly_rate_rub=1200.0,
        token_cost_per_1k_rub=0.015,
        coeff_short=0.3,
        coeff_medium=1.0,
        coeff_long=2.0,
        short_max_tokens=4000,
        long_min_tokens=30000,
    )
    records = [
        RoiRecord(
            status="success",
            tokens=10000,
            manual_time_minutes=30.0,
            tools_used=["CRM"],
            task_type="data_analysis",
            scenario_id="s1",
            scenario_name="Экспорт отчётов",
        )
    ]
    return compute_roi(records, config)


class _FakeRoiService:
    async def get_roi(self, filters, overrides=None):
        return _canned_roi()


@pytest.fixture
def app():
    return create_app(check_db_on_startup=False)


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac


async def test_ping(client) -> None:
    resp = await client.get("/api/ping")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_openapi_exposes_documented_routes(app) -> None:
    schema = app.openapi()
    paths = schema["paths"]
    expected = [
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/users/me",
        "/api/v1/ingest",
        "/api/v1/logs",  # live webhook (POST) + logs table (GET)
        "/api/v1/sources",
        "/api/v1/recompute",
        "/api/v1/dashboard",
        "/api/v1/scenarios",
        "/api/v1/roi",
        "/api/v1/export",
        "/api/v1/analytics/users",
        "/api/v1/analytics/models",
    ]
    for path in expected:
        assert path in paths, f"missing route in OpenAPI: {path}"
    # live webhook is POST, logs table is GET on the same path
    assert "post" in paths["/api/v1/logs"]
    assert "get" in paths["/api/v1/logs"]


async def test_protected_route_requires_auth(client) -> None:
    resp = await client.get("/api/v1/roi")
    assert resp.status_code == 401
    body = resp.json()
    assert body.get("error_code") == "AUTH_REQUIRED"


async def test_export_xlsx(app, client) -> None:
    app.dependency_overrides[get_current_user] = lambda: object()
    app.dependency_overrides[get_roi_service] = lambda: _FakeRoiService()
    try:
        resp = await client.get("/api/v1/export?format=xlsx")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert "xl/workbook.xml" in zf.namelist()


async def test_export_csv(app, client) -> None:
    app.dependency_overrides[get_current_user] = lambda: object()
    app.dependency_overrides[get_roi_service] = lambda: _FakeRoiService()
    try:
        resp = await client.get("/api/v1/export?format=csv")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "# Summary" in resp.text
    assert "roi_multiplier" in resp.text


async def test_export_rejects_bad_format(app, client) -> None:
    app.dependency_overrides[get_current_user] = lambda: object()
    app.dependency_overrides[get_roi_service] = lambda: _FakeRoiService()
    try:
        resp = await client.get("/api/v1/export?format=pdf")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422


async def test_cors_allows_frontend_origin_with_credentials(client) -> None:
    origin = "http://localhost:3000"
    resp = await client.get("/api/ping", headers={"Origin": origin})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin
    assert resp.headers.get("access-control-allow-credentials") == "true"


async def test_cors_preflight(client) -> None:
    resp = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "POST" in resp.headers.get("access-control-allow-methods", "")


# --- date filters (asyncpg cannot bind bare strings to timestamptz) ----------


def test_dashboard_filters_parse_iso_dates_into_datetimes():
    from api.v1.deps import dashboard_filters

    filters = dashboard_filters(source_id=None, from_="2026-07-25", to=None)

    assert isinstance(filters["from"], datetime)
    assert filters["from"] == datetime(2026, 7, 25, tzinfo=UTC)


def test_dashboard_filters_treat_bare_to_date_as_end_of_day():
    """from=X&to=X must return that whole day, not an empty range."""
    from api.v1.deps import dashboard_filters

    filters = dashboard_filters(source_id=None, from_="2026-07-25", to="2026-07-25")

    assert filters["from"] == datetime(2026, 7, 25, tzinfo=UTC)
    assert filters["to"] > filters["from"]
    assert filters["to"].day == 25


def test_dashboard_filters_reject_garbage_dates():
    from fastapi.exceptions import RequestValidationError

    from api.v1.deps import dashboard_filters

    with pytest.raises(RequestValidationError):
        dashboard_filters(source_id=None, from_="not-a-date", to=None)


def test_ml_client_serializes_datetime_filters_for_the_wire():
    from service.ml.client import _clean

    cleaned = _clean(
        {"source_id": "s1", "from": datetime(2026, 7, 25, tzinfo=UTC), "to": None}
    )

    assert cleaned == {"source_id": "s1", "from": "2026-07-25T00:00:00+00:00"}
