# AGENTS.md

OAuth/OIDC Backend-for-Frontend demo plus the software factory that builds on it.

## Layout

- `bff/`: FastAPI Backend-for-Frontend, the OAuth confidential client (login, logout, CSRF, sessions, `/api` proxy). Python, uv.
- `api/`: FastAPI resource server (notes per user), verifies JWTs from Keycloak. Python, uv.
- `web/`: Vite + React + TypeScript SPA. UI copy is Polish.
- `keycloak/`: dev-only Keycloak (`docker-compose.yml`) and the `demo` realm (`realm-demo.json`).
- `.claude/`, `factory/`: the software factory (skill, agents, dashboard, backlog). See README.md.

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
docker compose -f keycloak/docker-compose.yml up -d                  # Keycloak, port 8080 (admin/admin)
cd api && uv run uvicorn app.main:create_app --factory --port 8001    # API, port 8001
cd bff && uv run uvicorn app.main:create_app --factory --port 8000    # BFF, port 8000
cd web && npm run dev                                                 # web, port 5173
```

Open http://localhost:5173. Demo users `alice`/`alice` and `bob`/`bob` (dev only).

The root `Makefile` wraps these: `make docker-up` (also `docker-down`,
`docker-logs`), `make backend` (API and BFF in one terminal, Ctrl-C stops both)
and `make dashboard`. `make help` lists every target.

- To look at pages, the web dev server can run on another port:
  `cd web && npm run dev -- --port <port>`. Signing in only works on 5173, the
  redirect URI registered in `keycloak/realm-demo.json`. The page needs the BFF on
  8000 (the Vite proxy target) to get past "checking session".
- The factory dashboard (`make dashboard` or `python3 -m http.server`) defaults
  to port 8000 and collides with the BFF. While the BFF runs, serve it on
  another port: `make dashboard DASHBOARD_PORT=8090` or
  `cd factory && python3 -m http.server 8090` (or any free port).

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
