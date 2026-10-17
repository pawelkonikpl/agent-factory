# API clients: models, migration, CRUD, search and the paginated list

> Feature: Add clients to the API: the `clients` and `client_category` models and migration, CRUD under `/clients/` with full-replacement `PUT`, server-side search and the paginated list with its total, as specified in `specs/email-sender/backend.md` API-5 (covers B4 without bulk)

## Context

This is roadmap item API-5 of Phase 4 (Email Sender API). The source of truth is
`specs/email-sender/backend.md`, "API-5: Clients" (Requirements, Pitfalls, Acceptance criteria),
plus that file's "Rules for every item". The wire format is in
`specs/email-sender/api-contract.md` §0 (conventions, errors, pagination), §2 (`ClientSchema`,
`ClientCreateSchema` / `ClientUpdateSchema`, `Page<T>`), §3.1 (`DELETE /categories/{id}` removes
the category's links to clients) and §3.2 (the clients endpoints). The contract already documents
the full-replacement `PUT` [FIX W-01], the search fields [NEW W-08], the "Categories not found"
rule [FIX W-26] and the duplicate-email message. Background is in `specs/email-sender/README.md`:
§4 (`email-validator` through `pydantic[email]` arrives with API-5), §5 (layout and layer rules),
§6 (every query filters `is_deleted = false`, every Email Sender endpoint takes `PrincipalDep`,
relationships load with `selectin`, no bare dicts between layers, a unique-index violation is
mapped to `ConflictError` in the repository), §10 W-01, W-02, W-08, W-26 and §11 D5 (domain data
is global, no owner column) and D28 (`skip`/`limit`). This spec restates the backend.md section.
Where they differ, this spec wins.

What API-2 to API-4 left in `api/` (specs `specs/features/010-api-async-database.md`,
`011-api-core-schemas.md` and `012-api-categories.md`):

- `app/models/base.py`: `Base` with `NAMING_CONVENTION`, `IdMixin`, `TimestampMixin` (Python-side
  `default`/`onupdate` `utc_now`), `SoftDeleteMixin` (`is_deleted` indexed, Python-side
  `default=False`; `deleted_at`) and `utc_now()`. `app/models/__init__.py` imports `Base` and
  `Category` and lists them in `__all__`. Alembic sees only the tables imported there.
- `app/models/category.py`: `Category` with the partial unique index
  `Index("uq_categories_name_not_deleted", "name", unique=True, postgresql_where=text("is_deleted = false"))`
  in `__table_args__`. This is the pattern for `clients.primary_email`.
- `app/schemas/base.py`: `BaseSchema`, `Page[T]` (`items`, `total`), `PageParams` and
  `PageParamsDep` (`skip` ≥ 0 default 0, `limit` 1 to 1000 default 100; 422 outside).
  `app/schemas/categories.py`: `CategorySchema`, and `CategoryName =
  Annotated[str, AfterValidator(validate_category_name)]`, which trims the name and raises
  `ValueError` with the contract's messages. The company name rule follows the same pattern.
- The categories area is the pattern to copy: `app/repositories/category_repository.py`
  (a `_not_deleted()` select helper; writes commit; `_commit_name` catches `IntegrityError`, rolls
  back and raises `ConflictError`), `app/services/category_service.py` (only domain errors),
  `app/api/categories.py` (an `APIRouter` with prefix and tag, each endpoint taking `PrincipalDep`
  and a `...ServiceDep`, no `try`/`except`), `get_category_service` / `CategoryServiceDep` in
  `app/dependencies.py`, and `app.include_router(categories.router)` in `create_app`
  (`app/main.py`). The domain error handler there maps `NotFoundError` to 404 and the others to
  400 with `{"detail": str(exc)}`.
- `CategoryService.delete` only soft deletes today. 012 left out the step that removes the
  category's client links, because `client_category` did not exist yet. This item adds it, as
  the contract's §3.1 says.
- Migrations: the head is `315fac03750b` (`migrations/versions/315fac03750b_add_categories.py`).
  `migrations/script.py.mako` already renders a ruff-clean header. The installed versions are
  SQLAlchemy 2.1.5, Alembic 1.20.0, FastAPI 0.143.0 and Pydantic 2.14.0.
- Tests: `tests/conftest.py` resets `emailsender_test` once per run and migrates it. The per-test
  `session_factory` lets code under test commit and rolls everything back afterwards. The
  `client` fixture uses `httpx.ASGITransport`, and `bearer(**claims)` makes an `Authorization`
  header (default `sub` `alice`). The existing modules are `test_categories_schemas.py`,
  `test_categories_service.py` and `test_categories_api.py`, and their style (helpers, 401
  parametrization, exact-detail asserts) is the one to follow.
- `api/pyproject.toml` has `pydantic>=2.11`, and `email-validator` is not installed. `api/Containerfile`
  installs with `uv sync --frozen --no-dev`, so the dependency must be in `api/uv.lock`.

I ran a trial in a scratch copy of `api/` against a throwaway database, which I dropped
afterwards. It confirmed the approach:

- `uv add "pydantic[email]>=2.11"` in `api/` turns the `pydantic>=2.11` line into
  `pydantic[email]>=2.11` and adds `email-validator` 2.3.0 and `dnspython` 2.9.0 to `uv.lock`.
- `EmailStr` (Pydantic 2.14.0, email-validator 2.3.0) strips surrounding whitespace, lowercases
  only the domain (`Jan.Kowalski@Firma.PL` → `Jan.Kowalski@firma.pl`), accepts
  `John <j@example.com>` and returns `j@example.com`, and accepts `@acme.example` and
  `@example.com`. It **rejects** `@b.test`, `@acme.local` and `@localhost` as special-use
  domains, so test data must use `example.com` or `.example` addresses.
- A `client_category` `Table` with two `ForeignKey(..., ondelete="CASCADE")` primary-key columns,
  and a `Client` model with `Index("uq_clients_primary_email_not_deleted", ...,
  postgresql_where=...)` and `categories = relationship(secondary=client_category,
  lazy="selectin", order_by=Category.id)`, autogenerate (`-m "add clients"`) into `clients`
  (`pk_clients`), `ix_clients_is_deleted`, the partial unique index, and `client_category` with
  `pk_client_category`, `fk_client_category_client_id_clients` and
  `fk_client_category_category_id_categories`, both `ondelete='CASCADE'`. After
  `upgrade head`, `alembic check` prints "No new upgrade operations detected." mypy strict
  passes on the model.
- As rendered, the revision fails `ruff check` with four E501 errors (the `create_index` and
  `drop_index` lines for the partial index, and the two `ForeignKeyConstraint` lines). They have
  to be wrapped by hand, as 012 did.
- On PostgreSQL, `Column.icontains(term, autoescape=True)` renders `ILIKE '%' || :term || '%'
  ESCAPE '/'`, with `%`, `_` and `/` escaped in the term. With it, `100%` matches "Acme 100%"
  but not "Acme 1000", `_` matches only a literal underscore, and `\` matches literally. An
  `EXISTS` subquery over `client_category` joined to non-deleted `categories` returns a client
  linked to two matching categories once, and `count()` over `clients` with the same filter
  counts it once. `client.categories.clear()` followed by a commit deletes the client's
  `client_category` rows.

The dev database `emailsender` is shared with the main checkout, whose API migrates it at
startup. It is at `315fac03750b`. If a worktree upgrades it to this item's revision before the
merge, the main checkout's API stops starting ("Can't locate revision"). Generate the revision
and run the migration checks against `emailsender_test` only (see the Acceptance criteria).

The 012 security review (`factory/jobs/012-api-categories/round-1/review-security.md`, note 3)
found that a path ID outside the int32 range, or a NUL byte in a string, ends in a 500. 012 was
merged with that behaviour. This item inherits the same behaviour (see Assumptions).

## Requirements

1. **Dependency.** In `api/`, `uv add "pydantic[email]>=2.11"`. The `pydantic>=2.11` line in
   `pyproject.toml` becomes `pydantic[email]>=2.11`, and `uv.lock` is updated to match. No other
   dependency changes.
2. **Models**, in the new module `app/models/client.py` (SQLAlchemy 2 `Mapped[]`/`mapped_column`
   style):
   - `client_category = Table("client_category", Base.metadata, ...)` with exactly two columns:
     `client_id` (`ForeignKey("clients.id", ondelete="CASCADE")`, primary key) and `category_id`
     (`ForeignKey("categories.id", ondelete="CASCADE")`, primary key). There is no model class,
     no timestamps and no other columns.
   - `Client(IdMixin, TimestampMixin, SoftDeleteMixin, Base)`, table `clients`:
     `company_name` `String(128)` NOT NULL; `primary_email` `String(256)` NOT NULL;
     `additional_emails` `Text` NULL; `phone_number` `String` NULL; `address` `String` NULL;
     `is_active` bool NOT NULL with Python-side `default=True` (no server default, like
     `is_deleted`); `notes` `Text` NULL. [FIX W-02] There is no unique constraint on
     `primary_email`. Instead, `__table_args__` holds the partial unique index
     `Index("uq_clients_primary_email_not_deleted", "primary_email", unique=True,
     postgresql_where=text("is_deleted = false"))`. There is no owner column (D5).
   - `Client.categories: Mapped[list[Category]] = relationship(secondary=client_category,
     lazy="selectin", order_by=Category.id)`. There is no back-reference:
     `app/models/category.py` does not change.
   - `app/models/__init__.py` also imports `Client` and `client_category` and lists them in
     `__all__`.
3. **Migration.** One new Alembic revision, generated in `api/` with
   `uv run alembic revision --autogenerate -m "add clients"` against `emailsender_test` at
   `315fac03750b` (see the Context), then read and corrected by hand.
   - Its `down_revision` is `'315fac03750b'`.
   - `upgrade()` creates `clients` (`pk_clients`), `ix_clients_is_deleted`,
     `uq_clients_primary_email_not_deleted` (`unique=True`, `postgresql_where=sa.text('is_deleted = false')`)
     and `client_category` (`pk_client_category` on both columns, and the two foreign keys named
     by the convention, each with `ondelete='CASCADE'`).
   - `downgrade()` drops `client_category`, both indexes and `clients`.
   - Long lines are wrapped so the file passes `uv run ruff check .` with no `# noqa`. The
     existing revision and `migrations/script.py.mako` do not change.
4. **Schemas**, in the new module `app/schemas/clients.py`, all inheriting `BaseSchema`:
   - A company name rule like `CategoryName`. The value is trimmed (`str.strip()`). Empty after
     trimming raises `ValueError("Company name cannot be empty")`. Longer than 128 characters
     after trimming raises `ValueError("Company name cannot exceed 128 characters")`. The
     validated value is the trimmed name.
   - `ClientCreateSchema`: `company_name` (the rule above), `primary_email: EmailStr`,
     `additional_emails: str | None = None`, `phone_number: str | None = None`,
     `address: str | None = None`, `is_active: bool = True`, `notes: str | None = None`,
     `category_ids: list[int]` defaulting to an empty list. No other field is trimmed or
     validated (parity).
   - `ClientUpdateSchema`: the same fields, defaults and rules (a subclass or a shared base is
     fine).
   - `ClientSchema`: `id: int`, `company_name: str`, `primary_email: str`,
     `additional_emails`, `phone_number`, `address` and `notes` as `str | None`,
     `is_active: bool`, `created_at`, `updated_at` (`datetime`) and
     `categories: list[CategorySchema]`. It dumps exactly the keys `id`, `companyName`,
     `primaryEmail`, `additionalEmails`, `phoneNumber`, `address`, `isActive`, `notes`,
     `createdAt`, `updatedAt` and `categories`.
5. **Repository**: `ClientRepository` in `app/repositories/client_repository.py`, built with an
   `AsyncSession`. It owns every SQLAlchemy query for clients:
   - `get_by_id(client_id)`: the non-deleted client or `None`.
   - `get_all(skip, limit, search)`: non-deleted clients matching `search`, ordered by
     `company_name`, then `id`, with `skip`/`limit` applied.
   - `count(search)`: the number of non-deleted clients matching `search`, counted over
     `clients` with the same filter, before `skip`/`limit` and without a join to
     `client_category`.
   - `exists_by_email(email, exclude_id: int | None = None)`: whether a non-deleted client other
     than `exclude_id` has exactly this `primary_email`.
   - `load_categories(category_ids)`: the non-deleted categories with these IDs, ordered by `id`.
   - `create(data: ClientCreateSchema, categories: list[Category])`: a new client with every
     field of `data` except `category_ids`, linked to `categories`.
   - `update(client, data: ClientUpdateSchema, categories: list[Category])`: overwrites every
     field from `data`, `None` included, and replaces the client's categories with
     `categories`.
   - `soft_delete(client)`: sets `is_deleted = True` and `deleted_at = utc_now()`, and clears the
     client's categories (its `client_category` rows are deleted).
   - Each write commits and returns the client. `create` and `update` catch the `IntegrityError`
     the unique index raises, roll the session back and raise
     `ConflictError(f"Client with email '{email}' already exists")`, never a 500.
6. **Search** [NEW W-08]. `search: str | None`. When it is `None` or `""`, there is no filter.
   Otherwise the term is used as given (not trimmed), and a client matches when its
   `company_name`, `primary_email` or `phone_number` contains the term case-insensitively, or an
   `EXISTS` subquery finds a `client_category` row linking it to a non-deleted category whose
   name contains the term case-insensitively. `%`, `_` and `\` in the term are matched
   literally. Use `icontains(term, autoescape=True)` (verified in the Context) or an equivalent
   explicit `ILIKE ... ESCAPE`. A client that matches through several fields or categories
   appears once in the list and counts once in the total.
7. **Service**: `ClientService` in `app/services/client_service.py`, built with a
   `ClientRepository`. It owns the rules, raises only domain errors and imports nothing from
   `sqlalchemy`:
   - `get_all(skip, limit, search) -> Page[ClientSchema]`: the repository's `get_all` as
     `items` and `count(search)` as `total`. The page is a typed object, not a bare dict.
   - `get_by_id(client_id)`: raises `NotFoundError(f"Client {client_id} not found")` when the
     client is missing or soft-deleted.
   - `create(data)`: first, if `exists_by_email(data.primary_email)`, raise
     `ConflictError(f"Client with email '{email}' already exists")` (with the validated email).
     Then resolve the categories, then call the repository's `create`.
   - `update(client_id, data)`: `get_by_id` first (404), then the same email check excluding
     the client itself (keeping its own email is allowed), then resolve the categories, then
     call the repository's `update`. [FIX W-01] This is a full replacement: an omitted optional
     field becomes `null`, an omitted `isActive` becomes `true`, and an omitted `categoryIds`
     removes every category.
   - `delete(client_id)`: `get_by_id` first (404), then `soft_delete`.
   - Resolving categories [FIX W-26]: drop duplicate IDs, then `load_categories`. If any
     requested ID was not found (unknown or soft-deleted), raise
     `BusinessRuleError("Categories not found: " + ", ".join(...))` with the missing IDs in
     ascending order, for example "Categories not found: 3, 7". Duplicate IDs are not an error.
8. **Category delete removes client links.** `CategoryRepository` gains
   `remove_client_associations(category_id: int) -> None`, which deletes every `client_category`
   row with that `category_id` and does not commit. `CategoryService.delete` calls it after
   `get_by_id` and before `soft_delete`, so `soft_delete`'s commit writes both in one
   transaction. Nothing else in the categories area changes.
9. **Wiring** in `app/dependencies.py`: `get_client_service(session: SessionDep) ->
   ClientService` returns `ClientService(ClientRepository(session))`, and
   `ClientServiceDep = Annotated[ClientService, Depends(get_client_service)]`. Nothing is added
   to `Container`.
10. **Router**: `app/api/clients.py`, `APIRouter(prefix="/clients", tags=["Clients"])`,
    included in `create_app` after the categories router. Every endpoint function takes a
    `PrincipalDep` parameter and a `ClientServiceDep` parameter, and only does HTTP (no
    `try`/`except`, no status chosen from a message):
    - `GET /clients/` with `PageParamsDep` and the query parameter `search: str | None = None`
      → `200 Page[ClientSchema]`;
    - `POST /clients/`, body `ClientCreateSchema` → `201 ClientSchema`;
    - `GET /clients/{client_id}` (`client_id: int`) → `200 ClientSchema`;
    - `PUT /clients/{client_id}`, body `ClientUpdateSchema` → `200 ClientSchema`;
    - `DELETE /clients/{client_id}` → `204` with an empty body.
    The existing handlers produce the errors: 401 without a valid token, 404 and 400 from the
    domain handler, 422 from validation. There is no `/clients/bulk` route and no route without
    the trailing slash.
11. **Tests**, in three new modules in `api/tests/`, against `emailsender_test` through the
    existing fixtures. Test data uses `example.com` or `.example` email addresses. Names that
    the tests compare for order use the same case and plain ASCII letters (for example "Alfa",
    "Beta", "Gamma"), so the database collation doesn't matter.
    - `test_clients_schemas.py` (no database, no HTTP), for both `ClientCreateSchema` and
      `ClientUpdateSchema`:
      - a valid client given in camelCase;
      - `""` rejected with "Company name cannot be empty", and whitespace only rejected with the
        same message;
      - `"  Acme Sp. z o.o.  "` validated to `"Acme Sp. z o.o."`;
      - 129 characters rejected with "Company name cannot exceed 128 characters", and 128
        accepted;
      - `"not-an-email"` rejected as `primaryEmail`;
      - with only `companyName` and `primaryEmail` given, the other fields are `None`,
        `is_active` is `True` and `category_ids` is `[]`.

      Also, `ClientSchema` validated from a `Client` object with one category dumps exactly the
      eleven keys from Requirement 4, with `categories` holding `CategorySchema` dumps.
    - `test_clients_service.py`, a `ClientService(ClientRepository(session))` on a session from
      `session_factory`, with categories created through `CategoryRepository`. The backend.md
      ten, each its own test:
      1. create with categories (the client has them, ordered by `id`);
      2. a duplicate email is rejected (`ConflictError` with the contract message);
      3. [W-02] the email of a soft-deleted client can be reused;
      4. update replaces every field: a client created with `notes`, `phoneNumber`, `address`,
         `additionalEmails`, `isActive=False` and a category, then updated with only
         `companyName` and `primaryEmail`, has those four fields `None`, `is_active` `True` and
         no categories;
      5. an update to an email taken by another client is rejected;
      6. delete clears the categories (no `client_category` row for the client remains, and
         `get_by_id` raises `NotFoundError` "Client {id} not found");
      7. unknown `categoryIds` give `BusinessRuleError` "Categories not found: …", with an
         unknown ID and a soft-deleted category's ID listed in ascending order;
      8. `get_all` leaves out deleted clients;
      9. `search` finds by company name, email, phone and category name, case-insensitively;
      10. `total` ignores `skip`/`limit`.

      Plus these:
      - an update keeping its own email is allowed;
      - duplicate `categoryIds` give one link and no error;
      - a client linked to two categories that both match the search appears once, with
        `total` 1;
      - `search="100%"` finds "Acme 100%" but not "Acme 1000", and `search="_"` finds nothing
        when no client has an underscore;
      - the list is ordered by company name, then `id` (two clients with the same company name
        come in `id` order);
      - a repository race test: calling `ClientRepository.create` twice with the same email
        (bypassing the service check) raises `ConflictError`, not `IntegrityError`.
    - `test_clients_api.py`, through `client` and `bearer`:
      - 401 `{"detail": "Invalid or missing access token"}` with
        `www-authenticate: Bearer realm="demo-api"` and no token, on each of the five endpoints;
      - `POST` answers 201 with exactly the `ClientSchema` keys, the trimmed company name and its
        categories as `{id, name, createdAt, updatedAt}`, and `GET /clients/{id}` answers 200
        with the same client;
      - `GET /clients/` answers a body with exactly the keys `items` and `total`. With three
        clients, `?limit=2` gives the first two by company name and `total` 3, `?skip=2&limit=2`
        gives the third and `total` 3, and `?search=<term>` gives the matching client and
        `total` 1. A client created with `alice`'s token is listed for `bearer(sub="bob")` (D5);
      - `PUT` with only `companyName` and `primaryEmail` answers 200 with `additionalEmails`,
        `phoneNumber`, `address` and `notes` `null`, `isActive` `true` and `categories` `[]`;
      - `DELETE` answers 204 with an empty body. Afterwards `GET /clients/` omits the client,
        `GET /clients/{id}` answers 404, and a second `DELETE` answers 404;
      - 400 with the exact contract `detail` for: `POST` with a taken email, `PUT` to a taken
        email, and `POST` with an unknown category ID ("Categories not found: <id>");
      - `GET`, `PUT` and `DELETE` on an unknown ID answer `404 {"detail": "Client <id> not found"}`;
      - 422 for `POST {"companyName": "", ...}` (the `msg` contains "Company name cannot be
        empty"), for an invalid `primaryEmail`, and for `GET /clients/?limit=0`;
      - deleting a category removes it from its clients: after
        `DELETE /categories/{category_id}`, `GET /clients/{id}` answers 200 with that category
        missing from `categories`, and other categories of the client are kept.
    - `tests/conftest.py` and every existing test module do not change.
12. Strict mypy and ruff pass on all new and changed code, with no new `# type: ignore` or
    `# noqa` and no config changes.
13. No doc changes. `api-contract.md` §2, §3.1 and §3.2 already describe this behaviour, the
    full-replacement `PUT` included. README §4 already names `pydantic[email]` for API-5.
    `AGENTS.md` lists no API routes or dependencies. The checkout updates its environment
    automatically on `uv run`, and the sandbox image on rebuild.

## Acceptance criteria

All commands run in `api/` with PostgreSQL reachable on localhost:5432 (any run mode's).
`TEST_DB` below stands for
`postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender_test`.

1. **Validation.** `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests` all pass.
   The pytest summary includes the existing notes, core, database and categories tests, all
   still passing.
2. **Dependency.** `grep -n 'pydantic\[email\]>=2.11' pyproject.toml` matches,
   `grep -n 'name = "email-validator"' uv.lock` matches, and `uv lock --check` succeeds.
3. **Schema tests.** `uv run pytest tests/test_clients_schemas.py -v` passes and lists the cases
   from Requirement 11 for both schemas, plus the `ClientSchema` keys test.
4. **Service tests.** `uv run pytest tests/test_clients_service.py -v` passes and lists the ten
   backend.md tests and the six additional tests from Requirement 11.
5. **Endpoint tests.** `uv run pytest tests/test_clients_api.py -v` passes and lists tests for:
   401 on each of the five endpoints; 201 and 200 (`GET` by ID); the `Page` shape with `skip`,
   `limit`, `search` and `total`; another user seeing the client; the full-replacement `PUT`;
   204 and the follow-up 404s; 400 (duplicate email on `POST` and `PUT`, unknown category);
   404 (`GET`, `PUT`, `DELETE`); 422 (empty company name, invalid email, `limit=0`); and a
   category delete removing the category from the client.
6. **Migration.** `ls migrations/versions/` shows exactly two revision files besides `.gitkeep`.
   In the new one, `grep -n "down_revision" <file>` shows `'315fac03750b'`, and
   `grep -n "uq_clients_primary_email_not_deleted\|postgresql_where\|pk_client_category" <file>`
   matches in `upgrade()`. `grep -c "ondelete='CASCADE'" <file>` prints 2.
   `grep -n "unique=True\|UniqueConstraint" app/models/client.py` shows only the partial index.
7. **No drift and a clean round trip.** After `uv run pytest`,
   `API_DATABASE_URL=$TEST_DB uv run alembic check` prints "No new upgrade operations detected.",
   and `API_DATABASE_URL=$TEST_DB uv run alembic downgrade 315fac03750b` followed by
   `API_DATABASE_URL=$TEST_DB uv run alembic upgrade head` both succeed. Do not upgrade the
   shared dev database `emailsender` from the worktree (see the Context).
8. **Routes and tag.** `uv run python -c "from app.main import create_app; s = create_app().openapi(); print({p: sorted({t for op in s['paths'][p].values() for t in op['tags']}) for p in s['paths'] if p.startswith('/clients')})"`
   prints `{'/clients/': ['Clients'], '/clients/{client_id}': ['Clients']}`.
9. **Auth on every endpoint.** `grep -c "PrincipalDep" app/api/clients.py` prints at least 6
   (the import plus five endpoints), and `grep -n "dependencies=\|include_in_schema" app/api/clients.py`
   matches nothing.
10. **Running API.** `API_DATABASE_URL=$TEST_DB uv run uvicorn app.main:create_app --factory --port 8011`
    starts (its log shows "Application startup complete."), and
    `curl -si "http://localhost:8011/clients/?search=a"` answers `401` with
    `{"detail":"Invalid or missing access token"}` and `www-authenticate: Bearer realm="demo-api"`.
    Port 8001 may already be taken by the main checkout's API. Any free port works.
11. **Layering.** `grep -rn "sqlalchemy" app/api/clients.py app/services/client_service.py`
    matches nothing, and `grep -n "except\|ValueError" app/api/clients.py` matches nothing.
12. **Category delete.** `grep -n "remove_client_associations" app/repositories/category_repository.py app/services/category_service.py`
    matches in both files, and the category-delete endpoint test from criterion 5 passes.
13. **Scope.** `git diff --name-only main...HEAD` lists only files under `api/` plus
    `specs/features/013-api-clients.md`. Nothing under `bff/`, `web/`, `keycloak/`,
    `.devcontainer/`, `compose.yaml`, `Makefile`, `AGENTS.md` or `specs/email-sender/` changes.
    `api/tests/conftest.py`, the existing test modules, `api/migrations/env.py`,
    `api/migrations/script.py.mako`, `api/migrations/versions/315fac03750b_add_categories.py`,
    `api/app/models/category.py`, `api/.env.example` and `api/Containerfile` are unchanged, and
    `git diff main...HEAD -- api/pyproject.toml` shows only the `pydantic` line.

## Out of scope

- `POST /clients/bulk` and its schemas (API-6), the demo seed (API-14), and the clients screen
  and its API functions in `web/` (UI-7).
- Filters or options beyond `skip`, `limit` and `search`: no `is_active` or category filter, no
  sort parameter, no `include_deleted` for clients. No search on `additionalEmails`, `address`
  or `notes`, and no trimming of the search term.
- Trigram or full-text indexes, an index on `client_category.category_id`, or a
  `Category.clients` back-reference.
- Validating or trimming `additionalEmails`, `phoneNumber`, `address` or `notes`, and
  case-insensitive email uniqueness.
- `isDeleted`/`deletedAt` in `ClientSchema`, restoring a deleted client, or hard delete.
- Any change to the categories area beyond `remove_client_associations` and its call in
  `CategoryService.delete`, including the 012 security note (int32 path IDs, NUL bytes).
- An owner column or per-user filtering (D5).
- Changes to ruff or mypy configuration, `conftest.py`, `env.py`, the revision template,
  logging or settings.
- Changes to `api-contract.md`, `AGENTS.md`, `specs/email-sender/`, the BFF, `web/` or the
  notes demo.
- Committing the worktree's unrelated uncommitted change to `web/package-lock.json`.
- Upgrading the shared dev database `emailsender` from the worktree.

## Assumptions

- The repository's `create` and `update` take the loaded `Category` objects, not
  `category_ids` as backend.md writes it. Reason: the service has to load them anyway for the
  W-26 check, and passing them on avoids a second query and keeps the rule in the service.
- Missing category IDs are listed in ascending order. Reason: it is deterministic whatever the
  request order, and it matches the contract's example "3, 7".
- The email check runs before the category check on create and update. Reason: API-6 gives this
  order for its rows and reuses this path.
- Email uniqueness is exact on the value as `EmailStr` returns it. The domain is lowercased and
  the local part is kept, so `Jan@firma.pl` and `jan@firma.pl` can coexist. Reason: this is
  parity with the old unique constraint on the stored value, and backend.md asks for an index
  on `primary_email`. It is a product rule a human may want to change, and changing it to
  case-insensitive (an index on `lower(primary_email)`) is cheaper before this migration merges.
- The search term is not trimmed, and an absent or empty `search` means no filter. Reason: the
  contract defines no trimming, and `ILIKE '%%'` would match every client anyway.
- A client's `categories` are ordered by category `id` in every response. Reason: a stable chip
  order. The contract does not say, and `selectin` loading has no order of its own.
- A soft-deleted client answers 404 on `GET`, `PUT` and `DELETE`, so a second delete is a 404.
  Reason: this matches categories (012), and README §6 says every query filters deleted rows.
- `GET /clients/` lists inactive clients too. Reason: the contract says "non-deleted clients",
  and UI-7 and UI-11 show inactive clients with a chip.
- `"isActive": null` and `"categoryIds": null` answer 422. Reason: the contract gives defaults
  only for omitted fields, and UI-7 always sends every field with real values.
- Out-of-range integer IDs (in the path or in `categoryIds`) and NUL bytes in strings or in
  `search` end in a 500, as they do for categories. Reason: 012 was merged with this known
  behaviour (its security note 3), and fixing it for clients alone would make the two areas
  differ. Whether to fix it, here or in a separate item for both areas, is a security decision
  for a human.
- There is no index on `client_category.category_id`. Reason: backend.md asks for none, and
  only a category delete filters on it, in a demo-sized table.
- No doc change. Reason: the contract already documents every behaviour this item builds, and
  backend.md asks API-5 for none.
- The migration and live-API checks run against `emailsender_test`. Reason: the main checkout's
  API migrates `emailsender` at startup and cannot start once that database holds a revision
  `main` doesn't have.
