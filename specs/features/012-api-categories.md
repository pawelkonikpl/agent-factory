# API categories: model, migration and CRUD endpoints

> Feature: Add categories to the API: model, migration and CRUD endpoints under `/categories/` with soft delete and a partial unique index on the name, every endpoint behind `PrincipalDep`, as specified in `specs/email-sender/backend.md` API-4 (covers B3)

## Context

This is roadmap item API-4 of Phase 4 (Email Sender API), the first item that adds a table and
a production Email Sender route. The source of truth is `specs/email-sender/backend.md`,
"API-4: Categories" (Requirements, Pitfalls, Acceptance criteria) plus that file's "Rules for
every item". The wire format is in `specs/email-sender/api-contract.md` §0 (conventions,
errors), §2 (`CategorySchema`, `CategoryCreateSchema` / `CategoryUpdateSchema`) and §3.1 (the
four endpoints). Background is in `specs/email-sender/README.md`: §5 (layout and layer
rules), §6 (API conventions: every query filters `is_deleted = false`, every Email Sender
endpoint takes `PrincipalDep`, three validation layers, a unique-index violation mapped to
`ConflictError` in the repository), §10 W-02 (a global unique constraint blocked re-creating a
soft-deleted name), W-04 (the old categories router had no auth) and §11 D5 (categories are
global: no owner column). This spec restates the backend.md section; where they differ, this
spec wins.

What API-2 and API-3 left in `api/` (specs `specs/features/010-api-async-database.md` and
`specs/features/011-api-core-schemas.md`):

- `app/models/base.py`: `Base` with `NAMING_CONVENTION`, `IdMixin`, `TimestampMixin`
  (`created_at`/`updated_at`, Python-side default and `onupdate` `utc_now`), `SoftDeleteMixin`
  (`is_deleted` indexed, `deleted_at`), and the helper `utc_now()`. `app/models/__init__.py`
  imports `Base` only; it must import every model module so Alembic sees the tables.
- `app/database.py`: `create_engine`, `create_session_factory` (`expire_on_commit=False`),
  `run_migrations(url)`. The lifespan in `app/main.py` runs it at startup.
- `migrations/env.py` (async template, `target_metadata = Base.metadata`, `compare_type` and
  `compare_server_default` on; URL from the config, else `Settings().database_url`, so
  `API_DATABASE_URL` in the environment wins over `api/.env`). `migrations/versions/` holds only
  `.gitkeep`: this item writes the first revision. `migrations/script.py.mako` is the stock
  template. `api/Containerfile` already copies `migrations/`.
- `app/schemas/base.py`: `BaseSchema` (camelCase out, camelCase or snake_case in,
  `from_attributes=True`), `Page`, `PageParams`. `app/schemas/notes.py` holds the notes schemas.
- `app/errors.py`: `DomainError`, `NotFoundError`, `ConflictError`, `BusinessRuleError`.
  `create_app` in `app/main.py` maps them in one handler (`NotFoundError` → 404, the others →
  400, body `{"detail": str(exc)}`), and includes routers with `app.include_router(...)`
  (only `notes.router` today).
