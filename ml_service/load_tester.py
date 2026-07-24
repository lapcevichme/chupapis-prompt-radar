import argparse
import asyncio
import aiohttp
import json
import os
import sys
import time
from typing import List, Dict, Any

DEFAULT_DATASET_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "notebooks", "prompt_radar_dataset.json"
)


def load_dataset(file_path: str) -> List[Dict[str, Any]]:
    """Загружает логи из указанного JSON-файла."""
    if not os.path.exists(file_path):
        print(f"❌ Файл датасета не найден: {file_path}")
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "logs" in data:
                return data["logs"]
            else:
                print("⚠️ Формат JSON не является списком логов.")
                return []
    except Exception as e:
        print(f"❌ Ошибка чтения файла {file_path}: {e}")
        return []


async def send_batch(
    session: aiohttp.ClientSession,
    url: str,
    headers: Dict[str, str],
    batch: List[Dict[str, Any]],
    source_id: str,
    semaphore: asyncio.Semaphore,
) -> tuple[int, bool, int]:
    """Отправляет один батч логов на указанный эндпоинт."""
    async with semaphore:
        payload = {
            "source_id": source_id,
            "logs": batch
        }
        try:
            async with session.put(url, json=payload, headers=headers, timeout=10) as response:
                if response.status in (200, 201, 202):
                    return len(batch), True, response.status
                else:
                    err_text = await response.text()
                    print(f" ⚠️ [HTTP {response.status}] Ошибка отправки батча: {err_text[:100]}")
                    return len(batch), False, response.status
        except Exception as e:
            print(f" ❌ Ошибка подключения: {e}")
            return len(batch), False, 0


async def run_load_test(
    url: str,
    file_path: str,
    batch_size: int,
    concurrency: int,
    delay: float,
    token: str,
    source_id: str,
    repeat: int,
):
    """Главная функция асинхронной бомбардировки эндпоинта."""
    print("==================================================")
    print("🚀   СТАРТ СИМУЛЯЦИИ НАГРУЗКИ / НАГРУЗОЧНОГО ТЕСТИРОВАНИЯ")
    print("==================================================")
    print(f"🎯 Эндпоинт:    {url}")
    print(f"📂 Файл данных:  {file_path}")
    print(f"📦 Размер батча: {batch_size} логов / запрос")
    print(f"⚡ Конкурентность: {concurrency} параллельных потоков")
    print(f"⏱️ Задержка:     {delay} сек. между батчами")
    print("--------------------------------------------------")

    logs = load_dataset(file_path)
    if not logs:
        print("🛑 Нет данных для отправки. Нагрузочное тестирование остановлено.")
        return

    # Если задан флаг повтора, умножаем датасет
    total_logs_to_send = logs * repeat
    print(f"📊 Загружено {len(logs)} исходных записей. Подготовлено к отправке: {len(total_logs_to_send)} логов.")

    batches = [
        total_logs_to_send[i : i + batch_size]
        for i in range(0, len(total_logs_to_send), batch_size)
    ]

    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Service-Token"] = token
        headers["Authorization"] = f"Bearer {token}"

    semaphore = asyncio.Semaphore(concurrency)
    start_time = time.time()

    success_logs = 0
    failed_logs = 0
    success_batches = 0
    failed_batches = 0

    async with aiohttp.ClientSession() as session:
        tasks = []
        for i, batch in enumerate(batches):
            task = send_batch(session, url, headers, batch, source_id, semaphore)
            tasks.append(task)
            if delay > 0:
                await asyncio.sleep(delay)

        print(f"\n📡 Отправка {len(batches)} батчей...")
        results = await asyncio.gather(*tasks)

        for log_count, ok, status in results:
            if ok:
                success_logs += log_count
                success_batches += 1
            else:
                failed_logs += log_count
                failed_batches += 1

    elapsed = time.time() - start_time
    total_sent = success_logs + failed_logs
    rps = total_sent / elapsed if elapsed > 0 else 0
    batches_per_sec = (success_batches + failed_batches) / elapsed if elapsed > 0 else 0

    print("\n==================================================")
    print("🏁   РЕЗУЛЬТАТЫ НАГРУЗОЧНОГО ТЕСТИРОВАНИЯ")
    print("==================================================")
    print(f"⏱️ Общее время:          {elapsed:.2f} сек.")
    print(f"✅ Успешно отправлено:   {success_logs} логов ({success_batches} батчей)")
    print(f"❌ Ошибок отправки:     {failed_logs} логов ({failed_batches} батчей)")
    print(f"🚀 Пропускная способность: {rps:.1f} логов/сек ({batches_per_sec:.1f} батчей/сек)")
    print("==================================================\n")


def main():
    parser = argparse.ArgumentParser(
        description="Скрипт нагрузочного тестирования / бомбардировки логами эндпоинта PromptRadar."
    )
    parser.add_argument(
        "-u",
        "--url",
        default="http://localhost:8000/api/v1/logs",
        help="URL эндпоинта для приема логов (default: http://localhost:8000/api/v1/logs)",
    )
    parser.add_argument(
        "-f",
        "--file",
        default=DEFAULT_DATASET_PATH,
        help="Путь к JSON-файлу с датасетом логов",
    )
    parser.add_argument(
        "-b",
        "--batch-size",
        type=int,
        default=10,
        help="Размер батча (количество логов в 1 запросе, default: 10)",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=5,
        help="Количество параллельных асинхронных потоков (default: 5)",
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=float,
        default=0.05,
        help="Задержка между отправками батчей в секундах (default: 0.05)",
    )
    parser.add_argument(
        "-t",
        "--token",
        default="",
        help="Секретный токен авторизации (X-Service-Token)",
    )
    parser.add_argument(
        "-s",
        "--source-id",
        default="load_tester_src_01",
        help="Идентификатор источника данных (source_id)",
    )
    parser.add_argument(
        "-r",
        "--repeat",
        type=int,
        default=1,
        help="Количество циклов повтора датасета для увеличения нагрузки (default: 1)",
    )

    args = parser.parse_args()

    asyncio.run(
        run_load_test(
            url=args.url,
            file_path=args.file,
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            delay=args.delay,
            token=args.token,
            source_id=args.source_id,
            repeat=args.repeat,
        )
    )


if __name__ == "__main__":
    main()
