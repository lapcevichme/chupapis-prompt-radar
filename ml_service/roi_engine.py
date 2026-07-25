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
    Полностью соответствует контракту БД проекта и датасету.
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    request_id: Optional[str] = None
    timestamp: Optional[str] = None
    user_id: Optional[str] = "unknown_user"
    user_name: Optional[str] = "Unknown"
    department: Optional[str] = "Unknown"
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
           Base Category Minutes * Session Length Coefficient * Tool Multiplier.
        """
        if self.status != "success":
            return 0.0

        if self.estimated_manual_time_minutes is not None:
            return float(self.estimated_manual_time_minutes)

        cat_key = self.category or "other"
        base_mins = CATEGORY_BASE_MINUTES.get(cat_key, 10.0)

        # Коэффициенты длины сессий из product_owners_pain.md:
        tokens = self.total_tokens
        if tokens > 50000:
            session_coeff = 2.0  # Длинные сессии / тяжелый RAG
        elif tokens >= 10000:
            session_coeff = 1.0  # Средние сессии
        else:
            session_coeff = 0.3  # Короткие быстрые сессии

        # Мультипликатор использования инструментов
        tool_multiplier = 1.0 + (0.25 * len(self.tools_used))

        return round(base_mins * session_coeff * tool_multiplier, 2)


class UserStats(BaseModel):
    """Статистика потребления ИИ по конкретному сотруднику."""
    user_id: str
    name: str
    department: str
    requests_count: int = 0
    tokens_consumed: int = 0
    wasted_tokens: int = 0
    cost_rub: float = 0.0


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
    Результат расчёта бизнес-метрик, финансового ROI и MAU аналитики.
    Готовая структура для отправки на дашборды CTO и Product Owner.
    """
    total_logs: int
    success_rate_percent: float
    total_tokens_consumed: int
    wasted_tokens_on_errors: int
    wasted_cost_rub: float

    # Пользовательские метрики (MAU / Heavy Users / Департаменты)
    mau_count: int
    top_spenders: List[UserStats]
    department_costs: Dict[str, float]

    # Юнит-экономика и Финансовые показатели (руб)
    total_fte_hours_saved: float
    fte_hourly_rate_rub: float
    token_cost_per_1k_rub: float
    total_manual_cost_rub: float
    total_agent_cost_rub: float
    net_savings_rub: float
    roi_multiplier: float
    cost_per_successful_action_rub: float

    # Аналитические коэффициенты
    token_value_index: float  # Сэкономленные FTE-часы на 1000 токенов
    process_automation_rate: float  # Доля запросов с использованием тулзов
    top_tools_used: Dict[str, int]

    # Аналитика стилей ввода (Voice / Mobile / Jargon / Formal)
    style_breakdown: Dict[str, int]
    style_percentages: Dict[str, float]
    mobile_voice_adoption_rate: float
    style_insight: str

    category_breakdown: Dict[str, CategoryMetric]


