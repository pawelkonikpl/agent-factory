"""Campaigns are edited only as drafts, and not deleted while sending. Campaigns are global (D5)."""

from app.errors import BusinessRuleError, NotFoundError
from app.models.campaign import Campaign, CampaignStatus, RecipientStatus
from app.models.client import Client
from app.repositories.campaign_repository import CampaignRepository
from app.schemas.base import Page
from app.schemas.campaigns import (
    CampaignCreateSchema,
    CampaignRecipientSchema,
    CampaignSchema,
    CampaignStatsSchema,
    CampaignUpdateSchema,
)


def _refuse_sending(campaign: Campaign) -> None:
    if campaign.status == CampaignStatus.SENDING:
        raise BusinessRuleError("Campaign is being sent")


def _rate(count: int, total: int) -> float:
    return round(count / total * 100, 2) if total else 0.0


class CampaignService:
    def __init__(self, campaigns: CampaignRepository) -> None:
        self._campaigns = campaigns

    async def get_all(self, skip: int, limit: int, search: str | None) -> Page[CampaignSchema]:
        campaigns = await self._campaigns.get_all(skip, limit, search)
        total = await self._campaigns.count(search)
        return Page[CampaignSchema](
            items=[self.to_schema(campaign) for campaign in campaigns], total=total
        )

    async def get_by_id(self, campaign_id: int) -> Campaign:
        campaign = await self._campaigns.get_by_id(campaign_id)
        if campaign is None:
            raise NotFoundError(f"Campaign {campaign_id} not found")
        return campaign

    async def create(self, data: CampaignCreateSchema) -> Campaign:
        # A scheduledFor is stored only; the campaign stays a draft (D6).
        clients = await self._load_clients(data.recipient_ids)
        return await self._campaigns.create(data, clients)

    async def update(self, campaign_id: int, data: CampaignUpdateSchema) -> Campaign:
        campaign = await self.get_by_id(campaign_id)
        _refuse_sending(campaign)
        if campaign.status != CampaignStatus.DRAFT:
            raise BusinessRuleError("Only draft campaigns can be modified")
        # Resolved before any write, so unknown clients leave the campaign unchanged.
        clients = None
        if data.recipient_ids is not None:
            clients = await self._load_clients(data.recipient_ids)
        campaign = await self._campaigns.update(
            campaign,
            name=data.name,
            subject=data.subject,
            content=data.content,
            scheduled_for=data.scheduled_for,
            # An explicit null clears the date; an omitted one keeps it.
            write_scheduled_for="scheduled_for" in data.model_fields_set,
        )
        if clients is not None:
            campaign = await self._campaigns.set_recipients(campaign, clients)
        return campaign

    async def delete(self, campaign_id: int) -> None:
        campaign = await self.get_by_id(campaign_id)
        _refuse_sending(campaign)
        await self._campaigns.soft_delete(campaign)

    async def add_recipients(self, campaign_id: int, client_ids: list[int]) -> Campaign:
        campaign = await self.get_by_id(campaign_id)
        if campaign.status != CampaignStatus.DRAFT:
            raise BusinessRuleError("Only draft campaigns can have recipients added")
        clients = await self._load_clients(client_ids)
        return await self._campaigns.add_recipients(campaign, clients)

    def to_schema(self, campaign: Campaign) -> CampaignSchema:
        recipients = sorted(
            (recipient for recipient in campaign.recipients if not recipient.is_deleted),
            key=lambda recipient: recipient.id,
        )
        return CampaignSchema(
            id=campaign.id,
            name=campaign.name,
            subject=campaign.subject,
            content=campaign.content,
            status=campaign.status,
            sent_at=campaign.sent_at,
            scheduled_for=campaign.scheduled_for,
            created_at=campaign.created_at,
            updated_at=campaign.updated_at,
            recipients=[
                CampaignRecipientSchema(
                    id=recipient.id,
                    client_id=recipient.client_id,
                    client_name=recipient.client.company_name,
                    client_email=recipient.client.primary_email,
                    status=recipient.status,
                    sent_at=recipient.sent_at,
                    error=recipient.error,
                )
                for recipient in recipients
            ],
            stats=self.compute_stats(campaign),
        )

    def compute_stats(self, campaign: Campaign) -> CampaignStatsSchema:
        statuses = [
            recipient.status for recipient in campaign.recipients if not recipient.is_deleted
        ]
        total = len(statuses)
        sent = statuses.count(RecipientStatus.SENT)
        failed = statuses.count(RecipientStatus.FAILED)
        return CampaignStatsSchema(
            total=total,
            sent=sent,
            failed=failed,
            pending=statuses.count(RecipientStatus.PENDING),
            bounced=statuses.count(RecipientStatus.BOUNCED),
            # Bounced recipients count in total, in neither numerator (the contract's formulas).
            progress_percentage=_rate(sent + failed, total),
            success_rate=_rate(sent, total),
        )

    async def _load_clients(self, client_ids: list[int]) -> list[Client]:
        # Duplicate IDs are not an error (W-26); unknown and deleted ones are.
        requested = set(client_ids)
        clients = await self._campaigns.load_clients(sorted(requested))
        missing = requested - {client.id for client in clients}
        if missing:
            ids = ", ".join(str(client_id) for client_id in sorted(missing))
            raise BusinessRuleError(f"Clients not found: {ids}")
        return clients
