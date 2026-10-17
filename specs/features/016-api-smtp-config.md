# API per-user SMTP settings: `configs` table, Fernet encryption, `GET`/`PUT /config/smtp`

> Feature: Add per-user SMTP settings to the API: the `configs` table keyed by `user_sub`, its migration, Fernet encryption of the password with `API_ENCRYPTION_KEY`, and `GET`/`PUT /config/smtp`, as specified in `specs/email-sender/backend.md` API-7 (covers B5, B2 encryption)

## Context

This is roadmap item API-7 of Phase 4 (Email Sender API). The source of truth is
`specs/email-sender/backend.md`, "API-7: Per-user SMTP settings" (Requirements, Pitfalls,
Acceptance criteria), plus that file's "Rules for every item". The wire format is in
`specs/email-sender/api-contract.md` §0 (errors: `422` with Pydantic's `detail` list),
§2 (`SmtpConfigResponseSchema`, `SmtpConfigUpdateSchema`, `MessageSchema`) and §3.5 (the
`/config` endpoints; `POST /config/smtp/test` is API-8, not this item). Background is in
`specs/email-sender/README.md`: §5 (layout: `models/config.py`, `schemas/smtp_config.py`,
`api/config.py`, `services/encryption.py`; the `Container` holds the encryption service),
§6 (conventions: `BaseSchema`, no bare dicts between layers, every endpoint takes
`PrincipalDep`), §7 (`API_ENCRYPTION_KEY`, required; `api/.env` doesn't pick up new lines, so
`AGENTS.md` says to copy it), §9 (the demo key is public; never log passwords), §10 W-10 (the
key must be in `.env.example`, which the sandbox reads) and §11 D5 (only `configs` is per
user) and D12 (`user_sub` = `Principal.subject`, no `users` table, no foreign key). This spec
restates the backend.md section. Where they differ, this spec wins.

What API-2 to API-6 left in `api/` (specs `specs/features/010-api-async-database.md` to
`015-api-clients-bulk.md`):

- `app/config.py`: `Settings(BaseSettings)` with `env_prefix="API_"`, `env_file=".env"`,
  `extra="ignore"`; fields `issuer`, `audience`, `http_timeout_seconds`,
  `jwks_min_refresh_interval_seconds`, `database_url`, `test_database_url`. Every field has a
  default today.
- `app/main.py`: `create_app(settings=None, *, http_client, clock, session_factory)` builds
  `Settings()` when none is given, then `build_container(...)`, includes the `notes`,
  `categories` and `clients` routers, and maps `DomainError`s (404 for `NotFoundError`, else
  400). uvicorn calls this factory at startup, so an exception from `Settings()` stops the API
  from starting.
- `app/dependencies.py`: the frozen dataclass `Container(verifier, notes, sessions)`,
  `build_container(settings, http, clock, sessions)`, `PrincipalDep`, `SessionDep`, and
  per-request services built from the session (`get_client_service` / `ClientServiceDep`).
- `app/models/base.py`: `Base` with `NAMING_CONVENTION`, `IdMixin`, `TimestampMixin`
  (Python-side `default`/`onupdate` `utc_now`), `utc_now()`. `app/models/__init__.py` imports
  every model and lists it in `__all__`; Alembic sees only those tables.
- `app/schemas/base.py`: `BaseSchema` (camelCase out, camelCase or snake_case in,
  `from_attributes`). There is no `MessageSchema` yet.
- The categories and clients areas are the pattern: repository owns SQLAlchemy and commits;
  service raises only domain errors; router (`APIRouter(prefix=..., tags=[...])`) only does
  HTTP, each endpoint taking `PrincipalDep`. `Principal` (`app/services/token_verifier.py`) has
  `subject`.
- Migrations: the head is `524355d88f2d` (`migrations/versions/524355d88f2d_add_clients.py`).
  `migrations/env.py` calls `Settings().database_url` when no URL is set on the config, so the
  Alembic CLI reads `api/.env` and will need the new key there.
- Tests: `tests/conftest.py` builds `Settings(issuer=..., audience=..., database_url=...)` in the
  `app` fixture and `Settings()` in `resolve_test_database_url`; `tests/test_database.py` builds
  `Settings(...)` by hand three times. The `bearer(**claims)` fixture makes a token (default
  `sub` `alice`; `bearer(sub="bob")` for a second user). `session_factory` rolls every test back.
- Dependencies: `cryptography` 50.0.2 is installed only transitively (through `pyjwt[crypto]`);
  `api/pyproject.toml` doesn't list it. `api/Containerfile` runs `uv sync --frozen --no-dev`, so
  it must be in `api/uv.lock`.
- `compose.yaml` gives the sandbox's `api` service `env_file: ./api/.env.example`, so the demo
  key in `.env.example` is what the sandbox uses. The dev container's `post-create.sh` copies
  `.env.example` to `.env` only when `.env` is missing.
- The worktree's `api/.env` (git-ignored) lacks the key, like every existing `api/.env`.

I checked in `api/` (Pydantic 2.14, pydantic-settings 2.15, cryptography 50.0.2):

- A `field_validator` on `encryption_key: SecretStr` that calls
  `Fernet(value.get_secret_value())` and re-raises its `ValueError` as
  `ValueError("...")` `from None` gives a one-line `ValidationError` naming `encryption_key`.
  With `hide_input_in_errors=True` in `SettingsConfigDict`, the rejected value is not printed.
  A missing key gives `encryption_key  Field required`.
- `Fernet.encrypt` returns the token as URL-safe base64 `bytes` (`gAAAAA...`): decode it to
  `str` and store it as is. `Fernet.decrypt` raises `InvalidToken` for garbage and for `""`.

The dev database `emailsender` is shared with the main checkout, whose API migrates it at
startup. As in 013, generate the revision and run the migration checks against
`emailsender_test` only, or the main checkout's API stops starting ("Can't locate revision").

## Requirements

1. **Dependency.** In `api/`, `uv add cryptography` (declared directly although PyJWT pulls it
   in). `pyproject.toml` and `uv.lock` change to match; no other dependency changes.
2. **Settings** (`app/config.py`): add `encryption_key: SecretStr` with no default
   (`API_ENCRYPTION_KEY`, required). A field validator checks it is a valid Fernet key and
   otherwise raises `ValueError("API_ENCRYPTION_KEY must be a valid Fernet key (32 url-safe
   base64-encoded bytes)")` (wording may vary, but it names `API_ENCRYPTION_KEY` and says
   Fernet). Set `hide_input_in_errors=True` so neither a valid nor an invalid key ever appears
   in an error or log. Since uvicorn builds the app through `create_app`, which builds
   `Settings()`, a missing or invalid key stops the API at startup.
3. **`api/.env.example`**: add `API_ENCRYPTION_KEY=<key>` with a key generated by
   `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`,
   and a comment line saying it is a dev-only demo secret, public because it is in git, and to
   generate your own in `api/.env` before saving a real SMTP password. Also add the same line to
   the worktree's (ignored) `api/.env`, so the tests and the Alembic CLI run there.
4. **Encryption** (`app/services/encryption.py`): `EncryptionService(key: str)` wrapping one
   `Fernet`:
   - `encrypt(plaintext: str) -> str`: the Fernet token decoded to `str`, stored as is [FIX: no
     second base64 encoding].
   - `decrypt(token: str) -> str`: `""` raises `ValueError` (for example
     `"Cannot decrypt empty text"`); an invalid token raises
     `ValueError("Decryption failed: invalid token")` (message starts `Decryption failed: `,
     contains neither the token nor the key), chained `from None`.
   - `generate_key() -> str` as a `staticmethod`: a new Fernet key as `str`.
   - `Container` gets a field `encryption: EncryptionService`; `build_container` creates one
     instance from `settings.encryption_key.get_secret_value()`.
5. **Model** (`app/models/config.py`): `Config(IdMixin, TimestampMixin, Base)`, table
   `configs`: `user_sub` `String(255)` NOT NULL, `index=True`; `config_key` `String(255)` NOT
   NULL; `config_value_encrypted` `Text` NOT NULL; `is_encrypted` bool NOT NULL, Python-side
   `default=True` (no server default, like `is_active` on clients).
   `__table_args__ = (UniqueConstraint("user_sub", "config_key", name="uq_user_config_key"),)`.
   No `SoftDeleteMixin`, no foreign key, no `users` table (D12). `app/models/__init__.py`
   imports `Config` and lists it in `__all__`.
6. **Migration.** One new Alembic revision, generated in `api/` with
   `uv run alembic revision --autogenerate -m "add configs"` against `emailsender_test` at
   `524355d88f2d`, then read and corrected by hand. `down_revision` is `'524355d88f2d'`.
   `upgrade()` creates `configs` (`pk_configs`, `uq_user_config_key`) and `ix_configs_user_sub`;
   `downgrade()` drops the index and the table. It passes `ruff check` without `# noqa`;
   earlier revisions and `script.py.mako` don't change.
7. **Repository** (`app/repositories/config_repository.py`):
   `ConfigRepository(session: AsyncSession, encryption: EncryptionService)` with class
   constants `SMTP_KEYS = ["smtp_server", "smtp_port", "smtp_user", "smtp_use_tls"]` and
   `SMTP_ENCRYPTED_KEYS = {"smtp_password"}`. Rows are always filtered by `user_sub`.
   - `get_smtp_config(user_sub)`: the user's stored `SMTP_KEYS` values, never the password.
   - `get_smtp_config_with_password(user_sub)`: the same plus the decrypted `smtp_password`
     (rows with `is_encrypted` true are decrypted).
   - Both return a frozen dataclass (for example `StoredSmtpConfig` with `smtp_server`,
     `smtp_port`, `smtp_user`, `smtp_use_tls`, `smtp_password`, all `str | None`, the password
     `field(repr=False)`), not a bare dict (README §6).
   - `upsert_smtp_config(user_sub, payload: SmtpConfigUpdateSchema)`: for each of the five
     fields that is not `None`, write `str(value)` under its snake_case key (so `True` becomes
     `"True"` and `587` becomes `"587"`); `smtp_password` is encrypted first and written with
     `is_encrypted=True`, every other key with `is_encrypted=False`. Insert or update by
     (`user_sub`, `config_key`) with PostgreSQL `insert(...).on_conflict_do_update(constraint=
     "uq_user_config_key", ...)` setting the value, `is_encrypted` and `updated_at=utc_now()`,
     so two concurrent first saves can't end in a 500. Keys not in the payload are left alone.
     One commit for the whole call.
8. **Service** (`app/services/smtp_config_service.py`), built with a `ConfigRepository`:
   - `parse_bool(value: str) -> bool`: true for `true`, `1`, `yes` in any case (so `"True"`),
     false otherwise. A module-level function.
   - `get_smtp_config(user_sub) -> SmtpConfigResponseSchema`: each field `None` when not saved;
     `smtp_port` as `int`; `smtp_use_tls` through `parse_bool`.
   - `update_smtp_config(user_sub, payload) -> None`: calls `upsert_smtp_config`.
   - `get_smtp_config_for_sending(user_sub) -> SmtpConfig | None`: `None` when no
     `smtp_server` is saved; otherwise the frozen dataclass
     `SmtpConfig(smtp_server: str, smtp_port: int, smtp_user: str | None, smtp_password: str |
     None, smtp_use_tls: bool)` with the decrypted password, port default 587 and TLS default
     on. `smtp_password` is declared with `field(repr=False)`. No endpoint exposes it (API-8
     uses it).
   - Nothing in the service or repository logs a password, the key or a decrypted value.
9. **Schemas** (`app/schemas/smtp_config.py`, all `BaseSchema`):
   - `SmtpConfigResponseSchema`: `smtp_server: str | None`, `smtp_port: int | None`,
     `smtp_user: str | None`, `smtp_use_tls: bool | None`. It dumps exactly `smtpServer`,
     `smtpPort`, `smtpUser`, `smtpUseTls`; there is no password field.
   - `SmtpConfigUpdateSchema`: every field optional, default `None`, `None` meaning "don't
     change" (a field can't be cleared): `smtp_server` (trimmed; empty after trimming →
     `ValueError("SMTP server cannot be empty")`), `smtp_port` (`int`, 1 to 65535),
     `smtp_user` (trimmed; empty → `ValueError("SMTP user cannot be empty")`; any string,
     not necessarily an email [FIX]), `smtp_password` (`""` → `ValueError("SMTP password
     cannot be empty")`; not trimmed), `smtp_use_tls: bool | None`.
   - `MessageSchema`: `message: str`, in `app/schemas/base.py` (contract §2 lists it as shared).
