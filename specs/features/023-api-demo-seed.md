# Demo data seed (API-14)

> Feature: Seed the demo clients (on reserved `.example` email domains) and campaigns at startup when `API_SEED_DEMO_DATA` is true, idempotently, as specified in `specs/email-sender/backend.md` API-14 (covers B10)

## Context

This is roadmap item API-14 of Phase 4 (Email Sender API). The source of truth is
`specs/email-sender/backend.md`, "API-14: Demo data seed" (Requirements, Pitfalls, Acceptance
criteria), plus the "Rules for every item" at the top of that file. Background:
`specs/email-sender/README.md` §3.9 (D22: seed only when the setting is on, no SMTP seed), D31
(reserved `.example` domains, RFC 2606), W-27 (log counts only), §7 (the `API_SEED_DEMO_DATA`
row: default `false`, `.env.example` `true`). This spec restates them; where they differ, this
spec wins.

What exists today, in `api/`:

- `app/config.py`: `Settings` (prefix `API_`, reads `.env`), with `email_max_concurrent` and the
  required `encryption_key`. No `seed_demo_data`.
- `api/.env.example`: `API_ISSUER`, `API_AUDIENCE`, `API_DATABASE_URL`, `API_ENCRYPTION_KEY`,
  `API_EMAIL_MAX_CONCURRENT`, each with a comment line above. The sandbox (`compose.yaml`,
  service `api`, `env_file: ./api/.env.example`) and the dev container
  (`.devcontainer/post-create.sh` copies `.env.example` to `.env` when missing) read it.
- `app/main.py`: `create_app(settings, *, http_client, clock, session_factory,
  email_sender_factory)`. The lifespan runs `run_migrations` in a thread (logs and re-raises),
  then `build_campaign_sender(container, session).recover_interrupted()` in one
  `container.sessions()` session (logs and re-raises), then yields.
- `app/models/client.py`: `Client` (`company_name`, `primary_email`, `phone_number`, `notes`,
  `is_active` default true, `is_deleted`; partial unique index on `primary_email` among
  non-deleted clients). `app/models/campaign.py`: `Campaign` (`name`, `subject`, `content`,
  `status: CampaignStatus`, default `draft`; `recipients`), `CampaignRecipient` (`client_id`,
  `status` default `pending`). Neither has an owner column: domain data is global (D5).
- `app/schemas/clients.py` `ClientCreateSchema` (`primary_email: EmailStr`, company name rules)
  and `app/schemas/campaigns.py` `CampaignCreateSchema` (name, subject and content rules). The
  repositories (`app/repositories/client_repository.py`, `campaign_repository.py`) skip
  soft-deleted rows and commit inside each write method.
- `app/services/` holds the services; there is no `seed.py`.
- Tests: `tests/conftest.py` gives `database_url`, `session_factory` (one outer transaction
  per test, savepoint per session, rolled back after), `app` (builds `Settings(...)` with
  explicit values, still reading `api/.env` for the rest) and `client`.
  `tests/test_database.py` and `tests/test_campaign_sender.py`
  (`test_lifespan_fails_a_campaign_left_in_sending`) drive the lifespan with
  `app.router.lifespan_context(app)`. Because `Settings` reads `api/.env`, a developer whose
  `api/.env` has `API_SEED_DEMO_DATA=true` would make every lifespan test seed unless the tests
  set the value explicitly.

## Requirements

1. `Settings.seed_demo_data: bool = False` (env `API_SEED_DEMO_DATA`) in `app/config.py`, with a
   one-line comment. `api/.env.example` gets `API_SEED_DEMO_DATA=true` with a comment line
   (demo clients and campaigns at startup, idempotent, dev only).
2. `app/services/seed.py` with:
   - a frozen dataclass `SeedResult` with the int fields `clients_created`, `clients_skipped`,
     `campaigns_created`, `campaigns_skipped`, `recipients_created`;
   - `async def seed_clients_and_campaigns(session: AsyncSession) -> SeedResult`.
