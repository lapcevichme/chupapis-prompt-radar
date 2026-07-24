# PR F — Statistics aggregation contract

## Goal

Full `GET /api/v1/statistics` aggregation per ТЗ §8.8–8.11 and `docs/contracts/statistics.schema.json`.

## Implemented

| Area | Location |
|------|----------|
| Statistics builder (totals, Top-N, dynamics, trends, failure, freshness) | `app/pipeline/aggregation/builder.py` |
| Package exports | `app/pipeline/aggregation/__init__.py` |
| Wire `GET /statistics` to builder | `app/main.py` |
| `GET /scenarios` + `GET /scenarios/{id}` | `app/main.py` |
| Failure signals preserved on ingest | `app/main.py` (`_collect_failure_fields`) |
| Unit + contract tests | `tests/test_aggregation.py` |
| Smoke asserts contract fields | `tests/test_smoke.py` |
| `jsonschema` dependency | `pyproject.toml` |

## Aggregation rules

- **totals:** `records_total`, `scenarios_count`, `unknown_count`, `outliers_percentage`
- **tasks_distribution:** Top-N + `other` tail; **`unknown` never merged into `other`**
- **top_scenarios:** Top-N + `other` with `summary: null` (no fake summary)
- **dynamics:** counts by ISO date
- **trends (half-period):** `up` / `down` / `stable` / `new` / `insufficient_data` (threshold default 10%)
- **outliers_summary:** count + percentage
- **failure_analysis:** `available` when signals present (`response_status`, `error_code`, `user_feedback`, `retry_count`); else `not_available`
- **freshness:** `last_recompute_at`, `logs_since_last_recompute`, `recompute_pending`
- **filters_applied**, **schema_version**, **taxonomy_version**, **pipeline_version**, full **pipeline_metadata**

## Config defaults (`config.yaml` / env)

- `top_tasks_limit=7` (`TOP_TASKS_LIMIT`)
- `top_scenarios_limit=9` (`TOP_SCENARIOS_LIMIT`)
- `trend_threshold_percent=10.0` (`TREND_THRESHOLD_PERCENT`)

## How to verify

```bash
cd ml_service
python -m pytest tests/test_aggregation.py tests/test_smoke.py -v
```

Contract test loads `docs/contracts/statistics.schema.json` via `jsonschema.Draft202012Validator`.

## Status

**PR F completed.**
