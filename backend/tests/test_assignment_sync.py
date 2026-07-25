"""Assignment mirroring: deduplication and bind-parameter safety.

ML `/assignments` is paginated by offset while its worker keeps inserting rows, so
the same assignment can arrive on two pages. Feeding both into one
`ON CONFLICT DO UPDATE` makes Postgres raise CardinalityViolationError ("cannot
affect row a second time"), which aborts the transaction and used to surface as a
500 on `/ingest/status`. And a full-store sync exceeds asyncpg's 32767 bind
parameters in a single statement.
"""

from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from service.dashboard.service import _UPSERT_CHUNK_SIZE, DashboardService

SOURCE_ID = str(uuid4())

# Explicit columns plus the id/created_at/updated_at Python-side defaults.
_PARAMS_PER_ROW = 11
_ASYNCPG_PARAM_LIMIT = 32767


class _FakeSession:
    """Captures executed statements instead of talking to Postgres."""

    def __init__(self) -> None:
        self.statements = []
        self.commits = 0

    async def execute(self, statement):
        self.statements.append(statement)
        return None

    async def commit(self) -> None:
        self.commits += 1


class _FakeMl:
    def __init__(self, assignments) -> None:
        self._assignments = assignments

    async def get_assignments(self, filters):
        return self._assignments


def _service(assignments) -> tuple[DashboardService, _FakeSession]:
    settings = SimpleNamespace(
        ML_SERVICE_URL="http://ml",
        ML_SERVICE_TOKEN="token",
        ML_HTTP_TIMEOUT_SEC=10,
    )
    session = _FakeSession()
    service = DashboardService(session, settings)
    service._ml = _FakeMl(assignments)
    return service, session


def _assignment(request_id: str, task_type: str = "code_help") -> dict:
    return {
        "source_id": SOURCE_ID,
        "request_id": request_id,
        "task_type": task_type,
        "classification_confidence": 0.9,
        "scenario_id": "code_help:cluster_01",
        "scenario_name": "Отладка сборки",
        "is_outlier": False,
        "has_failure_signals": False,
    }


def _row_count(statement) -> int:
    return len(statement.compile(dialect=postgresql.dialect()).params) // _PARAMS_PER_ROW


async def test_duplicate_request_ids_collapse_to_one_row() -> None:
    """Overlapping pages must not put the same conflict key in one statement twice."""
    service, session = _service(
        [_assignment("req-1"), _assignment("req-2"), _assignment("req-1")]
    )

    synced = await service.sync_assignments(SOURCE_ID)

    assert synced == 2
    assert len(session.statements) == 1
    assert _row_count(session.statements[0]) == 2


async def test_last_occurrence_wins() -> None:
    """A later page carries fresher classification, so it must overwrite the earlier."""
    service, session = _service(
        [_assignment("req-1", "text_generation"), _assignment("req-1", "data_analysis")]
    )

    await service.sync_assignments(SOURCE_ID)

    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    assert "data_analysis" in compiled.params.values()
    assert "text_generation" not in compiled.params.values()


async def test_full_store_sync_is_chunked_under_the_bind_parameter_limit() -> None:
    """A recompute-sized sync must not exceed asyncpg's per-statement cap."""
    assignments = [_assignment(f"req-{i}") for i in range(4858)]
    service, session = _service(assignments)

    synced = await service.sync_assignments(None)

    assert synced == 4858
    assert len(session.statements) == 5  # ceil(4858 / 1000)
    for statement in session.statements:
        params = statement.compile(dialect=postgresql.dialect()).params
        assert len(params) <= _ASYNCPG_PARAM_LIMIT
    # One transaction regardless of how many statements it took.
    assert session.commits == 1


async def test_single_chunk_when_under_the_threshold() -> None:
    service, session = _service([_assignment(f"req-{i}") for i in range(_UPSERT_CHUNK_SIZE)])

    await service.sync_assignments(SOURCE_ID)

    assert len(session.statements) == 1


async def test_empty_assignments_touch_neither_db_nor_transaction() -> None:
    service, session = _service([])

    assert await service.sync_assignments(SOURCE_ID) == 0
    assert session.statements == []
    assert session.commits == 0
