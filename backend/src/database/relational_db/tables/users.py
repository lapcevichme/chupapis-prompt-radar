from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..tables.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin
from ..tables.table_base import Base


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Application user: id, email, password_hash, created_at."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
