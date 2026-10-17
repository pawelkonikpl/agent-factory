"""Campaign schemas (api-contract.md §2)."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field

from app.models.campaign import CampaignStatus, RecipientStatus
from app.schemas.base import BaseSchema

CAMPAIGN_NAME_MAX_LENGTH = 255
SUBJECT_MAX_LENGTH = 500


def validate_campaign_name(value: str) -> str:
    """Trim the name; a ValueError's message reaches the 422 as the contract's message."""
    name = value.strip()
    if not name:
        raise ValueError("Campaign name cannot be empty")
    if len(name) > CAMPAIGN_NAME_MAX_LENGTH:
        raise ValueError(f"Campaign name cannot exceed {CAMPAIGN_NAME_MAX_LENGTH} characters")
    return name


def validate_subject(value: str) -> str:
    subject = value.strip()
    if not subject:
        raise ValueError("Email subject cannot be empty")
    if len(subject) > SUBJECT_MAX_LENGTH:
        raise ValueError(f"Email subject cannot exceed {SUBJECT_MAX_LENGTH} characters")
    return subject


def validate_content(value: str) -> str:
    # Checked trimmed, kept as given: leading spaces and newlines may be part of the email.
    if not value.strip():
        raise ValueError("Email content cannot be empty")
    return value


CampaignName = Annotated[str, AfterValidator(validate_campaign_name)]
EmailSubject = Annotated[str, AfterValidator(validate_subject)]
EmailContent = Annotated[str, AfterValidator(validate_content)]


class CampaignCreateSchema(BaseSchema):
    name: CampaignName
    subject: EmailSubject
    content: EmailContent
    recipient_ids: list[int] = Field(default_factory=list)
    scheduled_for: datetime | None = None


class CampaignUpdateSchema(BaseSchema):
    """A partial update: null or omitted keeps a field, except an explicit null scheduledFor."""

    name: CampaignName | None = None
    subject: EmailSubject | None = None
    content: EmailContent | None = None
    recipient_ids: list[int] | None = None
    scheduled_for: datetime | None = None


class CampaignResendSchema(BaseSchema):
    """CampaignRecipient IDs, not client IDs; null or omitted means every failed recipient."""

    recipient_ids: list[int] | None = None


class CampaignRecipientSchema(BaseSchema):
    id: int
    client_id: int
    client_name: str
    client_email: str
    status: RecipientStatus
    sent_at: datetime | None
    error: str | None


class CampaignStatsSchema(BaseSchema):
    total: int
    sent: int
    failed: int
    pending: int
    bounced: int
    progress_percentage: float
    success_rate: float


class CampaignSchema(BaseSchema):
    id: int
    name: str
    subject: str
    content: str
    status: CampaignStatus
    sent_at: datetime | None
    scheduled_for: datetime | None
    created_at: datetime
    updated_at: datetime
    recipients: list[CampaignRecipientSchema]
    stats: CampaignStatsSchema | None
