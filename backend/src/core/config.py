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
    DEMO_USER_EMAIL: str = "test@gmail.com"
    DEMO_USER_PASSWORD: str = "test123"

    # --- CORS (frontend SPA, cookie auth needs explicit origins + credentials) ---
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080"

    # --- ML integration ---
    ML_SERVICE_URL: str = "http://ml-service:8000"
    ML_SERVICE_TOKEN: str = "change-me-ml-token"
    ML_INGEST_BATCH_SIZE: int = 200
    ML_HTTP_TIMEOUT_SEC: int = 30
    ML_PROCESSING_TIMEOUT_SEC: int = 86400
    ML_PROCESSING_POLL_INTERVAL_SEC: float = 1.0
    ML_RECOMPUTE_TIMEOUT_SEC: int = 3600

    # --- Preloaded analytical workspaces ---
    PRELOAD_DATASETS_ENABLED: bool = False
    PRELOAD_DATASETS_RECOMPUTE: bool = True

    # Live ingest webhook token (X-Ingest-Token). Empty disables the check.
    INGEST_TOKEN: str = "dev-ingest-token"

    # --- ROI: benefit side (B) ---
    # Reference average FTE cost given by the customer's expert (QNA §1.1).
    # The hourly rate is derived from it rather than being a standalone number,
    # so the assumption that can actually be challenged is the monthly salary.
    ROI_FTE_MONTHLY_RATE_RUB: float = 400_000.0
    ROI_WORK_HOURS_PER_MONTH: float = 168.0
    # Explicit override; when unset the hourly rate is derived from the two above.
    ROI_FTE_HOURLY_RATE_RUB: float | None = None

    # --- ROI: cost side (A) ---
    # Token cost is derived from infrastructure economics instead of being a
    # magic constant (QNA §1.2): GPU server capex amortised over N years, plus
    # electricity, divided by the tokens that server produces per year.
    ROI_INFRA_CAPEX_RUB: float = 100_000_000.0
    ROI_INFRA_AMORTIZATION_YEARS: float = 5.0
    ROI_INFRA_ELECTRICITY_RUB_PER_YEAR: float = 600_000.0
    ROI_INFRA_TOKENS_PER_YEAR: float = 20_000_000_000.0
    # Explicit override; when unset the price is derived from the four above.
    ROI_TOKEN_COST_PER_1K_RUB: float | None = None
    # Session-length coefficients applied to manual_time (customer FTE method, D6).
    ROI_SESSION_COEFF_SHORT: float = 0.3
    ROI_SESSION_COEFF_MEDIUM: float = 1.0
    ROI_SESSION_COEFF_LONG: float = 2.0
    ROI_SESSION_SHORT_MAX_TOKENS: int = 4000
    ROI_SESSION_LONG_MIN_TOKENS: int = 30000

    # --- Normalization ---
    NORMALIZE_SYNTHESIZE_TIMESTAMPS: bool = True
    NORMALIZE_TIMESTAMP_SPAN_DAYS: int = 14
    # Demo dataset path: backend-owned fixture (decoupled from ml_service layout).
    # Default is the full 4860-record set (real timestamps over 7 days, model
    # metadata, users/departments). `demo_dataset.json` is the older 385-record
    # fixture kept for the lightweight tests.
    DEMO_DATASET_PATH: str = str(BASE_DIR / "src" / "data" / "prompt_radar_dataset.json")

    # --- Read-model cache ---
    # Dashboard statistics is a read-model from the ML store; cache it briefly to
    # avoid hitting ML on every request. 0 disables caching.
    STATISTICS_CACHE_TTL_SEC: int = 15

    @property
    def roi_fte_hourly_rate(self) -> float:
        """FTE cost per hour: explicit override, else monthly salary / hours."""
        if self.ROI_FTE_HOURLY_RATE_RUB is not None:
            return self.ROI_FTE_HOURLY_RATE_RUB
        if self.ROI_WORK_HOURS_PER_MONTH <= 0:
            return 0.0
        return self.ROI_FTE_MONTHLY_RATE_RUB / self.ROI_WORK_HOURS_PER_MONTH

    @property
    def roi_token_cost_per_1k(self) -> float:
        """Cost of 1k tokens: explicit override, else derived from infra economics."""
        if self.ROI_TOKEN_COST_PER_1K_RUB is not None:
            return self.ROI_TOKEN_COST_PER_1K_RUB
        if (
            self.ROI_INFRA_AMORTIZATION_YEARS <= 0
            or self.ROI_INFRA_TOKENS_PER_YEAR <= 0
        ):
            return 0.0
        yearly = (
            self.ROI_INFRA_CAPEX_RUB / self.ROI_INFRA_AMORTIZATION_YEARS
            + self.ROI_INFRA_ELECTRICITY_RUB_PER_YEAR
        )
        return yearly / self.ROI_INFRA_TOKENS_PER_YEAR * 1000.0

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS CSV into a clean list of allowed origins."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

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
