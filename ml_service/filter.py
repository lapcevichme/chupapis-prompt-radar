from pydantic import BaseModel, Field
import json
import os
from datetime import datetime


class Filter:
    class Valves(BaseModel):
        LOG_FILE_PATH: str = Field(
            default="/app/backend/data/input.jsonl",
            description="Путь куда складывать логи для ML",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.last_query = ""  # Сохраняем запрос пользователя между inlet и outlet

    async def inlet(self, body: dict, __user__: dict = None) -> dict:
        # Ловим запрос пользователя ДО отправки модели
        messages = body.get("messages", [])
        if messages:
            self.last_query = messages[-1].get("content", "")
        return body

    async def outlet(self, body: dict, __user__: dict = None) -> dict:
        try:
            messages = body.get("messages", [])

            response_text = ""
            tool_calls = []

            # Ищем последнее сообщение assistant
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
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

                    # Фоллбек на старый content
                    if not response_text:
                        response_text = msg.get("content", "")

                    tool_calls = msg.get("tool_calls", []) or []
                    break

            log_entry = {
                "request_id": f"req_{int(datetime.now().timestamp() * 1000)}",
                "query_text": self.last_query,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "response_text": response_text,
                "response_status": "success",
                "metadata": {
                    "tools_used": (
                        [tc.get("function", {}).get("name") for tc in tool_calls]
                        if tool_calls
                        else []
                    ),
                    "usage": (
                        msg.get("usage") if "msg" in locals() else None
                    ),  # опционально
                },
            }

            os.makedirs(os.path.dirname(self.valves.LOG_FILE_PATH), exist_ok=True)
            with open(self.valves.LOG_FILE_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

            print(f"[FILTER] Logged: '{self.last_query}' → '{response_text[:100]}...'")

        except Exception as e:
            print(f"[FILTER ERROR] {e}")

        return body