10. **Router** (`app/api/config.py`): `APIRouter(prefix="/config", tags=["Configuration"])`,
    included in `create_app`. Both endpoints take `PrincipalDep` and use `principal.subject`
    as the user, never an email or a name:
    - `GET /config/smtp` → `200 SmtpConfigResponseSchema` (all `null` when nothing is saved).
    - `PUT /config/smtp` with body `SmtpConfigUpdateSchema` → `200`
      `{"message": "Configuration updated successfully"}` (`response_model=MessageSchema`);
      `422` for an invalid body.
    - Wiring in `app/dependencies.py`: `get_smtp_config_service(session, container)` building
      `SmtpConfigService(ConfigRepository(session, container.encryption))`, and
      `SmtpConfigServiceDep`.
11. **Tests**, following the existing modules' style (new files `test_smtp_config_schemas.py`,
    `test_smtp_config_service.py`, `test_smtp_config_api.py`, `test_encryption.py`):
    - Every hand-built `Settings(...)` in `tests/` passes
      `encryption_key=EncryptionService.generate_key()` (or a module-level generated key), so
      the tests don't depend on the key in `api/.env` apart from the bare `Settings()` in
      `resolve_test_database_url`.
    - Schemas (7): port 0 and 65536 rejected; an empty (or whitespace-only) server rejected;
      the server trimmed; an empty password rejected; all fields `null` accepted; a
      `smtpUser` that isn't an email accepted.
    - Service, against the test database (7): save and read back; the raw
      `config_value_encrypted` of the `smtp_password` row differs from the plain password and
      `EncryptionService.decrypt` gives it back; `get_smtp_config` never carries the password;
      a partial update keeps the other keys; `alice` and `bob` have separate settings;
      `parse_bool` cases (`"True"`, `"true"`, `"1"`, `"YES"` true; `"False"`, `"0"`, `""`
      false); `get_smtp_config_for_sending` returns `None` without a server and the defaults
      587 / TLS on when only the server is saved, and `repr()` of the result doesn't contain the
      password.
    - `EncryptionService`: round trip; an invalid token → `ValueError` starting
      `Decryption failed: `; empty text → `ValueError`; a token from another key → `ValueError`.
    - Endpoints: `401` without a token on both endpoints; `GET` all `null` before saving;
      `PUT` `200` with the message, then `GET` returns the saved values and no password key;
      `422` for `smtpPort: 0`; a value saved by `alice` is not seen by `bob`.
    - Settings: `Settings(encryption_key="not-a-key")` raises `ValidationError` whose text
      names `encryption_key`, says Fernet and doesn't contain `not-a-key`.
