# Import the OAuth/OIDC BFF demo (bff, api, keycloak, web)

> Feature: Copy the OAuth/OIDC auth from /Users/pawel/Downloads/oauth-bff-demo into this project: the BFF (bff/: login, logout, CSRF, session store, proxy), the protected API (api/), the Keycloak setup (keycloak/docker-compose.yml, realm-demo.json) and the web login flow (web/), with their tests and .env.example files

## Context

**This repo today.** The worktree holds only the software factory template:
`.claude/` (the `/factory` skill and seven agents), `factory/` (`dashboard.html`,
`backlog.md`), `README.md`, `BUILD_PROMPT.md` and a root `.gitignore` containing
`node_modules/` and `factory/jobs/`. There is no application code, no test
runner and **no `AGENTS.md`/`CLAUDE.md`**. README.md step 4 ("Use it in your
repo") says the agents read setup, dev-server, test, build and lint commands
from `AGENTS.md`, and `.claude/agents/builder.md` and the reviewers start by
reading it. So this job must create it.

**The source** (`/Users/pawel/Downloads/oauth-bff-demo`, no git, no lock files,
no README) is a self-contained, already-tested demo of four parts:

- `bff/` - FastAPI Backend-for-Frontend, an OAuth confidential client (Python
  >=3.11, uv project, `package = false`). Entry point
  `uvicorn app.main:create_app --factory --port 8000`.
  - `app/api/session.py`: `GET /bff/login` (PKCE S256, login cookie, redirect to
    IdP), `GET /bff/callback`, `GET /bff/session`, `POST /bff/logout`
    (refresh-token revocation + RP-initiated logout URL).
  - `app/security.py`: CSRF check (`X-CSRF: 1` header plus Origin and
    Sec-Fetch-Site), `__Host-Http-` prefixed HttpOnly cookies (Strict session,
    Lax login).
  - `app/stores.py`, `app/session_repository.py`: in-memory TTL store, session
    idle/absolute timeouts.
  - `app/api/proxy.py`, `app/services/api_proxy.py`: `/api/*` forwarded to
    `BFF_API_BASE_URL` with the bearer token, header allow-list, dot-segment
    rejection.
  - `app/services/{auth_service,oidc_client,token_service,crypto}.py`.
  - Tests: `tests/{conftest,fake_authorization_server,test_login,test_logout,test_csrf,test_proxy}.py`.
  - `.env.example` (`BFF_` prefix; `BFF_CLIENT_SECRET` has no default, so the
    app will not start without `.env`).
- `api/` - FastAPI resource server (notes per `sub`), JWT verification against
  the issuer's JWKS with audience `demo-api`
  (`app/services/token_verifier.py`). Port 8001. Tests:
  `tests/{conftest,test_notes_api}.py`. `.env.example` (`API_` prefix).
- `keycloak/` - `docker-compose.yml` (Keycloak 26.7.5, `start-dev
  --import-realm`, port 8080, admin/admin) and `realm-demo.json` (realm `demo`,
  confidential client `demo-bff` with redirect URI
  `http://localhost:5173/bff/callback`, audience mapper `demo-api`, users
  alice/alice and bob/bob).
- `web/` - Vite + React 19 + TanStack Query + zod SPA, TypeScript strict. Dev
  server on 5173 (`strictPort`) proxying `/bff` and `/api` to the BFF at
  `http://localhost:8000` (`vite.config.ts`). Login screen
  (`src/components/login-screen.tsx`, maps `?login_error=` codes to messages),
  header with logout, notes panel, and a "what JavaScript can see" panel. All UI
  copy is Polish (`index.html` has `lang="pl"`). Scripts: `dev`, `build`
  (`tsc --noEmit && vite build`), `typecheck`, `preview`. No web tests and no
  `web/.env.example` exist in the source.
- Source root `.gitignore`: `__pycache__/`, `.venv/`, `.pytest_cache/`,
  `.mypy_cache/`, `.ruff_cache/`, `node_modules/`, `dist/`, `.env`.

Both Python projects configure pytest (`asyncio_mode = "auto"`), ruff
(line length 100) and mypy (`strict`, pydantic plugin) in their
`pyproject.toml`. Local toolchain available: uv 0.9, Python 3.13, Node 24,
Docker.

**Port note.** README.md's dashboard instructions (`cd factory && python3 -m
http.server`) default to port 8000, the same port the BFF and the Vite proxy use.

## Requirements

1. Copy `bff/`, `api/`, `keycloak/` and `web/` from
   `/Users/pawel/Downloads/oauth-bff-demo` to the same paths at the repo root,
   file for file and byte for byte, including `bff/.env.example`,
   `api/.env.example`, every `__init__.py`, and all tests. Do not copy generated
   or local-only artifacts (`.venv/`, `node_modules/`, `dist/`, `__pycache__/`,
   `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, any `.env`).
