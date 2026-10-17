from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.errors import ConflictError, NotFoundError
from app.repositories.category_repository import CategoryRepository
from app.schemas.categories import CategoryCreateSchema, CategoryUpdateSchema
from app.services.category_service import CategoryService


@pytest.fixture
async def repository(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[CategoryRepository]:
    async with session_factory() as session:
        yield CategoryRepository(session)


@pytest.fixture
def service(repository: CategoryRepository) -> CategoryService:
    return CategoryService(repository)


async def create(service: CategoryService, name: str) -> int:
    category = await service.create(CategoryCreateSchema(name=name))
    return category.id


async def test_create_category(service: CategoryService) -> None:
    category = await service.create(CategoryCreateSchema(name="Klienci VIP"))

    assert category.name == "Klienci VIP"
    assert (await service.get_by_id(category.id)).name == "Klienci VIP"


async def test_create_duplicate_name_is_rejected(service: CategoryService) -> None:
    await create(service, "Klienci")

    with pytest.raises(ConflictError) as error:
        await create(service, "Klienci")

    assert str(error.value) == "Category with name 'Klienci' already exists"


async def test_create_duplicate_name_is_allowed_after_soft_delete(
    service: CategoryService,
) -> None:
    deleted_id = await create(service, "Klienci")
    await service.delete(deleted_id)

    category = await service.create(CategoryCreateSchema(name="Klienci"))

    assert category.id != deleted_id
    assert category.name == "Klienci"


async def test_update_category(service: CategoryService) -> None:
    category_id = await create(service, "Klienci")

    category = await service.update(category_id, CategoryUpdateSchema(name="Partnerzy"))

    assert category.name == "Partnerzy"
    assert (await service.get_by_id(category_id)).name == "Partnerzy"


async def test_update_to_a_name_taken_by_another_category_is_rejected(
    service: CategoryService,
) -> None:
    await create(service, "Klienci")
    category_id = await create(service, "Partnerzy")

    with pytest.raises(ConflictError) as error:
        await service.update(category_id, CategoryUpdateSchema(name="Klienci"))

    assert str(error.value) == "Category with name 'Klienci' already exists"


async def test_update_keeping_its_own_name_is_allowed(service: CategoryService) -> None:
    category_id = await create(service, "Klienci")

    category = await service.update(category_id, CategoryUpdateSchema(name="Klienci"))

    assert category.name == "Klienci"


async def test_delete_category(service: CategoryService) -> None:
    category_id = await create(service, "Klienci")

    await service.delete(category_id)

    with pytest.raises(NotFoundError) as error:
        await service.get_by_id(category_id)
    assert str(error.value) == f"Category {category_id} not found"


async def test_get_all_without_deleted(service: CategoryService) -> None:
    kept_id = await create(service, "Klienci")
    await service.delete(await create(service, "Partnerzy"))

    categories = await service.get_all()

    assert [category.id for category in categories] == [kept_id]


async def test_get_all_including_deleted_is_ordered_by_id(service: CategoryService) -> None:
    first_id = await create(service, "Klienci")
    second_id = await create(service, "Partnerzy")
    third_id = await create(service, "Dostawcy")
    await service.delete(second_id)

    categories = await service.get_all(include_deleted=True)

    assert [category.id for category in categories] == [first_id, second_id, third_id]


async def test_repository_create_with_a_taken_name_raises_conflict_error(
    repository: CategoryRepository,
) -> None:
    # Two requests that both passed the service check: the unique index rejects the second.
    await repository.create("Klienci")

    with pytest.raises(ConflictError) as error:
        await repository.create("Klienci")

    assert str(error.value) == "Category with name 'Klienci' already exists"
    assert [category.name for category in await repository.get_all()] == ["Klienci"]
