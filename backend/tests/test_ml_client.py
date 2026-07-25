"""Unit tests for MlClient streaming (backend-ml.md §2: source_id per record)."""

from types import SimpleNamespace
from typing import Any

import pytest

from core.errors import MLUnavailableError
from service.ml.client import MlClient, _clean


@pytest.fixture
def captured_client(ml_settings: SimpleNamespace, monkeypatch):
    client = MlClient(ml_settings)
    calls: list[dict[str, Any]] = []

    async def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, int]:
        calls.append({"method": method, "path": path, **kwargs})
        logs = kwargs.get("json", {}).get("logs", [])
        return {"accepted": len(logs), "duplicates": 0, "rejected": 0}

    monkeypatch.setattr(client, "_request", fake_request)
    return client, calls


async def test_source_id_injected_into_every_record(captured_client) -> None:
    client, calls = captured_client
    records = [{"request_id": "req_0"}, {"request_id": "req_1"}, {"request_id": "req_2"}]

    await client.stream_logs("src_abc", records)

    all_logs = [log for call in calls for log in call["json"]["logs"]]
    assert len(all_logs) == 3
    assert all(log["source_id"] == "src_abc" for log in all_logs)
    # top-level source_id also set on each batch payload
    assert all(call["json"]["source_id"] == "src_abc" for call in calls)


async def test_batches_respect_batch_size(captured_client) -> None:
    client, calls = captured_client  # ML_INGEST_BATCH_SIZE == 2
    records = [{"request_id": f"req_{i}"} for i in range(5)]

    totals = await client.stream_logs("src_abc", records)

    assert len(calls) == 3  # 2 + 2 + 1
    assert [len(c["json"]["logs"]) for c in calls] == [2, 2, 1]
    assert totals["accepted"] == 5


async def test_missing_ml_url_raises_unavailable() -> None:
    client = MlClient(SimpleNamespace(ML_SERVICE_URL="", ML_SERVICE_TOKEN="t",
                                      ML_HTTP_TIMEOUT_SEC=5, ML_INGEST_BATCH_SIZE=200))
    with pytest.raises(MLUnavailableError):
        client._client()


async def test_waits_for_async_ml_assignments(ml_settings, monkeypatch) -> None:
    client = MlClient(ml_settings)
    observed = iter((0, 1, 2))

    async def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, int]:
        assert method == "GET"
        assert path == "/api/v1/assignments"
        assert kwargs["params"]["source_id"] == "source-a"
        return {"items": [], "total": next(observed)}

    monkeypatch.setattr(client, "_request", fake_request)

    assert await client.wait_for_assignment_count("source-a", 2) == 2


def test_clean_drops_none_params() -> None:
    assert _clean({"source_id": "s", "from": None, "to": "x"}) == {
        "source_id": "s",
        "to": "x",
    }
    assert _clean(None) == {}
