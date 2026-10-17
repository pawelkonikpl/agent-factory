from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.errors import BusinessRuleError, NotFoundError
from app.models.campaign import Campaign
from app.models.client import Client
from app.models.email import Email, EmailStatus
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.client_repository import ClientRepository
from app.repositories.config_repository import ConfigRepository
from app.repositories.email_repository import EmailRepository
from app.schemas.campaigns import CampaignCreateSchema, CampaignUpdateSchema
from app.schemas.clients import ClientCreateSchema
from app.schemas.emails import EmailFilters, EmailStatsSchema, EmailUpdateSchema
from app.schemas.smtp_config import SmtpConfigUpdateSchema
from app.services.campaign_service import CampaignService
from app.services.client_service import ClientService
from app.services.email_service import EmailService
from app.services.encryption import EncryptionService
from app.services.smtp_config_service import SmtpConfigService
from app.services.smtp_sender import SendResult
from tests.conftest import FakeSenders

USER = "alice"
NO_SMTP = "SMTP configuration not found. Please configure SMTP settings first."


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def repository(session: AsyncSession) -> EmailRepository:
    return EmailRepository(session)


@pytest.fixture
def senders() -> FakeSenders:
    return FakeSenders()


@pytest.fixture
async def smtp_configs(session: AsyncSession) -> SmtpConfigService:
    """SMTP settings saved for USER, none for anyone else."""
    configs = SmtpConfigService(
        ConfigRepository(session, EncryptionService(EncryptionService.generate_key()))
    )
    settings = {"smtp_server": "smtp.example.com", "smtp_port": 587, "smtp_use_tls": True}
    await configs.update_smtp_config(USER, SmtpConfigUpdateSchema.model_validate(settings))
    return configs


@pytest.fixture
def service(
    repository: EmailRepository, smtp_configs: SmtpConfigService, senders: FakeSenders
) -> EmailService:
    return EmailService(repository, smtp_configs, senders)


@pytest.fixture
def campaigns(session: AsyncSession) -> CampaignService:
    return CampaignService(CampaignRepository(session))


@pytest.fixture
def clients(session: AsyncSession) -> ClientService:
    return ClientService(ClientRepository(session))


@dataclass
class Log:
    """Two campaigns, two clients, and a way to add emails between them."""

    repository: EmailRepository
    session: AsyncSession
    autumn: Campaign
    winter: Campaign
    acme: Client
    beta: Client

    async def add(
        self,
        campaign: Campaign | None = None,
        client: Client | None = None,
        subject: str = "Nowości",
        **fields: Any,
    ) -> Email:
        client = client or self.acme
        email = await self.repository.create(
            campaign=campaign or self.autumn,
            client=client,
            recipient_email=client.primary_email,
            subject=subject,
            body="Dzień dobry",
        )
        for name, value in fields.items():
            setattr(email, name, value)
        await self.session.commit()
        return email


async def add_client(clients: ClientService, company_name: str) -> Client:
    email = f"biuro@{company_name.lower()}.example"
    data = ClientCreateSchema.model_validate({"company_name": company_name, "primary_email": email})
    return await clients.create(data)


async def add_campaign(campaigns: CampaignService, name: str) -> Campaign:
    data = CampaignCreateSchema.model_validate(
        {"name": name, "subject": "Nowości", "content": "Dzień dobry"}
    )
    return await campaigns.create(data)


@pytest.fixture
async def log(
    repository: EmailRepository,
    session: AsyncSession,
    campaigns: CampaignService,
    clients: ClientService,
) -> Log:
    return Log(
        repository=repository,
        session=session,
        autumn=await add_campaign(campaigns, "Jesień"),
        winter=await add_campaign(campaigns, "Zima"),
        acme=await add_client(clients, "Acme"),
        beta=await add_client(clients, "Beta"),
    )


async def listed_ids(service: EmailService, **filters: Any) -> list[int]:
    page = await service.get_all(EmailFilters(**filters), 0, 100)
    return [email.id for email in page.items]


async def reload(service: EmailService, session: AsyncSession, email_id: int) -> Email:
    """The email as stored, not the object already in the session."""
    session.expunge_all()
    return await service.get_by_id(email_id)


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, 0, tzinfo=UTC)


