"""Sending a campaign (api-contract.md §4): the request starts it, a background task sends."""

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.errors import BusinessRuleError, NotFoundError
from app.models.base import utc_now
from app.models.campaign import Campaign, CampaignRecipient, CampaignStatus, RecipientStatus
from app.models.email import Email, EmailStatus
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.email_repository import EmailRepository
from app.services.email_content import render_content
from app.services.smtp_config_service import SmtpConfig, SmtpConfigService
from app.services.smtp_sender import EmailItem, EmailSenderFactory, SendResult, send_many

logger = logging.getLogger(__name__)

CLIENT_INACTIVE = "Client is inactive"
MAX_RETRIES_EXCEEDED = "Maximum retries exceeded"
SENDING_INTERRUPTED = "Sending interrupted"


@dataclass(frozen=True, eq=False)
class RecipientEmail(EmailItem):
    recipient: CampaignRecipient
    # The pair's existing log row, None before the first attempt.
    email: Email | None


def _active(campaign: Campaign) -> list[CampaignRecipient]:
    return [recipient for recipient in campaign.recipients if not recipient.is_deleted]


def _pending(campaign: Campaign) -> list[CampaignRecipient]:
    return [
        recipient for recipient in _active(campaign) if recipient.status == RecipientStatus.PENDING
    ]


def _fail(recipient: CampaignRecipient, error: str) -> None:
    recipient.status = RecipientStatus.FAILED
    recipient.error = error


def _finish(campaign: Campaign) -> None:
    """§4 step 7: failed while any recipient is failed, else sent."""
    if any(recipient.status == RecipientStatus.FAILED for recipient in _active(campaign)):
        campaign.status = CampaignStatus.FAILED
    else:
        campaign.status = CampaignStatus.SENT
        campaign.sent_at = utc_now()


class CampaignSender:
    """start and recover_interrupted use the given session; run opens its own from sessions."""

    def __init__(
        self,
        session: AsyncSession,
        smtp_configs: SmtpConfigService,
        sessions: async_sessionmaker[AsyncSession],
        email_sender_factory: EmailSenderFactory,
    ) -> None:
        self._session = session
        self._campaigns = CampaignRepository(session)
        self._smtp_configs = smtp_configs
        self._sessions = sessions
        self._email_sender_factory = email_sender_factory

    async def start(
        self, campaign_id: int, user_sub: str, retry_recipient_ids: list[int] | None = None
    ) -> tuple[Campaign, SmtpConfig]:
        """§4 checks 1 to 4, then step 5. retry_recipient_ids is for the resend (API-12)."""
        campaign = await self._campaigns.get_by_id(campaign_id)
        if campaign is None:
            raise NotFoundError(f"Campaign {campaign_id} not found")
        if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.FAILED):
            raise _not_sendable(campaign.status)
        if campaign.status == CampaignStatus.DRAFT:
            chosen = _pending(campaign)
            reset = []
        else:
            chosen = [
                recipient
                for recipient in _active(campaign)
                if recipient.status == RecipientStatus.FAILED
            ]
            reset = chosen
        if not chosen:
            raise BusinessRuleError("Campaign has no pending recipients")
        smtp_config = await self._smtp_configs.get_smtp_config_for_sending(user_sub)
        if smtp_config is None:
            raise BusinessRuleError(
                "SMTP configuration not found. Please configure SMTP settings first."
            )
        if not await self._campaigns.start_sending(campaign, reset):
            # Another request started it after the checks.
            stored = await self._campaigns.get_status(campaign_id)
            raise _not_sendable(stored)
        return campaign, smtp_config

    async def run(self, campaign_id: int, smtp_config: SmtpConfig, max_concurrent: int) -> None:
        """The background task. It never raises: an escaping error would reach the server."""
        try:
            async with self._sessions() as session:
                await self._send(session, campaign_id, smtp_config, max_concurrent)
        except Exception as exc:
            logger.exception("Sending campaign %s failed", campaign_id)
            # A fresh session: the first may be unusable after the error.
            try:
                async with self._sessions() as session:
                    await self._fail_pending(session, campaign_id, f"Unexpected error: {exc}")
            except Exception:
                logger.exception("Could not mark campaign %s failed", campaign_id)

    async def recover_interrupted(self) -> None:
        """§4 step 8: finish the campaigns a restart left in sending."""
        for campaign in await self._campaigns.get_sending():
            for recipient in _pending(campaign):
                _fail(recipient, SENDING_INTERRUPTED)
            _finish(campaign)
            logger.warning("Campaign %s was interrupted, now %s", campaign.id, campaign.status)
        await self._session.commit()

    async def _send(
        self,
        session: AsyncSession,
        campaign_id: int,
        smtp_config: SmtpConfig,
        max_concurrent: int,
    ) -> None:
        campaign = await CampaignRepository(session).get_by_id(campaign_id)
        if campaign is None:
            raise NotFoundError(f"Campaign {campaign_id} not found")
        emails = EmailRepository(session)
        items: list[RecipientEmail] = []
        for recipient in _pending(campaign):
            client = recipient.client
            if not client.is_active or client.is_deleted:
                _fail(recipient, CLIENT_INACTIVE)
                continue
            email = await emails.get_for_recipient(campaign.id, client.id)
            if email is not None and email.retry_count >= email.max_retries:
                _fail(recipient, MAX_RETRIES_EXCEEDED)
                continue
            items.append(
                RecipientEmail(
                    to=client.primary_email,
                    subject=campaign.subject,
                    html_body=render_content(campaign.content, client),
                    recipient=recipient,
                    email=email,
                )
            )
        await session.commit()

        sender = self._email_sender_factory(smtp_config)
        # Only the sends run concurrently; every write holds the lock, so the session is
        # never used by two coroutines at once.
        lock = asyncio.Lock()

        async def on_result(item: RecipientEmail, result: SendResult) -> None:
            async with lock:
                _record(session, campaign, item, result)
                await session.commit()

        await send_many(sender, items, max_concurrent, on_result)
        _finish(campaign)
        await session.commit()

    async def _fail_pending(self, session: AsyncSession, campaign_id: int, error: str) -> None:
        campaign = await CampaignRepository(session).get_by_id(campaign_id)
        if campaign is None:
            return
        for recipient in _pending(campaign):
            _fail(recipient, error)
        campaign.status = CampaignStatus.FAILED
        await session.commit()


def _not_sendable(status: CampaignStatus | None) -> BusinessRuleError:
    value = None if status is None else status.value
    return BusinessRuleError(f"Campaign cannot be sent — current status: {value}")


def _record(
    session: AsyncSession, campaign: Campaign, item: RecipientEmail, result: SendResult
) -> None:
    """Write one attempt to the recipient and to the pair's Email row (W-17)."""
    recipient = item.recipient
    email = item.email
    if email is None:
        email = Email(campaign=campaign, client=recipient.client)
        session.add(email)
    else:
        email.retry_count += 1
    email.recipient_email = item.to
    email.subject = item.subject
    email.body = item.html_body
    if result.success:
        now = utc_now()
        recipient.status = RecipientStatus.SENT
        recipient.sent_at = now
        recipient.error = None
        email.status = EmailStatus.SENT
        email.sent_at = now
        email.smtp_message_id = result.smtp_message_id
        email.error_message = None
    else:
        recipient.status = RecipientStatus.FAILED
        recipient.error = result.error
        email.status = EmailStatus.FAILED
        email.error_message = result.error
