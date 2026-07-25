#!/usr/bin/env python3
"""Train CatBoost task-type classifier on query embeddings.

Pipeline:
  query_text → embedding provider (OpenRouter / Ollama / mock) → dense features
  → CatBoost MultiClass → .cbm (+ .meta.json)

Runtime must embed with the **same family/dim** used at train time
(default: qwen3-embedding 4b, dim 2560).

Example:
  cd ml_service
  # online (OpenRouter) — uses OPENROUTER_API_KEY from env / .env
  python catboost/train_catboost.py --provider openrouter

  # offline Ollama
  python catboost/train_catboost.py --provider ollama

  # reuse cached vectors (skip API)
  python catboost/train_catboost.py --cache catboost/embeddings_cache.npz
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sklearn.decomposition import PCA
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# load ml_service/.env if present (OPENROUTER_API_KEY etc.)
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

TEXT_COL = "query_text"
TARGET_COL = "category"
DEFAULT_DATA = ROOT / "catboost" / "prompt_radar_dataset.json"
DEFAULT_OUT = ROOT / "app" / "models" / "catboost_task_classifier.cbm"
DEFAULT_CACHE = ROOT / "catboost" / "embeddings_cache.npz"
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


def _text_fingerprint(texts: list[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def _mock_embed(texts: list[str], dim: int = 2560) -> np.ndarray:
    """Deterministic mock vectors (same idea as runtime MockEmbeddingAdapter)."""
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for i, t in enumerate(texts):
        digest = hashlib.sha256((t or "").encode("utf-8")).digest()
        rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))
        v = rng.standard_normal(dim).astype(np.float32)
        n = float(np.linalg.norm(v)) or 1.0
        out[i] = v / n
    return out


async def _embed_async(
    texts: list[str],
    *,
    provider: str,
    batch_size: int,
) -> np.ndarray:
    from app.core.config import EmbeddingsSettings
    from app.pipeline.embeddings.adapter import create_embedding_adapter

    provider = provider.lower().strip()
    if provider == "mock":
        return _mock_embed(texts)

    cfg = EmbeddingsSettings(
        mode="online" if provider == "openrouter" else "offline",
        provider=provider,
        batch_size=batch_size,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "qwen/qwen3-embedding-4b"),
        openrouter_url=os.getenv(
            "OPENROUTER_EMBEDDINGS_URL",
            "https://openrouter.ai/api/v1/embeddings",
        ),
        ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3-embedding:4b"),
        dim=int(os.getenv("EMBEDDINGS_DIM", "2560")),
        max_concurrency=int(os.getenv("EMBEDDINGS_MAX_CONCURRENCY", "4")),
        timeout_sec=float(os.getenv("EMBEDDINGS_TIMEOUT_SEC", "60")),
    )
    # force resolved provider
    cfg.provider = provider
    adapter = create_embedding_adapter(cfg)
    try:
        vectors = await adapter.embed(texts)
    finally:
        await adapter.close()
    return np.asarray(vectors, dtype=np.float32)


def load_or_compute_embeddings(
    texts: list[str],
    *,
    provider: str,
    cache_path: Optional[Path],
    batch_size: int,
    force_refresh: bool,
) -> np.ndarray:
    fp = _text_fingerprint(texts)
    if cache_path and cache_path.is_file() and not force_refresh:
        try:
            data = np.load(cache_path, allow_pickle=False)
            if str(data.get("fingerprint", "")) == fp and data["X"].shape[0] == len(texts):
                print(f"Loaded embeddings cache {cache_path} shape={data['X'].shape}")
                return np.asarray(data["X"], dtype=np.float32)
            print(f"Cache fingerprint mismatch or size change — recomputing ({cache_path})")
        except Exception as exc:  # noqa: BLE001
            print(f"Cache unreadable ({exc}) — recomputing")

    print(f"Embedding {len(texts)} texts via provider={provider} batch_size={batch_size}...")
    X = asyncio.run(
        _embed_async(texts, provider=provider, batch_size=batch_size)
    )
    print(f"Embeddings shape: {X.shape}")

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache_path, X=X, fingerprint=np.asarray(fp))
        print(f"Cache saved → {cache_path}")
    return X


def train_model(
    X_train: np.ndarray,
    y_train: pd.Series,
    X_test: np.ndarray,
    y_test: pd.Series,
    *,
    iterations: int,
    learning_rate: float,
    depth: int,
    seed: int,
    task_type: str,
) -> CatBoostClassifier:
    train_pool = Pool(X_train, y_train)
    test_pool = Pool(X_test, y_test)
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
    )
    model.fit(train_pool, eval_set=test_pool, use_best_model=True)
    return model


def evaluate(
    model: CatBoostClassifier,
    X_test: np.ndarray,
    y_test: pd.Series,
    out_dir: Path,
) -> float:
    y_pred = model.predict(X_test)
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
        plt.title("Confusion Matrix (embedding CatBoost)")
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


def demo_predict(
    model: CatBoostClassifier,
    provider: str,
    *,
    pca: Optional[PCA] = None,
) -> None:
    examples = [
        "Сформируй еженедельный отчет по проекту из Jira и отправь команде",
        "Напиши unit-тесты для функции parse_csv на Python",
        "Найди в Confluence инструкцию по подключению VPN",
        "Объясни, как работает OAuth2 в нашем SSO",
        "Построй сводную таблицу продаж по регионам за Q2",
    ]
    print("\n" + "=" * 60)
    print("Demo predictions (embed → CatBoost):")
    try:
        X = asyncio.run(_embed_async(examples, provider=provider, batch_size=8))
        if pca is not None:
            X = pca.transform(X).astype(np.float32)
    except Exception as exc:  # noqa: BLE001
        print(f"(demo skipped: {exc})")
        return
    preds = model.predict(X)
    probs = model.predict_proba(X)
    for i, text in enumerate(examples):
        label = preds[i]
        if isinstance(label, (list, np.ndarray)):
            label = label[0]
        top = sorted(zip(model.classes_, probs[i]), key=lambda x: -x[1])[:3]
        tops = ", ".join(f"{c}={p:.3f}" for c, p in top)
        print(f"  [{str(label):20s}] {text[:70]}")
        print(f"    top: {tops}")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train CatBoost on query embeddings (text → vector → classify)"
    )
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--provider",
        choices=("openrouter", "ollama", "mock"),
        default=os.getenv("EMBEDDINGS_PROVIDER")
        or ("openrouter" if os.getenv("OPENROUTER_API_KEY") else "ollama"),
        help="Embedding provider used to build features",
    )
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--refresh-cache", action="store_true")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--test-size", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=RANDOM_SEED)
    p.add_argument("--iterations", type=int, default=500)
    p.add_argument("--learning-rate", type=float, default=0.05)
    p.add_argument("--depth", type=int, default=6)
    p.add_argument(
        "--pca-dim",
        type=int,
        default=256,
        help="Project embeddings to this dim before CatBoost (0 = raw). "
        "Default 256 avoids OOM on high-dim models (e.g. 2560).",
    )
    p.add_argument("--task-type", choices=("CPU", "GPU"), default="CPU")
    p.add_argument("--skip-demo", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    data_path = args.data if args.data.is_absolute() else (ROOT / args.data)
    if not data_path.is_file():
        alt = Path(args.data)
        if alt.is_file():
            data_path = alt
        else:
            print(f"Dataset not found: {args.data}", file=sys.stderr)
            return 1

    out_path = args.out if args.out.is_absolute() else (ROOT / args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cache_path: Optional[Path] = None
    if not args.no_cache:
        cache_path = args.cache if args.cache.is_absolute() else (ROOT / args.cache)

    df = load_dataset(data_path)
    texts = df[TEXT_COL].tolist()
    y = df[TARGET_COL]

    X = load_or_compute_embeddings(
        texts,
        provider=args.provider,
        cache_path=cache_path,
        batch_size=args.batch_size,
        force_refresh=args.refresh_cache,
    )
    if X.shape[0] != len(df):
        print("Embedding count mismatch", file=sys.stderr)
        return 1

    raw_dim = int(X.shape[1])
    pca = None
    feature_dim = raw_dim
    if args.pca_dim and args.pca_dim > 0 and args.pca_dim < raw_dim:
        n_comp = min(args.pca_dim, X.shape[0] - 1, raw_dim)
        print(f"PCA {raw_dim} → {n_comp} (fit on full set for stable runtime transform)")
        pca = PCA(n_components=n_comp, random_state=args.seed)
        X = pca.fit_transform(X).astype(np.float32)
        feature_dim = n_comp
        explained = float(np.sum(pca.explained_variance_ratio_))
        print(f"PCA explained variance: {explained:.3f}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.seed, stratify=y
    )

    print(
        f"Training embedding CatBoost: iterations={args.iterations} "
        f"lr={args.learning_rate} depth={args.depth} feature_dim={feature_dim} "
        f"raw_dim={raw_dim} task_type={args.task_type} provider={args.provider}"
    )
    model = train_model(
        X_train,
        y_train,
        X_test,
        y_test,
        iterations=args.iterations,
        learning_rate=args.learning_rate,
        depth=args.depth,
        seed=args.seed,
        task_type=args.task_type,
    )

    acc = evaluate(model, X_test, y_test, out_path.parent)
    model.save_model(str(out_path))
    print(f"\nModel saved → {out_path.resolve()}")
    print(f"Classes: {list(model.classes_)}")
    print(f"Holdout accuracy: {acc:.4f}")

    if pca is not None:
        pca_path = out_path.with_suffix(".pca.npz")
        np.savez_compressed(
            pca_path,
            mean=pca.mean_.astype(np.float32),
            components=pca.components_.astype(np.float32),
        )
        print(f"PCA transform saved → {pca_path}")

    if not args.skip_demo:
        demo_predict(model, args.provider, pca=pca)

    meta = {
        "input": "embedding",
        "embeddings": True,
        "embedding_provider": args.provider,
        "embedding_dim": raw_dim,
        "feature_dim": feature_dim,
        "pca_dim": int(feature_dim) if pca is not None else None,
        "classes": [str(c) for c in model.classes_],
        "holdout_accuracy": acc,
        "n_samples": int(len(df)),
        "text_feature": None,
    }
    meta_path = out_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Meta saved → {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
