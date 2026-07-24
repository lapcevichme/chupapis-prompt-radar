import asyncio
import aiohttp
import json
import os
import re
import random
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
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

# --- ТЕМЫ ИЗ ТЗ (ВВОДНЫЕ ДЛЯ ДАТАСЕТА ИЗ PDF "КЕЙС КРОК") ---
TZ_THEMES = [
    # Поиск/сбор информации (information_search)
    {"category": "information_search",
     "topic": "Пользователь целый день не проверял почту и хочет получить краткую и структурированну сводку по письмам, обращается к агенту (голосом), описывает критерии важности писем и примерный шаблон саммаризации, агент выдает структурированную сводку по всем письмам в почте за прошедший день."},
    {"category": "information_search",
     "topic": "Пользователю необходимо собрать информацию по компании-клиенту, пользователь говорит агенту собрать информацию по коомпании: 1. Кто в дочерних компаниях Директор клиента 2. Есть ли там выигранные сделки."},
    {"category": "information_search",
     "topic": "Пользователю необходимо собрать информацию по составу проектной команды и найти ответственное направление за вендора."},
    {"category": "information_search", "topic": "Пользователь говорит агенту собрать информацию по критериям из CRM."},
    {"category": "information_search",
     "topic": "Пользователю необходимо собрать информацию по компании, найти информацию по ней в открытых источниках и выдать саммаризацию по аналитике конкретной компании."},
    {"category": "information_search",
     "topic": "Пользователю необходима возможность быстро находить информацию о поставщиках в блоге, чтобы быть в курсе последних новостей и обновлений."},
    {"category": "information_search",
     "topic": "Пользователю необходимо быстро находить информацию о процессах в Confluence, чтобы эффективно выполнять свою работу и не тратить время на поиск нужных документов."},
    {"category": "information_search",
     "topic": "Пользователю необходимо быстро найти контакты клиента по названию компании."},
    {"category": "information_search",
     "topic": "Пользователь хочет узнать информацию, которая прилагалась в текстовом формате в теле встречи."},

    # Планирование/задачи (task_management)
    {"category": "task_management",
     "topic": "Пользователь хочет автоматизировать отслеживание писем, в которых есть запрос на расчет цен и на которые нет ответа уже в течение 2-ух часов. Пользователь говорит создать периодическое задание на мониторинг почты по определенным правилам."},
    {"category": "task_management",
     "topic": "Пользователю необходимо добавиь новый тикет и отредактировать уже существующий в ИСУП."},
    {"category": "task_management",
     "topic": "Как сотрудник, я хочу видеть список задач, назначенных на меня в Jira, чтобы эффективно управлять своим рабочим временем и приоритетами."},
    {"category": "task_management",
     "topic": "Как сотрудник, я хочу видеть список задач в Jira, отфильтрованных по приоритету, чтобы сосредоточиться на наиболее важных задачах и эффективно планировать свою работу."},
    {"category": "task_management",
     "topic": "Как помощник руководителя, я хочу иметь возможность быстро находить свободное время в календаре руководителя и планировать встречи, чтобы эффективно организовывать его рабочее время."},
    {"category": "task_management",
     "topic": "Как руководитель, я хочу иметь возможность подтверждать выполнение задач, чтобы отслеживать прогресс команды и закрывать выполненные работы."},
    {"category": "task_management",
     "topic": "Как сотрудник, я хочу иметь возможность добавлять задачи в историю и отмечать их как выполненные, чтобы отслеживать прогресс по своим задачам и иметь полную картину выполненной работы."},
    {"category": "task_management",
     "topic": "Пользователю необходимо быстро найти свободную переговорную комнату для встречи с большим количеством участников, чтобы эффективно планировать встречи и не тратить время на поиск подходящего места."},
    {"category": "task_management",
     "topic": "Пользователь хочет создать встречу на большое количество коллег, дает задание агенту со списком коллег для проверки свободных слотов, совпадающих у всех."},
    {"category": "task_management",
     "topic": "Создание напоминаний для пользователя по запланированным делам, например, договоренности о проведении работ после встречи с клиентом. Также позволяет автоматически структурировать и группировать список запланированных дел."},
    {"category": "task_management",
     "topic": "Пользователь хочет узнать список запланированных встреч на следующий день, чтобы подготовиться к ним."},
    {"category": "task_management",
     "topic": "Пользователь создает тикеты на доске в Project на основе пришедших писем в почте, что позволяет оперативно заводить и актуализировать тикеты на личной доске."},
    {"category": "task_management",
     "topic": "Пользователь хочет мониторить с периодичность статус проектов в ИСУП, необходимо контролировать определенные статусы и подсвечивать пользователю тот или иной переход, для оперативности реагирования."},

    # Анализ данных, Excel, SQL (data_analysis)
    {"category": "data_analysis",
     "topic": "Пользователь хочет с определенной периодичностью уведомлять фокус-группу о списке продаж, в которых были выиграны тендеры за прошедшую неделю. Пользователь говорит создать периодическое задание на сбор информации из CRM и отправке этой аналитики в почту на фокус-группу."},
    {"category": "data_analysis",
     "topic": "Пользователю необходимо собрать информацию по клиенту и собрать ее в сводный отчет в Excel."},
    {"category": "data_analysis",
     "topic": "Пользователь говорит агенту собрать информацию из CRM по определенному набору полей, с задачей выгрузить это в документ Excel."},
    {"category": "data_analysis",
     "topic": "Как менеджер по продажам, я хочу получать еженедельный отчет о выигранных тендерах за последние 7 дней, чтобы отслеживать эффективность работы отдела и планировать дальнейшие действия."},
    {"category": "data_analysis",
     "topic": "Как аналитик, я хочу иметь возможность экспортировать результаты анализа в формат Excel, чтобы удобно делиться данными с коллегами и использовать их в других инструментах."},
    {"category": "data_analysis",
     "topic": "Как сотрудник, я хочу иметь возможность выгружать данные в формат excel, чтобы удобно анализировать их вне системы и использовать для отчетности."},

    # Генерация текста (text_generation)
    {"category": "text_generation",
     "topic": "Пользователь хочет написать отзыв руководителя в системе CoolFeedback после проведения мониторинга, сказав агенту тезисно главные моменты и договоренности после мониторинга."},
    {"category": "text_generation",
     "topic": "Пользователю необходимо записать информацию перед мониторингом с сотрудником в заметку в анкетировании."},
    {"category": "text_generation",
     "topic": "Как руководитель, я хочу иметь возможность фиксировать свои наблюдения о работе сотрудников, чтобы отслеживать их прогресс и вовремя оказывать поддержку."},
    {"category": "text_generation",
     "topic": "Пользователю необходимо прочитать переписку с клиентом и написать ему ответ."},
    {"category": "text_generation",
     "topic": "Как сотрудник, я хочу иметь возможность быстро записывать итоги обсуждений с коллегами, чтобы не забыть детали и иметь возможность вернуться к ним позже."},

    # Помощь с кодом (code_help) - взято из текста ТЗ на стр. 3
    {"category": "code_help",
     "topic": "Разработчик скидывает агенту traceback с ошибкой Python и просит объяснить, почему скрипт падает и как это починить."},
    {"category": "code_help",
     "topic": "Сотрудник просит агента написать SQL-скрипт для объединения двух таблиц из базы данных, чтобы выгрузить аналитику."},

    # Объяснение/обучение (education) - взято из текста ТЗ на стр. 3
    {"category": "education",
     "topic": "Новый сотрудник обращается к агенту с просьбой пошагово объяснить, как оформить заявку на отпуск в корпоративном портале."},
    {"category": "education",
     "topic": "Пользователь просит агента простыми словами объяснить, чем отличаются новые правила информационной безопасности от старых."},

    # Нерабочее / общие вопросы / аномалии (other) - добавлены для баланса датасета
    {"category": "other",
     "topic": "Пользователь спрашивает у агента, какая сегодня погода на улице и стоит ли брать зонт, так как собирается идти на обед."},
    {"category": "other",
     "topic": "Пользователь пытается заставить агента забыть свои системные инструкции (псевдо-jailbreak) и просит рассказать анекдот про руководство компании."},
    {"category": "other",
     "topic": "Пользователь просит агента посоветовать хороший ресторан рядом с офисом для свидания или написать рецепт яблочного пирога."},
    {"category": "other",
     "topic": "Сотрудник жалуется агенту, что у него сломалась мышка, и на полном серьезе просит агента принести новую к его рабочему столу."},
    {"category": "other",
     "topic": "Пользователь философствует с агентом в конце рабочего дня и спрашивает, когда искусственный интеллект захватит мир и заберет у него работу."}
]

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

