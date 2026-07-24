from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..tables.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin
from ..tables.table_base import Base

# origin {"upload", "demo"}
# status {"ingesting", "classified", "recomputed", "failed"}


class IngestionSource(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A dataset upload (source_id) streamed into the ML service."""

    __tablename__ = "ingestion_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    records_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    records_valid: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    records_rejected: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    normalization_report: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ingesting", server_default="ingesting"
    )
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
