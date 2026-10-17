from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.errors import BusinessRuleError, NotFoundError
from app.main import create_app
from app.models.base import utc_now
from app.models.campaign import Campaign, CampaignStatus, RecipientStatus
from app.models.client import Client
from app.models.email import Email, EmailStatus
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.client_repository import ClientRepository
from app.repositories.config_repository import ConfigRepository
from app.repositories.email_repository import EmailRepository
from app.schemas.campaigns import CampaignCreateSchema
from app.schemas.clients import ClientCreateSchema
from app.schemas.smtp_config import SmtpConfigUpdateSchema
from app.services import campaign_sender
from app.services.campaign_sender import CampaignSender
from app.services.campaign_service import CampaignService
from app.services.client_service import ClientService
from app.services.encryption import EncryptionService
from app.services.smtp_config_service import SmtpConfig, SmtpConfigService
from app.services.smtp_sender import EmailSender, SendResult
from tests.conftest import FakeSenders

SMTP = SmtpConfig(
    smtp_server="localhost",
    smtp_port=2525,
    smtp_user="noreply@localhost",
    smtp_password=None,
    smtp_use_tls=False,
)


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def smtp_configs(session: AsyncSession) -> SmtpConfigService:
    encryption = EncryptionService(EncryptionService.generate_key())
    return SmtpConfigService(ConfigRepository(session, encryption))


@pytest.fixture
def senders() -> FakeSenders:
    return FakeSenders()


@pytest.fixture
def sender(
    session: AsyncSession,
    smtp_configs: SmtpConfigService,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
) -> CampaignSender:
    return CampaignSender(session, smtp_configs, session_factory, senders)


async def save_smtp(smtp_configs: SmtpConfigService) -> None:
    payload = SmtpConfigUpdateSchema.model_validate(
        {"smtp_server": "localhost", "smtp_port": 2525, "smtp_use_tls": False}
    )
    await smtp_configs.update_smtp_config("alice", payload)


async def add_client(session: AsyncSession, company_name: str, email: str | None = None) -> Client:
    email = email or f"biuro@{company_name.lower()}.example"
    data = ClientCreateSchema.model_validate({"company_name": company_name, "primary_email": email})
    return await ClientService(ClientRepository(session)).create(data)


async def create(
    session: AsyncSession, clients: list[Client], content: str = "Dzień dobry {name}"
) -> Campaign:
    data = CampaignCreateSchema.model_validate(
        {
            "name": "Jesień",
            "subject": "Nowości",
            "content": content,
            "recipient_ids": [client.id for client in clients],
        }
    )
    return await CampaignService(CampaignRepository(session)).create(data)


async def stored(
    session_factory: async_sessionmaker[AsyncSession], campaign_id: int
) -> tuple[Campaign, dict[str, Email]]:
    """The campaign and its emails by address, as stored, read in a fresh session."""
    async with session_factory() as fresh:
        campaign = await fresh.scalar(select(Campaign).where(Campaign.id == campaign_id))
        assert campaign is not None
        emails = await fresh.scalars(select(Email).where(Email.campaign_id == campaign_id))
        return campaign, {email.recipient_email: email for email in emails}


def recipient_states(campaign: Campaign) -> dict[str, tuple[RecipientStatus, str | None]]:
    return {
        recipient.client.primary_email: (recipient.status, recipient.error)
        for recipient in campaign.recipients
        if not recipient.is_deleted
    }


def addresses(senders: FakeSenders) -> list[str]:
    return sorted(to for to, _, _ in senders.sent)


async def test_start_moves_a_draft_to_sending_and_returns_the_smtp_config(
    sender: CampaignSender,
    session: AsyncSession,
    smtp_configs: SmtpConfigService,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
) -> None:
    await save_smtp(smtp_configs)
    campaign = await create(session, [await add_client(session, "Acme")])

    started, smtp_config = await sender.start(campaign.id, "alice")

    assert started.status == CampaignStatus.SENDING
    assert smtp_config == SmtpConfig(
        smtp_server="localhost",
        smtp_port=2525,
        smtp_user=None,
        smtp_password=None,
        smtp_use_tls=False,
    )
    saved, _ = await stored(session_factory, campaign.id)
    assert saved.status == CampaignStatus.SENDING
    assert senders.sent == []


