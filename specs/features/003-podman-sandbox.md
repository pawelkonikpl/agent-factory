# Run the stack under rootless Podman, with a one-command sandbox

> Feature: Run the whole project in a sandbox with Podman instead of Docker: make Keycloak (keycloak/docker-compose.yml) run under rootless Podman (`podman compose` / podman-compose), optionally containerize api/, bff/ and web/ (Containerfiles) so the full stack starts in an isolated sandbox with one command, update the Makefile (e.g. `make podman-up` / `make podman-down` / `make podman-logs`, or switch the docker-* targets to a `CONTAINER_ENGINE` variable defaulting to podman), and update README.md and AGENTS.md

## Context

- `keycloak/docker-compose.yml`: one service, `keycloak`, image
  `quay.io/keycloak/keycloak:26.7.5` (already fully qualified, which Podman's
  short-name rules need), `start-dev --import-realm`, admin `admin`/`admin`, port
  `8080:8080`, and `./realm-demo.json` bind-mounted read-only into
  `/opt/keycloak/data/import/`. Nothing in it is Docker-specific.
- `Makefile` (root): `COMPOSE = docker compose -f keycloak/docker-compose.yml` and
  targets `docker-up` (`$(COMPOSE) up -d`), `docker-down`, `docker-logs`
  (`logs -f`), plus `help`, `dashboard`, `backend`. `make help` prints every
  target that has a `## ` comment using `printf "  %-12s %s\n"`. The file says it
  must work with GNU Make 3.81 (macOS).
- `bff/` and `api/`: FastAPI apps run with uv
  (`uv run uvicorn app.main:create_app --factory --port 8000` / `--port 8001`).
  Dependencies are in `pyproject.toml` + `uv.lock` (`[tool.uv] package = false`,
  `requires-python >= 3.11`, a `dev` dependency group). Settings come from env
  vars or a `.env` file in the working directory (`bff/app/config.py`, prefix
  `BFF_`; `api/app/config.py`, prefix `API_`). `bff/.env.example` and
  `api/.env.example` hold the dev values; `BFF_CLIENT_SECRET` has no default and
  must be set. `.env` files are git-ignored and hold secrets.
- Every URL in the config is `localhost`: issuer `http://localhost:8080/realms/demo`
  (both apps fetch `<issuer>/.well-known/openid-configuration` and require its
  `issuer` to match exactly: `bff/app/services/oidc_client.py`,
  `api/app/services/token_verifier.py`), `BFF_API_BASE_URL=http://localhost:8001`,
  redirect URI `http://localhost:5173/bff/callback` (the only one registered in
  `keycloak/realm-demo.json`).
- `web/`: Vite 8 + React. `web/vite.config.ts` serves on 5173 (`strictPort`) and
  proxies `/bff` and `/api` to `http://localhost:8000`. Vite 8 needs Node
  `^20.19.0 || >=22.12.0` (`web/package-lock.json`). Lockfile exists, so
  `npm ci` works.
- Because the browser, the BFF and the API all use `localhost:8080` for
  Keycloak, the containers must see Keycloak, the BFF and the API on `localhost`
  as well, or the issuer check and the redirect URI break. The way to get that
  without touching app code or config is one shared network namespace: the
  `keycloak` service owns the namespace and publishes the ports, and `api`,
  `bff` and `web` join it with `network_mode: "service:keycloak"`. Both compose
  providers `podman compose` can delegate to (docker-compose and podman-compose)
  support this.
- Podman 5.8 and both podman-compose and docker-compose are installed on this
  machine. On macOS Podman runs in a VM (`podman-machine-default`), which must be
  started with `podman machine start` before any `podman` command works.
- Docs: `AGENTS.md` "Run locally" lists
  `docker compose -f keycloak/docker-compose.yml up -d` and describes the make
  targets; `README.md` "Dashboard" section has a short note on `make dashboard`
  and `make help`.

## Requirements

1. `keycloak/docker-compose.yml` starts Keycloak under rootless Podman with
   `podman compose -f keycloak/docker-compose.yml up -d`, and still works with
   `docker compose`. Keep the file name and the service as they are; change it
   only if Podman needs a change to run it.
2. Add `api/Containerfile` and `bff/Containerfile` that:
   - start `FROM` a fully qualified, version-pinned image (registry included,
     e.g. `docker.io/library/python:3.12-slim`; uv from a pinned
     `ghcr.io/astral-sh/uv` tag or installed at a pinned version);
   - copy only what the app needs to run (`pyproject.toml`, `uv.lock`, `app/`),
     never `.env`, `.venv` or `tests/`;
   - install with `uv sync --frozen --no-dev` at build time;
   - run as a non-root user;
   - start with the same uvicorn command and port as AGENTS.md
     (`app.main:create_app --factory`, port 8001 for the API, 8000 for the BFF),
     run from the virtualenv built into the image, with no dependency sync or
     download at container start.
