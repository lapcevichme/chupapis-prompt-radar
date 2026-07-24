from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..tables.mixins import UUIDPrimaryKeyMixin
from ..tables.table_base import Base


class RoiCache(UUIDPrimaryKeyMixin, Base):
    """Optional cache of computed ROI. The key encodes source_id, filters and rates."""

    __tablename__ = "roi_cache"

    key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    by_category: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    by_scenario: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
