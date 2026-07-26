"""Unit tests for the ROI calculator (killer feature, D6 session coefficients)."""

import pytest
from service.roi.calculator import RoiConfig, compute_roi


def test_session_coeff_thresholds(roi_config: RoiConfig) -> None:
    # short: tokens <= short_max_tokens
    assert roi_config.session_coeff(0) == 0.3
    assert roi_config.session_coeff(4000) == 0.3
    # medium: between thresholds
    assert roi_config.session_coeff(4001) == 1.0
    assert roi_config.session_coeff(29999) == 1.0
    # long: tokens >= long_min_tokens
    assert roi_config.session_coeff(30000) == 2.0
    assert roi_config.session_coeff(100000) == 2.0


def test_empty_input_returns_zeroed_summary(roi_config: RoiConfig) -> None:
    roi = compute_roi([], roi_config)
    assert roi.summary.total_logs == 0
    assert roi.summary.total_fte_hours_saved == 0.0
    assert roi.summary.roi_multiplier == 0.0
    assert roi.summary.token_value_index == 0.0
    assert roi.by_category == []
    assert roi.by_scenario == []
    # assumptions still surfaced for the UI
    assert roi.assumptions.session_coefficients.long == 2.0


def test_single_success_medium_session(roi_config: RoiConfig, make_record) -> None:
    # 10000 tokens -> medium coeff (1.0); 30 min manual -> 0.5 h saved
    roi = compute_roi([make_record(tokens=10000, manual_time_minutes=30.0)], roi_config)
    s = roi.summary
    assert s.total_logs == 1
    assert s.success_rate_percent == 100.0
    assert s.total_fte_hours_saved == 0.5
    assert s.total_manual_cost_rub == 600.0  # 0.5h * 1200
    # agent cost = 10000/1000 * 0.015 = 0.15
    assert s.total_agent_cost_rub == 0.15
    assert s.net_savings_rub == 599.85
    assert s.roi_multiplier == 4000.0  # 600 / 0.15
    assert s.total_tokens_consumed == 10000
    assert s.wasted_tokens_on_errors == 0
    assert s.process_automation_rate == 100.0
    assert s.top_tools_used == {"CRM": 1}


def test_short_session_applies_030_coeff(roi_config: RoiConfig, make_record) -> None:
    # 1000 tokens -> short (0.3); 60 min -> 1.0h * 0.3 = 0.3h
    roi = compute_roi([make_record(tokens=1000, manual_time_minutes=60.0)], roi_config)
    assert roi.summary.total_fte_hours_saved == 0.3


def test_long_session_applies_2x_coeff(roi_config: RoiConfig, make_record) -> None:
    # 50000 tokens -> long (2.0); 30 min -> 0.5h * 2.0 = 1.0h
    roi = compute_roi([make_record(tokens=50000, manual_time_minutes=30.0)], roi_config)
    assert roi.summary.total_fte_hours_saved == 1.0


def test_error_record_saves_no_time_and_wastes_tokens(roi_config: RoiConfig, make_record) -> None:
    roi = compute_roi(
        [make_record(status="error_tool", tokens=5000, manual_time_minutes=30.0)],
        roi_config,
    )
    s = roi.summary
    assert s.success_rate_percent == 0.0
    assert s.total_fte_hours_saved == 0.0  # errors save nothing
    assert s.wasted_tokens_on_errors == 5000
    assert s.total_tokens_consumed == 5000
    assert s.process_automation_rate == 0.0  # tools only count on success


def test_zero_tokens_no_division_error(roi_config: RoiConfig, make_record) -> None:
    roi = compute_roi([make_record(tokens=0, manual_time_minutes=30.0)], roi_config)
    s = roi.summary
    assert s.total_agent_cost_rub == 0.0
    assert s.roi_multiplier == 0.0  # guarded: agent_cost == 0
    assert s.token_value_index == 0.0  # guarded: total_tokens == 0