3. The seeded clients are exactly these five (`is_active` true, no address, no additional
   emails, no categories):

   | Company | Email | Phone | Notes |
   |---|---|---|---|
   | Acme Logistics | contact@acme-logistics.example | +1-202-555-0101 | Priority logistics partner |
   | Bright Dental Clinic | hello@brightdental.example | +1-202-555-0102 | Monthly newsletter subscriber |
   | Northwind Electronics | sales@northwind-electronics.example | +1-202-555-0103 | Interested in product launch campaigns |
   | Green Foods Market | owner@greenfoods-market.example | +1-202-555-0104 | Seasonal promo campaigns |
   | Pixel Craft Studio | team@pixelcraft.example | +1-202-555-0105 | Design partner |

4. The seeded campaigns are exactly these three, all `draft`, no `scheduled_for`, each with one
   recipient (status `pending`) per listed client, 7 recipients in total:

   | Name | Subject | Recipients |
   |---|---|---|
   | Spring Product Update | See what's new this spring 🌱 | Acme Logistics, Northwind Electronics, Pixel Craft Studio |
   | Monthly Newsletter - April | April highlights from our team | Bright Dental Clinic, Green Foods Market |
   | VIP Partner Invitation | Invitation: partner strategy session | Acme Logistics, Pixel Craft Studio |

   Content: a short HTML greeting that contains `{company}` (for example
   `<p>Hello {company},</p><p>…</p>`), one per campaign. The subject's emoji stays (it
   exercises the UTF-8 subject). No categories are created.
5. The seed data passes the API's own validation: each client's values validate as
   `ClientCreateSchema` and each campaign's as `CampaignCreateSchema` (reuse the schemas, so
   a value the API would reject can't be seeded).
