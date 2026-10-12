# React frontend on the BFF, API-only backend

> Feature: Build the React frontend for the app (web/, Vite + React + TypeScript, Polish UI copy) on top of the existing login flow, talking to the backend only through the BFF `/api` proxy. First check whether the backend (bff/ or api/) already serves any frontend or static files (StaticFiles mounts, HTML/template routes, a bundled build, leftover placeholder pages); if it does, remove that code, its tests and its docs, so the backend is API-only and the SPA is served by Vite (dev) or a separate static host. Update README.md and AGENTS.md if the run instructions change

## Context

**Most of this already exists.** Job 001 imported a working SPA into `web/`.
The spec writer checked it against the request and the backend:

**The SPA (`web/`)** is Vite 8 + React 19 + TypeScript (strict) + TanStack Query + zod.
`npm run build` (`tsc --noEmit && vite build`) passes on `main` today.
- `web/vite.config.ts`: dev server on 5173 (`strictPort`). It proxies `/bff` and
  `/api` to the BFF at `http://localhost:8000`, so the SPA and the BFF share one
  origin. Line 8 holds a leftover comment:
  `// In production, put both behind the same reverse proxy or let the BFF serve the SPA.`
  It suggests the BFF could serve the SPA, which goes against this request.
- `web/src/services/bff-client.ts`: `bffRequest()` is the only `fetch` call
  in `web/src`. It sends same-origin relative paths with the `X-CSRF: 1` header.
  `web/src` contains no absolute URLs and makes no other network calls
  (no XHR, EventSource or WebSocket).
- `web/src/services/session-api.ts` covers the login flow: `GET /bff/session`,
  a full-page navigation to `/bff/login?returnTo=`, and `POST /bff/logout`
  followed by navigating to the returned `logout_url`.
- `web/src/services/notes-api.ts` sends all application data through the BFF
  proxy: `GET /api/notes` and `POST /api/notes`. Those are the only routes the
  resource server has (`api/app/api/notes.py`; text is 1 to 500 characters).
- `web/src/hooks/use-session.ts`, `web/src/hooks/use-notes.ts` and
  `web/src/query-client.ts` handle errors. A 401 invalidates the session query,
  which brings back the login screen.
- `web/src/app.tsx` renders the session states: checking, error, login screen,
  or header + notes + token panel.
- Components in `web/src/components/`:
  - `login-screen.tsx` maps `?login_error=` codes to Polish messages.
  - `header-bar.tsx` shows the user name and email and has a "Wyloguj" button.
  - `notes-panel.tsx` has the form, the list, and empty, loading and error states.
  - `token-check.tsx` shows what JavaScript on the page can see.
- All UI copy is Polish, and `index.html` has `lang="pl"`. Styling is plain CSS
  in `web/src/styles.css` (`.card`, `.header`, `.muted`, `.error`).
- **One real gap.** `HeaderBar` calls `useLogout()` (`useMutation({ mutationFn: logout })`)
  and never reads `logout.isError`. If `POST /bff/logout` fails with anything
  other than 401 (for example a 502 when Keycloak is down, or a network error),
  the button re-enables and the user gets no feedback. Compare
  `notes-panel.tsx`, which shows
  `<p className="error">Nie udało się zapisać notatki.</p>` on a failed mutation.
- `web/` has no test runner, only `npm run build`.

**The backend is already API-only.** The spec writer searched `bff/app`,
`api/app`, `bff/tests`, `api/tests` and both `pyproject.toml` files for
`StaticFiles`, `.mount(`, `HTMLResponse`, `FileResponse`, Jinja/templates,
`aiofiles` and `.html`, and found nothing. Neither project has `static/`,
`templates/`, `public/` or `*.html` files. Neither depends on `jinja2` or
`aiofiles`.
- `bff/app/main.py` registers only the `/bff/*` routes (`app/api/session.py`)
  and the `/api/{path}` proxy (`app/api/proxy.py`). It disables `/docs` and
  `/redoc`, and `GET /` returns a JSON 404.
- `api/app/main.py` registers `/notes` and a JSON `/health`. It keeps FastAPI's
  default `/docs`, `/redoc` and `/openapi.json`, which document the API and are
  not a frontend.
