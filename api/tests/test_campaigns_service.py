from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.errors import BusinessRuleError, NotFoundError
from app.models.campaign import Campaign, CampaignRecipient, CampaignStatus, RecipientStatus
from app.models.client import Client
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.client_repository import ClientRepository
from app.schemas.campaigns import CampaignCreateSchema, CampaignUpdateSchema
from app.schemas.clients import ClientCreateSchema
from app.services.campaign_service import CampaignService
from app.services.client_service import ClientService


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def service(session: AsyncSession) -> CampaignService:
    return CampaignService(CampaignRepository(session))


@pytest.fixture
def clients(session: AsyncSession) -> ClientService:
    return ClientService(ClientRepository(session))


async def add_client(clients: ClientService, company_name: str) -> Client:
    email = f"biuro@{company_name.lower()}.example"
    data = ClientCreateSchema.model_validate({"company_name": company_name, "primary_email": email})
    return await clients.create(data)


async def create(service: CampaignService, name: str = "Jesień", **fields: Any) -> Campaign:
    data = CampaignCreateSchema.model_validate(
        {"name": name, "subject": "Nowości", "content": "Dzień dobry"} | fields
    )
    return await service.create(data)


async def update(service: CampaignService, campaign_id: int, **fields: Any) -> Campaign:
    return await service.update(campaign_id, CampaignUpdateSchema.model_validate(fields))


async def reload(service: CampaignService, session: AsyncSession, campaign_id: int) -> Campaign:
    """The campaign as stored, not the objects already in the session."""
    session.expunge_all()
    return await service.get_by_id(campaign_id)


def active_client_ids(campaign: Campaign) -> list[int]:
    return [recipient.client_id for recipient in campaign.recipients if not recipient.is_deleted]


async def set_status(session: AsyncSession, campaign: Campaign, status: CampaignStatus) -> None:
    campaign.status = status
    await session.commit()


async def set_recipient_statuses(
    session: AsyncSession, campaign: Campaign, statuses: list[RecipientStatus]
) -> None:
    for recipient, status in zip(campaign.recipients, statuses, strict=True):
        recipient.status = status
    await session.commit()


async def listed_names(service: CampaignService, search: str | None = None) -> list[str]:
    page = await service.get_all(0, 100, search)
    return [campaign.name for campaign in page.items]


async def test_create_with_recipients_gives_a_draft_with_pending_recipients(
    service: CampaignService, session: AsyncSession, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    beta = await add_client(clients, "Beta")

    campaign = await create(service, recipient_ids=[beta.id, acme.id])

    stored = await reload(service, session, campaign.id)
    assert stored.status == CampaignStatus.DRAFT
    assert sorted(active_client_ids(stored)) == [acme.id, beta.id]
    assert {recipient.status for recipient in stored.recipients} == {RecipientStatus.PENDING}


async def test_create_with_a_scheduled_date_stays_a_draft(
    service: CampaignService, session: AsyncSession
) -> None:
    scheduled = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)

    campaign = await create(service, scheduled_for=scheduled)

    stored = await reload(service, session, campaign.id)
    assert stored.status == CampaignStatus.DRAFT
    assert stored.scheduled_for == scheduled


