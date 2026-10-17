"""Client emails are unique among non-deleted clients. Clients are global (D5)."""

from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.models.category import Category
from app.models.client import Client
from app.repositories.client_repository import ClientRepository
from app.schemas.base import Page
from app.schemas.clients import ClientCreateSchema, ClientSchema, ClientUpdateSchema


class ClientService:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def get_all(self, skip: int, limit: int, search: str | None) -> Page[ClientSchema]:
        clients = await self._clients.get_all(skip, limit, search)
        total = await self._clients.count(search)
        return Page[ClientSchema](
            items=[ClientSchema.model_validate(client) for client in clients], total=total
        )

    async def get_by_id(self, client_id: int) -> Client:
        client = await self._clients.get_by_id(client_id)
        if client is None:
            raise NotFoundError(f"Client {client_id} not found")
        return client

    async def create(self, data: ClientCreateSchema) -> Client:
        await self._check_email_free(data.primary_email)
        categories = await self._load_categories(data.category_ids)
        return await self._clients.create(data, categories)

    async def update(self, client_id: int, data: ClientUpdateSchema) -> Client:
        client = await self.get_by_id(client_id)
        # Keeping its own email is not a conflict.
        await self._check_email_free(data.primary_email, exclude_id=client.id)
        categories = await self._load_categories(data.category_ids)
        return await self._clients.update(client, data, categories)

    async def delete(self, client_id: int) -> None:
        client = await self.get_by_id(client_id)
        await self._clients.soft_delete(client)

    async def _check_email_free(self, email: str, exclude_id: int | None = None) -> None:
        if await self._clients.exists_by_email(email, exclude_id=exclude_id):
            raise ConflictError(f"Client with email '{email}' already exists")

    async def _load_categories(self, category_ids: list[int]) -> list[Category]:
        # Duplicate IDs are not an error (W-26); unknown and deleted ones are.
        requested = set(category_ids)
        categories = await self._clients.load_categories(sorted(requested))
        missing = requested - {category.id for category in categories}
        if missing:
            ids = ", ".join(str(category_id) for category_id in sorted(missing))
            raise BusinessRuleError(f"Categories not found: {ids}")
        return categories
