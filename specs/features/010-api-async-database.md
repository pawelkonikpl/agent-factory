# Async database layer for the API

> Feature: Add the async database layer to `api/`: SQLAlchemy 2 async with asyncpg, Alembic (`api/alembic.ini`, `api/migrations/`, no tables yet, `upgrade head` at startup), the model base with its naming convention and mixins, a per-request session dependency, and test fixtures on a separate `emailsender_test` database with per-test rollback that fail clearly when PostgreSQL is down, as specified in `specs/email-sender/backend.md` API-2 (covers B0 dependencies, B1 infrastructure, B11 `conftest.py`)

## Context

This is roadmap item API-2 of Phase 4 (Email Sender API). The source of truth is
`specs/email-sender/backend.md`, section "API-2: Async database layer" (Requirements,
Pitfalls, Acceptance criteria), with background in `specs/email-sender/README.md` §3.3
(D14, D15), §5 (the target `api/` layout), §7 (configuration) and §10 (defects W-22, W-25).
This spec restates that section; where they differ, this spec wins.

API-1 (`specs/features/009-postgresql-run-modes.md`) already runs PostgreSQL 18.6 in all
three run modes (host: `keycloak/docker-compose.yml` on 127.0.0.1:5432; sandbox: root
`compose.yaml`, `api` waits for `postgres` to be healthy; dev container:
`.devcontainer/compose.yaml`, `localhost:5432` inside `dev`). `api/.env.example` already has
`API_DATABASE_URL=postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender`.
No `api/` code uses it yet.

The API today (`api/`):

- `pyproject.toml`: runtime deps fastapi, uvicorn, httpx, pydantic-settings, pyjwt; dev group
  pytest, pytest-asyncio, ruff, mypy. `asyncio_mode = "auto"`,
  `asyncio_default_fixture_loop_scope = "function"` (each test gets its own event loop),
  mypy `strict = true` with the pydantic plugin, ruff rules E F W I UP B SIM RUF ASYNC.
  `uv.lock` is committed.
- `app/config.py`: `Settings(BaseSettings)` with `env_prefix="API_"`, `env_file=".env"`,
  `extra="ignore"`; fields `issuer`, `audience`, `http_timeout_seconds`,
  `jwks_min_refresh_interval_seconds` with defaults.
- `app/main.py`: `create_app(settings=None, *, http_client=None, clock=time.monotonic)`. Its
  `lifespan` only closes the httpx client it built. It stores `build_container(...)` in
  `app.state.container`, mounts `app.api.notes.router`, `/health` and the token error handlers.
  The pattern to follow for injecting a dependency from tests is `http_client`: optional
  argument, built internally when missing, cleaned up in the lifespan only when built internally.
- `app/dependencies.py`: frozen dataclass `Container(verifier, notes)`, `build_container`,
  `get_container`/`ContainerDep`, `get_principal`/`PrincipalDep`, `NoteServiceDep`.
- Notes are in memory (`app/repositories/note_repository.py`) and stay so (README §3.10).
- `tests/conftest.py`: `FakeIssuer`, the `issuer`, `client` (builds
  `Settings(issuer=ISSUER, audience=AUDIENCE)`, calls `create_app`, wraps it in
  `httpx.ASGITransport`) and `bearer` fixtures. `tests/test_notes_api.py` uses them.
- `Containerfile`: copies `pyproject.toml`, `uv.lock`, then `app` only.
  `.dockerignore` excludes `.env`, `.venv`, caches.
- `Makefile` `backend` runs the API with `uv run uvicorn app.main:create_app --factory --port 8001`
  from `api/`; `.devcontainer/post-start.sh` runs `make backend`.

`AGENTS.md` "Run locally" and "Validation" don't mention that the API needs PostgreSQL.

## Requirements

1. **Dependencies** in `api/pyproject.toml`, added with `uv add` so `uv.lock` is updated:
   runtime `sqlalchemy[asyncio]>=2.0`, `asyncpg`, `alembic`. If any code imports `asyncpg`
   directly, add `asyncpg-stubs` to the dev group or a mypy override for `asyncpg` only;
   strict mypy stays on everywhere else.
