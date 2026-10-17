"""Campaigns and their recipients in PostgreSQL. Every query skips soft-deleted campaigns."""

from datetime import datetime

from sqlalchemy import ColumnElement, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utc_now
from app.models.campaign import Campaign, CampaignRecipient, CampaignStatus, RecipientStatus
from app.models.client import Client
from app.schemas.campaigns import CampaignCreateSchema


def _list_filters(search: str | None) -> list[ColumnElement[bool]]:
    """The list's and its total's filter: not deleted and, unless search is empty, matching.

    autoescape matches %, _ and the escape character literally.
    """
    filters = [Campaign.is_deleted == false()]
    if search:
        filters.append(
            or_(
                Campaign.name.icontains(search, autoescape=True),
                Campaign.subject.icontains(search, autoescape=True),
                Campaign.content.icontains(search, autoescape=True),
            )
        )
    return filters


def _active(campaign: Campaign) -> list[CampaignRecipient]:
    return [recipient for recipient in campaign.recipients if not recipient.is_deleted]


def _add(campaign: Campaign, clients: list[Client]) -> None:
    # The client object, not only its ID: the response reads it without a lazy load.
    for client in clients:
        campaign.recipients.append(CampaignRecipient(client=client, status=RecipientStatus.PENDING))


class CampaignRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, campaign_id: int) -> Campaign | None:
        query = select(Campaign).where(Campaign.id == campaign_id, Campaign.is_deleted == false())
        return await self._session.scalar(query)

    async def get_all(self, skip: int, limit: int, search: str | None) -> list[Campaign]:
        query = (
            select(Campaign)
            .where(*_list_filters(search))
            .order_by(Campaign.created_at.desc(), Campaign.id.desc())
            .offset(skip)
            .limit(limit)
        )
        campaigns = await self._session.scalars(query)
        return list(campaigns)

    async def count(self, search: str | None) -> int:
        query = select(func.count()).select_from(Campaign).where(*_list_filters(search))
        return (await self._session.execute(query)).scalar_one()

    async def load_clients(self, client_ids: list[int]) -> list[Client]:
        query = (
            select(Client)
            .where(Client.id.in_(client_ids), Client.is_deleted == false())
            .order_by(Client.id)
        )
        clients = await self._session.scalars(query)
        return list(clients)

    async def create(self, data: CampaignCreateSchema, clients: list[Client]) -> Campaign:
        campaign = Campaign(
            name=data.name,
            subject=data.subject,
            content=data.content,
            scheduled_for=data.scheduled_for,
            status=CampaignStatus.DRAFT,
            recipients=[],
        )
        _add(campaign, clients)
        self._session.add(campaign)
        await self._session.commit()
        return campaign

    async def update(
        self,
        campaign: Campaign,
        *,
        name: str | None = None,
        subject: str | None = None,
        content: str | None = None,
        scheduled_for: datetime | None = None,
        write_scheduled_for: bool = False,
    ) -> Campaign:
        """Write the given fields: a None text is kept, scheduled_for only with the flag."""
        if name is not None:
            campaign.name = name
        if subject is not None:
            campaign.subject = subject
        if content is not None:
            campaign.content = content
        if write_scheduled_for:
            campaign.scheduled_for = scheduled_for
        await self._session.commit()
        return campaign

    async def set_recipients(self, campaign: Campaign, clients: list[Client]) -> Campaign:
        now = utc_now()
        for recipient in _active(campaign):
            recipient.is_deleted = True
            recipient.deleted_at = now
        # The unit of work may insert before it updates: with a client in both sets, the
        # partial unique index would then fire.
        await self._session.flush()
        _add(campaign, clients)
        await self._session.commit()
        return campaign

    async def add_recipients(self, campaign: Campaign, clients: list[Client]) -> Campaign:
        present = {recipient.client_id for recipient in _active(campaign)}
        _add(campaign, [client for client in clients if client.id not in present])
        await self._session.commit()
        return campaign

    async def soft_delete(self, campaign: Campaign) -> Campaign:
        now = utc_now()
        campaign.is_deleted = True
        campaign.deleted_at = now
        for recipient in _active(campaign):
            recipient.is_deleted = True
            recipient.deleted_at = now
        await self._session.commit()
        return campaign