class ROICalculator:
    """
    Изолированный движок для подсчета бизнес-метрик, юнит-экономики и финансового ROI ИИ-агентов.
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
        users_analytics: Dict[str, UserStats] = {}
        department_costs: Dict[str, float] = {}

        for log in logs:
            tokens = log.total_tokens
            total_tokens += tokens
            cost_for_log = (tokens / 1000.0) * self.token_cost_per_1k_rub

            # Пользовательская аналитика (MAU & Heavy Users)
            uid = log.user_id or "unknown_user"
            uname = log.user_name or "Unknown"
            dept = log.department or "Unknown"

            if uid not in users_analytics:
                users_analytics[uid] = UserStats(user_id=uid, name=uname, department=dept)
            u_stat = users_analytics[uid]
            u_stat.requests_count += 1
            u_stat.tokens_consumed += tokens
            u_stat.cost_rub += cost_for_log

            # Затраты по департаментам
            department_costs[dept] = department_costs.get(dept, 0.0) + cost_for_log

            # Стили
            log_style = log.style or "formal"
            style_stats[log_style] = style_stats.get(log_style, 0) + 1

            # Категории
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
                u_stat.wasted_tokens += tokens

        total_fte_hours = total_saved_minutes / 60.0

        manual_cost = total_fte_hours * self.fte_hourly_rate_rub
        agent_cost = (total_tokens / 1000.0) * self.token_cost_per_1k_rub
        wasted_cost = (wasted_tokens / 1000.0) * self.token_cost_per_1k_rub
        net_savings = manual_cost - agent_cost
        roi_mult = round(manual_cost / agent_cost, 2) if agent_cost > 0 else 0.0
        cost_per_action = round(agent_cost / success_count, 2) if success_count > 0 else 0.0

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

        # Стили
        style_percentages = {
            st: round((cnt / total_logs) * 100, 1) for st, cnt in style_stats.items()
        }
        mobile_voice_count = style_stats.get("voice", 0) + style_stats.get("typo", 0)
        mobile_voice_rate = round((mobile_voice_count / total_logs) * 100, 1)

        insight = (
            f"📱 {mobile_voice_rate}% запросов поступают в неформальном/мобильном стиле (голос или опечатки с телефона). "
            f"Рекомендуется поддерживать и развивать Voice-to-Text интерфейс."
        )

        # Топ-3 Heavy Users
        sorted_users = sorted(users_analytics.values(), key=lambda x: x.tokens_consumed, reverse=True)
        top_spenders = sorted_users[:3]

        sorted_departments = {
            k: round(v, 2)
            for k, v in sorted(department_costs.items(), key=lambda item: item[1], reverse=True)
        }

        return ROISummary(
            total_logs=total_logs,
            success_rate_percent=round((success_count / total_logs) * 100, 1),
            total_tokens_consumed=total_tokens,
            wasted_tokens_on_errors=wasted_tokens,
            wasted_cost_rub=round(wasted_cost, 2),
            mau_count=len(users_analytics),
            top_spenders=top_spenders,
            department_costs=sorted_departments,
            total_fte_hours_saved=round(total_fte_hours, 2),
            fte_hourly_rate_rub=self.fte_hourly_rate_rub,
            token_cost_per_1k_rub=self.token_cost_per_1k_rub,
            total_manual_cost_rub=round(manual_cost, 2),
            total_agent_cost_rub=round(agent_cost, 2),
            net_savings_rub=round(net_savings, 2),
            roi_multiplier=roi_mult,
            cost_per_successful_action_rub=cost_per_action,
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
            wasted_cost_rub=0.0,
            mau_count=0,
            top_spenders=[],
            department_costs={},
            total_fte_hours_saved=0.0,
            fte_hourly_rate_rub=self.fte_hourly_rate_rub,
            token_cost_per_1k_rub=self.token_cost_per_1k_rub,
            total_manual_cost_rub=0.0,
            total_agent_cost_rub=0.0,
            net_savings_rub=0.0,
            roi_multiplier=0.0,
            cost_per_successful_action_rub=0.0,
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
        print("📊   БИЗНЕС ROI & MAU АНАЛИТИКА (ПРОДУКТОВЫЙ ОТЧЕТ)")
        print("==================================================")
        print(f"Пользователей (MAU):      {result.mau_count} уникальных сотрудников")
        print(f"Всего запросов:           {result.total_logs} (Успешность: {result.success_rate_percent}%)")
        print(f"Токенов сожжено:          {result.total_tokens_consumed:,}")
        print("--------------------------------------------------")
        print("💰 ФИНАНСЫ & ЮНИТ-ЭКОНОМИКА:")
        print(f"Экономия ФОТ:             {result.total_manual_cost_rub:,.2f} руб. ({result.total_fte_hours_saved} FTE-ч.)")
        print(f"Затраты на ИИ (API):      {result.total_agent_cost_rub:,.2f} руб.")
        print(f"ЧИСТАЯ ПРИБЫЛЬ:           {result.net_savings_rub:,.2f} руб. (x{result.roi_multiplier} ROI)")
        print(f"Цена успешного действия:  {result.cost_per_successful_action_rub:.2f} руб.")
        print(f"Слито на ошибках API/LLM: {result.wasted_cost_rub:.2f} руб. ({result.wasted_tokens_on_errors:,} токенов)")
        print("--------------------------------------------------")
        print("🔥 ТОП-3 'HEAVY USERS' (Больше всего тратят):")
        for u in result.top_spenders:
            print(f"  • {u.name} ({u.department}): {u.tokens_consumed:,} токенов | {u.cost_rub:.2f} руб. | {u.requests_count} запросов")
        print("--------------------------------------------------")
        print("🏢 ЗАТРАТЫ ПО ДЕПАРТАМЕНТАМ:")
        for dep, cost in result.department_costs.items():
            print(f"  • {dep}: {cost:,.2f} руб.")
        print("--------------------------------------------------")
        print(f"🗣️ СТИЛИ ВВОДА: {result.style_percentages}")
        print(f"{result.style_insight}")
        print("==================================================\n")
    else:
        print(f"Файл датасета не найден по путям: {possible_paths}")