2. **Settings** (`app/config.py`): `database_url: str` defaulting to
   `postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender` (the
   `api/.env.example` value), and `test_database_url: str | None = None`
   (`API_TEST_DATABASE_URL`).
3. **Model base**, `app/models/base.py`:
   - `NAMING_CONVENTION = {"ix": "ix_%(column_0_label)s", "uq": "uq_%(table_name)s_%(column_0_name)s", "ck": "ck_%(table_name)s_%(constraint_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s", "pk": "pk_%(table_name)s"}`;
   - `Base(DeclarativeBase)` with `metadata = MetaData(naming_convention=NAMING_CONVENTION)`;
   - `IdMixin`: `id` int primary key, autoincrement;
   - `TimestampMixin`: `created_at` and `updated_at`, `DateTime(timezone=True)`, NOT NULL,
     default `datetime.now(UTC)` (a callable, never `utcnow`), `updated_at` also
     `onupdate` `datetime.now(UTC)`;
   - `SoftDeleteMixin`: `is_deleted` bool NOT NULL default `False`, indexed; `deleted_at`
     `DateTime(timezone=True)` nullable;
   - SQLAlchemy 2 `Mapped[]`/`mapped_column` style throughout.
   - `app/models/__init__.py` imports every model module (only `base` for now, exporting
     `Base`) so Alembic sees all tables. No table is defined in this item.
4. **`app/database.py`**:
   - `create_engine(url: str) -> AsyncEngine` via `create_async_engine(url, pool_pre_ping=True)`;
   - `create_session_factory(engine) -> async_sessionmaker[AsyncSession]` with
     `expire_on_commit=False`;
   - `run_migrations(url: str) -> None`: builds an Alembic `Config` from `api/alembic.ini`
     (absolute path), sets an absolute `script_location` (`api/migrations`) and
     `sqlalchemy.url` to `url`, then calls `alembic.command.upgrade(config, "head")`. It works
     regardless of the current working directory.
5. **Alembic**: `api/alembic.ini` and `api/migrations/` generated from the async template
   (`uv run alembic init -t async migrations` in `api/`), with `migrations/versions/` present
   and empty (keep it in git, e.g. with a `.gitkeep`). Changes to the template:
   - `env.py` uses the `sqlalchemy.url` the caller set on the config; when none is set, it uses
     `Settings().database_url`. `alembic.ini` carries no placeholder URL that would win over
     that fallback (blank or removed `sqlalchemy.url`).
   - `target_metadata = Base.metadata` (imported through `app.models`), and `context.configure`
     gets `compare_type=True` and `compare_server_default=True` (online and offline).
   - The logging setup from `alembic.ini` must not disable the app's existing loggers when it
     runs inside the API (call `fileConfig(..., disable_existing_loggers=False)`, or skip it when
     the caller configured logging), so uvicorn's and the app's logs keep working after startup.
   - `alembic.ini` makes `app` importable (`prepend_sys_path = .`), so `uv run alembic ...` works
     from `api/`.
   - `migrations/` passes `uv run ruff check .`.
6. **`create_app`** (`app/main.py`):
   - new keyword argument `session_factory: async_sessionmaker[AsyncSession] | None = None`.
     Without one it builds the engine with `create_engine(settings.database_url)` and the
     factory with `create_session_factory`, and disposes that engine on shutdown. An injected
     factory is never disposed by the app.
   - the `lifespan` first runs `await asyncio.to_thread(run_migrations, settings.database_url)`.
     On error it logs the exception (`logger.exception`) and re-raises, so the API does not
     start without its database. The existing httpx-client cleanup stays.
7. **Session dependency** (`app/dependencies.py`): `Container` gains `sessions:
   async_sessionmaker[AsyncSession]`, passed through `build_container`. `async def
   get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]` yields one session per
   request from it (opened with `async with`, so it is closed afterwards);
   `SessionDep = Annotated[AsyncSession, Depends(get_session)]`. No router uses it yet.
