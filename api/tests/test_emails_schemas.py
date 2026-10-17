from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.email import EmailStatus
from app.schemas.emails import EmailSchema, EmailUpdateSchema


def test_email_schema_dumps_the_contract_keys() -> None:
    created = datetime(2026, 10, 10, 13, 3, tzinfo=UTC)
    email = EmailSchema(
        id=5,
        campaign_id=4,
        client_id=7,
        recipient_email="biuro@acme.example",
        client_name="Acme",
        campaign_name="Jesień",
        subject="Nowości",
        content="Dzień dobry",
        status=EmailStatus.SENT,
        sent_at=created,
        delivered_at=None,
        opened_at=None,
        clicked_at=None,
        bounced_at=None,
        error_message=None,
        error_code=None,
        retry_count=0,
        max_retries=3,
        smtp_message_id="<1@acme.example>",
        smtp_response=None,
        created_at=created,
        updated_at=created,
    )

    assert email.model_dump(mode="json") == {
        "id": 5,
        "campaignId": 4,
        "clientId": 7,
        "recipientEmail": "biuro@acme.example",
        "clientName": "Acme",
        "campaignName": "Jesień",
        "subject": "Nowości",
        "content": "Dzień dobry",
        "status": "sent",
        "sentAt": "2026-10-10T13:03:00Z",
        "deliveredAt": None,
        "openedAt": None,
        "clickedAt": None,
        "bouncedAt": None,
        "errorMessage": None,
        "errorCode": None,
        "retryCount": 0,
        "maxRetries": 3,
        "smtpMessageId": "<1@acme.example>",
        "smtpResponse": None,
        "createdAt": "2026-10-10T13:03:00Z",
        "updatedAt": "2026-10-10T13:03:00Z",
    }


def test_update_accepts_an_empty_body() -> None:
    update = EmailUpdateSchema.model_validate({})

    assert update.model_dump(by_alias=False) == dict.fromkeys(EmailUpdateSchema.model_fields)


@pytest.mark.parametrize(
    "body",
    [
        {"errorMessage": "Timeout", "errorCode": "421", "deliveredAt": "2026-10-10T13:03:00Z"},
        {"error_message": "Timeout", "error_code": "421", "delivered_at": "2026-10-10T13:03:00Z"},
    ],
    ids=["camelCase", "snake_case"],
)
def test_update_accepts_camel_and_snake_case_keys(body: dict[str, str]) -> None:
    update = EmailUpdateSchema.model_validate(body | {"status": "sent"})

    assert update.status == "sent"
    assert update.error_message == "Timeout"
    assert update.error_code == "421"
    assert update.delivered_at == datetime(2026, 10, 10, 13, 3, tzinfo=UTC)


def test_update_keeps_an_unknown_status_for_the_service_to_check() -> None:
    assert EmailUpdateSchema.model_validate({"status": "bogus"}).status == "bogus"


def test_error_code_of_51_characters_is_rejected() -> None:
    with pytest.raises(ValidationError, match="errorCode"):
        EmailUpdateSchema.model_validate({"errorCode": "a" * 51})


def test_error_code_of_50_characters_is_accepted() -> None:
    assert EmailUpdateSchema.model_validate({"errorCode": "a" * 50}).error_code == "a" * 50


def test_smtp_message_id_of_256_characters_is_rejected() -> None:
    with pytest.raises(ValidationError, match="smtpMessageId"):
        EmailUpdateSchema.model_validate({"smtpMessageId": "a" * 256})