async def test_create_stores_a_pending_email_with_the_snapshot(
    service: EmailService, session: AsyncSession, log: Log
) -> None:
    email = await log.add(subject="Jesienne nowości")

    stored = await reload(service, session, email.id)
    assert stored.status == EmailStatus.PENDING
    assert (stored.campaign_id, stored.client_id) == (log.autumn.id, log.acme.id)
    assert stored.recipient_email == "biuro@acme.example"
    assert (stored.subject, stored.body) == ("Jesienne nowości", "Dzień dobry")
    assert (stored.retry_count, stored.max_retries) == (0, 3)
    assert stored.sent_at is None
    assert stored.error_message is None


async def test_get_returns_the_email_as_a_schema(service: EmailService, log: Log) -> None:
    email = await log.add()

    schema = service.to_schema(await service.get_by_id(email.id))

    assert schema.id == email.id
    assert (schema.client_name, schema.campaign_name) == ("Acme", "Jesień")
    assert (schema.subject, schema.content) == ("Nowości", "Dzień dobry")
    assert schema.status == EmailStatus.PENDING


async def test_unknown_or_deleted_email_is_not_found(service: EmailService, log: Log) -> None:
    email = await log.add()
    await service.delete(email.id)
    unknown = email.id + 1000

    for email_id in (unknown, email.id):
        with pytest.raises(NotFoundError) as error:
            await service.get_by_id(email_id)
        assert str(error.value) == f"Email {email_id} not found"


async def test_list_filters_by_campaign(service: EmailService, log: Log) -> None:
    autumn = await log.add(log.autumn)
    await log.add(log.winter)

    assert await listed_ids(service, campaign_id=log.autumn.id) == [autumn.id]


async def test_list_filters_by_client(service: EmailService, log: Log) -> None:
    await log.add(client=log.acme)
    beta = await log.add(client=log.beta)

    assert await listed_ids(service, client_id=log.beta.id) == [beta.id]


async def test_list_filters_by_status(service: EmailService, log: Log) -> None:
    sent = await log.add(status=EmailStatus.SENT)
    await log.add(status=EmailStatus.FAILED)
    await log.add()

    assert await listed_ids(service, status=EmailStatus.SENT) == [sent.id]


async def test_list_filters_by_an_inclusive_date_range_on_created_at(
    service: EmailService, log: Log
) -> None:
    await log.add(created_at=at(1))
    first = await log.add(created_at=at(2))
    second = await log.add(created_at=at(3))
    await log.add(created_at=at(4))

    assert await listed_ids(service, from_date=at(2), to_date=at(3)) == [second.id, first.id]
    assert await listed_ids(service, from_date=at(4, 0)) == (
        await listed_ids(service, from_date=at(3, 13))
    )
    assert len(await listed_ids(service, to_date=at(2))) == 2


async def test_list_filters_by_has_error(service: EmailService, log: Log) -> None:
    failed = await log.add(error_message="Connection refused")
    clean = await log.add()

    assert await listed_ids(service, has_error=True) == [failed.id]
    assert await listed_ids(service, has_error=False) == [clean.id]


async def test_list_search_matches_recipient_subject_client_and_campaign(
    service: EmailService, log: Log
) -> None:
    by_client = await log.add(log.autumn, log.beta, subject="Oferta")
    by_campaign = await log.add(log.winter, log.acme, subject="Oferta")
    by_subject = await log.add(log.autumn, log.acme, subject="Rabat 50% dla stałych klientów")
    by_recipient = await log.add(
        log.autumn, log.acme, subject="Oferta", recipient_email="x@q.example"
    )

    assert await listed_ids(service, search="BETA") == [by_client.id]
    assert await listed_ids(service, search="zIMa") == [by_campaign.id]
    assert await listed_ids(service, search="50%") == [by_subject.id]
    assert await listed_ids(service, search="%") == [by_subject.id]
    assert await listed_ids(service, search="Q.EXAMPLE") == [by_recipient.id]
    assert len(await listed_ids(service, search="")) == 4
    assert len(await listed_ids(service, search=None)) == 4


async def test_list_is_ordered_by_created_at_then_id_descending(
    service: EmailService, log: Log
) -> None:
    old = await log.add(created_at=at(1))
    first = await log.add(created_at=at(2))
    second = await log.add(created_at=at(2))

    assert await listed_ids(service) == [second.id, first.id, old.id]


async def test_total_ignores_skip_and_limit_and_honours_the_filters(
    service: EmailService, log: Log
) -> None:
    for _ in range(3):
        await log.add(log.autumn)
    await log.add(log.winter)

    page = await service.get_all(EmailFilters(campaign_id=log.autumn.id), 1, 1)

    assert len(page.items) == 1
    assert page.total == 3
    assert (await service.get_all(EmailFilters(), 0, 2)).total == 4


