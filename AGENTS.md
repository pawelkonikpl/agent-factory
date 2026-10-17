# AGENTS.md

OAuth/OIDC Backend-for-Frontend demo plus the software factory that builds on it.

## Layout

- `bff/`: FastAPI Backend-for-Frontend, the OAuth confidential client (login, logout, CSRF, sessions, `/api` proxy). Python, uv.
- `api/`: FastAPI resource server (notes per user), verifies JWTs from Keycloak. Python, uv.
- `web/`: Vite + React + TypeScript SPA. UI copy is Polish. The Vite dev server serves it in development, and `bun run build` writes a static bundle to `web/dist/` for a separate static host that shares its origin with the BFF (proxying `/bff` and `/api`), since `bff/` and `api/` serve no frontend files. The SPA talks to the backend only through `/bff/*` (session) and `/api/*` (the BFF proxy).
- `keycloak/`: dev-only Keycloak, PostgreSQL and smtp4dev (`docker-compose.yml`) and the `demo` realm (`realm-demo.json`).
- `compose.yaml` (root): the dev-only sandbox that runs the whole stack in containers, built from the `Containerfile` in each of `api/`, `bff/` and `web/`.
- `.devcontainer/`: dev-only coding environment (dev container plus Keycloak, PostgreSQL and smtp4dev), see "Dev container".
- `.claude/`, `factory/`: the software factory (skill, agents, dashboard served by `factory/serve.py`, backlog). See README.md.
- `specs/`: `mission.md` (why the repo exists, its principles and non-goals; read it before planning a feature), `features/` (one spec per factory job, `<job-id>.md`, committed with the code it describes) and `email-sender/` (the Email Sender's product docs, HTTP contract and per-item specs for Phases 4 and 5 of the backlog). The roadmap is `factory/backlog.md`.

## Setup (fresh checkout)

Each line from the repo root:

```bash
cd bff && cp .env.example .env && uv sync
cd api && cp .env.example .env && uv sync
cd web && bun install
```

The `web/` commands need bun 1.4.3 on the host.

`.env` files are git-ignored. The BFF does not start without `bff/.env`.

An existing `api/.env` lacks `API_ENCRYPTION_KEY`, which is required: without it the
API, its tests and `alembic` don't start. Copy that line from `api/.env.example`. The
demo key there is public (it is in git): before saving a real SMTP password, generate
your own key into `api/.env` with
`cd api && uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`,
or use the dev SMTP server smtp4dev (values under "Run locally").

`api/.env.example` sets `API_SEED_DEMO_DATA=true`: at startup the API seeds five demo
clients on reserved `.example` addresses and three draft campaigns, idempotently (a
second start creates nothing). An existing `api/.env` lacks the line and gets no demo
data until it is copied from `api/.env.example`. `cd api && uv run python -m app.services.seed`
seeds by hand, whatever the setting says.

## Run locally

Each command in its own terminal, from the repo root:

```bash
podman compose -f keycloak/docker-compose.yml up -d                  # Keycloak, port 8080 (admin/admin), PostgreSQL, port 5432, and smtp4dev, ports 2525 and 5080
cd api && uv run uvicorn app.main:create_app --factory --port 8001    # API, port 8001
cd bff && uv run uvicorn app.main:create_app --factory --port 8000    # BFF, port 8000
cd web && bun run dev                                                 # web, port 5173
```

Docker works too: `docker compose -f keycloak/docker-compose.yml up -d` or
`make docker-up CONTAINER_ENGINE=docker`.

The Keycloak compose file also starts PostgreSQL on 127.0.0.1:5432 (database, user
and password `emailsender`, dev only, no persistent data). A PostgreSQL already
running on the host on 5432 clashes with it: stop that one first.

It also starts smtp4dev, a dev SMTP server that accepts every message and keeps it
in an inbox instead of delivering it (no persistent mail): SMTP on 127.0.0.1:2525,
inbox at http://localhost:5080. Anything else listening on 2525 or 5080 clashes with
it. To send through it, enter these values in "Ustawienia": server `localhost`, port
`2525`, TLS off, user `noreply@localhost` (also the `From` address) and no password.
With TLS off the API refuses to log in, so it never sends a password in clear text:
with a saved password, `POST /config/smtp/test` answers 400. A saved password can't be
cleared, so for smtp4dev sign in as a demo user that has none saved.

The API needs PostgreSQL: start it first (`make docker-up`). At startup the API
runs `alembic upgrade head` (`api/alembic.ini`, `api/migrations/`) against
`API_DATABASE_URL`; without PostgreSQL it logs the error and does not start.

Open http://localhost:5173. Demo users `alice`/`alice` and `bob`/`bob` (dev only).

The root `Makefile` wraps these: `make docker-up` (also `docker-down`,
`docker-logs`; Keycloak and PostgreSQL only), `make backend` (API and BFF in one terminal,
Ctrl-C stops both), `make web` (web dev server, port 5173), `make web-build`
(runs `bun run build` in `web/`) and `make dashboard`. `make sandbox-up` (also
`sandbox-down`, `sandbox-logs`) runs the whole stack in containers, see
"Sandbox". The `docker-*` and `sandbox-*` targets run through
`CONTAINER_ENGINE` (default `podman`; `CONTAINER_ENGINE=docker` for Docker).
`make help` lists every target.

- To look at pages, the web dev server can run on another port:
  `cd web && bun run dev --port <port>`. Signing in only works on 5173, the
  redirect URI registered in `keycloak/realm-demo.json`. The page needs the BFF on
  8000 (the Vite proxy target) to get past "checking session".
- To look at signed-in pages without Keycloak, the BFF or a sign-in, stub the
  SPA's requests in the browser (for example with `agent-browser network route`):
  `GET /bff/session` returns
  `{"authenticated":true,"user":{"sub":"alice","name":"Alice Example","email":"alice@example.com"}}`,
  `GET /api/notes` returns `[]` or
  `[{"id":"1","text":"Notatka","created_at":"2026-10-10T15:03:00+02:00"}]`, and
  `POST /bff/logout` returns `{"logout_url":"http://localhost:5173/"}` (abort it
  to see the logout error).
- The factory dashboard (`make dashboard` or `python3 factory/serve.py`) defaults
  to port 8000 and collides with the BFF. While the BFF runs, serve it on
  another port: `make dashboard DASHBOARD_PORT=8090` or
  `python3 factory/serve.py --port 8090` (or any free port).

## Sandbox

The root `compose.yaml` runs Keycloak, PostgreSQL, smtp4dev, the API, the BFF and
the web dev server in containers. It needs Podman with a compose provider (`podman compose`
delegates to docker-compose or podman-compose); on macOS run
`podman machine start` first.

```bash
make sandbox-up      # build the images and start all six services
make sandbox-logs    # follow the logs until Ctrl-C
make sandbox-down    # stop and remove the containers
```

- Open http://localhost:5173. Keycloak is on http://localhost:8080. Both bind to
  127.0.0.1 only. The BFF (8000) and the API (8001) are not published.
- The fifth service, `postgres` (PostgreSQL, database, user and password
  `emailsender`, no persistent data), is reachable on localhost:5432 inside the
  shared namespace only and is not published. `api` starts once it is healthy.
- The sixth service, `smtp4dev` (no persistent mail), shows its inbox on
  http://localhost:5080. Its SMTP port, 2525, is reachable inside the shared
  namespace only and is not published; the "Ustawienia" values are the ones under
  "Run locally".
- It uses the `.env.example` values, not `bff/.env` or `api/.env`.
- The source is baked into the images, with no live reload: after a code change
  run `make sandbox-up` again to rebuild.
- Keycloak takes a while to start, so the first login may fail until it is up.
  Watch `make sandbox-logs`.
- It cannot run at the same time as the host-run Keycloak and PostgreSQL
  (`make docker-up`) or `bun run dev` (`make web`) on 5173: they use the same ports.

## Dev container

`.devcontainer/` is a coding environment with Python 3.12, uv, bun 1.4.3, Node 22, git
and make. Keycloak runs as a second container that shares its network, so
`localhost:8080` inside it is Keycloak. PostgreSQL runs as a third container on the
same network, so `localhost:5432` inside it is PostgreSQL (database, user and
password `emailsender`, no persistent data, not forwarded to the host). smtp4dev runs
as a fourth container on the same network: SMTP on `localhost:2525` inside it (the
"Ustawienia" values are the ones under "Run locally"), and its inbox on 5080, which
the client forwards to http://localhost:5080. It needs Docker or Podman and a Dev
Containers client, such as VS Code with the Dev Containers extension ("Dev
Containers: Reopen in Container"). VS Code asks which configuration to use: "OAuth
BFF demo" for Docker, "OAuth BFF demo (Podman)" for Podman.

The API, the BFF and the web dev server start in the background on every start of
the container (`.devcontainer/post-start.sh`). Logs: `/tmp/dev-backend.log` and
`/tmp/dev-web.log`. To restart them, stop them with `pkill -f uvicorn; pkill -f vite`
and run the script again, or run each in its own terminal:

```bash
make backend    # API and BFF
make web        # web dev server, port 5173
```

- A dev container created before PostgreSQL, smtp4dev or bun was added doesn't have
  them: rebuild it ("Dev Containers: Rebuild Container").
- Setup runs automatically when the container is created: `.env` is copied from
  `.env.example` where it is missing, then `uv sync --frozen` and
  `bun install --frozen-lockfile`.
- Open http://localhost:5173. The client forwards 5173, 8080 and 5080 to the host. Demo
  users and the validation commands are the same as on the host.
- Podman: set the VS Code setting `dev.containers.dockerPath` to `podman`.
  `.devcontainer/podman/` maps your user to `vscode` (`keep-id`), so the container
  can write the checkout under rootless Podman. `podman compose` needs
  docker-compose or podman-compose 1.2 or newer.
- `bunx @devcontainers/cli up --workspace-folder .` also builds and starts it; for
  Podman add `--docker-path podman --config .devcontainer/podman/devcontainer.json`.
  That CLI doesn't forward ports, so it's good for tests but not for signing in
  from a host browser.
- It cannot run at the same time as the sandbox, the host-run Keycloak and
  PostgreSQL (`make docker-up`) or host `make web`: they use the same ports.
- `.venv` and `node_modules` live in the bind-mounted checkout and are shared with
  the host. The container installs Linux builds there, so after using it, rerun
  the host setup.
- There is no container engine inside, so the `make docker-*` and
  `make sandbox-*` targets don't work there.
- Keycloak takes a while to start on first use, so the first login may fail until
  it is up.
- `devcontainer-lock.json`, in `.devcontainer/` and in `.devcontainer/podman/`,
  pins the Node feature version. Commit it when the client updates it.

## Validation

In `bff/` and in `api/`:

```bash
uv run pytest
uv run ruff check .
uv run mypy app tests
```

In `api/`, `uv run pytest` needs PostgreSQL running (any run mode's). It creates
the `emailsender_test` database itself, resets its schema and runs the migrations
on it; override it with `API_TEST_DATABASE_URL`, whose database name must contain
`test`. When PostgreSQL is not reachable, the tests fail with a message naming the
host and port.

`uv run pytest` in `api/` includes one test marked `online` that sends a real email
through smtp4dev on `localhost:2525` (`make docker-up`, or inside the dev
container; the sandbox doesn't publish 2525). It skips when smtp4dev is not running; `uv run pytest -m "not online"`
leaves it out, `uv run pytest -m online -rs` runs only it.

In `web/`:

```bash
bun run build
bun run test
```

`bun run test` runs Vitest with jsdom and Testing Library on the `*.test.ts(x)` files in
`web/src`, with `fetch` stubbed, so no backend has to run. It runs Vitest on Node, not on
bun, so it needs `node` on PATH in jsdom 30's range: 22.22.2 or newer on 22, 24.15 or
newer on 24, or 26 and later. The dev container has it. `bun test` is bun's own test
runner, not Vitest, and fails on these tests.
