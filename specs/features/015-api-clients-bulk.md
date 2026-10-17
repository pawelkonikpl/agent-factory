# API clients: bulk create endpoint

> Feature: Add `POST /clients/bulk`, which creates clients row by row and reports per-row errors without stopping, as specified in `specs/email-sender/backend.md` API-6 (covers B4, bulk part)

## Context

This is roadmap item API-6 of Phase 4 (Email Sender API). The source of truth is
`specs/email-sender/backend.md`, "API-6: Bulk client import endpoint" (Requirements, Pitfalls,
Acceptance criteria) plus that file's "Rules for every item" (layout, tests with the code,
`401` and every status code tested, validation commands green). The wire format is in
`specs/email-sender/api-contract.md` §2 "ClientBulkCreateSchema / ClientBulkResultSchema" and
the `POST /clients/bulk` row of §3.2. The UI for it (F11, import from Excel/CSV) is deferred
(`specs/email-sender/README.md` D7), so this job is API only.

API-5 (`specs/features/013-api-clients.md`) built everything this job reuses:

- `api/app/schemas/clients.py`: `ClientCreateSchema` (camelCase via `BaseSchema` in
  `api/app/schemas/base.py`, `EmailStr` primary email, trimmed `CompanyName` with the messages
  "Company name cannot be empty" / "... cannot exceed 128 characters", `category_ids` default
  `[]`).
- `api/app/services/client_service.py`: `ClientService.create` runs `_check_email_free`
  (raises `ConflictError("Client with email '{email}' already exists")`) and `_load_categories`
  (raises `BusinessRuleError("Categories not found: 3, 7")`, duplicates ignored), then calls
  `ClientRepository.create`.
- `api/app/repositories/client_repository.py`: `ClientRepository.create` adds the client and
  calls `_commit_email`, which **commits** the session and maps an `IntegrityError` from the
  partial unique index `uq_clients_primary_email_not_deleted` (`api/app/models/client.py`) to
  `ConflictError`, after a rollback. A commit inside `session.begin_nested()` commits the outer
  transaction, so the bulk path cannot call `create` as-is inside a per-row savepoint: it needs
  a repository method that adds and flushes inside a savepoint without committing.
- `api/app/api/clients.py`: the router, every route taking `PrincipalDep` and
  `ClientServiceDep` (`api/app/dependencies.py`, one `AsyncSession` per request, created with
  `expire_on_commit=False` in `api/app/database.py`).
- Tests: `api/tests/test_clients_schemas.py`, `test_clients_service.py` (service against the
  test database) and `test_clients_api.py` (through the `client` and `bearer` fixtures in
  `api/tests/conftest.py`, with a parametrized `test_missing_token_answers_401`).

Layer rules (`specs/email-sender/README.md` §5): the router only does HTTP, the service owns the
rules and raises typed domain errors, the repository owns SQLAlchemy (so the savepoint lives in
the repository, not the service).

## Requirements

1. `api/app/schemas/clients.py` gains:
   - `ClientBulkCreateSchema(BaseSchema)` with `clients: list[dict[str, Any]]`, constrained to
     1 to 1000 items (`Field(min_length=1, max_length=1000)`), so an empty list or 1001 rows
     answers `422` from FastAPI. Rows stay raw dicts; they are not typed as
     `ClientCreateSchema`.
   - `ClientBulkErrorSchema(BaseSchema)` `{row: int, message: str}` and
     `ClientBulkResultSchema(BaseSchema)` `{success: int, failed: int,
     errors: list[ClientBulkErrorSchema]}`.
2. `ClientService.bulk_create(data: ClientBulkCreateSchema) -> ClientBulkResultSchema` processes
   the rows in order; `row` is the 1-based position in `clients`. For each row:
   1. Validate it with `ClientCreateSchema.model_validate(row)`. On `ValidationError` the
      message is the errors joined with `"; "`, each formatted `<field>: <msg>`, where `<field>`
      is the error's `loc` joined with `.` with the first element in camelCase (for example
      `primaryEmail: value is not a valid email address: ...`,
      `companyName: Value error, Company name cannot be empty`, `categoryIds.0: ...`), and just
      `<msg>` when `loc` is empty. `msg` is Pydantic's text, unchanged.
   2. If the validated `primary_email` equals one accepted earlier in this batch, fail the row
      with "Client with email '{email}' already exists" (the same message as the service's
      `ConflictError`).
   3. Otherwise run the same checks as `create`: `_check_email_free` and `_load_categories`.
      Their `ConflictError` / `BusinessRuleError` message is the row's message.
   4. Create the client through the new repository method (requirement 3). A `ConflictError`
      from it (the unique index) fails the row with its message.
   A failing row appends `{row, message}` to `errors` and the loop continues. `success` counts
   created rows, `failed` counts failed rows, `success + failed == len(clients)`.