async def test_failed_list_is_optionally_by_campaign(service: EmailService, log: Log) -> None:
    autumn = await log.add(log.autumn, status=EmailStatus.FAILED)
    winter = await log.add(log.winter, status=EmailStatus.FAILED)
    await log.add(log.autumn, status=EmailStatus.SENT)

    assert [email.id for email in await service.get_failed(None)] == [winter.id, autumn.id]
    assert [email.id for email in await service.get_failed(log.autumn.id)] == [autumn.id]


async def test_by_campaign_lists_newest_first_with_skip_and_limit(
    service: EmailService, log: Log
) -> None:
    old = await log.add(log.autumn, created_at=at(1))
    new = await log.add(log.autumn, created_at=at(2))
    await log.add(log.winter)

    assert [email.id for email in await service.get_by_campaign(log.autumn.id, 0, 100)] == [
        new.id,
        old.id,
    ]
    assert [email.id for email in await service.get_by_campaign(log.autumn.id, 1, 1)] == [old.id]


async def test_by_client_lists_newest_first_with_skip_and_limit(
    service: EmailService, log: Log
) -> None:
    old = await log.add(client=log.beta, created_at=at(1))
    new = await log.add(client=log.beta, created_at=at(2))
    await log.add(client=log.acme)

    assert [email.id for email in await service.get_by_client(log.beta.id, 0, 100)] == [
        new.id,
        old.id,
    ]
    assert [email.id for email in await service.get_by_client(log.beta.id, 0, 1)] == [new.id]


async def test_update_changes_only_the_given_fields(
    service: EmailService, session: AsyncSession, log: Log
) -> None:
    email = await log.add(smtp_response="250 OK")
    data = EmailUpdateSchema.model_validate(
        {"status": "sent", "sentAt": "2026-10-10T13:03:00Z", "errorCode": None}
    )

    await service.update(email.id, data)

    stored = await reload(service, session, email.id)
    assert stored.status == EmailStatus.SENT
    assert stored.sent_at == datetime(2026, 10, 10, 13, 3, tzinfo=UTC)
    assert stored.smtp_response == "250 OK"
    assert stored.subject == "Nowości"
    assert stored.error_code is None


async def test_update_with_an_invalid_status_is_rejected_and_writes_nothing(
    service: EmailService, session: AsyncSession, log: Log
) -> None:
    email = await log.add()
    data = EmailUpdateSchema.model_validate({"status": "bogus", "errorMessage": "Nie"})

    with pytest.raises(BusinessRuleError) as error:
        await service.update(email.id, data)

    assert str(error.value) == "Invalid email status: bogus"
    stored = await reload(service, session, email.id)
    assert stored.status == EmailStatus.PENDING
    assert stored.error_message is None


async def test_soft_delete_hides_the_email_from_get_lists_and_totals(
    service: EmailService, session: AsyncSession, log: Log
) -> None:
    email = await log.add(status=EmailStatus.FAILED)
    kept = await log.add()

    await service.delete(email.id)

    with pytest.raises(NotFoundError):
        await service.get_by_id(email.id)
    page = await service.get_all(EmailFilters(), 0, 100)
    assert ([item.id for item in page.items], page.total) == ([kept.id], 1)
    assert await service.get_failed(None) == []
    assert [item.id for item in await service.get_by_campaign(log.autumn.id, 0, 100)] == [kept.id]
    deleted_at = await session.scalar(
        text("SELECT deleted_at FROM emails WHERE id = :id"), {"id": email.id}
    )
    assert deleted_at is not None


async def test_mark_opened_and_clicked_set_the_time_and_keep_the_status(
    service: EmailService, log: Log
) -> None:
    email = await log.add(status=EmailStatus.SENT, opened_at=at(1))
    before = datetime.now(UTC)

    opened = await service.mark_opened(email.id)
    clicked = await service.mark_clicked(email.id)

    assert opened.opened_at is not None and opened.opened_at >= before
    assert clicked.clicked_at is not None and clicked.clicked_at >= before
    assert clicked.status == EmailStatus.SENT
    with pytest.raises(NotFoundError, match=f"Email {email.id + 1000} not found"):
        await service.mark_clicked(email.id + 1000)


async def test_get_for_recipient_returns_the_newest_email_of_the_pair(
    repository: EmailRepository, log: Log
) -> None:
    await log.add(log.autumn, log.acme, created_at=at(1))
    newest = await log.add(log.autumn, log.acme, created_at=at(2))
    await log.add(log.winter, log.acme)

    found = await repository.get_for_recipient(log.autumn.id, log.acme.id)

    assert found is not None and found.id == newest.id
    assert await repository.get_for_recipient(log.autumn.id, log.beta.id) is None


