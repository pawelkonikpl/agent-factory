# Email Sender

The Email Sender is the demo app built on the BFF: a bulk email campaign tool. Signed-in users
keep clients in categories, build campaigns in a 4-step wizard, send them in the background
through their own SMTP server, and read an email log with stats.

These files specify it for this repo. They are translated from Polish rebuild notes, written on
2026-10-14 by reviewing an older Email Sender codebase that this repo doesn't contain, and
adapted to the existing `api/`, `web/` and BFF. The notes themselves are not in the repo.

| File | Contents |
|---|---|
| `README.md` (this file) | product, data model, scope, how the app fits this repo, stack, architecture, conventions, configuration, run modes, security notes, defects of the old version, decisions, deferred work, source task mapping |
| `api-contract.md` | the HTTP contract: enums, schemas, endpoints, the send rules, errors |
| `backend.md` | one section per API roadmap item, `API-1` to `API-14` |
| `frontend.md` | one section per UI roadmap item, `UI-1` to `UI-13` |
| `roadmap.md` | Phase 4 and Phase 5, to paste into `factory/backlog.md` after Phase 3 |

Tags in the item sections and the contract:

- **[PARITY]**: behave like the old version.
- **[FIX]**: the old version has a bug or inconsistency here; do it right (see §10).
- **[NEW]**: the UI needs it or promises it, and the old backend didn't have it.
- **[ADAPT]**: changed to fit this repo (see §3 and the decisions from D11 on).

The source's optional **[OPT]** work is listed in §12, Deferred.

## 1. How to work on an item

Each line of `roadmap.md` is one factory job. `/factory next` takes the next line; the
spec-writer reads the line, this README, `api-contract.md` and the item's section in
`backend.md` or `frontend.md`. An item's requirements are the minimum, its acceptance
criteria are its test plan, and it ends with every validation command in `AGENTS.md` green.
Items only depend on earlier items. Each one adds its own tests, its own migration, and its own
API functions, zod schemas and hooks, instead of building one big layer up front.

When an item changes the contract, it updates `api-contract.md` in the same job.

## 2. Product and scope

**Email Sender** ("Marketing Platform"), bulk email campaigns for one operator or team:

1. Each user configures their own SMTP server (the "Ustawienia" screen).
2. Users keep a base of **clients** (recipients) grouped in **categories** (many-to-many).
3. They create **campaigns** (name, subject, HTML content, recipient list, optional scheduled
   date) in a 4-step wizard.
4. They **send** a campaign through their SMTP server. Sending runs in the background, the
   campaign shows its progress, each recipient gets a status, and every attempt lands in the
   **email log**.
