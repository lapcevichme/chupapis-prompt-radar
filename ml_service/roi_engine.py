import json
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

# Базовая экспертная оценка ручного времени по категориям (в минутах) из product_owners_pain.md
CATEGORY_BASE_MINUTES: Dict[str, float] = {
    "text_generation": 15.0,    # Генерация текста (письма, посты)
    "code_help": 30.0,          # Помощь с кодом
    "data_analysis": 45.0,      # Анализ данных, Excel, SQL
    "education": 20.0,          # Объяснение / обучение
    "information_search": 15.0,  # Поиск / сбор информации
    "task_management": 25.0,    # Планирование / задачи
    "other": 10.0               # Прочие вопросы
}


class AgentLog(BaseModel):
    """
    Модель входящего лога из БД / ML-сервиса.
    Полностью соответствует контракту БД проекта.
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    request_id: Optional[str] = None
    timestamp: Optional[str] = None
    query_text: Optional[str] = None
    user_query: Optional[str] = None  # fallback
    response_text: Optional[str] = None
    status: Optional[str] = "success"
    category: Optional[str] = "other"
    style: Optional[str] = "formal"
    total_tokens: int = Field(default=0, ge=0)
    tools_used: List[str] = Field(default_factory=list)
    estimated_manual_time_minutes: Optional[float] = None

    @property
    def effective_query(self) -> str:
        return self.query_text or self.user_query or ""

    @property
    def effective_saved_minutes(self) -> float:
        """
        Расчёт сэкономленного времени по алгоритму из product_owners_pain.md:
        1. Если есть явно заданный / предсказанный ML 'estimated_manual_time_minutes', используем его.
        2. Иначе рассчитываем по алгоритму Product Owner:
           Base Category Minutes * Session Length Coefficient (0.3 / 1.0 / 2.0) * Tool Multiplier.
        """
        if self.status != "success":
            return 0.0

        if self.estimated_manual_time_minutes is not None:
            return float(self.estimated_manual_time_minutes)

        cat_key = self.category or "other"
        base_mins = CATEGORY_BASE_MINUTES.get(cat_key, 10.0)

        # Коэффициенты длины сессий из product_owners_pain.md:
        # Короткая сессия (< 1000 токенов) -> 0.3
        # Средняя сессия (1000 - 5000 токенов) -> 1.0
        # Длинная сессия (> 5000 токенов) -> 2.0
        tokens = self.total_tokens
        if tokens < 1000:
            session_coeff = 0.3
        elif tokens <= 5000:
            session_coeff = 1.0
        else:
            session_coeff = 2.0

        # Мультипликатор использования инструментов
        tool_multiplier = 1.0 + (0.25 * len(self.tools_used))

        return round(base_mins * session_coeff * tool_multiplier, 2)


class CategoryMetric(BaseModel):
    """Метрики по отдельной категории задач."""
    count: int
    success_count: int
    success_rate_percent: float
    saved_minutes: float
    tokens_used: int
    fte_hours_saved: float


class ROISummary(BaseModel):
    """
    Результат расчёта бизнес-метрик и финансового ROI.
    Готовая структура для отправки на дашборды.
    """
    total_logs: int
    success_rate_percent: float
    total_tokens_consumed: int
    wasted_tokens_on_errors: int
    total_fte_hours_saved: float

    # Финансовые показатели (руб)
    fte_hourly_rate_rub: float
    token_cost_per_1k_rub: float
    total_manual_cost_rub: float
    total_agent_cost_rub: float
    net_savings_rub: float
    roi_multiplier: float

    # Аналитические коэффициенты
    token_value_index: float  # Сэкономленные FTE-часы на 1000 токенов
    process_automation_rate: float  # Доля запросов с использованием тулзов
    top_tools_used: Dict[str, int]
    
    # Аналитика стилей ввода (Voice / Mobile / Jargon / Formal)
    style_breakdown: Dict[str, int]
    style_percentages: Dict[str, float]
    mobile_voice_adoption_rate: float  # % мобильного/голосового ввода (voice + typo)
    style_insight: str
    
    category_breakdown: Dict[str, CategoryMetric]


class ROICalculator:
    """
    Изолированный движок для подсчета бизнес-метрик и финансового ROI ИИ-агентов.
    """

    def __init__(self, fte_hourly_rate_rub: float = 1200.0, token_cost_per_1k_rub: float = 0.015):
        self.fte_hourly_rate_rub = fte_hourly_rate_rub
        self.token_cost_per_1k_rub = token_cost_per_1k_rub

    def calculate(self, logs: List[AgentLog]) -> ROISummary:
        if not logs:
            return self._empty_summary()

        total_logs = len(logs)
        success_count = 0
        total_tokens = 0
        wasted_tokens = 0
        total_saved_minutes = 0.0
        automation_count = 0

        tools_frequency: Dict[str, int] = {}
        style_stats: Dict[str, int] = {}
        category_raw_stats: Dict[str, Dict[str, Any]] = {}

        for log in logs:
            tokens = log.total_tokens
            total_tokens += tokens

            log_style = log.style or "formal"
            style_stats[log_style] = style_stats.get(log_style, 0) + 1

            cat_key = log.category or "other"
            if cat_key not in category_raw_stats:
                category_raw_stats[cat_key] = {
                    "count": 0,
                    "success_count": 0,
                    "saved_minutes": 0.0,
                    "tokens_used": 0
                }

            cat = category_raw_stats[cat_key]
            cat["count"] += 1
            cat["tokens_used"] += tokens

            if log.status == "success":
                success_count += 1
                cat["success_count"] += 1
                saved_mins = log.effective_saved_minutes
                total_saved_minutes += saved_mins
                cat["saved_minutes"] += saved_mins

                if len(log.tools_used) > 0:
                    automation_count += 1
                    for tool in log.tools_used:
                        tools_frequency[tool] = tools_frequency.get(tool, 0) + 1
            else:
                wasted_tokens += tokens

        total_fte_hours = total_saved_minutes / 60.0

        manual_cost = total_fte_hours * self.fte_hourly_rate_rub
        agent_cost = (total_tokens / 1000.0) * self.token_cost_per_1k_rub
        net_savings = manual_cost - agent_cost
        roi_mult = round(manual_cost / agent_cost, 2) if agent_cost > 0 else 0.0

        tvi = round(total_fte_hours / (total_tokens / 1000.0), 4) if total_tokens > 0 else 0.0

        categories_formatted: Dict[str, CategoryMetric] = {}
        for c_key, c_data in category_raw_stats.items():
            cnt = c_data["count"]
            succ = c_data["success_count"]
            categories_formatted[c_key] = CategoryMetric(
                count=cnt,
                success_count=succ,
                success_rate_percent=round((succ / cnt) * 100, 1) if cnt > 0 else 0.0,
                saved_minutes=round(c_data["saved_minutes"], 2),
                tokens_used=c_data["tokens_used"],
                fte_hours_saved=round(c_data["saved_minutes"] / 60.0, 2)
            )

        top_tools = dict(sorted(tools_frequency.items(), key=lambda item: item[1], reverse=True))

        # Расчет аналитики по стилям (Mobile / Voice / Jargon adoption)
        style_percentages = {
            st: round((cnt / total_logs) * 100, 1) for st, cnt in style_stats.items()
        }
        mobile_voice_count = style_stats.get("voice", 0) + style_stats.get("typo", 0)
        mobile_voice_rate = round((mobile_voice_count / total_logs) * 100, 1)

        insight = (
            f"📱 {mobile_voice_rate}% запросов поступают в неформальном/мобильном стиле (голос или опечатки с телефона). "
            f"Рекомендуется поддерживать и развивать Voice-to-Text интерфейс."
        )

        return ROISummary(
            total_logs=total_logs,
            success_rate_percent=round((success_count / total_logs) * 100, 1),
            total_tokens_consumed=total_tokens,
            wasted_tokens_on_errors=wasted_tokens,
            total_fte_hours_saved=round(total_fte_hours, 2),
            fte_hourly_rate_rub=self.fte_hourly_rate_rub,
            token_cost_per_1k_rub=self.token_cost_per_1k_rub,
            total_manual_cost_rub=round(manual_cost, 2),
            total_agent_cost_rub=round(agent_cost, 2),
            net_savings_rub=round(net_savings, 2),
            roi_multiplier=roi_mult,
            token_value_index=tvi,
            process_automation_rate=round((automation_count / total_logs) * 100, 1),
            top_tools_used=top_tools,
            style_breakdown=style_stats,
            style_percentages=style_percentages,
            mobile_voice_adoption_rate=mobile_voice_rate,
            style_insight=insight,
            category_breakdown=categories_formatted
        )

    def _empty_summary(self) -> ROISummary:
        return ROISummary(
            total_logs=0,
            success_rate_percent=0.0,
            total_tokens_consumed=0,
            wasted_tokens_on_errors=0,
            total_fte_hours_saved=0.0,
            fte_hourly_rate_rub=self.fte_hourly_rate_rub,
            token_cost_per_1k_rub=self.token_cost_per_1k_rub,
            total_manual_cost_rub=0.0,
            total_agent_cost_rub=0.0,
            net_savings_rub=0.0,
            roi_multiplier=0.0,
            token_value_index=0.0,
            process_automation_rate=0.0,
            top_tools_used={},
            style_breakdown={},
            style_percentages={},
            mobile_voice_adoption_rate=0.0,
            style_insight="",
            category_breakdown={}
        )


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    possible_paths = [
        os.path.join(BASE_DIR, "notebooks", "prompt_radar_dataset.json"),
        os.path.join(BASE_DIR, "prompt_radar_dataset.json")
    ]

    dataset_file = next((p for p in possible_paths if os.path.exists(p)), None)

    if dataset_file:
        print(f"Загрузка реальных логов из датасета: {dataset_file}")
        with open(dataset_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        parsed_logs = [AgentLog(**item) for item in raw_data]

        engine = ROICalculator(fte_hourly_rate_rub=1200.0, token_cost_per_1k_rub=0.015)
        result = engine.calculate(parsed_logs)

        print("\n==================================================")
        print("📊   БИЗНЕС И ФИНАНСОВЫЙ ROI ENGINE (РЕАЛЬНЫЕ ДАННЫЕ)")
        print("==================================================")
        print(f"Обработано логов: {result.total_logs}")
        print(f"Успешность (Success Rate): {result.success_rate_percent}%")
        print(f"Уровень автоматизации: {result.process_automation_rate}% (с инструментами)")
        print("--------------------------------------------------")
        print(f"⏱️ Сэкономлено времени: {result.total_fte_hours_saved} FTE-часов")
        print(f"💼 Эквивалент ручного труда: {result.total_manual_cost_rub:,.2f} руб.")
        print(f"🤖 Затраты на ИИ-агентов (API): {result.total_agent_cost_rub:,.2f} руб.")
        print(f"💎 ЧИСТАЯ ЭКОНОМИЯ (Net Savings): {result.net_savings_rub:,.2f} руб.")
        print(f"🚀 ROI Множитель: {result.roi_multiplier}x")
        print("--------------------------------------------------")
        print(f"🗣️ Распределение стилей ввода: {result.style_percentages}")
        print(f"{result.style_insight}")
        print("--------------------------------------------------")
        print(f"🔥 Всего токенов: {result.total_tokens_consumed}")
        print(f"📈 TVI (FTE-часов / 1k токенов): {result.token_value_index}")
        print(f"🛠️ Топ инструментов: {result.top_tools_used}")
        print("==================================================\n")
    else:
        print(f"Файл датасета не найден по путям: {possible_paths}")