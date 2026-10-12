# AGENTS.md

OAuth/OIDC Backend-for-Frontend demo plus the software factory that builds on it.

## Layout

- `bff/`: FastAPI Backend-for-Frontend, the OAuth confidential client (login, logout, CSRF, sessions, `/api` proxy). Python, uv.
- `api/`: FastAPI resource server (notes per user), verifies JWTs from Keycloak. Python, uv.
- `web/`: Vite + React + TypeScript SPA. UI copy is Polish. The Vite dev server serves it in development, and `npm run build` writes a static bundle to `web/dist/` for a separate static host that shares its origin with the BFF (proxying `/bff` and `/api`), since `bff/` and `api/` serve no frontend files. The SPA talks to the backend only through `/bff/*` (session) and `/api/*` (the BFF proxy).
- `keycloak/`: dev-only Keycloak (`docker-compose.yml`) and the `demo` realm (`realm-demo.json`).
- `compose.yaml` (root): the dev-only sandbox that runs the whole stack in containers, built from the `Containerfile` in each of `api/`, `bff/` and `web/`.
- `.devcontainer/`: dev-only coding environment (dev container plus Keycloak), see "Dev container".
- `.claude/`, `factory/`: the software factory (skill, agents, dashboard, backlog). See README.md.
- `specs/`: `mission.md` (why the repo exists, its principles and non-goals; read it before planning a feature) and `features/` (one spec per factory job, `<job-id>.md`, committed with the code it describes). The roadmap is `factory/backlog.md`.

## Setup (fresh checkout)

Each line from the repo root:

```bash
cd bff && cp .env.example .env && uv sync
cd api && cp .env.example .env && uv sync
cd web && npm install
```

`.env` files are git-ignored. The BFF does not start without `bff/.env`.

## Run locally

Each command in its own terminal, from the repo root:

```bash
podman compose -f keycloak/docker-compose.yml up -d                  # Keycloak, port 8080 (admin/admin)
cd api && uv run uvicorn app.main:create_app --factory --port 8001    # API, port 8001
cd bff && uv run uvicorn app.main:create_app --factory --port 8000    # BFF, port 8000
cd web && npm run dev                                                 # web, port 5173
```

Docker works too: `docker compose -f keycloak/docker-compose.yml up -d` or
`make docker-up CONTAINER_ENGINE=docker`.

Open http://localhost:5173. Demo users `alice`/`alice` and `bob`/`bob` (dev only).

The root `Makefile` wraps these: `make docker-up` (also `docker-down`,
`docker-logs`; Keycloak only), `make backend` (API and BFF in one terminal,
Ctrl-C stops both), `make web` (web dev server, port 5173), `make web-build`
(runs `npm run build` in `web/`) and `make dashboard`. `make sandbox-up` (also
`sandbox-down`, `sandbox-logs`) runs the whole stack in containers, see
"Sandbox". The `docker-*` and `sandbox-*` targets run through
`CONTAINER_ENGINE` (default `podman`; `CONTAINER_ENGINE=docker` for Docker).
`make help` lists every target.

- To look at pages, the web dev server can run on another port:
  `cd web && npm run dev -- --port <port>`. Signing in only works on 5173, the
  redirect URI registered in `keycloak/realm-demo.json`. The page needs the BFF on
  8000 (the Vite proxy target) to get past "checking session".
- The factory dashboard (`make dashboard` or `python3 -m http.server`) defaults
  to port 8000 and collides with the BFF. While the BFF runs, serve it on
  another port: `make dashboard DASHBOARD_PORT=8090` or
  `cd factory && python3 -m http.server 8090` (or any free port).

## Sandbox

The root `compose.yaml` runs Keycloak, the API, the BFF and the web dev server
in containers. It needs Podman with a compose provider (`podman compose`
delegates to docker-compose or podman-compose); on macOS run
`podman machine start` first.

```bash
make sandbox-up      # build the images and start all four services
make sandbox-logs    # follow the logs until Ctrl-C
make sandbox-down    # stop and remove the containers
```

- Open http://localhost:5173. Keycloak is on http://localhost:8080. Both bind to
  127.0.0.1 only. The BFF (8000) and the API (8001) are not published.
- It uses the `.env.example` values, not `bff/.env` or `api/.env`.
- The source is baked into the images, with no live reload: after a code change
  run `make sandbox-up` again to rebuild.
- Keycloak takes a while to start, so the first login may fail until it is up.
  Watch `make sandbox-logs`.
- It cannot run at the same time as the host-run Keycloak (`make docker-up`) or
  `npm run dev` (`make web`) on 5173: they use the same ports.

## Dev container

`.devcontainer/` is a coding environment with Python 3.12, uv, Node 22, git and
make. Keycloak runs as a second container that shares its network, so
`localhost:8080` inside it is Keycloak. It needs Docker or Podman and a Dev
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

- Setup runs automatically when the container is created: `.env` is copied from
  `.env.example` where it is missing, then `uv sync --frozen` and `npm ci`.
- Open http://localhost:5173. The client forwards 5173 and 8080 to the host. Demo
  users and the validation commands are the same as on the host.
- Podman: set the VS Code setting `dev.containers.dockerPath` to `podman`.
  `.devcontainer/podman/` maps your user to `vscode` (`keep-id`), so the container
  can write the checkout under rootless Podman. `podman compose` needs
  docker-compose or podman-compose 1.2 or newer.
- `npx @devcontainers/cli up --workspace-folder .` also builds and starts it; for
  Podman add `--docker-path podman --config .devcontainer/podman/devcontainer.json`.
  That CLI doesn't forward ports, so it's good for tests but not for signing in
  from a host browser.
- It cannot run at the same time as the sandbox, the host-run Keycloak
  (`make docker-up`) or host `make web`: they use the same ports.
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

In `web/`:

```bash
npm run build
```
