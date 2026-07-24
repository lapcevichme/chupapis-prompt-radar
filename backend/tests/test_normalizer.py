"""Unit tests for dataset normalization (backend-ml.md §1 mapping)."""

from types import SimpleNamespace

from service.ingestion.normalizer import normalize, parse_raw


def test_maps_user_query_and_status(normalize_settings: SimpleNamespace) -> None:
    raw = [
        {
            "user_query": "  Выгрузи отчёт из CRM  ",
            "status": "success",
            "simulated_context_tokens": 12000,
            "estimated_manual_time_minutes": 30,
            "tools_used": ["CRM"],
            "category": "data_analysis",
            "style": "formal",
        }
    ]
    result = normalize(raw, normalize_settings)
    assert len(result.log_records) == 1
    log = result.log_records[0]
    assert log["query_text"] == "Выгрузи отчёт из CRM"  # trimmed
    assert log["response_status"] == "success"
    assert log["error_code"] is None
    assert log["metadata"]["gold_category"] == "data_analysis"
    assert log["metadata"]["tokens"] == 12000

    row = result.dataset_rows[0]
    assert row.tokens == 12000
    assert row.manual_time_minutes == 30.0
    assert row.tools_used == ["CRM"]
    assert row.status == "success"


def test_query_text_alias_supported(normalize_settings: SimpleNamespace) -> None:
    # live webhook / demo dataset may send query_text instead of user_query
    result = normalize([{"query_text": "hello"}], normalize_settings)
    assert result.log_records[0]["query_text"] == "hello"


def test_status_map_errors(normalize_settings: SimpleNamespace) -> None:
    raw = [
        {"user_query": "a", "status": "error_tool"},
        {"user_query": "b", "status": "hallucination_loop"},
        {"user_query": "c", "status": "weird_unknown_status"},
    ]
    logs = normalize(raw, normalize_settings).log_records
    assert (logs[0]["response_status"], logs[0]["error_code"]) == ("error", "tool_error")
    assert logs[1]["error_code"] == "hallucination_loop"
    # unknown status falls back to success/none, does not reject the row
    assert (logs[2]["response_status"], logs[2]["error_code"]) == ("success", None)


def test_synthesizes_request_id_by_index(normalize_settings: SimpleNamespace) -> None:
    raw = [{"user_query": "a"}, {"user_query": "b"}]
    logs = normalize(raw, normalize_settings, id_prefix="live_").log_records
    assert logs[0]["request_id"] == "live_0"
    assert logs[1]["request_id"] == "live_1"


def test_honors_incoming_request_id(normalize_settings: SimpleNamespace) -> None:
    logs = normalize(
        [{"user_query": "a", "request_id": "req_custom"}], normalize_settings
    ).log_records
    assert logs[0]["request_id"] == "req_custom"


def test_rejects_empty_query(normalize_settings: SimpleNamespace) -> None:
    raw = [{"user_query": "ok"}, {"user_query": "   "}, {"status": "success"}, "notdict"]
    result = normalize(raw, normalize_settings)
    assert result.report["records_total"] == 4
    assert result.report["records_valid"] == 1
    assert result.report["records_rejected"] == 3
    assert result.report["rejected_reasons"]["empty_query_text"] == 2
    assert result.report["rejected_reasons"]["not_an_object"] == 1


def test_timestamps_synthesized_within_span(normalize_settings: SimpleNamespace) -> None:
    raw = [{"user_query": f"q{i}"} for i in range(5)]
    rows = normalize(raw, normalize_settings).dataset_rows
    # ascending across the span
    stamps = [r.timestamp for r in rows]
    assert stamps == sorted(stamps)


def test_timestamps_disabled(normalize_settings: SimpleNamespace) -> None:
    normalize_settings.NORMALIZE_SYNTHESIZE_TIMESTAMPS = False
    result = normalize([{"user_query": "a"}], normalize_settings)
    assert result.report["synthesized_timestamp"] == 0


def test_parse_raw_json_and_jsonl() -> None:
    assert parse_raw(b'[{"user_query": "a"}]', "data.json") == [{"user_query": "a"}]
    jsonl = b'{"user_query": "a"}\n{"user_query": "b"}\n'
    assert parse_raw(jsonl, "data.jsonl") == [{"user_query": "a"}, {"user_query": "b"}]


def test_parse_raw_wrapped_records() -> None:
    assert parse_raw(b'{"records": [{"user_query": "a"}]}', "x.json") == [
        {"user_query": "a"}
    ]


def test_parse_raw_csv_coerces_types() -> None:
    csv_bytes = (
        b"user_query,status,simulated_context_tokens,tools_used\n"
        b'hello,success,5000,"CRM,Mail"\n'
    )
    rows = parse_raw(csv_bytes, "data.csv")
    assert rows[0]["simulated_context_tokens"] == 5000
    assert rows[0]["tools_used"] == ["CRM", "Mail"]
