"""Campaigns are global (D5). A campaign is sent to its recipients, one per client."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.models.client import Client


class CampaignStatus(enum.StrEnum):
    DRAFT = "draft"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    SCHEDULED = "scheduled"


class RecipientStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"


def _values(enum_class: type[enum.Enum]) -> list[str]:
    # Store the lowercase values, not the member names SQLAlchemy stores by default.
    return [member.value for member in enum_class]


class Campaign(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # VARCHAR with a named CHECK constraint, so a new status needs no ALTER TYPE.
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(
            CampaignStatus,
            native_enum=False,
            values_callable=_values,
            create_constraint=True,
            name="campaign_status",
        ),
        nullable=False,
        default=CampaignStatus.DRAFT,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Stored only; nothing sends at this time (D6).
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Soft-deleted recipients are loaded too; readers skip them.
    recipients: Mapped[list["CampaignRecipient"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CampaignRecipient.id",
    )


class CampaignRecipient(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "campaign_recipients"
    # A client is on a campaign once among non-deleted recipients.
    __table_args__ = (
        Index(
            "uq_campaign_recipients_campaign_id_client_id_not_deleted",
            "campaign_id",
            "client_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[RecipientStatus] = mapped_column(
        Enum(
            RecipientStatus,
            native_enum=False,
            values_callable=_values,
            create_constraint=True,
            name="recipient_status",
        ),
        nullable=False,
        default=RecipientStatus.PENDING,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    campaign: Mapped[Campaign] = relationship(back_populates="recipients", lazy="selectin")
    client: Mapped[Client] = relationship(lazy="selectin")
