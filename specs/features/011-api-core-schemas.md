# API core: BaseSchema, domain errors and pagination

> Feature: Add the API core: the camelCase `BaseSchema` (with `app/schemas.py` turned into a package), typed domain errors mapped by one handler, the paginated `Page` response `{ items, total }` and the `skip`/`limit` parameters, as specified in `specs/email-sender/backend.md` API-3 (covers B2)

## Context

This is roadmap item API-3 of Phase 4 (Email Sender API). The source of truth is
`specs/email-sender/backend.md`, section "API-3: Core" (Requirements, Pitfalls, Acceptance
criteria). Background is in `specs/email-sender/README.md`: §5 (the target `api/` layout, with
`app/schemas/base.py`, `app/errors.py` holding "token errors (existing) + domain errors"), §6
(API conventions: every Email Sender schema inherits `BaseSchema`, the notes schemas don't;
three validation layers, where services raise typed domain errors), §10 W-23 (the old code
picked 400 or 404 by matching exception text) and §11 D28 (page size), D29 (schema package),
D30 (no request-logging middleware). `specs/email-sender/api-contract.md` §0 ("Errors",
"Pagination") and §2 ("Page<T>") already describe the wire format this item builds. This spec
restates the backend.md section; where they differ, this spec wins.

API-2 (`specs/features/010-api-async-database.md`) is merged: `create_app` takes an optional
`session_factory`, `app/dependencies.py` has `SessionDep`, and `tests/conftest.py` has the
session-scoped migrated `emailsender_test` database, the per-test `session_factory`, and the
`client`, `issuer` and `bearer` fixtures. Every `api/` test run needs PostgreSQL.

The API today (`api/`):

