"""The email log: one row per email to a campaign recipient, with its own copy of the text."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin, enum_values
from app.models.campaign import Campaign
from app.models.client import Client


class EmailStatus(enum.StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class Email(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "emails"

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_email: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    # The subject and body as sent, not the campaign's current text (D25, W-17).
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EmailStatus] = mapped_column(
        Enum(
            EmailStatus,
            native_enum=False,
            values_callable=enum_values,
            create_constraint=True,
            name="email_status",
        ),
        nullable=False,
        default=EmailStatus.PENDING,
        index=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Delivered is a time, not a status (W-09).
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(nullable=False, default=3)
    smtp_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    campaign: Mapped[Campaign] = relationship(lazy="selectin")
    client: Mapped[Client] = relationship(lazy="selectin")