- `app/dependencies.py`: `PrincipalDep`, `SessionDep` (one `AsyncSession` per request from the
  container's factory, no router uses it yet), `NoteServiceDep`. README §5: per-request
  services are built by dependency functions from the per-request session.
- The pattern to follow is the notes area: `app/api/notes.py` (an `APIRouter` with a prefix and
  tag, each endpoint taking `PrincipalDep` and a `...ServiceDep`), `app/services/note_service.py`,
  `app/repositories/note_repository.py`. API-5 will call `CategoryRepository` by that name
  (`CategoryRepository.remove_client_associations`).
- Tests: `tests/conftest.py` resets `emailsender_test` once per run and migrates it with
  `run_migrations`; the per-test `session_factory` binds sessions to one connection inside an
  outer transaction (`join_transaction_mode="create_savepoint"`), so code under test may commit
  and everything is rolled back after the test. The `client` fixture talks to the app over
  `httpx.ASGITransport`; `bearer(**claims)` makes an `Authorization` header (default `sub`
  `alice`). `tests/test_database.py` compares `alembic_version` with the computed Alembic head,
  so it keeps passing with a revision. Existing test modules are named `test_core_schemas.py`
  and `test_core_api.py` (README §5: `test_<area>_*.py`).
- Installed: SQLAlchemy 2.1.5, Alembic 1.20.0, FastAPI 0.143.0, Pydantic 2.14.0. Ruff checks
  `migrations/` too (`uv run ruff check .` in `api/`, rules E F W I UP B SIM RUF ASYNC, line
  length 100, `py311`); `uv run mypy app tests` does not cover `migrations/`.
- The BFF proxy (`bff/app/api/proxy.py`, `/{path:path}`) keeps the trailing slash, so the SPA's
  `/api/categories/` reaches `/categories/`. The BFF does not change (README §3.2).

A trial run in a scratch copy of `api/` against a throwaway database confirmed the approach:

- A model with `__table_args__ = (Index("uq_categories_name_not_deleted", "name", unique=True,
  postgresql_where=text("is_deleted = false")),)` autogenerates `op.create_index(...,
  unique=True, postgresql_where=sa.text('is_deleted = false'))` plus
  `ix_categories_is_deleted`, and after `upgrade head`, `alembic check` prints "No new upgrade
  operations detected."
- The generated revision fails `ruff check` as rendered: UP035 (`typing.Sequence`), I001
  (import order), UP007 three times (`Union[...]`), W291 (the empty `Revises: ` line of a first
  revision) and E501 on the two long `create_index` / `drop_index` lines. The first three come
  from `migrations/script.py.mako`, so every later item's revision would hit them too.
- A duplicate non-deleted name raises `sqlalchemy.exc.IntegrityError` (asyncpg
  `UniqueViolationError`, SQLSTATE 23505) at flush or commit; after `await session.rollback()`
  the session, including the per-test savepoint session, is usable again.

The dev database `emailsender` is shared with the main checkout, whose API (running on 8001 in
the dev container) migrates it at startup. If a worktree upgrades `emailsender` to this item's
revision before it is merged, the main checkout's API stops starting ("Can't locate revision").
The checks below therefore migrate only `emailsender_test`, which every test run resets.

## Requirements

1. **Model** `Category` in `app/models/category.py`, table `categories`, SQLAlchemy 2
   `Mapped[]`/`mapped_column` style: `name` `String(64)` NOT NULL, plus `IdMixin`,
   `TimestampMixin` and `SoftDeleteMixin` from `app/models/base.py`. No owner or `user_sub`
   column (D5). [FIX W-02] No unique constraint on `name`; instead a partial unique index
   `Index("uq_categories_name_not_deleted", "name", unique=True,
   postgresql_where=text("is_deleted = false"))` in `__table_args__`. `app/models/__init__.py`
   imports `Category` and lists it in `__all__`.
2. **Migration**: one Alembic revision, generated in `api/` with
   `uv run alembic revision --autogenerate -m "add categories"` and then read and corrected by
   hand. It creates `categories` (with `pk_categories`), `ix_categories_is_deleted` and
   `uq_categories_name_not_deleted` with `unique=True` and its `postgresql_where`; its
   `downgrade()` drops the two indexes and the table. `down_revision` is `None` (the first
   revision). The file passes `uv run ruff check .` with no `# noqa` and no ruff config change
   (wrap the long lines, drop the trailing space after `Revises:`).
3. **Revision template**: `migrations/script.py.mako` renders a ruff-clean header for later
   revisions: `from collections.abc import Sequence` instead of `typing`, the `alembic` and
   `sqlalchemy` imports in the order ruff's isort wants, and `str | Sequence[str] | None`
   instead of `Union[...]` for `down_revision`, `branch_labels` and `depends_on`. Nothing else
   in the template changes.
4. **Schemas**, `app/schemas/categories.py`, all inheriting `BaseSchema`:
   - `CategoryCreateSchema` and `CategoryUpdateSchema`, each with one field `name: str`, sharing
     one validation rule: the value is trimmed (`str.strip()`); empty after trimming raises
     `ValueError("Category name cannot be empty")`; longer than 64 characters after trimming
     raises `ValueError("Category name cannot exceed 64 characters")`. The validated value is
     the trimmed name. Use a validator raising `ValueError`, not `Field(max_length=...)`, so
     the 422 `msg` carries the contract's message (with Pydantic's `Value error, ` prefix).
   - `CategorySchema`: `id: int`, `name: str`, `created_at: datetime`, `updated_at: datetime`,
     dumped as exactly `{"id", "name", "createdAt", "updatedAt"}`.
