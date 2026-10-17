import logging

import pytest
from sqlalchemy import false, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import main
from app.config import Settings
from app.main import create_app
from app.models.campaign import Campaign, CampaignRecipient, CampaignStatus, RecipientStatus
from app.models.client import Client
from app.repositories.client_repository import ClientRepository
from app.schemas.clients import ClientCreateSchema
from app.services.client_service import ClientService
from app.services.encryption import EncryptionService
from app.services.seed import SeedResult, seed_clients_and_campaigns

CLIENTS = [
    (
        "Acme Logistics",
        "contact@acme-logistics.example",
        "+1-202-555-0101",
        "Priority logistics partner",
    ),
    (
        "Bright Dental Clinic",
        "hello@brightdental.example",
        "+1-202-555-0102",
        "Monthly newsletter subscriber",
    ),
    (
        "Northwind Electronics",
        "sales@northwind-electronics.example",
        "+1-202-555-0103",
        "Interested in product launch campaigns",
    ),
    (
        "Green Foods Market",
        "owner@greenfoods-market.example",
        "+1-202-555-0104",
        "Seasonal promo campaigns",
    ),
    ("Pixel Craft Studio", "team@pixelcraft.example", "+1-202-555-0105", "Design partner"),
]

CAMPAIGNS = [
    (
        "Spring Product Update",
        "See what's new this spring 🌱",
        ["Acme Logistics", "Northwind Electronics", "Pixel Craft Studio"],
    ),
    (
        "Monthly Newsletter - April",
        "April highlights from our team",
        ["Bright Dental Clinic", "Green Foods Market"],
    ),
    (
        "VIP Partner Invitation",
        "Invitation: partner strategy session",
        ["Acme Logistics", "Pixel Craft Studio"],
    ),
]

CREATED = SeedResult(
    clients_created=5,
    clients_skipped=0,
    campaigns_created=3,
    campaigns_skipped=0,
    recipients_created=7,
)


async def seed(session_factory: async_sessionmaker[AsyncSession]) -> SeedResult:
    async with session_factory() as session:
        return await seed_clients_and_campaigns(session)


async def row_counts(session_factory: async_sessionmaker[AsyncSession]) -> tuple[int, int, int]:
    async with session_factory() as session:
        counts = []
        for model in (Client, Campaign, CampaignRecipient):
            query = select(func.count()).select_from(model).where(model.is_deleted == false())
            counts.append((await session.execute(query)).scalar_one())
    return counts[0], counts[1], counts[2]


async def stored_clients(session_factory: async_sessionmaker[AsyncSession]) -> list[Client]:
    async with session_factory() as session:
        return list(await session.scalars(select(Client).order_by(Client.id)))


async def stored_campaigns(session_factory: async_sessionmaker[AsyncSession]) -> list[Campaign]:
    async with session_factory() as session:
        return list(await session.scalars(select(Campaign).order_by(Campaign.id)))


@pytest.fixture
def skip_migrations(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test database is migrated already. Alembic's env.py would also replace the root
    logging handlers, caplog's among them, so the seed's log lines would not be captured."""
    monkeypatch.setattr(main, "run_migrations", lambda url: None)


def lifespan_settings(database_url: str, seed_demo_data: bool) -> Settings:
    return Settings(
        database_url=database_url,
        encryption_key=EncryptionService.generate_key(),
        seed_demo_data=seed_demo_data,
    )


async def test_seed_creates_the_demo_data_on_an_empty_database(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result = await seed(session_factory)

    assert result == CREATED
    assert await row_counts(session_factory) == (5, 3, 7)
    clients = await stored_clients(session_factory)
    assert [
        (client.company_name, client.primary_email, client.phone_number, client.notes)
        for client in clients
    ] == CLIENTS
    assert all(client.primary_email.endswith(".example") for client in clients)
    assert all(client.is_active for client in clients)
    assert all(client.address is None and client.additional_emails is None for client in clients)
    assert all(client.categories == [] for client in clients)
    campaigns = await stored_campaigns(session_factory)
    assert [
        (
            campaign.name,
            campaign.subject,
            [recipient.client.company_name for recipient in campaign.recipients],
        )
        for campaign in campaigns
    ] == CAMPAIGNS
    for campaign in campaigns:
        assert campaign.status == CampaignStatus.DRAFT
        assert campaign.scheduled_for is None
        assert "{company}" in campaign.content
        assert {recipient.status for recipient in campaign.recipients} == {RecipientStatus.PENDING}


async def test_second_run_creates_nothing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed(session_factory)

    result = await seed(session_factory)

    assert result == SeedResult(
        clients_created=0,
        clients_skipped=5,
        campaigns_created=0,
        campaigns_skipped=3,
        recipients_created=0,
    )
    assert await row_counts(session_factory) == (5, 3, 7)


async def test_seed_reuses_an_existing_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        data = ClientCreateSchema.model_validate(
            {"company_name": "Acme (mine)", "primary_email": "contact@acme-logistics.example"}
        )
        existing = await ClientService(ClientRepository(session)).create(data)

    result = await seed(session_factory)

    assert result.clients_created == 4
    assert result.clients_skipped == 1
    assert await row_counts(session_factory) == (5, 3, 7)
    clients = await stored_clients(session_factory)
    acme = [client for client in clients if client.primary_email.startswith("contact@acme")]
    assert [(client.id, client.company_name) for client in acme] == [(existing.id, "Acme (mine)")]
    campaigns = {campaign.name: campaign for campaign in await stored_campaigns(session_factory)}
    for name in ("Spring Product Update", "VIP Partner Invitation"):
        assert existing.id in [recipient.client_id for recipient in campaigns[name].recipients]


@pytest.mark.parametrize(("seed_demo_data", "expected"), [(True, (5, 3, 7)), (False, (0, 0, 0))])
@pytest.mark.usefixtures("skip_migrations")
async def test_lifespan_seeds_only_with_the_setting_on(
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
    seed_demo_data: bool,
    expected: tuple[int, int, int],
) -> None:
    app = create_app(
        lifespan_settings(database_url, seed_demo_data), session_factory=session_factory
    )

    with caplog.at_level(logging.INFO, logger="app.main"):
        async with app.router.lifespan_context(app):
            pass

    assert await row_counts(session_factory) == expected
    seed_lines = [record.getMessage() for record in caplog.records if record.name == "app.main"]
    if seed_demo_data:
        assert seed_lines == [
            "Demo data seed: 5 clients created, 0 skipped; 3 campaigns created, 0 skipped; "
            "7 recipients created"
        ]
    else:
        assert seed_lines == []


@pytest.mark.usefixtures("skip_migrations")
async def test_lifespan_logs_a_seed_error_and_still_starts(
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_seed(session: AsyncSession) -> SeedResult:
        session.add(Client(company_name="Half", primary_email="half@seed.example"))
        await session.flush()
        raise RuntimeError("seed broke")

    monkeypatch.setattr(main, "seed_clients_and_campaigns", failing_seed)
    app = create_app(lifespan_settings(database_url, True), session_factory=session_factory)
    started = False

    async with app.router.lifespan_context(app):
        started = True

    assert started
    assert "Seeding demo data failed" in caplog.text
    assert "seed broke" in caplog.text
    assert await row_counts(session_factory) == (0, 0, 0)