3. `ClientRepository` gains a method that adds one client with its categories inside
   `session.begin_nested()` and flushes (no commit), mapping an `IntegrityError` to the same
   `ConflictError` as `_commit_email`; a failed row's savepoint is rolled back and never undoes
   earlier rows. It also gains a `commit()` the service calls once after the loop. The existing
   `create`, `update` and their behaviour stay unchanged.
4. The create rules are not duplicated: `create` and `bulk_create` share the email check and
   the category loading (the existing `_check_email_free` / `_load_categories`, or one helper
   both call).
5. `api/app/api/clients.py` gets `POST /clients/bulk` (path `"/bulk"` on the existing router),
   body `ClientBulkCreateSchema`, `PrincipalDep`, `ClientServiceDep`,
   `response_model=ClientBulkResultSchema`, status `200`.
6. Tests, following the existing files' style:
   - `test_clients_schemas.py`: `ClientBulkCreateSchema` rejects `[]` and 1001 rows, accepts 1
     and 1000; the result schema dumps `success`, `failed`, `errors[].row`, `errors[].message`.
   - `test_clients_service.py`: a batch mixing valid rows, a duplicate of an existing client, a
     duplicate of an earlier row in the batch, an invalid email, an empty company name and an
     unknown category gives the right counts and `{row, message}` pairs, and the valid rows
     exist afterwards (read back through the service or a fresh session); a soft-deleted
     client's email is accepted in a batch; a row that hits the unique index in the repository
     (bypassing the service check) fails only that row while earlier rows stay.
   - `test_clients_api.py`: add `POST /clients/bulk` to `test_missing_token_answers_401`; the
     mixed batch answers `200` with the expected body and the valid clients appear in
     `GET /clients/`; `{"clients": []}` and 1001 rows answer `422`.
7. `specs/email-sender/api-contract.md` §3.2, the `POST /clients/bulk` row: the response cell
   says `422` for an empty list or more than 1000 rows, and §2 "ClientBulkCreateSchema /
   ClientBulkResultSchema" states the `message` format (the service's message for business
   errors, or the validation errors as `<camelCase field>: <msg>` joined with `; `).

## Acceptance criteria

1. With PostgreSQL running, `cd api && uv run pytest` passes, including the new tests named in
   requirement 6.
2. `cd api && uv run ruff check .` and `cd api && uv run mypy app tests` pass.
3. `api/tests/test_clients_api.py` has a test posting a batch with valid rows, a duplicate of an
   existing client, a duplicate of an earlier row, an invalid email, an empty company name and
   an unknown category; it asserts `200`, `success` and `failed` equal to the counts, `errors`
   with the exact row numbers (1-based) and messages ("Client with email '...' already exists"
   for both duplicates, "Categories not found: <id>", `primaryEmail: ...`,
   `companyName: Value error, Company name cannot be empty`), and that the valid clients are
   listed by `GET /clients/` afterwards.
4. `api/tests/test_clients_api.py` asserts `422` for `{"clients": []}` and for 1001 rows, and
   `test_missing_token_answers_401` includes `POST /clients/bulk` with `401`.
5. `api/tests/test_clients_service.py` has a test where one row fails at the unique index inside
   the repository and the rows before and after it are still created.
6. `api/app/api/clients.py` contains a `POST /clients/bulk` route taking `PrincipalDep`, and
   `ClientBulkCreateSchema.clients` is typed `list[dict[str, Any]]` (not
   `list[ClientCreateSchema]`).
7. `specs/email-sender/api-contract.md` §3.2's bulk row mentions `422` for an empty list, and
   §2 describes the `message` format.
8. `git diff main -- bff/ web/` is empty.

## Out of scope

- Any web UI, Excel/CSV parsing or file upload (F11, deferred).
- Updating or upserting existing clients from a batch; a duplicate is always an error row.
- A transaction-wide "all or nothing" mode, dry-run flag or any other option.
- Changing `POST /clients/`, `PUT /clients/{id}` or their messages, or the unique index.
- Accepting rows that are not JSON objects (they fail the whole request with `422`, as the
  `list[dict]` type gives).
- New migrations (no table changes).

## Assumptions

- The in-batch duplicate check compares the validated `primary_email` exactly, as the database
  index does; reason: the batch rule must agree with the existing uniqueness rule, which is
  case-sensitive after `EmailStr` normalisation.
- The in-batch duplicate uses the same message as the database duplicate; reason: backend.md
  lists only the service's message for business errors.
- All rows are committed once at the end, with one savepoint per row; reason: backend.md asks for
  savepoints, and a commit inside a savepoint would commit the outer transaction.
- Nested `loc` entries are joined with `.`, with only the first element camelCased; reason:
  backend.md gives `<camelCase field>: <msg>` without saying how list indexes are shown.
- The Pydantic `msg` keeps its `Value error, ` prefix; reason: the contract (§0 Errors) already
  documents that prefix for 422 messages, and backend.md says to join the validation errors as
  they are.
