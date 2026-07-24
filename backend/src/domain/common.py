from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    """Generic list envelope: items + total (contract §0)."""

    items: list[T]
    total: int