5. **Repository** `CategoryRepository` in `app/repositories/category_repository.py`, built
   with an `AsyncSession`, owning every SQLAlchemy query for categories:
   - `get_by_id(id)`, `get_by_name(name)`: the non-deleted category or `None`;
   - `get_all(include_deleted: bool = False)`: ordered by `id`; non-deleted only unless
     `include_deleted`;
   - `exists_by_name(name, exclude_id: int | None = None)`: whether a non-deleted category
     other than `exclude_id` has exactly this name;
   - `create(name)`, `update(category, name)`, `soft_delete(category)`: each writes and commits
     the session and returns the category. `soft_delete` sets `is_deleted = True` and
     `deleted_at` to `utc_now()`.
   - `create` and `update` catch the `IntegrityError` the unique index raises (two concurrent
     requests can both pass the service check), roll the session back and raise
     `ConflictError("Category with name '{name}' already exists")`, never a 500.
6. **Service** `CategoryService` in `app/services/category_service.py`, built with a
   `CategoryRepository`; it owns the rules and raises only domain errors:
   - `get_all(include_deleted: bool = False)`;
   - `get_by_id(id)`: raises `NotFoundError(f"Category {id} not found")` when the category is
     missing or soft-deleted;
   - `create(data: CategoryCreateSchema)`: if `exists_by_name(name)`, raises
     `ConflictError(f"Category with name '{name}' already exists")` (with the trimmed name);
   - `update(id, data: CategoryUpdateSchema)`: `get_by_id` first (404), then the same
     uniqueness check excluding the category itself, so keeping its own name is allowed;
   - `delete(id)`: `get_by_id` first (404), then `soft_delete`. (Removing client links is
     API-5.)
7. **Wiring** in `app/dependencies.py`: `get_category_service(session: SessionDep) ->
   CategoryService` returning `CategoryService(CategoryRepository(session))`, and
   `CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]`. Nothing is
   added to `Container`.
8. **Router** `app/api/categories.py`: `APIRouter(prefix="/categories", tags=["Categories"])`,
   included in `create_app` next to the notes router. Every endpoint function has a
   `PrincipalDep` parameter [FIX W-04] and a `CategoryServiceDep` parameter, and only does HTTP
   (no `try`/`except`, no status chosen from a message):
   - `GET /categories/` with the query parameter `include_deleted: bool = False` →
     `200 list[CategorySchema]` (a plain array, no pagination);
   - `POST /categories/`, body `CategoryCreateSchema` → `201 CategorySchema`;
   - `PUT /categories/{category_id}` (`category_id: int`), body `CategoryUpdateSchema` →
     `200 CategorySchema`;
   - `DELETE /categories/{category_id}` → `204` with an empty body.
   The errors come from the existing handlers: 401 without a valid token, 404 and 400 from the
   domain handler, 422 from validation. No route is added without the trailing slash and no
   `GET /categories/{category_id}`.