async def test_schema_reads_the_snapshot_not_the_campaigns_current_text(
    service: EmailService, campaigns: CampaignService, session: AsyncSession, log: Log
) -> None:
    email = await log.add(subject="Nowości")
    changed = CampaignUpdateSchema.model_validate({"subject": "Zmieniony", "content": "Inna"})
    await campaigns.update(log.autumn.id, changed)

    schema = service.to_schema(await reload(service, session, email.id))

    assert (schema.subject, schema.content) == ("Nowości", "Dzień dobry")


async def test_resend_success_marks_the_email_sent_and_counts_the_retry(
    service: EmailService, senders: FakeSenders, session: AsyncSession, log: Log
) -> None:
    email = await log.add(status=EmailStatus.FAILED, error_message="SMTP error: earlier")

    await service.resend(email.id, USER)

    stored = await reload(service, session, email.id)
    assert stored.status == EmailStatus.SENT
    assert stored.sent_at is not None
    assert (stored.smtp_message_id, stored.error_message) == ("<1@test>", None)
    assert stored.retry_count == 1
    assert senders.sent == [("biuro@acme.example", "Nowości", "Dzień dobry")]
    assert [(c.smtp_server, c.smtp_port) for c in senders.configs] == [("smtp.example.com", 587)]


@pytest.mark.parametrize("sent_at", [None, at(1)], ids=["never-sent", "sent-before"])
async def test_resend_failure_marks_the_email_failed_and_keeps_sent_at(
    service: EmailService,
    senders: FakeSenders,
    session: AsyncSession,
    log: Log,
    sent_at: datetime | None,
) -> None:
    senders.result = SendResult(success=False, smtp_message_id=None, error="SMTP error: boom")
    email = await log.add(status=EmailStatus.SENT, sent_at=sent_at, smtp_message_id="<0@test>")

    await service.resend(email.id, USER)

    stored = await reload(service, session, email.id)
    assert stored.status == EmailStatus.FAILED
    assert stored.sent_at == sent_at
    assert (stored.smtp_message_id, stored.error_message) == (None, "SMTP error: boom")
    assert stored.retry_count == 1


async def test_resend_without_smtp_settings_is_rejected_and_sends_nothing(
    service: EmailService, senders: FakeSenders, session: AsyncSession, log: Log
) -> None:
    email = await log.add(status=EmailStatus.FAILED, error_message="SMTP error: earlier")
    before = service.to_schema(await reload(service, session, email.id))

    with pytest.raises(BusinessRuleError) as error:
        await service.resend(email.id, "bob")

    assert str(error.value) == NO_SMTP
    assert (senders.configs, senders.sent) == ([], [])
    assert service.to_schema(await reload(service, session, email.id)) == before


async def test_resend_of_an_unknown_or_deleted_email_is_not_found(
    service: EmailService, senders: FakeSenders, log: Log
) -> None:
    email = await log.add()
    await service.delete(email.id)
    unknown = email.id + 1000

    for email_id in (unknown, email.id):
        with pytest.raises(NotFoundError) as error:
            await service.resend(email_id, USER)
        assert str(error.value) == f"Email {email_id} not found"
    assert senders.sent == []


async def test_resend_sends_the_snapshot_not_the_campaigns_current_text(
    service: EmailService, campaigns: CampaignService, senders: FakeSenders, log: Log
) -> None:
    email = await log.add(subject="Nowości")
    changed = CampaignUpdateSchema.model_validate({"subject": "Zmieniony", "content": "Inna"})
    await campaigns.update(log.autumn.id, changed)

    await service.resend(email.id, USER)

    assert senders.sent == [("biuro@acme.example", "Nowości", "Dzień dobry")]


async def test_resend_leaves_the_campaign_its_recipients_and_other_emails_unchanged(
    service: EmailService, campaigns: CampaignService, session: AsyncSession, log: Log
) -> None:
    await campaigns.add_recipients(log.autumn.id, [log.acme.id, log.beta.id])
    email = await log.add(status=EmailStatus.FAILED)
    other = await log.add(client=log.beta, status=EmailStatus.FAILED)
    session.expunge_all()
    campaign_before = campaigns.to_schema(await campaigns.get_by_id(log.autumn.id))
    other_before = service.to_schema(await service.get_by_id(other.id))

    await service.resend(email.id, USER)

    session.expunge_all()
    assert campaigns.to_schema(await campaigns.get_by_id(log.autumn.id)) == campaign_before
    assert service.to_schema(await service.get_by_id(other.id)) == other_before


