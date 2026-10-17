"""Shared schema pieces: the camelCase base schema, the paginated response and its parameters."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

T = TypeVar("T")

# PostgreSQL's limits on input: a value past them answers 422, not a database error (500).
DbInt = Annotated[int, Field(ge=-(2**31), le=2**31 - 1)]


def _without_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    return value


def _in_utc_range(value: datetime) -> datetime:
    # The database gets the time in UTC; a naive time is taken as UTC already.
    if value.tzinfo is not None:
        try:
            value.astimezone(UTC)
        except OverflowError:
            raise ValueError("date out of range in UTC") from None
    return value


DbText = Annotated[str, AfterValidator(_without_nul)]
DbDatetime = Annotated[datetime, AfterValidator(_in_utc_range)]


class BaseSchema(BaseModel):
    """camelCase out, camelCase or snake_case in, and validation from ORM objects."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        from_attributes=True,
    )


class Page(BaseSchema, Generic[T]):
    items: list[T]
    total: int


@dataclass(frozen=True)
class PageParams:
    """The skip and limit query parameters of a paginated list (D28)."""

    skip: int = Query(0, ge=0, le=2**63 - 1)
    limit: int = Query(100, ge=1, le=1000)


PageParamsDep = Annotated[PageParams, Depends()]


class MessageSchema(BaseSchema):
    message: str