12. **`AGENTS.md`**: in "Setup (fresh checkout)" (or right after it), say that an existing
    `api/.env` lacks the new required `API_ENCRYPTION_KEY` and the API, its tests and
    `alembic` won't start without it: copy that line from `api/.env.example`. Say also that the
    demo key is public: before saving a real SMTP password, generate your own key into
    `api/.env` with the command from Requirement 3, or use a dev SMTP server (smtp4dev, coming
    with API-8). Nothing else in `AGENTS.md` changes.

## Acceptance criteria

1. `cd api && uv run pytest` passes (PostgreSQL running, `api/.env` with the key), including
   the new schema, service, encryption, endpoint and settings tests of Requirement 11.
2. `cd api && uv run ruff check .` and `cd api && uv run mypy app tests` pass.
3. `cd bff && uv run pytest && uv run ruff check . && uv run mypy app tests` still pass, and
   `git diff main --stat -- bff web` is empty.
4. `grep -n cryptography api/pyproject.toml` shows a direct dependency, and
   `grep -n '^name = "cryptography"' api/uv.lock` finds it.
5. `grep API_ENCRYPTION_KEY api/.env.example` shows one line, preceded by a dev-only demo
   secret comment, and
   `cd api && uv run python -c "from cryptography.fernet import Fernet; import re; k=[l.split('=',1)[1] for l in open('.env.example') if l.startswith('API_ENCRYPTION_KEY=')][0].strip(); Fernet(k); print('ok')"`
   prints `ok`.
