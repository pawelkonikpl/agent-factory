from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.models.category import Category
from app.models.client import Client, client_category
from app.repositories.category_repository import CategoryRepository
from app.repositories.client_repository import ClientRepository
from app.schemas.clients import ClientCreateSchema, ClientUpdateSchema
from app.services.client_service import ClientService


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def repository(session: AsyncSession) -> ClientRepository:
    return ClientRepository(session)


@pytest.fixture
def service(repository: ClientRepository) -> ClientService:
    return ClientService(repository)


@pytest.fixture
def categories(session: AsyncSession) -> CategoryRepository:
    return CategoryRepository(session)


def client_data(company_name: str, primary_email: str, **fields: Any) -> dict[str, Any]:
    return {"company_name": company_name, "primary_email": primary_email} | fields


async def create(
    service: ClientService, company_name: str, primary_email: str, **fields: Any
) -> Client:
    data = ClientCreateSchema.model_validate(client_data(company_name, primary_email, **fields))
    return await service.create(data)


async def update(
    service: ClientService, client_id: int, company_name: str, primary_email: str, **fields: Any
) -> Client:
    data = ClientUpdateSchema.model_validate(client_data(company_name, primary_email, **fields))
    return await service.update(client_id, data)


async def reload(service: ClientService, session: AsyncSession, client_id: int) -> Client:
    """The client as stored, not the objects already in the session."""
    session.expunge_all()
    return await service.get_by_id(client_id)


async def listed_names(service: ClientService, search: str | None = None) -> list[str]:
    page = await service.get_all(0, 100, search)
    return [client.company_name for client in page.items]


async def links(session: AsyncSession, client_id: int) -> int:
    query = (
        select(func.count())
        .select_from(client_category)
        .where(client_category.c.client_id == client_id)
    )
    return (await session.execute(query)).scalar_one()


async def test_create_client_with_categories(
    service: ClientService, session: AsyncSession, categories: CategoryRepository
) -> None:
    first = await categories.create("Hurtownie")
    second = await categories.create("Detal")

    client = await create(
        service, "Acme", "biuro@acme.example", category_ids=[second.id, first.id]
    )

    stored = await reload(service, session, client.id)
    assert stored.company_name == "Acme"
    assert [category.id for category in stored.categories] == [first.id, second.id]


async def test_create_duplicate_email_is_rejected(service: ClientService) -> None:
    await create(service, "Acme", "biuro@acme.example")

    with pytest.raises(ConflictError) as error:
        await create(service, "Acme Bis", "biuro@acme.example")

    assert str(error.value) == "Client with email 'biuro@acme.example' already exists"


async def test_create_duplicate_email_is_allowed_after_soft_delete(
    service: ClientService,
) -> None:
    deleted = await create(service, "Acme", "biuro@acme.example")
    await service.delete(deleted.id)

    client = await create(service, "Acme", "biuro@acme.example")

    assert client.id != deleted.id
    assert client.primary_email == "biuro@acme.example"


async def test_update_replaces_every_field(
    service: ClientService, session: AsyncSession, categories: CategoryRepository
) -> None:
    category = await categories.create("Hurtownie")
    client = await create(
        service,
        "Acme",
        "biuro@acme.example",
        additional_emails="handel@acme.example",
        phone_number="+48 600 100 200",
        address="ul. Prosta 1, Warszawa",
        is_active=False,
        notes="Stały klient",
        category_ids=[category.id],
    )

    await update(service, client.id, "Acme Sp. z o.o.", "kontakt@acme.example")

    stored = await reload(service, session, client.id)
    assert stored.company_name == "Acme Sp. z o.o."
    assert stored.primary_email == "kontakt@acme.example"
    assert stored.additional_emails is None
    assert stored.phone_number is None
    assert stored.address is None
    assert stored.notes is None
    assert stored.is_active is True
    assert stored.categories == []


async def test_update_to_an_email_taken_by_another_client_is_rejected(
    service: ClientService,
) -> None:
    await create(service, "Acme", "biuro@acme.example")
    client = await create(service, "Beta", "biuro@beta.example")

    with pytest.raises(ConflictError) as error:
        await update(service, client.id, "Beta", "biuro@acme.example")

    assert str(error.value) == "Client with email 'biuro@acme.example' already exists"


async def test_delete_clears_the_categories(
    service: ClientService, session: AsyncSession, categories: CategoryRepository
) -> None:
    first = await categories.create("Hurtownie")
    second = await categories.create("Detal")
    client = await create(
        service, "Acme", "biuro@acme.example", category_ids=[first.id, second.id]
    )

    await service.delete(client.id)

    assert await links(session, client.id) == 0
    with pytest.raises(NotFoundError) as error:
        await service.get_by_id(client.id)
    assert str(error.value) == f"Client {client.id} not found"


