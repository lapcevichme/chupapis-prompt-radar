"""Classification eval skeleton: accuracy / macro-F1 / unknown rate.

Gold labels come from log metadata (`metadata.gold_category`) or a flat field
`gold_category` / `category`. Dry-run friendly — no training, no I/O required.

Usage (offline):
    from eval.classification_eval import evaluate_classification, extract_gold_labels
    metrics = evaluate_classification(y_true, y_pred)
    print(metrics.as_dict())
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.domain.taxonomy import CORE_TASK_TYPES


@dataclass
class ClassificationMetrics:
    n: int = 0
    n_with_gold: int = 0
    accuracy: float = 0.0
    macro_f1: float = 0.0
    unknown_rate: float = 0.0
    per_class: Dict[str, Dict[str, float]] = field(default_factory=dict)
    confusion: Dict[str, Dict[str, int]] = field(default_factory=dict)
    notes: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def extract_gold_labels(records: Iterable[Dict[str, Any]]) -> List[Optional[str]]:
    """Pull gold task_type from log-like dicts (contract: metadata.gold_category)."""
    out: List[Optional[str]] = []
    for r in records:
        gold = None
        meta = r.get("metadata") or {}
        if isinstance(meta, dict):
            gold = meta.get("gold_category") or meta.get("category")
        if gold is None:
            gold = r.get("gold_category") or r.get("category")
        if gold is not None:
            gold = str(gold).strip()
            if not gold:
                gold = None
        out.append(gold)
    return out


def _f1(tp: int, fp: int, fn: int) -> float:
    if tp == 0 and fp == 0 and fn == 0:
        return 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def evaluate_classification(
    y_true: Sequence[Optional[str]],
    y_pred: Sequence[str],
    *,
    labels: Optional[Sequence[str]] = None,
    unknown_label: str = "unknown",
) -> ClassificationMetrics:
    """Compute accuracy, macro-F1 (over core classes), unknown rate.

    Rows without gold are skipped for accuracy/F1 but count toward n and
    unknown_rate (unknown_rate is over all predictions).
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred length mismatch")

    label_list = list(labels) if labels is not None else list(CORE_TASK_TYPES)
    n = len(y_pred)
    unknown_count = sum(1 for p in y_pred if p == unknown_label)
    unknown_rate = unknown_count / n if n else 0.0

    pairs = [(t, p) for t, p in zip(y_true, y_pred) if t is not None]
    n_gold = len(pairs)
    if n_gold == 0:
        return ClassificationMetrics(
            n=n,
            n_with_gold=0,
            unknown_rate=unknown_rate,
            notes="no gold labels — accuracy/F1 skipped",
        )

    correct = sum(1 for t, p in pairs if t == p)
    accuracy = correct / n_gold

    # confusion: true → pred counts
    confusion: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for t, p in pairs:
        confusion[str(t)][str(p)] += 1

    per_class: Dict[str, Dict[str, float]] = {}
    f1s: List[float] = []
    for lab in label_list:
        tp = sum(1 for t, p in pairs if t == lab and p == lab)
        fp = sum(1 for t, p in pairs if t != lab and p == lab)
        fn = sum(1 for t, p in pairs if t == lab and p != lab)
        support = sum(1 for t, _ in pairs if t == lab)
        f1 = _f1(tp, fp, fn)
        per_class[lab] = {
            "precision": (tp / (tp + fp)) if (tp + fp) else 0.0,
            "recall": (tp / (tp + fn)) if (tp + fn) else 0.0,
            "f1": f1,
            "support": float(support),
        }
        if support > 0:
            f1s.append(f1)

    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0

    # materialize confusion as plain dict
    conf_plain = {t: dict(preds) for t, preds in confusion.items()}

    return ClassificationMetrics(
        n=n,
        n_with_gold=n_gold,
        accuracy=accuracy,
        macro_f1=macro_f1,
        unknown_rate=unknown_rate,
        per_class=per_class,
        confusion=conf_plain,
    )


def dry_run_report(
    records: Sequence[Dict[str, Any]],
    predictions: Sequence[Dict[str, Any]],
) -> ClassificationMetrics:
    """Convenience: gold from records, pred task_type from classifier outputs."""
    golds = extract_gold_labels(records)
    preds = [str(p.get("task_type", "unknown")) for p in predictions]
    return evaluate_classification(golds, preds)
