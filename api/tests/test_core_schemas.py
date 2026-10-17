from datetime import UTC, datetime

from app.schemas.base import BaseSchema, Page
from app.schemas.notes import NoteCreate, NoteResponse


class Thing(BaseSchema):
    company_name: str


def test_base_schema_dumps_camel_case_keys() -> None:
    thing = Thing(company_name="Acme")

    assert thing.model_dump() == {"companyName": "Acme"}
    assert thing.model_dump_json() == '{"companyName":"Acme"}'


def test_base_schema_accepts_camel_case_and_snake_case_input() -> None:
    from_camel = Thing.model_validate({"companyName": "Acme"})
    from_snake = Thing.model_validate({"company_name": "Acme"})

    assert from_camel.company_name == "Acme"
    assert from_snake.company_name == "Acme"


def test_page_dumps_items_and_total() -> None:
    page = Page[Thing](items=[Thing(company_name="Acme")], total=1)

    assert page.model_dump() == {"items": [{"companyName": "Acme"}], "total": 1}


def test_notes_schemas_keep_snake_case() -> None:
    note = NoteResponse(
        id="1", text="Notatka", created_at=datetime(2026, 10, 10, 13, 3, tzinfo=UTC)
    )

    assert not issubclass(NoteResponse, BaseSchema)
    assert not issubclass(NoteCreate, BaseSchema)
    assert note.model_dump(mode="json") == {
        "id": "1",
        "text": "Notatka",
        "created_at": "2026-10-10T13:03:00Z",
    }