2. Merge the source `.gitignore` entries into the root `.gitignore` (keep the
   existing `node_modules/` and `factory/jobs/` lines; add `__pycache__/`,
   `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `dist/`, `.env`).
   Do not add a second `.gitignore` inside the subprojects.
3. Commit the lock files produced by installing: `bff/uv.lock`, `api/uv.lock`
   and `web/package-lock.json`.
4. Every copied project passes its own checks unchanged:
   `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests` in `bff/`
   and `api/`; `npm run build` in `web/`. If a check fails on the verbatim copy,
   make the smallest fix that makes it pass and list each changed file and the
   reason under a `## Deviations from source` heading in `build.md`. Change
   nothing else in the copied code.
5. Create `AGENTS.md` at the repo root. Keep it short and factual. It must
   cover:
   - Layout: one line each for `bff/`, `api/`, `web/`, `keycloak/`, and the
     factory (`.claude/`, `factory/`).
   - Setup of a fresh checkout: `cp .env.example .env` in `bff/` and `api/`,
     `uv sync` in `bff/` and `api/`, `npm install` in `web/`.
   - Running locally, with ports: `docker compose -f keycloak/docker-compose.yml
     up -d` (8080), API `cd api && uv run uvicorn app.main:create_app --factory
     --port 8001`, BFF `cd bff && uv run uvicorn app.main:create_app --factory
     --port 8000`, web `cd web && npm run dev` (5173). Demo users alice/alice
     and bob/bob, dev only.
   - That the web dev server can run on another port with
     `npm run dev -- --port <port>` for looking at pages, but signing in only
     works on 5173 (the redirect URI registered in `keycloak/realm-demo.json`),
     and the page needs the BFF on 8000 to get past "checking session".
   - That the factory dashboard defaults to port 8000 and collides with the BFF,
     so serve it with `python3 -m http.server 8090` (or any free port) while the
     BFF runs.
   - Validation commands exactly as in requirement 4.
6. Do not edit `README.md`, `BUILD_PROMPT.md`, `.claude/` or `factory/`.

## Acceptance criteria

1. The copy is exact. With the source still at its path, each of these prints
   nothing (or only the files listed under "Deviations from source" in
   build.md):
   ```
   cd <worktree> && for d in bff api web keycloak; do diff -rq -x .venv -x node_modules -x __pycache__ -x .pytest_cache -x .mypy_cache -x .ruff_cache -x dist -x uv.lock -x package-lock.json -x .env /Users/pawel/Downloads/oauth-bff-demo/$d $d; done
   ```
2. The required files are tracked: `git ls-files bff api web keycloak` lists
   `bff/.env.example`, `api/.env.example`, `keycloak/docker-compose.yml`,
   `keycloak/realm-demo.json`, `bff/tests/test_login.py`,
   `bff/tests/test_logout.py`, `bff/tests/test_csrf.py`,
   `bff/tests/test_proxy.py`, `bff/tests/fake_authorization_server.py`,
   `api/tests/test_notes_api.py`, `web/src/components/login-screen.tsx`,
   `bff/uv.lock`, `api/uv.lock` and `web/package-lock.json`.
3. No secrets or local artifacts are tracked:
   `git ls-files | grep -E '(^|/)(\.env|\.venv|node_modules|dist|__pycache__)(/|$)'`
   prints nothing, and
   `git check-ignore bff/.env api/.env bff/.venv web/node_modules web/dist bff/app/__pycache__`
   prints all six paths.
4. BFF tests pass: `cd bff && uv run pytest` exits 0 and reports the tests
   from `test_login.py`, `test_logout.py`, `test_csrf.py` and `test_proxy.py`
   as passed, none skipped.
5. API tests pass: `cd api && uv run pytest` exits 0 with `test_notes_api.py`
   passed, none skipped.
6. Lint and types pass: `uv run ruff check .` and `uv run mypy app tests` exit 0
   in both `bff/` and `api/`.
7. The SPA builds: `cd web && npm install && npm run build` exits 0.
8. The Keycloak setup is valid: `docker compose -f keycloak/docker-compose.yml
   config --quiet` exits 0, and `python3 -m json.tool keycloak/realm-demo.json`
   exits 0. The realm's `demo-bff` redirect URI and secret equal
   `BFF_REDIRECT_URI` and `BFF_CLIENT_SECRET` in `bff/.env.example`.
9. BFF endpoints behave without Keycloak. With `bff/.env` copied from
   `.env.example` and the BFF running on 8000:
   - `curl -s -H 'X-CSRF: 1' http://localhost:8000/bff/session` returns
     `{"authenticated":false,"user":null}`.
   - `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/bff/session`
     (no CSRF header) prints `403`.
   - `curl -s -o /dev/null -w '%{http_code}' -H 'X-CSRF: 1' http://localhost:8000/api/notes`
     prints `401`.
10. The login page renders. With the BFF on 8000 and `cd web && npm run dev`
    (or `npm run dev -- --port <port>`), the root page shows a card headed
    "Notatki" with a "Zaloguj się" button (`data-testid="login-button"`), and
    `/?login_error=access_denied` additionally shows an alert reading
    "Logowanie anulowane – nie udzielono zgody." (`data-testid="login-error"`).
11. End-to-end login works (builder only; needs Docker). With Keycloak, API, BFF
    and web all running as AGENTS.md describes, on http://localhost:5173:
    clicking "Zaloguj się" goes to the Keycloak `demo` realm login; signing in
    as alice/alice returns to the app showing the user name, the "Twoje
    notatki" panel and the token-check panel with `document.cookie` shown as
    "(puste)"; adding a note lists it; "Wyloguj" ends at the login screen again.
    Record what each step showed in build.md.
12. `AGENTS.md` exists at the repo root and contains every item in
    requirement 5: check with
    `grep -nE 'uv run pytest|ruff check|mypy app tests|npm run build|docker compose|--port 8000|--port 8001|5173|8090|cp .env.example .env' AGENTS.md`.
13. Nothing outside the requirement list changed:
    `git diff --stat main...factory/001-oauth-bff-auth -- README.md BUILD_PROMPT.md .claude factory`
    prints nothing.

## Out of scope

- Translating the Polish UI copy, renaming the "demo"/"Notatki" branding, or
  restyling the web app.
- Changing ports, client IDs, realm names, secrets, timeouts or any other
  configuration value from the source, or making the Vite proxy target
  configurable.
- Refactoring, "improving", or reformatting the copied code beyond the minimal
  fixes allowed by requirement 4; upgrading or pinning dependency versions
  beyond what the lock files record.
- Adding a Redis/shared session store, production Keycloak config, HTTPS, CI,
  Dockerfiles for bff/api/web, or a root docker-compose for the whole stack.
- Adding web tests or a JS test runner, or new Python tests.
- Makefile/Taskfile, metrics, or worktree helpers (separate backlog items).
- Editing README.md, BUILD_PROMPT.md, `.claude/`, `factory/dashboard.html` or
  `factory/backlog.md` (the orchestrator checks off the backlog).
- Wiring the factory dashboard into the app, or the app into the factory.

## Assumptions

1. Copy verbatim, including Polish UI text and comments citing RFC numbers.
   Reason: the request says "copy"; translating copy is a product decision.
2. Committed demo credentials (`demo-bff-secret-change-me`, admin/admin,
   alice/alice, bob/bob) stay as in the source. Reason: they are dev-only
   Keycloak fixtures that `.env.example` and the tests rely on. Real secrets
   only ever go in the ignored `.env`.
3. Projects go at the repo root (`bff/`, `api/`, `web/`, `keycloak/`), not
   under a subfolder. Reason: the request names those paths, and the factory
   template is meant to sit at a repo root next to app code.
4. Commit `uv.lock` and `package-lock.json` although the source has none.
   Reason: installs become reproducible, and the builder must leave a clean
   tree after `uv sync` and `npm install`.
5. No `web/.env.example` is created. Reason: the source has none and the SPA
   reads no environment variables.
6. Create `AGENTS.md` instead of extending README.md. Reason: README.md tells
   users to put setup and validation commands there, and every factory agent
   reads it first.
7. Keep the BFF on port 8000 and document the clash with the dashboard's
   default port instead of moving either. Reason: the port is fixed in the
   source's Vite config, `.env.example` and realm, so changing it touches all
   three.

## Changes

Allow the CSS overflow fix in web/src/styles.css from round-1/review-ui.md; list it under Deviations from source. This overrides spec AC1 (byte-identical web/), requirement 4 and the no-restyling out-of-scope item for that one file only. Re-check at 375px and 1280px with a long email and a 200-character unbroken note.
