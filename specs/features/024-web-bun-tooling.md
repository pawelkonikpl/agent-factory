# Replace npm with bun in `web/`

> Feature: Replace npm with bun for `web/` in every run mode: `bun.lock` replaces the old lockfile, a pinned `oven/bun` image in `web/Containerfile`, bun in the dev container image and `post-create.sh`, `bun run` in the Makefile, bun commands in AGENTS.md, with no app code change, as specified in `specs/email-sender/frontend.md` UI-1 (covers F0, tooling part)

## Context

The full item is `specs/email-sender/frontend.md`, section "UI-1: Replace npm with bun in `web/`"
(Requirements, Pitfalls, Acceptance criteria). It rests on `specs/email-sender/README.md` §3.4
and decision D16: bun, with one lockfile `bun.lock`, no npm commands left, and Node kept in the
dev container. It also closes defect W-18 (one lockfile). This is the first item of Phase 5.
UI-2 adds `bun run test` later.

How `web/` is installed and run today, with npm:

- `web/package.json` has the scripts `dev` = `vite`, `build` = `tsc --noEmit && vite build`,
  `typecheck` and `preview`. It has no `packageManager` field.
- `web/package-lock.json` (lockfileVersion 3, 52 packages) pins the direct dependencies at:
  react 19.3.0, react-dom 19.3.0, @tanstack/react-query 5.104.1, zod 4.6.5, @types/react 19.3.0,
  @types/react-dom 19.3.0, @vitejs/plugin-react 6.1.2, typescript 6.0.3 and vite 8.3.4.
- `web/Containerfile` is the sandbox image, from 003-podman-sandbox:
  - it starts `FROM docker.io/library/node:22-slim`;
  - the `node` user owns `/app`, because Vite writes `node_modules/.vite`;
  - it runs `COPY --chown=node:node package.json package-lock.json ./` and then `RUN npm ci`;
  - it copies `index.html`, `tsconfig.json`, `vite.config.ts` and `src`;
  - it ends with `CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]`.

  `web/.dockerignore` already keeps `node_modules`, `dist` and `.env` out of the build.
- `web/vite.config.ts` binds the dev server to 127.0.0.1 on port 5173 (strictPort) and proxies
  `/bff` and `/api` to the BFF on 8000. It stays as it is.
- `.devcontainer/Containerfile` starts from `mcr.microsoft.com/devcontainers/python:1-3.12-bookworm`
  (Debian, glibc) and adds uv with `COPY --from=ghcr.io/astral-sh/uv:0.9.10 /uv /bin/uv`. bun
  should come in the same way. Node 22 is a devcontainer feature in `.devcontainer/devcontainer.json`
  and `.devcontainer/podman/devcontainer.json`, and it stays.
- `.devcontainer/post-create.sh` ends with `(cd web && npm ci)`.
- `.devcontainer/post-start.sh` starts `make web` unless `pgrep -f "node_modules/.bin/vite"`
  finds a running server. If one is running, it prints `already running: node_modules/.bin/vite`.
- `Makefile`: `web` runs `cd web && npm run dev` and `web-build` runs `cd web && npm run build`
  (from 005-makefile-web-target). Their `## ` help texts don't mention npm.
- `AGENTS.md` mentions npm or npx in these places:
  - "Layout": `npm run build` writes the bundle.
  - "Setup": `cd web && npm install`.
  - "Run locally": `cd web && npm run dev`, "`make web-build` (runs `npm run build` in `web/`)"
    and `cd web && npm run dev -- --port <port>`.
  - "Sandbox": "`npm run dev` (`make web`)" in the port clash note.
  - "Dev container": the intro lists "uv, Node 22"; setup runs `uv sync --frozen` and `npm ci`;
    there is a `npx @devcontainers/cli up …` line, and the rebuild note covers only PostgreSQL
    and smtp4dev.
  - "Validation": `npm run build`.

  `git grep` finds npm or npx in no other tracked file outside `specs/`: `README.md`, `.claude/`
  and `factory/` have none.
- This job reverses some earlier decisions. 001-oauth-bff-auth committed `web/package-lock.json`.
  003-podman-sandbox chose a Node image with `npm ci` and `npm run dev -- --host 0.0.0.0`.
  004-react-frontend and 005-makefile-web-target used `npm run dev` and `npm run build`. Those
  specs are history and stay unchanged.
