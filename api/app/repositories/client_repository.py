"""Clients in PostgreSQL. Every query skips soft-deleted clients and categories."""

from sqlalchemy import ColumnElement, Select, false, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConflictError
from app.models.base import utc_now
from app.models.category import Category
from app.models.client import Client, client_category
from app.schemas.clients import ClientCreateSchema, ClientFieldsSchema, ClientUpdateSchema


def _not_deleted() -> Select[Client]:
    # The same predicate as the partial unique index on the primary email.
    return select(Client).where(Client.is_deleted == false())


def _matches(search: str) -> ColumnElement[bool]:
    """The company name, email, phone or a linked category's name contains search.

    autoescape matches %, _ and the escape character literally. EXISTS, not a join, so a
    client with two matching categories is found once.
    """
    in_category = (
        select(client_category.c.client_id)
        .join(Category, Category.id == client_category.c.category_id)
        .where(
            client_category.c.client_id == Client.id,
            Category.is_deleted == false(),
            Category.name.icontains(search, autoescape=True),
        )
        .exists()
    )
    return or_(
        Client.company_name.icontains(search, autoescape=True),
        Client.primary_email.icontains(search, autoescape=True),
        Client.phone_number.icontains(search, autoescape=True),
        in_category,
    )


def _list_filters(search: str | None) -> list[ColumnElement[bool]]:
    """The list's and its total's filter: not deleted and, unless search is empty, matching."""
    filters = [Client.is_deleted == false()]
    if search:
        filters.append(_matches(search))
    return filters


def _write(client: Client, data: ClientFieldsSchema, categories: list[Category]) -> None:
    # Every field, None included: an update is a full replacement (W-01).
    client.company_name = data.company_name
    client.primary_email = data.primary_email
    client.additional_emails = data.additional_emails
    client.phone_number = data.phone_number
    client.address = data.address
    client.is_active = data.is_active
    client.notes = data.notes
    client.categories = categories


def _email_taken(email: str) -> ConflictError:
    return ConflictError(f"Client with email '{email}' already exists")


class ClientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, client_id: int) -> Client | None:
        return await self._session.scalar(_not_deleted().where(Client.id == client_id))

    async def get_all(self, skip: int, limit: int, search: str | None) -> list[Client]:
        query = (
            select(Client)
            .where(*_list_filters(search))
            .order_by(Client.company_name, Client.id)
            .offset(skip)
            .limit(limit)
        )
        clients = await self._session.scalars(query)
        return list(clients)

    async def count(self, search: str | None) -> int:
        # Over clients alone: a join to client_category would count a client once per category.
        query = select(func.count()).select_from(Client).where(*_list_filters(search))
        return (await self._session.execute(query)).scalar_one()

    async def exists_by_email(self, email: str, exclude_id: int | None = None) -> bool:
        query = _not_deleted().where(Client.primary_email == email)
        if exclude_id is not None:
            query = query.where(Client.id != exclude_id)
        return bool(await self._session.scalar(select(query.exists())))

    async def load_categories(self, category_ids: list[int]) -> list[Category]:
        query = (
            select(Category)
            .where(Category.id.in_(category_ids), Category.is_deleted == false())
            .order_by(Category.id)
        )
        categories = await self._session.scalars(query)
        return list(categories)

    async def create(self, data: ClientCreateSchema, categories: list[Category]) -> Client:
        client = Client()
        _write(client, data, categories)
        self._session.add(client)
        await self._commit_email(data.primary_email)
        return client

    async def add_in_savepoint(
        self, data: ClientCreateSchema, categories: list[Category]
    ) -> Client:
        """Add and flush in a savepoint, without committing: a failure undoes this client only."""
        client = Client()
        _write(client, data, categories)
        try:
            async with self._session.begin_nested():
                self._session.add(client)
                await self._session.flush()
        except IntegrityError as exc:
            raise _email_taken(data.primary_email) from exc
        return client

    async def update(
        self, client: Client, data: ClientUpdateSchema, categories: list[Category]
    ) -> Client:
        _write(client, data, categories)
        await self._commit_email(data.primary_email)
        return client

    async def soft_delete(self, client: Client) -> Client:
        client.is_deleted = True
        client.deleted_at = utc_now()
        # Deletes the client's client_category rows.
        client.categories.clear()
        await self._session.commit()
        return client

    async def commit(self) -> None:
        await self._session.commit()

    async def _commit_email(self, email: str) -> None:
        # Two concurrent requests can both pass the service check; the index then rejects one.
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise _email_taken(email) from exc
