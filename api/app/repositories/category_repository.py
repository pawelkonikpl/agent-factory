"""Categories in PostgreSQL. Every query skips soft-deleted rows unless asked otherwise."""

from sqlalchemy import Select, false, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConflictError
from app.models.base import utc_now
from app.models.category import Category


def _not_deleted() -> Select[Category]:
    # The same predicate as the partial unique index on the name.
    return select(Category).where(Category.is_deleted == false())


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, category_id: int) -> Category | None:
        return await self._session.scalar(_not_deleted().where(Category.id == category_id))

    async def get_by_name(self, name: str) -> Category | None:
        return await self._session.scalar(_not_deleted().where(Category.name == name))

    async def get_all(self, include_deleted: bool = False) -> list[Category]:
        query = select(Category) if include_deleted else _not_deleted()
        categories = await self._session.scalars(query.order_by(Category.id))
        return list(categories)

    async def exists_by_name(self, name: str, exclude_id: int | None = None) -> bool:
        query = _not_deleted().where(Category.name == name)
        if exclude_id is not None:
            query = query.where(Category.id != exclude_id)
        return bool(await self._session.scalar(select(query.exists())))

    async def create(self, name: str) -> Category:
        category = Category(name=name)
        self._session.add(category)
        await self._commit_name(name)
        return category

    async def update(self, category: Category, name: str) -> Category:
        category.name = name
        await self._commit_name(name)
        return category

    async def soft_delete(self, category: Category) -> Category:
        category.is_deleted = True
        category.deleted_at = utc_now()
        await self._session.commit()
        return category

    async def _commit_name(self, name: str) -> None:
        # Two concurrent requests can both pass the service check; the index then rejects one.
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"Category with name '{name}' already exists") from exc
