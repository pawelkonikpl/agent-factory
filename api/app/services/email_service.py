"""The email log: reads, filters, stats, manual updates and the single-email resend."""

from app.errors import BusinessRuleError, NotFoundError
from app.models.email import Email, EmailStatus
from app.repositories.email_repository import EmailRepository
from app.schemas.base import Page
from app.schemas.emails import EmailFilters, EmailSchema, EmailStatsSchema, EmailUpdateSchema
from app.services.smtp_config_service import SmtpConfigService
from app.services.smtp_sender import EmailSenderFactory


def _rate(count: int, total: int) -> float:
    return round(count / total * 100, 2) if total else 0.0


class EmailService:
    def __init__(
        self,
        emails: EmailRepository,
        smtp_configs: SmtpConfigService,
        sender_factory: EmailSenderFactory,
    ) -> None:
        self._emails = emails
        self._smtp_configs = smtp_configs
        self._sender_factory = sender_factory

    async def get_all(self, filters: EmailFilters, skip: int, limit: int) -> Page[EmailSchema]:
        emails = await self._emails.get_all(filters, skip, limit)
        total = await self._emails.count(filters)
        return Page[EmailSchema](items=[self.to_schema(email) for email in emails], total=total)

    async def get_by_campaign(self, campaign_id: int, skip: int, limit: int) -> list[EmailSchema]:
        emails = await self._emails.get_by_campaign(campaign_id, skip, limit)
        return [self.to_schema(email) for email in emails]

    async def get_by_client(self, client_id: int, skip: int, limit: int) -> list[EmailSchema]:
        emails = await self._emails.get_by_client(client_id, skip, limit)
        return [self.to_schema(email) for email in emails]

    async def get_failed(self, campaign_id: int | None) -> list[EmailSchema]:
        return [self.to_schema(email) for email in await self._emails.get_failed(campaign_id)]

    async def get_by_id(self, email_id: int) -> Email:
        email = await self._emails.get_by_id(email_id)
        if email is None:
            raise NotFoundError(f"Email {email_id} not found")
        return email

    async def update(self, email_id: int, data: EmailUpdateSchema) -> Email:
        email = await self.get_by_id(email_id)
        status = None
        if data.status is not None:
            # Checked before any write, so an invalid status leaves the email unchanged.
            if data.status not in EmailStatus:
                raise BusinessRuleError(f"Invalid email status: {data.status}")
            status = EmailStatus(data.status)
        return await self._emails.update(email, data, status)

    async def delete(self, email_id: int) -> None:
        email = await self.get_by_id(email_id)
        await self._emails.soft_delete(email)

    async def mark_opened(self, email_id: int) -> Email:
        return await self._emails.mark_opened(await self.get_by_id(email_id))

    async def mark_clicked(self, email_id: int) -> Email:
        return await self._emails.mark_clicked(await self.get_by_id(email_id))

    async def resend(self, email_id: int, user_sub: str) -> Email:
        """Send the stored snapshot once with the user's settings and record the result."""
        email = await self.get_by_id(email_id)
        config = await self._smtp_configs.get_smtp_config_for_sending(user_sub)
        if config is None:
            raise BusinessRuleError(
                "SMTP configuration not found. Please configure SMTP settings first."
            )
        sender = self._sender_factory(config)
        result = await sender.send(email.recipient_email, email.subject, email.body)
        return await self._emails.record_send(email, result)

    async def get_stats(self, campaign_id: int | None) -> EmailStatsSchema:
        counts = await self._emails.get_stats(campaign_id)
        return EmailStatsSchema(
            total=counts.total,
            pending=counts.pending,
            sending=counts.sending,
            sent=counts.sent,
            failed=counts.failed,
            bounced=counts.bounced,
            rejected=counts.rejected,
            deferred=counts.deferred,
            delivered=counts.delivered,
            opened=counts.opened,
            clicked=counts.clicked,
            # The contract's denominators: total, sent, sent, total.
            delivery_rate=_rate(counts.delivered, counts.total),
            open_rate=_rate(counts.opened, counts.sent),
            click_rate=_rate(counts.clicked, counts.sent),
            bounce_rate=_rate(counts.bounced, counts.total),
        )

    def to_schema(self, email: Email) -> EmailSchema:
        # subject and content are the snapshot sent, never the campaign's current text.
        return EmailSchema(
            id=email.id,
            campaign_id=email.campaign_id,
            client_id=email.client_id,
            recipient_email=email.recipient_email,
            client_name=email.client.company_name,
            campaign_name=email.campaign.name,
            subject=email.subject,
            content=email.body,
            status=email.status,
            sent_at=email.sent_at,
            delivered_at=email.delivered_at,
            opened_at=email.opened_at,
            clicked_at=email.clicked_at,
            bounced_at=email.bounced_at,
            error_message=email.error_message,
            error_code=email.error_code,
            retry_count=email.retry_count,
            max_retries=email.max_retries,
            smtp_message_id=email.smtp_message_id,
            smtp_response=email.smtp_response,
            created_at=email.created_at,
            updated_at=email.updated_at,
        )
