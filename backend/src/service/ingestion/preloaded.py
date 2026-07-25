import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from core.config import Settings, get_settings

from .normalizer import parse_raw

logger = logging.getLogger(__name__)

_SOURCE_NAMESPACE = uuid5(NAMESPACE_URL, "prompt-radar:preloaded-datasets:v1")


@dataclass(frozen=True)
class PreloadedDatasetSpec:
    key: str
    name: str
    categories: frozenset[str]

    @property
    def source_id(self) -> UUID:
        return uuid5(_SOURCE_NAMESPACE, self.key)


PRELOADED_DATASETS: tuple[PreloadedDatasetSpec, ...] = (
    PreloadedDatasetSpec(
        key="knowledge-communications",
        name="Knowledge & Communications",
        categories=frozenset(
            {"text_generation", "education", "information_search"}
        ),
    ),
    PreloadedDatasetSpec(
        key="engineering-data",
        name="Engineering & Data",
        categories=frozenset({"code_help", "data_analysis"}),
    ),
    PreloadedDatasetSpec(
        key="operations-planning",
        name="Operations & Planning",
        categories=frozenset({"task_management", "other"}),
    ),
)


def load_preloaded_records(
    settings: Settings, spec: PreloadedDatasetSpec
) -> list[dict]:
    path = Path(settings.DEMO_DATASET_PATH)
    raw_records = parse_raw(path.read_bytes(), path.name)
    return [
        row
        for row in raw_records
        if isinstance(row, dict) and str(row.get("category")) in spec.categories
    ]


async def seed_preloaded_datasets(settings: Settings | None = None) -> None:
    """Reconcile deterministic preloaded sources with ML, then recompute once."""
    settings = settings or get_settings()

    from database.relational_db import get_session_factory
    from service.dashboard import DashboardService
    from service.ml import MlClient
    from service.recompute import RecomputeService, finalize_recompute

    from .service import IngestionService, stream_source_logs

    client = MlClient(settings)
    factory = get_session_factory(settings)
    needs_recompute = False

    for spec in PRELOADED_DATASETS:
        async with factory() as session:
            result, created = await IngestionService(
                session, settings
            ).ensure_preloaded(spec)

        expected = result.source_out.records_valid
        observed = await client.get_assignment_count(result.source_id)
        already_recomputed = result.source_out.status.value == "recomputed"

        if observed < expected:
            logger.info(
                "preloading dataset key=%s source_id=%s assignments=%s/%s",
                spec.key,
                result.source_id,
                observed,
                expected,
            )
            await stream_source_logs(settings, result.source_id, result.log_records)
            needs_recompute = True
        else:
            async with factory() as session:
                await DashboardService(session, settings).sync_assignments(
                    result.source_id
                )
            needs_recompute = needs_recompute or created or not already_recomputed

    if needs_recompute and settings.PRELOAD_DATASETS_RECOMPUTE:
        job = await RecomputeService(settings).trigger()
        await finalize_recompute(settings, job.job_id)


async def run_preloaded_seed_safely(settings: Settings) -> None:
    try:
        await seed_preloaded_datasets(settings)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("preloaded dataset seed failed")


async def cancel_preloaded_seed(task: asyncio.Task[None] | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
