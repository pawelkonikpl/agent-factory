from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.category import Category
from app.models.client import Client
from app.schemas.clients import ClientCreateSchema, ClientSchema, ClientUpdateSchema

InputSchema = type[ClientCreateSchema] | type[ClientUpdateSchema]

both_schemas = pytest.mark.parametrize(
    "schema", [ClientCreateSchema, ClientUpdateSchema], ids=["create", "update"]
)


def payload(**overrides: Any) -> dict[str, Any]:
    return {"companyName": "Acme", "primaryEmail": "biuro@acme.example"} | overrides


@both_schemas
def test_valid_client_is_accepted(schema: InputSchema) -> None:
    client = schema.model_validate(
        payload(
            additionalEmails="handel@acme.example, faktury@acme.example",
            phoneNumber="+48 600 100 200",
            address="ul. Prosta 1, Warszawa",
            isActive=False,
            notes="Stały klient",
            categoryIds=[1, 2],
        )
    )

    assert client.company_name == "Acme"
    assert client.primary_email == "biuro@acme.example"
    assert client.additional_emails == "handel@acme.example, faktury@acme.example"
    assert client.phone_number == "+48 600 100 200"
    assert client.address == "ul. Prosta 1, Warszawa"
    assert client.is_active is False
    assert client.notes == "Stały klient"
    assert client.category_ids == [1, 2]


@both_schemas
def test_empty_company_name_is_rejected(schema: InputSchema) -> None:
    with pytest.raises(ValidationError, match="Company name cannot be empty"):
        schema.model_validate(payload(companyName=""))


@both_schemas
def test_whitespace_only_company_name_is_rejected(schema: InputSchema) -> None:
    with pytest.raises(ValidationError, match="Company name cannot be empty"):
        schema.model_validate(payload(companyName="   "))


@both_schemas
def test_company_name_is_trimmed(schema: InputSchema) -> None:
    client = schema.model_validate(payload(companyName="  Acme Sp. z o.o.  "))

    assert client.company_name == "Acme Sp. z o.o."


@both_schemas
def test_company_name_of_129_characters_is_rejected(schema: InputSchema) -> None:
    with pytest.raises(ValidationError, match="Company name cannot exceed 128 characters"):
        schema.model_validate(payload(companyName="a" * 129))


@both_schemas
def test_company_name_of_128_characters_is_accepted(schema: InputSchema) -> None:
    assert schema.model_validate(payload(companyName="a" * 128)).company_name == "a" * 128


@both_schemas
def test_invalid_primary_email_is_rejected(schema: InputSchema) -> None:
    with pytest.raises(ValidationError) as error:
        schema.model_validate(payload(primaryEmail="not-an-email"))

    assert [problem["loc"] for problem in error.value.errors()] == [("primaryEmail",)]


@both_schemas
def test_omitted_fields_take_their_defaults(schema: InputSchema) -> None:
    client = schema.model_validate(payload())

    assert client.additional_emails is None
    assert client.phone_number is None
    assert client.address is None
    assert client.notes is None
    assert client.is_active is True
    assert client.category_ids == []


def test_client_schema_dumps_the_contract_keys_with_its_categories() -> None:
    created = datetime(2026, 10, 10, 13, 3, tzinfo=UTC)
    category = Category(
        id=3, name="Hurtownie", created_at=created, updated_at=created, is_deleted=False
    )
    client = Client(
        id=7,
        company_name="Acme",
        primary_email="biuro@acme.example",
        additional_emails=None,
        phone_number="+48 600 100 200",
        address=None,
        is_active=True,
        notes=None,
        created_at=created,
        updated_at=created,
        is_deleted=False,
        categories=[category],
    )

    dumped = ClientSchema.model_validate(client).model_dump(mode="json")

    assert dumped == {
        "id": 7,
        "companyName": "Acme",
        "primaryEmail": "biuro@acme.example",
        "additionalEmails": None,
        "phoneNumber": "+48 600 100 200",
        "address": None,
        "isActive": True,
        "notes": None,
        "createdAt": "2026-10-10T13:03:00Z",
        "updatedAt": "2026-10-10T13:03:00Z",
        "categories": [
            {
                "id": 3,
                "name": "Hurtownie",
                "createdAt": "2026-10-10T13:03:00Z",
                "updatedAt": "2026-10-10T13:03:00Z",
            }
        ],
    }