async def add_stats_rows(log: Log) -> None:
    # Autumn: 6 live rows. Winter: 2 live rows. One deleted autumn row counts nowhere.
    await log.add(log.autumn, status=EmailStatus.SENT, delivered_at=at(1), opened_at=at(1))
    await log.add(
        log.autumn,
        status=EmailStatus.SENT,
        delivered_at=at(1),
        opened_at=at(1),
        clicked_at=at(1),
    )
    await log.add(log.autumn, status=EmailStatus.SENT, delivered_at=at(1))
    await log.add(log.autumn, status=EmailStatus.FAILED)
    await log.add(log.autumn, status=EmailStatus.BOUNCED)
    await log.add(log.autumn)
    await log.add(
        log.autumn,
        status=EmailStatus.SENT,
        delivered_at=at(1),
        opened_at=at(1),
        is_deleted=True,
        deleted_at=at(2),
    )
    await log.add(log.winter, status=EmailStatus.SENT, delivered_at=at(1), opened_at=at(1))
    await log.add(log.winter, status=EmailStatus.DEFERRED)


async def test_stats_for_one_campaign_match_hand_computed_counts_and_rates(
    service: EmailService, log: Log
) -> None:
    await add_stats_rows(log)

    stats = await service.get_stats(log.autumn.id)

    assert stats == EmailStatsSchema(
        total=6,
        pending=1,
        sending=0,
        sent=3,
        failed=1,
        bounced=1,
        rejected=0,
        deferred=0,
        delivered=3,
        opened=2,
        clicked=1,
        delivery_rate=50.0,
        open_rate=66.67,
        click_rate=33.33,
        bounce_rate=16.67,
    )


async def test_stats_over_all_campaigns_match_hand_computed_counts_and_rates(
    service: EmailService, log: Log
) -> None:
    await add_stats_rows(log)

    stats = await service.get_stats(None)

    assert stats == EmailStatsSchema(
        total=8,
        pending=1,
        sending=0,
        sent=4,
        failed=1,
        bounced=1,
        rejected=0,
        deferred=1,
        delivered=4,
        opened=3,
        clicked=1,
        delivery_rate=50.0,
        open_rate=75.0,
        click_rate=25.0,
        bounce_rate=12.5,
    )


async def test_stats_without_rows_are_zero_with_zero_rates(service: EmailService, log: Log) -> None:
    zero = EmailStatsSchema.model_validate(
        dict.fromkeys(EmailStatsSchema.model_fields, 0)
        | dict.fromkeys(["delivery_rate", "open_rate", "click_rate", "bounce_rate"], 0.0)
    )

    for campaign_id in (None, log.autumn.id):
        stats = await service.get_stats(campaign_id)
        assert stats == zero
        assert {type(stats.open_rate), type(stats.delivery_rate)} == {float}


async def test_stats_with_no_sent_emails_have_zero_open_and_click_rates(
    service: EmailService, log: Log
) -> None:
    await log.add(status=EmailStatus.FAILED, opened_at=at(1))

    stats = await service.get_stats(None)

    assert (stats.total, stats.sent, stats.opened) == (1, 0, 1)
    assert (stats.open_rate, stats.click_rate) == (0.0, 0.0)


async def test_status_is_stored_by_value_and_checked_by_the_database(
    session: AsyncSession, log: Log
) -> None:
    email = await log.add()

    stored = await session.scalar(
        text("SELECT status FROM emails WHERE id = :id"), {"id": email.id}
    )

    assert stored == "pending"
    with pytest.raises(IntegrityError, match="ck_emails_email_status"):
        await session.execute(
            text("UPDATE emails SET status = 'bogus' WHERE id = :id"), {"id": email.id}
        )


@pytest.mark.parametrize(
    ("table", "constraint"),
    [("campaigns", "fk_emails_campaign_id_campaigns"), ("clients", "fk_emails_client_id_clients")],
)
async def test_the_database_refuses_to_delete_a_campaign_or_client_with_emails(
    session: AsyncSession, log: Log, table: str, constraint: str
) -> None:
    email_id = (await log.add()).id
    owner_id = log.autumn.id if table == "campaigns" else log.acme.id

    with pytest.raises(IntegrityError, match=constraint):
        await session.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": owner_id})
    await session.rollback()

    remaining = await session.scalar(
        text("SELECT count(*) FROM emails WHERE id = :id"), {"id": email_id}
    )
    assert remaining == 1
