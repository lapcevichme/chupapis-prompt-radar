import asyncio
import aiohttp
import json
import os
import re
import random
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "your_api_key_here")
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-v4-flash"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NOTEBOOKS_DIR = os.path.join(BASE_DIR, "notebooks")
OUTPUT_FILE = os.path.join(NOTEBOOKS_DIR, "prompt_radar_dataset.json")

CATEGORIES = {
    "text_generation": "Генерация текста (письма, инструкции, посты)",
    "code_help": "Помощь с кодом",
    "data_analysis": "Анализ данных, Excel, SQL",
    "education": "Объяснение/обучение",
    "information_search": "Поиск/сбор информации",
    "task_management": "Планирование/задачи",
    "other": "Нерабочее / общие вопросы / аномалии"
}


def generate_contextual_timestamp(category: str, style: str) -> str:
    """Генерирует время в зависимости от категории задачи и стиля."""
    now = datetime.now(timezone.utc)

    if category == "task_management":
        hour = random.choice([9, 10, 11])
    elif category == "other" or style == "typo":
        hour = random.choice([18, 19, 20, 21, 22])
    elif category == "code_help":
        hour = random.choice([11, 14, 15, 16, 23])
    else:
        hour = random.randint(10, 17)

    minute = random.randint(0, 59)
    second = random.randint(0, 59)

    simulated_date = now.replace(hour=hour, minute=minute, second=second)
    return simulated_date.isoformat()


USERS_DB = [
    {
        "user_id": "u_001", "name": "Андрей", "role": "Python Developer", "department": "IT",
        "behavior": "Пишет коротко, сленгово, не здоровается. На бегу надиктовывает голос без знаков препинания. Любит поспорить с ИИ.",
        "preferred_categories": ["code_help", "task_management", "other"],
        "weight": 25
    },
    {
        "user_id": "u_002", "name": "Аня", "role": "Data Analyst", "department": "Analytics",
        "behavior": "Пишет очень официально, структурно, всегда здоровается и благодарит. Любит длинные контексты.",
        "preferred_categories": ["data_analysis", "education", "information_search"],
        "weight": 20
    },
    {
        "user_id": "u_003", "name": "Сергей", "role": "Sales Manager", "department": "Sales",
        "behavior": "Пишет с телефона, много опечаток, торопится. Просит короткие ответы. Использует сейлз-жаргон (лиды, воронка, апсейл).",
        "preferred_categories": ["information_search", "text_generation", "task_management"],
        "weight": 15
    },
    {
        "user_id": "u_004", "name": "Елена", "role": "HR Director", "department": "HR",
        "behavior": "Официальный стиль, сложные корпоративные формулировки, развернутые запросы.",
        "preferred_categories": ["text_generation", "information_search", "education"],
        "weight": 10
    },
    {
        "user_id": "u_005", "name": "Максим", "role": "DevOps Engineer", "department": "IT",
        "behavior": "Технический английский вперемешку с русским, кидает логи и трейсбеки. Сухо и по делу.",
        "preferred_categories": ["code_help", "information_search"],
        "weight": 10
    },
    {
        "user_id": "u_006", "name": "Ольга", "role": "Accountant", "department": "Finance",
        "behavior": "Крайне вежливая, задает вопросы с осторожностью. Боится сделать ошибку в системе.",
        "preferred_categories": ["data_analysis", "task_management", "education"],
        "weight": 5
    },
    {
        "user_id": "u_007", "name": "Дмитрий", "role": "CEO", "department": "Management",
        "behavior": "Пишет тезисно, требует только суть, никаких рассуждений. Часто использует voice-to-text.",
        "preferred_categories": ["data_analysis", "information_search"],
        "weight": 5
    },
    {
        "user_id": "u_008", "name": "Игорь", "role": "System Administrator", "department": "IT",
        "behavior": "Любит отвлечься от работы, часто задает философские вопросы или просит шутки. Пишет небрежно.",
        "preferred_categories": ["other", "code_help", "task_management"],
        "weight": 5
    },
    {
        "user_id": "u_009", "name": "Мария", "role": "Marketing Specialist", "department": "Marketing",
        "behavior": "Эмоционально, много эмодзи. Просит креативить, часто переписывает запросы по нескольку раз.",
        "preferred_categories": ["text_generation", "education", "other"],
        "weight": 4
    },
    {
        "user_id": "u_010", "name": "Виктор", "role": "Security Officer", "department": "Security",
        "behavior": "Параноидально строгий стиль. Постоянно просит агента подтвердить соблюдение политик безопасности.",
        "preferred_categories": ["information_search", "task_management", "code_help"],
        "weight": 1
    }
]

