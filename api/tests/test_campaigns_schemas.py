from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.campaign import CampaignStatus, RecipientStatus
from app.schemas.campaigns import (
    CampaignCreateSchema,
    CampaignRecipientSchema,
    CampaignSchema,
    CampaignStatsSchema,
    CampaignUpdateSchema,
)


def payload(**overrides: Any) -> dict[str, Any]:
    return {"name": "Jesień", "subject": "Nowości", "content": "Dzień dobry"} | overrides


def test_valid_campaign_is_accepted() -> None:
    campaign = CampaignCreateSchema.model_validate(
        payload(recipientIds=[1, 2], scheduledFor="2026-11-01T09:00:00Z")
    )

    assert campaign.name == "Jesień"
    assert campaign.subject == "Nowości"
    assert campaign.content == "Dzień dobry"
    assert campaign.recipient_ids == [1, 2]
    assert campaign.scheduled_for == datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def test_omitted_recipients_and_date_take_their_defaults() -> None:
    campaign = CampaignCreateSchema.model_validate(payload())

    assert campaign.recipient_ids == []
    assert campaign.scheduled_for is None


@pytest.mark.parametrize("name", ["", "   "], ids=["empty", "whitespace"])
def test_empty_name_is_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="Campaign name cannot be empty"):
        CampaignCreateSchema.model_validate(payload(name=name))


def test_name_is_trimmed() -> None:
    campaign = CampaignCreateSchema.model_validate(payload(name="  Jesień 2026  "))

    assert campaign.name == "Jesień 2026"


def test_name_of_256_characters_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Campaign name cannot exceed 255 characters"):
        CampaignCreateSchema.model_validate(payload(name="a" * 256))


def test_name_of_255_characters_is_accepted() -> None:
    assert CampaignCreateSchema.model_validate(payload(name="a" * 255)).name == "a" * 255


@pytest.mark.parametrize("subject", ["", "   "], ids=["empty", "whitespace"])
def test_empty_subject_is_rejected(subject: str) -> None:
    with pytest.raises(ValidationError, match="Email subject cannot be empty"):
        CampaignCreateSchema.model_validate(payload(subject=subject))


def test_subject_is_trimmed() -> None:
    assert CampaignCreateSchema.model_validate(payload(subject="  Nowości  ")).subject == (
        "Nowości"
    )


@pytest.mark.parametrize("content", ["", "  \n "], ids=["empty", "whitespace"])
def test_empty_content_is_rejected(content: str) -> None:
    with pytest.raises(ValidationError, match="Email content cannot be empty"):
        CampaignCreateSchema.model_validate(payload(content=content))


def test_content_is_not_trimmed() -> None:
    assert CampaignCreateSchema.model_validate(payload(content="  Hi  ")).content == "  Hi  "


def test_subject_of_501_characters_is_rejected_on_update() -> None:
    with pytest.raises(ValidationError, match="Email subject cannot exceed 500 characters"):
        CampaignUpdateSchema.model_validate({"subject": "a" * 501})


def test_update_applies_the_create_rules_to_given_strings() -> None:
    with pytest.raises(ValidationError, match="Campaign name cannot be empty"):
        CampaignUpdateSchema.model_validate({"name": " "})

    update = CampaignUpdateSchema.model_validate({"name": "  Zima  ", "content": "  Hi  "})

    assert (update.name, update.content) == ("Zima", "  Hi  ")


def test_update_tells_an_explicit_null_date_from_an_omitted_one() -> None:
    cleared = CampaignUpdateSchema.model_validate({"scheduledFor": None})
    omitted = CampaignUpdateSchema.model_validate({})

    assert "scheduled_for" in cleared.model_fields_set
    assert cleared.scheduled_for is None
    assert "scheduled_for" not in omitted.model_fields_set


def test_campaign_schema_dumps_the_contract_keys() -> None:
    created = datetime(2026, 10, 10, 13, 3, tzinfo=UTC)
    campaign = CampaignSchema(
        id=4,
        name="Jesień",
        subject="Nowości",
        content="Dzień dobry",
        status=CampaignStatus.DRAFT,
        sent_at=None,
        scheduled_for=None,
        created_at=created,
        updated_at=created,
        recipients=[
            CampaignRecipientSchema(
                id=9,
                client_id=7,
                client_name="Acme",
                client_email="biuro@acme.example",
                status=RecipientStatus.PENDING,
                sent_at=None,
                error=None,
            )
        ],
        stats=CampaignStatsSchema(
            total=1,
            sent=0,
            failed=0,
            pending=1,
            bounced=0,
            progress_percentage=0.0,
            success_rate=0.0,
        ),
    )

    assert campaign.model_dump(mode="json") == {
        "id": 4,
        "name": "Jesień",
        "subject": "Nowości",
        "content": "Dzień dobry",
        "status": "draft",
        "sentAt": None,
        "scheduledFor": None,
        "createdAt": "2026-10-10T13:03:00Z",
        "updatedAt": "2026-10-10T13:03:00Z",
        "recipients": [
            {
                "id": 9,
                "clientId": 7,
                "clientName": "Acme",
                "clientEmail": "biuro@acme.example",
                "status": "pending",
                "sentAt": None,
                "error": None,
            }
        ],
        "stats": {
            "total": 1,
            "sent": 0,
            "failed": 0,
            "pending": 1,
            "bounced": 0,
            "progressPercentage": 0.0,
            "successRate": 0.0,
        },
    }
