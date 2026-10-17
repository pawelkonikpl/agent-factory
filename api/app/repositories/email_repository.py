"""The email log in PostgreSQL. Every query skips soft-deleted emails."""

from dataclasses import dataclass

from sqlalchemy import ColumnElement, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utc_now
from app.models.campaign import Campaign
from app.models.client import Client
from app.models.email import Email, EmailStatus
from app.schemas.emails import EmailFilters, EmailUpdateSchema
from app.services.smtp_sender import SendResult


@dataclass(frozen=True)
class EmailCounts:
    """The stats' counts: all emails, per status, and with a delivery, open or click time."""

    total: int
    pending: int
    sending: int
    sent: int
    failed: int
    bounced: int
    rejected: int
    deferred: int
    delivered: int
    opened: int
    clicked: int


def _list_filters(filters: EmailFilters) -> list[ColumnElement[bool]]:
    """The list's and its total's filter: not deleted and matching every given filter.

    autoescape matches %, _ and the escape character literally.
    """
    conditions = [Email.is_deleted == false()]
    if filters.campaign_id is not None:
        conditions.append(Email.campaign_id == filters.campaign_id)
    if filters.client_id is not None:
        conditions.append(Email.client_id == filters.client_id)
    if filters.status is not None:
        conditions.append(Email.status == filters.status)
    if filters.from_date is not None:
        conditions.append(Email.created_at >= filters.from_date)
    if filters.to_date is not None:
        conditions.append(Email.created_at <= filters.to_date)
    if filters.has_error is not None:
        has_error = Email.error_message.is_not(None)
        conditions.append(has_error if filters.has_error else Email.error_message.is_(None))
    if filters.search:
        term = filters.search
        conditions.append(
            or_(
                Email.recipient_email.icontains(term, autoescape=True),
                Email.subject.icontains(term, autoescape=True),
                # EXISTS subqueries, so each email is returned once.
                Email.client.has(Client.company_name.icontains(term, autoescape=True)),
                Email.campaign.has(Campaign.name.icontains(term, autoescape=True)),
            )
        )
    return conditions


_NEWEST_FIRST = (Email.created_at.desc(), Email.id.desc())


class EmailRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        campaign: Campaign,
        client: Client,
        recipient_email: str,
        subject: str,
        body: str,
    ) -> Email:
        # The campaign and client objects, not only their IDs: the schema reads their names
        # without a lazy load.
        email = Email(
            campaign=campaign,
            client=client,
            recipient_email=recipient_email,
            subject=subject,
            body=body,
            status=EmailStatus.PENDING,
        )
        self._session.add(email)
        await self._session.commit()
        return email

    async def get_by_id(self, email_id: int) -> Email | None:
        query = select(Email).where(Email.id == email_id, Email.is_deleted == false())
        return await self._session.scalar(query)

    async def get_all(self, filters: EmailFilters, skip: int, limit: int) -> list[Email]:
        query = (
            select(Email)
            .where(*_list_filters(filters))
            .order_by(*_NEWEST_FIRST)
            .offset(skip)
            .limit(limit)
        )
        return list(await self._session.scalars(query))

    async def count(self, filters: EmailFilters) -> int:
        query = select(func.count()).select_from(Email).where(*_list_filters(filters))
        return (await self._session.execute(query)).scalar_one()

    async def get_by_campaign(self, campaign_id: int, skip: int, limit: int) -> list[Email]:
        return await self.get_all(EmailFilters(campaign_id=campaign_id), skip, limit)

    async def get_by_client(self, client_id: int, skip: int, limit: int) -> list[Email]:
        return await self.get_all(EmailFilters(client_id=client_id), skip, limit)

    async def get_failed(self, campaign_id: int | None) -> list[Email]:
        filters = EmailFilters(campaign_id=campaign_id, status=EmailStatus.FAILED)
        query = select(Email).where(*_list_filters(filters)).order_by(*_NEWEST_FIRST)
        return list(await self._session.scalars(query))

    async def get_for_recipient(self, campaign_id: int, client_id: int) -> Email | None:
        filters = EmailFilters(campaign_id=campaign_id, client_id=client_id)
        query = select(Email).where(*_list_filters(filters)).order_by(*_NEWEST_FIRST).limit(1)
        return await self._session.scalar(query)

    async def update(
        self, email: Email, data: EmailUpdateSchema, status: EmailStatus | None
    ) -> Email:
        """Write the given status and every other field of data that is not None."""
        if status is not None:
            email.status = status
        # Field names, not the camelCase aliases the schema dumps by default.
        fields = data.model_dump(by_alias=False, exclude={"status"}, exclude_none=True)
        for name, value in fields.items():
            setattr(email, name, value)
        await self._session.commit()
        return email

    async def soft_delete(self, email: Email) -> Email:
        email.is_deleted = True
        email.deleted_at = utc_now()
        await self._session.commit()
        return email

    async def mark_opened(self, email: Email) -> Email:
        email.opened_at = utc_now()
        await self._session.commit()
        return email

    async def mark_clicked(self, email: Email) -> Email:
        email.clicked_at = utc_now()
        await self._session.commit()
        return email

    async def record_send(self, email: Email, result: SendResult) -> Email:
        """Write a send's outcome; sent_at only moves on success."""
        if result.success:
            email.status = EmailStatus.SENT
            email.sent_at = utc_now()
        else:
            email.status = EmailStatus.FAILED
        email.smtp_message_id = result.smtp_message_id
        email.error_message = None if result.success else result.error
        email.retry_count += 1
        await self._session.commit()
        return email

    async def get_stats(self, campaign_id: int | None) -> EmailCounts:
        """One aggregate query, COUNT(*) FILTER (WHERE ...) per count; no rows are loaded.

        Each count is labelled with its EmailCounts field.
        """
        by_status = [
            func.count().filter(Email.status == status).label(status.value)
            for status in EmailStatus
        ]
        query = (
            select(
                func.count().label("total"),
                *by_status,
                func.count().filter(Email.delivered_at.is_not(None)).label("delivered"),
                func.count().filter(Email.opened_at.is_not(None)).label("opened"),
                func.count().filter(Email.clicked_at.is_not(None)).label("clicked"),
            )
            .select_from(Email)
            .where(*_list_filters(EmailFilters(campaign_id=campaign_id)))
        )
        row = (await self._session.execute(query)).one()
        return EmailCounts(**row._asdict())
