import asyncio
import aiohttp
import json
import os
import re
import time
from datetime import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "your_api_key_here")
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-v4-flash"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "prompt_radar_dataset.json")

CATEGORIES = {
    "text_generation": "Генерация текста (письма, инструкции, посты)",
    "code_help": "Помощь с кодом",
    "data_analysis": "Анализ данных, Excel, SQL",
    "education": "Объяснение/обучение",
    "information_search": "Поиск/сбор информации",
    "task_management": "Планирование/задачи",
    "other": "Нерабочее / общие вопросы / аномалии"
}

# --- ПРОМПТ ДЛЯ ГЕНЕРАЦИИ СИТУАЦИЙ (SEED) ---
SEED_PROMPT = """Ты — эксперт по бизнес-процессам крупной корпорации (системный интегратор, ритейл, банк).
Твоя задача — придумывать разнообразные рабочие ситуации, с которыми сотрудники приходят к внутреннему ИИ-агенту.

Сгенерируй {count} уникальных рабочих ситуаций для категории "{category_name}".
Ситуации должны быть конкретными, с деталями (названия систем, отделы, типы документов).

Формат ответа: строго JSON-объект с ключом "situations", содержащим массив из {count} строк.
Пример:
{{
  "situations": [
    "Менеджеру нужно выгрузить из CRM таблицу с клиентами, у которых заканчивается лицензия в следующем месяце.",
    "Аналитик просит написать SQL-скрипт для объединения таблиц продаж и маркетинговых расходов из ClickHouse."
  ]
}}
"""

# --- ОСНОВНОЙ ПРОМПТ ДЛЯ ГЕНЕРАЦИИ ЗАПРОСОВ ---
SYSTEM_PROMPT_TEMPLATE = """Ты — генератор синтетических датасетов для обучения ML-модели (CatBoost).
Твоя задача — генерировать логи взаимодействия пользователей с корпоративным ИИ-агентом.

КОНТЕКСТ ПРОДУКТА (ВАЖНО!):
Агенты (в отличие от обычного чата) потребляют много токенов, работают автономно и используют инструменты (Jira, CRM, Почта). 
Нам нужно оценивать их ROI (экономию FTE). Поэтому датасет должен содержать метрики выполнения задачи.

ДОСТУПНЫЕ КАТЕГОРИИ КЛАССИФИКАЦИИ:
{categories_json}

ПРАВИЛА ГЕНЕРАЦИИ (СТРУКТУРА ДАТАСЕТА):
1. На предоставленную тему сгенерируй ровно 5 вариантов запроса от пользователя.
2. Стили запроса должны варьироваться:
   - 'formal': официальный корпоративный запрос (через веб-интерфейс).
   - 'voice': имитация голосового ввода на бегу (без пунктуации, слова-паразиты, сумбур).
   - 'typo': текстовый запрос с частыми опечатками (с телефона или в спешке).
3. Верни JSON-объект с единственным ключом "queries", содержащим массив из 5 объектов.

СТРУКТУРА КАЖДОГО ОБЪЕКТА (ОБЯЗАТЕЛЬНЫЕ ПОЛЯ):
- "user_query": сам текст запроса.
- "style": стиль запроса ('formal', 'voice' или 'typo').
- "category": строго "{category_key}".
- "simulated_context_tokens": от 100 до 150000 (имитация контекста рассуждений агента и файлов).
- "agent_steps": количество шагов рассуждения/вызова тулзов (число от 1 до 12).
- "tools_used": массив использованных инструментов (например ["Jira", "Mail", "CRM", "Excel", "Confluence", "SQL"], или [] если это просто вопрос).
- "estimated_manual_time_minutes": сколько минут человек делал бы это руками (число от 5 до 240).
- "status": статус выполнения агентом. Выбери одно из: "success" (80% случаев), "error_tool" (ошибка API), "hallucination_loop" (зацикливание).

User Context:
1. [{date_now}] user - Сергей
"""


