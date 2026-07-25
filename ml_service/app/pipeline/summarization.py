"""LLM scenario summarization via LangChain Chat + Pydantic structured output.

    chat = chat_openrouter(...)  # or chat_ollama(...)
    structured = chat.with_structured_output(ScenarioSummary)
    result = await structured.ainvoke(prompt)
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.adapters.llm import chat_from_settings, chat_ollama, chat_openrouter

logger = logging.getLogger(__name__)

_AUTOMATION = frozenset({"low", "medium", "high"})


def _word_count(name: str) -> int:
    return len([w for w in (name or "").strip().split() if w])


def extract_json(text: str) -> Any:
    """Legacy helper for unit tests that parse fenced JSON."""
    import json
    import re

    text = (text or "").strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def technical_summary(
    scenario_id: str,
    task_type: str,
    examples: Optional[List[str]] = None,
) -> "ScenarioSummary":
    try:
        n = int(scenario_id.rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        n = 0
    name = f"Сценарий {task_type} {n}"
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
    """Structured LLM output for a scenario (ТЗ §8.9)."""

    name: str = Field(description="Short scenario name, at most 4 words")
    summary: str = Field(description="2-3 sentence summary of the use-case")
    user_goal: str = Field(description="What the user wants to achieve")
    pain_points: List[str] = Field(
        default_factory=list,
        description="User pains / friction points",
    )
    automation_potential: str = Field(description="One of: low, medium, high")
    examples: List[str] = Field(
        default_factory=list,
        description="2-5 short example queries",
    )

    model_config = {"extra": "ignore"}

    @field_validator("name")
    @classmethod
    def name_max_four_words(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("name must be non-empty")
        if _word_count(v) > 4:
            v = " ".join(v.split()[:4])
        return v

    @field_validator("automation_potential")
    @classmethod
    def automation_enum(cls, v: str) -> str:
        v = (v or "low").strip().lower()
        return v if v in _AUTOMATION else "low"


class Summarizer:
    """Thin wrapper: pick Chat provider → with_structured_output(ScenarioSummary)."""

    def __init__(
        self,
        *,
        backend: str = "openrouter",
        api_key: str = "",
        model: str = "google/gemma-4-26b-a4b-it",
        base_url: str = "",
        max_retries: int = 2,
        scenario_name_max_words: int = 4,
        temperature: float = 0.3,
        chat_model: Any = None,
    ) -> None:
        self.backend = (backend or "openrouter").lower()
        self.api_key = api_key or ""
        self.model = model
        self.base_url = base_url
        self.max_retries = max(0, int(max_retries))
        self.scenario_name_max_words = int(scenario_name_max_words)
        self.temperature = temperature
        self._chat = chat_model
        # compat for old logs/tests
        self.url = base_url or (
            "openrouter"
            if self.backend == "openrouter"
            else (base_url or "http://127.0.0.1:11434")
        )

    def _chat_model(self):
        if self._chat is not None:
            return self._chat
        if self.backend == "ollama":
            self._chat = chat_ollama(
                model=self.model,
                base_url=self.base_url or "http://127.0.0.1:11434",
                temperature=self.temperature,
            )
        else:
            self._chat = chat_openrouter(
                model=self.model,
                api_key=self.api_key,
                temperature=self.temperature,
            )
        return self._chat

    def _structured(self):
        return self._chat_model().with_structured_output(ScenarioSummary)

    @classmethod
    def from_settings(cls, settings: Any = None, **overrides: Any) -> "Summarizer":
        if settings is None:
            from app.core.config import settings as default_settings

            settings = default_settings
        llm = settings.llm
        backend = overrides.get("backend") or llm.resolve_provider()
        if backend == "ollama":
            return cls(
                backend="ollama",
                model=overrides.get("model") or llm.ollama_model,
                base_url=overrides.get("base_url") or llm.ollama_url,
                max_retries=int(
                    overrides.get("max_retries", settings.summarization.max_llm_retries)
                ),
                scenario_name_max_words=int(settings.summarization.scenario_name_max_words),
            )
        return cls(
            backend="openrouter",
            api_key=overrides.get("api_key") or llm.openrouter_api_key,
            model=overrides.get("model") or llm.openrouter_model,
            base_url=overrides.get("base_url") or llm.openrouter_url,
            max_retries=int(
                overrides.get("max_retries", settings.summarization.max_llm_retries)
            ),
            scenario_name_max_words=int(settings.summarization.scenario_name_max_words),
        )

    @classmethod
    def from_config(cls, config: Optional[dict] = None, **overrides: Any) -> "Summarizer":
        import os

        cfg = config or {}
        sum_cfg = cfg.get("summarization") or {}
        llm = cfg.get("llm") or cfg.get("models", {}).get("llm") or {}
        mode = (llm.get("mode") or os.getenv("LLM_MODE") or "offline").lower()
        if mode in ("online", "openrouter", "cloud"):
            openrouter = llm.get("openrouter") or {}
            return cls(
                backend="openrouter",
                api_key=overrides.get("api_key")
                or openrouter.get("api_key")
                or os.getenv("OPENROUTER_API_KEY", ""),
                model=overrides.get("model")
                or openrouter.get("model_name")
                or "google/gemma-4-26b-a4b-it",
                max_retries=int(
                    overrides.get("max_retries", sum_cfg.get("max_llm_retries", 2))
                ),
                scenario_name_max_words=int(sum_cfg.get("scenario_name_max_words", 4)),
            )
        ollama = llm.get("ollama") or {}
        return cls(
            backend="ollama",
            model=overrides.get("model")
            or ollama.get("model_name")
            or os.getenv("OLLAMA_LLM_MODEL")
            or "gemma4:26b-a4b-it",
            base_url=overrides.get("url")
            or ollama.get("url")
            or os.getenv("OLLAMA_URL")
            or "http://127.0.0.1:11434",
            max_retries=int(
                overrides.get("max_retries", sum_cfg.get("max_llm_retries", 2))
            ),
            scenario_name_max_words=int(sum_cfg.get("scenario_name_max_words", 4)),
        )

    async def close(self) -> None:
        self._chat = None

    def is_available(self) -> bool:
        return self.backend == "ollama" or bool(self.api_key)

    async def summarize_scenario(
        self,
        scenario_id: str,
        examples: List[str],
        task_type: str,
    ) -> ScenarioSummary:
        if not examples:
            return technical_summary(scenario_id, task_type, examples)
        if self.backend == "openrouter" and not self.api_key:
            logger.info("No OpenRouter api_key — technical fallback for %s", scenario_id)
            return technical_summary(scenario_id, task_type, examples)

        prompt = self._build_prompt(scenario_id, examples, task_type)
        structured = self._structured()
        last_err: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                result = await structured.ainvoke(prompt)
                if isinstance(result, ScenarioSummary):
                    summary = result
                elif isinstance(result, dict):
                    summary = ScenarioSummary.model_validate(result)
                elif hasattr(result, "model_dump"):
                    summary = ScenarioSummary.model_validate(result.model_dump())
                else:
                    raise TypeError(f"unexpected structured type: {type(result)}")

                if _word_count(summary.name) > self.scenario_name_max_words:
                    words = summary.name.split()[: self.scenario_name_max_words]
                    summary = summary.model_copy(update={"name": " ".join(words)})
                if not summary.examples:
                    summary = summary.model_copy(update={"examples": examples[:5]})
                return summary
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning(
                    "summarize attempt %s/%s failed for %s (%s): %s",
                    attempt + 1,
                    self.max_retries + 1,
                    scenario_id,
                    self.backend,
                    exc,
                )

        logger.error("LLM summarization failed for %s: %s", scenario_id, last_err)
        return technical_summary(scenario_id, task_type, examples)

    def _build_prompt(
        self,
        scenario_id: str,
        examples: List[str],
        task_type: str,
    ) -> str:
        examples_text = "\n".join(f"- {ex}" for ex in examples)
        return f"""Ты — эксперт по бизнес-процессам и ИИ-агентам в крупной компании.

Сценарий ID: {scenario_id}
Тип задачи (task_type): {task_type}

Примеры запросов:
{examples_text}

Заполни поля схемы ScenarioSummary по примерам.
Правила: не выдумывай факты; по-русски если примеры на русском;
name ≤ 4 слов; automation_potential = low|medium|high.
"""
