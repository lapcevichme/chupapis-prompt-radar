"""ML service error codes and exception types (ТЗ §10)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


# Canonical error codes from ТЗ §10 / docs/contracts/backend-ml.md
INVALID_REQUEST = "INVALID_REQUEST"
INGEST_VALIDATION_FAILED = "INGEST_VALIDATION_FAILED"
CLASSIFIER_NOT_AVAILABLE = "CLASSIFIER_NOT_AVAILABLE"
EMBEDDING_PROVIDER_UNAVAILABLE = "EMBEDDING_PROVIDER_UNAVAILABLE"
EMBEDDING_REQUEST_FAILED = "EMBEDDING_REQUEST_FAILED"
LLM_PROVIDER_UNAVAILABLE = "LLM_PROVIDER_UNAVAILABLE"
LLM_RESPONSE_INVALID = "LLM_RESPONSE_INVALID"
CLUSTERING_FAILED = "CLUSTERING_FAILED"
STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
RECOMPUTE_FAILED = "RECOMPUTE_FAILED"
INTERNAL_ERROR = "INTERNAL_ERROR"
UNAUTHORIZED = "UNAUTHORIZED"

# Default HTTP status + retryable flag per code
_CODE_META: dict[str, tuple[int, bool]] = {
    INVALID_REQUEST: (400, False),
    INGEST_VALIDATION_FAILED: (400, False),
    UNAUTHORIZED: (401, False),
    CLASSIFIER_NOT_AVAILABLE: (503, True),
    EMBEDDING_PROVIDER_UNAVAILABLE: (503, True),
    EMBEDDING_REQUEST_FAILED: (502, True),
    LLM_PROVIDER_UNAVAILABLE: (503, True),
    LLM_RESPONSE_INVALID: (502, False),
    CLUSTERING_FAILED: (500, False),
    STORE_UNAVAILABLE: (503, True),
    RECOMPUTE_FAILED: (500, True),
    INTERNAL_ERROR: (500, False),
}


@dataclass
class ErrorBody:
    """Wire format: { code, message, retryable, details? } — no secrets/stack traces."""

    code: str
    message: str
    retryable: bool
    details: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details is not None:
            out["details"] = self.details
        return out


@dataclass
class MLServiceError(Exception):
    """Domain exception mapped to HTTP error body."""

    code: str
    message: str
    retryable: Optional[bool] = None
    details: Optional[dict[str, Any]] = None
    status_code: Optional[int] = None

    def __post_init__(self) -> None:
        default_status, default_retry = _CODE_META.get(self.code, (500, False))
        if self.status_code is None:
            self.status_code = default_status
        if self.retryable is None:
            self.retryable = default_retry
        super().__init__(self.message)

    def to_body(self) -> ErrorBody:
        return ErrorBody(
            code=self.code,
            message=self.message,
            retryable=bool(self.retryable),
            details=self.details,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.to_body().to_dict()


def error_response(
    code: str,
    message: str,
    *,
    retryable: Optional[bool] = None,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a standard error payload without raising."""
    _, default_retry = _CODE_META.get(code, (500, False))
    body = ErrorBody(
        code=code,
        message=message,
        retryable=default_retry if retryable is None else retryable,
        details=details,
    )
    return body.to_dict()
