"""LLM scenario summarization: offline (Ollama) | online (OpenRouter).

Models (same family):
  offline → Ollama chat gemma4:26b-a4b-it
  online  → OpenRouter google/gemma-4-26b-a4b-it
"""

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
    """LLM summarizer: backend ollama (offline) or openrouter (online)."""

    def __init__(
        self,
        *,
        backend: str = "openrouter",
        api_key: str = "",
        model: str = "google/gemma-4-26b-a4b-it",
        url: str = "https://openrouter.ai/api/v1/chat/completions",
        max_retries: int = 2,
        scenario_name_max_words: int = 4,
        timeout_sec: float = 120.0,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self.backend = (backend or "openrouter").lower()
        self.api_key = api_key or ""
        self.model = model
        self.url = url
        self.max_retries = max(0, int(max_retries))
        self.scenario_name_max_words = int(scenario_name_max_words)
        self.timeout_sec = timeout_sec
        self._session = session
        self._owns_session = session is None

    @classmethod
    def from_settings(cls, settings: Any = None, **overrides: Any) -> "Summarizer":
        """Build from app Settings (mode offline/online)."""
        if settings is None:
            from app.core.config import settings as default_settings

            settings = default_settings
        llm = settings.llm
        backend = overrides.get("backend") or llm.resolve_provider()
        if backend == "ollama":
            base = (overrides.get("url") or llm.ollama_url or "http://127.0.0.1:11434").rstrip(
                "/"
            )
            url = base if base.endswith("/api/chat") else f"{base}/api/chat"
            model = overrides.get("model") or llm.ollama_model or "gemma4:26b-a4b-it"
            api_key = ""
        else:
            url = (
                overrides.get("url")
                or llm.openrouter_url
                or "https://openrouter.ai/api/v1/chat/completions"
            )
            model = (
                overrides.get("model")
                or llm.openrouter_model
                or "google/gemma-4-26b-a4b-it"
            )
            api_key = overrides.get("api_key") or llm.openrouter_api_key or ""
        sum_cfg = settings.summarization
        return cls(
            backend=backend,
            api_key=api_key,
            model=model,
            url=url,
            max_retries=int(
                overrides.get("max_retries", sum_cfg.max_llm_retries)
            ),
            scenario_name_max_words=int(sum_cfg.scenario_name_max_words),
            timeout_sec=float(overrides.get("timeout_sec", llm.timeout_sec)),
        )

    @classmethod
    def from_config(cls, config: Optional[dict] = None, **overrides: Any) -> "Summarizer":
        """Legacy dict config; prefer from_settings."""
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
                url=overrides.get("url")
                or openrouter.get("url")
                or os.getenv(
                    "OPENROUTER_CHAT_URL",
                    "https://openrouter.ai/api/v1/chat/completions",
                ),
                max_retries=int(
                    overrides.get("max_retries", sum_cfg.get("max_llm_retries", 2))
                ),
                scenario_name_max_words=int(sum_cfg.get("scenario_name_max_words", 4)),
            )
        ollama = llm.get("ollama") or {}
        base = (
            overrides.get("url")
            or ollama.get("url")
            or os.getenv("OLLAMA_LLM_URL")
            or os.getenv("OLLAMA_URL")
            or "http://127.0.0.1:11434"
        ).rstrip("/")
        url = base if base.endswith("/api/chat") else f"{base}/api/chat"
        return cls(
            backend="ollama",
            api_key="",
            model=overrides.get("model")
            or ollama.get("model_name")
            or os.getenv("OLLAMA_LLM_MODEL")
            or "gemma4:26b-a4b-it",
            url=url,
            max_retries=int(
                overrides.get("max_retries", sum_cfg.get("max_llm_retries", 2))
            ),
            scenario_name_max_words=int(sum_cfg.get("scenario_name_max_words", 4)),
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

    def is_available(self) -> bool:
        if self.backend == "ollama":
            return True  # local; readiness probe is optional
        return bool(self.api_key)

    async def summarize_scenario(
        self,
        scenario_id: str,
        examples: List[str],
        task_type: str,
    ) -> ScenarioSummary:
        """Generate structured summary; fallback to technical name on failure."""
        if not examples:
            return technical_summary(scenario_id, task_type, examples)

        if self.backend == "openrouter" and not self.api_key:
            logger.info("No OpenRouter api_key — technical fallback for %s", scenario_id)
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
                    attempts,
                    scenario_id,
                    self.backend,
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
        if self.backend == "ollama":
            return await self._call_ollama(prompt)
        return await self._call_openrouter(prompt)

    async def _call_openrouter(self, prompt: str) -> str:
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
                raise RuntimeError(f"OpenRouter HTTP {response.status}: {body[:200]}")
            data = await response.json()
            return data["choices"][0]["message"]["content"]

    async def _call_ollama(self, prompt: str) -> str:
        """Ollama /api/chat — local Gemma-class model."""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.3},
        }
        session = await self._get_session()
        async with session.post(self.url, json=payload) as response:
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(f"Ollama HTTP {response.status}: {body[:200]}")
            data = await response.json(content_type=None)
            # chat response: message.content
            msg = data.get("message") or {}
            content = msg.get("content") or data.get("response") or ""
            if not content:
                raise RuntimeError("Ollama returned empty content")
            return content

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
- Если мало данных — укажи 'insufficient examples' в summary.
"""