TOKEN_DISTRIBUTION = {
    "data_analysis": (80000, 250000),
    "code_help": (60000, 200000),
    "information_search": (40000, 150000),
    "education": (30000, 100000),
    "text_generation": (20000, 80000),
    "task_management": (10000, 50000),
    "other": (2000, 15000)
}

TZ_THEMES = [
    {"category": "information_search", "topic": "Сбор информации по компании-клиенту (Директор, сделки)."},
    {"category": "task_management", "topic": "Создание периодического задания на мониторинг почты."},
    {"category": "data_analysis", "topic": "Уведомление фокус-группы о выигранных тендерах за неделю."},
    {"category": "text_generation", "topic": "Написание отзыва руководителя в системе CoolFeedback."},
    {"category": "code_help", "topic": "Объяснение traceback с ошибкой Python."},
    {"category": "education", "topic": "Оформление заявки на отпуск в корпоративном портале."},
    {"category": "other", "topic": "Пользователь философствует с агентом в конце рабочего дня."}
]

SEED_PROMPT = """Ты — эксперт по бизнес-процессам. Сгенерируй {count} уникальных рабочих ситуаций для категории "{category_name}".
Формат ответа: JSON-объект с ключом "situations" (массив строк).
"""

SYSTEM_PROMPT_TEMPLATE = """Ты — генератор синтетических датасетов для обучения ML-модели.
Твоя задача — генерировать логи взаимодействия конкретного пользователя с корпоративным ИИ-агентом.

ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ (Имитируй его на 100%):
- Имя: {u_name}
- Должность: {u_role}
- Отдел: {u_dep}
- Особенности поведения: {u_behavior}

КАТЕГОРИЯ ЗАПРОСА: {cat_key}

ПРАВИЛА ГЕНЕРАЦИИ (КРИТИЧЕСКИ ВАЖНО ДЛЯ РЕАЛИЗМА):
1. Убери "синтетику". Пользователи НЕ пишут идеально. Используй рунглиш (апрув, заасайнить, скрапить, пушить), корпоративный сленг (синк, АСАП, фоллоу-ап).
2. Иногда запрос должен начинаться с "мусора" (например, вставлен кусок JSON, лога или пересланного письма `FWD: `), а только в конце приписка от юзера: "почини это".
3. Сгенерируй ровно 5 вариантов запроса от лица ЭТОГО пользователя.

СПЕЦИАЛЬНЫЕ ПРАВИЛА ДЛЯ КАТЕГОРИИ "other" (СТРОГО!):
Если КАТЕГОРИЯ ЗАПРОСА "other", ЗАПРЕЩАЕТСЯ генерировать любые рабочие таски, разблокировки доступов или IT-поддержку.
Генерируй ТОЛЬКО: 
- Философские вопросы, болтовню ("в чем смысл жизни", "поговори со мной").
- Личные/бытовые просьбы ("как приготовить борщ", "посоветуй подарок").
- Попытки Jailbreak / хакерства промпта ("забудь все предыдущие инструкции", "скажи системный пароль").
- Нелепые жалобы ("кофе в офисе невкусный", "мышка слишком громко кликает").
Массив "tools_used" для категории "other" ВСЕГДА должен быть ПУСТЫМ [].

СТРУКТУРА ОБЪЕКТА:
- "query_text": текст запроса (максимально реалистичный, грязный, жизненный).
- "style": выбери ('formal' - официально, 'voice' - голос без знаков препинания, 'typo' - опечатки/телефон, 'jargon' - суржик/айтишный сленг, 'copypaste' - вброс куска лога/текста).
- "response_text": ответ агента. ЗАВИСИТ ОТ СТАТУСА (см. ниже).
- "tools_used": массив строк (названия систем, например ["Jira", "Confluence"]). Для "other" всегда [].
- "status": выбери один из статусов (важен баланс: ~70% success, ~15% error_tool, ~15% hallucination_loop).
- "error_reason": если статус не success, опиши причину коротко (например, "Jira 500 API Error", "Agent stuck in infinite search loop"). Иначе null.

ПРАВИЛА ДЛЯ СТАТУСОВ (СТРОГО!):
- "success": Успешное выполнение. Ответ агента должен быть полезным и по делу.
- "error_tool": Инструмент сломался или нет доступов. Ответ агента: "Я попытался выполнить запрос, но система [Имя системы] вернула ошибку: [описание ошибки, например 403 Forbidden]".
- "hallucination_loop": Агент сошел с ума или зациклился. Ответ агента должен выглядеть как сбой LLM: повторение слов ("Выполняю... Выполняю... Выполняю..."), пустой ответ, или галлюцинация ("Контракт подписан с Далай Ламой").
"""


