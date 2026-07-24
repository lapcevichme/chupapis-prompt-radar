import json
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class AgentLog(BaseModel):
    """
    Модель входящего лога взаимодействия пользователя с ИИ-агентом.
    Контракт между бэкендом/ML и ROI Engine.
    """
    model_config = ConfigDict(extra="ignore")

    user_query: str
    category: str
    style: Optional[str] = "formal"
    simulated_context_tokens: int = Field(default=0, ge=0)
    agent_steps: int = Field(default=1, ge=1)
    tools_used: List[str] = Field(default_factory=list)
    estimated_manual_time_minutes: int = Field(default=0, ge=0)
    status: str


class CategoryMetric(BaseModel):
    """Метрики по отдельной категории задач."""
    count: int
    success_count: int
    success_rate_percent: float
    saved_minutes: int
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
    roi_multiplier: float  # во сколько раз агент дешевле ручного труда (e.g. 15.5x)

    # Аналитические коэффициенты
    token_value_index: float  # Сэкономленные FTE-часы на 1000 токенов
    process_automation_rate: float  # Доля запросов с использованием тулзов
    top_tools_used: Dict[str, int]
    style_breakdown: Dict[str, int]
    category_breakdown: Dict[str, CategoryMetric]


class ROICalculator:
    """
    Изолированный движок для подсчета бизнес-метрик и финансового ROI ИИ-агентов.
    """

    def __init__(self, fte_hourly_rate_rub: float = 1200.0, token_cost_per_1k_rub: float = 0.015):
        """
        :param fte_hourly_rate_rub: Средняя стоимость 1 часа работы сотрудника (руб/час)
        :param token_cost_per_1k_rub: Стоимость 1000 токенов модели (руб)
        """
        self.fte_hourly_rate_rub = fte_hourly_rate_rub
        self.token_cost_per_1k_rub = token_cost_per_1k_rub

    def calculate(self, logs: List[AgentLog]) -> ROISummary:
        if not logs:
            return self._empty_summary()

        total_logs = len(logs)
        success_count = 0
        total_tokens = 0
        wasted_tokens = 0
        total_saved_minutes = 0
        automation_count = 0

        tools_frequency: Dict[str, int] = {}
        style_stats: Dict[str, int] = {}
        category_raw_stats: Dict[str, Dict[str, Any]] = {}

        for log in logs:
            total_tokens += log.simulated_context_tokens

            # Учет стилей
            log_style = log.style or "unknown"
            style_stats[log_style] = style_stats.get(log_style, 0) + 1

            # Инициализация категории
            if log.category not in category_raw_stats:
                category_raw_stats[log.category] = {
                    "count": 0,
                    "success_count": 0,
                    "saved_minutes": 0,
                    "tokens_used": 0
                }

            cat = category_raw_stats[log.category]
            cat["count"] += 1
            cat["tokens_used"] += log.simulated_context_tokens

            if log.status == "success":
                success_count += 1
                cat["success_count"] += 1
                total_saved_minutes += log.estimated_manual_time_minutes
                cat["saved_minutes"] += log.estimated_manual_time_minutes

                if len(log.tools_used) > 0:
                    automation_count += 1
                    for tool in log.tools_used:
                        tools_frequency[tool] = tools_frequency.get(tool, 0) + 1
            else:
                wasted_tokens += log.simulated_context_tokens

        total_fte_hours = total_saved_minutes / 60.0

        # Расчет финансовых метрик
        manual_cost = total_fte_hours * self.fte_hourly_rate_rub
        agent_cost = (total_tokens / 1000.0) * self.token_cost_per_1k_rub
        net_savings = manual_cost - agent_cost
        roi_mult = round(manual_cost / agent_cost, 2) if agent_cost > 0 else 0.0

        # Token Value Index (FTE часов на 1000 токенов)
        tvi = round(total_fte_hours / (total_tokens / 1000.0), 4) if total_tokens > 0 else 0.0

        # Формирование подробных метрик категорий через Pydantic
        categories_formatted: Dict[str, CategoryMetric] = {}
        for c_key, c_data in category_raw_stats.items():
            cnt = c_data["count"]
            succ = c_data["success_count"]
            categories_formatted[c_key] = CategoryMetric(
                count=cnt,
                success_count=succ,
                success_rate_percent=round((succ / cnt) * 100, 1) if cnt > 0 else 0.0,
                saved_minutes=c_data["saved_minutes"],
                tokens_used=c_data["tokens_used"],
                fte_hours_saved=round(c_data["saved_minutes"] / 60.0, 2)
            )

        # Сортировка популярных тулзов
        top_tools = dict(sorted(tools_frequency.items(), key=lambda item: item[1], reverse=True))

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
            category_breakdown={}
        )


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # Поиск файла датасета (в notebooks/ или в ml_service/)
    possible_paths = [
        os.path.join(BASE_DIR, "notebooks", "prompt_radar_dataset.json"),
        os.path.join(BASE_DIR, "prompt_radar_dataset.json")
    ]
    
    dataset_file = next((p for p in possible_paths if os.path.exists(p)), None)

    if dataset_file:
        print(f"Загрузка данных из датасета: {dataset_file}")
        with open(dataset_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        # Строгая Pydantic валидация
        parsed_logs = [AgentLog(**item) for item in raw_data]

        engine = ROICalculator(fte_hourly_rate_rub=1200.0, token_cost_per_1k_rub=0.015)
        result = engine.calculate(parsed_logs)

        print("\n=== БИЗНЕС И ФИНАНСОВЫЙ ROI ENGINE ===")
        print(f"Всего логов в датасете: {result.total_logs}")
        print(f"Успешность (Success Rate): {result.success_rate_percent}%")
        print(f"Уровень автоматизации: {result.process_automation_rate}% (с инструментами)")
        print("--------------------------------------------------")
        print(f"⏱️ Сэкономлено времени: {result.total_fte_hours_saved} FTE-часов")
        print(f"💼 Эквивалент ручного труда: {result.total_manual_cost_rub:,.2f} руб.")
        print(f"🤖 Затраты на ИИ-агентов (API): {result.total_agent_cost_rub:,.2f} руб.")
        print(f"💎 ЧИСТАЯ ЭКОНОМИЯ (Net Savings): {result.net_savings_rub:,.2f} руб.")
        print(f"🚀 ROI Множитель: {result.roi_multiplier}x")
        print("--------------------------------------------------")
        print(f"🔥 Всего токенов: {result.total_tokens_consumed}")
        print(f"🗑️ Токены на ошибках: {result.wasted_tokens_on_errors}")
        print(f"📈 TVI (FTE-часов / 1k токенов): {result.token_value_index}")
        print(f"🛠️ Популярность тулзов: {result.top_tools_used}")
        print("==================================================\n")
    else:
        print(f"Файл датасета не найден по путям: {possible_paths}")