9. **Tests**, in `api/tests/`, against `emailsender_test` through the existing fixtures:
   - `test_categories_schemas.py` (no database, no HTTP), for both `CategoryCreateSchema` and
     `CategoryUpdateSchema`: a valid name; `""` rejected with "Category name cannot be empty";
     whitespace only rejected with the same message; `"  Klienci VIP  "` validated to
     `"Klienci VIP"`; 65 characters rejected with "Category name cannot exceed 64 characters";
     64 characters accepted. Also: `CategorySchema` validated from a `Category` object dumps
     exactly the keys `id`, `name`, `createdAt`, `updatedAt`.
   - `test_categories_service.py`, a `CategoryService(CategoryRepository(session))` on a session
     from `session_factory`, with these nine tests: create; duplicate name rejected
     (`ConflictError` with the contract message); duplicate allowed after soft delete; update;
     update to a name taken by another category rejected; update keeping its own name; delete
     (a later `get_by_id` raises `NotFoundError` "Category {id} not found"); `get_all` without
     deleted; `get_all(include_deleted=True)` includes them, ordered by `id`. Plus one
     repository test for the race: calling `CategoryRepository.create` twice with the same name
     (bypassing the service check) raises `ConflictError`, not `IntegrityError`.
   - `test_categories_api.py`, through `client` and `bearer`:
     - 401 `{"detail": "Invalid or missing access token"}` without a token on each of the four
       endpoints;
     - `POST` answers 201 with exactly `id`, `name`, `createdAt`, `updatedAt` and the trimmed
       name; a following `GET /categories/` (a separate request) lists it; a category created
       with `alice`'s token is listed for `bearer(sub="bob")` (D5);
     - `PUT` answers 200 with the new name; `DELETE` answers 204 with an empty body; afterwards
       `GET /categories/` omits it and `GET /categories/?include_deleted=true` includes it; a
       second `DELETE` of it answers 404;
     - `POST` with a taken name and `PUT` to a taken name answer
       `400 {"detail": "Category with name '<name>' already exists"}`;
     - `PUT` and `DELETE` on an unknown ID answer `404 {"detail": "Category <id> not found"}`;
     - `POST {"name": ""}` and `PUT {"name": "   "}` answer 422, and the error's `msg` contains
       "Category name cannot be empty".
   - `tests/conftest.py`, `tests/test_notes_api.py`, `tests/test_database.py`,
     `tests/test_core_api.py` and `tests/test_core_schemas.py` do not change.
10. Strict mypy and ruff pass on all new code with no new `# type: ignore` or `# noqa` and no
    config changes.
11. No doc changes: the API-4 section asks for none, `api-contract.md` §2 and §3.1 already
    describe these endpoints (the "remove its links to clients" step of `DELETE` arrives with
    API-5), and `AGENTS.md` lists no API routes or modules.

## Acceptance criteria

