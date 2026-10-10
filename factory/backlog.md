# Backlog

`/factory next` builds the first unchecked item and checks it off with its job id.

- [ ] Copy the OAuth/OIDC auth from /Users/pawel/Downloads/oauth-bff-demo into this project: the BFF (bff/: login, logout, CSRF, session store, proxy), the protected API (api/), the Keycloak setup (keycloak/docker-compose.yml, realm-demo.json) and the web login flow (web/), with their tests and .env.example files


- [ ] Add a Makefile (or Taskfile) so the dashboard starts with one command, e.g. `make dashboard` serving factory/ on http://localhost:8000/dashboard.html, plus a short note in README.md
- [ ] Add git worktree support for the factory: make sure each job runs in its own worktree (../<name>-factory/<job-id> on branch factory/<job-id>), add helpers (e.g. `make worktrees` to list them, `make worktree-clean` to remove merged/stale ones), gitignore factory/jobs/, and show the worktree path on the dashboard job cards
- [ ] Add application metrics: expose a /metrics endpoint (Prometheus format) with request count, latency histogram, error rate and auth login/logout counters, plus a short note on how to scrape it