- The BFF's redirects (`LOGIN_ERROR_REDIRECT = "/?login_error={code}"` and the
  callback's `return_to`) are relative paths. They land on the SPA because
  the SPA and the BFF share an origin. This is not the BFF serving pages.

The one leftover that mentions the backend serving the frontend is the
`web/vite.config.ts` comment above. There is no backend code or tests to delete.

**Docs.** In `AGENTS.md`, "Layout" has one line per part, with `web/` as "Vite +
React + TypeScript SPA. UI copy is Polish." "Run locally" lists the four dev
commands. `README.md` covers the factory and the `make` targets only. It has no
app run instructions.

**Parallel job.** Job `003-podman-sandbox` is in progress on its own branch and
may touch `Makefile`, `README.md`, `AGENTS.md` and container files. Keep this
job's doc edits small and local to avoid merge conflicts.

## Requirements

1. Leave the backend's API-only state as it is. Add no code, routes,
   dependencies or files to `bff/` or `api/` that serve HTML, static files or a
   built SPA. Change nothing under `bff/` or `api/`.
2. Replace the comment on line 8 of `web/vite.config.ts` so that it no longer
   suggests the BFF serve the SPA. Say instead that in production the built SPA
   (`web/dist/`) is served by a separate static host, and that a reverse proxy
   in front of it routes `/bff` and `/api` to the BFF on the same origin. Make
   no other change to `vite.config.ts`.
3. In `web/src/components/header-bar.tsx`, show a Polish error message when
   logout fails. Use the existing pattern: render
   `<p className="error" role="alert" data-testid="logout-error">Nie udało się wylogować. Spróbuj ponownie.</p>`
   when `logout.isError`. Put it inside the existing `<header className="header">`
   or directly after it, with no new CSS classes, and keep the layout from
   breaking at narrow widths (360px). Leave the message hidden while a retry is
   pending or after a successful retry. TanStack Query resets `isError` when
   the mutation runs again.
4. Leave every other network call in `web/src` as it is. All calls go through
   `bffRequest` in `web/src/services/bff-client.ts` or navigate to `/bff/login`.
   Application data uses `/api/*` (the BFF proxy) and the login flow uses
   `/bff/*`. Add no absolute URLs, no direct calls to the API on 8001 or to
   Keycloak on 8080, and no second `fetch`.
5. In `AGENTS.md`, extend the `web/` line in "Layout" with one or two
   sentences. They must say four things:
   - The SPA is served by the Vite dev server in development.
   - `npm run build` writes a static bundle to `web/dist/` for a separate static
     host, which must share its origin with the BFF (proxying `/bff` and `/api`).
   - The backend (`bff/`, `api/`) serves no frontend files.
   - The SPA talks to the backend only through `/bff/*` (session) and `/api/*`
     (the BFF proxy).

   Change nothing else in `AGENTS.md`.
6. Leave `README.md` unchanged, because the run instructions do not change
   (see Assumptions).
7. Keep all existing validation green: `npm run build` in `web/`, and
   `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests` in both
   `bff/` and `api/`.

## Acceptance criteria

1. **The backend serves no frontend.** From the worktree root:
   `grep -rnE "StaticFiles|HTMLResponse|FileResponse|Jinja2Templates|TemplateResponse|\.mount\(|aiofiles|jinja2" bff/app api/app bff/tests api/tests bff/pyproject.toml api/pyproject.toml`
   prints nothing.
   `find bff api \( -name '*.html' -o -name static -o -name templates -o -name public -o -name dist \) -not -path '*/.venv/*'`
   prints nothing.
2. **Nothing under the backend changed.** `git diff --stat main...HEAD -- bff api`
   prints nothing.
3. **The BFF root is not a page.** With `bff/.env` copied from `.env.example`,
   run `cd bff && uv run uvicorn app.main:create_app --factory --port 8000`.
   Then `curl -s -i http://localhost:8000/` returns status 404 with
   `content-type: application/json`, not HTML.
4. **The vite comment is fixed.** `grep -n "BFF serve" web/vite.config.ts`
   prints nothing. `grep -niE "static host" web/vite.config.ts` prints the new
   comment. `git diff main...HEAD -- web/vite.config.ts` shows only comment
   lines changed.
