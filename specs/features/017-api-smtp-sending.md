# API SMTP sending service, `POST /config/smtp/test` and smtp4dev in all run modes

> Feature: Add the SMTP sending service (aiosmtplib, correct TLS modes, 8 s timeout, mapped errors, a semaphore-bounded `send_many`), `POST /config/smtp/test`, and smtp4dev in all three run modes, as specified in `specs/email-sender/backend.md` API-8 (covers B6, B5 test endpoint, B12 smtp4dev part)

## Context

This is roadmap item API-8 of Phase 4 (Email Sender API). The source of truth is
`specs/email-sender/backend.md`, "API-8: SMTP sending service, test endpoint and smtp4dev"
(Requirements, Pitfalls, Acceptance criteria) plus that file's "Rules for every item". The wire
format is `specs/email-sender/api-contract.md` §2 (`SmtpTestRequestSchema` /
`SmtpTestResultSchema`), §3.5 (`POST /config/smtp/test`) and §5 (SMTP behaviour: TLS, timeout,
message, error messages). Background in `specs/email-sender/README.md`: §3.6 / D18 (8 s, because
the BFF's proxy timeout is 10 s), §3.7 / D19 (smtp4dev on 2525 and 5080; the sandbox publishes
only the web UI), §5 (layout: `app/services/smtp_sender.py`), §6 (a fake `EmailSender` in tests;
no test touches a real SMTP server apart from the opt-in online test), W-12 (`Message-ID` was
never set), W-13 (TLS semantics) and W-24 (`send_many` is the only place with send concurrency).
This spec restates the backend.md section; where they differ, this spec wins.

What API-7 (`specs/features/016-api-smtp-config.md`) left in `api/`:

- `app/services/smtp_config_service.py`: `SmtpConfigService.get_smtp_config_for_sending(user_sub)
  -> SmtpConfig | None` (None when no server is saved) and the frozen dataclass
  `SmtpConfig(smtp_server, smtp_port, smtp_user, smtp_password (repr=False), smtp_use_tls)` with
  the decrypted password, port default 587 and TLS default on. This is the type the sender takes.
- `app/api/config.py`: router `prefix="/config"` with `GET /smtp` and `PUT /smtp`, both taking
  `PrincipalDep` and `SmtpConfigServiceDep`.
- `app/schemas/smtp_config.py`: the settings schemas, all on `BaseSchema` (`app/schemas/base.py`,
  camelCase aliases); `MessageSchema` is in `app/schemas/base.py`.
- `app/errors.py`: `DomainError` subclasses, among them `BusinessRuleError`; `app/main.py` maps
  every non-`NotFoundError` `DomainError` to `400 {"detail": str(exc)}` in one handler.
- `app/dependencies.py`: frozen dataclass `Container(verifier, notes, sessions, encryption)` built
  by `build_container(settings, http, clock, sessions)`; per-request services built from
  `SessionDep` (for example `get_smtp_config_service`).
- `app/main.py`: `create_app(settings=None, *, http_client=None, clock=time.monotonic,
  session_factory=None)`; tests inject fakes through these keyword arguments.
- `tests/conftest.py`: the session-scoped `database_url` fixture (fails when PostgreSQL is down),
  per-test rolled-back `session_factory`, `FakeIssuer`, and the `app`, `client` and `bearer`
  fixtures. `tests/test_smtp_config_api.py` shows the endpoint-test style.
- `api/pyproject.toml`: no `aiosmtplib`, no pytest markers registered.

Run modes today (API-1, `specs/features/009-postgresql-run-modes.md`):

- Host: `keycloak/docker-compose.yml` has `keycloak` and `postgres` (published on
  `127.0.0.1:5432`); `make docker-up` / `docker-down` / `docker-logs` in the root `Makefile` run
  it, and their `##` help text names the services and ports.
- Sandbox: root `compose.yaml`; every service joins `keycloak`'s namespace
  (`network_mode: "service:keycloak"`) and `keycloak` publishes `127.0.0.1:8080` and
  `127.0.0.1:5173`. The header comment describes the services.
- Dev container: `.devcontainer/compose.yaml` (same namespace pattern, nothing published);
  `.devcontainer/devcontainer.json` and `.devcontainer/podman/devcontainer.json` forward 5173
  and 8080 with `portsAttributes` labels and are kept in sync; `.devcontainer/podman/compose.yaml`
  only overlays `keycloak` and `dev` and needs no change.