6. Idempotence by natural keys: a client is looked up by `primary_email` among non-deleted
   clients, a campaign by `name` among non-deleted campaigns. A found row is counted as
   skipped and left untouched (an existing campaign's recipients are not changed). A created
   campaign's recipients point at the clients found or created in the same run. A second run
   creates nothing.
7. The seed commits once, at the end, so a failure part-way leaves nothing behind.
8. Lifespan in `app/main.py`: after the migrations and `recover_interrupted()`, when
   `settings.seed_demo_data` is true, run the seed in one `container.sessions()` session. On
   any exception: roll back, log it with `logger.exception`, and let startup continue (do not
   re-raise). On success log one INFO line with the five counts and nothing else (W-27). With
   the setting false the seed is not called.
9. `uv run python -m app.services.seed` (from `api/`) runs the seed by hand against
   `API_DATABASE_URL` from `Settings()` (its own engine, disposed afterwards), whatever
   `API_SEED_DEMO_DATA` says, and prints the five counts. It does not run migrations.
10. Tests in `api/tests/test_seed.py`, against the test database through `session_factory`:
    - on an empty database: 5 clients, 3 campaigns, 7 recipients created, 0 skipped; the
      stored rows have exactly the values in Requirements 3 and 4 (company, email, phone,
      notes; name, subject, status `draft`, recipient companies); every seeded email address
      ends in `.example`; each content contains `{company}`;
    - a second run: 0 clients and 0 campaigns created, 5 and 3 skipped, 0 recipients created,
      and the row counts are unchanged;
    - a pre-existing client with one of the seed emails is reused (skipped, not duplicated) and
      the created campaigns point at it;
    - the lifespan seeds with `seed_demo_data=True` and doesn't with `False`;
    - a seed that raises (for example `monkeypatch` on the seed function as `app.main` uses
      it) is logged (`caplog`) and the lifespan still yields.
11. Every test that builds `Settings` and runs the lifespan sets `seed_demo_data` explicitly
    (the conftest `app` fixture and the existing lifespan tests pass `seed_demo_data=False`),
    so results don't depend on the developer's `api/.env`.
12. Docs: `AGENTS.md` gets a short note (near the `API_ENCRYPTION_KEY` paragraph under
    "Setup") that `api/.env.example` sets `API_SEED_DEMO_DATA=true`, which seeds five demo
    clients on `.example` addresses and three draft campaigns at API startup, idempotently;
    that an existing `api/.env` lacks the line and gets no demo data until it is copied; and
    that `cd api && uv run python -m app.services.seed` seeds by hand. No `api-contract.md`
    change (no endpoint changes).

## Acceptance criteria

1. `api/app/config.py` has `seed_demo_data: bool = False`; `api/.env.example` contains the
   line `API_SEED_DEMO_DATA=true`. Check: `grep -n seed_demo_data api/app/config.py` and
   `grep -n API_SEED_DEMO_DATA api/.env.example`.
2. With PostgreSQL running (`make docker-up`), `cd api && uv run pytest tests/test_seed.py`
   passes, covering: first run creates 5 clients, 3 campaigns, 7 recipients with the exact
   table values and only `.example` addresses; second run creates nothing (5 and 3 skipped, 0
   recipients); a pre-existing client is reused; the lifespan seeds with the setting on, not
   with it off; a seed error is logged and the app still starts.
3. `grep -rn "acme-logistics.com\|brightdental.com\|northwind-electronics.com\|greenfoods-market.com\|pixelcraft.studio" api/`
   prints nothing.
4. With `API_SEED_DEMO_DATA=true` in `api/.env` and PostgreSQL running, starting the API
   (`cd api && uv run uvicorn app.main:create_app --factory --port 8001`) logs one line with
   the counts (5 clients created on an empty database, all skipped on the next start) and no
   other seed output; with the setting false or absent no seed line is logged.
5. `cd api && uv run python -m app.services.seed` prints the five counts and exits 0 (all
   skipped when the data is already there).
6. `make sandbox-up`, sign in at http://localhost:5173 as `alice`/`alice`, and
   `GET /api/clients/` through that origin (for example in the browser's devtools, signed in)
   lists the five seeded clients.
7. `AGENTS.md` describes `API_SEED_DEMO_DATA`, the note that an existing `api/.env` lacks it,
   and the `uv run python -m app.services.seed` command.
8. In `api/`: `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests` pass. `bff/` is
   unchanged (`git diff --stat main -- bff/` prints nothing).

## Out of scope

- Seeding SMTP settings, notes, categories, emails or anything per user (D22: Keycloak subs are
  generated at realm import).
- Any `.test`, `localhost` or real or registrable domain in seed data (D31; `EmailStr` rejects
  `.test` and `localhost`).
- Updating or "repairing" existing rows that match a natural key (changing their values,
  recipients or status), or undeleting soft-deleted rows.
- A new Alembic revision, new endpoints, a reset/unseed command, or seeding from a data file.
- Web (`web/`) changes, or changes to `compose.yaml` and the dev container (they already read
  `api/.env.example`).

## Assumptions

- Campaigns are matched by name among non-deleted campaigns only. Reason: backend.md says "(not
  deleted)" for clients, and every campaign query in the repo skips deleted rows.
- An existing campaign is skipped as a whole, without checking its recipients. Reason: backend.md
  idempotence is by natural key, and the counts have no "recipients skipped".
- The seed commits once, so it is all or nothing. Reason: backend.md says an error rolls back,
  which only leaves a clean state with a single commit.
- The manual command seeds even when `API_SEED_DEMO_DATA` is false and doesn't migrate. Reason:
  running it by hand is the explicit request; the API's startup owns migrations.
- The campaign content text is ours (short HTML with `{company}`). Reason: backend.md says the
  source's text is unknown.
- `AGENTS.md` gets the note even though the variable is optional. Reason: README.md §7 says
  `api/.env` doesn't pick up new lines, and without the line a developer sees no demo data.
