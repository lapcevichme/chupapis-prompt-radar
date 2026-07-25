from types import SimpleNamespace

import service.recompute.service as recompute_module
from service.recompute.service import RecomputeService


class _CompletedMl:
    async def get_recompute_status(self, job_id: str):
        return {
            "job_id": job_id,
            "status": "completed",
            "clusters_created": 22,
            "scenarios_named": 22,
            "completed_at": "2026-07-25T09:21:32+00:00",
        }


async def test_status_maps_ml_completed_at_to_public_finished_at() -> None:
    previous_job_id = recompute_module._LAST_JOB_ID
    recompute_module._LAST_JOB_ID = "recompute_test"
    try:
        settings = SimpleNamespace(
            ML_SERVICE_URL="http://ml",
            ML_SERVICE_TOKEN="token",
            ML_HTTP_TIMEOUT_SEC=10,
        )
        service = RecomputeService(settings)
        service._ml = _CompletedMl()

        result = await service.status()

        assert result.status == "completed"
        assert result.finished_at is not None
        assert result.finished_at.isoformat() == "2026-07-25T09:21:32+00:00"
    finally:
        recompute_module._LAST_JOB_ID = previous_job_id
