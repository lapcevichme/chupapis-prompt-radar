# 📡 PromptRadar (Chupapis Prompt Radar)

Микросервис аналитики, классификации и расчёта бизнес-ROI для корпоративных ИИ-агентов и систем на базе LLM.

---

### 🚀 Быстрый старт ML-сервиса

Все зависимости сервиса управляются через `uv`:

```bash
cd ml_service

# 1. Установка всех зависимостей
uv sync

# 2. Генерация синтетического датасета
uv run python dataset.py

# 3. Запуск расчёта бизнес и финансового ROI
uv run python roi_engine.py
```

---

### 🌐 Интеграция с Open WebUI (OWUI)

Для перехвата диалогов пользователей в веб-интерфейсе Open WebUI используется фильтр-коннектор [`ml_service/filter.py`](file:///home/lapcevichme/crochack/ml_service/filter.py) (OWUI Pipelines Filter).

#### 1. Запуск Open WebUI через Docker Compose
Запустите контейнеры в фоновом режиме:
```bash
sudo docker compose up -d
```

#### 2. Установка фильтра перехвата логов в OWUI
1. Откройте веб-интерфейс Open WebUI в браузере (по умолчанию `http://localhost:3000`).
2. Перейдите в **Admin Panel** $\rightarrow$ **Pipelines / Filters** $\rightarrow$ **Add Filter**.
3. Вставьте содержимое файла [`ml_service/filter.py`](file:///home/lapcevichme/crochack/ml_service/filter.py).
4. Активируйте фильтр для нужных моделей/чатов.
5. При необходимости укажите URL бэкенда в настройках фильтра (**Valves**):
   - `BACKEND_URL`: `http://backend:8000/api/v1/logs` (или `http://host.docker.internal:8000/api/v1/logs`)
   - `BACKEND_SERVICE_TOKEN`: секретный токен бэкенда.

Фильтр автоматически дублирует логи локально в файл (`LOG_FILE_PATH`) и асинхронно стримит их по HTTP на бэкенд (`BACKEND_URL`).

---

### 🛠 Диагностика и проверка логов OWUI

Выполните следующие команды для проверки работы контейнера и сбора логов:

* **Просмотр логов контейнера Open WebUI**:
  ```bash
  sudo docker logs --tail 100 open-webui
  ```

* **Просмотр записанных перехваченных логов (JSONL)**:
  ```bash
  sudo docker exec -it open-webui cat /app/backend/data/input.jsonl
  ```

---

### 📊 Бизнес-метрики и ROI Engine

Модуль [`ml_service/roi_engine.py`](file:///home/lapcevichme/crochack/ml_service/roi_engine.py) реализует методику оценки эффективности ИИ-агентов на основе алгоритмов Product Owner:

* **FTE-часы**: Сэкономленное время сотрудников.
* **Финансовый ROI**: Чистая экономия в рублях (с учётом зарплатной ставки и расходов на API LLM).
* **TVI (Token Value Index)**: Сэкономленные FTE-часы на каждые 1,000 токенов.
* **Аналитика стилей**: Оценка доли мобильного и голосового ввода (`voice`, `typo`, `formal`, `jargon`).

### 💣 Нагрузочное тестирование & Стресс-тест бэкенда

Скрипт [`ml_service/load_tester.py`](file:///home/lapcevichme/crochack/ml_service/load_tester.py) берет сгенерированный датасет и асинхронно отправляет батчи логов на эндпоинт (`PUT /api/v1/logs`):

```bash
cd ml_service

# Запуск стандартной бомбардировки локального бэкенда
uv run python load_tester.py

# Запуск с кастомным URL, размером батча (20) и 10 параллельными потоками
uv run python load_tester.py --url http://localhost:8000/api/v1/logs --batch-size 20 --concurrency 10 --repeat 5
```

---

### Technologies

* **Claude Code**: @laughin_me
* **Antigravity**: @lapcevichme
* **Grok Build**: @oatis123