def test_success_rate_and_mixed_records(roi_config: RoiConfig, make_record) -> None:
    records = [
        make_record(status="success", tokens=10000, manual_time_minutes=30.0),
        make_record(status="success", tokens=10000, manual_time_minutes=30.0),
        make_record(status="error_tool", tokens=10000, manual_time_minutes=30.0),
        make_record(status="hallucination_loop", tokens=10000, manual_time_minutes=30),
    ]
    s = compute_roi(records, roi_config).summary
    assert s.total_logs == 4
    assert s.success_rate_percent == 50.0
    assert s.total_fte_hours_saved == 1.0  # two 0.5h successes
    assert s.wasted_tokens_on_errors == 20000
    assert s.total_tokens_consumed == 40000


def test_grouping_by_category_and_scenario(roi_config: RoiConfig, make_record) -> None:
    records = [
        make_record(task_type="data_analysis", scenario_id="s1", scenario_name="A"),
        make_record(task_type="data_analysis", scenario_id="s1", scenario_name="A"),
        make_record(task_type="code_help", scenario_id="s2", scenario_name="B"),
    ]
    roi = compute_roi(records, roi_config)
    cats = {c.task_type: c for c in roi.by_category}
    assert cats["data_analysis"].count == 2
    assert cats["code_help"].count == 1
    assert cats["data_analysis"].label  # human label present
    scenarios = {sc.scenario_id: sc for sc in roi.by_scenario}
    assert scenarios["s1"].count == 2
    assert scenarios["s1"].name == "A"
    # sorted by count desc -> data_analysis first
    assert roi.by_category[0].task_type == "data_analysis"


def test_none_task_type_bucketed_as_unknown(roi_config: RoiConfig, make_record) -> None:
    # unclassified log (ML degraded) still counted under "unknown"
    roi = compute_roi([make_record(task_type=None, scenario_id=None)], roi_config)
    assert roi.by_category[0].task_type == "unknown"
    assert roi.by_scenario == []  # no scenario grouping without scenario_id


def test_rate_overrides_change_costs(make_record) -> None:
    config = RoiConfig(
        fte_hourly_rate_rub=2400.0,
        token_cost_per_1k_rub=0.03,
        coeff_short=0.3,
        coeff_medium=1.0,
        coeff_long=2.0,
        short_max_tokens=4000,
        long_min_tokens=30000,
    )
    roi = compute_roi([make_record(tokens=10000, manual_time_minutes=30.0)], config)
    assert roi.summary.total_manual_cost_rub == 1200.0  # 0.5h * 2400
    assert roi.summary.total_agent_cost_rub == 0.3  # 10 * 0.3


def test_missing_manual_time_uses_category_fallback(roi_config: RoiConfig, make_record) -> None:
    # None manual_time_minutes on code_help -> 30 min fallback * 1.0 coeff = 0.5h
    rec = make_record(tokens=10000, manual_time_minutes=None, task_type="code_help")
    roi = compute_roi([rec], roi_config)
    assert roi.summary.total_fte_hours_saved == 0.5


def test_case_insensitive_and_completed_status(roi_config: RoiConfig, make_record) -> None:
    rec1 = make_record(status="SUCCESS", tokens=10000, manual_time_minutes=30.0)
    rec2 = make_record(status="completed", tokens=10000, manual_time_minutes=30.0)
    roi = compute_roi([rec1, rec2], roi_config)
    assert roi.summary.success_rate_percent == 100.0
    assert roi.summary.total_fte_hours_saved == 1.0


# --- QNA §1: explicit B > A verdict and derived rates -----------------------


def test_verdict_states_payoff_explicitly(roi_config, make_record):
    """The B > A comparison must be an output, not something the reader infers."""
    roi = compute_roi(
        [make_record(status="success", manual_time_minutes=600.0, tokens=1000)],
        roi_config,
    )

    assert roi.verdict.pays_off is True
    assert roi.verdict.benefit_rub == roi.summary.total_manual_cost_rub
    assert roi.verdict.cost_rub == roi.summary.total_agent_cost_rub
    assert roi.verdict.net_rub == pytest.approx(
        roi.verdict.benefit_rub - roi.verdict.cost_rub
    )
    assert "окупается" in roi.verdict.headline


