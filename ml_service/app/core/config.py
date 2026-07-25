"""ML service configuration: config.yaml + env overrides (ТЗ §4)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _dig(data: Mapping[str, Any], *path: str, default: Any = None) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


@dataclass
class ServerSettings:
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class StoreSettings:
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "prompt_radar_vectors"
    meta_db_url: str = "sqlite:////data/ml/meta.db"


@dataclass
class EmbeddingsSettings:
    """Embeddings: mode offline (Ollama) | online (OpenRouter) | mock (tests).

    Same model family in both modes:
      offline → qwen3-embedding:4b (Ollama)
      online  → qwen/qwen3-embedding-4b (OpenRouter)
    """

    mode: str = "offline"  # offline | online | mock
    # resolved transport (kept for back-compat with EMBEDDINGS_PROVIDER)
    provider: str = "ollama"  # mock | ollama | openrouter
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3-embedding:4b"
    openrouter_url: str = "https://openrouter.ai/api/v1/embeddings"
    openrouter_model: str = "qwen/qwen3-embedding-4b"
    openrouter_api_key: str = ""
    batch_size: int = 32
    timeout_sec: float = 30.0
    max_retries: int = 2
    dim: int = 384  # used by mock; real dim comes from provider response
    max_concurrency: int = 4
    cache_enabled: bool = False
    cache_max_size: int = 10_000

    def resolve_provider(self) -> str:
        p = (self.provider or "").strip().lower()
        # explicit mock always wins (unit tests)
        if p == "mock":
            return "mock"
        m = (self.mode or "").strip().lower()
        if m in ("mock", "test"):
            return "mock"
        if m in ("online", "cloud", "openrouter"):
            return "openrouter"
        if m in ("offline", "local", "ollama"):
            return "ollama"
        # fall back to explicit provider
        return p if p in {"mock", "ollama", "openrouter"} else "ollama"


@dataclass
class LLMSettings:
    """Chat LLM for summarization (and classifier llm-fallback).

    Same model family:
      offline → Ollama chat gemma4:26b-a4b-it (same family as OpenRouter)
      online  → OpenRouter google/gemma-4-26b-a4b-it
    """

    mode: str = "offline"  # offline | online
    provider: str = "ollama"  # ollama | openrouter (resolved from mode)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:26b-a4b-it"
    openrouter_url: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_model: str = "google/gemma-4-26b-a4b-it"
    openrouter_api_key: str = ""
    timeout_sec: float = 120.0
    max_retries: int = 2

    def resolve_provider(self) -> str:
        m = (self.mode or "").strip().lower()
        if m in ("online", "cloud", "openrouter"):
            return "openrouter"
        if m in ("offline", "local", "ollama"):
            return "ollama"
        p = (self.provider or "ollama").lower()
        return p if p in {"ollama", "openrouter"} else "ollama"


@dataclass
class ClassifierSettings:
    provider: str = "catboost"
    # Docker default; local resolve also scans app/models/ via classifier code when env set.
    model_path: str = "app/models/catboost_task_classifier.cbm"
    confidence_threshold: float = 0.60
    fallback_mode: str = "llm"  # fail_fast | llm | embedding_centroid
    taxonomy_version: str = "v1"


@dataclass
class IngestSettings:
    batch_max_size: int = 200
    worker_concurrency: int = 8
    embeddings_batch_size: int = 32


@dataclass
class OnlineClusteringSettings:
    similarity_threshold: float = 0.85
    recompute_centroid: bool = True


@dataclass
class UmapSettings:
    n_neighbors: int = 15
    n_components: int = 10
    min_dist: float = 0.0
    metric: str = "cosine"
    random_state: int = 42


@dataclass
class HdbscanSettings:
    min_cluster_size: int = 5
    min_samples: int = 3
    metric: str = "euclidean"
    cluster_selection_method: str = "eom"


@dataclass
class RecomputeSettings:
    interval_hours: int = 2
    umap: UmapSettings = field(default_factory=UmapSettings)
    hdbscan: HdbscanSettings = field(default_factory=HdbscanSettings)


@dataclass
class SummarizationSettings:
    representative_examples_count: int = 10
    scenario_name_max_words: int = 4
    max_llm_retries: int = 2


@dataclass
class AggregationDefaults:
    top_tasks_limit: int = 7
    top_scenarios_limit: int = 9
    trend_threshold_percent: float = 10.0


@dataclass
class LongTextSettings:
    max_direct_tokens: int = 8000
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64


@dataclass
class Settings:
    server: ServerSettings = field(default_factory=ServerSettings)
    store: StoreSettings = field(default_factory=StoreSettings)
    embeddings: EmbeddingsSettings = field(default_factory=EmbeddingsSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    classifier: ClassifierSettings = field(default_factory=ClassifierSettings)
    ingest: IngestSettings = field(default_factory=IngestSettings)
    online_clustering: OnlineClusteringSettings = field(default_factory=OnlineClusteringSettings)
    recompute: RecomputeSettings = field(default_factory=RecomputeSettings)
    summarization: SummarizationSettings = field(default_factory=SummarizationSettings)
    aggregation_defaults: AggregationDefaults = field(default_factory=AggregationDefaults)
    long_text: LongTextSettings = field(default_factory=LongTextSettings)
    service_token: str = ""
    log_level: str = "INFO"
    config_path: Optional[str] = None
    config_loaded: bool = False
    config_errors: list[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        return not self.config_errors

    def pipeline_metadata_params(self) -> dict[str, Any]:
        """Parameters that affect results — for /statistics pipeline_metadata."""
        emb_p = self.embeddings.resolve_provider()
        llm_p = self.llm.resolve_provider()
        return {
            "embeddings_mode": self.embeddings.mode,
            "embeddings_provider": emb_p,
            "embedding_provider": emb_p,
            "embedding_model": (
                self.embeddings.ollama_model
                if emb_p == "ollama"
                else self.embeddings.openrouter_model
                if emb_p == "openrouter"
                else "mock"
            ),
            "llm_mode": self.llm.mode,
            "llm_provider": llm_p,
            "llm_model": (
                self.llm.ollama_model if llm_p == "ollama" else self.llm.openrouter_model
            ),
            "classifier_provider": self.classifier.provider,
            "classifier_fallback_mode": self.classifier.fallback_mode,
            "classifier_confidence_threshold": self.classifier.confidence_threshold,
            "taxonomy_version": self.classifier.taxonomy_version,
            "online_similarity_threshold": self.online_clustering.similarity_threshold,
            "online_recompute_centroid": self.online_clustering.recompute_centroid,
            "umap": {
                "n_neighbors": self.recompute.umap.n_neighbors,
                "n_components": self.recompute.umap.n_components,
                "min_dist": self.recompute.umap.min_dist,
                "metric": self.recompute.umap.metric,
                "random_state": self.recompute.umap.random_state,
            },
            "hdbscan": {
                "min_cluster_size": self.recompute.hdbscan.min_cluster_size,
                "min_samples": self.recompute.hdbscan.min_samples,
                "metric": self.recompute.hdbscan.metric,
                "cluster_selection_method": self.recompute.hdbscan.cluster_selection_method,
            },
            "summarization": {
                "representative_examples_count": self.summarization.representative_examples_count,
                "scenario_name_max_words": self.summarization.scenario_name_max_words,
            },
        }


def _default_config_candidates() -> list[Path]:
    """Search order for config.yaml relative to package / CWD."""
    here = Path(__file__).resolve()
    # app/core/config.py → ml_service/
    ml_service_root = here.parents[2]
    return [
        ml_service_root / "config.yaml",
        Path.cwd() / "config.yaml",
        Path.cwd() / "ml_service" / "config.yaml",
    ]


def resolve_config_path(explicit: Optional[str] = None) -> Optional[Path]:
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    env_path = os.getenv("ML_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
    for candidate in _default_config_candidates():
        if candidate.is_file():
            return candidate
    return None


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyYAML is required to load config.yaml") from exc
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config root must be a mapping, got {type(data).__name__}")
    return data


def _embeddings_from_yaml(raw: Mapping[str, Any]) -> EmbeddingsSettings:
    emb = _dig(raw, "models", "embeddings") or raw.get("embeddings") or {}
    ollama = emb.get("ollama") or {}
    openrouter = emb.get("openrouter") or {}
    ollama_url = _as_str(ollama.get("url"), "http://ollama:11434/api/embed")
    # store base URL without /api/embed for adapter compatibility when needed
    if ollama_url.endswith("/api/embed"):
        ollama_base = ollama_url[: -len("/api/embed")] or "http://ollama:11434"
    else:
        ollama_base = ollama_url
    mode = _as_str(emb.get("mode"), "")
    provider = _as_str(emb.get("provider"), "ollama")
    if not mode:
        # derive mode from legacy provider field
        if provider == "openrouter":
            mode = "online"
        elif provider == "mock":
            mode = "mock"
        else:
            mode = "offline"
    es = EmbeddingsSettings(
        mode=mode,
        provider=provider,
        ollama_url=ollama_base,
        ollama_model=_as_str(ollama.get("model_name"), "qwen3-embedding:4b"),
        openrouter_url=_as_str(
            openrouter.get("url"), "https://openrouter.ai/api/v1/embeddings"
        ),
        openrouter_model=_as_str(openrouter.get("model_name"), "qwen/qwen3-embedding-4b"),
        batch_size=_as_int(_dig(raw, "ingest", "embeddings_batch_size"), 32),
        max_concurrency=_as_int(emb.get("max_concurrency"), 4),
        cache_enabled=_as_bool(emb.get("cache_enabled"), False),
        cache_max_size=_as_int(emb.get("cache_max_size"), 10_000),
    )
    es.provider = es.resolve_provider()
    return es


def _llm_from_yaml(raw: Mapping[str, Any]) -> LLMSettings:
    llm = _dig(raw, "models", "llm") or raw.get("llm") or {}
    openrouter = llm.get("openrouter") or {}
    ollama = llm.get("ollama") or {}
    mode = _as_str(llm.get("mode"), "")
    provider = _as_str(llm.get("provider"), "ollama")
    if not mode:
        mode = "online" if provider == "openrouter" else "offline"
    ollama_url = _as_str(ollama.get("url"), "http://127.0.0.1:11434")
    if ollama_url.endswith("/api/chat"):
        ollama_url = ollama_url[: -len("/api/chat")]
    ls = LLMSettings(
        mode=mode,
        provider=provider,
        ollama_url=ollama_url,
        ollama_model=_as_str(ollama.get("model_name"), "gemma4:26b-a4b-it"),
        openrouter_url=_as_str(
            openrouter.get("url"), "https://openrouter.ai/api/v1/chat/completions"
        ),
        openrouter_model=_as_str(
            openrouter.get("model_name"), "google/gemma-4-26b-a4b-it"
        ),
    )
    ls.provider = ls.resolve_provider()
    return ls


def _classifier_from_yaml(raw: Mapping[str, Any]) -> ClassifierSettings:
    clf = _dig(raw, "models", "classifier") or raw.get("classifier") or {}
    return ClassifierSettings(
        provider=_as_str(clf.get("provider"), "catboost"),
        model_path=_as_str(clf.get("model_path"), "/app/models/catboost_task_classifier.cbm"),
        confidence_threshold=_as_float(clf.get("confidence_threshold"), 0.60),
        fallback_mode=_as_str(clf.get("fallback_mode"), "llm"),
        taxonomy_version=_as_str(clf.get("taxonomy_version"), "v1"),
    )


def _settings_from_yaml(raw: Mapping[str, Any], path: Path) -> Settings:
    server = raw.get("server") or {}
    store = raw.get("store") or {}
    ingest = raw.get("ingest") or {}
    online = raw.get("online_clustering") or {}
    recompute = raw.get("recompute") or {}
    umap = recompute.get("umap") or {}
    hdbscan = recompute.get("hdbscan") or {}
    summarization = raw.get("summarization") or {}
    agg = raw.get("aggregation_defaults") or {}
    long_text = raw.get("long_text") or {}

    return Settings(
        server=ServerSettings(
            host=_as_str(server.get("host"), "0.0.0.0"),
            port=_as_int(server.get("port"), 8000),
        ),
        store=StoreSettings(
            qdrant_url=_as_str(store.get("qdrant_url"), "http://qdrant:6333"),
            qdrant_collection=_as_str(store.get("qdrant_collection"), "prompt_radar_vectors"),
            meta_db_url=_as_str(store.get("meta_db_url"), "sqlite:////data/ml/meta.db"),
        ),
        embeddings=_embeddings_from_yaml(raw),
        llm=_llm_from_yaml(raw),
        classifier=_classifier_from_yaml(raw),
        ingest=IngestSettings(
            batch_max_size=_as_int(ingest.get("batch_max_size"), 200),
            worker_concurrency=_as_int(ingest.get("worker_concurrency"), 8),
            embeddings_batch_size=_as_int(ingest.get("embeddings_batch_size"), 32),
        ),
        online_clustering=OnlineClusteringSettings(
            similarity_threshold=_as_float(online.get("similarity_threshold"), 0.85),
            recompute_centroid=_as_bool(online.get("recompute_centroid"), True),
        ),
        recompute=RecomputeSettings(
            interval_hours=_as_int(recompute.get("interval_hours"), 2),
            umap=UmapSettings(
                n_neighbors=_as_int(umap.get("n_neighbors"), 15),
                n_components=_as_int(umap.get("n_components"), 10),
                min_dist=_as_float(umap.get("min_dist"), 0.0),
                metric=_as_str(umap.get("metric"), "cosine"),
                random_state=_as_int(umap.get("random_state"), 42),
            ),
            hdbscan=HdbscanSettings(
                min_cluster_size=_as_int(hdbscan.get("min_cluster_size"), 5),
                min_samples=_as_int(hdbscan.get("min_samples"), 3),
                metric=_as_str(hdbscan.get("metric"), "euclidean"),
                cluster_selection_method=_as_str(
                    hdbscan.get("cluster_selection_method"), "eom"
                ),
            ),
        ),
        summarization=SummarizationSettings(
            representative_examples_count=_as_int(
                summarization.get("representative_examples_count"), 10
            ),
            scenario_name_max_words=_as_int(summarization.get("scenario_name_max_words"), 4),
            max_llm_retries=_as_int(summarization.get("max_llm_retries"), 2),
        ),
        aggregation_defaults=AggregationDefaults(
            top_tasks_limit=_as_int(agg.get("top_tasks_limit"), 7),
            top_scenarios_limit=_as_int(agg.get("top_scenarios_limit"), 9),
            trend_threshold_percent=_as_float(agg.get("trend_threshold_percent"), 10.0),
        ),
        long_text=LongTextSettings(
            max_direct_tokens=_as_int(long_text.get("max_direct_tokens"), 8000),
            chunk_size_tokens=_as_int(long_text.get("chunk_size_tokens"), 512),
            chunk_overlap_tokens=_as_int(long_text.get("chunk_overlap_tokens"), 64),
        ),
        config_path=str(path),
        config_loaded=True,
    )


def _apply_env_overrides(s: Settings) -> Settings:
    """Apply environment variable overrides (secrets + ops knobs)."""
    # Store
    if v := os.getenv("QDRANT_URL"):
        s.store.qdrant_url = v
    if v := os.getenv("QDRANT_COLLECTION"):
        s.store.qdrant_collection = v
    if v := os.getenv("ML_META_DB_URL"):
        s.store.meta_db_url = v

    # Global mode shortcut (sets both embeddings + llm unless overridden)
    global_mode = (os.getenv("ML_MODE") or "").strip().lower()

    # Embeddings mode: offline=Ollama, online=OpenRouter, mock=tests
    if v := os.getenv("EMBEDDINGS_MODE"):
        s.embeddings.mode = v.strip().lower()
    elif global_mode in ("offline", "online", "mock"):
        s.embeddings.mode = global_mode
    if v := os.getenv("EMBEDDINGS_PROVIDER"):
        # legacy: still works; also maps to mode if EMBEDDINGS_MODE unset
        s.embeddings.provider = v.strip().lower()
        if not os.getenv("EMBEDDINGS_MODE") and not global_mode:
            if v.lower() == "openrouter":
                s.embeddings.mode = "online"
            elif v.lower() == "mock":
                s.embeddings.mode = "mock"
            elif v.lower() == "ollama":
                s.embeddings.mode = "offline"
    if v := os.getenv("OLLAMA_URL"):
        s.embeddings.ollama_url = v.rstrip("/")
        if not os.getenv("OLLAMA_LLM_URL"):
            s.llm.ollama_url = v.rstrip("/")
    if v := os.getenv("OLLAMA_MODEL"):
        s.embeddings.ollama_model = v
    if v := os.getenv("OPENROUTER_EMBEDDINGS_URL"):
        s.embeddings.openrouter_url = v
    if v := os.getenv("OPENROUTER_MODEL"):
        s.embeddings.openrouter_model = v
    if v := os.getenv("OPENROUTER_API_KEY"):
        s.embeddings.openrouter_api_key = v
        s.llm.openrouter_api_key = v
    if v := os.getenv("EMBEDDINGS_BATCH_SIZE"):
        s.embeddings.batch_size = _as_int(v, s.embeddings.batch_size)
        s.ingest.embeddings_batch_size = s.embeddings.batch_size
    if v := os.getenv("EMBEDDINGS_TIMEOUT_SEC"):
        s.embeddings.timeout_sec = _as_float(v, s.embeddings.timeout_sec)
    if v := os.getenv("EMBEDDINGS_MAX_RETRIES"):
        s.embeddings.max_retries = _as_int(v, s.embeddings.max_retries)
    if v := os.getenv("EMBEDDINGS_DIM"):
        s.embeddings.dim = _as_int(v, s.embeddings.dim)
    if v := os.getenv("EMBEDDINGS_MAX_CONCURRENCY"):
        s.embeddings.max_concurrency = _as_int(v, s.embeddings.max_concurrency)
    if v := os.getenv("EMBEDDINGS_CACHE_ENABLED"):
        s.embeddings.cache_enabled = _as_bool(v, s.embeddings.cache_enabled)
    if v := os.getenv("EMBEDDINGS_CACHE_MAX_SIZE"):
        s.embeddings.cache_max_size = _as_int(v, s.embeddings.cache_max_size)
    # resolve provider from mode after overrides
    s.embeddings.provider = s.embeddings.resolve_provider()

    # LLM mode: offline=Ollama chat, online=OpenRouter chat
    if v := os.getenv("LLM_MODE"):
        s.llm.mode = v.strip().lower()
    elif global_mode in ("offline", "online"):
        s.llm.mode = global_mode
    if v := os.getenv("LLM_PROVIDER"):
        s.llm.provider = v.strip().lower()
        if not os.getenv("LLM_MODE") and not global_mode:
            s.llm.mode = "online" if v.lower() == "openrouter" else "offline"
    if v := os.getenv("OLLAMA_LLM_URL"):
        s.llm.ollama_url = v.rstrip("/")
    if v := os.getenv("OLLAMA_LLM_MODEL"):
        s.llm.ollama_model = v
    if v := os.getenv("OPENROUTER_CHAT_URL"):
        s.llm.openrouter_url = v
    if v := os.getenv("OPENROUTER_CHAT_MODEL"):
        s.llm.openrouter_model = v
    s.llm.provider = s.llm.resolve_provider()

    # Classifier
    if v := os.getenv("CLASSIFIER_MODEL_PATH"):
        s.classifier.model_path = v
    if v := os.getenv("CLASSIFIER_FALLBACK_MODE"):
        s.classifier.fallback_mode = v
    if v := os.getenv("CLASSIFIER_CONFIDENCE_THRESHOLD"):
        s.classifier.confidence_threshold = _as_float(v, s.classifier.confidence_threshold)
    if v := os.getenv("TAXONOMY_VERSION"):
        s.classifier.taxonomy_version = v

    # Online clustering
    if v := os.getenv("ONLINE_SIMILARITY_THRESHOLD"):
        s.online_clustering.similarity_threshold = _as_float(
            v, s.online_clustering.similarity_threshold
        )
    if v := os.getenv("RECOMPUTE_CENTROID"):
        s.online_clustering.recompute_centroid = _as_bool(
            v, s.online_clustering.recompute_centroid
        )

    # UMAP / HDBSCAN
    if v := os.getenv("UMAP_N_NEIGHBORS"):
        s.recompute.umap.n_neighbors = _as_int(v, s.recompute.umap.n_neighbors)
    if v := os.getenv("UMAP_N_COMPONENTS"):
        s.recompute.umap.n_components = _as_int(v, s.recompute.umap.n_components)
    if v := os.getenv("HDBSCAN_MIN_CLUSTER_SIZE"):
        s.recompute.hdbscan.min_cluster_size = _as_int(v, s.recompute.hdbscan.min_cluster_size)
    if v := os.getenv("HDBSCAN_MIN_SAMPLES"):
        s.recompute.hdbscan.min_samples = _as_int(v, s.recompute.hdbscan.min_samples)

    # Summarization
    if v := os.getenv("SUMMARIZATION_EXAMPLES_COUNT"):
        s.summarization.representative_examples_count = _as_int(
            v, s.summarization.representative_examples_count
        )
    if v := os.getenv("SCENARIO_NAME_MAX_WORDS"):
        s.summarization.scenario_name_max_words = _as_int(
            v, s.summarization.scenario_name_max_words
        )
    if v := os.getenv("MAX_LLM_RETRIES"):
        s.summarization.max_llm_retries = _as_int(v, s.summarization.max_llm_retries)

    # Long text
    if v := os.getenv("MAX_DIRECT_TOKENS"):
        s.long_text.max_direct_tokens = _as_int(v, s.long_text.max_direct_tokens)
    if v := os.getenv("CHUNK_SIZE_TOKENS"):
        s.long_text.chunk_size_tokens = _as_int(v, s.long_text.chunk_size_tokens)
    if v := os.getenv("CHUNK_OVERLAP_TOKENS"):
        s.long_text.chunk_overlap_tokens = _as_int(v, s.long_text.chunk_overlap_tokens)

    # Ingest
    if v := os.getenv("INGEST_BATCH_MAX_SIZE"):
        s.ingest.batch_max_size = _as_int(v, s.ingest.batch_max_size)
    if v := os.getenv("INGEST_WORKER_CONCURRENCY"):
        s.ingest.worker_concurrency = _as_int(v, s.ingest.worker_concurrency)

    # Server / ops
    if v := os.getenv("ML_HOST"):
        s.server.host = v
    if v := os.getenv("ML_PORT"):
        s.server.port = _as_int(v, s.server.port)
    if v := os.getenv("ML_SERVICE_TOKEN"):
        s.service_token = v
    if v := os.getenv("LOG_LEVEL"):
        s.log_level = v.upper()

    return s


def _validate(s: Settings) -> Settings:
    errors: list[str] = []
    if s.online_clustering.similarity_threshold < 0 or s.online_clustering.similarity_threshold > 1:
        errors.append("online_clustering.similarity_threshold must be in [0, 1]")
    if s.classifier.confidence_threshold < 0 or s.classifier.confidence_threshold > 1:
        errors.append("classifier.confidence_threshold must be in [0, 1]")
    if s.classifier.fallback_mode not in {
        "fail_fast",
        "llm",
        "embedding_centroid",
        "keyword",  # offline/tests only
    }:
        errors.append(
            "classifier.fallback_mode must be one of: "
            "fail_fast, llm, embedding_centroid, keyword"
        )
    if s.embeddings.mode not in {"offline", "online", "mock", "local", "ollama", "cloud", "openrouter", "test", ""}:
        errors.append("embeddings.mode must be offline|online|mock")
    if s.embeddings.resolve_provider() not in {"mock", "ollama", "openrouter"}:
        errors.append("embeddings.provider must resolve to mock|ollama|openrouter")
    if s.llm.mode not in {"offline", "online", "local", "ollama", "cloud", "openrouter", ""}:
        errors.append("llm.mode must be offline|online")
    if s.llm.resolve_provider() not in {"ollama", "openrouter"}:
        errors.append("llm.provider must resolve to ollama|openrouter")
    if s.ingest.batch_max_size < 1:
        errors.append("ingest.batch_max_size must be >= 1")
    if s.recompute.umap.n_neighbors < 2:
        errors.append("recompute.umap.n_neighbors must be >= 2")
    if s.recompute.hdbscan.min_cluster_size < 2:
        errors.append("recompute.hdbscan.min_cluster_size must be >= 2")
    # OpenRouter key not required at load time (degraded mode ok); only warn via readiness.
    s.config_errors = errors
    return s


def load_settings(
    *,
    config_path: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Settings:
    """Load settings from config.yaml (optional) then apply env overrides.

    ``env`` may be passed in tests to avoid mutating process environment.
    When provided, temporarily overlays os.environ for override application.
    """
    path = resolve_config_path(config_path)
    if path is not None:
        try:
            raw = _load_yaml(path)
            settings_obj = _settings_from_yaml(raw, path)
        except Exception as exc:  # noqa: BLE001
            settings_obj = Settings(
                config_path=str(path),
                config_loaded=False,
                config_errors=[f"failed to load config: {exc}"],
            )
    else:
        # Env-only / defaults (unit tests, local without yaml)
        settings_obj = Settings(config_loaded=False)

    if env is not None:
        saved = {k: os.environ.get(k) for k in env}
        try:
            os.environ.update({k: str(v) for k, v in env.items()})
            settings_obj = _apply_env_overrides(settings_obj)
        finally:
            for k, old in saved.items():
                if old is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = old
    else:
        settings_obj = _apply_env_overrides(settings_obj)

    return _validate(settings_obj)


def reload_settings(**kwargs: Any) -> Settings:
    """Reload global settings (tests / runtime reconfigure)."""
    global settings
    settings = load_settings(**kwargs)
    return settings


settings = load_settings()
