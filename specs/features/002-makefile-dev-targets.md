# Makefile with dev targets (dashboard, backend, Docker, help)

> Feature: Add a Makefile (or Taskfile) so the dashboard starts with one command, e.g. `make dashboard` serving factory/ on http://localhost:8000/dashboard.html, plus targets to run the backend and Docker services: `make backend` (starts api/ and bff/ locally), `make docker-up` / `make docker-down` / `make docker-logs` (Keycloak and any other docker-compose services), and `make help` listing all targets; add a short note in README.md

## Context

- There is no Makefile or Taskfile in the repo today. Every dev command is typed by hand from the repo root, as listed in `AGENTS.md` ("Run locally"):
  - Keycloak: `docker compose -f keycloak/docker-compose.yml up -d` (port 8080).
  - API: `cd api && uv run uvicorn app.main:create_app --factory --port 8001`.
  - BFF: `cd bff && uv run uvicorn app.main:create_app --factory --port 8000`. It does not start without `bff/.env` (see "Setup" in `AGENTS.md`).
  - Web: `cd web && npm run dev` (port 5173). The Vite proxy targets the BFF on 8000 (`web/vite.config.ts`).
- The only compose file is `keycloak/docker-compose.yml`. It has one service, `keycloak`.
- The factory dashboard is `factory/dashboard.html`. It finds jobs by fetching the directory listing at `jobs/` and then `jobs/<id>/job.json` (around lines 399-407), so it needs a server that lists directories. `python3 -m http.server` does. `README.md` ("Dashboard" section) documents `cd factory && python3 -m http.server`, which serves on port 8000 and binds to all interfaces.
- Port clash: the dashboard's default port 8000 is also the BFF's port. `AGENTS.md` already says so and tells you to use `python3 -m http.server 8090` while the BFF runs.
- Tooling on the dev machine (macOS): `/usr/bin/make` is **GNU Make 3.81**. Features from 3.82 and later (e.g. `.ONESHELL`, `!=`, `define`-based `$(file ...)`) are not available.
- Docs to update: `README.md` (asked for in the request) and `AGENTS.md` ("Run locally" section, which also has the port-clash note).

## Requirements

1. Add a `Makefile` at the repo root. It must work with GNU Make 3.81 and be run from the repo root. Do not add a Taskfile.
2. Targets, each declared `.PHONY`:
   - `help`: prints every target in this list, each with a one-line description. It is the default goal, so plain `make` runs it. Generate the list from `## description` comments on the target lines (the usual `grep`/`awk` pattern) so it cannot drift from the real targets.
   - `dashboard`: serves the `factory/` directory with `python3 -m http.server`, bound to `127.0.0.1`, on port `$(DASHBOARD_PORT)`. `DASHBOARD_PORT` defaults to `8000` (`DASHBOARD_PORT ?= 8000`). Before it starts serving, it prints the URL `http://localhost:$(DASHBOARD_PORT)/dashboard.html`. It runs in the foreground until Ctrl-C.
   - `backend`: starts the API (`api/`, port 8001) and the BFF (`bff/`, port 8000) with the same `uv run uvicorn app.main:create_app --factory --port ...` commands as `AGENTS.md`. Both run from one terminal in the foreground, with their logs interleaved on stdout. One Ctrl-C stops both, leaving no uvicorn process behind. If either process exits, `make backend` must not hang with the other half orphaned; stopping both is fine.
   - `docker-up`: `docker compose -f keycloak/docker-compose.yml up -d`.
   - `docker-down`: `docker compose -f keycloak/docker-compose.yml down`.
   - `docker-logs`: `docker compose -f keycloak/docker-compose.yml logs -f` (follows until Ctrl-C).
3. The compose file path appears once, as a variable (e.g. `COMPOSE = docker compose -f keycloak/docker-compose.yml`), so that a second compose file can be added in one place later.
4. `README.md`: in the "Dashboard" section, add a short note that `make dashboard` starts the dashboard and that `make help` lists the other targets. Keep the existing `python3 -m http.server` instructions, because the README also describes copying `factory/` into other repos that will not have this Makefile.
5. `AGENTS.md`: in "Run locally", add a short note that `make docker-up`, `make backend` and `make dashboard` (and `make help`) wrap these commands. Update the port-clash bullet to say `make dashboard DASHBOARD_PORT=8090` while the BFF runs. Keep the existing raw commands.

## Acceptance criteria

