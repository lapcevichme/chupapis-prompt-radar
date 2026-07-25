from pathlib import Path
from types import SimpleNamespace

from service.ingestion.preloaded import PRELOADED_DATASETS, load_preloaded_records


def test_preloaded_datasets_are_distinct_and_cover_demo_fixture() -> None:
    settings = SimpleNamespace(
        DEMO_DATASET_PATH=str(
            Path(__file__).resolve().parents[1] / "src" / "data" / "demo_dataset.json"
        )
    )

    source_ids = {str(spec.source_id) for spec in PRELOADED_DATASETS}
    category_sets = [spec.categories for spec in PRELOADED_DATASETS]
    counts = [len(load_preloaded_records(settings, spec)) for spec in PRELOADED_DATASETS]

    assert len(source_ids) == len(PRELOADED_DATASETS) == 3
    assert all(category_sets[i].isdisjoint(category_sets[j]) for i in range(3) for j in range(i))
    assert counts == [170, 106, 109]
    assert sum(counts) == 385
