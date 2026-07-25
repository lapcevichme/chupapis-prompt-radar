from unittest.mock import AsyncMock, MagicMock
import pytest
from domain.analytics import ModelsAnalyticsResponse, UsersAnalyticsResponse
from service.analytics import AnalyticsService


@pytest.mark.asyncio
async def test_analytics_service_empty_returns_valid_structure():
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.all.return_value = []
    mock_session.execute.return_value = mock_res

    service = AnalyticsService(mock_session)

    users_res = await service.get_users_analytics({})
    assert isinstance(users_res, UsersAnalyticsResponse)
    assert users_res.summary.total_users == 0
    assert users_res.users == []

    models_res = await service.get_models_analytics({})
    assert isinstance(models_res, ModelsAnalyticsResponse)
    assert models_res.summary.total_models_detected == 0
    assert models_res.models == []
