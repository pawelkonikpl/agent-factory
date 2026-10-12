# Makefile targets for the web app (`make web`, `make web-build`)

> Feature: Add a `make web` target to the root Makefile that starts the web dev server (cd web && npm run dev, port 5173), and a `make web-build` target running npm run build; list them in `make help`, and document them in README.md and AGENTS.md next to the other make targets.

## Context

- The root `Makefile` (added by job 002) has the targets `help`, `dashboard`, `backend`, `docker-up`, `docker-down` and `docker-logs`, all listed in one `.PHONY` line. It must work with GNU Make 3.81 (macOS `/usr/bin/make`), as its first-line comment says.
- `make help` is the default goal (first target). It builds its list by grepping `$(MAKEFILE_LIST)` for lines matching `^[a-zA-Z_-]+:.*## ` and printing the name padded to 12 columns plus the `## ` description. So a new target appears in `make help` as soon as its rule line carries a `## description` comment; `web-build` (9 chars) fits the padding and matches the regex.
- The web app is in `web/`. `web/package.json` scripts: `dev` = `vite`, `build` = `tsc --noEmit && vite build` (output `web/dist/`, git-ignored by `dist/` in the root `.gitignore`). `web/vite.config.ts` fixes the dev server to port 5173 with `strictPort: true` and proxies `/bff` and `/api` to the BFF on 8000. So `npm run dev` already serves on 5173 with no extra flag. Both commands need `web/node_modules` from `cd web && npm install` ("Setup" in `AGENTS.md`).
- `AGENTS.md`, "Run locally": lists the raw command `cd web && npm run dev  # web, port 5173`, then a paragraph (lines 38-40): "The root `Makefile` wraps these: `make docker-up` (also `docker-down`, `docker-logs`), `make backend` (...) and `make dashboard`. `make help` lists every target." "Validation" lists `npm run build` in `web/`.
- `README.md`, "Dashboard" section (lines 89-91): "In this repo, `make dashboard` does the same from the repo root (...), and `make help` lists the other targets." This is the only place README mentions make targets.

## Requirements

1. In the root `Makefile`, add two targets, both added to the existing `.PHONY` line:
   - `web`: runs `cd web && npm run dev` in the foreground until Ctrl-C. Its `## ` description says it starts the web dev server on port 5173.
   - `web-build`: runs `cd web && npm run build`. Its `## ` description says it builds the web app (type check plus production build into `web/dist/`).
   Each rule line carries a `## description` so the existing `help` target lists it. Do not change the `help` recipe. Place the two targets after `backend` and before the `docker-*` targets. Keep GNU Make 3.81 compatibility.
2. `make web` does not pass `--port`; the port comes from `web/vite.config.ts`.
3. A failing `npm run build` makes `make web-build` exit non-zero (the default behaviour of a plain recipe line; do not swallow errors).
4. `AGENTS.md`, "Run locally": extend the existing "The root `Makefile` wraps these" paragraph to mention `make web` (web dev server, port 5173) and `make web-build` (runs `npm run build` in `web/`). Keep the raw commands and the other text as they are.
5. `README.md`, "Dashboard" section: extend the existing "In this repo, `make dashboard` ..." sentence/paragraph so it also names `make web` (web dev server) and `make web-build` (production build of `web/`), next to `make dashboard` and `make help`. Keep it short and keep the `python3 -m http.server` instructions.

## Acceptance criteria

1. `make help` (and plain `make`) run from the repo root exit 0 and print `web` and `web-build`, each with a description, alongside the six existing targets. Verify by running both.
2. `make -n web` prints `cd web && npm run dev` (no `--port`), and `make -n web-build` prints `cd web && npm run build`. Both exit 0.
3. `grep -n '^.PHONY' Makefile` shows `web` and `web-build` in the `.PHONY` list.
4. After `cd web && npm install`, `make web-build` from the repo root exits 0 and `web/dist/index.html` exists.
5. With `web/node_modules` installed and port 5173 free, `make web` from the repo root starts Vite: `curl -s -o /dev/null -w '%{http_code}' http://localhost:5173/` returns `200`. After Ctrl-C in that terminal, `lsof -nP -iTCP:5173 -sTCP:LISTEN` prints nothing.
6. `grep -n "make web" AGENTS.md` matches in the "Run locally" paragraph that starts "The root `Makefile` wraps these", and both `make web` and `make web-build` appear there. The raw `cd web && npm run dev` command is still listed.
7. `grep -n "make web" README.md` matches in the "Dashboard" section, next to `make dashboard` and `make help`, and both `make web` and `make web-build` appear. `cd factory && python3 -m http.server` is still there.
8. `git diff --stat main` lists only `Makefile`, `README.md` and `AGENTS.md` (`web/dist/` is git-ignored and must not be committed).
9. Existing validation still passes as a sanity check: `cd web && npm run build`, and in `bff/` and `api/`: `uv run pytest`, `uv run ruff check .`, `uv run mypy app tests`.

## Out of scope

- A `WEB_PORT` variable or any port override for `make web`; `AGENTS.md` already documents `cd web && npm run dev -- --port <port>` for that.
- An `install`/`web-install` target, or running `npm install` automatically inside `web`/`web-build`.
- Other targets (`dev`, `all`, `test`, `lint`, `typecheck`, `preview`, `clean`), or making `backend` also start the web server.
- Changing the `help` recipe, existing targets, `web/package.json`, `web/vite.config.ts` or any application code.
- Removing raw commands from README.md or AGENTS.md, rewriting the "Validation" section, or adding new README sections.

## Assumptions

- **README mention goes in the "Dashboard" section paragraph.** It is the only place README lists make targets today, and the request says "next to the other make targets".
- **AGENTS.md mention goes only in the "Run locally" make paragraph**, not also in "Validation". That paragraph is where the other targets are listed; the request asks for nothing more.
- **`make web` relies on `vite.config.ts` for port 5173** instead of passing `--port 5173`, so the port is defined in one place.
- **No dependency check or auto-install.** Matches the existing targets (`backend` does not run `uv sync` either); setup stays in "Setup" in AGENTS.md.
