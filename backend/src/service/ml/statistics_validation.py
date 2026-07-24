from typing import Any

from core.errors import StatisticsSchemaInvalidError

# Semantic check against statistics.schema.json (required keys only, no jsonschema dep).


def validate_statistics(payload: Any) -> dict[str, Any]:
    """Validate the ML /statistics response by meaning; raise on mismatch."""
    if not isinstance(payload, dict):
        raise StatisticsSchemaInvalidError("Statistics payload is not an object")

    for key in ("schema_version", "generated_at", "totals", "tasks_distribution"):
        if key not in payload:
            raise StatisticsSchemaInvalidError(f"Missing required field: {key}")

    totals = payload["totals"]
    if not isinstance(totals, dict) or "records_total" not in totals:
        raise StatisticsSchemaInvalidError("totals.records_total is required")

    if not isinstance(payload["tasks_distribution"], list):
        raise StatisticsSchemaInvalidError("tasks_distribution must be a list")

    for item in payload["tasks_distribution"]:
        if not isinstance(item, dict) or "task_type" not in item or "count" not in item:
            raise StatisticsSchemaInvalidError(
                "tasks_distribution items need task_type and count"
            )

    if "top_scenarios" in payload and not isinstance(payload["top_scenarios"], list):
        raise StatisticsSchemaInvalidError("top_scenarios must be a list")

    return payload
