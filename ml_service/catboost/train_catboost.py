#!/usr/bin/env python3
"""Train CatBoost task-type classifier on raw query text (no embeddings).

Uses CatBoost text_features (BoW / token dictionaries) — better for small
datasets (~hundreds of rows) than high-dim embedding + CatBoost.

Example:
  cd ml_service
  python catboost/train_catboost.py
  python catboost/train_catboost.py --data catboost/prompt_radar_dataset.json \\
      --out app/models/catboost_task_classifier.cbm
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
TEXT_COL = "query_text"
TARGET_COL = "category"
DEFAULT_DATA = ROOT / "catboost" / "prompt_radar_dataset.json"
DEFAULT_OUT = ROOT / "app" / "models" / "catboost_task_classifier.cbm"
RANDOM_SEED = 42


def load_dataset(path: Path) -> pd.DataFrame:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or not data:
        raise ValueError(f"Dataset must be a non-empty JSON list: {path}")

    rows: list[dict[str, Any]] = []
    for item in data:
        text = (item.get("query_text") or item.get("text") or "").strip()
        label = (item.get(TARGET_COL) or item.get("gold_category") or "").strip()
        if not text or not label:
            continue
        rows.append({TEXT_COL: text, TARGET_COL: label})

    if not rows:
        raise ValueError(f"No usable rows with query_text + category in {path}")

    df = pd.DataFrame(rows)
    print(f"Loaded {len(df)} rows from {path}")
    print(f"Class distribution:\n{df[TARGET_COL].value_counts()}\n")
    return df


def make_pools(
    df: pd.DataFrame, test_size: float, seed: int
) -> tuple[Pool, Pool, pd.Series, pd.Series]:
    X = df[[TEXT_COL]]
    y = df[TARGET_COL]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y
    )
    train_pool = Pool(X_train, y_train, text_features=[TEXT_COL])
    test_pool = Pool(X_test, y_test, text_features=[TEXT_COL])
    return train_pool, test_pool, y_train, y_test


def train_model(
    train_pool: Pool,
    test_pool: Pool,
    *,
    iterations: int,
    learning_rate: float,
    depth: int,
    seed: int,
    task_type: str,
) -> CatBoostClassifier:
    # Text features: CPU is the reliable path; GPU text support is limited.
    # Provide either text_processing OR tokenizers+dictionaries+feature_calcers (not both).
    model = CatBoostClassifier(
        iterations=iterations,
        learning_rate=learning_rate,
        depth=depth,
        loss_function="MultiClass",
        eval_metric="TotalF1:average=Macro",
        random_seed=seed,
        verbose=50,
        early_stopping_rounds=80,
        auto_class_weights="Balanced",
        task_type=task_type,
        tokenizers=[
            {
                "tokenizer_id": "Space",
                "delimiter": " ",
                "separator_type": "ByDelimiter",
            }
        ],
        dictionaries=[
            {
                "dictionary_id": "Word",
                "max_dictionary_size": "50000",
                "occurrence_lower_bound": "2",
                "gram_order": "1",
            }
        ],
        feature_calcers=["BoW:top_tokens_count=5000", "NaiveBayes", "BM25"],
    )
    model.fit(train_pool, eval_set=test_pool, use_best_model=True)
    return model


def evaluate(model: CatBoostClassifier, test_pool: Pool, y_test: pd.Series, out_dir: Path) -> float:
    y_pred = model.predict(test_pool)
    # CatBoost MultiClass returns column vector of labels
    if isinstance(y_pred, np.ndarray) and y_pred.ndim > 1:
        y_pred = y_pred.ravel()
    y_pred = pd.Series([str(p) for p in y_pred], index=y_test.index)

    acc = float(accuracy_score(y_test, y_pred))
    print("\n" + "=" * 60)
    print(f"Accuracy: {acc:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, digits=3, zero_division=0))

    labels = list(model.classes_)
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    print("Confusion matrix (rows=true, cols=pred):")
    print(pd.DataFrame(cm, index=labels, columns=labels).to_string())

    try:
        import matplotlib.pyplot as plt
        import seaborn as sns

        plt.figure(figsize=(10, 8))
        sns.heatmap(
            cm,
            annot=True,
            fmt="d",
            cmap="Blues",
            xticklabels=labels,
            yticklabels=labels,
        )
        plt.title("Confusion Matrix (text CatBoost)")
        plt.ylabel("True")
        plt.xlabel("Predicted")
        plt.tight_layout()
        cm_path = out_dir / "confusion_matrix.png"
        plt.savefig(cm_path, dpi=150)
        plt.close()
        print(f"\nConfusion matrix saved → {cm_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"(plot skipped: {exc})")

    return acc


def demo_predict(model: CatBoostClassifier) -> None:
    examples = [
        "Сформируй еженедельный отчет по проекту из Jira и отправь команде",
        "Напиши unit-тесты для функции parse_csv на Python",
        "Найди в Confluence инструкцию по подключению VPN",
        "Объясни, как работает OAuth2 в нашем SSO",
        "Построй сводную таблицу продаж по регионам за Q2",
    ]
    print("\n" + "=" * 60)
    print("Demo predictions:")
    for text in examples:
        pool = Pool(pd.DataFrame({TEXT_COL: [text]}), text_features=[TEXT_COL])
        pred = model.predict(pool)
        label = str(pred[0][0] if isinstance(pred[0], (list, np.ndarray)) else pred[0])
        proba = model.predict_proba(pool)[0]
        top = sorted(zip(model.classes_, proba), key=lambda x: -x[1])[:3]
        tops = ", ".join(f"{c}={p:.3f}" for c, p in top)
        print(f"  [{label:20s}] {text[:70]}")
        print(f"    top: {tops}")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train text CatBoost classifier (no embeddings)")
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--test-size", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=RANDOM_SEED)
    p.add_argument("--iterations", type=int, default=800)
    p.add_argument("--learning-rate", type=float, default=0.05)
    p.add_argument("--depth", type=int, default=6)
    p.add_argument(
        "--task-type",
        choices=("CPU", "GPU"),
        default="CPU",
        help="Text features: prefer CPU",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    data_path = args.data if args.data.is_absolute() else (ROOT / args.data)
    if not data_path.is_file():
        # also try relative to CWD / script dir
        alt = Path(args.data)
        if alt.is_file():
            data_path = alt
        else:
            print(f"Dataset not found: {args.data}", file=sys.stderr)
            return 1

    out_path = args.out if args.out.is_absolute() else (ROOT / args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = load_dataset(data_path)
    train_pool, test_pool, _y_train, y_test = make_pools(df, args.test_size, args.seed)

    print(
        f"Training text CatBoost: iterations={args.iterations} lr={args.learning_rate} "
        f"depth={args.depth} task_type={args.task_type}"
    )
    model = train_model(
        train_pool,
        test_pool,
        iterations=args.iterations,
        learning_rate=args.learning_rate,
        depth=args.depth,
        seed=args.seed,
        task_type=args.task_type,
    )

    acc = evaluate(model, test_pool, y_test, out_path.parent)
    model.save_model(str(out_path))
    print(f"\nModel saved → {out_path.resolve()}")
    print(f"Classes: {list(model.classes_)}")
    print(f"Holdout accuracy: {acc:.4f}")

    demo_predict(model)

    # small sidecar meta for runtime
    meta = {
        "input": "text",
        "text_feature": TEXT_COL,
        "classes": [str(c) for c in model.classes_],
        "holdout_accuracy": acc,
        "n_samples": int(len(df)),
        "embeddings": False,
    }
    meta_path = out_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Meta saved → {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