6. `cd api && API_ENCRYPTION_KEY=not-a-key uv run python -c "from app.main import create_app; create_app()"`
   exits non-zero with a `ValidationError` naming `encryption_key` and Fernet, and the output
   doesn't contain `not-a-key`.
7. Against the test database only:
   `cd api && API_DATABASE_URL=postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender_test uv run alembic upgrade head`
   then `... uv run alembic check` (same variable) prints "No new upgrade operations
   detected."; `... uv run alembic downgrade -1` followed by `... upgrade head` succeeds. The
   new revision's `down_revision` is `'524355d88f2d'`.
8. With the stack running (`make docker-up`, `make backend`, `make web`, and the key in
   `api/.env`), signed in as `alice` at http://localhost:5173, the browser's devtools console:
   `fetch('/api/config/smtp').then(r => r.json())` gives all four fields `null`;
   `PUT /api/config/smtp` (with the `X-CSRF` header the BFF requires) and body
   `{"smtpServer":" smtp.example.com ","smtpPort":587,"smtpUser":"noreply@localhost","smtpPassword":"secret","smtpUseTls":false}`
   answers `{"message":"Configuration updated successfully"}`; `GET` then returns
   `{"smtpServer":"smtp.example.com","smtpPort":587,"smtpUser":"noreply@localhost","smtpUseTls":false}`
   with no password field. (The endpoint tests cover the same behaviour without Keycloak.)
