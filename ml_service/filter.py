from pydantic import BaseModel, Field
import json
import os
import asyncio
from datetime import datetime, timezone


class Filter:
    class Valves(BaseModel):
        LOG_FILE_PATH: str = Field(
            default="/app/backend/data/input.jsonl",
            description="Путь локального сбора логов в файл JSONL",
        )
        BACKEND_URL: str = Field(
            default="http://backend:8000/api/v1/logs",
            description="HTTP endpoint бэкенда для логирования",
        )
        BACKEND_SERVICE_TOKEN: str = Field(
            default="",
            description="Секретный токен авторизации бэкенда (X-Service-Token / Bearer)",
        )
        ENABLE_HTTP_STREAMING: bool = Field(
            default=True,
            description="Включить асинхронную отправку логов по HTTP на бэкенд",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _extract_text_from_content(self, content) -> str:
        """Извлекает текст вне зависимости от того, строка это или список блоков."""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif isinstance(item, str):
                    texts.append(item)
            return " ".join(texts)
        return ""

    async def _send_log_to_backend(self, log_entry: dict):
        """Асинхронная отправка лога на эндпоинт бэкенда с использованием aiohttp."""
        if not self.valves.ENABLE_HTTP_STREAMING or not self.valves.BACKEND_URL:
            return

        try:
            import aiohttp

            headers = {
                "Content-Type": "application/json",
            }
            if self.valves.BACKEND_SERVICE_TOKEN:
                headers["Authorization"] = f"Bearer {self.valves.BACKEND_SERVICE_TOKEN}"
                headers["X-Service-Token"] = self.valves.BACKEND_SERVICE_TOKEN

            payload = {
                "source_id": "open_webui",
                "logs": [log_entry]
            }

            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.valves.BACKEND_URL, json=payload, headers=headers
                ) as resp:
                    if resp.status in (200, 201, 202):
                        print(f"[FILTER HTTP SUCCESS] Log sent to backend ({resp.status})")
                    else:
                        resp_text = await resp.text()
                        print(f"[FILTER HTTP WARN] Backend returned {resp.status}: {resp_text[:100]}")
        except Exception as e:
            print(f"[FILTER HTTP ERROR] Failed to send log to backend: {e}")

    async def inlet(self, body: dict, __user__: dict = None) -> dict:
        return body

    async def outlet(self, body: dict, __user__: dict = None) -> dict:
        try:
            messages = body.get("messages", []) or []

            user_query = ""
            response_text = ""
            tool_calls = []
            usage_info = {}

            # 1. Извлекаем последний запрос пользователя
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_query = self._extract_text_from_content(msg.get("content", ""))
                    break

            # 2. Извлекаем ответ ассистента
            assistant_msg = None
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    assistant_msg = msg
                    # Новый формат Open WebUI
                    if "output" in msg and msg["output"]:
                        for item in msg["output"]:
                            if item.get("type") == "message" and "content" in item:
                                for content_item in item.get("content", []):
                                    if content_item.get("type") == "output_text":
                                        response_text = content_item.get("text", "")
                                        break
                                if response_text:
                                    break

                    # Фоллбек на старый формат content
                    if not response_text:
                        response_text = self._extract_text_from_content(msg.get("content", ""))

                    tool_calls = msg.get("tool_calls", []) or []
                    usage_info = msg.get("usage", {}) or body.get("usage", {}) or {}
                    break

            # Считаем токены из usage или ориентировочно по длине
            total_tokens = (
                usage_info.get("total_tokens")
                if isinstance(usage_info, dict) and usage_info.get("total_tokens")
                else max(100, (len(user_query) + len(response_text)) // 4)
            )

            log_entry = {
                "request_id": f"req_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                "query_text": user_query,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response_text": response_text,
                "status": "success",
                "total_tokens": total_tokens,
                "tools_used": [
                    tc.get("function", {}).get("name")
                    for tc in tool_calls
                    if isinstance(tc, dict) and tc.get("function")
                ],
                "metadata": {
                    "usage": usage_info,
                    "user_email": __user__.get("email") if __user__ else "anonymous",
                },
            }

            # 1. Локальное сохранение в файл
            if self.valves.LOG_FILE_PATH:
                os.makedirs(os.path.dirname(self.valves.LOG_FILE_PATH), exist_ok=True)
                with open(self.valves.LOG_FILE_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

            print(f"[FILTER] Logged locally: '{user_query[:40]}...' → '{response_text[:40]}...'")

            # 2. Асинхронная отправка по HTTP на бэкенд
            asyncio.create_task(self._send_log_to_backend(log_entry))

        except Exception as e:
            print(f"[FILTER ERROR] {e}")

        return body