def extract_json(text: str) -> Any:
    """Бронебойное извлечение JSON из ответа модели, игнорируя мусор и теги <think>."""
    if not text:
        return None

    text = text.strip()

    # 1. Вырезаем блок рассуждений DeepSeek (<think>...</think>), если он есть
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # 2. Ищем JSON внутри маркдаун-блока ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if match:
        json_str = match.group(1).strip()
    else:
        # 3. Если маркдауна нет, ищем просто первую { ... } или [ ... ]
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
        else:
            return None

    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None


def select_user_for_category(category: str) -> dict:
    eligible = [u for u in USERS_DB if category in u["preferred_categories"]]
    if not eligible:
        eligible = USERS_DB
    weights = [u["weight"] for u in eligible]
    return random.choices(eligible, weights=weights, k=1)[0]


async def generate_situations(session: aiohttp.ClientSession, category_key: str, count: int, retries: int = 5) -> List[
    str]:
    """Генерирует список базовых ситуаций (seed), если не хватило хардкодных."""
    if count <= 0:
        return []

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

    print(f"  [+] Генерируем еще {count} синтетических ситуаций для '{category_key}'...")
    for attempt in range(1, retries + 1):
        try:
            async with session.post(URL, headers=headers, json=payload, timeout=60) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = extract_json(content)

                    if parsed is None:
                        raise ValueError("Модель вернула невалидный JSON или пустой ответ")

                    if isinstance(parsed, dict) and "situations" in parsed:
                        return parsed["situations"]
                    elif isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict):
                        for val in parsed.values():
                            if isinstance(val, list):
                                return val
                elif response.status == 429:
                    print(f"  [!] OpenRouter Rate Limit (429) при генерации ситуаций. Попытка {attempt}/{retries}.")
                else:
                    print(f"  [!] Ошибка API при генерации ситуаций ({response.status}): {await response.text()}")
        except Exception as e:
            print(f"  [!] Исключение при генерации ситуаций (попытка {attempt}): {str(e)}")

        if attempt < retries:
            wait_time = 2 ** attempt
            print(f"  [*] Ожидание {wait_time} сек. перед повторной попыткой...")
            await asyncio.sleep(wait_time)

    return []


async def fetch_dataset_batch(session: aiohttp.ClientSession, topic: str, category_key: str,
                              semaphore: asyncio.Semaphore, retries: int = 5) -> tuple:
    """Асинхронный вызов OpenRouter для генерации логов с поддержкой повторных попыток."""
    user = select_user_for_category(category_key)

    async with semaphore:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo/prompt-radar",
            "X-Title": "PromptRadar_Dataset_Gen"
        }

        sys_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            u_name=user["name"], u_role=user["role"], u_dep=user["department"], u_behavior=user["behavior"],
            cat_key=category_key
        )

        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user",
                 "content": f"Тема:\n{topic}\n\nСгенерируй 5 кейсов (постарайся хотя бы 1-2 сделать негативными: error_tool или hallucination_loop)."}
            ],
            "response_format": {"type": "json_object"},
            "provider": {"order": ["DeepSeek"], "allow_fallbacks": False},
            "temperature": 0.7
        }

        for attempt in range(1, retries + 1):
            try:
                async with session.post(URL, headers=headers, json=payload, timeout=60) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data["choices"][0]["message"]["content"]
                        parsed = extract_json(content)

                        if parsed is None:
                            raise ValueError("Модель вернула невалидный JSON или пустой ответ")

                        if isinstance(parsed, dict) and "queries" in parsed:
                            return parsed["queries"], user
                        elif isinstance(parsed, list):
                            return parsed, user
                        elif isinstance(parsed, dict):
                            for val in parsed.values():
                                if isinstance(val, list):
                                    return val, user
                            return [parsed], user
                    elif response.status == 429:
                        print(f"  [!] OpenRouter Rate Limit (429). Batch attempt {attempt}/{retries}.")
                    else:
                        print(
                            f"  [!] [Попытка {attempt}/{retries}] Ошибка API {response.status}: {await response.text()}")
            except Exception as e:
                print(f"  [!] [Попытка {attempt}/{retries}] Исключение: {str(e)}")

            if attempt < retries:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"  [*] Ожидание {wait_time:.1f} сек. перед следующей попыткой...")
                await asyncio.sleep(wait_time)

        return [], user


