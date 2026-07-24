"""Taxonomy v1: shared task classes and human-readable RU labels."""

TAXONOMY_VERSION = "v1"

# 7 v1 classes + service values (unknown/other), mapped to dashboard labels.
TASK_LABELS: dict[str, str] = {
    "text_generation": "Генерация текста",
    "code_help": "Помощь с кодом",
    "data_analysis": "Анализ данных",
    "education": "Объяснение / обучение",
    "information_search": "Поиск информации",
    "task_management": "Планирование / задачи",
    "other": "Другое",
    "unknown": "Не уверены",
}


def label(task_type: str | None) -> str:
    """Return the RU label for a task_type; unknown/None -> 'Не уверены'."""
    if not task_type:
        return TASK_LABELS["unknown"]
    return TASK_LABELS.get(task_type, TASK_LABELS["other"])
