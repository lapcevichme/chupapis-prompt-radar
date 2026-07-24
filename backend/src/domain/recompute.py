from datetime import datetime

from pydantic import BaseModel


class RecomputeJob(BaseModel):
    job_id: str
    status: str
    started_at: datetime | None = None


class RecomputeStatus(BaseModel):
    job_id: str | None = None
    status: str
    clusters_created: int | None = None
    scenarios_named: int | None = None
    finished_at: datetime | None = None
