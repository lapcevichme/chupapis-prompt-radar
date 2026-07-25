from types import SimpleNamespace

import pytest

from core.errors import NotFoundError
from service.dashboard.service import DashboardService


class _ScenarioMl:
    def __init__(self) -> None:
        self.filters = []

    async def get_scenarios(self, filters):
        self.filters.append(filters)
        return [
            {"scenario_id": "active", "task_type": "code_help", "count": 3},
            {"scenario_id": "outside-workspace", "task_type": "education", "count": 0},
        ]


def _service() -> tuple[DashboardService, _ScenarioMl]:
    settings = SimpleNamespace(
        ML_SERVICE_URL="http://ml",
        ML_SERVICE_TOKEN="token",
        ML_HTTP_TIMEOUT_SEC=10,
    )
    service = DashboardService(object(), settings)
    ml = _ScenarioMl()
    service._ml = ml
    return service, ml


async def test_workspace_scenarios_exclude_zero_count() -> None:
    service, ml = _service()
    filters = {"source_id": "source-1", "from": None, "to": None}

    result = await service.get_scenarios(filters)

    assert result.total == 1
    assert result.items[0].scenario_id == "active"
    assert ml.filters == [filters]


async def test_scenario_detail_uses_workspace_filters() -> None:
    service, ml = _service()
    filters = {"source_id": "source-1", "from": None, "to": None}

    result = await service.get_scenario("active", filters)

    assert result.count == 3
    assert ml.filters == [filters]

    with pytest.raises(NotFoundError):
        await service.get_scenario("outside-workspace", filters)
