# Email Sender API items (API-1 to API-14)

Context, tags, the defects (W-xx) and the decisions (D-x) are in `README.md`; request and
response shapes in `api-contract.md`. Each section is one roadmap item in `factory/backlog.md`, Phase 4,
with Goal, Requirements, Pitfalls, Depends on and Acceptance criteria.

Rules for every item:

- Work in the existing `api/` layout (`README.md` §5): router in `app/api/<area>.py`, service in
  `app/services/<area>_service.py`, repository in `app/repositories/<area>_repository.py`,
  models in `app/models/`, schemas in `app/schemas/`, wiring in `app/dependencies.py`.
- An item that adds tables adds one Alembic revision for them, generated with
  `uv run alembic revision --autogenerate -m "<message>"` and then read and corrected by hand
  (partial indexes, CHECK constraints). `uv run alembic check` reports no differences afterwards.
- Tests come with the code (the source's B11 is split across the items): schema tests, service
  tests against the test database, and endpoint tests through the `client` fixture, including
  `401` without a token and every status code the item's endpoints answer. Test names from the
  old project are kept where the sections list them.
- The item ends with `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests` green
  in `api/` (and untouched in `bff/`), and updates `AGENTS.md` and `api-contract.md` where its
  section says so.

---

## API-1: PostgreSQL in all three run modes

Covers B12 (the run-mode part).

### Goal

A PostgreSQL server runs in every run mode, so API-2 can connect to it. No `api/` code changes.

### Requirements

- A `postgres` service on `docker.io/library/postgres:18.6` (a pinned major.minor tag; 18.6 is
  the newest 18.x when this was written) with `POSTGRES_DB`, `POSTGRES_USER` and
  `POSTGRES_PASSWORD` all `emailsender` (demo credentials, in git). No volume. A healthcheck
  `pg_isready -U emailsender -d emailsender` (interval 10 s, timeout 5 s, 5 retries, start
  period 10 s).
- **Host**, `keycloak/docker-compose.yml`: add the service, published as
  `127.0.0.1:5432:5432`. Update the file's header comment (Keycloak and PostgreSQL, dev only).
- **Sandbox**, `compose.yaml`: add the service with `network_mode: "service:keycloak"` and
  `depends_on: [keycloak]`, not published. `api` depends on `postgres` with
  `condition: service_healthy` (and on `keycloak` with `condition: service_started`; one
  `depends_on` can't mix the list and map forms). Update the header comment.
- **Dev container**, `.devcontainer/compose.yaml`: add the service, joined to `keycloak`'s
  namespace, so `localhost:5432` inside `dev` is PostgreSQL. Not published. `dev` depends on
  it with `condition: service_healthy`. `.devcontainer/podman/compose.yaml` extends this file
  and needs nothing: the service has no bind mount, so no `label=disable`.
- `api/.env.example`: add
  `API_DATABASE_URL=postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender`
  with a one-line comment. `api/app/config.py` has `extra="ignore"`, so the API still starts.
- `Makefile`: the `docker-up`, `docker-down` and `docker-logs` help texts mention PostgreSQL
  (port 5432) next to Keycloak.
- `AGENTS.md`:
  - "Layout": `keycloak/` runs Keycloak and PostgreSQL; `.devcontainer/` is the dev container
    plus Keycloak and PostgreSQL.
  - "Run locally": the compose command also starts PostgreSQL on 127.0.0.1:5432 (database,
    user and password `emailsender`); port 5432 clashes with a PostgreSQL already running on the
    host, which has to be stopped first.
  - "Sandbox": a fifth service, `postgres`, not published; `api` starts once it is healthy.
  - "Dev container": PostgreSQL runs as a third container sharing the network, so
    `localhost:5432` inside it is PostgreSQL; an existing dev container must be rebuilt to get
    it ("Dev Containers: Rebuild Container").

### Pitfalls

- Podman resolves short image names only with a registries configuration: use the fully
  qualified `docker.io/library/postgres:18.6`, as the repo does for every image.
- Everything binds to 127.0.0.1 (mission). Only the host mode publishes 5432; the sandbox and
  the dev container don't publish it at all.
- In the shared network namespace PostgreSQL listens on 5432 next to Keycloak's 8080; nothing
  else in the namespace may take 5432.
- `condition: service_healthy` needs the healthcheck; check it with both Podman compose
  providers (docker-compose and podman-compose 1.2 or newer) and with Docker.
- No `api/` code and no new dependency: API-2 makes the API use the database.

### Depends on

Nothing.

### Acceptance criteria

1. `make docker-up` starts Keycloak and PostgreSQL;
   `podman compose -f keycloak/docker-compose.yml exec postgres pg_isready -U emailsender -d emailsender`
   prints "accepting connections", and `podman port` shows 5432 bound to 127.0.0.1 only. The
   same with `CONTAINER_ENGINE=docker`.
2. `make sandbox-up` starts five services; `podman compose exec postgres pg_isready -U emailsender -d emailsender`
   succeeds; `podman compose ps` shows no published 5432; sign-in and the notes demo still work
   on http://localhost:5173.
3. Inside a rebuilt dev container, `bash -c '</dev/tcp/127.0.0.1/5432' && echo open` prints
   `open`, and the post-start servers still come up.
4. `api/.env.example` holds the `API_DATABASE_URL` line; the validation commands in `api/`,
   `bff/` and `web/` pass unchanged.
5. `AGENTS.md` documents PostgreSQL in "Run locally", "Sandbox" and "Dev container", the 5432
   clash and the rebuild.

---

## API-2: Async database layer

Covers B0 (the dependencies), B1 (the infrastructure part), B11 (`conftest.py`).

### Goal

The API connects to PostgreSQL through SQLAlchemy 2 async with asyncpg, migrates itself with
Alembic at startup, and its tests run against a separate test database with real per-test
isolation. No tables yet.

### Requirements

- Dependencies in `api/pyproject.toml`: `sqlalchemy[asyncio]>=2.0`, `asyncpg`, `alembic`.
- Settings (`app/config.py`): `database_url: str` with the `api/.env.example` value as default
  (like `issuer`), and `test_database_url: str | None = None` (`API_TEST_DATABASE_URL`).
- `app/models/base.py`:
  - `NAMING_CONVENTION = {"ix": "ix_%(column_0_label)s", "uq": "uq_%(table_name)s_%(column_0_name)s", "ck": "ck_%(table_name)s_%(constraint_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s", "pk": "pk_%(table_name)s"}`;
  - `Base(DeclarativeBase)` with `MetaData(naming_convention=NAMING_CONVENTION)`;
  - mixins: `IdMixin` (`id` int primary key, autoincrement), `TimestampMixin` (`created_at`,
    `updated_at`: `DateTime(timezone=True)`, NOT NULL, default `datetime.now(UTC)`,
    `updated_at` also on update), `SoftDeleteMixin` (`is_deleted` bool NOT NULL default False,
    **indexed**; `deleted_at` `DateTime(timezone=True)` NULL).
  - [FIX W-22] every date column in every later table is `DateTime(timezone=True)`; defaults
    use `datetime.now(UTC)`, never `utcnow`.
  - `app/models/__init__.py` imports every model module, so Alembic sees all tables.
- `app/database.py`: `create_engine(url) -> AsyncEngine` (`create_async_engine`,
  `pool_pre_ping=True`), `create_session_factory(engine)` (`async_sessionmaker`,
  `expire_on_commit=False`), and `run_migrations(url)`, which calls
  `alembic.command.upgrade(config, "head")` with an absolute `script_location` and
  `sqlalchemy.url` set to `url`.
- Alembic: `api/alembic.ini` and `api/migrations/` from the async template
  (`alembic init -t async migrations`). `env.py` takes the URL from the config when the caller
  set one, else from `Settings().database_url`; `target_metadata = Base.metadata`;
  `compare_type=True`, `compare_server_default=True`. No revision yet: `upgrade head` on an
  empty database only creates `alembic_version`.
- `create_app` (`app/main.py`):
  - takes `session_factory: async_sessionmaker[AsyncSession] | None = None`; without one it
    builds the engine and factory from `settings.database_url`, and disposes the engine on
    shutdown;
  - its `lifespan` first runs `await asyncio.to_thread(run_migrations, settings.database_url)`;
    an error is logged and re-raised, so the API does not start without its database.
- `app/dependencies.py`: the `Container` gains `sessions` (the session factory);
  `get_session` yields one `AsyncSession` per request from it; `SessionDep =
  Annotated[AsyncSession, Depends(get_session)]`.
- `api/Containerfile` also copies `alembic.ini` and `migrations/`, so the sandbox image can
  migrate.
- Tests, `tests/conftest.py`:
  - the test URL is `API_TEST_DATABASE_URL`, else `API_DATABASE_URL` (or the default) with the
    database name replaced by `emailsender_test`. **Guard:** a URL without `test` raises
    `RuntimeError` (never touch the app database);
  - a session-scoped, autouse fixture checks that the server answers, creates the test database
    when it is missing (connecting to the `postgres` database), recreates the `public` schema
    and runs `run_migrations(test_url)`. When the server is not reachable, it fails with
    `PostgreSQL is not reachable at <host>:<port> (API_TEST_DATABASE_URL). Start it with
    make docker-up.` Tests never skip because of the database;
  - [FIX W-25] per test: an engine, one connection, an outer transaction, and a session factory
    bound to that connection with `join_transaction_mode="create_savepoint"`. Code under test may
    commit; the fixture rolls the outer transaction back at the end;
  - the `client` fixture builds `Settings` with the test URL and passes that factory to
    `create_app`. The notes tests keep passing unchanged.
- `AGENTS.md`: "Validation" says `uv run pytest` in `api/` needs PostgreSQL running (any run
  mode's) and creates `emailsender_test` itself; "Run locally" says the API needs PostgreSQL
  (start `make docker-up` first) and migrates at startup.

### Pitfalls

- The async Alembic template's `env.py` calls `asyncio.run()`, which fails inside a running
  event loop: the lifespan runs the migration in a thread (`asyncio.to_thread`); a sync test
  fixture can call it directly.
- asyncpg connections belong to the event loop that opened them, and the repo's pytest config
  gives each test its own loop (`asyncio_default_fixture_loop_scope = "function"`): create the
  engine per test (or with `NullPool`), never share one across tests.
- `httpx.ASGITransport` (the `client` fixture) does not run the lifespan, so it never runs the
  migrations. One test runs the lifespan explicitly (`app.router.lifespan_context(app)`) against
  the test database.
- Lazy loading raises `MissingGreenlet` in async code: `expire_on_commit=False`, and later
  relationships use `selectin` or `selectinload`.
- asyncpg ships no type hints: add `asyncpg-stubs` as a dev dependency or a mypy override for
  `asyncpg`, so `mypy app tests` stays strict elsewhere.
- Don't build the test schema with `Base.metadata.create_all`: the migrations are the schema,
  and running them in tests tests them.
- W-22, W-25: no naive datetimes; no `hash(nodeid)` tricks for unique test data.
- From this item on, every `api/` test run needs PostgreSQL, the factory's own builders and
  reviewers included: the dev container they run in must have been rebuilt after API-1 merged
  (API-1 documents the rebuild), or this item's checks can't pass there.

### Depends on

API-1.

### Acceptance criteria

1. With PostgreSQL up, `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests` pass
   in `api/`, the notes tests included.
2. With PostgreSQL stopped, `uv run pytest` fails at the session fixture with the "PostgreSQL is not reachable" message, and no test is reported as skipped.
3. A test shows that the guard raises `RuntimeError` for a URL without `test`.
4. A test runs the app's lifespan against the test database and finds the current head in
   `alembic_version`.
5. A test proves isolation: it creates a table and a row through the session factory and
   commits, and a separate connection does not see the table.
6. `uv run alembic upgrade head` and then `uv run alembic check` against the dev database
   report no differences.
7. `make docker-up` then `make backend`: the API starts and `/notes` works through the BFF.
   With PostgreSQL stopped, the API exits with the migration error in its log.
8. `make sandbox-up`: the `api` log shows the migration and the notes demo works.
9. `AGENTS.md` "Validation" and "Run locally" say the API and its tests need PostgreSQL.

---

## API-3: Core

Covers B2 (without encryption).

### Goal

The shared pieces every area uses: the camelCase `BaseSchema`, typed domain errors with one
handler, the `Page` response and its `skip`/`limit` parameters.

### Requirements

- `app/schemas.py` becomes the package `app/schemas/` (D29): `notes.py` holds the existing
  note schemas unchanged (update the imports in `app/api/notes.py`); `base.py` holds:
  - `BaseSchema(BaseModel)` with `model_config = ConfigDict(alias_generator=to_camel,
    validate_by_name=True, validate_by_alias=True, serialize_by_alias=True,
    from_attributes=True)`: camelCase out, camelCase or snake_case in;
  - `Page(BaseSchema, Generic[T])` with `items: list[T]` and `total: int`;
  - `PageParams` (`skip: int = Query(0, ge=0)`, `limit: int = Query(100, ge=1, le=1000)`,
    D28) and `PageParamsDep`.
- `app/errors.py` gains `DomainError` with the subclasses `NotFoundError`, `ConflictError` and
  `BusinessRuleError`. `app/main.py` registers one handler for `DomainError` that answers
  `{"detail": str(exc)}` with 404 for `NotFoundError` and 400 for the other two [FIX W-23].
  Services raise these errors; routers don't catch `ValueError` or match exception text.
- Dropped from the source's B2: CORS and `expose_headers`, the `get_current_user` stub
  (`PrincipalDep` exists), the request-logging middleware and `logging.basicConfig` (D30),
  and the OpenAPI description. Each later router declares its tag (*Categories*, *Clients*,
  *Campaigns*, *Emails*, *Configuration*).

### Pitfalls

- The source's `"populate_by_alias": True` is not a Pydantic 2 setting. Use
  `validate_by_name`/`validate_by_alias` (Pydantic 2.11 replaced `populate_by_name` with them)
  and check against the installed Pydantic.
- FastAPI serializes responses by alias by default (`response_model_by_alias=True`); keep it.
- The notes schemas must **not** inherit `BaseSchema`: the SPA's notes zod schema reads
  `created_at`, and `/notes` doesn't change.
- `api/` supports Python 3.11 (`requires-python`, ruff `py311`): write `Generic[T]`, not the
  3.12 `class Page[T]` syntax.
- The domain handler must not catch `InvalidTokenError` or `KeySetUnavailableError`, which keep
  their own handlers.

### Depends on

API-2 (its test fixtures).

### Acceptance criteria

1. Unit tests: `BaseSchema` dumps camelCase and validates both camelCase and snake_case input;
   `Page[T]` dumps `{"items": [...], "total": n}`.
2. Endpoint tests on a test-only route that uses `PageParamsDep`: `skip=-1`, `limit=0` and
   `limit=1001` answer 422; no parameters give `skip=0`, `limit=100`.
3. Handler tests: a route raising `NotFoundError("Thing 1 not found")` answers
   `404 {"detail": "Thing 1 not found"}`; `ConflictError` and `BusinessRuleError` answer 400;
   a missing token still answers the existing 401 with `WWW-Authenticate`.
4. `/notes` answers exactly as before (the existing notes tests pass unchanged).
5. The validation commands pass.

---

## API-4: Categories

Covers B3.

### Goal

CRUD for categories with soft delete. Details in `api-contract.md` §3.1.

### Requirements

- Model `Category` (`categories`): `name` `String(64)` NOT NULL, plus `IdMixin`,
  `TimestampMixin`, `SoftDeleteMixin`. [FIX W-02] A partial unique index on `name`
  `WHERE is_deleted = false` (`Index(..., unique=True, postgresql_where=...)`). Its own
  migration.
- Schemas (`app/schemas/categories.py`): `CategoryCreateSchema`, `CategoryUpdateSchema` (name
  trimmed, not empty, at most 64; messages "Category name cannot be empty", "Category name cannot exceed 64 characters") and `CategorySchema`.
- Repository: `get_by_id`, `get_all(include_deleted)` (ordered by `id`), `get_by_name`,
  `exists_by_name(name, exclude_id)`, `create`, `update`, `soft_delete`.
- Service: `create` (name unique among non-deleted categories, else `ConflictError`
  "Category with name '{name}' already exists"), `update` (unique excluding itself;
  `NotFoundError` "Category {id} not found"), `delete` (soft delete), `get_by_id`, `get_all`.
- Router `app/api/categories.py`, prefix `/categories`, tag *Categories*:
  `GET /categories/?include_deleted=false`, `POST /categories/` (201), `PUT /categories/{id}`,
  `DELETE /categories/{id}` (204). [FIX W-04] Every endpoint takes `PrincipalDep`.
- Categories are global (D5): every user sees and edits the same ones.

### Pitfalls

- W-02: a global unique constraint would block re-creating a deleted name; use the partial
  index, and check that autogenerate wrote its `postgresql_where`.
- Two concurrent creates can both pass the service check; the index then raises
  `IntegrityError`, which the repository maps to the same `ConflictError`, not a 500.
- W-04: no endpoint without `PrincipalDep`.
- Removing client links on delete needs `client_category`, which API-5 adds; it isn't part of
  this item.

### Depends on

API-3.

### Acceptance criteria

1. Schema tests (6): valid name, empty, whitespace only, trimmed, 65 characters rejected, 64
   accepted.
2. Service tests (9): create, duplicate rejected, duplicate allowed after soft delete, update,
   update to a taken name rejected, update keeping its own name, delete, `get_all` without
   deleted, `get_all(include_deleted=True)`.
3. Endpoint tests: 401 without a token on each endpoint; 201, 200, 204; 400 duplicate with the
   contract message; 404 with the contract message; 422 for an empty name.
4. `uv run alembic check` reports no differences; the validation commands pass.

---

## API-5: Clients

Covers B4 without the bulk endpoint.

### Goal

CRUD for clients with categories, server-side search and a paginated list with its total.
Details in `api-contract.md` §3.2.

### Requirements

- Models (their own migration):
  - `Client` (`clients`): `company_name` `String(128)` NOT NULL; `primary_email` `String(256)`
    NOT NULL; `additional_emails` `Text`; `phone_number` `String`; `address` `String`;
    `is_active` bool NOT NULL default True; `notes` `Text`; the three mixins. [FIX W-02] A
    partial unique index on `primary_email` `WHERE is_deleted = false`.
  - `client_category`: `client_id` FK → `clients.id` ON DELETE CASCADE, `category_id` FK →
    `categories.id` ON DELETE CASCADE, composite primary key (`client_id`, `category_id`).
  - `Client.categories` many-to-many with `lazy="selectin"`.
- Dependency `pydantic[email]` for `EmailStr`.
- Schemas: `ClientCreateSchema`, `ClientUpdateSchema` (same shape), `ClientSchema` with
  `categories: list[CategorySchema]`. `companyName` trimmed, not empty, at most 128 (messages
  in the contract); `primaryEmail: EmailStr`.
- Repository: `get_by_id`, `get_all(skip, limit, search)`, `count(search)`,
  `exists_by_email(email, exclude_id)`, `create(data, category_ids)`, `update`,
  `soft_delete` (set the flags and clear `categories`), `load_categories(ids)` (non-deleted
  only).
- [NEW W-08] `search`: case-insensitive `ILIKE '%term%'` on `company_name`, `primary_email`,
  `phone_number` and the name of a linked non-deleted category (an `EXISTS` subquery, so a client
  matching two categories appears once). Order `company_name, id`. `total` = `count(search)`.
- [FIX W-26] `categoryIds`: duplicates dropped; unknown or deleted IDs →
  `BusinessRuleError` "Categories not found: 3, 7".
- [FIX W-01] `PUT` is a full replacement, documented in the contract: omitted optional fields
  are cleared. (UI-7 always sends every field.)
- Router `app/api/clients.py`, prefix `/clients`, tag *Clients*, every endpoint with
  `PrincipalDep`: `GET /clients/` (`Page[ClientSchema]`), `POST /clients/` (201),
  `GET /clients/{id}`, `PUT /clients/{id}`, `DELETE /clients/{id}` (204). Messages as in the
  contract.
- The category service's `delete` now first removes the category's `client_category` rows
  (`CategoryRepository.remove_client_associations`), as the contract says.

### Pitfalls

- Escape `%`, `_` and `\` in the search term before building the `ILIKE` pattern, so
  `search=100%` means the text "100%".
- Count with the same filter as the list, before `skip`/`limit`, and without the join that
  would count a client once per category.
- `selectin` loads categories in one extra query per page, not one per client.
- Map the unique index's `IntegrityError` to the `ConflictError`, as in API-4.
- `PUT` replaces the categories too: `categoryIds` omitted means "no categories".

### Depends on

API-4.

### Acceptance criteria

1. Schema tests (5): valid, empty company name, trimmed, 129 characters rejected, invalid
   email rejected.
2. Service tests (10): create with categories; duplicate email rejected; [W-02] the email of a
   soft-deleted client can be reused; update replaces every field (an omitted `notes` becomes
   null); update to a taken email rejected; delete clears the categories; unknown
   `categoryIds` → "Categories not found: …"; `get_all` without deleted clients; `search`
   finds by company, email, phone and category name; `total` ignores `skip`/`limit`.
3. Endpoint tests: 401 without a token; the `Page` shape; 201, 200, 204, 400, 404, 422.
4. Deleting a category removes it from its clients (`GET /clients/{id}` no longer lists it).
5. `uv run alembic check` reports no differences; the validation commands pass.

---

## API-6: Bulk client import endpoint

Covers B4 (the bulk part).

### Goal

`POST /clients/bulk` creates many clients in one call, row by row, and reports per-row errors
[NEW W-07]. Its UI (F11) is deferred; the endpoint is tested through the API.

### Requirements

- Request `ClientBulkCreateSchema` `{ clients: list[dict[str, Any]] }` with 1 to 1000 rows
  (`422` outside). Rows are raw objects, so one bad row doesn't fail the whole request.
- For each row, in order: validate it as `ClientCreateSchema`; check that `primaryEmail` is
  unique against non-deleted clients **and** the earlier rows of this batch; check the
  `categoryIds`; create the client. A failing row adds `{row, message}` (`row` from 1) and the
  loop goes on.
- `message`: the client service's message for business errors ("Client with email '{email}' already exists", "Categories not found: …"), or the validation errors joined with `; `, each
  as `<camelCase field>: <msg>`.
- Response `200 ClientBulkResultSchema` `{success, failed, errors}`.
- Each row runs in its own savepoint (`session.begin_nested()`), so a failing row never undoes
  the rows before it.
- Route `POST /clients/bulk` in `app/api/clients.py` with `PrincipalDep`.

### Pitfalls

- Typing the body as `list[ClientCreateSchema]` would make FastAPI reject the whole batch with
  422; validate rows in the service.
- A duplicate within the batch never reaches the database index if the check also looks at the
  emails accepted earlier in the batch; without the savepoint, an `IntegrityError` would roll
  back everything.
- Reuse the client service's create path; don't duplicate its rules.

### Depends on

API-5.

### Acceptance criteria

1. A batch with valid rows, a duplicate of an existing client, a duplicate of an earlier row,
   an invalid email, an empty company name and an unknown category answers `success` and
   `failed` counts that match, and `errors` with the right row numbers and messages; the valid
   rows exist afterwards.
2. 1001 rows → 422; an empty list → 422; no token → 401.
3. The validation commands pass.

---

## API-7: Per-user SMTP settings

Covers B5 (without the test endpoint), B2 (encryption).

### Goal

Each user saves and reads their own SMTP settings; the password is stored encrypted and never
returned. Details in `api-contract.md` §3.5.

### Requirements

- Model `Config` (`configs`, its own migration): `user_sub` `String(255)` NOT NULL, indexed;
  `config_key` `String(255)` NOT NULL; `config_value_encrypted` `Text` NOT NULL; `is_encrypted`
  bool NOT NULL default True; `IdMixin` and `TimestampMixin`.
  `UniqueConstraint(user_sub, config_key, name="uq_user_config_key")`. No foreign key and no
  `users` table (D12).
- Settings: `encryption_key: SecretStr`, required (`API_ENCRYPTION_KEY`), checked at startup to
  be a valid Fernet key with a clear error. `api/.env.example` gets a demo key generated with
  `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`,
  with a comment that it is a dev-only demo secret. Add `cryptography` to the dependencies.
- `app/services/encryption.py` `EncryptionService(key)`: `encrypt(str) -> str`,
  `decrypt(str) -> str` (empty text → `ValueError`; an invalid token →
  `ValueError("Decryption failed: …")`), `generate_key()`. [FIX] Store the Fernet token as it
  is (the old version base64-encoded it again). One instance in the `Container`.
- Repository `ConfigRepository(session, encryption)`: `SMTP_KEYS = ["smtp_server",
  "smtp_port", "smtp_user", "smtp_use_tls"]`, `SMTP_ENCRYPTED_KEYS = {"smtp_password"}`;
  `get_smtp_config(user_sub)` (no password), `get_smtp_config_with_password(user_sub)`,
  `upsert_smtp_config(user_sub, payload)` (only keys that are present and not null; values as
  `str(value)`; `is_encrypted` only for the password; update or insert by
  (`user_sub`, `config_key`)).
- Service (`app/services/smtp_config_service.py`): `get_smtp_config` →
  `SmtpConfigResponseSchema` (port as `int`; `smtp_use_tls` parsed by `parse_bool`, which
  accepts `true`, `1`, `yes` in any case); `update_smtp_config`; `get_smtp_config_for_sending`
  → the frozen dataclass `SmtpConfig(smtp_server, smtp_port, smtp_user, smtp_password,
  smtp_use_tls)` with the decrypted password and the defaults port 587 and TLS on, or `None`
  without a saved `smtp_server`. `smtp_password` is declared with `field(repr=False)`, so a log
  line or a test failure never prints it. Never exposed through the API.
- Schemas: `SmtpConfigResponseSchema`, `SmtpConfigUpdateSchema` (validators as in the
  contract; [FIX] `smtpUser` needn't be an email address), `MessageSchema`.
- Router `app/api/config.py`, prefix `/config`, tag *Configuration*: `GET /config/smtp`,
  `PUT /config/smtp` → `{"message": "Configuration updated successfully"}`. The user is
  `principal.subject`.
- `AGENTS.md`: an existing `api/.env` lacks the new required line; say to copy
  `API_ENCRYPTION_KEY` from `api/.env.example` into it. Also say that the demo key is public:
  before saving a real SMTP password, generate your own key into `api/.env` (the command
  above), or use smtp4dev.

### Pitfalls

- W-10: the key must be in `.env.example`, which the sandbox reads, or the API won't start
  anywhere.
- Never log the password, the key or decrypted values.
- `str(True)` is `"True"`: `parse_bool` must accept it (case-insensitive `true`).
- The existing tests build `Settings(...)` by hand; give them a generated key.
- Users are told apart by `sub` only; never by email or name, which users can change in
  Keycloak.

### Depends on

API-3.

### Acceptance criteria

1. Schema tests (7): port 0 and 65536 rejected, an empty server rejected, the server trimmed,
   an empty password rejected, all fields `null` accepted, a `smtpUser` that isn't an email
   accepted.
2. Service tests (7): save and read back; the password is encrypted in the database (the raw
   `config_value_encrypted` differs from the plain password and decrypts to it); the password
   never appears in `get_smtp_config`; a partial update keeps the other keys; `alice` and `bob`
   have separate settings; `parse_bool` cases; `get_smtp_config_for_sending` defaults and
   `None`.
3. `EncryptionService`: round trip, an invalid token, empty text.
4. Endpoint tests: 401 without a token; `GET` all `null` before saving; `PUT` 200 with the
   message; 422 for an invalid port.
5. The API refuses to start with an invalid `API_ENCRYPTION_KEY`, with a clear message.
6. `uv run alembic check` reports no differences; the validation commands pass.

---

## API-8: SMTP sending service, test endpoint and smtp4dev

Covers B6, B5 (the test endpoint), B12 (the smtp4dev part).

### Goal

One testable way to send an email through `aiosmtplib`, a `POST /config/smtp/test` that uses
it, and a dev SMTP server in every run mode.

### Requirements

- Dependency `aiosmtplib>=5.1`.
- `app/services/smtp_sender.py`:
  - frozen dataclass `SendResult(success, smtp_message_id, error)`;
  - Protocol `EmailSender` with `async def send(to, subject, html_body) -> SendResult`, and the
    factory type `EmailSenderFactory = Callable[[SmtpConfig], EmailSender]`, held by the
    `Container` and passed to `create_app` as an optional argument so tests inject a fake;
  - `SmtpEmailSender(config)` implements it;
  - `send_many(sender, items, max_concurrent, on_result)` runs the sends with
    `asyncio.Semaphore(max_concurrent)` and awaits `on_result(item, result)` as each one
    finishes; an exception from one send becomes that item's failed result (`gather` with
    `return_exceptions=True`). [FIX W-24] It is the only place with send concurrency; API-11
    uses it.
- The message: `MIMEMultipart("alternative")` with `From` (= `smtp_user`), `To`, `Subject`
  encoded as UTF-8 (`email.header.Header`; a subject with an emoji must arrive intact), `Date`
  (RFC 2822, `email.utils.formatdate`), [FIX W-12] `Message-ID` (`email.utils.make_msgid`),
  and one `text/html; charset=utf-8` part. `smtp_message_id` in the result is that
  `Message-ID`.
- The connection [FIX W-13]: TLS on and port 465 → `use_tls=True`; TLS on, any other port →
  `start_tls=True`; TLS off → `use_tls=False, start_tls=False`. Log in only when both
  `smtp_user` and `smtp_password` are set.
- [ADAPT, D18] `SMTP_TIMEOUT_SECONDS = 8`: passed to `aiosmtplib` as `timeout`, and the whole
  send (connect, login, send) runs inside `asyncio.timeout(SMTP_TIMEOUT_SECONDS)`.
- Errors mapped to `SendResult.error`, most specific first: `SMTPAuthenticationError` →
  `SMTP Authentication failed: …`; `SMTPRecipientsRefused` → `Recipient refused: …`;
  `SMTPException` → `SMTP error: …`; `TimeoutError` → `SMTP error: timed out after 8 s`;
  anything else → `Unexpected error: …`. Log the failure with the recipient address; never log
  passwords or bodies.
- `POST /config/smtp/test` (router `app/api/config.py`): body `SmtpTestRequestSchema`; loads
  the caller's `get_smtp_config_for_sending`; none → `BusinessRuleError` "SMTP configuration not found. Please configure SMTP settings first."; sends a short HTML message with the subject
  "Email Sender — test połączenia SMTP"; success → `200 {"success": true, "message": "Test email sent to {recipient}"}`; failure → `400` with the mapped error as `detail`.
- smtp4dev, `docker.io/rnwood/smtp4dev:3.15.0` (pinned; not `prerelease`), no volume, with
  `ServerOptions__Port=2525` and `ServerOptions__Urls=http://*:5080` so it listens on the same
  ports in every mode:
  - host, `keycloak/docker-compose.yml`: published as `127.0.0.1:2525:2525` and
    `127.0.0.1:5080:5080`;
  - sandbox, `compose.yaml`: joins `keycloak`'s namespace; `keycloak` also publishes
    `127.0.0.1:5080:5080` for the web UI (D19); SMTP is not published;
  - dev container, `.devcontainer/compose.yaml`: joins `keycloak`'s namespace; both
    `devcontainer.json` files (`.devcontainer/` and `.devcontainer/podman/`) forward 5080 with
    the label `smtp4dev`.
- `AGENTS.md`: smtp4dev in "Run locally", "Sandbox" and "Dev container", the inbox at
  http://localhost:5080, and the values to enter in "Ustawienia": server `localhost`, port
  `2525`, TLS off, user `noreply@localhost` (also the `From` address), any password (smtp4dev
  accepts any credentials); ports 2525 and 5080 clash with anything else on them.
- `api/pyproject.toml` registers the `online` pytest marker.

### Pitfalls

- With `start_tls=None` (the aiosmtplib default), the client upgrades whenever the server
  offers STARTTLS; smtp4dev offers it with a self-signed certificate, so TLS off must pass
  `start_tls=False`. Check every TLS argument against the aiosmtplib 5.x docs.
- `SMTPRecipientsRefused` and `SMTPAuthenticationError` are `SMTPException` subclasses: catch
  them first.
- `From` is the SMTP user: with a login that isn't an address, many servers refuse the mail.
  That is the user's setting, not a bug to work around.
- The source's 30 s test timeout would outlast the BFF's 10 s and turn into a 502.
- In the shared namespace there is no port mapping, so smtp4dev itself must listen on 2525 and
  5080 (its image defaults are 25 and 80). Use the fully qualified image name.
- Never connect to a real SMTP server in the default test run.

### Depends on

API-7.

### Acceptance criteria

1. Unit tests with a fake `aiosmtplib.SMTP`: the MIME message has `From`, `To`, `Subject`,
   `Date`, `Message-ID` and an HTML part, and a subject with an emoji survives a round trip
   through `email.message_from_bytes`; no login without a password; TLS arguments for port 465,
   port 587 and TLS off; the four error classes and a timeout map to their messages (the
   timeout test patches a short timeout).
2. `send_many`: a mix of success, failure and an exception gives three results through
   `on_result`, and no more than `max_concurrent` sends run at once.
3. Endpoint tests with a fake sender factory: 200 with the message; no settings → 400 with the
   contract message; an SMTP failure → 400 with the mapped error; no token → 401.
4. An online test (`@pytest.mark.online`) sends through smtp4dev on `localhost:2525` and skips
   when that port doesn't answer within 1.5 s; it passes with `make docker-up` running.
5. `make docker-up`: http://localhost:5080 shows the smtp4dev inbox and the test email arrives
   there after saving the AGENTS.md values; `make sandbox-up`: the same through the sandbox's
   5080.
6. The validation commands pass without smtp4dev running.

---

## API-9: Campaigns

Covers B7.

### Goal

Manage `draft` campaigns and their recipients, and read their stats. Details in
`api-contract.md` §3.3.

### Requirements

- Models (their own migration):
  - `Campaign` (`campaigns`): `name` `String(255)` NOT NULL; `subject` `String(500)` NOT NULL;
    `content` `Text` NOT NULL; `status` NOT NULL default `draft`; `sent_at`, `scheduled_for`
    (`DateTime(timezone=True)`); the three mixins. Relationship `recipients` (cascade
    `all, delete-orphan`, `lazy="selectin"`).
  - `CampaignRecipient` (`campaign_recipients`): `campaign_id` FK → `campaigns.id` ON DELETE
    CASCADE NOT NULL; `client_id` FK → `clients.id` ON DELETE CASCADE NOT NULL; `status` NOT
    NULL default `pending`; `sent_at`; `error` `Text`; the three mixins. Relationships
    `campaign` and `client` (`selectin`). [FIX] A partial unique index on (`campaign_id`,
    `client_id`) `WHERE is_deleted = false`.
- Enums as `str, enum.Enum`: `CampaignStatus {DRAFT, SENDING, SENT, FAILED, SCHEDULED}` (with
  `sending` from the start, D17) and `RecipientStatus {PENDING, SENT, FAILED, BOUNCED}`. Store
  the lowercase **values**: `Enum(..., native_enum=False, values_callable=lambda e: [m.value for
  m in e], create_constraint=True, name="campaign_status")` (and `recipient_status`), so the
  columns are `VARCHAR` with a CHECK constraint.
- Schemas: `CampaignCreateSchema`, `CampaignUpdateSchema`, `CampaignSchema`,
  `CampaignRecipientSchema`, `CampaignStatsSchema` (shapes, limits and messages in the
  contract). [FIX] `subject` is limited to 500 on update too. [FIX] An explicit
  `"scheduledFor": null` clears it (`model_fields_set`); any other `null` means "don't change".
- Repository: `get_by_id`, `get_all(skip, limit, search)` and `count(search)`, `create`,
  `update`, `soft_delete` (the campaign and its recipients), `set_recipients(campaign,
  client_ids)` (soft-delete the old rows, then add new `pending` ones), `add_recipients` (skips
  clients already on the campaign), `get_recipients_by_ids`.
- Service: `create` (a `draft` with recipients), `update` (**`draft` only**, partial,
  `recipientIds` replaces), `delete`, `add_recipients` (`draft` only), `get_all`, `get_by_id`,
  `to_schema(campaign)` (enum values, only non-deleted recipients, `clientName` and
  `clientEmail` from the client) and `compute_stats` (the contract's formulas over active
  recipients).
- [FIX W-26] `recipientIds`: duplicates dropped; every ID a non-deleted client, else
  `BusinessRuleError` "Clients not found: 3, 7".
- [FIX W-16] The contract says edits are `draft`-only; UI-9 and UI-12 show "Edytuj" only for
  `draft`.
- `scheduledFor` is stored only (D6): creating with a date still gives a `draft`.
- Router `app/api/campaigns.py`, prefix `/campaigns`, tag *Campaigns*, every endpoint with
  `PrincipalDep`: `GET /campaigns/` (`Page[CampaignSchema]`; `search` on name, subject and
  content; order `created_at desc, id desc`), `POST /campaigns/` (201), `GET /campaigns/{id}`,
  `PUT /campaigns/{id}`, `DELETE /campaigns/{id}` (204), `POST /campaigns/{id}/recipients`
  (body: a bare array of client IDs; 201).

### Pitfalls

- SQLAlchemy's `Enum` stores member **names** (`DRAFT`) by default, while the API and the atomic
  update in API-11 use values (`draft`): `values_callable` is required. `native_enum=False`
  also avoids `ALTER TYPE` when an enum gains a value.
- The CHECK constraint needs a `name` for the naming convention's `ck` pattern.
- `set_recipients` with overlapping IDs: flush the soft deletes before inserting the new rows,
  or the partial unique index fires (the unit of work may order the INSERT first).
- Inactive clients may be recipients; API-11 handles them at send time (W-14).
- Rounding: `round(x, 2)` on floats; `progressPercentage` and `successRate` are 0 when `total`
  is 0.
- Rules for the `sending` status (refusing `PUT` and `DELETE`) come with API-11.

### Depends on

API-5.

### Acceptance criteria

1. Schema tests (6): valid, empty name, trimmed name, name over 255, empty subject, empty
   content; plus a subject over 500 rejected on update.
2. Service tests (12): create with recipients; duplicate IDs dropped; unknown clients →
   "Clients not found: …"; get; list `search`; `total`; update a draft; update a non-draft
   raises "Only draft campaigns can be modified"; update replaces the recipients; explicit
   `scheduledFor: null` clears it; delete soft-deletes the recipients; `add_recipients` skips
   duplicates and refuses a non-draft; `to_schema`.
3. Stats on three cases: no recipients (all 0), all pending (progress 0), a mix of sent, failed
   and pending (the contract's formulas, 2 decimals).
4. Endpoint tests: 401; `Page` shape and order; 201, 200, 204, 400, 404, 422; the bare-array
   body of `POST /campaigns/{id}/recipients`.
5. `uv run alembic check` reports no differences; the validation commands pass.

---

## API-10: The email log

Covers B9 without the resend.

### Goal

The email log table and its read, filter, stats and manual endpoints. Details in
`api-contract.md` §3.4.

### Requirements

- Model `Email` (`emails`, its own migration): `campaign_id` FK → `campaigns.id` ON DELETE
  CASCADE NOT NULL, **indexed**; `client_id` FK → `clients.id` ON DELETE CASCADE NOT NULL,
  **indexed**; `recipient_email` `String(256)` NOT NULL, **indexed**; [D25, W-17] `subject`
  `String(500)` NOT NULL and `body` `Text` NOT NULL (the snapshot); `status` NOT NULL default
  `pending`, **indexed**; `sent_at` (**indexed**), `delivered_at`, `opened_at`, `clicked_at`,
  `bounced_at` (all `DateTime(timezone=True)`); `error_message` `Text`; `error_code`
  `String(50)`; `retry_count` int NOT NULL default 0; `max_retries` int NOT NULL default 3;
  `smtp_message_id` `String(255)`; `smtp_response` `Text`; the three mixins. Relationships
  `campaign` and `client` (`selectin`).
- `EmailStatus {PENDING, SENDING, SENT, FAILED, BOUNCED, REJECTED, DEFERRED}`, stored by value
  as in API-9.
- Repository: `create`, `get_by_id`, `get_all(filters)` and `count(filters)`,
  `get_by_campaign`, `get_by_client`, `get_failed`, `get_for_recipient(campaign_id,
  client_id)` (for API-11), `update`, `soft_delete`, `mark_opened`, `mark_clicked`,
  `get_stats(campaign_id)`.
- Filters on `GET /emails/`: `campaign_id`, `client_id`, `status`, `from_date`/`to_date` (on
  `created_at`), `has_error` (`error_message` is or isn't null), [NEW W-08] `search` (case-
  insensitive on `recipient_email`, the client's company name, the campaign's name and the
  email's `subject`). Order `created_at desc, id desc`, also for the by-campaign and by-client
  lists.
- [FIX] `get_stats` in SQL (`COUNT(*) FILTER (WHERE …)`), not by loading rows; rates as in
  the contract (denominators `total`, `sent`, `sent`, `total`).
- Service: `update` (only the fields given; `status` must be an `EmailStatus` value, else
  `BusinessRuleError` "Invalid email status: {value}"), `to_schema` (`status` value,
  `clientName`, `campaignName`, `subject` and `content` from the snapshot).
- Router `app/api/emails.py`, prefix `/emails`, tag *Emails*, every endpoint with
  `PrincipalDep`, the routes and responses of the contract except `POST /emails/{id}/resend`.
  `/stats/`, `/failed/`, `/campaign/{campaign_id}` and `/client/{client_id}` are registered
  before `/{email_id}`.
- `GET /emails/` answers `Page[EmailSchema]`; the by-campaign, by-client and failed lists are
  plain arrays (D27).

### Pitfalls

- Route order: with `/{email_id}` first, `/stats/` would answer 422 (not an int).
- Count and stats use the same filters as the list, without `skip`/`limit`; soft-deleted rows
  never count.
- Nothing writes emails until API-11; tests create rows through the repository.
- `delivered` is not a status (W-09): it is `delivered_at IS NOT NULL`.

### Depends on

API-9.

### Acceptance criteria

1. Service tests (15): create, get, not found, each filter (campaign, client, status, date
   range, `has_error`, `search`), order, `total`, failed list, by campaign, by client, update,
   invalid status → 400 message, soft delete, mark opened and clicked.
2. Stats on a fixed set of rows match hand-computed counts and rates, including 0.0 for zero
   denominators.
3. Endpoint tests: 401; `Page` shape; route order (`/emails/stats/` isn't parsed as an ID);
   200, 404, 400, 422 (`status=unknown` in the query); `DELETE` answers the message.
4. `uv run alembic check` reports no differences; the validation commands pass.

---

## API-11: Campaign send in the background

Covers B8 (the send part).

### Goal

`POST /campaigns/{id}/send` checks the request, starts a background send and answers `202`; the
campaign shows `sending` and its progress until it ends as `sent` or `failed`. Rules in
`api-contract.md` §4. [FIX W-24] fully.

### Requirements

- `app/services/email_content.py`:
  - [NEW W-06, D4] content without HTML tags (no match for `<[a-zA-Z/!][^>]*>`) is
    HTML-escaped and gets `\n` → `<br>`;
  - [NEW W-05, D3] then `{name}`, `{email}` and `{company}` are replaced with `re.sub` over
    these keys only (`{company}` and `{name}` = company name, `{email}` = primary email), with
    the values HTML-escaped; unknown `{x}` stays.
- `app/services/campaign_sender.py`:
  - `start(campaign_id, user_sub, retry_recipient_ids=None)`: §4 checks 1 to 4 (with
    `retry_recipient_ids` always `None` in this item: `draft` → pending recipients, `failed` →
    all failed recipients), then step 5: the atomic
    `UPDATE … SET status = 'sending' WHERE id = :id AND status IN ('draft','failed') AND
    is_deleted = false` (a lost race gives the check-1 message with the current status), the
    reset of the chosen failed recipients, one commit. Returns the campaign and the
    `SmtpConfig` for the task.
  - `run(campaign_id, smtp_config, max_concurrent)`: the background task. It opens its own
    session from the `Container`'s factory, loads the `pending` recipients with their clients,
    and sends through `send_many` (API-8) with the sender from the factory. Each result is
    written as it arrives, under an `asyncio.Lock`, with its `Email` row, and committed: §4
    step 6 (inactive or deleted clients, `max_retries`, create or update the `Email` row, the
    snapshot, `retry_count`). Then step 7. Any unexpected exception is caught: pending
    recipients → `failed` with `Unexpected error: …`, campaign → `failed`, logged. It never
    raises.
  - `recover_interrupted()`: §4 step 8, called from the lifespan after the migrations.
- Router: `POST /campaigns/{id}/send` with `max_concurrent: int | None = Query(None, ge=1,
  le=50)` (D10; `None` → `settings.email_max_concurrent`), `status_code=202`, `PrincipalDep`
  (the user is `principal.subject`), and FastAPI `BackgroundTasks` to run `run(...)` after the
  response. Answers `CampaignSchema` with `status: "sending"`.
- Settings `email_max_concurrent: int = Field(10, ge=1, le=50)`; `api/.env.example` gets
  `API_EMAIL_MAX_CONCURRENT=10`.
- The campaign service refuses `PUT` and `DELETE` on a `sending` campaign with
  `BusinessRuleError` "Campaign is being sent" (`PUT` keeps "Only draft campaigns can be modified" for `sent`, `failed` and `scheduled`).

### Pitfalls

- One `AsyncSession` must never be used by two coroutines at once: only the SMTP calls run
  concurrently; the writes go through the lock.
- The request's session is closed when the task runs; the task uses its own from the factory.
  The test session factory (API-2) is bound to the test connection, so the task sees the test's
  data.
- `httpx.ASGITransport` returns the response only after the app's background tasks ran, so a
  test's next `GET` sees the final state. To test a campaign in `sending`, set the status in
  the database.
- An exception escaping a background task reaches the server (and fails the test through
  `ASGITransport`): the task catches everything itself.
- Run checks 1 to 4 before changing anything: a failing check must leave recipients and status
  untouched.
- `sending` blocks a second click server-side; the 202 comes back before any SMTP traffic, so
  the BFF's 10 s timeout no longer matters for campaigns.
- Send only to `primaryEmail`, never to `additionalEmails` [PARITY].
- Escape before converting newlines, and substitute after converting, so a company name with
  `<` stays text.

### Depends on

API-8, API-9, API-10.

### Acceptance criteria

All with a fake sender from the factory, no SMTP:

1. A draft with 3 recipients: `POST …/send` answers 202 with `status: "sending"`; afterwards
   `GET /campaigns/{id}` shows `sent` with `sentAt`, and there are 3 `Email` rows `sent` with
   `smtpMessageId` and the snapshot.
2. One failure out of 3: the campaign ends `failed`, `stats.sent = 2`, `stats.failed = 1`, the
   recipient and its `Email` row carry the error.
3. `send` on that failed campaign retries only the failed recipient, updates its existing
   `Email` row (`retryCount` 1, no new row) and ends `sent` (the old
   `partial_failures_keep_campaign_failed_until_retry` and
   `can_resend_after_failed_campaign` cases).
4. 400 messages: on `sent` ("current status: sent"), on `sending`, no recipients, no SMTP
   settings; 404 for an unknown campaign; 422 for `max_concurrent=0` and `51`; 401 without a
   token. A failing check changes nothing.
5. A lost race: with the status changed between the checks and the update, `start` answers the
   status message and doesn't send.
6. Variables are substituted and escaped; plain-text content gets `<br>`; HTML content keeps its
   tags.
7. An inactive client: its recipient is `failed` with "Client is inactive" and the fake sender
   wasn't called for it. A row at `max_retries` fails with "Maximum retries exceeded".
8. Concurrency never exceeds `max_concurrent` (the fake records in-flight sends).
9. A sender that raises an unexpected error mid-campaign: the remaining pending recipients and
   the campaign end `failed` with `Unexpected error: …`.
10. `recover_interrupted()` on a campaign left in `sending` with pending recipients: they become
    `failed` with "Sending interrupted" and the campaign `failed`.
11. `PUT` and `DELETE` on a `sending` campaign answer 400 "Campaign is being sent".
12. The validation commands pass.

---

## API-12: Campaign resend in the background

Covers B8 (the resend part).

### Goal

`POST /campaigns/{id}/resend` sends again to all failed recipients or to chosen ones, through
the same background flow as API-11.

### Requirements

- Schema `CampaignResendSchema` `{ recipientIds?: number[] | null }` (campaign recipient IDs).
- `campaign_sender.start` takes `retry_recipient_ids` (§4 check 2): with a `draft` →
  "Only failed campaigns can be resent"; with a `failed` campaign, every ID must belong to it
  ("Recipients not found in campaign: 3, 5") and be `failed` ("Can only resend failed recipients: 4"); an empty list chooses nobody, so check 3 answers "Campaign has no pending recipients". Without IDs it behaves like `send`.
- Router: `POST /campaigns/{id}/resend?max_concurrent=` with the optional body, 202,
  `PrincipalDep`, `BackgroundTasks`, as in API-11.

### Pitfalls

- The IDs are `CampaignRecipient` IDs, not client IDs.
- Validate all chosen IDs before resetting any (no half-applied reset).
- Recipients not chosen stay `failed`, so the campaign ends `failed` again (§4 step 7).

### Depends on

API-11.

### Acceptance criteria

1. Resend without a body after a partial failure: only the failed recipients are retried and the
   campaign ends `sent`.
2. Resend with chosen IDs: only those are retried; the others stay `failed` and so does the
   campaign.
3. The four 400 messages (draft with IDs, unknown IDs listed, non-failed IDs listed, empty list),
   400 on `sending` and `sent`, 404, 422 for `max_concurrent`, 401.
4. The router passes the chosen IDs to the service (the old router test).
5. The validation commands pass.

---

## API-13: Single-email resend

Covers B9 (the resend part).

### Goal

`POST /emails/{id}/resend` sends one logged email again, synchronously, within the BFF's
timeout.

### Requirements

- `EmailService.resend(email_id, user_sub)`: the email (404 "Email {id} not found"); the
  caller's `get_smtp_config_for_sending` (none → 400 "SMTP configuration not found. Please configure SMTP settings first."); send to `recipient_email` with the stored `subject` and
  `body` through the sender factory; update the same row: `status` `sent` or `failed`,
  `sent_at` only on success, `smtp_message_id`, `error_message` (`null` on success),
  `retry_count + 1`.
- Router: `POST /emails/{id}/resend` in `app/api/emails.py`, `PrincipalDep`, answers
  `200 EmailSchema`.
- It doesn't change the campaign or its recipient [PARITY].

### Pitfalls

- The 8 s SMTP timeout (API-8) keeps the request inside the BFF's 10 s; don't add retries.
- Use the snapshot, not the campaign's current text (W-17).

### Depends on

API-8, API-10.

### Acceptance criteria

1. With a fake sender: success → `sent`, `sentAt` set, `retryCount` 1, `smtpMessageId`;
   failure → `failed` with `errorMessage`, `sentAt` unchanged.
2. No SMTP settings → 400 with the message; unknown email → 404; no token → 401.
3. The sender receives the snapshot subject and body, even after the campaign was edited.
4. The validation commands pass.

---

## API-14: Demo data seed

Covers B10.

### Goal

Demo clients and campaigns for local work, created at startup when the setting is on, and
idempotent.

### Requirements

- Settings `seed_demo_data: bool = False` (`API_SEED_DEMO_DATA`); `api/.env.example` sets it to
  `true`, so the sandbox and fresh checkouts get the data.
- `app/services/seed.py` `seed_clients_and_campaigns(session) -> SeedResult` with the counts
  `clients_created`, `clients_skipped`, `campaigns_created`, `campaigns_skipped`,
  `recipients_created`. Idempotent: a client is found by `primary_email` (not deleted), a
  campaign by `name`.
- Clients, exactly. [FIX, D31] The names, phones and notes are the source's; the email domains
  are reserved `.example` domains instead of the source's real or registrable ones
  (`acme-logistics.com`, `brightdental.com`, `northwind-electronics.com`,
  `greenfoods-market.com`, `pixelcraft.studio`), so a seeded draft sent through a real SMTP
  account reaches nobody:

  | Company | Email | Phone | Notes |
  |---|---|---|---|
  | Acme Logistics | contact@acme-logistics.example | +1-202-555-0101 | Priority logistics partner |
  | Bright Dental Clinic | hello@brightdental.example | +1-202-555-0102 | Monthly newsletter subscriber |
  | Northwind Electronics | sales@northwind-electronics.example | +1-202-555-0103 | Interested in product launch campaigns |
  | Green Foods Market | owner@greenfoods-market.example | +1-202-555-0104 | Seasonal promo campaigns |
  | Pixel Craft Studio | team@pixelcraft.example | +1-202-555-0105 | Design partner |

- Campaigns, all `draft`:

  | Name | Subject | Recipients |
  |---|---|---|
  | Spring Product Update | See what's new this spring 🌱 | Acme Logistics, Northwind Electronics, Pixel Craft Studio |
  | Monthly Newsletter - April | April highlights from our team | Bright Dental Clinic, Green Foods Market |
  | VIP Partner Invitation | Invitation: partner strategy session | Acme Logistics, Pixel Craft Studio |

  Content: a short HTML greeting that uses `{company}` (the source doesn't give the old text).
  No categories (parity: the old seed created none).
- The lifespan, after the migrations and `recover_interrupted()`: when `seed_demo_data` is true,
  run the seed in one session; an error rolls back and is logged, and startup goes on. Log the
  counts, nothing else (W-27).
- `uv run python -m app.services.seed` runs it by hand against `API_DATABASE_URL` and prints the
  counts.
- The source's `seed_smtp4dev_config` is dropped (D22).

### Pitfalls

- Keycloak subs are generated at realm import, so no per-user data can be seeded.
- Idempotence by natural keys: a second run must create nothing and skip everything.
- The subject's emoji is deliberate: it exercises the UTF-8 subject from API-8.
- Never seed a real or registrable domain (D31). `EmailStr` accepts `.example` but rejects
  `.test` and `localhost`, so those can't be used instead.

### Depends on

API-5, API-9, API-11.

### Acceptance criteria

1. On an empty test database the seed creates 5 clients, 3 campaigns and 7 recipients with the
   values above; every seeded email address ends in `.example`.
2. A second run creates nothing: 5 clients and 3 campaigns skipped, 0 recipients created.
3. The lifespan seeds with the setting on and doesn't with it off; a seed error is logged and
   the app still starts.
4. `make sandbox-up`: `GET /api/clients/` through the SPA's origin lists the five clients.
5. The validation commands pass.