def test_verdict_reports_loss_when_cost_exceeds_benefit(roi_config, make_record):
    """A token-heavy failure saves nothing but still burns budget -> B < A."""
    roi = compute_roi(
        [make_record(status="error_tool", manual_time_minutes=5.0, tokens=50_000_000)],
        roi_config,
    )

    assert roi.verdict.benefit_rub == 0.0
    assert roi.verdict.cost_rub > 0
    assert roi.verdict.pays_off is False
    assert "не окупается" in roi.verdict.headline


def test_verdict_on_empty_input_is_not_a_false_positive(roi_config):
    roi = compute_roi([], roi_config)

    assert roi.verdict.pays_off is False
    assert roi.verdict.benefit_rub == 0.0
    assert roi.verdict.cost_rub == 0.0


def test_fte_hourly_rate_derived_from_monthly_salary():
    """QNA §1.1 reference: ~400 000 RUB/month, not a standalone hourly constant."""
    from core.config import Settings

    # _env_file=None: assert the shipped defaults, not the developer's local .env
    s = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://t:t@localhost/t",
        JWT_SECRET="super-secret-test-key-32-chars-long!",
    )

    assert s.ROI_FTE_HOURLY_RATE_RUB is None
    assert s.roi_fte_hourly_rate == pytest.approx(400_000.0 / 168.0)


def test_token_cost_uses_the_mandated_price():
    """The organisers fix 139 RUB per million so teams' numbers compare."""
    from core.config import Settings

    # _env_file=None: assert the shipped defaults, not the developer's local .env
    s = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://t:t@localhost/t",
        JWT_SECRET="super-secret-test-key-32-chars-long!",
    )

    assert s.ROI_TOKEN_COST_PER_1K_RUB is None
    assert s.ROI_TOKEN_COST_PER_MLN_RUB == 139.0
    assert s.roi_token_cost_per_1k == pytest.approx(0.139)


def test_infra_derivation_kept_as_sanity_check():
    """The independent derivation stays available but no longer sets the price."""
    from core.config import Settings

    s = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://t:t@localhost/t",
        JWT_SECRET="super-secret-test-key-32-chars-long!",
    )
    expected = (100_000_000.0 / 5.0 + 600_000.0) / 20_000_000_000.0 * 1000.0

    assert s.roi_infra_token_cost_per_1k == pytest.approx(expected)
    assert s.roi_infra_token_cost_per_1k != s.roi_token_cost_per_1k


def test_analysis_cost_is_reported(roi_config, make_record):
    """The expert asked what classification itself costs — it must be an output."""
    records = [make_record(status="success", tokens=1000, query_chars=300) for _ in range(10)]

    roi = compute_roi(records, roi_config)
    model = roi.assumptions.analysis_cost_model

    assert model is not None
    # 10 records x 300 chars, all in one scenario -> one summarisation pass
    assert model.embedding_tokens == int(3000 / model.chars_per_token)
    assert model.summarization_tokens == int(model.tokens_per_scenario)
    expected_cost = (
        (model.embedding_tokens + model.summarization_tokens) / 1000.0
    ) * roi_config.token_cost_per_1k_rub
    assert model.cost_rub == pytest.approx(expected_cost, abs=0.01)
    assert model.cost_per_request_rub > 0


def test_explicit_rate_overrides_win_over_derivation():
    from core.config import Settings

    s = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://t:t@localhost/t",
        JWT_SECRET="super-secret-test-key-32-chars-long!",
        ROI_FTE_HOURLY_RATE_RUB=1200.0,
        ROI_TOKEN_COST_PER_1K_RUB=0.1,
    )

    assert s.roi_fte_hourly_rate == 1200.0
    assert s.roi_token_cost_per_1k == 0.1