- `app/schemas.py`: one module with `NOTE_MAX_LENGTH`, `NoteCreate` and `NoteResponse`
  (plain `BaseModel`, snake_case on the wire: the SPA's notes zod schema reads `created_at`).
  Its only importer is `app/api/notes.py` (`from app.schemas import NoteCreate, NoteResponse`).
  `api/Containerfile` copies the whole `app` directory, so a package needs no image change.
- `app/errors.py`: `InvalidTokenError` (with `token_present`) and `KeySetUnavailableError`,
  both plain `Exception` subclasses. Its docstring says the HTTP mapping lives in
  `app/main.py`.
- `app/main.py`: `create_app(settings=None, *, http_client=None, clock=..., session_factory=None)`
  includes `app.api.notes.router`, defines `/health`, and registers one exception handler per
  token error: `InvalidTokenError` → 401 `{"detail": "Invalid or missing access token"}` with a
  `WWW-Authenticate: Bearer realm="demo-api"` challenge (plus `error="invalid_token"` when a
  token was sent), `KeySetUnavailableError` → 503. The new handler follows the same
  `@app.exception_handler(...)` pattern inside `create_app`.
- `app/dependencies.py`: `PrincipalDep`, `NoteServiceDep`, `SessionDep`, all as
  `Annotated[..., Depends(...)]` aliases. `PageParamsDep` follows that alias style.
- Installed versions (from `api/uv.lock`): FastAPI 0.143.0 and Pydantic 2.14.0. FastAPI itself
  only requires `pydantic>=2.9`; `api/pyproject.toml` lists no direct `pydantic` dependency,
  although `app/` imports it. The `validate_by_name`, `validate_by_alias` and
  `serialize_by_alias` config keys exist only from Pydantic 2.11.
- Tooling (`api/pyproject.toml`): `requires-python = ">=3.11"`, ruff `target-version = "py311"`
  with rules E F W I UP B SIM RUF ASYNC, mypy `strict` with the pydantic plugin.
- Tests: `tests/test_notes_api.py` (notes and token behaviour through `client`),
  `tests/test_database.py` (API-2). README §5 names test files `test_<area>_*.py`.

A quick check against the installed versions confirmed the approach: a `BaseSchema` with the
config below validates `{"companyName": ...}` and `{"company_name": ...}` and dumps
`companyName`; `Page[Thing]` dumps `{"items": [{"companyName": ...}], "total": 1}`; a dataclass
`PageParams` with `Query` defaults used as `Annotated[PageParams, Depends()]` gives defaults
0/100 and 422 for `skip=-1`, `limit=0` and `limit=1001`, and passes strict mypy and ruff.

## Requirements

1. **Schema package (D29).** `api/app/schemas.py` becomes the package `api/app/schemas/`:
   - `app/schemas/notes.py` holds the current contents of `app/schemas.py`, byte for byte
     (move it with `git mv` so the history follows). `NoteCreate` and `NoteResponse` stay plain
     `BaseModel` subclasses and must not inherit `BaseSchema`.
   - `app/schemas/__init__.py` exists and re-exports nothing (an empty file or a one-line
     docstring).
   - `app/api/notes.py` imports `from app.schemas.notes import NoteCreate, NoteResponse`. No
     other change to `app/api/notes.py`.
2. **`app/schemas/base.py`** holds:
   - `BaseSchema(BaseModel)` with
     `model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True, validate_by_alias=True, serialize_by_alias=True, from_attributes=True)`
     (`to_camel` from `pydantic.alias_generators`): camelCase out, camelCase or snake_case in,
     and validation from ORM objects for later items. Not `populate_by_alias` or
     `populate_by_name`.
   - A module-level `T = TypeVar("T")` and `Page(BaseSchema, Generic[T])` with `items: list[T]`
     and `total: int`. Python 3.11 syntax: `Generic[T]`, not `class Page[T]`.
   - `PageParams` with `skip: int = Query(0, ge=0)` and `limit: int = Query(100, ge=1, le=1000)`
     (D28), read by FastAPI as the query parameters `skip` and `limit` and exposed as the
     attributes `.skip` and `.limit` (a dataclass, as checked above, is fine), and
     `PageParamsDep = Annotated[PageParams, Depends()]`.
3. **Pydantic floor.** `pydantic>=2.11` is added to the `dependencies` in `api/pyproject.toml`
   with `uv add "pydantic>=2.11"` in `api/`, so `uv.lock` is updated in the same change and the
   installed Pydantic stays 2.14.0 (no other package version changes).
4. **Domain errors** in `app/errors.py`: `DomainError(Exception)` and its direct subclasses
   `NotFoundError`, `ConflictError` and `BusinessRuleError`, each raised with one message string
   (`NotFoundError("Category 3 not found")`) and with a one-line docstring saying when to raise
   it. `app/errors.py` stays free of HTTP: no status codes and no FastAPI imports in it.
   `InvalidTokenError` and `KeySetUnavailableError` are unchanged and do not inherit
   `DomainError`.
5. **One handler** in `create_app` (`app/main.py`): `@app.exception_handler(DomainError)`
   answers `JSONResponse({"detail": str(exc)})` with status 404 when `exc` is a `NotFoundError`
   and 400 otherwise (`ConflictError`, `BusinessRuleError`, or a bare `DomainError`). It is the
   only place that maps domain errors to HTTP status codes; no router catches `ValueError` or a
   domain error, and nothing matches exception text (W-23). The `InvalidTokenError` and
   `KeySetUnavailableError` handlers stay as they are.
6. **Tests**, in `api/tests/`:
   - `tests/test_core_schemas.py` (unit tests, no HTTP): a small `BaseSchema` subclass with a
     snake_case field (for example `company_name`) dumps the camelCase key
     (`model_dump()` and `model_dump_json()`), and validates both camelCase and snake_case
     input to the same value; `Page[<that subclass>]` dumps exactly
     `{"items": [{"companyName": ...}], "total": n}`; `NoteResponse` is not a `BaseSchema`
     subclass and still dumps `created_at`.
   - `tests/test_core_api.py` (through HTTP, an app built like the `client` fixture builds it,
     with test-only routes added in the test code, never in `app/`):
     - a route taking `PageParamsDep` that returns the `skip` and `limit` it received: no
       parameters give `skip=0`, `limit=100`; `skip=5&limit=1000` gives 5 and 1000;
       `skip=-1`, `limit=0` and `limit=1001` each answer 422;
     - routes raising `NotFoundError("Thing 1 not found")`, a `ConflictError` and a
       `BusinessRuleError`: 404 with exactly `{"detail": "Thing 1 not found"}`, and 400 with
       `{"detail": <the message>}` for the other two;
     - a route taking `PrincipalDep` that raises `NotFoundError`: without an `Authorization`
       header it answers 401 with `{"detail": "Invalid or missing access token"}` and
       `WWW-Authenticate: Bearer realm="demo-api"`; with a valid `bearer()` token it answers 404.
   - Splitting the `client` fixture in `tests/conftest.py` into an `app` fixture plus `client`,
     so tests can add routes, is allowed. `tests/test_notes_api.py` and `tests/test_database.py`
     do not change.
7. Strict mypy and ruff pass on all new code without new `# type: ignore` or `# noqa`
   comments and without config changes.
8. No doc changes: `AGENTS.md` does not describe the API's modules, and `api-contract.md` §0
   and §2 already describe `Page<T>`, the domain error statuses and the pagination parameters.

## Acceptance criteria

1. **Package.** `test -d api/app/schemas && test ! -e api/app/schemas.py` succeeds;
   `git show main:api/app/schemas.py | diff - api/app/schemas/notes.py` prints nothing;
   `grep -n "from app.schemas.notes import NoteCreate, NoteResponse" api/app/api/notes.py`
   matches; `grep -rn "BaseSchema" api/app/schemas/notes.py` matches nothing.
2. **BaseSchema config.** `api/app/schemas/base.py` contains `alias_generator=to_camel`,
   `validate_by_name=True`, `validate_by_alias=True`, `serialize_by_alias=True` and
   `from_attributes=True`, and `grep -rn "populate_by" api/app` matches nothing.
3. **Schema unit tests.** In `api/`, `uv run pytest tests/test_core_schemas.py -v` passes and
   lists the tests from Requirement 6: camelCase dump, camelCase and snake_case input,
   `Page` dump `{"items": [...], "total": n}`, notes schema unchanged.
4. **Pagination parameters.** In `api/`, `uv run pytest tests/test_core_api.py -v` passes,
   including the tests for the defaults (0 and 100), `skip=5&limit=1000`, and 422 for
   `skip=-1`, `limit=0` and `limit=1001`.
5. **Domain handler.** The same run includes passing tests for 404
   `{"detail": "Thing 1 not found"}`, 400 for `ConflictError` and for `BusinessRuleError` with
   the message in `detail`, and 401 with `WWW-Authenticate: Bearer realm="demo-api"` on a
   `PrincipalDep` route without a token (404 with a token).
6. **One mapping, no HTTP in errors.** `grep -n "exception_handler(DomainError)" api/app/main.py`
   matches once; `grep -nE "fastapi|status_code|HTTP_" api/app/errors.py` matches nothing;
   `grep -n "class DomainError\|class NotFoundError(DomainError)\|class ConflictError(DomainError)\|class BusinessRuleError(DomainError)" api/app/errors.py`
   shows all four classes.
7. **Notes unchanged.** `git diff --quiet main -- api/tests/test_notes_api.py api/tests/test_database.py`
   succeeds, and the notes tests pass in the full run below.
8. **Pydantic floor.** `grep -n '"pydantic>=2.11' api/pyproject.toml` matches; in `api/`,
   `uv sync --locked` succeeds and `uv run python -c "import pydantic; print(pydantic.VERSION)"`
   prints `2.14.0`.
9. **Validation.** With PostgreSQL running (`make docker-up` or the dev container's), in
   `api/`: `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests` all pass.
10. **Scope.** `git diff --name-only main` lists only files under `api/` plus
    `specs/features/011-api-core-schemas.md`; nothing under `bff/`, `web/`, `keycloak/`,
    `.devcontainer/`, `compose.yaml`, `Makefile`, `AGENTS.md` or `specs/email-sender/` changes,
    and no file is added under `api/migrations/versions/`.

## Out of scope

- Anything the source's B2 had that backend.md drops: CORS and `expose_headers`, a
  `get_current_user` stub (`PrincipalDep` exists), a request-logging middleware,
  `logging.basicConfig` (D30), and an OpenAPI description. The app's `title` stays
  "Demo notes API".
- The encryption part of B2 (`API_ENCRYPTION_KEY`, Fernet): API-7.
- Any Email Sender model, migration, repository, service, router or tag (categories, clients,
  campaigns, emails, configuration): API-4 onwards. No production route uses `PageParamsDep`,
  `Page` or the domain errors yet.
- Changing the notes demo: its schemas, wire format, router, service, in-memory repository or
  tests.
- Mapping `IntegrityError` or `ValueError` to domain errors, logging in the domain handler, or
  extra fields (codes, IDs) on the domain errors.
- Re-exports from `app/schemas/__init__.py`, a `Page` helper for counting, or a different
  pagination style (cursor, page numbers, `X-Total-Count`).
- Changes to the BFF, its proxy or its forwarded headers, and to `web/` (the SPA's `Page` zod
  helper is UI-5).

## Assumptions

- A bare `DomainError` answers 400. Reason: the handler maps `NotFoundError` to 404 and "the
  other two" to 400; treating every non-404 domain error the same keeps one rule.
- `app/schemas/__init__.py` re-exports nothing. Reason: backend.md says to update the import in
  `app/api/notes.py`, and per-area modules imported by path avoid cycles between areas.
- `pydantic>=2.11` becomes a declared dependency. Reason: `app/` imports Pydantic directly and
  `BaseSchema` relies on config keys added in 2.11, while FastAPI alone allows 2.9; the lock
  already has 2.14.0, so nothing installed changes.
- The test-only routes are added in `tests/` to an app built by a fixture (optionally a new
  `app` fixture in `conftest.py`). Reason: backend.md asks for test-only routes, and none may
  exist in `app/`.
- The handler does not log. Reason: domain errors are expected client errors, and uvicorn's
  access log already records the status (D30).
- No documentation changes. Reason: `AGENTS.md` doesn't list API modules, and
  `api-contract.md` already describes `Page<T>`, the error statuses and `skip`/`limit`; the
  API-3 section asks for no doc update.