5. **The SPA uses only the BFF.** `grep -rn "fetch(" web/src` prints exactly
   one line, in `web/src/services/bff-client.ts`.
   `grep -rnE "https?://|localhost|XMLHttpRequest|EventSource|WebSocket" web/src`
   prints nothing. ``grep -rhoE "[\"\`]/(api|bff)/[a-z]+" web/src | sort -u``
   prints exactly four lines, for `/api/notes`, `/bff/logout`, `/bff/session`
   and `/bff/login` (each prefixed by the quote or backtick that opens it).
6. **Logout errors are shown.** `web/src/components/header-bar.tsx` contains
   `logout.isError`, `data-testid="logout-error"`, `role="alert"` and the text
   `Nie udało się wylogować. Spróbuj ponownie.`.
   To check by hand, start the full stack on 5173 (Keycloak, `make backend`,
   `cd web && npm run dev`), sign in as `alice`/`alice`, stop the BFF and click
   "Wyloguj". The red message appears in the header area without overflowing
   at 360px width, and the button becomes clickable again.
7. **The login flow still renders.** With the BFF on 8000 and
   `cd web && npm run dev -- --port <port>`, `/` shows the "Notatki" card with
   the "Zaloguj się" button (`data-testid="login-button"`).
   `/?login_error=access_denied` also shows "Logowanie anulowane – nie udzielono
   zgody." (`data-testid="login-error"`).
8. **All UI copy is Polish.** Every user-visible string added or changed in
   `web/src` is Polish. `web/index.html` still has `lang="pl"`.
9. **AGENTS.md is updated.** The `web/` line in "Layout" mentions `web/dist`,
   a separate static host on the BFF's origin, that `bff/`/`api/` serve no
   frontend files, and `/bff/*` + `/api/*`. `git diff main...HEAD -- AGENTS.md`
   touches only that Layout entry.
10. **README.md is unchanged.** `git diff --stat main...HEAD -- README.md`
    prints nothing.
11. **Validation passes.** `cd web && npm run build` exits 0. In both `bff/` and
    `api/`, `uv run pytest`, `uv run ruff check .` and `uv run mypy app tests`
    exit 0 (34 BFF tests and 10 API tests pass on `main` today).

## Out of scope

- Rewriting, restyling or restructuring the existing SPA, adding a router,
  new pages, or a UI or component library.
- New note features (edit, delete, search, pagination). The API has no routes
  for them, and adding API routes is out of scope.
- Adding a web test runner (Vitest, Playwright) or new Python tests. Nothing
  changes in the backend.
- Removing or disabling FastAPI's `/docs`, `/redoc` and `/openapi.json` on the
  resource server.
- Adding a production static host, an nginx/Caddy config, Containerfiles or
  Makefile targets for the SPA. Job 003 owns container and Makefile work.
- Changing the Vite proxy, ports, `strictPort`, Keycloak redirect URIs, cookie
  settings or CSRF handling.
- Adding a "retry" button to the "Nie udało się sprawdzić sesji." state, or any
  other UX polish beyond the logout error.
- Editing `.claude/`, `factory/` or `BUILD_PROMPT.md`.

## Assumptions

- **"Build the React frontend" means finishing and checking the existing SPA,
  not rebuilding it.** `web/` already covers every endpoint the API and the BFF
  expose, in Polish, using only the BFF. A rewrite would add risk for no
  benefit. The approver should escalate if the human wanted a larger feature set.
- **"Only through the BFF `/api` proxy" covers application data.** The existing
  login flow necessarily uses the BFF's own `/bff/*` session endpoints, and the
  request says to build "on top of the existing login flow".
- **The logout error message is the one functional change.** It is the only
  place where a failed request gives the user no feedback at all. That is a
  defect in the login-flow UI, not an extra feature.
- **The resource server's Swagger `/docs` is not a "frontend" to remove.** It
  documents the API and has nothing to do with the SPA. Browsers cannot reach
  it through the BFF anyway, because `/api/*` requires the `X-CSRF` header and
  a session.
- **The run instructions do not change, so README.md stays untouched.** The
  request makes README/AGENTS updates conditional on that. The AGENTS.md
  Layout note records the API-only and static-host split so later agents don't
  reintroduce SPA serving in the BFF.
