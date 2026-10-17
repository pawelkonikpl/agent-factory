"""Client emails are unique among non-deleted clients. Clients are global (D5)."""

from typing import Any

from pydantic import ValidationError
from pydantic.alias_generators import to_camel

from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.models.category import Category
from app.models.client import Client
from app.repositories.client_repository import ClientRepository
from app.schemas.base import Page
from app.schemas.clients import (
    ClientBulkCreateSchema,
    ClientBulkErrorSchema,
    ClientBulkResultSchema,
    ClientCreateSchema,
    ClientSchema,
    ClientUpdateSchema,
)


def _email_taken(email: str) -> ConflictError:
    return ConflictError(f"Client with email '{email}' already exists")


def _validation_message(error: ValidationError) -> str:
    """Each problem as "<camelCase field>: <msg>", the field's path joined with dots."""
    problems = []
    for problem in error.errors():
        loc = [str(part) for part in problem["loc"]]
        if loc:
            field = ".".join([to_camel(loc[0]), *loc[1:]])
            problems.append(f"{field}: {problem['msg']}")
        else:
            problems.append(problem["msg"])
    return "; ".join(problems)


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

    async def bulk_create(self, data: ClientBulkCreateSchema) -> ClientBulkResultSchema:
        """Create the rows in order; a failing row is reported and the others go on (W-07)."""
        errors: list[ClientBulkErrorSchema] = []
        accepted: set[str] = set()
        for row, raw in enumerate(data.clients, start=1):
            try:
                email = await self._bulk_create_row(raw, accepted)
            except ValidationError as exc:
                errors.append(ClientBulkErrorSchema(row=row, message=_validation_message(exc)))
            except (ConflictError, BusinessRuleError) as exc:
                errors.append(ClientBulkErrorSchema(row=row, message=str(exc)))
            else:
                accepted.add(email)
        await self._clients.commit()
        failed = len(errors)
        return ClientBulkResultSchema(
            success=len(data.clients) - failed, failed=failed, errors=errors
        )

    async def _bulk_create_row(self, raw: dict[str, Any], accepted: set[str]) -> str:
        """Create one row, checked like create and against the batch's earlier emails."""
        data = ClientCreateSchema.model_validate(raw)
        if data.primary_email in accepted:
            raise _email_taken(data.primary_email)
        await self._check_email_free(data.primary_email)
        categories = await self._load_categories(data.category_ids)
        await self._clients.add_in_savepoint(data, categories)
        return data.primary_email

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
            raise _email_taken(email)

    async def _load_categories(self, category_ids: list[int]) -> list[Category]:
        # Duplicate IDs are not an error (W-26); unknown and deleted ones are.
        requested = set(category_ids)
        categories = await self._clients.load_categories(sorted(requested))
        missing = requested - {category.id for category in categories}
        if missing:
            ids = ", ".join(str(category_id) for category_id in sorted(missing))
            raise BusinessRuleError(f"Categories not found: {ids}")
        return categories