9. `grep -rn "smtp_password\|encryption_key\|decrypt" api/app | grep -i "log"` finds no log
   call that prints a password, the key or a decrypted value.
10. `AGENTS.md` tells existing installs to copy `API_ENCRYPTION_KEY` from `api/.env.example`
    into `api/.env`, says the demo key is public and gives the key-generation command.

## Out of scope

- `POST /config/smtp/test`, the SMTP sender, `aiosmtplib` and smtp4dev (API-8).
- Clearing a saved field, deleting a user's settings, or any SMTP key beyond the five listed.
- Key rotation or re-encrypting stored values; a migration of existing data (the table is new).
- Changes to `compose.yaml`, `.devcontainer/` or the Makefile: the sandbox already reads
  `api/.env.example`, and the dev container copies it on create.
- Editing `api/.env` in the main checkout (the human does that, per the `AGENTS.md` note).
- Any change to `bff/`, `web/` or `specs/email-sender/` (the contract already describes these
  endpoints).
- Upgrading the shared dev database `emailsender` from the worktree.

## Assumptions

- `MessageSchema` lives in `app/schemas/base.py`: the contract lists it among the shared shapes
  and later items (API-8 onward) reuse it.
- The repository returns a frozen dataclass rather than a `dict[str, str]`: README §6 forbids
  bare dicts between layers.
- The upsert uses PostgreSQL `ON CONFLICT DO UPDATE` on `uq_user_config_key`: it is the
  smallest way to make concurrent first saves safe instead of a 500.
- A field set to `null` in the `PUT` body is skipped like an omitted field: the contract says
  `null` means "don't change" and a field can't be cleared.
- Validation messages for the update schema ("SMTP server cannot be empty" and so on) are my
  wording: the contract doesn't fix them, and the SPA shows Pydantic's `msg`.
- `smtpPassword` is not trimmed: spaces can be part of a real password.
- `hide_input_in_errors=True` applies to all API settings: none of them should be echoed on a
  startup error, and it hides the key.
- A stored password that no longer decrypts (the key changed) surfaces as `ValueError` from
  `get_smtp_config_for_sending`; how a send reports it is API-8's decision, and no endpoint here
  reads the password.