8. **`api/Containerfile`** also copies `alembic.ini` and `migrations/` into `/app`, so the
   sandbox image migrates at startup.
9. **Test fixtures**, `tests/conftest.py`:
   - A function that computes the test URL: `API_TEST_DATABASE_URL` (via
     `Settings().test_database_url`) if set, else `Settings().database_url` with the database
     name replaced by `emailsender_test` (use `sqlalchemy.engine.make_url(...).set(database=...)`).
     **Guard:** if the resulting URL's database name does not contain `test`, it raises
     `RuntimeError`; the fixtures never touch the app database.
   - A session-scoped, autouse, **synchronous** fixture that: checks the server answers;
     creates the test database when it is missing (connected to the `postgres` maintenance
     database, `CREATE DATABASE` outside a transaction / autocommit); drops and recreates the
     `public` schema of the test database; then calls `run_migrations(test_url)` directly. Any
     async work it needs runs in its own `asyncio.run(...)` with an engine disposed before
     returning. When the server is not reachable it calls `pytest.fail` (or raises) with exactly
     `PostgreSQL is not reachable at <host>:<port> (API_TEST_DATABASE_URL). Start it with make docker-up.`
     with the real host and port filled in. No test is ever skipped because of the database.
   - A per-test async fixture (W-25), e.g. `session_factory`: a new engine for the test URL
     (per test, or `NullPool`; never shared across tests, since asyncpg connections belong to
     one event loop), one connection, an outer transaction begun on it, and
     `async_sessionmaker(bind=connection, expire_on_commit=False,
     join_transaction_mode="create_savepoint")`. Code under test may commit; on teardown the
     fixture rolls the outer transaction back, closes the connection and disposes the engine.
   - `client` builds `Settings(issuer=ISSUER, audience=AUDIENCE, database_url=<test URL>)` and
     passes the per-test factory to `create_app(..., session_factory=...)`.
   - The schema is built only by the migrations, never by `Base.metadata.create_all`. No
     `hash(nodeid)` tricks.
   - `tests/test_notes_api.py` passes unchanged.
10. **New tests** (e.g. `tests/test_database.py`):
    - the guard raises `RuntimeError` for a URL whose database name lacks `test` (e.g.
      `.../emailsender`);
    - one test runs the real lifespan (`async with app.router.lifespan_context(app):`) of an app
      created with `Settings(database_url=<test URL>)` and the per-test session factory, then
      reads `alembic_version` from the test database through a separate connection and finds the
      current head as reported by Alembic's `ScriptDirectory` (with no revisions yet, the head
      is `None` and the table is empty: the assertion compares against the computed head, so it
      keeps working when later items add revisions);
    - isolation: through the per-test session factory it creates a table, inserts a row and
      commits; a separate connection (its own engine) does not see the table.
