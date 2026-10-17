"""Email log schemas (api-contract.md §2) and the list's filter parameters (§3.4)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query
from pydantic import Field

from app.models.email import EmailStatus
from app.schemas.base import BaseSchema, DbDatetime, DbInt, DbText


class EmailSchema(BaseSchema):
    id: int
    campaign_id: int
    client_id: int
    recipient_email: str
    client_name: str | None
    campaign_name: str | None
    subject: str
    content: str
    status: EmailStatus
    sent_at: datetime | None
    delivered_at: datetime | None
    opened_at: datetime | None
    clicked_at: datetime | None
    bounced_at: datetime | None
    error_message: str | None
    error_code: str | None
    retry_count: int
    max_retries: int
    smtp_message_id: str | None
    smtp_response: str | None
    created_at: datetime
    updated_at: datetime


class EmailUpdateSchema(BaseSchema):
    """A partial update: null or omitted keeps a field. The service checks the status."""

    status: str | None = None
    sent_at: DbDatetime | None = None
    delivered_at: DbDatetime | None = None
    opened_at: DbDatetime | None = None
    clicked_at: DbDatetime | None = None
    bounced_at: DbDatetime | None = None
    error_message: DbText | None = None
    # The column lengths: a longer value answers 422, not a database error.
    error_code: DbText | None = Field(default=None, max_length=50)
    smtp_message_id: DbText | None = Field(default=None, max_length=255)
    smtp_response: DbText | None = None


class EmailStatsSchema(BaseSchema):
    total: int
    pending: int
    sending: int
    sent: int
    failed: int
    bounced: int
    rejected: int
    deferred: int
    # Rows with deliveredAt, openedAt and clickedAt set; delivered is not a status (W-09).
    delivered: int
    opened: int
    clicked: int
    delivery_rate: float
    open_rate: float
    click_rate: float
    bounce_rate: float


@dataclass(frozen=True)
class EmailFilters:
    """The filters of GET /emails/, passed as one object down to the repository.

    Plain None defaults, so the repository can build one for its own lists.
    """

    campaign_id: Annotated[DbInt | None, Query()] = None
    client_id: Annotated[DbInt | None, Query()] = None
    status: Annotated[EmailStatus | None, Query()] = None
    # Both bounds inclusive, on createdAt.
    from_date: Annotated[DbDatetime | None, Query()] = None
    to_date: Annotated[DbDatetime | None, Query()] = None
    has_error: Annotated[bool | None, Query()] = None
    search: Annotated[DbText | None, Query()] = None


EmailFiltersDep = Annotated[EmailFilters, Depends()]