5. A campaign ends as `sent` (everyone got it) or `failed` (someone didn't). A failed campaign
   can be **resent**, to all failed recipients or to chosen ones.
6. The email log per campaign, its stats, and resending a single email.

UI language: Polish (D1). API, code, commits, tests and these docs: English. Theme: light and
dark (dark by default), "Modern SaaS 2026" style, the Inter font.

### Data model

Summary; the full columns are in `backend.md` (API-4, API-5, API-7, API-9, API-10).

```
configs     SMTP key/value rows per user: user_sub = the Keycloak "sub"; the password is Fernet-encrypted
clients     N───M  categories           (table client_category)
campaigns   1───N  campaign_recipients  N───1 clients
campaigns   1───N  emails (the log)     N───1 clients
```

Soft delete (`is_deleted`, `deleted_at`) on `clients`, `categories`, `campaigns`,
`campaign_recipients` and `emails`. Domain data is global: it has no owner column, so every
signed-in user (for example `alice` and `bob`) sees the same clients, categories, campaigns and
log. Only the SMTP settings are per user (D5). A campaign goes out through the SMTP settings of
the user who presses send.

### Scope

In scope: clients, categories, campaigns (CRUD, recipients, background send, resend, clone in
the UI), the email log with its stats and single-email resend, per-user SMTP settings with a
test email, the demo seed, PostgreSQL and smtp4dev in all three run modes, bun for `web/`, and
tests.

Out of scope:

- Auth, which the BFF and Keycloak own (D12): registration, sign-in and sign-out, email
  verification, password reset, `/auth/*` endpoints, the `User` model and password hashing, JWT
  handling, the login rate limiter, the admin seed and the auth email templates, and the
  source's auth screens.
- The old version's dead code (W-11, W-21).
- CI, image publishing and production deployment (D21; mission non-goals).
- The source's optional work, listed in §12.

## 3. How it fits this repo

### 3.1 Location and auth (D11, D12)

The Email Sender is built into the existing `api/` (resource server) and `web/` (SPA), behind
the BFF. There is no `backend/` or `frontend/` folder. The source's separate "auth project" is
the BFF plus Keycloak, which already exist.

- **API.** The current user is the existing `PrincipalDep` (`api/app/dependencies.py`). Its
  `Principal.subject`, the Keycloak `sub` (a string; demo users have generated UUIDs), replaces
  the source's `current_user.id`. There is no `users` table. `configs` has `user_sub`
  `String(255)` NOT NULL, indexed, with `UniqueConstraint(user_sub, config_key)` and no foreign
  key. Every Email Sender endpoint requires the principal; a missing or invalid token gives
  401 from the existing handler in `api/app/main.py`.
- **Web.** Requests go through `bffRequest` (`web/src/services/bff-client.ts`): same-origin
  cookie plus the `X-CSRF` header. There is no token store, no token refresh, no
  `Authorization` header and no `/login` route. A 401 invalidates the session query, so the
  existing login screen comes back. The NavBar's user section shows `name` and `email` from
  `GET /bff/session` (the avatar initial comes from `name`), "Wyloguj" uses the existing
  logout, and "Profil" is hidden.

### 3.2 Paths and list totals (D13)

- The API serves `/categories/`, `/clients/`, `/campaigns/`, `/emails/` and `/config/smtp` at
  its root. The SPA calls them as `/api/categories/` and so on; the BFF proxy forwards
  `/api/<path>` to `BFF_API_BASE_URL` + `/<path>` with the session's access token.
- Every paginated list (`GET /clients/`, `GET /campaigns/`, `GET /emails/`) answers
  `200 { "items": [...], "total": N }`, where `total` counts the rows after filters and before
  `skip`/`limit`.
- **The BFF does not change for the Email Sender.** That includes `FORWARDED_RESPONSE_HEADERS`
  in `bff/app/services/api_proxy.py` (`content-type`, `cache-control`, `etag`,
  `last-modified`): totals travel in the body, so no new response header has to pass the proxy.

### 3.3 PostgreSQL (D14, D15)

- PostgreSQL runs in all three run modes (host, sandbox, dev container) as a `postgres` service
  with demo credentials in git: database, user and password `emailsender` (API-1).
- The API uses SQLAlchemy 2 async with asyncpg and Alembic; `alembic upgrade head` runs at
  startup (API-2). Each later API item adds its own tables in its own migration.
- Timestamps are `DateTime(timezone=True)` (W-22). Unique client emails and category names use
  partial unique indexes `WHERE is_deleted = false` (W-02).
- Tests use a separate database from `API_TEST_DATABASE_URL` (default: the same server,
  database `emailsender_test`, created by the test fixture when missing). The URL must contain
  `test`, else `RuntimeError`. Each test runs in an outer transaction with savepoints (W-25).
  From API-2 on, `uv run pytest` in `api/` needs PostgreSQL running and fails with a clear
  message when it is not reachable.

### 3.4 bun (D16)

`web/` replaces npm with bun in every run mode (UI-1): one lockfile, `bun.lock`; a pinned bun
image for the sandbox; a pinned bun in the dev container image; `bun run` in the Makefile;
bun commands in `AGENTS.md`. Validation in `web/` becomes `bun run build`, and from UI-2 on also
`bun run test` (Vitest).

### 3.5 Background sending (D17)

`POST /campaigns/{id}/send` and `POST /campaigns/{id}/resend` check the request, move the
campaign to the new `sending` status with one atomic update, start the sending as a background
task and answer `202` with the campaign. The task sends with a semaphore and commits each
recipient's result as it finishes. The SPA polls `GET /campaigns/{id}` while the status is
`sending` and shows the result when it ends. The rules are in `api-contract.md` §4.

### 3.6 Timeouts (D18)

The BFF limits every proxied call to 10 s (`http_timeout_seconds` in `bff/app/config.py`). The
two calls that still talk to SMTP inside a request, `POST /config/smtp/test` and
`POST /emails/{id}/resend`, send one email with an 8 s SMTP timeout, so they answer in time.

### 3.7 Dev SMTP (D19)

smtp4dev runs next to PostgreSQL in all three run modes (API-8): SMTP on port 2525 and its web
UI on port 5080. To send real test mail, enter in "Ustawienia": server `localhost`, port `2525`,
TLS off, user `noreply@localhost` (also the `From` address) and any password (smtp4dev accepts
any credentials). Mail shows up at http://localhost:5080.

### 3.8 Other adaptations (D20, D21)

- **API:** follow the existing `api/` layout and wiring (§5), not the source's
  module-per-feature tree. Settings use the `API_` prefix (§7). The validation commands are the
  existing three in `AGENTS.md`. The image stays `api/Containerfile`.
- **Web:** zod schemas in `web/src/services/` (the `bffRequest` pattern) replace generated
  OpenAPI types. Kebab-case file names. No axios, no ESLint and no husky.
- No CI workflows, no image push, no new Containerfiles and no `docs/` trees.

### 3.9 Seed (D22)

Demo clients and campaigns are seeded at startup only when `API_SEED_DEMO_DATA` is true;
`api/.env.example` sets it to true (API-14). There is no SMTP seed.

### 3.10 The notes demo stays (D23)

The notes panel and the token check move to their own route, `/notes`, under the NavBar's
"Inne" section (UI-4). `/notes` in the API is unchanged.

## 4. Stack

**API** (`api/`, existing: Python ≥ 3.11 with 3.12 images, FastAPI, uvicorn, Pydantic 2,
pydantic-settings, PyJWT, httpx, pytest + pytest-asyncio, ruff, mypy strict, uv). Added by the
items: SQLAlchemy 2 (`sqlalchemy[asyncio]`, `Mapped[]`/`mapped_column` style) and asyncpg
(API-2), Alembic (API-2), `email-validator` through `pydantic[email]` (API-5), `cryptography`
for Fernet, declared directly although PyJWT already pulls it in (API-7), `aiosmtplib >= 5.1`
(API-8).

**Web** (`web/`, existing: React 19, TypeScript strict with `verbatimModuleSyntax` and
`noUncheckedIndexedAccess`, Vite 8, TanStack Query 5, zod 4). Added by the items: bun (UI-1);
Vitest, jsdom and Testing Library (UI-2); MUI (`@mui/material`, `@mui/icons-material`, Emotion)
and `@fontsource-variable/inter` (UI-3); `react-router` and `react-error-boundary` (UI-4);
`react-hook-form` (UI-6); `date-fns` with the `pl` locale (UI-9); DOMPurify (UI-11). Use the
current major of each and check the APIs these files name against it: the source targeted
MUI 7 and react-router-dom 7, and newer majors exist.

## 5. Architecture

### API: the existing layering

`router → service → repository → models`, wired like the notes demo.

```
api/
├── alembic.ini, migrations/            env.py, script.py.mako, versions/          (API-2)
├── app/
│   ├── main.py            create_app: lifespan (migrations, recovery, seed), routers, error handlers
│   ├── config.py          Settings (API_ prefix)
│   ├── dependencies.py    Container, build_container, Annotated dependency aliases (SessionDep, ...)
│   ├── errors.py          token errors (existing) + domain errors (API-3)
│   ├── database.py        engine, session factory, run_migrations                   (API-2)
│   ├── models/            base.py (Base, naming convention, mixins), category.py, client.py,
│   │                      config.py, campaign.py, email.py
│   ├── schemas/           base.py (BaseSchema, Page), notes.py, categories.py, clients.py,
│   │                      smtp_config.py, campaigns.py, emails.py                  (API-3 on)
│   ├── api/               notes.py, categories.py, clients.py, config.py, campaigns.py, emails.py
│   ├── services/          <area>_service.py, encryption.py, smtp_sender.py,
│   │                      campaign_sender.py, email_content.py, seed.py
│   └── repositories/      <area>_repository.py
└── tests/                 conftest.py + test_<area>_*.py
```

Layer rules: a router only does HTTP (parsing, status codes); a service owns the business
rules and status transitions and raises typed domain errors; a repository owns the SQLAlchemy
queries. Shared pieces live in `app/schemas/base.py`, `app/errors.py` and `app/database.py`.
No import cycles between areas.

The `Container` in `app/dependencies.py` holds the long-lived pieces: the token verifier, the
session factory (API-2), the encryption service (API-7) and the email sender factory (API-8).
Per-request services are built by dependency functions from a per-request `AsyncSession`.
`create_app` takes the session factory and the sender factory as optional arguments, as it
takes `http_client` today, so tests inject theirs.

### Web

```
web/src/
├── main.tsx, app.tsx, query-client.ts, styles.css (login and notes only)
├── theme/        tokens.ts, theme.ts, theme-mode-context.tsx, global-styles.tsx    (UI-3)
├── services/     bff-client.ts, page.ts, session-api.ts, notes-api.ts, categories-api.ts,
│                 clients-api.ts, smtp-config-api.ts, campaigns-api.ts, emails-api.ts
├── hooks/        use-session.ts, use-notes.ts, use-debounce.ts, use-categories.ts, use-clients.ts,
│                 use-smtp-config.ts, use-campaigns.ts, use-emails.ts
├── utils/        error-message.ts, plural.ts
├── components/   ui/ (shared), layout/ (nav bar, app layout, error boundary), categories/,
│                 clients/, settings/, campaigns/ (list, send, wizard and its steps), emails/,
│                 plus the existing login-screen.tsx, notes-panel.tsx and token-check.tsx
└── test/         setup.ts, utils.tsx, mocks.ts                                       (UI-2 on)
```

## 6. Conventions

**API**

- Every Email Sender request and response schema inherits `BaseSchema`: camelCase on the wire,
  snake_case also accepted on input. The notes schemas don't; their snake_case wire format
  stays.
- No bare dicts between layers: Pydantic models or dataclasses (`model_dump()`,
  `model_validate()`).
- Validation in three layers: syntax (Pydantic, 422), business rules (services, typed domain
  errors, 400 or 404), technical (repositories and integrations, for example a unique index
  violation mapped to `ConflictError`).
- `emails` is a historical log: `recipient_email`, `subject` and `body` are snapshots from the
  moment of sending.
- Soft delete wherever `is_deleted` exists; every query filters `is_deleted = false`.
- Every Email Sender endpoint takes `PrincipalDep`.
- Async all the way: `AsyncSession`, never a sync database call in an endpoint. Relationships
  load with `lazy="selectin"` or an explicit `selectinload`, never lazily in async code.
- Tests: pure logic without database or HTTP; services and endpoints against
  `emailsender_test` with per-test rollback; endpoints through `httpx.AsyncClient` with
  `ASGITransport` and tokens from the existing `FakeIssuer` in `api/tests/conftest.py`; a fake
  `EmailSender` instead of SMTP. No test touches the app database or a real SMTP server, apart
  from the opt-in online test in API-8.

**Web**

- Strict TypeScript, no `any`. Data only through `services/*-api.ts` (zod plus `bffRequest`)
  and hooks; components never call `bffRequest` themselves.
- Server state in TanStack Query, forms in react-hook-form. Every async view has loading,
  error and empty states.
- Kebab-case file names and named exports, as in `web/src` today. IDs are numbers.
- Styling from the theme tokens: radii 12 to 16 px, primary gradient `#6366f1 → #8b5cf6`, no
  hex colours in components.
- Components stay under about 250 lines (the old ones reached 525); split them.
- Accessibility in every screen (F12): `aria-label` on icon buttons, focus moves into dialogs
  and back, the wizard works from the keyboard, text contrast passes WCAG AA in both themes.
- Tests with Vitest and Testing Library next to the code (`*.test.tsx`), with `fetch` stubbed:
  no network and no `act()` warnings.

## 7. Configuration

API settings, read by `api/app/config.py` with the `API_` prefix:

| Variable | Default | Added by | Purpose |
|---|---|---|---|
| `API_ISSUER`, `API_AUDIENCE` | existing | | token verification, unchanged |
| `API_DATABASE_URL` | `postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender` | API-1 (`.env.example`), API-2 (setting) | the app database |
| `API_TEST_DATABASE_URL` | the app URL with the database `emailsender_test` | API-2 | the test database; must contain `test` |
| `API_ENCRYPTION_KEY` | none, required | API-7 | Fernet key for SMTP passwords; `.env.example` holds a demo key |
| `API_EMAIL_MAX_CONCURRENT` | `10` | API-11 | default `max_concurrent`, 1 to 50 |
| `API_SEED_DEMO_DATA` | `false` (`.env.example`: `true`) | API-14 | seed demo clients and campaigns at startup |

`api/.env` is a copy of `api/.env.example` and doesn't pick up new lines by itself. An item
that adds a required variable says in `AGENTS.md` to copy the new line.

Dropped source variables: `API_V1_STR`, `PROJECT_NAME`, `BACKEND_CORS_ORIGINS` (no prefix, no
CORS), `SMTP_*`, `EMAIL_ENABLED`, `EMAIL_TEST_MODE`, `SMTP_FROM_NAME` (unused, W-11),
`FRONTEND_URL` and the auth secrets (the BFF owns auth), and every `VITE_*` variable: the SPA
is same-origin, holds no tokens, and the Vite proxy target stays in `web/vite.config.ts`.

## 8. Run modes

| Service | Host (`keycloak/docker-compose.yml`) | Sandbox (`compose.yaml`) | Dev container (`.devcontainer/compose.yaml`) |
|---|---|---|---|
| `postgres` (API-1) | published on `127.0.0.1:5432` | joins `keycloak`'s network namespace, not published; `api` waits until it is healthy | joins `keycloak`'s namespace, so `localhost:5432` inside `dev` is PostgreSQL; not published; `dev` waits until it is healthy |
| `smtp4dev` (API-8) | SMTP on `127.0.0.1:2525`, web UI on `127.0.0.1:5080` | joins the namespace; `keycloak` publishes `127.0.0.1:5080` for the web UI; SMTP stays internal | joins the namespace; the Dev Containers client forwards 5080 |

Neither service has a volume: like Keycloak's in-memory database, data is gone after
`down`, and the seed recreates the demo data. Port 5432 (and later 2525 and 5080) clashes with
anything else on the host using it, such as a host PostgreSQL.

## 9. Security notes

- The API holds SMTP passwords encrypted with Fernet and never returns them. The demo key in
  `api/.env.example` is a demo secret, allowed in git like the other dev-only secrets.
- The API connects to whatever SMTP host and port a signed-in user saves, and the test
  endpoint does so on demand. That is the product (each user's own server), and the stack is
  dev-only and bound to 127.0.0.1; a production version would restrict the targets.
- Campaign content is HTML written by users. The SPA renders it only sanitized (DOMPurify,
  UI-11) and the API HTML-escapes the values it substitutes (API-11).
- Logs carry recipient addresses and error messages, never passwords or email bodies.

## 10. Defects of the old version (do not repeat)

Severity: **High** = bug, data loss or security; **Medium** = a feature doesn't work or
misleads; **Low** = quality.

| ID | Severity | Description | Fixed in |
|---|---|---|---|
| W-01 | High | Editing a client in the UI sent `PUT` without `additionalEmails`, `address` and `notes`; the backend treats `PUT` as a full replacement and **cleared those fields**. The form didn't show them either. | UI-7 (fields in the form, full payload) + API-5 (documented full replacement) |
| W-02 | High | `clients.primary_email` and `categories.name` had a **global unique constraint**, while the service checked only non-deleted rows: after a soft delete, the same email or name could not be created again (IntegrityError, 500). | API-4, API-5 (partial unique indexes `WHERE is_deleted = false`) |
| W-03 | High | The "review" step rendered HTML with `dangerouslySetInnerHTML` without sanitizing it (XSS). | UI-11 (DOMPurify) |
| W-04 | High | The categories router had no auth dependency: its endpoints were public. | API-4 (`PrincipalDep` on every endpoint) |
| W-05 | Medium | The wizard promised the variables `{name}`, `{email}` and `{company}`, but the backend sent the content without substituting them. | API-11 (D3) |
| W-06 | Medium | The content field is a plain textarea, but mail goes out as HTML, so line breaks vanish in the mail client. No `text/plain` part. | API-11 (D4: `\n` to `<br>` for plain text) + UI-11 (preview); the `text/plain` part is deferred |
| W-07 | Medium | The frontend called `POST /clients/bulk` and `POST /config/smtp/test`, which **the backend didn't have**. | API-6, API-8 |
| W-08 | Medium | The frontend sent `search` to `/clients/` and `/emails/`, and the backend ignored it (only `/campaigns/` filtered). Client search worked only in the browser, on the first 100 rows. | API-5, API-10 |
| W-09 | Medium | No `total`: the UI fetched again with `limit=1000` just to count rows (wrong above 1000). `useEmailStats` fetched up to 10 000 emails and computed stats in the browser although `/emails/stats/` existed, and counted a `delivered` status the backend doesn't have. | API-3 (`Page` with `total`, replacing the source's X-Total-Count header), API-5, API-9, API-10, UI-5, UI-13 |
| W-10 | Medium | `ENCRYPTION_KEY` was required by the settings but missing from `.env.example` and `compose.yaml`, so the backend didn't start on a fresh install. | API-7 (`API_ENCRYPTION_KEY` in `api/.env.example`) |
| W-11 | Low | Dead code: `utils/email.py` (refers to undefined `smtp_config`/`user_id`), the env variables `EMAIL_ENABLED`, `EMAIL_TEST_MODE`, `SMTP_FROM_NAME`, the `SMTP_*` defaults, `LoginRateLimiter` and so on. | do not port |
| W-12 | Medium | `smtp_message_id` was always `null`: the code read `message.get("Message-ID")` but never set it. | API-8 (`email.utils.make_msgid`) |
| W-13 | Medium | "Use TLS" semantics: `aiosmtplib` `use_tls=True` is implicit TLS (port 465). The default `smtpUseTls = true` with port 587 (the UI placeholder) failed to connect. | API-8 (465: implicit TLS, otherwise STARTTLS, off: plain) + UI-8 (switch description) |
| W-14 | Medium | Sending ignored `client.is_active` and sent to inactive clients. | API-11 |
| W-15 | Medium | The UI showed "Otwarte"/"Kliknięcia", but nothing set `opened_at`/`clicked_at`/`delivered_at` apart from the manual `POST /emails/{id}/mark-*`; delivery, open and click stats were always 0. | UI-13 hides them (D8); tracking is deferred |
| W-16 | Medium | The edit button showed for `failed`/`scheduled`, while the backend lets only `draft` be edited (400). `scheduled` and `scheduledFor` were stored, but **nothing sent them** (no scheduler). | API-9 (draft-only PUT, documented), UI-9 and UI-12 (edit only for `draft`); the scheduler is deferred (D6) |
| W-17 | Low | An `Email` row was created on every attempt (a campaign resend added rows instead of updating them), `retry_count`/`max_retries` were never used, and the email DTO's `subject`/`content` came from the *current* campaign, not a snapshot. | API-10 (snapshot columns, D25), API-11 (update the row on retry, `retry_count`, `max_retries`) |
| W-18 | Low | Three lockfiles (`bun.lock`, package-lock.json, `pnpm-lock.yaml`), Dockerfile on pnpm, CI on bun, the README on npm. | UI-1 (bun only: `bun.lock` replaces package-lock.json) |
| W-19 | Low | Generated types were **stale** against the backend, and hand-written duplicates sat next to them. | UI-5 and each screen item: hand-written zod schemas that also validate at runtime (D20) |
| W-20 | Low | Dead NavBar links (`/clients/import`, `/help`); `/emails` had no menu entry and was reachable only through a campaign name. | UI-4 (each screen item adds its own NavBar entry, no dead links), UI-13 |
| W-21 | Low | Dead frontend components (`CampaignFormModal`, `CampaignForm`, `RecipientSelector`, `ClientsHeader`, `SearchBar`, `useClientSearch`, `ErrorNotificationTest`, `src/types/legacy/*`); the docs mentioned `@dnd-kit` and `xlsx`, which were not dependencies. | do not port |
| W-22 | Low | Dates: `created_at`/`updated_at` were `DateTime(timezone=True)` filled with naive `datetime.utcnow`, while `sent_at`, `scheduled_for`, `delivered_at` and the like had no timezone. | API-2 (every date column `DateTime(timezone=True)`, defaults `datetime.now(UTC)`) |
| W-23 | Low | 400/404 responses came from matching exception text (`"not found" in str(e)`). | API-3 (typed domain errors, one handler) |
| W-24 | Low | `send` ran the whole send synchronously inside the HTTP request, used a synchronous SQLAlchemy session in `async` endpoints (blocking the loop), and had no server-side guard against a double click. | API-2 (async sessions), API-11 (background task, atomic status change) |
| W-25 | Low | Test isolation was fake: repositories committed, and the "rollback" fixture undid nothing, so tests needed unique emails from `hash(nodeid)`. The API was barely tested. | API-2 (outer transaction plus savepoints), endpoint tests in every item |
| W-26 | Low | No check that related IDs exist: unknown `categoryIds` on a client were silently skipped, unknown `recipientIds` on a campaign ended in an FK error (500), and duplicate `recipientIds` created duplicate recipients. | API-5, API-9 |
| W-27 | Low | The seed logged the admin password. Auth is out of scope, but don't port the pattern. | API-14 (logs counts only) |
| W-28 | Low | The old docs had stale paths and a contradicting rule ("all UI texts in English" next to a Polish UI). | these files (current paths; D1) |

## 11. Decisions

D1 to D10 are the source's open decisions with their resolution here. D11 on are the
adaptations to this repo.

| ID | Question | Decision |
|---|---|---|
| D1 | UI language. | **Polish** (parity, and the repo's rule). Copy lives as constants in each screen's module; no i18n library. Backend `detail` and `message` texts are English and are shown as they come, as in the old app. |
| D2 | List totals. | Replaced by D13: totals in the response body. |
| D3 | `{name}` / `{email}` / `{company}` in the content. | Implement (API-11): `{company}` = `companyName`, `{name}` = `companyName` (a client has no person field), `{email}` = `primaryEmail`. Unknown keys stay as they are. Values are HTML-escaped. |
| D4 | Content format. | HTML. The editor is a multiline field with a preview. Content without HTML tags is HTML-escaped and gets `\n` → `<br>` on the server (API-11). The SPA sanitizes the preview (UI-11). |
| D5 | Global or per-user domain data. | Global (parity); only `configs` is per user. |
| D6 | Scheduled campaigns (`scheduled`). | Store `scheduledFor` only; nothing sends it later and nothing sets the `scheduled` status. The scheduler (B13) is deferred. The wizard says so: the date's helper text and the review step don't promise a scheduled send (UI-11). |
| D7 | Client import from Excel. | Deferred (F11). `POST /clients/bulk` is still built, as its own item (API-6). |
| D8 | Open and click tracking. | Deferred (B14). The UI hides "Otwarte", "Kliknięcia" and the activity column. |
| D9 | A `/help` page. | No link and no page. |
| D10 | Send concurrency. | Query parameter `max_concurrent` (query parameters are snake_case), default `API_EMAIL_MAX_CONCURRENT` (10), validated 1 to 50. |
| D11 | Where the app lives. | In the existing `api/` and `web/`, behind the BFF, following the existing layering (§5). |
| D12 | Auth seam. | BFF plus Keycloak. API: `PrincipalDep`, `Principal.subject` instead of `current_user.id`, no `users` table, `configs.user_sub` without a foreign key (the source's FK to users.id is dropped), no `get_current_user` stub, no CORS. Web: `bffRequest`; the source's `tokenStore`, `POST /auth/refresh` refresh, `Authorization` header and `/login` route are dropped; a 401 shows the existing login screen. |
| D13 | Paths and totals. | The `/api/v1` prefix is dropped; the API serves at its root and the SPA calls `/api/...` through the BFF. Paginated lists answer `{ "items": [...], "total": N }`; the source's X-Total-Count header and CORS `expose_headers` are dropped. The BFF doesn't change. |
| D14 | Database. | PostgreSQL in every run mode and for tests, replacing the source's SQLite (no aiosqlite). asyncpg replaces psycopg2-binary. Tests use `emailsender_test` on the dev server and fail, not skip, when it is down; no testcontainers, since the dev container has no container engine. |
| D15 | ORM style and migrations. | SQLAlchemy 2 async, replacing the source's synchronous `Session` (W-24). Each API item adds its own tables in its own Alembic revision; there is no single initial migration with every table. |
| D16 | Web package manager. | bun, with one lockfile `bun.lock` (it replaces package-lock.json; no npm commands remain). Validation: `bun run build`, and `bun run test` from UI-2 on. Node stays in the dev container for tools that need it. |
| D17 | Campaign send. | In the background (§3.5), replacing the synchronous send; `SendCampaignResultSchema` is dropped. New status `sending`. A `sending` campaign can't be sent, resent, edited or deleted. The task is in-process (FastAPI `BackgroundTasks`), not a queue; a startup sweep fails campaigns a restart left in `sending`. Single-email resend stays synchronous. Progress is the campaign's existing `stats`. |
| D18 | Timeouts. | 8 s per SMTP email; the source's 30 s test timeout is dropped (the BFF allows 10 s). |
| D19 | Dev SMTP server. | smtp4dev on a pinned tag (not `prerelease`) in all three run modes. In the sandbox `keycloak` also publishes the web UI port 5080, so the inbox is visible from the host like in the other two modes; SMTP stays internal there. |
| D20 | Web types and HTTP. | zod schemas in `web/src/services/` replace OpenAPI-generated types (no `openapi-typescript`, `types:generate` or `types:check`); `bffRequest` replaces axios. No ESLint and no husky; type checking stays in `bun run build`. |
| D21 | Infrastructure. | No GitHub Actions workflows, no image build or push targets, no new Containerfiles, no `docs/` trees: all dropped (production deployment and CI are non-goals). Existing Containerfiles change only where an item says so. |
| D22 | Seed. | Only when `API_SEED_DEMO_DATA` is true (`api/.env.example`: true). The source's SMTP seed for one user is dropped: Keycloak subs are generated at realm import, so no user can be seeded ahead of time; `AGENTS.md` gives the smtp4dev values instead. |
| D23 | Notes demo. | Stays, on the `/notes` route under "Inne" (UI-4). The API's `/notes` and the token check don't change. |
| D24 | Font loading. | Inter is bundled with `@fontsource-variable/inter` instead of loaded from Google Fonts, so the SPA makes no third-party requests. |
| D25 | Email snapshot. | `emails.subject` and `emails.body` store what was sent; `EmailSchema.subject` and `content` read them (W-17). |
| D26 | Entry to the email log. | From `sent` **and** `failed` campaigns. The source linked only `sent` campaigns, which have no failed emails, so resending one email was unreachable. |
| D27 | The by-campaign and by-client email lists. | Keep `skip`/`limit` and stay plain arrays, as in the source's endpoint table; no screen uses them (UI-13 uses `GET /emails/?campaign_id=`). |
| D28 | Page size. | `skip ≥ 0` (default 0), `limit` 1 to 1000 (default 100); 422 outside. The old UI's `limit=1000` workaround is gone, and an uncapped limit would load whole tables. |
| D29 | Schema module. | `api/app/schemas.py` becomes the package `api/app/schemas/` (API-3), with the notes schemas in `notes.py`, unchanged. |
| D30 | Request logging. | The source's request-logging middleware and `logging.basicConfig` are dropped: uvicorn's access log already logs method, path and status. |
| D32 | Small screens. | Below MUI's `md` breakpoint the NavBar becomes a temporary drawer opened from a top bar (UI-4), and every table scrolls horizontally inside its own container (UI-3). Each screen is checked at 375 px. This takes in the source's optional small-screen NavBar (F12). |

## 12. Deferred

Optional in the source, not on the roadmap:

- **B13: scheduler for `scheduled` campaigns.** It needs an owner for the SMTP settings, which
  global campaigns don't have. Until then the UI keeps `scheduledFor` as stored data (D6).
- **B14: open and click tracking** (pixel and redirect). Until then the UI hides "Otwarte" and
  "Kliknięcia" (D8).
- **F11: client import from Excel or CSV.** `POST /clients/bulk` (API-6) is ready for it.
- **A `text/plain` alternative part** in every email (B6).
- A display name in `From` (B6).
- Rejecting a `scheduledFor` in the past (B7).
- A warning when leaving the wizard with unsaved changes (F7).
- The rate percentages (`deliveryRate`, `openRate`, `clickRate`, `bounceRate`) on the email
  stats cards (F8).

W-11 and W-21 stay "do not port": that dead code is not deferred, it is dropped.

## 13. Source task mapping

Every source task and where it went. B11, F10 and F12 are not items of their own: each item
carries its share of their tests, accessibility and cleanup.

| Source task | Roadmap items | Notes |
|---|---|---|
| B0 Project bootstrap | API-2 | `api/` already has uv, ruff, pytest, settings and a Containerfile; API-2 adds the database dependencies and settings. The source's Dockerfile, Makefile targets and `generate_secrets.sh` are dropped (D21; the key command is in `api/.env.example`). |
| B1 Database layer and migrations | API-2, API-4, API-5, API-7, API-9, API-10 | API-2 the base, session and Alembic; each table in the item that uses it (D15). |
| B2 Core | API-3, API-7 | API-3 `BaseSchema`, domain errors, `Page` (replaces the source's X-Total-Count helper); API-7 encryption. CORS, `expose_headers`, the `get_current_user` stub and the logging middleware are dropped (D12, D13, D30). |
| B3 Categories module | API-4, API-5 | API-5 adds removing client links on delete. |
| B4 Clients module | API-5, API-6 | API-6 is the bulk endpoint. |
| B5 SMTP configuration | API-7, API-8 | API-8 adds `POST /config/smtp/test`. |
| B6 SMTP service | API-8 | The `text/plain` part and the `From` display name are deferred. |
| B7 Campaigns CRUD and recipients | API-9 | |
| B8 Campaign send and resend | API-11, API-12 | Background sending replaces the synchronous send and `SendCampaignResultSchema` (D17). |
| B9 Emails module | API-10, API-13 | API-13 is the single-email resend. |
| B10 Demo seed | API-14 | The SMTP seed is dropped (D22). |
| B11 Backend tests | API-2 and every API item | API-2 the fixtures (`conftest.py`); each item its own tests. The source's "coverage of `app/` at least 85 %" is dropped: `api/` has no coverage tooling. |
| B12 CI, Docker, compose, docs | API-1, API-8 | API-1 PostgreSQL and API-8 smtp4dev in the run modes; GitHub Actions, image push and `docs/` are dropped (D21). |
| B13 [OPT] Scheduler | deferred | needs an SMTP owner for global campaigns |
| B14 [OPT] Open and click tracking | deferred | D8 |
| F0 Bootstrap | UI-1, UI-2, UI-4 | UI-1 bun, UI-2 the test setup, UI-4 the page title. Vite, React and TypeScript exist; ESLint, husky, openapi-typescript, `env.ts` and `.env` are dropped (D20, §7). |
| F1 Design system | UI-3 | |
| F2 API layer, types, hooks, errors | UI-5, UI-4, UI-6 to UI-13 | UI-5 the error handling, `getErrorMessage`, `Page` helper, query defaults and `useDebounce`; UI-4 the ErrorBoundary; each screen item its own API functions, zod schemas and hooks. Axios, the `tokenStore` seam and generated types are dropped (D12, D20). |
| F3 App shell | UI-4 | Each screen item adds its route and NavBar entry. |
| F4 Categories | UI-6 | |
| F5 Clients | UI-7 | |
| F6 Campaign list | UI-9, UI-10 | UI-10 the send and resend with polling. |
| F7 Campaign wizard | UI-11, UI-12 | UI-12 the edit mode. |
| F8 Email log | UI-13 | |
| F9 SMTP settings | UI-8 | |
| F10 Tests and CI | UI-2 and every UI item | UI-2 the tooling and helpers; the CI workflow is dropped (D21). The source's thresholds (80 % of lines, 100 % of the campaign send's critical paths) are dropped: `web/` has no coverage tooling; UI-10 tests the send paths instead. |
| F11 [OPT] Excel/CSV import | deferred | D7 |
| F12 Cleanup and consistency | every UI item, UI-3, UI-4 | Dead code is not ported (W-21), each item adds only live NavBar entries (W-20) and its own accessibility. Small screens (D32): UI-3 the scrolling tables and stacked headers, UI-4 the small-screen NavBar. `frontend/docs/` is dropped (D21). |
