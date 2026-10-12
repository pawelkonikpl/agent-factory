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
- [ ] Add `make dev` so the stack runs on the host with one command: start Keycloak in the background (as `make docker-up`), then run the API, the BFF and the web dev server in one terminal with their logs interleaved, where one Ctrl-C stops all three (as `make backend` does for two); document it in AGENTS.md and README.md next to the other make targets

## Phase 2: Factory tooling

Goal: running, inspecting and cleaning up parallel factory jobs needs no manual git work and no port juggling.

- [ ] Stop factory jobs colliding on port 8000: make the dashboard default to port 8090 (`DASHBOARD_PORT` in the Makefile, the README's `python3 -m http.server` command and the AGENTS.md port-clash note), let `web/vite.config.ts` take the BFF proxy target from an environment variable that defaults to `http://localhost:8000`, and document in AGENTS.md how an agent runs the BFF and the web dev server on its own ports to check the app
- [ ] Add worktree helpers for the factory (jobs already run in their own worktree at ../<name>-factory/<job-id> on branch factory/<job-id>, and factory/jobs/ is already gitignored): `make worktrees` lists the job worktrees with their branch and job stage, `make worktree-clean` removes the worktrees and factory/<job-id> branches already merged into main, and the dashboard job cards show the worktree path from job.json next to the branch

## Phase 3: Observability

Goal: the app reports its traffic, latency, errors and auth activity in a form Prometheus can scrape.

- [ ] Add application metrics: expose a /metrics endpoint (Prometheus format) with request count, latency histogram, error rate and auth login/logout counters, plus a short note on how to scrape it