async def test_start_on_a_failed_campaign_resets_only_its_failed_recipients(
    sender: CampaignSender,
    session: AsyncSession,
    smtp_configs: SmtpConfigService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await save_smtp(smtp_configs)
    clients = [await add_client(session, name) for name in ("Acme", "Beta", "Gamma")]
    campaign = await create(session, clients)
    sent, failed, deleted = campaign.recipients
    sent.status = RecipientStatus.SENT
    failed.status = RecipientStatus.FAILED
    failed.error = "SMTP error: busy"
    deleted.status = RecipientStatus.FAILED
    deleted.is_deleted = True
    campaign.status = CampaignStatus.FAILED
    await session.commit()

    await sender.start(campaign.id, "alice")

    saved, _ = await stored(session_factory, campaign.id)
    assert saved.status == CampaignStatus.SENDING
    assert recipient_states(saved) == {
        "biuro@acme.example": (RecipientStatus.SENT, None),
        "biuro@beta.example": (RecipientStatus.PENDING, None),
    }
    assert [r.status for r in saved.recipients if r.is_deleted] == [RecipientStatus.FAILED]


async def failed(session: AsyncSession) -> Campaign:
    """A failed campaign: Acme sent, Beta and Gamma failed."""
    clients = [await add_client(session, name) for name in ("Acme", "Beta", "Gamma")]
    campaign = await create(session, clients)
    sent, *failed = campaign.recipients
    sent.status = RecipientStatus.SENT
    sent.sent_at = utc_now()
    for recipient in failed:
        recipient.status = RecipientStatus.FAILED
        recipient.error = "SMTP error: busy"
    campaign.status = CampaignStatus.FAILED
    await session.commit()
    return campaign


async def test_start_with_ids_resets_only_the_chosen_failed_recipients(
    sender: CampaignSender,
    session: AsyncSession,
    smtp_configs: SmtpConfigService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await save_smtp(smtp_configs)
    campaign = await failed(session)
    _, beta, _ = campaign.recipients
    beta.sent_at = utc_now()
    await session.commit()

    started, _ = await sender.start(campaign.id, "alice", [beta.id, beta.id])

    assert started.status == CampaignStatus.SENDING
    saved, _ = await stored(session_factory, campaign.id)
    assert saved.status == CampaignStatus.SENDING
    assert recipient_states(saved) == {
        "biuro@acme.example": (RecipientStatus.SENT, None),
        "biuro@beta.example": (RecipientStatus.PENDING, None),
        "biuro@gamma.example": (RecipientStatus.FAILED, "SMTP error: busy"),
    }
    saved_beta = next(r for r in saved.recipients if r.id == beta.id)
    assert saved_beta.sent_at is None


async def test_start_with_ids_on_a_draft_raises(
    sender: CampaignSender, session: AsyncSession, smtp_configs: SmtpConfigService
) -> None:
    await save_smtp(smtp_configs)
    campaign = await create(session, [await add_client(session, "Acme")])

    for ids in ([campaign.recipients[0].id], []):
        with pytest.raises(BusinessRuleError) as raised:
            await sender.start(campaign.id, "alice", ids)
        assert str(raised.value) == "Only failed campaigns can be resent"


async def test_start_with_bad_ids_raises_and_changes_nothing(
    sender: CampaignSender,
    session: AsyncSession,
    smtp_configs: SmtpConfigService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await save_smtp(smtp_configs)
    campaign = await failed(session)
    acme, beta, gamma = campaign.recipients
    gamma.is_deleted = True
    other = await create(session, [await add_client(session, "Delta")])
    await session.commit()
    foreign = other.recipients[0].id
    cases = [
        (
            [999999, beta.id, foreign, gamma.id, acme.id, 999999],
            "Recipients not found in campaign: "
            + ", ".join(str(i) for i in sorted([gamma.id, foreign, 999999])),
        ),
        ([beta.id, acme.id, acme.id], f"Can only resend failed recipients: {acme.id}"),
        ([], "Campaign has no pending recipients"),
    ]

    for ids, message in cases:
        with pytest.raises(BusinessRuleError) as raised:
            await sender.start(campaign.id, "alice", ids)
        assert str(raised.value) == message

    saved, _ = await stored(session_factory, campaign.id)
    assert saved.status == CampaignStatus.FAILED
    assert recipient_states(saved) == {
        "biuro@acme.example": (RecipientStatus.SENT, None),
        "biuro@beta.example": (RecipientStatus.FAILED, "SMTP error: busy"),
    }


async def test_start_with_ids_checks_the_status_first(
    sender: CampaignSender, session: AsyncSession
) -> None:
    campaign = await failed(session)
    campaign.status = CampaignStatus.SENT
    await session.commit()

    with pytest.raises(BusinessRuleError) as raised:
        await sender.start(campaign.id, "alice", [999999])

    assert str(raised.value) == "Campaign cannot be sent — current status: sent"
    with pytest.raises(NotFoundError):
        await sender.start(999999, "alice", [999999])


async def test_start_that_loses_the_race_changes_nothing(
    sender: CampaignSender,
    session: AsyncSession,
    smtp_configs: SmtpConfigService,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await save_smtp(smtp_configs)
    campaign = await create(session, [await add_client(session, "Acme")])
    read_config = smtp_configs.get_smtp_config_for_sending

    async def read_config_then_lose_the_race(user_sub: str) -> SmtpConfig | None:
        # Another request starts the campaign after the checks, before the conditional update.
        async with session_factory() as other:
            await other.execute(
                text("UPDATE campaigns SET status = 'sending' WHERE id = :id"),
                {"id": campaign.id},
            )
            await other.commit()
        return await read_config(user_sub)

    monkeypatch.setattr(smtp_configs, "get_smtp_config_for_sending", read_config_then_lose_the_race)

    with pytest.raises(BusinessRuleError) as raised:
        await sender.start(campaign.id, "alice")

    assert str(raised.value) == "Campaign cannot be sent — current status: sending"
    saved, emails = await stored(session_factory, campaign.id)
    assert recipient_states(saved) == {"biuro@acme.example": (RecipientStatus.PENDING, None)}
    assert emails == {}
    assert senders.configs == []


async def test_run_skips_inactive_clients_and_recipients_past_their_retries(
    sender: CampaignSender,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
) -> None:
    acme, inactive, deleted, retried = [
        await add_client(session, name) for name in ("Acme", "Inactive", "Deleted", "Retried")
    ]
    campaign = await create(session, [acme, inactive, deleted, retried])
    inactive.is_active = False
    deleted.is_deleted = True
    email = await EmailRepository(session).create(
        campaign=campaign,
        client=retried,
        recipient_email=retried.primary_email,
        subject="Nowości",
        body="Wcześniej",
    )
    email.status = EmailStatus.FAILED
    email.retry_count = email.max_retries
    campaign.status = CampaignStatus.SENDING
    await session.commit()

    await sender.run(campaign.id, SMTP, 10)

    saved, emails = await stored(session_factory, campaign.id)
    assert recipient_states(saved) == {
        "biuro@acme.example": (RecipientStatus.SENT, None),
        "biuro@inactive.example": (RecipientStatus.FAILED, "Client is inactive"),
        "biuro@deleted.example": (RecipientStatus.FAILED, "Client is inactive"),
        "biuro@retried.example": (RecipientStatus.FAILED, "Maximum retries exceeded"),
    }
    assert saved.status == CampaignStatus.FAILED
    assert saved.sent_at is None
    assert addresses(senders) == ["biuro@acme.example"]
    assert set(emails) == {"biuro@acme.example", "biuro@retried.example"}
    unchanged = emails["biuro@retried.example"]
    assert (unchanged.status, unchanged.retry_count, unchanged.body) == (
        EmailStatus.FAILED,
        3,
        "Wcześniej",
    )


async def test_run_sends_the_rendered_body_and_writes_each_result(
    sender: CampaignSender,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
) -> None:
    acme = await add_client(session, "A<cme", "biuro@acme.example")
    beta = await add_client(session, "Beta")
    campaign = await create(session, [acme, beta], content="Dzień dobry {name},\n{email}")
    campaign.status = CampaignStatus.SENDING
    await session.commit()
    senders.failures = {beta.primary_email: "Recipient refused: no such user"}

    await sender.run(campaign.id, SMTP, 10)

    assert senders.configs == [SMTP]
    assert sorted(senders.sent) == [
        ("biuro@acme.example", "Nowości", "Dzień dobry A&lt;cme,<br>biuro@acme.example"),
        ("biuro@beta.example", "Nowości", "Dzień dobry Beta,<br>biuro@beta.example"),
    ]
    saved, emails = await stored(session_factory, campaign.id)
    assert recipient_states(saved) == {
        "biuro@acme.example": (RecipientStatus.SENT, None),
        "biuro@beta.example": (RecipientStatus.FAILED, "Recipient refused: no such user"),
    }
    sent, failed = emails["biuro@acme.example"], emails["biuro@beta.example"]
    assert (sent.status, sent.smtp_message_id, sent.error_message, sent.retry_count) == (
        EmailStatus.SENT,
        "<1@test>",
        None,
        0,
    )
    assert sent.sent_at is not None
    assert (failed.status, failed.error_message, failed.sent_at, failed.smtp_message_id) == (
        EmailStatus.FAILED,
        "Recipient refused: no such user",
        None,
        None,
    )
    assert saved.status == CampaignStatus.FAILED


async def test_run_sends_at_most_max_concurrent_at_once(
    sender: CampaignSender,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
) -> None:
    clients = [await add_client(session, f"Firma{number}") for number in range(6)]
    campaign = await create(session, clients)
    campaign.status = CampaignStatus.SENDING
    await session.commit()

    await sender.run(campaign.id, SMTP, 2)

    assert len(senders.sent) == 6
    assert senders.max_in_flight == 2
    saved, _ = await stored(session_factory, campaign.id)
    assert saved.status == CampaignStatus.SENT
    assert saved.sent_at is not None


async def test_a_send_that_raises_fails_only_its_recipient(
    sender: CampaignSender,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
) -> None:
    acme, beta = [await add_client(session, name) for name in ("Acme", "Beta")]
    campaign = await create(session, [acme, beta])
    campaign.status = CampaignStatus.SENDING
    await session.commit()
    senders.raises = {beta.primary_email}

    await sender.run(campaign.id, SMTP, 10)

    saved, _ = await stored(session_factory, campaign.id)
    assert recipient_states(saved) == {
        "biuro@acme.example": (RecipientStatus.SENT, None),
        "biuro@beta.example": (
            RecipientStatus.FAILED,
            "Unexpected error: boom for biuro@beta.example",
        ),
    }
    assert saved.status == CampaignStatus.FAILED


async def test_a_raising_sender_factory_fails_the_pending_recipients_and_the_campaign(
    session: AsyncSession,
    smtp_configs: SmtpConfigService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    def broken_factory(config: SmtpConfig) -> EmailSender:
        raise RuntimeError("no sender")

    sender = CampaignSender(session, smtp_configs, session_factory, broken_factory)
    campaign = await create(session, [await add_client(session, "Acme")])
    campaign.status = CampaignStatus.SENDING
    await session.commit()

    await sender.run(campaign.id, SMTP, 10)

    saved, emails = await stored(session_factory, campaign.id)
    assert recipient_states(saved) == {
        "biuro@acme.example": (RecipientStatus.FAILED, "Unexpected error: no sender")
    }
    assert saved.status == CampaignStatus.FAILED
    assert emails == {}


async def test_a_raising_result_write_fails_the_recipients_still_pending(
    sender: CampaignSender,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acme, beta = [await add_client(session, name) for name in ("Acme", "Beta")]
    campaign = await create(session, [acme, beta])
    campaign.status = CampaignStatus.SENDING
    await session.commit()
    record = campaign_sender._record

    def record_or_raise(
        session: AsyncSession,
        campaign: Campaign,
        item: campaign_sender.RecipientEmail,
        result: SendResult,
    ) -> None:
        if item.to == beta.primary_email:
            raise RuntimeError("write failed")
        record(session, campaign, item, result)

    monkeypatch.setattr(campaign_sender, "_record", record_or_raise)

    await sender.run(campaign.id, SMTP, 10)

    saved, _ = await stored(session_factory, campaign.id)
    assert recipient_states(saved) == {
        "biuro@acme.example": (RecipientStatus.SENT, None),
        "biuro@beta.example": (RecipientStatus.FAILED, "Unexpected error: write failed"),
    }
    assert saved.status == CampaignStatus.FAILED


async def test_a_failing_commit_is_recovered_in_a_fresh_session(
    sender: CampaignSender,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
) -> None:
    campaign = await create(session, [await add_client(session, "Acme")])
    campaign.status = CampaignStatus.SENDING
    await session.commit()
    # Longer than the smtp_message_id column: the commit fails in the database.
    senders.result = SendResult(success=True, smtp_message_id="x" * 300, error=None)

    await sender.run(campaign.id, SMTP, 10)

    saved, emails = await stored(session_factory, campaign.id)
    [(status, error)] = recipient_states(saved).values()
    assert status == RecipientStatus.FAILED
    assert error is not None and error.startswith("Unexpected error: ")
    assert saved.status == CampaignStatus.FAILED
    assert emails == {}


async def test_recover_interrupted_fails_the_pending_recipients_of_sending_campaigns(
    sender: CampaignSender,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clients = [await add_client(session, name) for name in ("Acme", "Beta", "Gamma")]
    interrupted = await create(session, clients)
    interrupted.recipients[0].status = RecipientStatus.SENT
    interrupted.status = CampaignStatus.SENDING
    finished = await create(session, clients[:1])
    finished.recipients[0].status = RecipientStatus.SENT
    finished.status = CampaignStatus.SENDING
    draft = await create(session, clients)
    await session.commit()

    await sender.recover_interrupted()

    saved, _ = await stored(session_factory, interrupted.id)
    assert recipient_states(saved) == {
        "biuro@acme.example": (RecipientStatus.SENT, None),
        "biuro@beta.example": (RecipientStatus.FAILED, "Sending interrupted"),
        "biuro@gamma.example": (RecipientStatus.FAILED, "Sending interrupted"),
    }
    assert saved.status == CampaignStatus.FAILED
    assert saved.sent_at is None
    saved_finished, _ = await stored(session_factory, finished.id)
    assert saved_finished.status == CampaignStatus.SENT
    assert saved_finished.sent_at is not None
    saved_draft, _ = await stored(session_factory, draft.id)
    assert saved_draft.status == CampaignStatus.DRAFT
    assert {status for status, _ in recipient_states(saved_draft).values()} == {
        RecipientStatus.PENDING
    }


async def test_lifespan_fails_a_campaign_left_in_sending(
    database_url: str,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    campaign = await create(session, [await add_client(session, "Acme")])
    campaign.status = CampaignStatus.SENDING
    await session.commit()
    settings = Settings(
        database_url=database_url,
        encryption_key=EncryptionService.generate_key(),
        seed_demo_data=False,
    )
    app = create_app(settings, session_factory=session_factory)

    async with app.router.lifespan_context(app):
        pass

    saved, _ = await stored(session_factory, campaign.id)
    assert saved.status == CampaignStatus.FAILED
    assert recipient_states(saved) == {
        "biuro@acme.example": (RecipientStatus.FAILED, "Sending interrupted")
    }