- `AGENTS.md` "Setup" ends with "or use a dev SMTP server (smtp4dev, coming with API-8)";
  "Run locally", "Sandbox" ("all five services") and "Dev container" describe PostgreSQL but no
  SMTP server. `README.md` lists the sandbox's services ("Keycloak, PostgreSQL, API, BFF and web").

## Requirements

1. `api/pyproject.toml` depends on `aiosmtplib>=5.1` (added with `uv add`, so `api/uv.lock` is
   updated), and registers the pytest marker `online` (`markers = ["online: ..."]` under
   `[tool.pytest.ini_options]`).
2. New `app/services/smtp_sender.py` with:
   - `SMTP_TIMEOUT_SECONDS = 8`;
   - frozen dataclass `SendResult(success: bool, smtp_message_id: str | None, error: str | None)`;
   - Protocol `EmailSender` with `async def send(self, to: str, subject: str, html_body: str) ->
     SendResult`;
   - `EmailSenderFactory = Callable[[SmtpConfig], EmailSender]`;
   - `SmtpEmailSender(config: SmtpConfig)` implementing `EmailSender` with `aiosmtplib`;
   - `async def send_many(sender, items, max_concurrent, on_result)`: each item carries what
     `send` needs (the builder picks a small typed item, for example a frozen dataclass with
     `to`, `subject`, `html_body`, generic enough for API-11 to subclass or wrap); it runs every
     send under one `asyncio.Semaphore(max_concurrent)`, awaits `on_result(item, result)` as each
     send finishes, and uses `asyncio.gather(..., return_exceptions=True)` so that an exception
     raised by one send becomes that item's failed `SendResult` (error `Unexpected error: …`)
     and does not stop the others. No other module adds send concurrency.
3. The message `SmtpEmailSender` builds: `MIMEMultipart("alternative")` with `From` =
   `smtp_user`, `To`, `Subject` as `email.header.Header(subject, "utf-8")`, `Date` from
   `email.utils.formatdate(localtime=True)`, `Message-ID` from `email.utils.make_msgid()`, and one
   `MIMEText(html_body, "html", "utf-8")` part. A successful result's `smtp_message_id` is that
   `Message-ID`.
4. The connection: `smtp_use_tls` and port 465 → `use_tls=True, start_tls=False`;
   `smtp_use_tls` and any other port → `use_tls=False, start_tls=True`; TLS off →
   `use_tls=False, start_tls=False` (never left at aiosmtplib's `start_tls=None`, which upgrades
   whenever the server offers STARTTLS). `timeout=SMTP_TIMEOUT_SECONDS` is passed to aiosmtplib.
   Login happens only when both `smtp_user` and `smtp_password` are set. The whole send (connect,
   login, send) runs inside `asyncio.timeout(SMTP_TIMEOUT_SECONDS)`. Check each argument name
   against the aiosmtplib 5.x API.
5. Errors become a failed `SendResult` (never raised from `send`), caught most specific first:
   `aiosmtplib.SMTPAuthenticationError` → `SMTP Authentication failed: <exc>`;
   `aiosmtplib.SMTPRecipientsRefused` → `Recipient refused: <exc>`; `aiosmtplib.SMTPException`
   → `SMTP error: <exc>`; `TimeoutError` → `SMTP error: timed out after <SMTP_TIMEOUT_SECONDS> s`
   (that is, "timed out after 8 s"); any other `Exception` → `Unexpected error: <exc>`. Each
   failure is logged at warning level with the recipient address and the error; passwords and
   message bodies are never logged.
6. Wiring: `Container` gains `email_sender_factory: EmailSenderFactory`; `create_app` gains the
   keyword argument `email_sender_factory: EmailSenderFactory | None = None` (default
   `SmtpEmailSender`), passed through `build_container`. `app/dependencies.py` exposes it as a
   dependency (for example `EmailSenderFactoryDep`), following the existing `Annotated[...,
   Depends(...)]` pattern.
7. Schemas in `app/schemas/smtp_config.py` on `BaseSchema`: `SmtpTestRequestSchema(recipient:
   EmailStr)` and `SmtpTestResultSchema(success: bool, message: str)`.
8. `POST /config/smtp/test` in `app/api/config.py`, taking `PrincipalDep`: loads
   `get_smtp_config_for_sending(principal.subject)`; None → raise `BusinessRuleError("SMTP
   configuration not found. Please configure SMTP settings first.")`; otherwise builds a sender
   with the factory and sends a short HTML message to `recipient` with the subject
   "Email Sender — test połączenia SMTP". Success → `200 {"success": true, "message": "Test email
   sent to {recipient}"}`; failure → `400 {"detail": <the mapped error>}` (raise
   `BusinessRuleError(result.error)`, so the one existing `DomainError` handler maps it). The
   orchestration may live in the router or in a small service method; either way no new HTTP
   mapping is added to `app/main.py`.