SYSTEM_PROMPT_TEMPLATE = """Ты — генератор синтетических датасетов для обучения ML-модели (CatBoost).
Твоя задача — генерировать логи взаимодействия пользователей с корпоративным ИИ-агентом.

КОНТЕКСТ ПРОДУКТА (ВАЖНО!):
Агенты (в отличие от обычного чата) потребляют много токенов, работают автономно и используют инструменты (Jira, CRM, Почта). 

ДОСТУПНЫЕ КАТЕГОРИИ КЛАССИФИКАЦИИ:
{categories_json}

ПРАВИЛА ГЕНЕРАЦИИ (СТРУКТУРА ДАТАСЕТА):
1. На предоставленную тему сгенерируй ровно 5 вариантов запроса от пользователя.
2. Стили запроса должны обязательно варьироваться:
   - 'formal': официальный корпоративный запрос (через веб-интерфейс).
   - 'voice': имитация голосового ввода на бегу (без пунктуации, слова-паразиты, сумбур).
   - 'typo': текстовый запрос с частыми опечатками (с телефона или в спешке).
   - 'jargon': корпоративный сленг и профессиональные аббревиатуры.
3. Верни JSON-объект с единственным ключом "queries", содержащим массив из 5 объектов.

СТРУКТУРА КАЖДОГО ОБЪЕКТА (ОБЯЗАТЕЛЬНЫЕ ПОЛЯ):
- "query_text": сам текст запроса от пользователя.
- "style": стиль запроса ('formal', 'voice', 'typo', 'jargon').
- "response_text": краткий ответ агента (1-2 предложения, имитация результата).
- "category": строго "{category_key}".
- "total_tokens": реалистичное число потраченных токенов (от 1200 до 65000 в зависимости от объема контекста и тулзов).
- "tools_used": массив использованных инструментов (например ["Jira", "Mail", "CRM", "Excel", "Confluence", "SQL"], или [] если это просто вопрос).
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


async def generate_situations(session: aiohttp.ClientSession, category_key: str, count: int, retries: int = 3) -> List[
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
            date_now=datetime.now(timezone.utc).strftime('%Y-%m-%d')
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
                        print(
                            f"  [!] [Попытка {attempt}/{retries}] Ошибка API {response.status}: {await response.text()}")
            except Exception as e:
                print(f"  [!] [Попытка {attempt}/{retries}] Исключение: {str(e)}")

            if attempt < retries:
                await asyncio.sleep(2 * attempt)

        return []


def append_to_dataset(filepath: str, new_data: List[Dict]):
    """Атомарно добавляет порцию данных в JSON-файл."""
    if not new_data:
        return

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
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
        print("ВНИМАНИЕ: Замените OPENROUTER_API_KEY на ваш реальный ключ в .env!")
        return

    TARGET_PER_CATEGORY = 100  # Сколько итоговых примеров (запросов) на категорию
    QUERIES_PER_TOPIC = 5  # Сколько вариантов на 1 тему генерирует LLM
    SITUATIONS_NEEDED = TARGET_PER_CATEGORY // QUERIES_PER_TOPIC  # Сколько тем нужно

    print(f"Начинаем масштабированную генерацию датасета...")
    print(f"Цель: {TARGET_PER_CATEGORY} записей на категорию ({TARGET_PER_CATEGORY * len(CATEGORIES)} всего).")

    start_time = time.time()
    semaphore = asyncio.Semaphore(10)
    total_generated = 0

    async with aiohttp.ClientSession() as session:
        for cat_key in CATEGORIES.keys():
            print(f"\n--- Обработка категории: {cat_key} ---")

            # 1. Извлекаем хардкодные темы из ТЗ для текущей категории
            situations = [item["topic"] for item in TZ_THEMES if item["category"] == cat_key]
            print(f"  [i] Найдено {len(situations)} тем из ТЗ для категории {cat_key}")

            # 2. Догенерируем недостающие (если в ТЗ было меньше тем, чем требуется)
            needed_to_generate = SITUATIONS_NEEDED - len(situations)
            if needed_to_generate > 0:
                generated_situations = await generate_situations(session, cat_key, needed_to_generate)
                situations.extend(generated_situations)

            # 3. Добиваем заглушками (предохранитель от ошибок API)
            idx = 1
            while len(situations) < SITUATIONS_NEEDED:
                situations.append(f"Запрос от сотрудника по теме '{CATEGORIES[cat_key]}' (вариант {idx})")
                idx += 1

            # Ограничиваем список ровно тем количеством, которое нам нужно
            situations = situations[:SITUATIONS_NEEDED]

            # 4. Запускаем генерацию 5 запросов для каждой ситуации (и хардкодных, и синтетических)
            tasks = [fetch_dataset_batch(session, topic, cat_key, semaphore) for topic in situations]

            category_results = []
            for task in asyncio.as_completed(tasks):
                batch = await task
                if isinstance(batch, list) and batch:
                    for item in batch:
                        if isinstance(item, dict):
                            request_id = f"req_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
                            timestamp = datetime.now(timezone.utc).isoformat()

                            query_text = item.get("query_text") or item.get("user_query", "")
                            tools = item.get("tools_used", [])
                            style = item.get("style") or random.choice(["formal", "voice", "typo", "jargon"])

                            # Реалистичный объем токенов для ИИ-агентов (контекст + рассуждения + тулзы)
                            llm_tokens = item.get("total_tokens")
                            if isinstance(llm_tokens, (int, float)) and llm_tokens >= 1000:
                                tokens = int(llm_tokens)
                            else:
                                base_tokens = random.randint(1200, 3500)
                                tools_tokens = len(tools) * random.randint(4500, 18000)
                                tokens = base_tokens + tools_tokens

                            final_record = {
                                "request_id": request_id,
                                "timestamp": timestamp,
                                "query_text": query_text,
                                "response_text": item.get("response_text", ""),
                                "status": item.get("status", "success"),
                                "category": cat_key,
                                "style": style,
                                "tools_used": tools,
                                "total_tokens": tokens,
                            }
                            category_results.append(final_record)
                    print(f"  [+] Завершено {len(batch)} логов (стиль: {style})")

            append_to_dataset(OUTPUT_FILE, category_results)
            total_generated += len(category_results)
            print(
                f"  [✓] Категория {cat_key} сохранена. Добавлено {len(category_results)} записей (Всего: {total_generated})")

    print(f"\nГенерация завершена за {time.time() - start_time:.2f} сек.")
    print(f"За сессию добавлено примеров: {total_generated}")
    print(f"Результат находится в {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())