All commands run in `api/` with PostgreSQL reachable on localhost:5432 (any run mode's).
`TEST_DB` below stands for
`postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender_test`.

1. **Validation.** `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests` all pass;
   the pytest summary includes the existing notes, core and database tests.
2. **Schema tests.** `uv run pytest tests/test_categories_schemas.py -v` passes and lists the
   six cases from Requirement 9 for both schemas, plus the `CategorySchema` keys test.
3. **Service tests.** `uv run pytest tests/test_categories_service.py -v` passes and lists the
   nine service tests and the repository race test from Requirement 9.
4. **Endpoint tests.** `uv run pytest tests/test_categories_api.py -v` passes and lists tests
   for 401 on each endpoint, 201, 200, 204, 400 (POST and PUT), 404 (PUT and DELETE, and a
   second DELETE), 422, `include_deleted=true`, and another user seeing the category.
5. **Migration.** `ls migrations/versions/` shows exactly one revision file besides
   `.gitkeep`; `grep -n "postgresql_where" migrations/versions/*.py` matches in `upgrade()`;
   `grep -n "uq_categories_name_not_deleted" migrations/versions/*.py` matches;
   `grep -rn "UniqueConstraint\|unique=True" app/models/category.py` shows only the partial
   index.
6. **No drift and a clean round trip.** After `uv run pytest`:
   `API_DATABASE_URL=$TEST_DB uv run alembic check` prints "No new upgrade operations detected.";
   `API_DATABASE_URL=$TEST_DB uv run alembic downgrade base` and then
   `API_DATABASE_URL=$TEST_DB uv run alembic upgrade head` both succeed. (Do not upgrade the
   shared dev database `emailsender` from the worktree, see Context.)
7. **Template.** `grep -n "Union\|from typing" migrations/script.py.mako` matches nothing, and
   `grep -n "collections.abc import Sequence" migrations/script.py.mako` matches.
8. **Routes and tag.** `uv run python -c "from app.main import create_app; s = create_app().openapi(); print({p: sorted({t for op in s['paths'][p].values() for t in op['tags']}) for p in s['paths'] if p.startswith('/categories')})"`
   prints `{'/categories/': ['Categories'], '/categories/{category_id}': ['Categories']}`.
9. **Auth on every endpoint.** `grep -c "PrincipalDep" app/api/categories.py` prints at least
   5 (the import plus four endpoints), and `grep -n "dependencies=\|include_in_schema" app/api/categories.py`
   matches nothing.
10. **Running API.** `API_DATABASE_URL=$TEST_DB uv run uvicorn app.main:create_app --factory --port 8011`
    starts (its log shows "Application startup complete."), and
    `curl -si http://localhost:8011/categories/` answers `401` with
    `{"detail":"Invalid or missing access token"}` and `www-authenticate: Bearer realm="demo-api"`.
    (Port 8001 may already be taken by the main checkout's API; any free port works.)
11. **Layering.** `grep -rn "sqlalchemy" app/api/categories.py app/services/category_service.py`
    matches nothing; `grep -n "except\|ValueError" app/api/categories.py` matches nothing.
12. **Scope.** `git diff --name-only main` lists only files under `api/` plus
    `specs/features/012-api-categories.md`; nothing under `bff/`, `web/`, `keycloak/`,
    `.devcontainer/`, `compose.yaml`, `Makefile`, `AGENTS.md` or `specs/email-sender/` changes,
    and `api/pyproject.toml`, `api/uv.lock`, `api/.env.example`, `api/Containerfile`,
    `api/tests/conftest.py` and `api/migrations/env.py` are unchanged.

## Out of scope

- `client_category`, `remove_client_associations` and anything about clients (API-5); the
  demo seed (API-14, which creates no categories).
- A `GET /categories/{id}` endpoint, pagination, search or sorting options for categories, an
  `isDeleted`/`deletedAt` field in `CategorySchema`, restoring a deleted category, or hard
  delete.
- Case-insensitive or accent-insensitive name uniqueness.
- An owner column or per-user filtering (D5).
- Changing ruff or mypy configuration, excluding `migrations/` from ruff, or a ruff post-write
  hook in `alembic.ini`.
- Changes to `api-contract.md`, `AGENTS.md`, the BFF, `web/` (the categories screen is UI-6),
  the notes demo or the test fixtures in `conftest.py`.
- Logging in the repository or service, or new settings.

## Assumptions

- A soft-deleted category answers 404 on `PUT` and `DELETE` (so a second delete is a 404).
  Reason: README §6 says every query filters `is_deleted = false`, and the contract lists only
  204 and 404 for `DELETE`.
- Name uniqueness is exact and case-sensitive after trimming ("Klienci" and "klienci" can
  coexist). Reason: parity with the old version, the index is on `name` as stored, and neither
  backend.md nor the contract asks for more. This is a product rule a human may want to change.
- `GET /categories/?include_deleted=true` returns deleted categories with no field marking them
  deleted. Reason: the contract's `CategorySchema` is `{ id, name, createdAt, updatedAt }`.
- The repository commits its writes and maps the index's `IntegrityError` to `ConflictError`.
  Reason: backend.md's Pitfalls put the mapping in the repository, which needs the flush and
  commit there; the per-test savepoint session allows commits.
- The partial index has the explicit name `uq_categories_name_not_deleted`. Reason: an `Index`
  needs a name in `__table_args__`, and a fixed name makes the migration checkable; API-5 can
  follow the same pattern for `clients.primary_email`.
- `migrations/script.py.mako` is fixed in this item. Reason: this is the first revision ever
  generated, the template is where three of the ruff errors come from, and API-5, API-7, API-9
  and API-10 would otherwise each fix the same lines by hand.
- `get_by_name` stays on the repository though no service method needs it yet. Reason:
  backend.md lists it among the repository methods.
- `PrincipalDep` is a parameter on each endpoint, not a router-level dependency. Reason:
  backend.md says every endpoint takes `PrincipalDep`, and the notes router does the same.
- The migration and live-API checks run against `emailsender_test`, not the dev database.
  Reason: the main checkout's API migrates `emailsender` at startup and cannot start once that
  database holds a revision the main branch does not have yet.
- No `AGENTS.md` change, although its Layout line still describes `api/` as "notes per user".
  Reason: the API-4 section asks for no doc update, and AGENTS.md lists no API routes.