async def test_create_drops_duplicate_recipient_ids(
    service: CampaignService, session: AsyncSession, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    beta = await add_client(clients, "Beta")

    campaign = await create(service, recipient_ids=[acme.id, beta.id, acme.id, beta.id])

    stored = await reload(service, session, campaign.id)
    assert sorted(active_client_ids(stored)) == [acme.id, beta.id]


async def test_create_with_unknown_or_deleted_clients_is_rejected(
    service: CampaignService, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    deleted = await add_client(clients, "Gone")
    await clients.delete(deleted.id)
    unknown = deleted.id + 1000

    with pytest.raises(BusinessRuleError) as error:
        await create(service, recipient_ids=[unknown, acme.id, deleted.id])

    assert str(error.value) == f"Clients not found: {deleted.id}, {unknown}"
    assert await listed_names(service) == []


async def test_get_returns_the_campaign_and_404s_an_unknown_or_deleted_one(
    service: CampaignService, session: AsyncSession
) -> None:
    campaign = await create(service, "Jesień")
    deleted = await create(service, "Zima")
    await service.delete(deleted.id)

    assert (await reload(service, session, campaign.id)).name == "Jesień"
    for missing_id in (deleted.id, campaign.id + 1000):
        with pytest.raises(NotFoundError) as error:
            await service.get_by_id(missing_id)
        assert str(error.value) == f"Campaign {missing_id} not found"


async def test_list_search_matches_name_subject_and_content_case_insensitively(
    service: CampaignService,
) -> None:
    await create(service, "Jesienna promocja")
    await create(service, "Zima", subject="Rabaty JESIENNE")
    await create(service, "Wiosna", content="Oferta na jesień")
    await create(service, "Lato")
    await create(service, "100% rabatu")

    assert sorted(await listed_names(service, "jesien")) == ["Jesienna promocja", "Zima"]
    assert await listed_names(service, "JESIEŃ") == ["Wiosna"]
    assert await listed_names(service, "%") == ["100% rabatu"]
    assert len(await listed_names(service, "")) == 5


async def test_list_total_ignores_skip_and_limit(service: CampaignService) -> None:
    for name in ("Alfa", "Beta", "Gamma"):
        await create(service, name)

    page = await service.get_all(1, 1, None)

    assert (len(page.items), page.total) == (1, 3)


async def test_list_is_ordered_newest_first_then_by_id_descending(
    service: CampaignService, session: AsyncSession
) -> None:
    first = await create(service, "Alfa")
    second = await create(service, "Beta")
    third = await create(service, "Gamma")
    # Beta and Gamma share a creation time: the higher ID comes first.
    first.created_at = datetime(2026, 10, 1, tzinfo=UTC)
    second.created_at = third.created_at = datetime(2026, 10, 2, tzinfo=UTC)
    await session.commit()

    assert await listed_names(service) == ["Gamma", "Beta", "Alfa"]


async def test_update_a_draft_changes_only_the_given_fields(
    service: CampaignService, session: AsyncSession, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    scheduled = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    campaign = await create(service, recipient_ids=[acme.id], scheduled_for=scheduled)

    await update(service, campaign.id, name="  Zima  ", content=None)

    stored = await reload(service, session, campaign.id)
    assert stored.name == "Zima"
    assert stored.subject == "Nowości"
    assert stored.content == "Dzień dobry"
    assert stored.scheduled_for == scheduled
    assert active_client_ids(stored) == [acme.id]


async def test_update_a_non_draft_is_rejected(
    service: CampaignService, session: AsyncSession
) -> None:
    campaign = await create(service)
    await set_status(session, campaign, CampaignStatus.SENT)

    with pytest.raises(BusinessRuleError) as error:
        await update(service, campaign.id, name="Zima")

    assert str(error.value) == "Only draft campaigns can be modified"
    assert (await reload(service, session, campaign.id)).name == "Jesień"


async def test_update_with_recipient_ids_replaces_an_overlapping_set(
    service: CampaignService, session: AsyncSession, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    beta = await add_client(clients, "Beta")
    gamma = await add_client(clients, "Gamma")
    campaign = await create(service, recipient_ids=[acme.id, beta.id])

    await update(service, campaign.id, recipient_ids=[beta.id, gamma.id])

    stored = await reload(service, session, campaign.id)
    assert active_client_ids(stored) == [beta.id, gamma.id]
    deleted = [recipient.client_id for recipient in stored.recipients if recipient.is_deleted]
    assert deleted == [acme.id, beta.id]

    await update(service, campaign.id, recipient_ids=[])

    assert active_client_ids(await reload(service, session, campaign.id)) == []


async def test_update_with_unknown_clients_changes_nothing(
    service: CampaignService, session: AsyncSession
) -> None:
    campaign = await create(service)

    with pytest.raises(BusinessRuleError) as error:
        await update(service, campaign.id, name="Zima", recipient_ids=[campaign.id + 1000])

    assert str(error.value) == f"Clients not found: {campaign.id + 1000}"
    assert (await reload(service, session, campaign.id)).name == "Jesień"


async def test_update_clears_scheduled_for_on_explicit_null_and_keeps_it_when_omitted(
    service: CampaignService, session: AsyncSession
) -> None:
    scheduled = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    campaign = await create(service, scheduled_for=scheduled)

    await update(service, campaign.id, name="Zima")
    assert (await reload(service, session, campaign.id)).scheduled_for == scheduled

    await update(service, campaign.id, scheduled_for=None)
    assert (await reload(service, session, campaign.id)).scheduled_for is None


async def test_delete_soft_deletes_the_campaign_and_its_recipients(
    service: CampaignService, session: AsyncSession, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    campaign = await create(service, recipient_ids=[acme.id])

    await service.delete(campaign.id)

    session.expunge_all()
    stored = await session.get_one(Campaign, campaign.id)
    assert stored.is_deleted is True
    assert stored.deleted_at is not None
    assert [(r.is_deleted, r.deleted_at is not None) for r in stored.recipients] == [(True, True)]
    with pytest.raises(NotFoundError):
        await service.get_by_id(campaign.id)


async def test_add_recipients_skips_clients_already_on_the_campaign(
    service: CampaignService, session: AsyncSession, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    beta = await add_client(clients, "Beta")
    campaign = await create(service, recipient_ids=[acme.id])

    await service.add_recipients(campaign.id, [acme.id, beta.id, beta.id])

    stored = await reload(service, session, campaign.id)
    assert active_client_ids(stored) == [acme.id, beta.id]


async def test_add_recipients_to_a_non_draft_is_rejected(
    service: CampaignService, session: AsyncSession, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    campaign = await create(service)
    await set_status(session, campaign, CampaignStatus.FAILED)

    with pytest.raises(BusinessRuleError) as error:
        await service.add_recipients(campaign.id, [acme.id])

    assert str(error.value) == "Only draft campaigns can have recipients added"


async def test_to_schema_lists_active_recipients_with_their_client_and_enum_values(
    service: CampaignService, session: AsyncSession, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    beta = await add_client(clients, "Beta")
    gamma = await add_client(clients, "Gamma")
    campaign = await create(service, recipient_ids=[acme.id, beta.id])
    await update(service, campaign.id, recipient_ids=[gamma.id, beta.id])

    schema = service.to_schema(await reload(service, session, campaign.id))
    dumped = schema.model_dump(mode="json")

    assert dumped["status"] == "draft"
    assert [
        (r["clientId"], r["clientName"], r["clientEmail"], r["status"])
        for r in dumped["recipients"]
    ] == [
        (beta.id, "Beta", "biuro@beta.example", "pending"),
        (gamma.id, "Gamma", "biuro@gamma.example", "pending"),
    ]
    assert dumped["recipients"][0]["id"] < dumped["recipients"][1]["id"]
    assert dumped["stats"]["total"] == 2


async def test_stats_with_no_recipients_are_all_zero(service: CampaignService) -> None:
    campaign = await create(service)

    stats = service.compute_stats(campaign).model_dump()

    assert stats == {
        "total": 0,
        "sent": 0,
        "failed": 0,
        "pending": 0,
        "bounced": 0,
        "progressPercentage": 0.0,
        "successRate": 0.0,
    }


async def test_stats_with_all_recipients_pending_show_no_progress(
    service: CampaignService, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    beta = await add_client(clients, "Beta")
    campaign = await create(service, recipient_ids=[acme.id, beta.id])

    stats = service.compute_stats(campaign)

    assert (stats.total, stats.pending) == (2, 2)
    assert (stats.progress_percentage, stats.success_rate) == (0.0, 0.0)


async def test_stats_of_a_mix_are_rounded_to_two_decimals(
    service: CampaignService, session: AsyncSession, clients: ClientService
) -> None:
    ids = [(await add_client(clients, name)).id for name in ("A", "B", "C", "D", "E", "F")]
    three = await create(service, "Trzy", recipient_ids=ids[:3])
    await set_recipient_statuses(
        session, three, [RecipientStatus.SENT, RecipientStatus.FAILED, RecipientStatus.PENDING]
    )
    six = await create(service, "Sześć", recipient_ids=ids)
    await set_recipient_statuses(
        session,
        six,
        [
            RecipientStatus.SENT,
            RecipientStatus.SENT,
            RecipientStatus.FAILED,
            RecipientStatus.BOUNCED,
            RecipientStatus.PENDING,
            RecipientStatus.PENDING,
        ],
    )

    stats_three = service.compute_stats(three)
    stats_six = service.compute_stats(six)

    assert (stats_three.progress_percentage, stats_three.success_rate) == (66.67, 33.33)
    assert (stats_six.total, stats_six.sent, stats_six.failed) == (6, 2, 1)
    assert (stats_six.pending, stats_six.bounced) == (2, 1)
    # (2 + 1) / 6 = 50 %, 2 / 6 = 33.333... %; bounced counts in total only.
    assert (stats_six.progress_percentage, stats_six.success_rate) == (50.0, 33.33)


async def test_status_columns_store_the_lowercase_values(
    service: CampaignService, session: AsyncSession, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    campaign = await create(service, recipient_ids=[acme.id])

    campaign_status = await session.scalar(
        text("SELECT status FROM campaigns WHERE id = :id"), {"id": campaign.id}
    )
    recipient_status = await session.scalar(
        text("SELECT status FROM campaign_recipients WHERE campaign_id = :id"),
        {"id": campaign.id},
    )

    assert (campaign_status, recipient_status) == ("draft", "pending")


async def test_check_constraint_rejects_an_unknown_status(
    service: CampaignService, session: AsyncSession
) -> None:
    campaign = await create(service)

    with pytest.raises(IntegrityError, match="ck_campaigns_campaign_status"):
        await session.execute(
            text("UPDATE campaigns SET status = 'bogus' WHERE id = :id"), {"id": campaign.id}
        )


async def test_recipients_stay_unique_per_campaign_among_non_deleted_rows(
    service: CampaignService, session: AsyncSession, clients: ClientService
) -> None:
    acme = await add_client(clients, "Acme")
    campaign = await create(service, recipient_ids=[acme.id])

    session.add(CampaignRecipient(campaign_id=campaign.id, client_id=acme.id))
    with pytest.raises(IntegrityError, match="uq_campaign_recipients_campaign_id_client_id"):
        await session.flush()
