# Backlog

The roadmap. Items are grouped into phases: a `## ` heading with the phase goal
on the line below it. `/factory next` builds the first unchecked item, top to
bottom, and checks it off with its job id. `specs/mission.md` says what the
phases serve.

## Phase 1: A working dev stack

Goal: the demo app runs on the host, in containers and in a dev container, each with one command.

- [x] Copy the OAuth/OIDC auth from /Users/pawel/Downloads/oauth-bff-demo into this project: the BFF (bff/: login, logout, CSRF, session store, proxy), the protected API (api/), the Keycloak setup (keycloak/docker-compose.yml, realm-demo.json) and the web login flow (web/), with their tests and .env.example files → 001-oauth-bff-auth
- [x] Add a Makefile (or Taskfile) so the dashboard starts with one command, e.g. `make dashboard` serving factory/ on http://localhost:8000/dashboard.html, plus targets to run the backend and Docker services: `make backend` (starts api/ and bff/ locally), `make docker-up` / `make docker-down` / `make docker-logs` (Keycloak and any other docker-compose services), and `make help` listing all targets; add a short note in README.md → 002-makefile-dev-targets
- [x] Run the whole project in a sandbox with Podman instead of Docker: make Keycloak (keycloak/docker-compose.yml) run under rootless Podman (`podman compose` / podman-compose), optionally containerize api/, bff/ and web/ (Containerfiles) so the full stack starts in an isolated sandbox with one command, update the Makefile (e.g. `make podman-up` / `make podman-down` / `make podman-logs`, or switch the docker-* targets to a `CONTAINER_ENGINE` variable defaulting to podman), and update README.md and AGENTS.md → 003-podman-sandbox
- [x] Build the React frontend for the app (web/, Vite + React + TypeScript, Polish UI copy) on top of the existing login flow, talking to the backend only through the BFF `/api` proxy. First check whether the backend (bff/ or api/) already serves any frontend or static files (StaticFiles mounts, HTML/template routes, a bundled build, leftover placeholder pages); if it does, remove that code, its tests and its docs, so the backend is API-only and the SPA is served by Vite (dev) or a separate static host. Update README.md and AGENTS.md if the run instructions change → 004-react-frontend
- [x] Bind everything the repo starts to 127.0.0.1: publish Keycloak in keycloak/docker-compose.yml as `127.0.0.1:8080:8080` (as compose.yaml already does) and add `--bind 127.0.0.1` to the README's raw `python3 -m http.server` dashboard command; check that `make docker-up` still serves http://localhost:8080/realms/demo with Podman and with `CONTAINER_ENGINE=docker` → 006-bind-localhost
- [x] Add `make dev` so the stack runs on the host with one command: start Keycloak in the background (as `make docker-up`), then run the API, the BFF and the web dev server in one terminal with their logs interleaved, where one Ctrl-C stops all three (as `make backend` does for two); document it in AGENTS.md and README.md next to the other make targets

## Phase 2: Factory tooling

Goal: running, inspecting and cleaning up parallel factory jobs needs no manual git work and no port juggling.

