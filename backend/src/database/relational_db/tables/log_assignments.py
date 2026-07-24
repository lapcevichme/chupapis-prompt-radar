from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..tables.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from ..tables.table_base import Base


class LogAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Cache of per-request assignments from the ML service, used by ROI and /logs.

    Synced from ML GET /assignments; (source_id, request_id) is unique (upsert).
    """

    __tablename__ = "log_assignments"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_sources.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    scenario_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scenario_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_outlier: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    has_failure_signals: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    __table_args__ = (
        Index(
            "ix_log_assignments_source_request",
            "source_id",
            "request_id",
            unique=True,
        ),
    )
