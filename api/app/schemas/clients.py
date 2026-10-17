"""Client schemas (api-contract.md §2)."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field

from app.schemas.base import BaseSchema
from app.schemas.categories import CategorySchema

COMPANY_NAME_MAX_LENGTH = 128


def validate_company_name(value: str) -> str:
    """Trim the name; a ValueError's message reaches the 422 as the contract's message."""
    name = value.strip()
    if not name:
        raise ValueError("Company name cannot be empty")
    if len(name) > COMPANY_NAME_MAX_LENGTH:
        raise ValueError(f"Company name cannot exceed {COMPANY_NAME_MAX_LENGTH} characters")
    return name


CompanyName = Annotated[str, AfterValidator(validate_company_name)]


class ClientFieldsSchema(BaseSchema):
    """What a client is written with. Create and update take the same fields and defaults."""

    company_name: CompanyName
    primary_email: EmailStr
    additional_emails: str | None = None
    phone_number: str | None = None
    address: str | None = None
    is_active: bool = True
    notes: str | None = None
    category_ids: list[int] = Field(default_factory=list)


class ClientCreateSchema(ClientFieldsSchema):
    pass


class ClientUpdateSchema(ClientFieldsSchema):
    """A full replacement (W-01): an omitted field takes its default, as on create."""


class ClientSchema(BaseSchema):
    id: int
    company_name: str
    primary_email: str
    additional_emails: str | None
    phone_number: str | None
    address: str | None
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
    categories: list[CategorySchema]