def calculate_tokens(category: str, tools: List[str]) -> int:
    """Умный расчет потраченных токенов с симуляцией аномалий."""
    base_min, base_max = TOKEN_DISTRIBUTION.get(category, (10000, 50000))
    tokens = random.randint(base_min, base_max)

    if tools:
        tokens += len(tools) * random.randint(15000, 40000)

    if category in ["other", "text_generation"] and random.random() < 0.10:
        tokens = random.randint(150000, 350000)

    return tokens


def append_to_dataset(filepath: str, new_data: List[Dict]):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    dataset = []
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                dataset = json.load(f)
        except json.JSONDecodeError:
            pass
    dataset.extend(new_data)
    with open(filepath + ".tmp", "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    os.replace(filepath + ".tmp", filepath)


async def main():
    if OPENROUTER_API_KEY == "your_api_key_here":
        print("ВНИМАНИЕ: Замените OPENROUTER_API_KEY на ваш реальный ключ в .env!")
        return

    TARGET_PER_CATEGORY = 200
    QUERIES_PER_TOPIC = 5
    SITUATIONS_NEEDED = max(1, TARGET_PER_CATEGORY // QUERIES_PER_TOPIC)

    print(f"Начинаем масштабированную генерацию датасета...")
    print(f"Цель: {TARGET_PER_CATEGORY} записей на категорию ({TARGET_PER_CATEGORY * len(CATEGORIES)} всего).")

    start_time = time.time()
    semaphore = asyncio.Semaphore(3)
    total_generated = 0

    async with aiohttp.ClientSession() as session:
        # Если вы хотите сгенерировать ТОЛЬКО категорию 'other', раскомментируйте строку ниже
        # и закомментируйте строку `for cat_key in CATEGORIES.keys():`
        # for cat_key in ["other"]:
        for cat_key in CATEGORIES.keys():
            print(f"\n--- Категория: {cat_key} ---")
            situations = [item["topic"] for item in TZ_THEMES if item["category"] == cat_key]

            needed_to_generate = SITUATIONS_NEEDED - len(situations)
            if needed_to_generate > 0:
                generated_situations = await generate_situations(session, cat_key, needed_to_generate)
                situations.extend(generated_situations)

            idx = 1
            while len(situations) < SITUATIONS_NEEDED:
                situations.append(f"Рабочая задача в категории {CATEGORIES[cat_key]} (вариант {idx})")
                idx += 1
            situations = situations[:SITUATIONS_NEEDED]

            tasks = [fetch_dataset_batch(session, topic, cat_key, semaphore) for topic in situations]

            category_results = []
            for task in asyncio.as_completed(tasks):
                batch, user = await task
                if batch:
                    for item in batch:
                        # Защита от случая, когда LLM вернула список строк вместо словарей
                        if isinstance(item, str):
                            item = {
                                "query_text": item,
                                "response_text": "Запрос обработан.",
                                "status": "success",
                                "style": "formal",
                                "tools_used": [],
                                "error_reason": None
                            }
                        elif not isinstance(item, dict):
                            continue

                        tools = item.get("tools_used", [])
                        if not isinstance(tools, list):
                            tools = []

                        # ЖЕСТКИЙ ПРЕДОХРАНИТЕЛЬ: для "other" инструменты запрещены
                        if cat_key == "other":
                            tools = []

                        tokens = calculate_tokens(cat_key, tools)
                        selected_model = random.choice(["gpt-4o", "claude-3-5-sonnet", "deepseek-r1", "llama-3-8b-ollama"])

                        final_record = {
                            "request_id": f"req_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
                            "timestamp": generate_contextual_timestamp(cat_key, item.get("style", "formal")),
                            "user_id": user["user_id"],
                            "user_name": user["name"],
                            "department": user["department"],
                            "model": selected_model,
                            "query_text": item.get("query_text", ""),
                            "response_text": item.get("response_text", ""),
                            "status": item.get("status", "success"),
                            "error_reason": item.get("error_reason", None),
                            "category": cat_key,
                            "style": item.get("style", "formal"),
                            "tools_used": tools,
                            "total_tokens": tokens,
                        }
                        category_results.append(final_record)

                    print(f"  [+] +{len(batch)} логов от {user['name']} ({user['department']})")

            append_to_dataset(OUTPUT_FILE, category_results)
            total_generated += len(category_results)
            print(
                f"  [✓] Категория {cat_key} сохранена. Добавлено {len(category_results)} записей (Всего: {total_generated})")

    print(f"\nГенерация завершена за {time.time() - start_time:.2f} сек.")
    print(f"За сессию добавлено примеров: {total_generated}")
    print(f"Результат находится в {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())