- [x] Stop factory jobs colliding on port 8000: make the dashboard default to port 8090 (`DASHBOARD_PORT` in the Makefile, the README's `python3 -m http.server` command and the AGENTS.md port-clash note), let `web/vite.config.ts` take the BFF proxy target from an environment variable that defaults to `http://localhost:8000`, and document in AGENTS.md how an agent runs the BFF and the web dev server on its own ports to check the app
- [x] Add worktree helpers for the factory (jobs already run in their own worktree at ../<name>-factory/<job-id> on branch factory/<job-id>, and factory/jobs/ is already gitignored): `make worktrees` lists the job worktrees with their branch and job stage, `make worktree-clean` removes the worktrees and factory/<job-id> branches already merged into main, and the dashboard job cards show the worktree path from job.json next to the branch
- [-] Let factory agents run the sandbox inside the dev container: install Podman with a compose provider (and fuse-overlayfs, uidmap, slirp4netns or passt) in `.devcontainer/Containerfile`, give the `dev` service in `.devcontainer/compose.yaml` (and the Podman variant in `.devcontainer/podman/`) the least privileges nested rootless Podman needs (today `unshare --user` fails under the default seccomp profile, and there is no `/dev/fuse` or `/dev/net/tun`), let `make sandbox-up` publish on other ports there, since the dev container's own Keycloak, PostgreSQL and web dev server already hold 8080, 5432 and 5173, and update the "Dev container" section of AGENTS.md, which says there is no container engine inside

## Phase 3: Observability

Goal: the app reports its traffic, latency, errors and auth activity in a form Prometheus can scrape.

- [ ] Add application metrics: expose a /metrics endpoint (Prometheus format) with request count, latency histogram, error rate and auth login/logout counters, plus a short note on how to scrape it

## Phase 4: Email Sender API

Goal: the resource server stores clients, categories and campaigns in PostgreSQL, sends campaigns in the background through each user's SMTP server and logs every email, all behind the BFF.

- [x] Run PostgreSQL in all three run modes: a pinned `postgres` service (database, user and password `emailsender`, no volume, a `pg_isready` healthcheck) in `keycloak/docker-compose.yml` (published on 127.0.0.1:5432), `compose.yaml` and `.devcontainer/compose.yaml` (in keycloak's network namespace, not published, `api`/`dev` wait for it), `API_DATABASE_URL` in `api/.env.example`, documented in AGENTS.md, with no `api/` code, as specified in `specs/email-sender/backend.md` API-1 (covers B12, run-mode part) → 009-postgresql-run-modes
- [x] Add the async database layer to `api/`: SQLAlchemy 2 async with asyncpg, Alembic (`api/alembic.ini`, `api/migrations/`, no tables yet, `upgrade head` at startup), the model base with its naming convention and mixins, a per-request session dependency, and test fixtures on a separate `emailsender_test` database with per-test rollback that fail clearly when PostgreSQL is down, as specified in `specs/email-sender/backend.md` API-2 (covers B0 dependencies, B1 infrastructure, B11 `conftest.py`) → 010-api-async-database
- [x] Add the API core: the camelCase `BaseSchema` (with `app/schemas.py` turned into a package), typed domain errors mapped by one handler, the paginated `Page` response `{ items, total }` and the `skip`/`limit` parameters, as specified in `specs/email-sender/backend.md` API-3 (covers B2) → 011-api-core-schemas
- [x] Add categories to the API: model, migration and CRUD endpoints under `/categories/` with soft delete and a partial unique index on the name, every endpoint behind `PrincipalDep`, as specified in `specs/email-sender/backend.md` API-4 (covers B3) → 012-api-categories
- [x] Add clients to the API: the `clients` and `client_category` models and migration, CRUD under `/clients/` with full-replacement `PUT`, server-side search and the paginated list with its total, as specified in `specs/email-sender/backend.md` API-5 (covers B4 without bulk) → 013-api-clients
- [x] Add `POST /clients/bulk`, which creates clients row by row and reports per-row errors without stopping, as specified in `specs/email-sender/backend.md` API-6 (covers B4, bulk part) → 015-api-clients-bulk
- [x] Add per-user SMTP settings to the API: the `configs` table keyed by `user_sub`, its migration, Fernet encryption of the password with `API_ENCRYPTION_KEY`, and `GET`/`PUT /config/smtp`, as specified in `specs/email-sender/backend.md` API-7 (covers B5, B2 encryption) → 016-api-smtp-config
- [x] Add the SMTP sending service (aiosmtplib, correct TLS modes, 8 s timeout, mapped errors, a semaphore-bounded `send_many`), `POST /config/smtp/test`, and smtp4dev in all three run modes, as specified in `specs/email-sender/backend.md` API-8 (covers B6, B5 test endpoint, B12 smtp4dev part) → 017-api-smtp-sending
- [ ] Add campaigns to the API: the `campaigns` and `campaign_recipients` models and migration, CRUD under `/campaigns/` for drafts, the recipients endpoint and the stats, as specified in `specs/email-sender/backend.md` API-9 (covers B7)
- [ ] Add the email log to the API: the `emails` model with its subject and body snapshot, the migration, the filtered paginated list, SQL stats, and the single-email read, update, mark and delete endpoints, as specified in `specs/email-sender/backend.md` API-10 (covers B9 without resend)
- [ ] Send campaigns in the background: `POST /campaigns/{id}/send` checks the request, moves the campaign to `sending` atomically and answers 202, a background task sends with a semaphore and commits each result, and a startup sweep fails campaigns a restart interrupted, as specified in `specs/email-sender/backend.md` API-11 (covers B8, send part)
- [ ] Add `POST /campaigns/{id}/resend` for all or chosen failed recipients, through the same background flow, as specified in `specs/email-sender/backend.md` API-12 (covers B8, resend part)
- [ ] Add `POST /emails/{id}/resend`, a synchronous single-email resend within the BFF's timeout, as specified in `specs/email-sender/backend.md` API-13 (covers B9, resend part)
- [ ] Seed the demo clients (on reserved `.example` email domains) and campaigns at startup when `API_SEED_DEMO_DATA` is true, idempotently, as specified in `specs/email-sender/backend.md` API-14 (covers B10)

## Phase 5: Email Sender UI

Goal: a signed-in user manages clients, categories, campaigns and SMTP settings in the Polish SPA, and sends a campaign end to end, watching its progress.

- [ ] Replace npm with bun for `web/` in every run mode: `bun.lock` replaces the old lockfile, a pinned `oven/bun` image in `web/Containerfile`, bun in the dev container image and `post-create.sh`, `bun run` in the Makefile, bun commands in AGENTS.md, with no app code change, as specified in `specs/email-sender/frontend.md` UI-1 (covers F0, tooling part)
- [ ] Add Vitest and Testing Library to `web/` with a `bun run test` script, the test helpers and the first tests of the existing components, and add `bun run test` to the validation, as specified in `specs/email-sender/frontend.md` UI-2 (covers F10, test half; F0 test config)
- [ ] Add MUI with the light/dark theme, the design tokens, the bundled Inter font and the shared `ui/` components (including the horizontally scrolling table container), as specified in `specs/email-sender/frontend.md` UI-3 (covers F1)
- [ ] Add the app shell: react-router routes, the NavBar with the user section and logout (a temporary drawer behind a top bar on small screens), the layout, the notes demo on its own route under "Inne", and the ErrorBoundary, as specified in `specs/email-sender/frontend.md` UI-4 (covers F3, F2 ErrorBoundary)
- [ ] Add the SPA's error handling and API plumbing: the global error snackbar, `getErrorMessage`, 401 handling with a session-expired message, the `Page` zod helper, the QueryClient defaults, `useDebounce` and the `pluralPl` helper, as specified in `specs/email-sender/frontend.md` UI-5 (covers F2 core)
- [ ] Add the categories screen, as specified in `specs/email-sender/frontend.md` UI-6 (covers F4)
- [ ] Add the clients screen with server-side search and pagination, as the start page, as specified in `specs/email-sender/frontend.md` UI-7 (covers F5)
- [ ] Add the SMTP settings screen with the test email, as specified in `specs/email-sender/frontend.md` UI-8 (covers F9)
- [ ] Add the campaign list: table, status chips, stats, search, pagination, clone and delete, as specified in `specs/email-sender/frontend.md` UI-9 (covers F6 without send)
- [ ] Add campaign send and resend from the list, with "W trakcie" progress and status polling until the send ends, as specified in `specs/email-sender/frontend.md` UI-10 (covers F6, send part)
- [ ] Add the campaign wizard for creating a campaign, with sanitized previews in a sandboxed iframe, as specified in `specs/email-sender/frontend.md` UI-11 (covers F7)
- [ ] Add the campaign wizard's edit mode for draft campaigns, as specified in `specs/email-sender/frontend.md` UI-12 (covers F7, edit mode)
- [ ] Add the email log screen with stats, pagination and single-email resend, as specified in `specs/email-sender/frontend.md` UI-13 (covers F8)
