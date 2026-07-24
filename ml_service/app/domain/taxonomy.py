import json
from pathlib import Path
from typing import Dict, List, Optional

class Taxonomy:
    """Taxonomy v1 integration for task types."""

    def __init__(self, taxonomy_path: Path = Path(__file__).parent.parent.parent.parent / "docs/taxonomy/taxonomy_v1.md"):
        self.taxonomy_path = taxonomy_path
        self.taxonomy: Dict[str, Dict] = {}
        self.load()

    def load(self):
        """Load taxonomy from markdown table."""
        with open(self.taxonomy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        current = None
        for line in lines:
            line = line.strip()
            if line.startswith("| `") and "| " in line:
                parts = line.split("|")
                task_type = parts[1].strip().strip("`")
                if task_type:
                    label = parts[2].strip()
                    description = parts[3].strip() if len(parts) > 4 else ""
                    self.taxonomy[task_type] = {
                        "label": label,
                        "description": description,
                        "task_type": task_type
                    }
        # Add unknown and other if not present
        if "unknown" not in self.taxonomy:
            self.taxonomy["unknown"] = {"label": "Не уверены", "description": "Классификатор не уверен", "task_type": "unknown"}
        if "other" not in self.taxonomy:
            self.taxonomy["other"] = {"label": "Другое", "description": "Нерабочее / общие вопросы / аномалии", "task_type": "other"}

    def get_task_type(self, label: str) -> Optional[str]:
        for t in self.taxonomy.values():
            if t.get("label") == label:
                return t["task_type"]
        return None

    def get_labels(self) -> List[str]:
        return list(self.taxonomy.keys())

    def get_label(self, task_type: str) -> str:
        return self.taxonomy.get(task_type, {}).get("label", task_type)