1. `make help` and plain `make` (from the repo root) both print `help`, `dashboard`, `backend`, `docker-up`, `docker-down` and `docker-logs`, each with a description, and exit 0. Verify by running both commands.
2. `make -n dashboard backend docker-up docker-down docker-logs` exits 0 and shows the expected commands: `python3 -m http.server` with `--bind 127.0.0.1` and `--directory factory` (or the same effect via `cd factory`) on port 8000; two `uv run uvicorn app.main:create_app --factory` commands, in `api` on `--port 8001` and in `bff` on `--port 8000`; and `docker compose -f keycloak/docker-compose.yml` with `up -d`, `down` and `logs -f`.
3. Run `make dashboard` in the main checkout (where `factory/jobs/` exists). It prints `http://localhost:8000/dashboard.html`. `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/dashboard.html` returns `200`, and `curl -s http://localhost:8000/jobs/` returns a directory listing. Ctrl-C stops it.
4. `make dashboard DASHBOARD_PORT=8090` serves on 8090. `curl -s -o /dev/null -w '%{http_code}' http://localhost:8090/dashboard.html` returns `200`.
5. While `make dashboard` runs, `lsof -nP -iTCP:8000 -sTCP:LISTEN` shows the listener bound to `127.0.0.1`, not `*`.
6. With `bff/.env` and `api/.env` set up as in "Setup" in `AGENTS.md`, `make backend` starts both servers: `curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/docs` and `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/docs` each return an HTTP status (not a connection error). After one Ctrl-C in that terminal, `lsof -nP -iTCP:8000 -sTCP:LISTEN` and `lsof -nP -iTCP:8001 -sTCP:LISTEN` print nothing, and `pgrep -f "uvicorn app.main:create_app"` prints nothing.
7. With Docker running: `make docker-up` starts Keycloak (`docker compose -f keycloak/docker-compose.yml ps` shows `keycloak` running). `make docker-logs` streams its logs until Ctrl-C. `make docker-down` removes it (`ps` then lists no containers).
8. `grep -n "make dashboard" README.md` matches inside the "Dashboard" section, and that section also mentions `make help`. The original `python3 -m http.server` instructions are still there.
9. `grep -n "make " AGENTS.md` shows the new note in "Run locally" and `DASHBOARD_PORT=8090` in the port-clash bullet.
10. `git diff --stat main` lists only `Makefile`, `README.md` and `AGENTS.md`.
11. The existing validation still passes: `cd bff && uv run pytest && uv run ruff check . && uv run mypy app tests`, the same in `api/`, and `cd web && npm run build`. Only docs and the Makefile change, so this is a sanity check.

## Out of scope

- Targets this request does not ask for: `web`/`dev` (the Vite server), `install`/`setup`, `test`, `lint`, `build`, `clean`, or separate `api`/`bff` targets.
- Changing ports, `keycloak/docker-compose.yml`, `.env.example` files or any application code under `api/`, `bff/` or `web/`.
- Adding a Taskfile, a `scripts/` helper, `honcho`/`foreman`/`concurrently`, or any other new dependency. The Makefile uses only `make`, POSIX `sh`, `python3`, `uv` and `docker`.
- Copying `.env.example` to `.env` automatically, or checking for Docker/uv first.
- Rewriting the README beyond the short note, or removing the raw commands from README or AGENTS.md.
- Adding new compose services.

## Assumptions

- **Makefile, not Taskfile.** `make` is already installed on macOS and Linux. Task would be a new dependency.
- **The dashboard defaults to port 8000**, as the request says, with a `DASHBOARD_PORT` override. The request asks for 8000, but `make backend` also uses 8000, so running both at once needs the override. AGENTS.md already documents 8090 for this.
- **The dashboard binds to `127.0.0.1`.** It serves job files (specs, reviews, decisions). Binding to every interface, as the current README command does, would expose them to the local network for no benefit.
- **`make backend` runs both servers in the foreground in one terminal**, not in the background. This matches how they are run today, keeps logs visible and makes Ctrl-C a clean stop. A detached mode would need pid files and a stop target that nobody asked for.
- **`make backend` does not start Keycloak or the web app.** The request lists `docker-up` separately and only names api/ and bff/ for `backend`.
- **`docker-logs` follows (`-f`).** That is the usual reason to run a logs target during development.
- **`help` is the default goal**, so plain `make` is safe and self-documenting instead of starting a server.
