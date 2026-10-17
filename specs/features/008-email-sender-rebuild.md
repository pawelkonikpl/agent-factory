# Email Sender specs and roadmap from the rebuild notes

> Feature: plan w fornderze new-app/rebuild jest dokumentacjia wstepna projektu trzeba dla nie j potrzeych speacifkacjie i dodac backbogu do implmentacji

(Translation: the plan in the `new-app/rebuild` folder is the project's preliminary documentation; write the specifications it needs and add backlog items to implement it.)

## Context

**The source.** `new-app/rebuild/` is untracked and exists only in the main checkout,
at `/workspace/new-app/rebuild/`. It is not in the worktree. The builder reads it from
there. It is in Polish and describes how to rebuild an "Email Sender" bulk email campaign
app from scratch. It was written by reviewing an older codebase that this repo doesn't
contain:

- `README.md` (341 lines): the product (clients in categories, campaigns built in a
  4-step wizard, sending through the user's own SMTP server, an email log with stats,
  resending), scope, the auth seam, stack, target architecture, conventions, env vars,
  infrastructure, 28 defects of the old version (W-01 to W-28, "do not repeat"), 10 open
  decisions with defaults (D1 to D10), and a task index with dependencies.
- `api-contract.md` (228 lines): the HTTP contract (enums, schemas, endpoints for
  `/categories`, `/clients`, `/campaigns`, `/emails` and `/config/smtp`, and the
  send/resend rules in §4 with their exact error messages).
- `backend-tasks.md`: B0 to B14 (B13 scheduler and B14 open/click tracking are optional).
- `frontend-tasks.md`: F0 to F12 (F11 Excel/CSV import is optional), with exact Polish
  UI copy and the full design tokens.
- `README copy.md`: an old frontend README. It is outdated (React 18, npm, `@dnd-kit`)
  and adds nothing the other files lack.

The notes assume a separate auth project: the SPA keeps JWTs, sends `Authorization:
Bearer`, refreshes tokens through `POST /auth/refresh`, and the backend has a `users`
table with an `int` id. They also assume their own `backend/` and `frontend/` folders,
an `/api/v1` prefix with CORS, list totals in an `X-Total-Count` header, a synchronous
send that answers with `SendCampaignResultSchema`, Docker images and GitHub Actions.
They use PostgreSQL (`psycopg2-binary`) and bun, which this job keeps (see
Requirements 5 and 6).

**How that meets this repo.**

- `specs/mission.md`: the repo exists for the factory and the OAuth/OIDC BFF demo. Its
  principles: tokens never reach the browser; the SPA talks to the backend only
  through `/bff/*` and `/api/*`; everything is dev-only with demo secrets in git;
  everything binds to 127.0.0.1; the stack runs on the host, in the sandbox and in the
  dev container, each documented in `AGENTS.md`; UI copy is Polish, and code, docs and
  specs are English. Its non-goals are production deployment (hosting, TLS, CI/CD) and
  real user management. The Email Sender is not mentioned anywhere.
- Auth already exists. The BFF (`bff/`) is the confidential client. `bff/app/api/proxy.py`
  forwards `/api/{path}` to `BFF_API_BASE_URL` (`http://localhost:8001`) with the session's
  access token. `bff/app/services/api_proxy.py` builds the upstream URL as
  `<base>/<path>`, so `/api/clients/` reaches the API at `/clients/`, and it passes back
  only the response headers in `FORWARDED_RESPONSE_HEADERS` (`content-type`,
  `cache-control`, `etag`, `last-modified`). The BFF's `http_timeout_seconds` is 10 s
  (`bff/app/config.py`, env prefix `BFF_`) and limits every proxied call.
- `api/` is the resource server: FastAPI, async, settings with env prefix `API_`
  (`api/app/config.py`), layered as `app/api/<router>.py` →
  `app/services/<x>_service.py` → `app/repositories/<x>_repository.py`, wired in
  `app/dependencies.py` (a `Container` plus `Annotated` dependency aliases). The caller
  is `PrincipalDep` (`Principal.subject`, the Keycloak `sub`, a string; demo users have
  generated UUIDs, see `keycloak/realm-demo.json`). A missing or invalid token gives
  401 through the handler in `api/app/main.py`. The notes demo (`app/api/notes.py`) is
  in memory, with no database. ruff, mypy strict and pytest are configured in
  `api/pyproject.toml`. `api/.env.example` holds only `API_ISSUER` and `API_AUDIENCE`.
  `api/Containerfile` is a uv-based image.
- `web/` is Vite + React 19 + TypeScript + TanStack Query + zod, installed with npm
  today (`package-lock.json`, `npm ci` in `web/Containerfile` on `node:22-slim`,
  `npm ci` in `.devcontainer/post-create.sh`, `npm run dev`/`npm run build` in the
  `Makefile` `web` and `web-build` targets, Node 22 as a dev container feature in
  `.devcontainer/devcontainer.json`, and `npm` commands in AGENTS.md).
  `.devcontainer/post-start.sh` finds the running dev server with the pattern
  `node_modules/.bin/vite`. It has no router, no UI library and no test runner. File
  names are kebab-case. `web/src/services/bff-client.ts` (`bffRequest`, zod parsing, the
  `X-CSRF` header, same-origin cookies) is the only `fetch` call, and returns only the
  parsed body. `web/src/app.tsx` shows the login screen or the header, the notes panel
  and the token check. `web/src/components/header-bar.tsx` shows the user's `name` and
  `email` from `GET /bff/session` and logs out through `POST /bff/logout`.
- Run modes: `keycloak/docker-compose.yml` (host; `make docker-up`), the root
  `compose.yaml` (sandbox: `api`, `bff` and `web` join the `keycloak` service's network
  namespace with `network_mode: "service:keycloak"`, and only `keycloak` publishes ports,
  on 127.0.0.1) and `.devcontainer/compose.yaml` (dev container: `dev` joins `keycloak`'s
  namespace, nothing is published). The dev container's image is
  `.devcontainer/Containerfile`, which copies `uv` in from its image with
  `COPY --from=ghcr.io/astral-sh/uv:0.9.10`. None of the modes has a database.
- `specs/` holds `mission.md` and `features/<job-id>.md`. `AGENTS.md` "Layout" describes
  it.
- `factory/backlog.md` is the roadmap. Phases 1 to 3 are there, and Phase 1 still has an
  unchecked item. `.claude/skills/factory/SKILL.md` ("Merge") says job branches never
  touch `factory/backlog.md`.

**What the human decided** (`rework-1.md`): the Email Sender is built into `api/` and
`web/` behind the BFF, with the mission change; the phases go to
`specs/email-sender/roadmap.md` and are pasted after Phase 3 once this job merges;
PostgreSQL, not SQLite, in every run mode; bun, not npm, for `web/`; campaign send and
resend run in the background with a semaphore, the campaign shows a `sending` status and
the UI polls it; list totals come in the response body, with no BFF change; and the
implementation is many small, independently mergeable roadmap items.

## Requirements

1. Create `specs/email-sender/` in English, translated from `/workspace/new-app/rebuild/`
   and adapted to this repo as items 3 to 11 below. Keep the source's detail: schemas,
   field limits, validation and error messages, status rules, stats formulas, the exact
   Polish UI copy (quoted verbatim, the only Polish allowed in these files), design
   tokens and per-task acceptance criteria. Keep the W-xx defect IDs and D-x decision IDs
   so later specs can cite them. Four files besides `roadmap.md`:
   - `README.md`: the product and data model, scope, how the app fits this repo (items 3
     to 11), conventions, configuration, the resolved decisions (D1 to D10, with D2
     changed by item 4, plus the adaptation decisions from items 3 to 11, numbered from
     D11), the defects table, a "Deferred" section, and a mapping table from every source
     task (B0 to B14, F0 to F12) to the roadmap item or items that cover it, or to
     "dropped" or "deferred" with a one-line reason.
   - `api-contract.md`: the adapted HTTP contract.
   - `backend.md`: one section per API roadmap item (`API-1` to `API-14`), each with Goal,
     Requirements, Pitfalls (W-xx), Depends on (earlier item IDs) and Acceptance criteria.
   - `frontend.md`: one section per UI roadmap item (`UI-1` to `UI-13`), same structure.
2. Create `specs/email-sender/roadmap.md` with the two phases below, in the exact format
   of `factory/backlog.md` (a `## ` heading, the goal on the line below, then `- [ ] `
   lines). Each item is one small job that can merge on its own and leaves every
   validation command green: roughly one backend area or one screen. Write each item as
   one line that a spec-writer can work from alone: it names the work, says "as
   specified in `specs/email-sender/backend.md` API-n" (or `frontend.md` UI-n), and
   names the source tasks it covers. Order and scope:
   - `## Phase 4: Email Sender API`. Goal: the resource server stores clients,
     categories and campaigns in PostgreSQL, sends campaigns in the background through
     each user's SMTP server and logs every email, all behind the BFF.
     - API-1 PostgreSQL in all three run modes: a `postgres` service in
       `keycloak/docker-compose.yml`, the root `compose.yaml` and
       `.devcontainer/compose.yaml`, `API_DATABASE_URL` in `api/.env.example`, AGENTS.md.
       No `api/` code. (B12, run-mode part)
     - API-2 Async database layer in `api/`: SQLAlchemy 2 async with asyncpg, Alembic
       (empty initial setup, `upgrade head` at startup), the test database fixtures with
       per-test isolation. (B0, B1 infrastructure, B11 `conftest.py`)
     - API-3 Core: the camelCase `BaseSchema`, typed domain errors with one handler, the
       paginated `Page` response `{ items, total }` and the `skip`/`limit` parameters.
       (B2)
     - API-4 Categories: model, migration, CRUD endpoints. (B3)
     - API-5 Clients: model and `client_category`, migration, CRUD, search, paginated
       list. (B4 without bulk)
     - API-6 `POST /clients/bulk`. (B4, bulk part)
     - API-7 Per-user SMTP settings: `configs` table, migration, Fernet encryption,
       `GET`/`PUT /config/smtp`. (B5)
     - API-8 The SMTP sending service, `POST /config/smtp/test`, and smtp4dev in all
       three run modes. (B6, B12 smtp4dev part)
     - API-9 Campaigns: models, migration, CRUD, recipients, stats. (B7)
     - API-10 The email log: model, migration, list with filters, stats, single-email
       read/update/mark/delete endpoints. (B9 without resend)
     - API-11 Campaign send in the background. (B8, send part)
     - API-12 Campaign resend in the background. (B8, resend part)
     - API-13 Single-email resend. (B9, resend part)
     - API-14 The demo data seed. (B10)
   - `## Phase 5: Email Sender UI`. Goal: a signed-in user manages clients, categories,
     campaigns and SMTP settings in the Polish SPA, and sends a campaign end to end,
     watching its progress.
     - UI-1 Switch `web/` from npm to bun in every run mode. (F0, tooling part)
     - UI-2 Vitest + Testing Library with a `bun run test` script and the test helpers.
       (F10, test half; F0 test config)
     - UI-3 MUI with the light/dark theme, design tokens, Inter and the shared `ui/`
       components. (F1)
     - UI-4 App shell: react-router routes, NavBar, layout, the notes route,
       ErrorBoundary. (F3, F2 ErrorBoundary)
     - UI-5 Error handling and API plumbing: the error snackbar, `getErrorMessage`, 401
       handling, the `Page` zod helper, QueryClient defaults, `useDebounce`. (F2 core)
     - UI-6 Categories screen. (F4)
     - UI-7 Clients screen. (F5)
     - UI-8 SMTP settings screen. (F9)
     - UI-9 Campaign list: table, status chips, stats, search, pagination, clone,
       delete. (F6 without send)
     - UI-10 Campaign send and resend with status polling. (F6, send part)
     - UI-11 Campaign wizard: create. (F7)
     - UI-12 Campaign wizard: edit. (F7, edit mode)
     - UI-13 Email log screen. (F8)
   B11, F10 and F12 are not separate items. Each item's section carries its share of
   their tests, accessibility and cleanup, and adds its own API functions, zod schemas
   and hooks (F2's table split by screen) rather than one big API layer up front.
3. Location and auth (README, contract, backend.md, frontend.md): the Email Sender is
   built into the existing `api/` and `web/`, behind the BFF. There is no `backend/` or
   `frontend/` folder. The "auth project" of the source notes is the BFF plus Keycloak:
   - API: the current user is the existing `PrincipalDep`. Its `Principal.subject` (a
     string) replaces `current_user.id`. There is no `users` table. `configs` has
     `user_sub` String(255) NOT NULL, indexed, with `UniqueConstraint(user_sub,
     config_key)`, and no foreign key. Every Email Sender endpoint requires the principal,
     and a missing token gives 401 from the existing handler. Drop the `get_current_user`
     stub, CORS and `expose_headers`: the browser only ever calls the same origin.
   - Web: no token store, no refresh, no `Authorization` header and no `/login` route.
     Requests go through `bffRequest` (cookie plus `X-CSRF`). A 401 invalidates the
     session query, so the existing login screen comes back. The NavBar's user section
     uses `name` and `email` from `GET /bff/session` (the avatar initial comes from
     `name`), and "Wyloguj" uses the existing logout. Hide "Profil".
4. Paths and list totals (contract): no `/api/v1` prefix. The API serves
   `/categories/`, `/clients/`, `/campaigns/`, `/emails/` and `/config/smtp`, and the SPA
   calls them as `/api/...` through the BFF. Keep the trailing-slash rules and the
   route-order note. Every paginated list (`GET /clients/`, `GET /campaigns/`,
   `GET /emails/`) answers `200 { "items": [...], "total": N }`, where `total` counts the
   rows after filters and before `skip`/`limit`. There is no `X-Total-Count` header. Lists
   without pagination (`GET /categories/`, `GET /emails/failed/`, the by-campaign and
   by-client email lists) stay plain arrays unless the source paginates them. Say in the
   README that the BFF, including `FORWARDED_RESPONSE_HEADERS` in
   `bff/app/services/api_proxy.py`, does not change for the Email Sender. This replaces
   D2.
5. PostgreSQL (README, API-1, API-2):
   - API-1 adds a `postgres` service on a pinned `docker.io/library/postgres` major/minor
     tag, with demo credentials in git (database, user and password `emailsender`), to
     all three compose files. Host (`keycloak/docker-compose.yml`): published as
     `127.0.0.1:5432:5432`. Sandbox (`compose.yaml`): joins the `keycloak` namespace like
     `api`, is not published, and `api` depends on it. Dev container
     (`.devcontainer/compose.yaml`): joins the `keycloak` namespace, so `localhost:5432`
     inside `dev` is Postgres. `api/.env.example` gets
     `API_DATABASE_URL=postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender`.
     AGENTS.md documents the service in "Run locally", "Sandbox" and "Dev container",
     that port 5432 clashes with a host Postgres, and that an existing dev container
     must be rebuilt to get it.
   - API-2 adds SQLAlchemy 2 async with asyncpg and Alembic (`api/alembic.ini`,
     `api/migrations/`), with `alembic upgrade head` run at startup. Each later API item
     adds its own tables in its own migration. Timestamps are `DateTime(timezone=True)`
     (W-22). Unique emails and category names use partial unique indexes
     `WHERE is_deleted = false` (W-02).
   - Tests use a separate database from `API_TEST_DATABASE_URL` (default the same server,
     database `emailsender_test`, created by the fixture when missing). Keep the source's
     guard: the URL must contain `test`, else `RuntimeError`. Isolation per test with an
     outer transaction and savepoints (W-25). `uv run pytest` in `api/` needs Postgres
     running from API-2 on and fails with a clear message when it is not reachable;
     API-2 says so in AGENTS.md "Validation".
6. bun (README, UI-1): `web/` uses bun, not npm. UI-1 replaces `package-lock.json` with
   `bun.lock` (W-18: one lockfile), moves `web/Containerfile` to a pinned
   `docker.io/oven/bun` image with `bun install --frozen-lockfile`, installs a pinned bun
   in `.devcontainer/Containerfile` (the same `COPY --from=` pattern as `uv`), runs
   `bun install --frozen-lockfile` in `.devcontainer/post-create.sh`, uses `bun run` in
   the `Makefile` `web` and `web-build` targets, keeps `.devcontainer/post-start.sh`
   finding the dev server, and changes every `npm` command in AGENTS.md to bun.
   `web/` validation becomes `bun run build`, and from UI-2 on also `bun run test`
   (Vitest; not `bun test`, which is bun's own runner: say so as a pitfall).
7. Background sending (contract §4, API-11, API-12, UI-10). This replaces the source's
   synchronous send and resolves W-24 fully:
   - `CampaignStatus` gains `sending`: `draft`, `sending`, `sent`, `failed`, `scheduled`.
   - `POST /campaigns/{id}/send` and `POST /campaigns/{id}/resend` run the §4 checks 1 to
     4 in the request, in the same order and with the same messages, then move the
     campaign to `sending` with one atomic `UPDATE ... WHERE status IN ('draft','failed')`
     (a lost race gives the same "current status" 400), start the sending as a
     background task and answer `202 CampaignSchema` with `status: "sending"`. A
     `sending` campaign therefore fails both endpoints with
     `"Campaign cannot be sent — current status: sending"`.
   - The background task uses its own database session, sends with
     `asyncio.Semaphore(max_concurrent)` (D10: query parameter, default
     `API_EMAIL_MAX_CONCURRENT`, 1 to 50), commits each recipient's result and `Email`
     row as it finishes, and ends with §4 steps 6: `failed` if any recipient is still
     `failed`, else `sent` with `sentAt`. An unexpected error marks the remaining
     `pending` recipients `failed` with an `Unexpected error: ...` message and the
     campaign `failed`.
   - At startup, campaigns left in `sending` by a restart get the same treatment, with
     the error `"Sending interrupted"`.
   - `DELETE` and `PUT` on a `sending` campaign give 400
     `"Campaign is being sent"` (PUT already allows only `draft`; keep that message for
     other statuses).
   - `SendCampaignResultSchema` is dropped. Progress is `CampaignSchema.stats`
     (`progressPercentage`, `sent`, `failed`, `pending`), read with
     `GET /campaigns/{id}`.
   - Tests replace the sender with a fake (the source's injected `EmailSender`) and wait
     for the background task to finish, with no real SMTP.
   - UI-10: after a 202 the campaign row shows the chip "W trakcie" with a
     `LinearProgress` from `stats.progressPercentage`, and the SPA polls
     `GET /campaigns/{id}` (TanStack Query `refetchInterval`, about 2 s) while the status
     is `sending`, then refreshes the campaign list, `["emails"]` and `["emailStats"]`.
     The source's result snackbars (success, "Wysłano częściowo", failure) are shown
     when polling sees the final status, with `successCount = stats.sent` and
     `failedCount = stats.failed`. Send and resend buttons are disabled while the
     campaign is `sending`. The "current status: sent" special case stays.
8. Timeouts (contract, API-8, API-13): the SMTP connect timeout is 8 s, so
   `POST /config/smtp/test` and `POST /emails/{id}/resend` (one email, synchronous) answer
   within the BFF's 10 s proxy timeout. The source's 30 s test timeout is dropped.
9. Dev SMTP (API-8): add smtp4dev (`rnwood/smtp4dev`, pinned tag) to the same three
   compose files as Postgres, placed the same way. SMTP port 2525 and web UI port 5080,
   published on 127.0.0.1 only on the host, and reachable as `localhost` from `api` in
   the sandbox and the dev container (the dev container's client forwards 5080). Document
   it in AGENTS.md with the values to enter in Ustawienia (server `localhost`, port 2525,
   TLS off).
10. Other stack adaptations (README and the item sections):
    - API: follow the existing `api/` layout and wiring, not the source's
      module-per-feature tree. Settings use the `API_` prefix (`API_DATABASE_URL`,
      `API_TEST_DATABASE_URL`, `API_ENCRYPTION_KEY`, `API_EMAIL_MAX_CONCURRENT`,
      `API_SEED_DEMO_DATA`). `api/.env.example` holds a demo Fernet key, which is allowed
      because demo secrets live in git. The validation commands are the existing three
      from AGENTS.md. The image stays `api/Containerfile`.
    - Web: zod schemas in `web/src/services/` (the `bffRequest` pattern) replace
      OpenAPI-generated types, so there is no `types:generate`/`types:check`. Kebab-case
      file names. No axios, no ESLint and no husky.
    - No GitHub Actions, no image push, no new Dockerfiles and no `docs/` trees.
11. Seed (API-14): demo clients and campaigns as in B10, only when `API_SEED_DEMO_DATA`
    is true (`api/.env.example` sets it to true). Drop `seed_smtp4dev_config`: Keycloak
    subs are generated, so the user enters the smtp4dev values from item 9 instead.
12. The existing notes demo stays. In UI-4, the notes panel and the token check move to
    their own route, under the NavBar's "Inne" section. `/notes` in the API is unchanged.
13. "Deferred" in README lists B13 (scheduler), B14 (open/click tracking), F11 (Excel/CSV
    import) and per-campaign text/plain alternatives, if the source marks them optional.
    Following D6 and D8, the UI hides "Otwarte"/"Kliknięcia" and stores `scheduledFor`
    without sending it later. W-11 and W-21 stay "do not port".
14. `specs/mission.md`, "Why this repo exists", item 2: say that the demo app built on
    the BFF is the Email Sender (clients, categories and email campaigns sent through the
    user's SMTP server, specified in `specs/email-sender/`), alongside the notes demo.
    Change nothing else in the mission.
15. `AGENTS.md`, "Layout", the `specs/` bullet: add `email-sender/` (the Email Sender's
    product docs, HTTP contract and per-item specs, with the roadmap phases to add to
    `factory/backlog.md` in `roadmap.md`).
16. Change no code and no file outside `specs/email-sender/`, `specs/mission.md` and
    `AGENTS.md`. The Postgres, smtp4dev, bun and env changes are written into the docs
    as work for later items, not made now.

## Acceptance criteria

1. `ls specs/email-sender/` lists exactly `README.md`, `api-contract.md`, `backend.md`,
   `frontend.md` and `roadmap.md`.
2. `git diff --name-only main` lists only those five files plus `specs/mission.md` and
   `AGENTS.md`. `factory/backlog.md` and `new-app/` are not in it.
3. `roadmap.md` has exactly two `## ` headings, `## Phase 4: Email Sender API` and
   `## Phase 5: Email Sender UI`, each followed by a `Goal:` line.
   `grep -c '^- \[ \] ' specs/email-sender/roadmap.md` prints `27` (14 then 13), in the
   order of Requirement 2, and every item line names its section (`API-n` or `UI-n`).
4. `backend.md` has sections `API-1` to `API-14` and `frontend.md` has sections `UI-1` to
   `UI-13`. Each has Goal, Requirements, Pitfalls, Depends on and Acceptance criteria
   headings or labels, and only depends on earlier items.
5. The mapping table in `README.md` lists all 28 source tasks: `grep -oE '\b[BF][0-9]+\b'
   specs/email-sender/README.md | sort -u` includes B0 to B14 and F0 to F12. Each one maps
   to one or more `API-n`/`UI-n` items, "dropped" or "deferred".
6. The adaptations are in place. `grep -rnE 'X-Total-Count|expose_headers|/api/v1|tokenStore|POST /auth/refresh|users\.id|SQLite|aiosqlite|npm |package-lock|GitHub Actions|SendCampaignResultSchema'
   specs/email-sender/` matches only lines that say the item is dropped or replaced (for
   example in the D11+ decisions or the mapping table).
7. The decided design is written down: `grep -n 'asyncpg' specs/email-sender/backend.md`,
   `grep -n '5432' specs/email-sender/backend.md`, `grep -n 'bun.lock' specs/email-sender/frontend.md`,
   `grep -n '202' specs/email-sender/api-contract.md`, `grep -n 'sending' specs/email-sender/api-contract.md`,
   `grep -n '"items"' specs/email-sender/api-contract.md`, `grep -n 'W trakcie' specs/email-sender/frontend.md`,
   `grep -n 'refetchInterval' specs/email-sender/frontend.md`, `grep -n 'user_sub' specs/email-sender/backend.md`
   and `grep -n 'PrincipalDep' specs/email-sender/backend.md` each find the matching rule
   from Requirements 3 to 7.
8. `api-contract.md` covers every endpoint of the source contract (§3.1 to §3.5) and the
   send rules (§4), with the same English error messages, plus the new
   "Campaign is being sent" and "Sending interrupted" messages. Check by comparing the
   endpoint tables with `/workspace/new-app/rebuild/api-contract.md`.
9. The detail survived translation. Spot-check against the source: the clients table and
   the email stats formulas in `api-contract.md`, the theme token table in `frontend.md`
   UI-3, the seed table in `backend.md` API-14, and the wizard's Polish copy in UI-11
   (for example "Wypełnij wszystkie wymagane pola przed przejściem dalej" appears
   verbatim).
10. Apart from quoted UI copy, the new files are English. A read-through finds no
    untranslated Polish prose.
11. A read-through of `roadmap.md` and the sections finds no item that needs a later
    item to pass its own acceptance criteria, and none that spans more than one backend
    area or one screen (UI-1 and API-1 are tooling-only).
12. `grep -n 'email-sender' specs/mission.md AGENTS.md` matches the new sentence in the
    mission and the new Layout text in AGENTS.md.
13. No code changed, so the existing validation still passes: `uv run pytest`,
    `uv run ruff check .` and `uv run mypy app tests` in `api/` and in `bff/`, and
    `npm run build` in `web/`.

## Out of scope

- Editing `factory/backlog.md`. Job branches never touch it (SKILL.md "Merge"). The
  phases wait in `roadmap.md` to be pasted in from the main checkout.
- Implementing any of the Email Sender: no code, dependency, env, compose, Containerfile,
  Makefile or BFF change.
- Committing, moving or deleting `new-app/rebuild/`.
- Specs for the deferred work (scheduler, tracking, import), a help page, i18n
  infrastructure, CI workflows or production deployment.
- Removing or changing the notes demo or the token check.
- Changing any part of `specs/mission.md` other than item 2 of "Why this repo exists",
  or the factory's skill and agent files.

## Assumptions

- **Email Sender phases go after Observability (Phases 4 and 5).** Reason: appending keeps
  the existing roadmap's order; the human confirmed pasting them after Phase 3.
- **27 items: 14 API and 13 UI.** Reason: the human asked for roughly one backend area or
  one screen per item; infra (Postgres, bun) and the send flow get their own items so
  each diff stays reviewable.
- **Each API item adds its own tables in its own migration, instead of one initial
  migration for every table.** Reason: it keeps each item self-contained and avoids
  models that no endpoint uses yet.
- **API tests run against the dev Postgres, in a separate `emailsender_test` database,
  and fail (not skip) when it is down.** Reason: the dev container has no container
  engine, so testcontainers can't work there, and silent skips would hide a broken
  suite. It means the factory's dev container must be rebuilt after API-1 merges, a
  human step that API-1 documents.
- **Postgres has no named volume.** Reason: it matches Keycloak's in-memory dev setup;
  the seed recreates demo data.
- **Background sending uses an in-process task, not a queue or worker.** Reason: the API
  is one dev process; a startup sweep of `sending` campaigns covers restarts.
- **Single-email resend stays synchronous.** Reason: it sends one email with an 8 s
  timeout, inside the BFF's 10 s limit; the human's rule was about campaign send and
  resend.
- **Deleting or editing a `sending` campaign is refused with "Campaign is being sent".**
  Reason: the background task would otherwise write into a deleted or changed campaign.
- **Polling uses the campaign's existing `stats`, and the result snackbars read the final
  campaign stats.** Reason: no new progress endpoint is needed; the resend snackbar
  therefore counts the whole campaign, not only this run.
- **`POST /clients/bulk` stays, as its own item, although its only UI (F11 import) is
  deferred.** Reason: the previous spec kept it and the human did not object; it is
  small and testable through the API.
- **Node stays in the dev container next to bun.** Reason: removing it is not needed for
  bun and could break tools that rely on it; the request only moves `web/` to bun.
- **No ESLint in `web/`.** Reason: the repo has none today and validation is `tsc` via
  `bun run build`; adding a linter is a separate decision.
- **The user key is the Keycloak `sub` string, and there is no `users` table.** Reason:
  "real user management" is a non-goal, and the demo realm is the user store.
- **Zod schemas replace OpenAPI-generated types in `web/`.** Reason: it reuses the existing
  `bffRequest` + zod pattern and gives runtime validation through one path.
- **The SMTP-config seed is dropped.** Reason: Keycloak subs are generated at import, so no
  user can be seeded ahead of time. AGENTS.md gives the smtp4dev values instead.
- **The notes demo and the token check stay, on their own route.** Reason: they show the
  BFF pattern the mission is about. Removing them is a separate decision.
- **Only the "Why this repo exists" item in the mission changes.** Reason: the principles and
  non-goals already cover the adapted design (Postgres and bun are dev tooling, not
  principles).