9. smtp4dev, image `docker.io/rnwood/smtp4dev:3.15.0`, no volume, environment
   `ServerOptions__Port=2525` and `ServerOptions__Urls=http://*:5080`, in:
   - `keycloak/docker-compose.yml`: service `smtp4dev` publishing `127.0.0.1:2525:2525` and
     `127.0.0.1:5080:5080`;
   - root `compose.yaml`: service `smtp4dev` with `network_mode: "service:keycloak"` and
     `depends_on: [keycloak]`; `keycloak` additionally publishes `127.0.0.1:5080:5080`; SMTP 2525
     is not published; the header comment mentions it;
   - `.devcontainer/compose.yaml`: service `smtp4dev` joining `keycloak`'s namespace the same
     way; the header comment mentions it; both `.devcontainer/devcontainer.json` and
     `.devcontainer/podman/devcontainer.json` add 5080 to `forwardPorts` and
     `"5080": { "label": "smtp4dev" }` to `portsAttributes`.
10. Tests (no real SMTP server in any test except the online one):
    - `tests/test_smtp_sender.py`: unit tests against a fake replacing `aiosmtplib.SMTP` (for
      example via `monkeypatch`) covering the MIME headers and HTML part, an emoji subject
      surviving `email.message_from_bytes` plus header decoding, no login without a password,
      the TLS arguments for port 465, port 587 and TLS off, each of the four exception classes
      and a timeout mapped to its message (the timeout test patches `SMTP_TIMEOUT_SECONDS` to a
      small value), and `send_many` with a success, a failure and a raising send giving three
      results through `on_result` while never exceeding `max_concurrent` concurrent sends.
    - `tests/test_smtp_test_api.py` (or added to `tests/test_smtp_config_api.py`): endpoint tests
      with a fake `EmailSenderFactory` passed to `create_app` (override the `app` fixture in the
      module as `conftest.py` allows): 200 with the message; no settings → 400 with the contract
      message; a failing fake → 400 with its error as `detail`; an invalid `recipient` → 422; no
      token → 401.
    - One online test marked `@pytest.mark.online` that sends through `SmtpEmailSender` to
      smtp4dev on `localhost:2525` (TLS off, user `noreply@localhost`, any password) and asserts
      success; it skips when a TCP connection to `localhost:2525` doesn't open within 1.5 s.
