from fastapi import APIRouter, status

from app.dependencies import CategoryServiceDep, PrincipalDep
from app.models.category import Category
from app.schemas.categories import CategoryCreateSchema, CategorySchema, CategoryUpdateSchema

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("/", response_model=list[CategorySchema])
async def list_categories(
    principal: PrincipalDep, service: CategoryServiceDep, include_deleted: bool = False
) -> list[Category]:
    return await service.get_all(include_deleted)


@router.post("/", response_model=CategorySchema, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreateSchema, principal: PrincipalDep, service: CategoryServiceDep
) -> Category:
    return await service.create(payload)


@router.put("/{category_id}", response_model=CategorySchema)
async def update_category(
    category_id: int,
    payload: CategoryUpdateSchema,
    principal: PrincipalDep,
    service: CategoryServiceDep,
) -> Category:
    return await service.update(category_id, payload)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int, principal: PrincipalDep, service: CategoryServiceDep
) -> None:
    await service.delete(category_id)