async def test_unknown_category_ids_are_rejected(
    service: ClientService, categories: CategoryRepository
) -> None:
    kept = await categories.create("Hurtownie")
    deleted = await categories.create("Detal")
    await categories.soft_delete(deleted)

    with pytest.raises(BusinessRuleError) as error:
        await create(
            service, "Acme", "biuro@acme.example", category_ids=[999999, kept.id, deleted.id]
        )

    assert str(error.value) == f"Categories not found: {deleted.id}, 999999"
    assert await listed_names(service) == []


async def test_get_all_without_deleted(service: ClientService) -> None:
    kept = await create(service, "Alfa", "biuro@alfa.example")
    deleted = await create(service, "Beta", "biuro@beta.example")
    await service.delete(deleted.id)

    page = await service.get_all(0, 100, None)

    assert [client.id for client in page.items] == [kept.id]
    assert page.total == 1


async def test_search_finds_by_company_name_email_phone_and_category_name(
    service: ClientService, categories: CategoryRepository
) -> None:
    category = await categories.create("Hurtownie")
    await create(service, "Alfa", "biuro@one.example", phone_number="+48 111 000 111")
    await create(service, "Beta", "Kontakt@Zeta.example")
    await create(service, "Gamma", "info@two.example", phone_number="+48 222 999 222")
    await create(service, "Delta", "info@three.example", category_ids=[category.id])

    assert await listed_names(service, "ALFA") == ["Alfa"]
    assert await listed_names(service, "kontakt@ZETA") == ["Beta"]
    assert await listed_names(service, "222 999") == ["Gamma"]
    assert await listed_names(service, "hurtOWNIE") == ["Delta"]
    assert (await service.get_all(0, 100, "hurtownie")).total == 1


async def test_total_ignores_skip_and_limit(service: ClientService) -> None:
    await create(service, "Alfa", "biuro@alfa.example")
    beta = await create(service, "Beta", "biuro@beta.example")
    await create(service, "Gamma", "biuro@gamma.example")

    page = await service.get_all(1, 1, None)

    assert [client.id for client in page.items] == [beta.id]
    assert page.total == 3


async def test_update_keeping_its_own_email_is_allowed(service: ClientService) -> None:
    client = await create(service, "Acme", "biuro@acme.example")

    updated = await update(service, client.id, "Acme Sp. z o.o.", "biuro@acme.example")

    assert updated.company_name == "Acme Sp. z o.o."
    assert updated.primary_email == "biuro@acme.example"


async def test_duplicate_category_ids_give_one_link(
    service: ClientService, session: AsyncSession, categories: CategoryRepository
) -> None:
    category = await categories.create("Hurtownie")

    client = await create(
        service, "Acme", "biuro@acme.example", category_ids=[category.id, category.id]
    )

    assert [linked.id for linked in client.categories] == [category.id]
    assert await links(session, client.id) == 1


async def test_client_matching_two_categories_is_listed_once(
    service: ClientService, categories: CategoryRepository
) -> None:
    linked: list[Category] = [
        await categories.create("Hurt Alfa"),
        await categories.create("Hurt Beta"),
    ]
    client = await create(
        service, "Acme", "biuro@acme.example", category_ids=[category.id for category in linked]
    )

    page = await service.get_all(0, 100, "hurt")

    assert [listed.id for listed in page.items] == [client.id]
    assert page.total == 1


async def test_search_matches_percent_underscore_and_backslash_literally(
    service: ClientService,
) -> None:
    await create(service, "Acme 100%", "biuro@one.example")
    await create(service, "Acme 1000", "biuro@two.example")
    await create(service, "Acme A\\B", "biuro@three.example")

    assert await listed_names(service, "100%") == ["Acme 100%"]
    assert (await service.get_all(0, 100, "_")).total == 0
    assert await listed_names(service, "_") == []
    assert await listed_names(service, "\\") == ["Acme A\\B"]


async def test_list_is_ordered_by_company_name_then_id(service: ClientService) -> None:
    gamma = await create(service, "Gamma", "biuro@gamma.example")
    first_alfa = await create(service, "Alfa", "biuro@alfa.example")
    beta = await create(service, "Beta", "biuro@beta.example")
    second_alfa = await create(service, "Alfa", "kontakt@alfa.example")

    page = await service.get_all(0, 100, None)

    assert [client.id for client in page.items] == [
        first_alfa.id,
        second_alfa.id,
        beta.id,
        gamma.id,
    ]


async def test_repository_create_with_a_taken_email_raises_conflict_error(
    repository: ClientRepository,
) -> None:
    # Two requests that both passed the service check: the unique index rejects the second.
    data = ClientCreateSchema.model_validate(client_data("Acme", "biuro@acme.example"))
    await repository.create(data, [])

    with pytest.raises(ConflictError) as error:
        await repository.create(data, [])

    assert str(error.value) == "Client with email 'biuro@acme.example' already exists"
    listed = await repository.get_all(0, 100, None)
    assert [client.primary_email for client in listed] == ["biuro@acme.example"]
