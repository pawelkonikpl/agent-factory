# PostgreSQL in all three run modes

> Feature: Run PostgreSQL in all three run modes: a pinned `postgres` service (database, user and password `emailsender`, no volume, a `pg_isready` healthcheck) in `keycloak/docker-compose.yml` (published on 127.0.0.1:5432), `compose.yaml` and `.devcontainer/compose.yaml` (in keycloak's network namespace, not published, `api`/`dev` wait for it), `API_DATABASE_URL` in `api/.env.example`, documented in AGENTS.md, with no `api/` code, as specified in `specs/email-sender/backend.md` API-1 (covers B12, run-mode part)

## Context

This is roadmap item API-1 of Phase 4 (Email Sender API). The source of truth is
`specs/email-sender/backend.md`, section "API-1: PostgreSQL in all three run modes"
(Goal, Requirements, Pitfalls, Acceptance criteria). It only provides the database
server; API-2 makes the API connect to it.

The three run modes today:

- **Host**, `keycloak/docker-compose.yml`: one `keycloak` service
  (`quay.io/keycloak/keycloak:26.7.5`, `ports: "8080:8080"`), header comment
  "Keycloak for local development only ...". Run by `make docker-up` /
  `docker-down` / `docker-logs` in the root `Makefile`
  (`COMPOSE = $(CONTAINER_ENGINE) compose -f keycloak/docker-compose.yml`); their
  `## ` help texts say "Start Keycloak (port 8080) ...", "Stop and remove Keycloak
  ...", "Follow Keycloak's logs ...".
- **Sandbox**, root `compose.yaml`: `keycloak` owns the network namespace and
  publishes `127.0.0.1:8080` and `127.0.0.1:5173`; `api`, `bff` and `web` join it
  with `network_mode: "service:keycloak"` and `depends_on: [keycloak]` (list form).
  `api` uses `env_file: ./api/.env.example`. The header comment explains the shared
  namespace. Built in job 003 (`specs/features/003-podman-sandbox.md`).
- **Dev container**, `.devcontainer/compose.yaml`: `keycloak` (nothing published) and
  `dev` (`network_mode: "service:keycloak"`, `depends_on: [keycloak]`).
  `.devcontainer/podman/compose.yaml` extends it with `keep-id` and
  `label=disable` for the bind-mounted services only. `.devcontainer/devcontainer.json`
  forwards 5173 and 8080; `.devcontainer/post-start.sh` starts the servers.

`api/.env.example` holds `API_ISSUER` and `API_AUDIENCE`. `api/app/config.py` uses
`SettingsConfigDict(env_prefix="API_", env_file=".env", extra="ignore")`, so an
unknown `API_DATABASE_URL` does not stop the API from starting.

`specs/mission.md` requires everything the repo starts to listen on 127.0.0.1 only.
The repo uses fully qualified image names everywhere (Podman short-name rules).

Docs: `AGENTS.md` "Layout", "Run locally", "Sandbox" and "Dev container" describe
these modes; `README.md` (around line 135) says the sandbox runs "Keycloak, API, BFF
and web" and the dev container comes "with Keycloak".

## Requirements

1. A `postgres` service, identical in all three compose files apart from networking:
   - `image: docker.io/library/postgres:18.6`;
   - `environment`: `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD` all
     `emailsender`;
   - no volume and no bind mount;
   - `healthcheck`: test `pg_isready -U emailsender -d emailsender` (CMD form),
     `interval: 10s`, `timeout: 5s`, `retries: 5`, `start_period: 10s`.
2. `keycloak/docker-compose.yml`: add the service with `ports: ["127.0.0.1:5432:5432"]`.
   Update the header comment to say it runs Keycloak and PostgreSQL, dev only (demo
   credentials, no persistent data).
3. `compose.yaml`: add the service with `network_mode: "service:keycloak"` and
   `depends_on: [keycloak]`, no `ports`. Change `api`'s `depends_on` to the map form:
   `keycloak: {condition: service_started}` and `postgres: {condition: service_healthy}`.
   `bff` and `web` are unchanged. Update the header comment to mention PostgreSQL
   (in the shared namespace on 5432, not published).
4. `.devcontainer/compose.yaml`: add the service with `network_mode: "service:keycloak"`
   and `depends_on: [keycloak]`, no `ports`. Change `dev`'s `depends_on` to the map
   form: `keycloak: {condition: service_started}`, `postgres: {condition: service_healthy}`.
   Update the header comment to mention PostgreSQL. `.devcontainer/podman/compose.yaml`
   and `.devcontainer/devcontainer.json` stay unchanged (no bind mount, so no
   `label=disable`; 5432 is not forwarded).
5. `api/.env.example`: add a one-line comment and
   `API_DATABASE_URL=postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender`.
6. `Makefile`: the `docker-up`, `docker-down` and `docker-logs` help texts mention
   PostgreSQL (port 5432) next to Keycloak, for example
   "Start Keycloak (port 8080) and PostgreSQL (port 5432) in the background ...".
7. `AGENTS.md`:
   - "Layout": `keycloak/` runs Keycloak and PostgreSQL (dev only); `.devcontainer/`
     is the dev container plus Keycloak and PostgreSQL.
   - "Run locally": the Keycloak compose command also starts PostgreSQL on
     127.0.0.1:5432 (database, user and password `emailsender`); a PostgreSQL already
     running on the host on 5432 clashes and has to be stopped first.
   - "Sandbox": a fifth service, `postgres`, not published; `api` starts once it is
     healthy.
   - "Dev container": PostgreSQL runs as a third container sharing the network, so
     `localhost:5432` inside it is PostgreSQL; an existing dev container must be
     rebuilt to get it ("Dev Containers: Rebuild Container").
8. `README.md`: the sentence listing the sandbox services and the dev container's
   companions mentions PostgreSQL.
9. No change under `api/` other than `api/.env.example`; no change under `bff/` or `web/`;
   no new dependency.

## Acceptance criteria

1. `podman compose -f keycloak/docker-compose.yml config`, `podman compose -f compose.yaml config`
   and `podman compose -f .devcontainer/compose.yaml config` (or the `docker compose`
   equivalents) all parse without error and each lists a `postgres` service with image
   `docker.io/library/postgres:18.6`, the three `emailsender` variables, the healthcheck
   from Requirement 1 and no volumes.
2. `make docker-up` starts Keycloak and PostgreSQL;
   `podman compose -f keycloak/docker-compose.yml exec postgres pg_isready -U emailsender -d emailsender`
   prints "accepting connections"; `podman port` on the postgres container shows 5432
   bound to `127.0.0.1` only. Same with `CONTAINER_ENGINE=docker` where Docker is
   available. `make docker-down` removes both.
3. `make sandbox-up` starts five services; `podman compose exec postgres pg_isready -U emailsender -d emailsender`
   succeeds; `podman compose ps` shows no published 5432; `api` started only after
   `postgres` was healthy (visible in `podman compose ps`/logs order); sign-in as
   `alice`/`alice` and the notes demo still work on http://localhost:5173.
4. In `compose.yaml` `api` and in `.devcontainer/compose.yaml` `dev`, `depends_on`
   names `postgres` with `condition: service_healthy` and `keycloak` with
   `condition: service_started`; neither file has a `ports` entry on `postgres`.
5. Inside a rebuilt dev container, `bash -c '</dev/tcp/127.0.0.1/5432' && echo open`
   prints `open`, and `/tmp/dev-backend.log` and `/tmp/dev-web.log` show the servers up.
   (Where no Dev Containers client is available,
   `npx @devcontainers/cli up --workspace-folder .` is enough.)
6. `grep API_DATABASE_URL api/.env.example` prints the exact line from Requirement 5,
   preceded by a comment line.
7. `make help` shows PostgreSQL (port 5432) in the `docker-up`, `docker-down` and
   `docker-logs` lines.
8. `AGENTS.md` documents PostgreSQL in "Layout", "Run locally" (127.0.0.1:5432,
   `emailsender` credentials, the 5432 clash), "Sandbox" (fifth service, not published,
   `api` waits for health) and "Dev container" (third container, `localhost:5432`,
   rebuild needed). `README.md` mentions PostgreSQL alongside Keycloak.
9. `git diff --stat main` touches only `keycloak/docker-compose.yml`, `compose.yaml`,
   `.devcontainer/compose.yaml`, `api/.env.example`, `Makefile`, `AGENTS.md`,
   `README.md` and the job's spec file.
10. In `api/` and `bff/`: `uv run pytest`, `uv run ruff check .` and
    `uv run mypy app tests` pass; in `web/`: `npm run build` passes.

## Out of scope

- Any `api/` code: SQLAlchemy, asyncpg, Alembic, a `database_url` setting in
  `api/app/config.py`, a test database or fixtures (all API-2).
- A named volume or any persistence for PostgreSQL.
- Publishing or forwarding 5432 in the sandbox or the dev container
  (`devcontainer.json` `forwardPorts` stays 5173 and 8080).
- smtp4dev or any other service (API-8).
- Changing `.devcontainer/podman/compose.yaml`, the Containerfiles or `post-start.sh`.
- Making `bff` or `web` wait for PostgreSQL.

## Assumptions

- README.md gets a one-phrase update even though backend.md API-1 lists only AGENTS.md:
  its sentence enumerating the sandbox services and the dev container's companions would
  otherwise be wrong.
- The healthcheck uses the CMD form (`["CMD", "pg_isready", ...]`): it needs no shell and
  behaves the same under docker-compose and podman-compose.
- The Makefile help-text change is required although the request line does not name it:
  backend.md API-1, which the request points to, lists it.
- Docker-engine checks in criterion 2 run only where Docker is installed; Podman is the
  default engine and is the required check.
