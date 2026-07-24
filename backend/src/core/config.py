import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=f"{BASE_DIR}/.env", extra="ignore")

    # --- App ---
    APP_STAGE: Literal["dev", "prod"] = "dev"
    APP_VERSION: str = "dev"
    DEBUG: bool | None = None
    LOG_LEVEL: str = "INFO"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8080
    SQL_ECHO: bool = False

    # --- DB / cache ---
    DATABASE_URL: str
    REDIS_URL: str | None = None  # optional (statistics/ROI cache)

    # --- Auth (JWT + cookie) ---
    JWT_SECRET: str
    JWT_ALGO: str = "HS256"
    ACCESS_TTL: int = 900
    REFRESH_TTL: int = 604800
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    COOKIE_DOMAIN: str | None = None
    COOKIE_PATH: str = "/"
    DEMO_USER_EMAIL: str = "demo@prompt-radar.local"
    DEMO_USER_PASSWORD: str = "DemoPass123!"

    # --- ML integration ---
    ML_SERVICE_URL: str = "http://ml-service:8000"
    ML_SERVICE_TOKEN: str = "change-me-ml-token"
    ML_INGEST_BATCH_SIZE: int = 200
    ML_HTTP_TIMEOUT_SEC: int = 30

    # --- ROI defaults ---
    ROI_FTE_HOURLY_RATE_RUB: float = 1200.0
    ROI_TOKEN_COST_PER_1K_RUB: float = 0.015

    # --- Normalization ---
    NORMALIZE_SYNTHESIZE_TIMESTAMPS: bool = True
    NORMALIZE_TIMESTAMP_SPAN_DAYS: int = 14
    # Demo dataset path: backend-owned fixture (decoupled from ml_service layout).
    DEMO_DATASET_PATH: str = str(BASE_DIR / "src" / "data" / "demo_dataset.json")

    @field_validator("COOKIE_SAMESITE", mode="before")
    @classmethod
    def _normalize_samesite(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return value.strip().lower()

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _normalize_debug(cls, value: bool | str | None) -> bool | None:
        if value is None or isinstance(value, bool):
            return value

        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        if normalized in {"", "none", "null", "release"}:
            return None

        return value

    @field_validator("JWT_SECRET")
    @classmethod
    def _validate_jwt_secret(cls, value: str) -> str:
        secret = value.strip()
        if len(secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long.")
        return secret


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def configure_logging(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    )