3. Add `web/Containerfile` that starts from a fully qualified, version-pinned
   Node image that satisfies Vite 8 (e.g. `docker.io/library/node:22-slim`),
   installs with `npm ci` inside the image (never copies the host's
   `node_modules`), copies only the files the dev server needs (`package.json`,
   `package-lock.json`, `index.html`, `tsconfig.json`, `vite.config.ts`, `src/`),
   runs as a non-root user, and starts `npm run dev -- --host 0.0.0.0` so the
   published port reaches it. `web/vite.config.ts` stays unchanged.
4. Add a `.dockerignore` in each of `api/`, `bff/` and `web/` that keeps `.env`,
   `.venv`, `node_modules`, `dist` and the tool caches (`__pycache__`,
   `.pytest_cache`, `.mypy_cache`, `.ruff_cache`) out of the build context.
5. Add a root `compose.yaml` for the sandbox with four services:
   - `keycloak`: the same image, command, environment and read-only realm
     mount as `keycloak/docker-compose.yml` (realm path relative to the root,
     `./keycloak/realm-demo.json`). It owns the network namespace and is the
     only service with `ports`, publishing exactly `127.0.0.1:8080:8080` and
     `127.0.0.1:5173:5173`.
   - `api`, `bff`, `web`: `build` from `./api`, `./bff`, `./web` with
     `dockerfile: Containerfile`, `network_mode: "service:keycloak"`, and
     `depends_on: [keycloak]`.
   - `api` and `bff` get their settings with `env_file: ./api/.env.example` and
     `env_file: ./bff/.env.example`. No new secrets or duplicated config
     values in `compose.yaml`.
   - No bind mounts other than the realm file. Ports 8000 and 8001 are not
     published.
   - A header comment in the same style as `keycloak/docker-compose.yml`
     saying it is for local development only and uses the demo passwords and
     secrets.
6. `Makefile`:
   - Add `CONTAINER_ENGINE ?= podman` and build `COMPOSE` from it:
     `COMPOSE = $(CONTAINER_ENGINE) compose -f keycloak/docker-compose.yml`.
   - Keep the `docker-up`, `docker-down` and `docker-logs` target names and
     commands, now running through `$(CONTAINER_ENGINE)`. Update their `## `
     help text so it says they control Keycloak and honour `CONTAINER_ENGINE`
     (default podman).
   - Add `SANDBOX = $(CONTAINER_ENGINE) compose -f compose.yaml` and targets
     `sandbox-up` (`$(SANDBOX) up -d --build`, then echo the URL
     `http://localhost:5173`), `sandbox-down` (`$(SANDBOX) down`) and
     `sandbox-logs` (`$(SANDBOX) logs -f`), each with a `## ` help line.
   - Add the new targets to `.PHONY`. Stay compatible with GNU Make 3.81.
