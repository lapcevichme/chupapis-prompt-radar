"""API-level contract / smoke tests (ASGI, no real DB or ML)."""

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
