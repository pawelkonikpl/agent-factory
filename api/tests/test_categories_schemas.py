from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.category import Category
from app.schemas.categories import CategoryCreateSchema, CategorySchema, CategoryUpdateSchema

NameSchema = type[CategoryCreateSchema] | type[CategoryUpdateSchema]

both_schemas = pytest.mark.parametrize(
    "schema", [CategoryCreateSchema, CategoryUpdateSchema], ids=["create", "update"]
)


@both_schemas
def test_valid_name_is_accepted(schema: NameSchema) -> None:
    assert schema(name="Klienci").name == "Klienci"


@both_schemas
def test_empty_name_is_rejected(schema: NameSchema) -> None:
    with pytest.raises(ValidationError, match="Category name cannot be empty"):
        schema(name="")


@both_schemas
def test_whitespace_only_name_is_rejected(schema: NameSchema) -> None:
    with pytest.raises(ValidationError, match="Category name cannot be empty"):
        schema(name="   ")


@both_schemas
def test_name_is_trimmed(schema: NameSchema) -> None:
    assert schema(name="  Klienci VIP  ").name == "Klienci VIP"


@both_schemas
def test_name_of_65_characters_is_rejected(schema: NameSchema) -> None:
    with pytest.raises(ValidationError, match="Category name cannot exceed 64 characters"):
        schema(name="a" * 65)


@both_schemas
def test_name_of_64_characters_is_accepted(schema: NameSchema) -> None:
    assert schema(name="a" * 64).name == "a" * 64


def test_category_schema_dumps_id_name_and_camel_case_timestamps() -> None:
    created = datetime(2026, 10, 10, 13, 3, tzinfo=UTC)
    category = Category(
        id=1, name="Klienci", created_at=created, updated_at=created, is_deleted=False
    )

    dumped = CategorySchema.model_validate(category).model_dump(mode="json")

    assert dumped == {
        "id": 1,
        "name": "Klienci",
        "createdAt": "2026-10-10T13:03:00Z",
        "updatedAt": "2026-10-10T13:03:00Z",
    }