7. `AGENTS.md`:
   - "Layout": mention the Containerfiles in `api/`, `bff/`, `web/` and the
     root `compose.yaml` sandbox.
   - "Run locally": the Keycloak line uses
     `podman compose -f keycloak/docker-compose.yml up -d`, and says Docker works
     too (`docker compose ...` or `make docker-up CONTAINER_ENGINE=docker`).
   - A short "Sandbox" section: prerequisites (Podman with a compose provider;
     on macOS `podman machine start` first), `make sandbox-up` /
     `sandbox-logs` / `sandbox-down`, what runs where (open
     http://localhost:5173, Keycloak on 8080, BFF and API not published), that
     it uses the `.env.example` values and not `bff/.env`/`api/.env`, that code
     changes need `make sandbox-up` again (images are rebuilt; no live reload),
     that the first login may fail until Keycloak has finished starting
     (watch `make sandbox-logs`), and that it cannot run at the same time as
     the host-run Keycloak or `npm run dev` on 5173 (same ports).
   - Update the make-targets paragraph to mention `CONTAINER_ENGINE` and the
     sandbox targets.
8. `README.md`: extend the existing make note in the "Dashboard" section by
   one or two sentences saying `make sandbox-up` runs the demo app's full stack
   under Podman (see AGENTS.md). Nothing more.
9. No changes to application code or config: `bff/app/`, `api/app/`,
   `web/src/`, `web/vite.config.ts`, the `.env.example` files and
   `keycloak/realm-demo.json` stay as they are.

## Acceptance criteria

Run the container checks with the Podman machine started (`podman machine start`)
and with nothing else listening on 5173 or 8080.

1. `make help` lists `docker-up`, `docker-down`, `docker-logs`, `sandbox-up`,
   `sandbox-down` and `sandbox-logs`, each with a description, and the columns
   line up.
2. `make -n docker-up` prints `podman compose -f keycloak/docker-compose.yml up -d`;
   `make -n docker-up CONTAINER_ENGINE=docker` prints
   `docker compose -f keycloak/docker-compose.yml up -d`.
3. `make -n sandbox-up` prints `podman compose -f compose.yaml up -d --build`;
   `make -n sandbox-down` and `make -n sandbox-logs` print the matching
   `down` and `logs -f` commands.
4. `make docker-up`, then (after Keycloak has started)
   `curl -s http://localhost:8080/realms/demo/.well-known/openid-configuration`
   returns JSON whose `issuer` is `http://localhost:8080/realms/demo`.
   `make docker-down` then leaves no Keycloak container in `podman ps -a`.
5. `make sandbox-up` on a clean state builds the three images and starts four
   containers; `podman ps --format '{{.Names}} {{.Status}} {{.Ports}}'` shows
   all four running, and the only published ports are `127.0.0.1:8080->8080`
   and `127.0.0.1:5173->5173`.
6. With the sandbox running and Keycloak started,
   `curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://localhost:5173/bff/login`
   prints `302` and a URL that starts with
   `http://localhost:8080/realms/demo/protocol/openid-connect/auth`
   (web proxies to the BFF, and the BFF reaches Keycloak's discovery document).
7. In a browser at http://localhost:5173 (sandbox running): sign in as
   `alice`/`alice`, the app shows the signed-in user, creating a note makes it
   appear in the list (BFF to API to Keycloak JWKS all work), and logging out
   returns to the signed-out page.
8. `podman compose -f compose.yaml exec api id -u`, and the same for `bff` and
   `web`, each print a non-zero uid.
9. No `.env` and no host `node_modules` reach the images: `api/Containerfile`,
   `bff/Containerfile` and `web/Containerfile` copy only the files listed in
   Requirements 2 and 3, each of `api/.dockerignore`, `bff/.dockerignore`,
   `web/.dockerignore` lists `.env`, and
   `podman compose -f compose.yaml exec bff sh -c 'ls -a'` in the app directory
   shows no `.env`.
10. `make sandbox-logs` follows the four services' logs until Ctrl-C;
    `make sandbox-down` stops and removes all four containers (none left in
    `podman ps -a`).
11. `git diff main --stat` shows no changes under `bff/app/`, `api/app/`,
    `web/src/`, nor to `web/vite.config.ts`, `bff/.env.example`,
    `api/.env.example` or `keycloak/realm-demo.json`.
12. `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests` pass in
    `bff/` and in `api/`; `npm run build` passes in `web/`.
13. `AGENTS.md` contains `make sandbox-up`, `CONTAINER_ENGINE`,
    `podman machine start` and
    `podman compose -f keycloak/docker-compose.yml up -d`; `README.md` contains
    `make sandbox-up`.

## Out of scope

- Production images: multi-stage size tuning, a production web build, serving
  the SPA from the BFF, TLS, a real database.
- Live reload or bind-mounting source code into the containers.
- Healthchecks or `depends_on` conditions waiting for Keycloak readiness.
- Any change to app code, settings defaults, `vite.config.ts`, the realm or the
  `.env.example` files (no new "internal issuer" or discovery URL settings).
- Renaming `keycloak/docker-compose.yml` or the `docker-*` targets, or removing
  Docker support.
- Changing `make backend` or `make dashboard`.
- Changing the port binding in `keycloak/docker-compose.yml`.
- Kubernetes / `podman kube play` / quadlets, CI, pushing images to a registry.
- Podman installation scripts or `podman machine init` automation.

## Assumptions

- Full stack is containerized, not just Keycloak: the request's headline is
  "run the whole project in a sandbox", and "one command" needs it.
- Shared network namespace (`network_mode: service:keycloak`) instead of a
  compose network: every service keeps using `localhost`, so the issuer, the
  redirect URI and the Vite proxy work with no code or config change.
- Kept the `docker-*` target names and made them engine-agnostic with
  `CONTAINER_ENGINE` (default podman), and named the full-stack targets
  `sandbox-*` instead of `podman-*`: they also honour `CONTAINER_ENGINE`, so a
  `podman-` name would be wrong with Docker, and existing habits and docs keep
  working.
- The sandbox reads `.env.example`, not `.env`: a fresh checkout must start
  with one command, and the example values are already correct for the
  sandbox.
- Published ports bind to `127.0.0.1` only: a sandbox with `admin`/`admin`
  Keycloak should not be reachable from the LAN.
- Ignore files are named `.dockerignore`, not `.containerignore`: Podman reads
  both, while docker-compose (which `podman compose` may delegate to) reads only
  `.dockerignore`.
- The root `compose.yaml` repeats the Keycloak service rather than using
  `extends` or multi-file merges: list merging (`ports`) differs between
  docker-compose and podman-compose, and the block is ten lines.
- Verified on macOS with the Podman machine; no SELinux `:z` relabel option is
  added unless Podman needs it to read the realm file on this machine.
