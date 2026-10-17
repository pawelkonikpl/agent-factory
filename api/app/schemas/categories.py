"""Category schemas (api-contract.md §2)."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator

from app.schemas.base import BaseSchema

CATEGORY_NAME_MAX_LENGTH = 64


def validate_category_name(value: str) -> str:
    """Trim the name; a ValueError's message reaches the 422 as the contract's message."""
    name = value.strip()
    if not name:
        raise ValueError("Category name cannot be empty")
    if len(name) > CATEGORY_NAME_MAX_LENGTH:
        raise ValueError(f"Category name cannot exceed {CATEGORY_NAME_MAX_LENGTH} characters")
    return name


CategoryName = Annotated[str, AfterValidator(validate_category_name)]


class CategoryCreateSchema(BaseSchema):
    name: CategoryName


class CategoryUpdateSchema(BaseSchema):
    name: CategoryName


class CategorySchema(BaseSchema):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
