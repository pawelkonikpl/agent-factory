"""Demo clients and campaigns (D22), found by natural key so a second run creates nothing.

Run by hand with: uv run python -m app.services.seed
"""

import asyncio
from dataclasses import dataclass

from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import create_engine, create_session_factory
from app.models.campaign import Campaign, CampaignRecipient, CampaignStatus, RecipientStatus
from app.models.client import Client
from app.schemas.campaigns import CampaignCreateSchema
from app.schemas.clients import ClientCreateSchema


@dataclass(frozen=True)
class SeedResult:
    clients_created: int
    clients_skipped: int
    campaigns_created: int
    campaigns_skipped: int
    recipients_created: int


@dataclass(frozen=True)
class SeedCampaign:
    data: CampaignCreateSchema
    # The recipients' primary emails, in CLIENTS.
    recipient_emails: tuple[str, ...]


# Built through the API's schemas, so a value the API would reject can't be seeded. Reserved
# .example domains only (D31, RFC 2606): a seeded draft sent through a real account reaches nobody.
CLIENTS = [
    ClientCreateSchema(
        company_name="Acme Logistics",
        primary_email="contact@acme-logistics.example",
        phone_number="+1-202-555-0101",
        notes="Priority logistics partner",
    ),
    ClientCreateSchema(
        company_name="Bright Dental Clinic",
        primary_email="hello@brightdental.example",
        phone_number="+1-202-555-0102",
        notes="Monthly newsletter subscriber",
    ),
    ClientCreateSchema(
        company_name="Northwind Electronics",
        primary_email="sales@northwind-electronics.example",
        phone_number="+1-202-555-0103",
        notes="Interested in product launch campaigns",
    ),
    ClientCreateSchema(
        company_name="Green Foods Market",
        primary_email="owner@greenfoods-market.example",
        phone_number="+1-202-555-0104",
        notes="Seasonal promo campaigns",
    ),
    ClientCreateSchema(
        company_name="Pixel Craft Studio",
        primary_email="team@pixelcraft.example",
        phone_number="+1-202-555-0105",
        notes="Design partner",
    ),
]

# The subject's emoji is deliberate: it exercises the UTF-8 subject.
CAMPAIGNS = [
    SeedCampaign(
        CampaignCreateSchema(
            name="Spring Product Update",
            subject="See what's new this spring 🌱",
            content=(
                "<p>Hello {company},</p>"
                "<p>Spring is here, and so are our newest products. Take a look!</p>"
            ),
        ),
        (
            "contact@acme-logistics.example",
            "sales@northwind-electronics.example",
            "team@pixelcraft.example",
        ),
    ),
    SeedCampaign(
        CampaignCreateSchema(
            name="Monthly Newsletter - April",
            subject="April highlights from our team",
            content="<p>Hello {company},</p><p>Here is what our team worked on this April.</p>",
        ),
        ("hello@brightdental.example", "owner@greenfoods-market.example"),
    ),
    SeedCampaign(
        CampaignCreateSchema(
            name="VIP Partner Invitation",
            subject="Invitation: partner strategy session",
            content=(
                "<p>Hello {company},</p>"
                "<p>We would like to invite you to our partner strategy session.</p>"
            ),
        ),
        ("contact@acme-logistics.example", "team@pixelcraft.example"),
    ),
]


async def seed_clients_and_campaigns(session: AsyncSession) -> SeedResult:
    """Add the missing demo clients and campaigns, leaving found ones untouched.

    Commits once, at the end, so a failure part-way leaves nothing behind.
    """
    clients: dict[str, Client] = {}
    clients_created = 0
    for data in CLIENTS:
        find_client = select(Client).where(
            Client.primary_email == data.primary_email, Client.is_deleted == false()
        )
        client = await session.scalar(find_client)
        if client is None:
            client = Client(
                company_name=data.company_name,
                primary_email=data.primary_email,
                phone_number=data.phone_number,
                is_active=data.is_active,
                notes=data.notes,
            )
            session.add(client)
            clients_created += 1
        clients[data.primary_email] = client

    campaigns_created = 0
    recipients_created = 0
    for seed in CAMPAIGNS:
        find_campaign = select(Campaign.id).where(
            Campaign.name == seed.data.name, Campaign.is_deleted == false()
        )
        if await session.scalar(find_campaign) is not None:
            continue
        campaign = Campaign(
            name=seed.data.name,
            subject=seed.data.subject,
            content=seed.data.content,
            status=CampaignStatus.DRAFT,
            recipients=[
                CampaignRecipient(client=clients[email], status=RecipientStatus.PENDING)
                for email in seed.recipient_emails
            ],
        )
        session.add(campaign)
        campaigns_created += 1
        recipients_created += len(seed.recipient_emails)

    await session.commit()
    return SeedResult(
        clients_created=clients_created,
        clients_skipped=len(CLIENTS) - clients_created,
        campaigns_created=campaigns_created,
        campaigns_skipped=len(CAMPAIGNS) - campaigns_created,
        recipients_created=recipients_created,
    )


async def main() -> None:
    """Seed the database at API_DATABASE_URL, whatever API_SEED_DEMO_DATA says. No migrations."""
    engine = create_engine(Settings().database_url)
    try:
        async with create_session_factory(engine)() as session:
            result = await seed_clients_and_campaigns(session)
    finally:
        await engine.dispose()
    print(
        f"clients_created={result.clients_created} clients_skipped={result.clients_skipped} "
        f"campaigns_created={result.campaigns_created} "
        f"campaigns_skipped={result.campaigns_skipped} "
        f"recipients_created={result.recipients_created}"
    )


if __name__ == "__main__":
    asyncio.run(main())
