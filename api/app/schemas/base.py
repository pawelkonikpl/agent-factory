"""Shared schema pieces: the camelCase base schema, the paginated response and its parameters."""

from dataclasses import dataclass
from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


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

    skip: int = Query(0, ge=0)
    limit: int = Query(100, ge=1, le=1000)


PageParamsDep = Annotated[PageParams, Depends()]
