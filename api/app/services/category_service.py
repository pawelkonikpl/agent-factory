"""Category names are unique among non-deleted categories. Categories are global (D5)."""

from app.errors import ConflictError, NotFoundError
from app.models.category import Category
from app.repositories.category_repository import CategoryRepository
from app.schemas.categories import CategoryCreateSchema, CategoryUpdateSchema


class CategoryService:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    async def get_all(self, include_deleted: bool = False) -> list[Category]:
        return await self._categories.get_all(include_deleted)

    async def get_by_id(self, category_id: int) -> Category:
        category = await self._categories.get_by_id(category_id)
        if category is None:
            raise NotFoundError(f"Category {category_id} not found")
        return category

    async def create(self, data: CategoryCreateSchema) -> Category:
        await self._check_name_free(data.name)
        return await self._categories.create(data.name)

    async def update(self, category_id: int, data: CategoryUpdateSchema) -> Category:
        category = await self.get_by_id(category_id)
        # Keeping its own name is not a conflict.
        await self._check_name_free(data.name, exclude_id=category.id)
        return await self._categories.update(category, data.name)

    async def delete(self, category_id: int) -> None:
        category = await self.get_by_id(category_id)
        await self._categories.remove_client_associations(category.id)
        await self._categories.soft_delete(category)

    async def _check_name_free(self, name: str, exclude_id: int | None = None) -> None:
        if await self._categories.exists_by_name(name, exclude_id=exclude_id):
            raise ConflictError(f"Category with name '{name}' already exists")
