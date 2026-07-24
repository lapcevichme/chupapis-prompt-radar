import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from catboost import CatBoostClassifier, Pool
import requests
from tqdm import tqdm
import seaborn as sns
import matplotlib.pyplot as plt

# ====================== НАСТРОЙКИ ======================
DATA_PATH = "catboost\prompt_radar_dataset.json"                  # путь к новому JSON
MODEL_NAME = "qwen3-embedding:4b"           # модель эмбеддингов в Ollama
OLLAMA_URL = "http://localhost:11434/api/embeddings"
TARGET_COLUMN = "category"                  # что предсказываем
TEST_SIZE = 0.2
RANDOM_SEED = 42
# =======================================================


def get_embedding(text: str, model: str = MODEL_NAME) -> list[float]:
    """Получает эмбеддинг одного текста через Ollama"""
    payload = {
        "model": model,
        "prompt": text
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()["embedding"]


def load_and_embed_data(path: str) -> tuple[np.ndarray, pd.Series, list]:
    """Загружает JSON нового формата и векторизует все query_text"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    texts = [item["query_text"] for item in data]
    targets = [item[TARGET_COLUMN] for item in data]
    request_ids = [item.get("request_id", "") for item in data]

    print(f"Векторизация {len(texts)} запросов через {MODEL_NAME}...")
    embeddings = []
    for text in tqdm(texts, desc="Embedding"):
        emb = get_embedding(text)
        embeddings.append(emb)

    X = np.array(embeddings, dtype=np.float32)
    y = pd.Series(targets)

    print(f"Размерность эмбеддингов: {X.shape}")
    print(f"Распределение классов:\n{y.value_counts()}\n")
    return X, y, request_ids


def train_catboost(X: np.ndarray, y: pd.Series):
    """Обучает CatBoost и возвращает модель + отчёт"""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=y
    )

    train_pool = Pool(X_train, y_train)
    test_pool = Pool(X_test, y_test)

    model = CatBoostClassifier(
        iterations=700,
        learning_rate=0.04,
        depth=6,
        loss_function="MultiClass",
        eval_metric="Accuracy",
        random_seed=RANDOM_SEED,
        verbose=100,
        early_stopping_rounds=60,
        auto_class_weights="Balanced",   # полезно при небольшом дисбалансе
        task_type="GPU",                 # поменяй на "GPU" при наличии
    )

    model.fit(train_pool, eval_set=test_pool, use_best_model=True)

    # Оценка
    y_pred = model.predict(X_test)
    print("\n" + "="*60)
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, digits=3))

    # Confusion Matrix
    cm = confusion_matrix(y_test, y_pred, labels=model.classes_)
    plt.figure(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=model.classes_, yticklabels=model.classes_)
    plt.title("Confusion Matrix")
    plt.ylabel("True")
    plt.xlabel("Predicted")
    plt.tight_layout()
    plt.savefig("confusion_matrix.png", dpi=150)
    print("\nConfusion matrix сохранена в confusion_matrix.png")

    return model


def main():
    # 1. Векторизация
    X, y, request_ids = load_and_embed_data(DATA_PATH)

    # 2. Обучение
    model = train_catboost(X, y)

    # 3. Сохранение модели
    model_path = Path("catboost_embedding_model.cbm")
    model.save_model(model_path)
    print(f"\nМодель сохранена: {model_path.resolve()}")

    # 4. Пример инференса
    example_query = "Сформируй еженедельный отчет по проекту из Jira и отправь команде"
    emb = np.array([get_embedding(example_query)], dtype=np.float32)
    pred = model.predict(emb)[0]
    proba = model.predict_proba(emb)[0]

    print("\n" + "="*60)
    print("Пример предсказания:")
    print(f"Запрос: {example_query}")
    print(f"Предсказанный класс: {pred}")
    print("Вероятности:")
    for cls, p in sorted(zip(model.classes_, proba), key=lambda x: -x[1]):
        print(f"  {cls:20s}: {p:.3f}")


if __name__ == "__main__":
    main()