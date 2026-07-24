"""Unit tests for scenario summarization (fallback path)."""
from __future__ import annotations

import pytest

from app.pipeline.summarization import ScenarioSummary, Summarizer, extract_json


def test_extract_json_raw():
    raw = (
        '{"name": "Test Scenario", "summary": "Test summary", '
        '"user_goal": "Test goal", "pain_points": ["test"], '
        '"automation_potential": "high"}'
    )
    data = extract_json(raw)
    assert data["name"] == "Test Scenario"


def test_extract_json_fenced():
    raw = '```json\n{"name": "A B", "summary": "s", "user_goal": "g", "pain_points": [], "automation_potential": "low"}\n```'
    data = extract_json(raw)
    assert data["name"] == "A B"


def test_scenario_summary_model():
    s = ScenarioSummary(
        name="Code review",
        summary="Helps with reviews",
        user_goal="Faster PR feedback",
        pain_points=["noise"],
        automation_potential="high",
    )
    assert s.name == "Code review"


def test_summarizer_init():
    s = Summarizer(api_key="test-key")
    assert "gemma" in s.model or s.model