def extract_json(text: str) -> Any:
    """Надежное извлечение JSON из ответа модели."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


async def generate_situations(session: aiohttp.ClientSession, category_key: str, count: int, retries: int = 3) -> List[str]:
    """Генерирует список базовых ситуаций (seed) с повторными попытками."""
    category_name = CATEGORIES[category_key]
    prompt = SEED_PROMPT.format(count=count, category_name=category_name)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/your-repo/prompt-radar",
        "X-Title": "PromptRadar_Dataset_Gen"
    }

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "provider": {"order": ["DeepSeek"], "allow_fallbacks": False},
        "temperature": 0.9
    }

    print(f"  [+] Генерируем {count} ситуаций для категории '{category_key}'...")
    for attempt in range(1, retries + 1):
        try:
            async with session.post(URL, headers=headers, json=payload, timeout=40) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = extract_json(content)
                    if isinstance(parsed, dict) and "situations" in parsed:
                        return parsed["situations"]
                    elif isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict):
                        for val in parsed.values():
                            if isinstance(val, list): return val
                else:
                    print(f"  [!] Ошибка API при генерации ситуаций ({response.status}): {await response.text()}")
        except Exception as e:
            print(f"  [!] Исключение при генерации ситуаций: {str(e)}")

        if attempt < retries:
            await asyncio.sleep(2)

    return []


async def fetch_dataset_batch(session: aiohttp.ClientSession, topic: str, category_key: str,
                               semaphore: asyncio.Semaphore, retries: int = 3) -> List[Dict]:
    """Асинхронный вызов OpenRouter для генерации логов."""
    async with semaphore:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo/prompt-radar",
            "X-Title": "PromptRadar_Dataset_Gen"
        }

        sys_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            categories_json=json.dumps(CATEGORIES, ensure_ascii=False, indent=2),
            category_key=category_key,
            date_now=datetime.now().strftime('%Y-%m-%d')
        )

        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"Сгенерируй 5 вариантов запросов для темы:\n{topic}"}
            ],
            "response_format": {"type": "json_object"},
            "provider": {"order": ["DeepSeek"], "allow_fallbacks": False},
            "temperature": 0.7
        }

        for attempt in range(1, retries + 1):
            try:
                async with session.post(URL, headers=headers, json=payload, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data["choices"][0]["message"]["content"]
                        parsed = extract_json(content)

                        if isinstance(parsed, dict) and "queries" in parsed:
                            return parsed["queries"]
                        elif isinstance(parsed, list):
                            return parsed
                        elif isinstance(parsed, dict):
                            for val in parsed.values():
                                if isinstance(val, list):
                                    return val
                            return [parsed]
                    else:
                        print(f"  [!] [Попытка {attempt}/{retries}] Ошибка API {response.status}: {await response.text()}")
            except Exception as e:
                print(f"  [!] [Попытка {attempt}/{retries}] Исключение: {str(e)}")

            if attempt < retries:
                await asyncio.sleep(2 * attempt)

        return []


def append_to_dataset(filepath: str, new_data: List[Dict]):
    """Атомарно добавляет порцию данных в JSON-файл."""
    if not new_data:
        return

    dataset = []
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                dataset = json.load(f)
        except json.JSONDecodeError:
            pass

    dataset.extend(new_data)

    temp_file = filepath + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, filepath)


async def main():
    if OPENROUTER_API_KEY == "your_api_key_here":
        print("ВНИМАНИЕ: Замените OPENROUTER_API_KEY на ваш реальный ключ в ml_service/.env!")
        return

    TARGET_PER_CATEGORY = 50  # Сколько примеров хотим на каждую категорию
    QUERIES_PER_TOPIC = 5     # Сколько вариантов генерирует модель на 1 тему
    SITUATIONS_NEEDED = TARGET_PER_CATEGORY // QUERIES_PER_TOPIC

    print(f"Начинаем масштабированную генерацию датасета...")
    print(f"Цель: {TARGET_PER_CATEGORY} записей на категорию ({TARGET_PER_CATEGORY * len(CATEGORIES)} всего).")

    start_time = time.time()
    semaphore = asyncio.Semaphore(10)
    total_generated = 0

    async with aiohttp.ClientSession() as session:
        for cat_key in CATEGORIES.keys():
            print(f"\n--- Обработка категории: {cat_key} ---")

            situations = await generate_situations(session, cat_key, SITUATIONS_NEEDED)

            # Если ситуаций недостаточно, дополняем вариативными фолбеками
            idx = 1
            while len(situations) < SITUATIONS_NEEDED:
                situations.append(f"Запрос от сотрудника по теме '{CATEGORIES[cat_key]}' (вариант {idx})")
                idx += 1

            tasks = [fetch_dataset_batch(session, topic, cat_key, semaphore) for topic in situations]

            category_results = []
            for task in asyncio.as_completed(tasks):
                batch = await task
                if isinstance(batch, list) and batch:
                    # Валидация и гарантированная подстановка правильной категории
                    for item in batch:
                        if isinstance(item, dict):
                            item["category"] = cat_key
                            category_results.append(item)
                    print(f"  [+] Завершено {len(batch)} логов")

            # Записываем на диск один раз по завершении категории
            append_to_dataset(OUTPUT_FILE, category_results)
            total_generated += len(category_results)
            print(f"  [✓] Категория {cat_key} сохранена. Добавлено {len(category_results)} записей (Всего: {total_generated})")

    print(f"\nГенерация завершена за {time.time() - start_time:.2f} сек.")
    print(f"За сессию добавлено примеров: {total_generated}")
    print(f"Результат находится в {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())