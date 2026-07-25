#!/usr/bin/env python3
"""Print accuracy metrics for the text CatBoost task classifier."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA = ROOT / "catboost" / "prompt_radar_dataset.json"
MODEL = ROOT / "app" / "models" / "catboost_task_classifier.cbm"
TEXT_COL = "query_text"
TARGET = "category"
SEED = 42

CB_PARAMS = dict(
    iterations=800,
    learning_rate=0.05,
    depth=6,
    loss_function="MultiClass",
    eval_metric="TotalF1:average=Macro",
    random_seed=SEED,
    verbose=False,
    early_stopping_rounds=80,
    auto_class_weights="Balanced",
    task_type="CPU",
    tokenizers=[
        {"tokenizer_id": "Space", "delimiter": " ", "separator_type": "ByDelimiter"}
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


def load_df() -> pd.DataFrame:
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    df = pd.DataFrame(
        [
            {
                TEXT_COL: (r.get("query_text") or "").strip(),
                TARGET: (r.get("category") or "").strip(),
            }
            for r in rows
            if (r.get("query_text") or "").strip() and (r.get("category") or "").strip()
        ]
    )
    return df


def app_predict(texts: list[str], thr: float) -> tuple[list[str], list[float]]:
    from app.domain.taxonomy import Taxonomy
    from app.pipeline.classification.catboost_classifier import CatBoostClassifier as AppClf

    clf = AppClf(
        model_path=str(MODEL),
        taxonomy=Taxonomy(),
        config={"fallback_mode": "fail_fast", "confidence_threshold": thr},
    )
    preds: list[str] = []
    confs: list[float] = []
    for t in texts:
        r = clf.predict_with_confidence(t)
        preds.append(r["task_type"])
        confs.append(float(r["classification_confidence"]))
    return preds, confs


def main() -> int:
    df = load_df()
    labels = sorted(df[TARGET].unique())
    y_true = df[TARGET].tolist()
    texts = df[TEXT_COL].tolist()

    print(f"dataset: {DATA}")
    print(f"n={len(df)} classes={labels}")
    print("balance:", dict(df[TARGET].value_counts().sort_index()))
    print(f"model: {MODEL} exists={MODEL.is_file()}")

    # --- shipped model, full set ---
    y_pred0, confs0 = app_predict(texts, 0.0)
    acc0 = accuracy_score(y_true, y_pred0)
    f10 = f1_score(y_true, y_pred0, average="macro", zero_division=0)
    print()
    print("=" * 60)
    print(f"SHIPPED MODEL · FULL SET n={len(df)} · thr=0.00")
    print("=" * 60)
    print(f"accuracy:  {acc0:.4f}  ({sum(a == b for a, b in zip(y_true, y_pred0))}/{len(y_true)})")
    print(f"macro-F1:  {f10:.4f}")
    print(
        f"confidence: mean={np.mean(confs0):.3f} min={np.min(confs0):.3f} max={np.max(confs0):.3f}"
    )
    print(classification_report(y_true, y_pred0, digits=3, zero_division=0))
    cm = confusion_matrix(y_true, y_pred0, labels=labels)
    print("confusion (rows=true, cols=pred):")
    print(pd.DataFrame(cm, index=labels, columns=labels).to_string())

    for thr in (0.30, 0.50, 0.60):
        y_pred, _ = app_predict(texts, thr)
        unk = sum(1 for p in y_pred if p == "unknown")
        correct = sum(1 for a, b in zip(y_true, y_pred) if a == b)
        known = [(a, b) for a, b in zip(y_true, y_pred) if b != "unknown"]
        acc_known = (
            accuracy_score([a for a, _ in known], [b for _, b in known]) if known else float("nan")
        )
        print()
        print(f"--- shipped model · full set · thr={thr:.2f} ---")
        print(f"unknown:                 {unk}/{len(y_pred)} ({100 * unk / len(y_pred):.1f}%)")
        print(
            f"accuracy (unknown=miss): {correct / len(y_true):.4f}  ({correct}/{len(y_true)})"
        )
        print(f"accuracy on known only:  {acc_known:.4f}  (n={len(known)})")
        print(f"pred dist: {dict(Counter(y_pred))}")

    # --- honest holdout retrain ---
    print()
    print("=" * 60)
    print("HONEST HOLDOUT 80/20 (retrain, seed=42) — comparable to train script")
    print("=" * 60)
    X = df[[TEXT_COL]]
    y = df[TARGET]
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=SEED, stratify=y
    )
    train_pool = Pool(X_tr, y_tr, text_features=[TEXT_COL])
    test_pool = Pool(X_te, y_te, text_features=[TEXT_COL])
    m = CatBoostClassifier(**CB_PARAMS)
    m.fit(train_pool, eval_set=test_pool, use_best_model=True)
    yp = m.predict(test_pool)
    if isinstance(yp, np.ndarray) and yp.ndim > 1:
        yp = yp.ravel()
    yp = [str(x) for x in yp]
    print(f"holdout n={len(y_te)} best_iteration={m.get_best_iteration()}")
    print(f"accuracy: {accuracy_score(y_te, yp):.4f}")
    print(f"macro-F1: {f1_score(y_te, yp, average='macro', zero_division=0):.4f}")
    print(classification_report(y_te, yp, digits=3, zero_division=0))
    cm2 = confusion_matrix(y_te, yp, labels=labels)
    print(pd.DataFrame(cm2, index=labels, columns=labels).to_string())

    # --- 5-fold CV ---
    print()
    print("=" * 60)
    print("5-FOLD STRATIFIED CV (retrain each fold)")
    print("=" * 60)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    fold_acc: list[float] = []
    fold_f1: list[float] = []
    all_true: list[str] = []
    all_pred: list[str] = []
    for fold, (tr, te) in enumerate(skf.split(X, y), 1):
        Xtr, Xte = X.iloc[tr], X.iloc[te]
        ytr, yte = y.iloc[tr], y.iloc[te]
        m2 = CatBoostClassifier(**CB_PARAMS)
        m2.fit(
            Pool(Xtr, ytr, text_features=[TEXT_COL]),
            eval_set=Pool(Xte, yte, text_features=[TEXT_COL]),
            use_best_model=True,
        )
        pred = m2.predict(Pool(Xte, text_features=[TEXT_COL]))
        if isinstance(pred, np.ndarray) and pred.ndim > 1:
            pred = pred.ravel()
        pred = [str(x) for x in pred]
        a = accuracy_score(yte, pred)
        f = f1_score(yte, pred, average="macro", zero_division=0)
        fold_acc.append(a)
        fold_f1.append(f)
        all_true.extend(yte.tolist())
        all_pred.extend(pred)
        print(f"  fold {fold}: acc={a:.4f}  macro-F1={f:.4f}  n={len(yte)}")
    print(f"CV accuracy: mean={np.mean(fold_acc):.4f}  std={np.std(fold_acc):.4f}")
    print(f"CV macro-F1: mean={np.mean(fold_f1):.4f}  std={np.std(fold_f1):.4f}")
    print("pooled CV classification report:")
    print(classification_report(all_true, all_pred, digits=3, zero_division=0))

    meta = MODEL.with_suffix(".meta.json")
    if meta.is_file():
        print("shipped meta:", meta.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
