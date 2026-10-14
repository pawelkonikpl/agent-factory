# Email Sender roadmap

The two phases below go into `factory/backlog.md` after Phase 3, pasted as they are from the
main checkout once job `008-email-sender-rebuild` has merged (job branches never touch the
backlog). Each line is one small factory job that merges on its own and leaves every validation
command green. The specs the lines point to are in this folder.

## Phase 4: Email Sender API

Goal: the resource server stores clients, categories and campaigns in PostgreSQL, sends campaigns in the background through each user's SMTP server and logs every email, all behind the BFF.

- [ ] Run PostgreSQL in all three run modes: a pinned `postgres` service (database, user and password `emailsender`, no volume, a `pg_isready` healthcheck) in `keycloak/docker-compose.yml` (published on 127.0.0.1:5432), `compose.yaml` and `.devcontainer/compose.yaml` (in keycloak's network namespace, not published, `api`/`dev` wait for it), `API_DATABASE_URL` in `api/.env.example`, documented in AGENTS.md, with no `api/` code, as specified in `specs/email-sender/backend.md` API-1 (covers B12, run-mode part)
- [ ] Add the async database layer to `api/`: SQLAlchemy 2 async with asyncpg, Alembic (`api/alembic.ini`, `api/migrations/`, no tables yet, `upgrade head` at startup), the model base with its naming convention and mixins, a per-request session dependency, and test fixtures on a separate `emailsender_test` database with per-test rollback that fail clearly when PostgreSQL is down, as specified in `specs/email-sender/backend.md` API-2 (covers B0 dependencies, B1 infrastructure, B11 `conftest.py`)
- [ ] Add the API core: the camelCase `BaseSchema` (with `app/schemas.py` turned into a package), typed domain errors mapped by one handler, the paginated `Page` response `{ items, total }` and the `skip`/`limit` parameters, as specified in `specs/email-sender/backend.md` API-3 (covers B2)
- [ ] Add categories to the API: model, migration and CRUD endpoints under `/categories/` with soft delete and a partial unique index on the name, every endpoint behind `PrincipalDep`, as specified in `specs/email-sender/backend.md` API-4 (covers B3)
- [ ] Add clients to the API: the `clients` and `client_category` models and migration, CRUD under `/clients/` with full-replacement `PUT`, server-side search and the paginated list with its total, as specified in `specs/email-sender/backend.md` API-5 (covers B4 without bulk)
- [ ] Add `POST /clients/bulk`, which creates clients row by row and reports per-row errors without stopping, as specified in `specs/email-sender/backend.md` API-6 (covers B4, bulk part)
- [ ] Add per-user SMTP settings to the API: the `configs` table keyed by `user_sub`, its migration, Fernet encryption of the password with `API_ENCRYPTION_KEY`, and `GET`/`PUT /config/smtp`, as specified in `specs/email-sender/backend.md` API-7 (covers B5, B2 encryption)
- [ ] Add the SMTP sending service (aiosmtplib, correct TLS modes, 8 s timeout, mapped errors, a semaphore-bounded `send_many`), `POST /config/smtp/test`, and smtp4dev in all three run modes, as specified in `specs/email-sender/backend.md` API-8 (covers B6, B5 test endpoint, B12 smtp4dev part)
- [ ] Add campaigns to the API: the `campaigns` and `campaign_recipients` models and migration, CRUD under `/campaigns/` for drafts, the recipients endpoint and the stats, as specified in `specs/email-sender/backend.md` API-9 (covers B7)
- [ ] Add the email log to the API: the `emails` model with its subject and body snapshot, the migration, the filtered paginated list, SQL stats, and the single-email read, update, mark and delete endpoints, as specified in `specs/email-sender/backend.md` API-10 (covers B9 without resend)
- [ ] Send campaigns in the background: `POST /campaigns/{id}/send` checks the request, moves the campaign to `sending` atomically and answers 202, a background task sends with a semaphore and commits each result, and a startup sweep fails campaigns a restart interrupted, as specified in `specs/email-sender/backend.md` API-11 (covers B8, send part)
- [ ] Add `POST /campaigns/{id}/resend` for all or chosen failed recipients, through the same background flow, as specified in `specs/email-sender/backend.md` API-12 (covers B8, resend part)
- [ ] Add `POST /emails/{id}/resend`, a synchronous single-email resend within the BFF's timeout, as specified in `specs/email-sender/backend.md` API-13 (covers B9, resend part)
- [ ] Seed the demo clients and campaigns at startup when `API_SEED_DEMO_DATA` is true, idempotently, as specified in `specs/email-sender/backend.md` API-14 (covers B10)

## Phase 5: Email Sender UI

Goal: a signed-in user manages clients, categories, campaigns and SMTP settings in the Polish SPA, and sends a campaign end to end, watching its progress.

- [ ] Replace npm with bun for `web/` in every run mode: `bun.lock` replaces the old lockfile, a pinned `oven/bun` image in `web/Containerfile`, bun in the dev container image and `post-create.sh`, `bun run` in the Makefile, bun commands in AGENTS.md, with no app code change, as specified in `specs/email-sender/frontend.md` UI-1 (covers F0, tooling part)
- [ ] Add Vitest and Testing Library to `web/` with a `bun run test` script, the test helpers and the first tests of the existing components, and add `bun run test` to the validation, as specified in `specs/email-sender/frontend.md` UI-2 (covers F10, test half; F0 test config)
- [ ] Add MUI with the light/dark theme, the design tokens, the bundled Inter font and the shared `ui/` components, as specified in `specs/email-sender/frontend.md` UI-3 (covers F1)
- [ ] Add the app shell: react-router routes, the NavBar with the user section and logout, the layout, the notes demo on its own route under "Inne", and the ErrorBoundary, as specified in `specs/email-sender/frontend.md` UI-4 (covers F3, F2 ErrorBoundary)
- [ ] Add the SPA's error handling and API plumbing: the global error snackbar, `getErrorMessage`, 401 handling, the `Page` zod helper, the QueryClient defaults and `useDebounce`, as specified in `specs/email-sender/frontend.md` UI-5 (covers F2 core)
- [ ] Add the categories screen, as specified in `specs/email-sender/frontend.md` UI-6 (covers F4)
- [ ] Add the clients screen with server-side search and pagination, as the start page, as specified in `specs/email-sender/frontend.md` UI-7 (covers F5)
- [ ] Add the SMTP settings screen with the test email, as specified in `specs/email-sender/frontend.md` UI-8 (covers F9)
- [ ] Add the campaign list: table, status chips, stats, search, pagination, clone and delete, as specified in `specs/email-sender/frontend.md` UI-9 (covers F6 without send)
- [ ] Add campaign send and resend from the list, with "W trakcie" progress and status polling until the send ends, as specified in `specs/email-sender/frontend.md` UI-10 (covers F6, send part)
- [ ] Add the campaign wizard for creating a campaign, with sanitized previews, as specified in `specs/email-sender/frontend.md` UI-11 (covers F7)
- [ ] Add the campaign wizard's edit mode for draft campaigns, as specified in `specs/email-sender/frontend.md` UI-12 (covers F7, edit mode)
- [ ] Add the email log screen with stats, pagination and single-email resend, as specified in `specs/email-sender/frontend.md` UI-13 (covers F8)