- While writing this spec, I tried bun 1.4.3 (from the npm `bun` package) on a copy of `web/`:
  - With `package-lock.json` present, `bun install` prints "migrated lockfile from
    package-lock.json". It writes a text `bun.lock` with the same 52 packages and the versions
    listed above.
  - `bun run build` passes.
  - `bun run dev --port 5199` passes the flag on to Vite (`$ vite --port "5199"`), so no `--` is
    needed.
  - With Node on PATH (the host and the dev container), the server's process is
    `node <dir>/web/node_modules/.bin/vite …`. The pattern in `post-start.sh` still matches it.
  - With no `node` on PATH (as in the `oven/bun` image), bun runs Vite itself. The server
    answers 200 and proxies `/bff` to the BFF.
- Docker Hub has the tags `oven/bun:1.4.3` (Debian) and `oven/bun:1.4.3-slim` (Debian slim).
  Both images have a `bun` user (uid 1000) and the binary at `/usr/local/bin/bun`. npm's `bun`
  package lists 1.4.3 as its latest version.
- The factory's build environment is a dev container created before bun was added, so
  `command -v bun` finds nothing there. It also has no container engine. bun 1.4.3 can be added
  to PATH without touching the repo: `npm install -g bun@1.4.3` ships the same binary, or use
  bun's own installer. Criteria that need Podman or Docker, or a Dev Containers client, run on a
  host that has them. 009-postgresql-run-modes was handled the same way.
- The BFF answers `GET /bff/session` only when the request carries `X-CSRF: 1`
  (`bff/app/security.py`). Without a session it returns `{"authenticated":false,"user":null}`.

## Requirements

1. `web/package.json` gets `"packageManager": "bun@1.4.3"`. Nothing else in the file changes:
   scripts and dependency ranges stay as they are.
2. `web/bun.lock`, in text format, replaces `web/package-lock.json`, which is deleted. Create it
   by running `bun install` in `web/` while `package-lock.json` is still there. bun then migrates
   the existing resolutions, so the direct dependencies keep the versions listed in Context.
   There is no binary `bun.lockb`.
3. `web/Containerfile`:
   - `FROM docker.io/oven/bun:1.4.3-slim` replaces `node:22-slim`.
   - The image's `bun` user owns `/app` and the container runs as `bun`: `chown bun:bun /app`,
     `USER bun`, and `--chown=bun:bun` on every COPY. The comment that explains why the user owns
     `/app` names `bun`.
   - `COPY --chown=bun:bun package.json bun.lock ./` is followed by
     `RUN bun install --frozen-lockfile`, which replaces `npm ci`.
   - The image still copies only `index.html`, `tsconfig.json`, `vite.config.ts` and `src/`.
   - The last line is `CMD ["bun", "run", "dev", "--host", "0.0.0.0"]`.
4. `.devcontainer/Containerfile` gets
   `COPY --from=docker.io/oven/bun:1.4.3 /usr/local/bin/bun /usr/local/bin/bun` after the uv
   line. Use the Debian tag, never `-alpine`. The header comment mentions bun. Node 22 stays a
   feature in both `devcontainer.json` files.
5. In `.devcontainer/post-create.sh`, `(cd web && npm ci)` becomes
   `(cd web && bun install --frozen-lockfile)`.
6. `.devcontainer/post-start.sh` stays unchanged. Its `node_modules/.bin/vite` pattern already
   matches a dev server started by `bun run dev` (see Context), so a second run still prints
   "already running" for the web server.
7. `Makefile`: `web` runs `cd web && bun run dev` and `web-build` runs `cd web && bun run build`.
   Their help texts stay as they are.
8. `AGENTS.md`: every npm or npx command becomes its bun equivalent. Change nothing else.
   - "Layout": `bun run build` writes the static bundle.
   - "Setup": `cd web && bun install`, plus one sentence saying the web commands need bun 1.4.3
     on the host.
   - "Run locally":
     - `cd web && bun run dev`, keeping the `# web, port 5173` comment in line with the others;
     - "`make web-build` (runs `bun run build` in `web/`)";
     - the other-port note becomes `cd web && bun run dev --port <port>`.
   - "Sandbox": "`bun run dev` (`make web`)" in the port clash note.
   - "Dev container":
     - the intro lists bun 1.4.3 next to uv and Node 22;
     - the rebuild note says that a dev container created before PostgreSQL, smtp4dev or bun
       was added doesn't have them;
     - setup runs `uv sync --frozen` and `bun install --frozen-lockfile`;
     - the CLI line becomes `bunx @devcontainers/cli up --workspace-folder .`, with the Podman
       flags unchanged.
   - "Validation", `web/`: `bun run build`.