11. Docs:
    - `AGENTS.md`: replace "(smtp4dev, coming with API-8)" with a pointer to the smtp4dev values;
      in "Run locally" say the Keycloak compose file also starts smtp4dev (SMTP on
      127.0.0.1:2525, inbox at http://localhost:5080) and that anything else on 2525 or 5080
      clashes with it; give the values to enter in "Ustawienia": server `localhost`, port `2525`,
      TLS off, user `noreply@localhost` (also the `From` address), any password (smtp4dev accepts
      any credentials); in "Sandbox" add smtp4dev (six services; inbox on 5080, SMTP reachable
      inside the shared namespace only); in "Dev container" add smtp4dev on `localhost:2525`
      inside and 5080 forwarded; in "Validation" note the `online` test (skips without smtp4dev;
      `uv run pytest -m "not online"` leaves it out).
    - Root `Makefile`: the `docker-up` / `docker-down` / `docker-logs` help text names smtp4dev
      (ports 2525 and 5080).
    - `README.md`: the sandbox service list includes smtp4dev.
    - `specs/email-sender/api-contract.md` only if the implementation differs from §2, §3.5 or
      §5 (it should not).

## Acceptance criteria

1. `cd api && uv run pytest`, `uv run ruff check .` and `uv run mypy app tests` pass with
   PostgreSQL running and smtp4dev not running (the online test is reported as skipped).
2. With `make docker-up` running (smtp4dev up), `cd api && uv run pytest -m online -rs` runs the
   online test and it passes, and `curl -s http://localhost:5080/api/messages` (or the inbox page
   at http://localhost:5080) shows the email it sent.
3. `cd api && uv run pytest tests/test_smtp_sender.py -v` lists passing tests for: the MIME
   headers (`From`, `To`, `Subject`, `Date`, `Message-ID`, HTML part), the emoji subject round
   trip, no login without a password, TLS arguments for 465 / 587 / off, the four error classes
   and the timeout message, and `send_many` (three results, concurrency cap respected).
4. The endpoint tests pass and cover: `POST /config/smtp/test` → 200 `{"success": true,
   "message": "Test email sent to <recipient>"}`; no saved server → 400 `{"detail": "SMTP
   configuration not found. Please configure SMTP settings first."}`; a failing sender → 400 with
   the mapped error; bad `recipient` → 422; no token → 401.
5. `grep -n "aiosmtplib" api/pyproject.toml api/uv.lock` finds the dependency, and
   `grep -n "online" api/pyproject.toml` finds the registered marker; `uv run pytest` prints no
   `PytestUnknownMarkWarning`.
6. `app/services/smtp_sender.py` passes `start_tls=False` when TLS is off and contains
   `asyncio.Semaphore` and `return_exceptions=True`; `grep -rn "Semaphore" api/app` finds it in
   that file only.
7. `make docker-up` then http://localhost:5080 shows the smtp4dev web UI, and
   `podman ps` (or `docker ps`) shows smtp4dev's ports bound to `127.0.0.1:2525` and
   `127.0.0.1:5080`.
8. `make sandbox-up` then http://localhost:5080 shows the smtp4dev web UI;
   `podman compose config` (root) shows `smtp4dev` with `network_mode: service:keycloak`,
   `keycloak` publishing `127.0.0.1:5080`, and no published 2525.
9. `.devcontainer/compose.yaml` has the `smtp4dev` service in `keycloak`'s namespace, and both
   `devcontainer.json` files list 5080 in `forwardPorts` with the label `smtp4dev`
   (`grep -n 5080 .devcontainer/devcontainer.json .devcontainer/podman/devcontainer.json`).
10. `grep -n "smtp4dev" AGENTS.md README.md Makefile` finds the entries from Requirement 11, and
    `AGENTS.md` lists the "Ustawienia" values (`localhost`, `2525`, TLS off,
    `noreply@localhost`, any password) and no longer says "coming with API-8".
11. `bff/` is unchanged (`git diff --stat main -- bff` is empty) and `cd web && npm run build`
    still passes.

## Out of scope

- Any web change (the "Ustawienia" screen with the test button is UI-8).
- Campaigns, the email log, background sending and resends (API-9 to API-13); `send_many` is
  built and tested here but not called by any endpoint yet.
- Retries, connection pooling or reuse across sends, plain-text alternative parts, attachments,
  a configurable `From` name or address, or a configurable timeout or concurrency setting.
- Changing the existing `keycloak` port binding `8080:8080` in `keycloak/docker-compose.yml` or
  any other existing service.
- Persisting smtp4dev mail (no volume) or adding smtp4dev to the API's startup dependencies.
- New Alembic revisions: API-8 adds no tables.

## Assumptions

- The `online` test runs in the default `uv run pytest` and skips when smtp4dev is not
  listening, rather than being deselected by default: acceptance criterion 4 of backend.md says
  it "passes with `make docker-up` running", and skipping keeps the default run off any server.
- When `smtp_user` is not saved, no `From` header is set and aiosmtplib's failure surfaces as the
  mapped `Unexpected error: …` (or `SMTP error: …`), with no special-case code: backend.md says
  `From` is the SMTP user and a bad login is "the user's setting, not a bug to work around".
- The timeout message is formatted from `SMTP_TIMEOUT_SECONDS`, so the patched-timeout test
  asserts against the patched value and a separate assertion pins the constant at 8: backend.md
  requires both the "8 s" text and a short timeout in the test.
- An exception that escapes a send inside `send_many` is mapped to `Unexpected error: <exc>`:
  §5 of the contract lists that as the catch-all message.
- smtp4dev in the sandbox and the dev container starts with `depends_on: [keycloak]` only, and
  nothing depends on it: the API only connects to SMTP when a user sends.
- The `docker.io/rnwood/smtp4dev:3.15.0` tag is taken from backend.md as given; if it does not
  exist the builder uses the newest pinned 3.x release tag and notes it, since D19 only requires
  a pinned, non-`prerelease` tag.

## Changes

wlacz tls

Clarified by the user: block login without TLS. When TLS is off and an SMTP password is saved, the API must refuse to log in and send the password in clear text, and answer with a mapped error (a 400 from `POST /config/smtp/test`) instead. Sending without a login (no password saved) still works over a connection without TLS, so smtp4dev keeps working in all three run modes.
