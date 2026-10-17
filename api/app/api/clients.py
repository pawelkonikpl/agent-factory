from fastapi import APIRouter, status

from app.dependencies import ClientServiceDep, PrincipalDep
from app.models.client import Client
from app.schemas.base import Page, PageParamsDep
from app.schemas.clients import (
    ClientBulkCreateSchema,
    ClientBulkResultSchema,
    ClientCreateSchema,
    ClientSchema,
    ClientUpdateSchema,
)

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.get("/", response_model=Page[ClientSchema])
async def list_clients(
    page: PageParamsDep,
    principal: PrincipalDep,
    service: ClientServiceDep,
    search: str | None = None,
) -> Page[ClientSchema]:
    return await service.get_all(page.skip, page.limit, search)


@router.post("/", response_model=ClientSchema, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreateSchema, principal: PrincipalDep, service: ClientServiceDep
) -> Client:
    return await service.create(payload)


@router.post("/bulk", response_model=ClientBulkResultSchema)
async def bulk_create_clients(
    payload: ClientBulkCreateSchema, principal: PrincipalDep, service: ClientServiceDep
) -> ClientBulkResultSchema:
    return await service.bulk_create(payload)


@router.get("/{client_id}", response_model=ClientSchema)
async def get_client(client_id: int, principal: PrincipalDep, service: ClientServiceDep) -> Client:
    return await service.get_by_id(client_id)


@router.put("/{client_id}", response_model=ClientSchema)
async def update_client(
    client_id: int,
    payload: ClientUpdateSchema,
    principal: PrincipalDep,
    service: ClientServiceDep,
) -> Client:
    return await service.update(client_id, payload)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(client_id: int, principal: PrincipalDep, service: ClientServiceDep) -> None:
    await service.delete(client_id)