9. The bun version is 1.4.3 everywhere it appears: `web/package.json`, `web/Containerfile`,
   `.devcontainer/Containerfile` and `AGENTS.md`.
10. No app code changes. Nothing changes under `web/src/`, nor `web/index.html`,
    `web/tsconfig.json`, `web/vite.config.ts`, `web/.dockerignore`, `bff/`, `api/`,
    `compose.yaml` or the `devcontainer.json` and `devcontainer-lock.json` files.

## Acceptance criteria

The builder can check criteria 1 to 11 with bun 1.4.3 on PATH and no container engine.

1. **One text lockfile.** `git ls-files web | grep -i lock` prints only `web/bun.lock`.
   `test ! -e web/package-lock.json && test ! -e web/bun.lockb && echo ok` prints `ok`.
   `head -c1 web/bun.lock` prints `{`.
2. **Same dependency versions.** This command:
   `grep -oE '"(react|react-dom|@tanstack/react-query|zod|@types/react|@types/react-dom|@vitejs/plugin-react|typescript|vite)@[0-9][^"]*"' web/bun.lock | sort -u`
   prints exactly these nine lines:
   - `"@tanstack/react-query@5.104.1"`
   - `"@types/react-dom@19.3.0"`
   - `"@types/react@19.3.0"`
   - `"@vitejs/plugin-react@6.1.2"`
   - `"react-dom@19.3.0"`
   - `"react@19.3.0"`
   - `"typescript@6.0.3"`
   - `"vite@8.3.4"`
   - `"zod@4.6.5"`
3. **Install and build pass.**
   - `cd web && bun install --frozen-lockfile && bun run build` exits 0 and writes
     `web/dist/index.html`.
   - Afterwards, `git status --porcelain web/bun.lock` prints nothing.
   - `make web-build` from the repo root exits 0.
4. **No npm left.** This command prints nothing:
   `grep -nE '\bnpm\b|\bnpx\b' AGENTS.md Makefile .devcontainer/*.sh .devcontainer/Containerfile web/Containerfile web/package.json`
5. **One bun version.** This command prints at least one line for each of the four files, and
   every match ends in `1.4.3`:
   `grep -noE 'bun(@|:| )[0-9]+\.[0-9]+\.[0-9]+' web/package.json web/Containerfile .devcontainer/Containerfile AGENTS.md`
6. **Makefile.** `make -n web` prints `cd web && bun run dev`, and `make -n web-build` prints
   `cd web && bun run build`.
7. **Images and setup scripts.**
   - `web/Containerfile` contains these lines and no `node` user:
     - `FROM docker.io/oven/bun:1.4.3-slim`
     - `USER bun`
     - `COPY --chown=bun:bun package.json bun.lock ./`
     - `RUN bun install --frozen-lockfile`
     - `CMD ["bun", "run", "dev", "--host", "0.0.0.0"]`
   - `.devcontainer/Containerfile` contains
     `COPY --from=docker.io/oven/bun:1.4.3 /usr/local/bin/bun /usr/local/bin/bun`.
   - `.devcontainer/post-create.sh` ends with `(cd web && bun install --frozen-lockfile)`.
   - `git diff main -- .devcontainer/post-start.sh` prints nothing.
8. **The dev server runs under bun with Node on PATH** (the host and dev container case). Start
   the BFF on 8000 and run `cd web && bun run dev --port 5199`. Then:
   - `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5199/` prints `200`;
   - `curl -s -H 'X-CSRF: 1' http://127.0.0.1:5199/bff/session` prints the BFF's JSON,
     `{"authenticated":false,"user":null}` when there is no session;
   - `pgrep -af node_modules/.bin/vite` lists this server, with a path under this checkout's
     `web/`.

   Stop the server afterwards.
