from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..tables.mixins import UUIDPrimaryKeyMixin
from ..tables.table_base import Base


class DatasetRecord(UUIDPrimaryKeyMixin, Base):
    """Raw dataset fields kept for the ROI join and the logs view.

    (source_id, request_id) is unique: the idempotency key for re-ingestion.
    """

    __tablename__ = "dataset_records"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_sources.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    gold_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # source field: simulated_context_tokens
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # source field: estimated_manual_time_minutes
    manual_time_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    tools_used: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_dataset_records_source_request",
            "source_id",
            "request_id",
            unique=True,
        ),
    )
