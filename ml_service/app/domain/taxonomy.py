"""Taxonomy v1 — shared task_type vocabulary for ML classification."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set

# Canonical 7 classes (docs/taxonomy/taxonomy_v1.md). unknown is per-record only.
CORE_TASK_TYPES: tuple[str, ...] = (
    "text_generation",
    "code_help",
    "data_analysis",
    "education",
    "information_search",
    "task_management",
    "other",
)

SERVICE_TASK_TYPES: tuple[str, ...] = ("unknown",)

# Human-readable RU labels (fallback if markdown parse fails)
_DEFAULT_LABELS: Dict[str, str] = {
    "text_generation": "Генерация текста",
    "code_help": "Помощь с кодом",
    "data_analysis": "Анализ данных",
    "education": "Объяснение / обучение",
    "information_search": "Поиск информации",
    "task_management": "Планирование / задачи",
    "other": "Другое",
    "unknown": "Не уверены",
}

_DEFAULT_DESCRIPTIONS: Dict[str, str] = {
    "text_generation": "письма, инструкции, посты, ответы клиентам",
    "code_help": "написание/объяснение кода, ошибки, SQL-скрипты как код",
    "data_analysis": "Excel, аналитика, отчёты, выгрузки, SQL-запросы к данным",
    "education": "«объясни», «что значит», обучающие вопросы",
    "information_search": "сбор данных из CRM/Confluence/почты, ресёрч по компании",
    "task_management": "Jira/тикеты, встречи, напоминания, календарь",
    "other": "нерабочее, общие вопросы, аномалии",
    "unknown": "классификатор не уверен (confidence < порога)",
}

TAXONOMY_VERSION = "v1"


def _default_taxonomy_path() -> Path:
    """Resolve docs/taxonomy/taxonomy_v1.md from package or monorepo root."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "docs" / "taxonomy" / "taxonomy_v1.md",  # repo root
        here.parents[2] / "docs" / "taxonomy" / "taxonomy_v1.md",
        Path.cwd() / "docs" / "taxonomy" / "taxonomy_v1.md",
        Path.cwd().parent / "docs" / "taxonomy" / "taxonomy_v1.md",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return candidates[0]


class Taxonomy:
    """Taxonomy v1 integration for task types."""

    def __init__(self, taxonomy_path: Optional[Path] = None):
        self.taxonomy_path = Path(taxonomy_path) if taxonomy_path else _default_taxonomy_path()
        self.taxonomy: Dict[str, Dict] = {}
        self.version = TAXONOMY_VERSION
        self.load()

    def load(self) -> None:
        """Load taxonomy from markdown table; fall back to built-in defaults."""
        self.taxonomy = {}
        if self.taxonomy_path.is_file():
            self._load_from_markdown(self.taxonomy_path)
        # Ensure all core + service types exist
        for tt in CORE_TASK_TYPES:
            if tt not in self.taxonomy:
                self.taxonomy[tt] = {
                    "task_type": tt,
                    "label": _DEFAULT_LABELS[tt],
                    "description": _DEFAULT_DESCRIPTIONS[tt],
                }
        for tt in SERVICE_TASK_TYPES:
            if tt not in self.taxonomy:
                self.taxonomy[tt] = {
                    "task_type": tt,
                    "label": _DEFAULT_LABELS[tt],
                    "description": _DEFAULT_DESCRIPTIONS[tt],
                }

    def _load_from_markdown(self, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line.startswith("| `"):
                continue
            parts = [p.strip() for p in line.split("|")]
            # parts[0] empty, parts[1]=`task_type`, parts[2]=label, parts[3]=desc
            if len(parts) < 3:
                continue
            raw = parts[1]
            m = re.match(r"`([^`]+)`", raw)
            if not m:
                continue
            task_type = m.group(1).strip()
            if task_type in ("task_type", "---") or not task_type:
                continue
            label = parts[2].strip() if len(parts) > 2 else task_type
            description = parts[3].strip() if len(parts) > 3 else ""
            self.taxonomy[task_type] = {
                "task_type": task_type,
                "label": label,
                "description": description,
            }

    def get_task_type(self, label: str) -> Optional[str]:
        for t in self.taxonomy.values():
            if t.get("label") == label:
                return t["task_type"]
        return None

    def get_labels(self) -> List[str]:
        """All known keys including service types."""
        return list(self.taxonomy.keys())

    def get_core_labels(self) -> List[str]:
        """Classification targets only (no unknown)."""
        return [t for t in CORE_TASK_TYPES if t in self.taxonomy]

    def get_label(self, task_type: str) -> str:
        return self.taxonomy.get(task_type, {}).get("label", task_type)

    def get_description(self, task_type: str) -> str:
        return self.taxonomy.get(task_type, {}).get("description", "")

    def is_valid(self, task_type: str, *, allow_unknown: bool = True) -> bool:
        if task_type in CORE_TASK_TYPES:
            return True
        if allow_unknown and task_type == "unknown":
            return True
        return False

    def normalize(self, raw: str) -> Optional[str]:
        """Map free-form model output to a core task_type (or None)."""
        if not raw:
            return None
        s = raw.strip().strip("`\"'").lower().replace(" ", "_").replace("-", "_")
        if s in CORE_TASK_TYPES:
            return s
        # label match (RU)
        for tt, meta in self.taxonomy.items():
            if tt == "unknown":
                continue
            if meta.get("label", "").lower() == raw.strip().lower():
                return tt
        # partial: first token is a valid class
        token = s.split()[0] if s else ""
        if token in CORE_TASK_TYPES:
            return token
        return None

    def core_set(self) -> Set[str]:
        return set(CORE_TASK_TYPES)