9. **The dev server runs under bun without Node** (the case inside the sandbox image). Repeat
   criterion 8 with a PATH where `bun` is found but `command -v node` finds nothing, for example
   a directory holding only a `bun` symlink plus `/usr/bin:/bin` when node isn't installed
   there. Both curl checks give the same results.
10. **AGENTS.md.** Each of these strings appears in the section named in Requirement 8:
    - `bun run build` (in "Layout")
    - `cd web && bun install`
    - `bun 1.4.3`
    - `cd web && bun run dev`
    - "runs `bun run build` in `web/`"
    - `bun run dev --port <port>`
    - "`bun run dev` (`make web`)"
    - `bun install --frozen-lockfile`
    - `bunx @devcontainers/cli up --workspace-folder .`

    The rebuild note names bun, and the "Validation" `web/` block reads `bun run build`.
11. **Scope.** `git diff --stat main` lists only these files:
    - `AGENTS.md`
    - `Makefile`
    - `.devcontainer/Containerfile`
    - `.devcontainer/post-create.sh`
    - `web/Containerfile`
    - `web/package.json`
    - `web/bun.lock` (new)
    - `web/package-lock.json` (deleted)
    - `specs/features/024-web-bun-tooling.md`

Criteria 12 to 14 need a host with Podman or Docker, and for 14 a Dev Containers client. A human
runs them if the builder can't.

12. **Host.** Run `cd web && bun install`, then `make docker-up`, `make backend` and `make web`.
    http://localhost:5173 shows the app, and signing in as `alice`/`alice` works.
13. **Sandbox.**
    - `make sandbox-up` builds the `web` image without errors.
    - `podman compose -f compose.yaml exec web bun --version` prints `1.4.3`.
    - `podman compose -f compose.yaml exec web id -u` prints a non-zero uid.
    - http://localhost:5173 serves the app, and signing in as `alice`/`alice` works.

    Run `make sandbox-down` afterwards.
14. **Dev container.** Rebuild it ("Dev Containers: Rebuild Container", or
    `bunx @devcontainers/cli up --workspace-folder .` with the Podman flags when using Podman).
    Then:
    - `bun --version` inside the container prints `1.4.3`;
    - post-create installed `web/` with `bun install --frozen-lockfile`, and `web/bun.lock` is
      unchanged;
    - `/tmp/dev-web.log` shows Vite ready on 127.0.0.1:5173;
    - running `bash .devcontainer/post-start.sh` again prints
      `already running: node_modules/.bin/vite`.

## Out of scope

- `bun run test`, Vitest or any other test setup (UI-2). `bun test` is not used either.
- Upgrading dependencies, or changing the version ranges in `web/package.json`.
- Adding `bunfig.toml`, `trustedDependencies` or `engines`.
- Removing Node from the dev container, or changing `devcontainer.json`,
  `devcontainer-lock.json`, `compose.yaml`, `web/.dockerignore` or `web/vite.config.ts`.
- Changing app code in `web/src/`, `bff/` or `api/`.
- Editing older specs in `specs/features/` or `specs/email-sender/` that mention npm. They are
  history.
- A Makefile install target, or `make web` installing dependencies itself.
- Copying `bunx` into the dev container image, or pinning images by digest.
- Instructions for installing bun in `AGENTS.md`, beyond the version requirement.

## Assumptions

- **The lockfile keeps the versions `package-lock.json` resolves today, through bun's migration,
  instead of a fresh resolve.** Switching package managers shouldn't also upgrade Vite or React,
  and the request asks for no app change.
- **`AGENTS.md` "Setup" keeps a plain `bun install` and gives the bun version but no install
  command.** UI-1 asks for exactly that, and `AGENTS.md` doesn't explain how to install uv either.
- **`post-start.sh` stays unchanged.** I checked that `bun run dev`, with Node on PATH, starts
  `node …/node_modules/.bin/vite`, and the existing pattern matches it.
- **The Makefile help texts stay unchanged.** They don't mention npm, so "their help texts
  follow" needs no edit.
- **The dev container rebuild note in `AGENTS.md` adds bun.** An existing container has no bun
  until it is rebuilt (UI-1 pitfall), and the note already exists for PostgreSQL and smtp4dev.
- **Criteria 12 to 14 may not run in the factory's build environment.** It has no container
  engine and no Dev Containers client. As in 009, the builder reports them as not run, and a
  human runs them before merging.
