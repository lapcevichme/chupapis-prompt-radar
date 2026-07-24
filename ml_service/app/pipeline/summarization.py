"""LLM scenario summarization with Pydantic validation, retries, and technical fallback."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional

import aiohttp
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

_AUTOMATION = frozenset({"low", "medium", "high"})


def extract_json(text: str) -> Any:
    """Robust JSON extraction from model output (raw or fenced)."""
    text = (text or "").strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def _word_count(name: str) -> int:
    return len([w for w in (name or "").strip().split() if w])


def technical_summary(
    scenario_id: str,
    task_type: str,
    examples: Optional[List[str]] = None,
) -> "ScenarioSummary":
    """Fallback structured summary when LLM is unavailable or invalid."""
    try:
        n = int(scenario_id.rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        n = 0
    name = f"Сценарий {task_type} {n}"
    # keep ≤ 4 words if task_type is long
    words = name.split()
    if len(words) > 4:
        name = " ".join(words[:4])
    return ScenarioSummary(
        name=name,
        summary="Summary unavailable",
        user_goal="Unknown",
        pain_points=[],
        automation_potential="low",
        examples=list(examples or [])[:5],
    )


class ScenarioSummary(BaseModel):
    """Structured output for scenario summarization (ТЗ §8.9)."""

    name: str = Field(..., description="Short name (≤ 4 words)")
    summary: str
    user_goal: str
    pain_points: List[str] = Field(default_factory=list)
    automation_potential: str = Field(..., description="low | medium | high")
    examples: List[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

    @field_validator("name")
    @classmethod
    def name_max_four_words(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("name must be non-empty")
        if _word_count(v) > 4:
            # soft-trim rather than hard-fail for slightly long names from LLM
            words = v.split()
            v = " ".join(words[:4])
        return v

    @field_validator("automation_potential")
    @classmethod
    def automation_enum(cls, v: str) -> str:
        v = (v or "low").strip().lower()
        if v not in _AUTOMATION:
            return "low"
        return v


class Summarizer:
    """LLM-based summarizer for scenarios (OpenRouter-compatible chat API)."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "google/gemma-4-26b-a4b-it",
        *,
        url: str = "https://openrouter.ai/api/v1/chat/completions",
        max_retries: int = 2,
        scenario_name_max_words: int = 4,
        timeout_sec: float = 60.0,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self.api_key = api_key or ""
        self.model = model
        self.url = url
        self.max_retries = max(0, int(max_retries))
        self.scenario_name_max_words = int(scenario_name_max_words)
        self.timeout_sec = timeout_sec
        self._session = session
        self._owns_session = session is None

    @classmethod
    def from_config(cls, config: Optional[dict] = None, **overrides: Any) -> "Summarizer":
        """Build from config.yaml-like dict + env-friendly overrides."""
        import os

        cfg = config or {}
        sum_cfg = cfg.get("summarization") or {}
        llm = cfg.get("llm") or cfg.get("models", {}).get("llm") or {}
        openrouter = llm.get("openrouter") or {}
        api_key = overrides.get("api_key") or os.getenv("OPENROUTER_API_KEY", "")
        model = (
            overrides.get("model")
            or openrouter.get("model_name")
            or "google/gemma-4-26b-a4b-it"
        )
        url = (
            overrides.get("url")
            or openrouter.get("url")
            or os.getenv("OPENROUTER_CHAT_URL", "https://openrouter.ai/api/v1/chat/completions")
        )
        return cls(
            api_key=api_key,
            model=model,
            url=url,
            max_retries=int(
                overrides.get("max_retries", sum_cfg.get("max_llm_retries", 2))
            ),
            scenario_name_max_words=int(
                sum_cfg.get("scenario_name_max_words", 4)
            ),
        )

    async def close(self) -> None:
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_sec)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._owns_session = True
        return self._session

    async def summarize_scenario(
        self,
        scenario_id: str,
        examples: List[str],
        task_type: str,
    ) -> ScenarioSummary:
        """
        Generate structured summary. Retries on invalid JSON/schema;
        falls back to technical name.
        """
        if not examples:
            return technical_summary(scenario_id, task_type, examples)

        if not self.api_key:
            logger.info("No LLM api_key — technical fallback for %s", scenario_id)
            return technical_summary(scenario_id, task_type, examples)

        prompt = self._build_summarization_prompt(scenario_id, examples, task_type)
        last_err: Optional[Exception] = None
        attempts = self.max_retries + 1

        for attempt in range(attempts):
            try:
                content = await self._call_llm(prompt)
                parsed = extract_json(content)
                if not isinstance(parsed, dict):
                    raise ValueError("LLM response is not a JSON object")
                summary = ScenarioSummary(**parsed)
                # enforce max words strictly after soft-trim validator
                if _word_count(summary.name) > self.scenario_name_max_words:
                    words = summary.name.split()[: self.scenario_name_max_words]
                    summary = summary.model_copy(update={"name": " ".join(words)})
                if not summary.examples:
                    summary = summary.model_copy(update={"examples": examples[:5]})
                return summary
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning(
                    "summarize attempt %s/%s failed for %s: %s",
                    attempt + 1,
                    attempts,
                    scenario_id,
                    exc,
                )

        logger.error(
            "LLM summarization failed for %s after %s attempts: %s",
            scenario_id,
            attempts,
            last_err,
        )
        return technical_summary(scenario_id, task_type, examples)

    async def _call_llm(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/prompt-radar",
            "X-Title": "PromptRadar_Summarizer",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }
        session = await self._get_session()
        async with session.post(self.url, headers=headers, json=payload) as response:
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(f"LLM HTTP {response.status}: {body[:200]}")
            data = await response.json()
            return data["choices"][0]["message"]["content"]

    def _build_summarization_prompt(
        self,
        scenario_id: str,
        examples: List[str],
        task_type: str,
    ) -> str:
        examples_text = "\n".join(f"- {ex}" for ex in examples)
        return f"""Ты — эксперт по бизнес-процессам и ИИ-агентам в крупной компании.

Сценарий ID: {scenario_id}
Тип задачи: {task_type}

Примеры запросов:
{examples_text}

На основе примеров сгенерируй структурированное саммари:
- Краткое название (≤ 4 слов)
- Краткий summary (2-3 предложения)
- user_goal: что хочет пользователь
- pain_points: список болей/проблем
- automation_potential: low/medium/high

Формат строго JSON:
{{
  "name": "...",
  "summary": "...",
  "user_goal": "...",
  "pain_points": ["проблема1", "проблема2"],
  "automation_potential": "medium"
}}

Правила:
- Не выдумывай факты вне примеров.
- Используй только информацию из примеров.
- Если мало данных — укажи 'insufficient examples'.
"""
