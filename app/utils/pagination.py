import math
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int


def calculate_pagination(total: int, page: int, per_page: int) -> dict:
    """Return pagination metadata dict for a given total, page, and per_page."""
    pages = math.ceil(total / per_page) if total > 0 else 0
    return {"total": total, "page": page, "per_page": per_page, "pages": pages}


def calculate_offset(page: int, per_page: int) -> int:
    """Return the SQL OFFSET for the given page and per_page values."""
    return (page - 1) * per_page
