import json
import asyncio
import aiohttp
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field

def extract_json(text: str) -> Any:
    """Надежное извлечение JSON из ответа модели."""
    text = text.strip()
    import re
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)

class ScenarioSummary(BaseModel):
    """Structured output for scenario summarization."""
    name: str = Field(..., description="Short name (≤ 4 words)")
    summary: str
    user_goal: str
    pain_points: List[str] = Field(default_factory=list)
    automation_potential: str = Field(..., description="low | medium | high")
    examples: List[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

class Summarizer:
    """LLM-based summarizer for scenarios using OpenRouter."""
    
    def __init__(self, api_key: str, model: str = "google/gemma-4-26b-a4b-it"):
        self.api_key = api_key
        self.model = model
        self.url = "https://openrouter.ai/api/v1/chat/completions"
    
    async def summarize_scenario(self, scenario_id: str, examples: List[str], task_type: str) -> ScenarioSummary:
        """Generate structured summary for a scenario using representative examples."""
        # Build prompt similar to dataset
        prompt = self._build_summarization_prompt(scenario_id, examples, task_type)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo/prompt-radar",
            "X-Title": "PromptRadar_Summarizer"
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "provider": {"order": ["DeepSeek"], "allow_fallbacks": False},
            "temperature": 0.3
        }
        
        try:
            async with aiohttp.ClientSession() as session:  # Note: need to import aiohttp
                async with session.post(self.url, headers=headers, json=payload, timeout=60) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data["choices"][0]["message"]["content"]
                        parsed = extract_json(content)
                        if isinstance(parsed, dict):
                            return ScenarioSummary(**parsed)
        except Exception as e:
            print(f"Error summarizing {scenario_id}: {str(e)}")
            # Fallback to technical name
            return ScenarioSummary(
                name=f"Scenario {scenario_id.split(':')[-1]}",
                summary="Summary unavailable",
                user_goal="Unknown",
                pain_points=[],
                automation_potential="low",
                examples=[]
            )
        return None  # or raise
    
    def _build_summarization_prompt(self, scenario_id: str, examples: List[str], task_type: str) -> str:
        """Build the LLM prompt for summarization."""
        examples_text = "\n".join([f"- {ex}" for ex in examples])
        prompt = f"""Ты — эксперт по бизнес-процессам и ИИ-агентам в крупной компании.

Сценарий ID: {scenario_id}
Тип задачи: {task_type}

Примеры запросов:
{examples_text}

На основе примеров сгенерируй структурированное саммари:
- Краткое название (≤ 4 слова)
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
- Не выдумывай факты из примеров.
- Используй примеры для точности.
- Если мало данных — укажи 'insufficient examples'.
"""
        return prompt