11. **`AGENTS.md`**:
    - "Run locally": the API needs PostgreSQL (start `make docker-up` first) and runs
      `alembic upgrade head` at startup; without PostgreSQL it does not start.
    - "Validation": `uv run pytest` in `api/` needs PostgreSQL running (any run mode's), creates
      the `emailsender_test` database itself (override with `API_TEST_DATABASE_URL`, which must
      contain `test`), and fails with a clear message when PostgreSQL is not reachable.
12. Nothing changes under `bff/` or `web/`, and no compose file, Makefile target or
    `api/.env.example` line changes.

## Acceptance criteria

1. With PostgreSQL up (any run mode), in `api/`: `uv run pytest`, `uv run ruff check .` and
   `uv run mypy app tests` all pass, and the pytest summary includes the existing notes tests.
   In `bff/` the same three commands still pass; in `web/` `npm run build` passes.
2. With PostgreSQL unreachable, `uv run pytest` fails with the "PostgreSQL is not reachable at
   <host>:<port> (API_TEST_DATABASE_URL). Start it with make docker-up." message, and the
   summary reports no skipped tests. Check either by stopping PostgreSQL or, where no container
   engine is available (dev container), with
   `API_TEST_DATABASE_URL=postgresql+asyncpg://emailsender:emailsender@localhost:5999/emailsender_test uv run pytest`
   (message names `localhost:5999`).
3. `uv run pytest -k guard` (or the guard test's name) runs a test asserting `RuntimeError` for
   a URL without `test`, and it passes.
4. A test runs `app.router.lifespan_context(app)` against `emailsender_test` and asserts the
   `alembic_version` contents equal the Alembic head; it passes.
5. A test creates a table and a row through the per-test session factory, commits, and asserts
   a separate connection does not see the table; it passes. After the test run,
   `psql postgresql://emailsender:emailsender@localhost:5432/emailsender_test -c '\dt'` (or an
   equivalent query) shows only `alembic_version`.
6. In `api/`: `uv run alembic upgrade head` then `uv run alembic check` against the dev
   database (`emailsender`) succeed, and `check` reports no new upgrade operations.
7. `ls api/migrations` shows `env.py`, `script.py.mako` and `versions/` (empty apart from a
   keep file); `api/alembic.ini` exists; `grep -n "compare_type=True" api/migrations/env.py`
   and `grep -n "compare_server_default=True" api/migrations/env.py` match.
8. `api/app/models/base.py` defines `NAMING_CONVENTION` exactly as in Requirement 3, `Base`,
   `IdMixin`, `TimestampMixin` and `SoftDeleteMixin`; `grep -rn utcnow api/app api/migrations`
   finds nothing.
9. `api/app/dependencies.py` defines `get_session` and `SessionDep`, and `Container` has a
   `sessions` field.
10. With PostgreSQL up, `make backend`: the API log shows the Alembic upgrade and the server
    starts; uvicorn's request log lines still appear after startup; signed in as `alice` on
    http://localhost:5173, adding and listing notes works. With PostgreSQL stopped (or
    `API_DATABASE_URL` pointing at a closed port), the API exits on startup with the migration
    error logged.
11. `make sandbox-up`: `make sandbox-logs` shows the `api` container running the Alembic
    upgrade and starting; the notes demo works at http://localhost:5173. (Needs a container
    engine; not checkable inside the dev container.)
12. `AGENTS.md` "Run locally" and "Validation" state that the API and its tests need
    PostgreSQL, as in Requirement 11.
13. `git diff --stat main` touches only files under `api/` (no change to `api/.env.example`),
    `AGENTS.md`, and the job's spec file.

## Out of scope

- Any table, model class or Alembic revision (API-4 on); moving the notes demo to the database.
- `BaseSchema`, `Page`, domain errors, turning `app/schemas.py` into a package (API-3).
- Using `SessionDep` in any router or service.
- Startup recovery, seeding or any other lifespan step besides migrations (API-11, API-14).
- testcontainers, SQLite or any fallback when PostgreSQL is down; skipping tests.
- Changes to compose files, the Makefile, `.devcontainer/`, `api/.env.example`, `bff/`, `web/`.
- A `make` target for migrations or a separate migration command in the run modes.

## Assumptions

- The lifespan test compares `alembic_version` with Alembic's computed head instead of a
  literal: with no revisions yet the head is `None` and the table is empty, and this keeps the
  test valid when later items add revisions.
- The session-scoped setup fixture is synchronous and uses `asyncio.run` for its async checks:
  the repo gives each test its own event loop, and the async Alembic `env.py` itself calls
  `asyncio.run`, which cannot run inside a running loop (backend.md Pitfalls).
- `env.py` keeps existing loggers alive (`disable_existing_loggers=False`): Alembic's default
  `fileConfig` would otherwise silence uvicorn's and the app's loggers once the lifespan
  migrates. backend.md does not name this; it is needed for criterion 10.
- `alembic.ini` gets no URL; `env.py` falls back to `Settings().database_url`, so the CLI picks
  up `API_DATABASE_URL` from `api/.env` like the app.
- `migrations/versions/` is kept in git with a `.gitkeep`, since git does not track empty
  directories and Alembic needs the folder.
- Criterion 2 may be checked with an unreachable `API_TEST_DATABASE_URL` instead of stopping
  PostgreSQL, because the dev container the factory runs in has no container engine.
