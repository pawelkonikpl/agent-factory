# Vitest and Testing Library in `web/`

> Feature: Add Vitest and Testing Library to `web/` with a `bun run test` script, the test helpers and the first tests of the existing components, and add `bun run test` to the validation, as specified in `specs/email-sender/frontend.md` UI-2 (covers F10, test half; F0 test config)

## Context

The full item is `specs/email-sender/frontend.md`, section "UI-2: Vitest and Testing Library"
(Requirements, Pitfalls, Acceptance criteria). It rests on `specs/email-sender/README.md`:

- §3.4 and D16: web validation is `bun run build`, and from UI-2 on also `bun run test`.
- §5 "Web": the helpers go in `web/src/test/` (`setup.ts`, `utils.tsx`, `mocks.ts`).
- §6 "Web": tests sit next to the code as `*.test.tsx`, with `fetch` stubbed, no network and
  no `act()` warnings.
- §13, F10: the CI workflow and coverage thresholds are dropped (D21). `web/` has no coverage
  tooling.

Every later Phase 5 item builds on these helpers:

- UI-3 adds the theme to `renderWithProviders`, and UI-4 adds a `MemoryRouter`.
- Later items add mock factories such as `createMockClient`.
- UI-4 removes `header-bar.tsx` and moves its tests into the NavBar.

### `web/` today, after 024-web-bun-tooling

- `web/package.json` has the scripts `dev`, `build` (`tsc --noEmit && vite build`), `typecheck`
  and `preview`, and `"packageManager": "bun@1.4.3"`. There is no test runner and no test file.
  `web/bun.lock` pins the direct dependencies at react 19.3.0, react-dom 19.3.0,
  @tanstack/react-query 5.104.1, zod 4.6.5, @types/react 19.3.0, @types/react-dom 19.3.0,
  @vitejs/plugin-react 6.1.2, typescript 6.0.3 and vite 8.3.4.
- `web/vite.config.ts` imports `defineConfig` from `vite`. It sets the dev server (127.0.0.1:5173,
  strictPort) and proxies `/bff` and `/api` to the BFF.
- `web/tsconfig.json` is strict, with `noUncheckedIndexedAccess`, `noUnusedLocals`,
  `verbatimModuleSyntax` and `types: ["vite/client"]`. It includes `src` and `vite.config.ts`, so
  `bun run build` (`tsc --noEmit`) type-checks every test file and helper under `src`.
- The code to test:
  - `web/src/services/bff-client.ts`: `bffRequest(path, parser, init)` is the only `fetch` in the
    app. It sets `X-CSRF: 1`, sets `Content-Type: application/json` when there is a body, and
    uses `credentials: "same-origin"`. On a non-2xx response it throws
    `ApiError(status, text)`. `isUnauthorized(error)` is true for an `ApiError` with status 401.
  - `web/src/query-client.ts`: `createQueryClient()`. The query and mutation caches' `onError`
    invalidates `SESSION_QUERY_KEY` (`["session"]`, from `web/src/hooks/use-session.ts`) on a 401.
    Queries retry up to 2 times, never on a 401.
  - `web/src/components/login-screen.tsx`: reads `?login_error=` from `window.location.search`.
    It maps six codes (`access_denied`, `login_expired`, `state_mismatch`, `issuer_mismatch`,
    `invalid_id_token`, `authorization_failed`) to Polish messages in `data-testid="login-error"`
    with `role="alert"`. An unknown code falls back to the `authorization_failed` message. The
    button is `data-testid="login-button"`, "Zaloguj się".
  - `web/src/components/header-bar.tsx` takes a `User` and shows:
    - `user.name ?? user.sub` in `data-testid="user-name"`;
    - the email unless it is `null`;
    - "Wyloguj" (`data-testid="logout-button"`), which runs `useLogout()` (`POST /bff/logout`).
    When logout fails, "Nie udało się wylogować. Spróbuj ponownie." shows in
    `data-testid="logout-error"` with `role="alert"`.
  - `web/src/components/notes-panel.tsx`: `useNotes()` (`GET /api/notes`) and `useCreateNote()`
    (`POST /api/notes`, then it invalidates `["notes"]`). It has these states:
    - loading: "Ładowanie…";
    - error: "Nie udało się pobrać notatek.";
    - empty: "Brak notatek. Dodaj pierwszą.";
    - list: `data-testid="notes-list"`, each note's text plus a `<time dateTime={created_at}>`
      formatted for `pl-PL` in the machine's timezone.

    On submit it trims the input. It sends nothing when the trimmed input is empty, and clears
    the input after a successful POST. The input is `data-testid="note-input"` and the button is
    `data-testid="note-submit"`.
  - `web/src/services/session-api.ts` exports the `User` type, and `notes-api.ts` exports `Note`.
    `startLogin()` and `logout()` call `window.location.assign`, which jsdom doesn't implement
    (it logs "Not implemented: navigation").
- `AGENTS.md` "Validation", `web/`, lists only `bun run build`. `README.md` and the Makefile name
  no web test command.

### What I checked while writing this spec

I tried this on a copy of `web/` with bun 1.4.3 and Node 22.23.3 (the factory's dev container
has both on PATH):

- **Install.** `bun add -d vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event`
  resolved:
  - vitest 5.0.5, whose peer range for vite is `^6.4.0 || ^7.0.0 || ^8.0.0`;
  - jsdom 30.1.3, @testing-library/react 16.3.3, @testing-library/jest-dom 7.0.1 and
    @testing-library/user-event 14.6.8.

  bun also installed `@testing-library/dom` 10.4.2, a peer dependency of
  `@testing-library/react` and `user-event`, and recorded it in `bun.lock`. The nine existing
  direct dependencies kept their versions.
- **Tests and build.** I used `defineConfig` from `vitest/config` with
  `test: { environment: "jsdom", setupFiles: "./src/test/setup.ts", css: true }`. Then:
  - `bun run test` (`vitest run`) ran sample tests of all five modules. They passed with no
    `act()` warnings.
  - `bun run build` type-checked them, including jest-dom's matchers and
    `mock.calls[0]?.[1]`, and passed.
- **Unknown requests.** A `stubFetch` failed the test whenever an unknown request was made, even
  when the caller swallowed the rejection. It did this by registering Vitest's `onTestFinished`
  hook and throwing from it. The output was
  `Error: stubFetch: unexpected requests: GET /api/unknown`, and the exit code was 1.
  TanStack Query turns a rejected `fetch` into an error state, so without such a hook an unknown
  request wouldn't fail the test.
- **Vitest needs Node.** With only `bun` on PATH (no `node`), `bun run test` fails before any
  test runs (`TypeError: 'addEventListener' called on an object that is not a valid instance of
  EventTarget`, from jsdom). With Node on PATH it passes. The engines fields are:
  - jsdom 30: node `^22.22.2 || ^24.15.0 || >=26.0.0`;
  - vitest 5: `^22.12.0 || ^24.0.0 || >=26.0.0`.
- **The no-Node case still works for dev and build.** With only `bun` on PATH (as in the sandbox
  image), the `vitest/config` import doesn't stop `bun run dev` (200 on `/`) or `bun run build`.
- **`bun test` is a different runner.** It is bun's own runner. It picks up the same files and
  fails them all (`vi.stubGlobal is not a function`).
- **Arguments pass through.** `bun run test --reporter=verbose` and
  `bun run test src/<file>.test.ts` reach Vitest.

## Requirements

1. **Dependencies.** In `web/`, add these dev dependencies with `bun add -d`, as caret ranges of
   their current majors:
   - `vitest` (^5)
   - `jsdom` (^30)
   - `@testing-library/react` (^16)
   - `@testing-library/jest-dom` (^7)
   - `@testing-library/user-event` (^14)

   `web/bun.lock` is updated in text format. The nine existing direct dependencies keep the
   versions listed in Context, and no existing range in `package.json` changes.
2. **Script.** `web/package.json` gets `"test": "vitest run"`. The other scripts stay as they
   are.
3. **Config.** `web/vite.config.ts` imports `defineConfig` from `vitest/config` instead of
   `vite`, and adds
   `test: { environment: "jsdom", setupFiles: "./src/test/setup.ts", css: true }`. There is no
   `globals` option. The plugins, the server settings, the proxy and the comments stay as they
   are.
4. **`web/src/test/setup.ts`.** It imports `@testing-library/jest-dom/vitest`. After each test it
   calls `cleanup()` from `@testing-library/react` and `vi.unstubAllGlobals()`, so one test's
   `fetch` stub never leaks into the next.
5. **`web/src/test/utils.tsx`** exports these four helpers:
   - `createTestQueryClient()`: a new `QueryClient` whose queries use
     `retry: false, gcTime: 0, staleTime: 0` and whose mutations use `retry: false`.
   - `renderWithProviders(ui, options?)`:
     - it renders `ui` inside a `QueryClientProvider`;
     - `options.queryClient` is optional and defaults to `createTestQueryClient()`;
     - it returns Testing Library's render result plus the `queryClient` it used.

     Later items add the theme and router options.
   - `stubFetch(routes)`:
     - It installs a `vi.fn` with `vi.stubGlobal("fetch", …)` and returns that mock, so a test
       can read each call's arguments.
     - Each key is `"<METHOD> <path>"`, for example `"GET /api/notes"`. The path is the URL's
       pathname, without the query string, resolved against the jsdom page's URL.
     - Each value is either `{ status?: number; body?: unknown }` or a function of the `Request`
       that returns one, directly or as a promise. The status defaults to 200. The body is sent
       as JSON with `Content-Type: application/json`. There is no body when `body` is
       `undefined`.
     - A request whose method and path match no route makes the `fetch` call reject with an
       error whose message starts with `stubFetch:` and names the method and path. That
       request also fails the test when the test finishes, with such a message, even if the
       code under test caught the rejection. Vitest's `onTestFinished` does this (see Context).
   - `waitForQueriesToSettle(queryClient)`: resolves once the client has no fetching query and no
     running mutation. It uses Testing Library's `waitFor`.
6. **`web/src/test/mocks.ts`** exports these two factories, built from the `User` and `Note`
   types with `import type`:
   - `createMockUser(overrides?: Partial<User>): User`, defaulting to
     `{ sub: "alice", name: "Alice Example", email: "alice@example.com" }`;
   - `createMockNote(overrides?: Partial<Note>): Note`, defaulting to
     `{ id: "1", text: "Notatka", created_at: "2026-10-10T15:03:00+02:00" }`.

   These are the stub values in `AGENTS.md`.
7. **Test rules.** Test files sit next to the code they test. They import `describe`, `it`,
   `expect` and `vi` from `vitest` and everything else from `@testing-library/react` and
   `@testing-library/user-event`. They stub every request with `stubFetch`. They await every
   user event (`userEvent.setup()`) and use `findBy*` for async results, so there are no
   `act()` warnings. Use the mock factories wherever a test needs a user or a note.
8. **First tests.** Each case below is its own test:
   - `web/src/services/bff-client.test.ts`:
     - the request carries `X-CSRF: 1` and `credentials: "same-origin"`, read from the
       `stubFetch` mock;
     - a 2xx JSON response returns the parser's result;
     - a non-2xx response (for example 502) throws an `ApiError` whose `status` is that status.
   - `web/src/query-client.test.ts` or `.tsx`, against `createQueryClient()` itself, not the
     test client:
     - a query whose request answers 401 is requested exactly once (no retry);
     - that 401 invalidates the `["session"]` query;
     - a mutation whose request answers 401 also invalidates the `["session"]` query.
   - `web/src/components/login-screen.test.tsx`. Each test sets the URL with
     `window.history.replaceState` and resets it to `/` afterwards.
     - Each of the six `login_error` codes shows its exact message in `login-error`. The test
       lists the six code and message pairs itself.
     - An unknown code shows the `authorization_failed` message.
     - Without `login_error` there is no alert, and the "Zaloguj się" button shows.
   - `web/src/components/header-bar.test.tsx`:
     - it shows `name`, and `sub` when `name` is `null`;
     - it shows the email, and no email when it is `null`;
     - clicking "Wyloguj" while `POST /bff/logout` answers an error (for example 502) shows
       "Nie udało się wylogować. Spróbuj ponownie." in an alert.
   - `web/src/components/notes-panel.test.tsx`:
     - **Empty:** an empty list shows "Brak notatek. Dodaj pierwszą.".
     - **List:** it shows each note's text and a `<time>` whose `dateTime` is its `created_at`.
       Don't assert the formatted time, which depends on the machine's timezone.
     - **Error:** a failing `GET /api/notes` (for example 500) shows
       "Nie udało się pobrać notatek.".
     - **Trimming:**
       - Typing "  Nowa notatka  " and submitting sends `POST /api/notes` with the body
         `{"text":"Nowa notatka"}`. The input is then empty, and the refreshed list shows the
         note.
       - Whitespace-only input sends no `POST`. Check this after `waitForQueriesToSettle`.
9. **`AGENTS.md`, "Validation".** Under "In `web/`:", the code block lists `bun run build` and
   `bun run test`. A short note below it says four things:
   - `bun run test` runs Vitest with jsdom and Testing Library on the `*.test.ts(x)` files in
     `web/src`, with `fetch` stubbed, so no backend has to run.
   - It runs Vitest on Node, not on bun.
   - So it needs `node` on PATH, in jsdom 30's range: 22.22.2 or newer on 22, 24.15 or newer on
     24, or 26 and later. The dev container has it.
   - `bun test` is bun's own test runner, not Vitest, and fails on these tests.

   Nothing else in `AGENTS.md` changes.
10. **Scope of the change.** No existing module under `web/src/` changes, and neither do
    `web/tsconfig.json`, `web/index.html`, `web/Containerfile`, `.devcontainer/`, `compose.yaml`,
    the `Makefile`, `bff/` or `api/`.

## Acceptance criteria

A builder with bun 1.4.3 and Node 22.22.2 or newer on PATH can check all of these. The factory's
dev container has both. None of them needs a container engine, the BFF, the API or Keycloak.

1. **Dependencies.** This command prints exactly five lines:
   `grep -nE '"(vitest": "\^5|jsdom": "\^30|@testing-library/react": "\^16|@testing-library/jest-dom": "\^7|@testing-library/user-event": "\^14)\.' web/package.json`.
   `grep -n '"test": "vitest run"' web/package.json` prints one line. `git diff main -- web/package.json`
   adds the script and the five dependencies and changes no existing script or version range.
   The only line it may change is `"vite": "^8.3.0"`, which gains a trailing comma.
2. **Existing versions are kept.** This command prints the same nine lines as in
   024-web-bun-tooling's criterion 2 (react 19.3.0 … zod 4.6.5, the versions listed in Context):
   `grep -oE '"(react|react-dom|@tanstack/react-query|zod|@types/react|@types/react-dom|@vitejs/plugin-react|typescript|vite)@[0-9][^"]*"' web/bun.lock | sort -u`.
3. **The lockfile is frozen.** `cd web && bun install --frozen-lockfile` exits 0. Afterwards
   `git status --porcelain web/bun.lock` prints nothing. `git ls-files web | grep -i lock` prints
   only `web/bun.lock`.
4. **The tests pass.** With no BFF, API or Keycloak running, `cd web && bun run test` exits 0.
   `bun run test --reporter=verbose` lists passing tests from these five files, with one test for
   each case in Requirement 8:
   - `src/services/bff-client.test.ts`
   - `src/query-client.test.ts(x)`
   - `src/components/login-screen.test.tsx`
   - `src/components/header-bar.test.tsx`
   - `src/components/notes-panel.test.tsx`
5. **The build passes.** `cd web && bun run build` exits 0, which also type-checks the tests and
   helpers. `make web-build` from the repo root exits 0.
6. **No `act()` warnings.** `cd web && bun run test 2>&1 | grep -nE 'wrapped in act|support act'`
   prints nothing.
7. **Breaking `X-CSRF` fails a test.**
   1. Run `sed -i '/headers.set(CSRF_HEADER/d' web/src/services/bff-client.ts`.
   2. `cd web && bun run test` exits non-zero and reports a failure in `bff-client.test.ts`.
   3. `git checkout web/src/services/bff-client.ts` restores the file. `bun run test` passes
      again.
8. **An unknown endpoint fails the test with a clear message.**
   1. Create `web/src/stub-check.test.ts`. It imports `it` from `vitest` and `stubFetch` from
      `./test/utils`, and has one test that does two things:
      - calls `stubFetch({ "GET /api/notes": { body: [] } })`;
      - runs `await fetch("/api/unknown").catch(() => undefined)`.
   2. `cd web && bun run test src/stub-check.test.ts` exits non-zero. Its output contains
      `stubFetch` and `GET /api/unknown`, though the test caught the rejection.
   3. Delete the file.
9. **Config and helpers.**
   - `web/vite.config.ts` contains `from "vitest/config"`, `environment: "jsdom"`,
     `setupFiles: "./src/test/setup.ts"` and `css: true`, and no `globals`.
     `git diff main -- web/vite.config.ts` shows only the import line and the added `test` block.
   - `web/src/test/setup.ts` contains `@testing-library/jest-dom/vitest`, `cleanup` and
     `vi.unstubAllGlobals`.
   - `grep -cE 'export (async )?function (createTestQueryClient|renderWithProviders|stubFetch|waitForQueriesToSettle)\b' web/src/test/utils.tsx`
     prints `4`.
   - `grep -cE 'export function (createMockUser|createMockNote)\b' web/src/test/mocks.ts`
     prints `2`.
   - `grep -L 'from "vitest"' $(find web/src -name '*.test.ts*')` prints nothing.
   - `grep -rln 'globals' web/vite.config.ts web/tsconfig.json` prints nothing.
10. **Dev and build still work without Node** (the sandbox image's case).
    1. Use a PATH where `bun` is found but `command -v node` finds nothing. For example, use a
       directory that holds only a `bun` symlink, plus `/usr/bin:/bin` when node isn't
       installed there.
    2. With that PATH, `cd web && bun run build` exits 0.
    3. `bun run dev --port 5199` serves `http://127.0.0.1:5199/` with status 200. Stop the
       server afterwards.
11. **`AGENTS.md`.**
    - The "Validation" section's `web/` code block has both `bun run build` and `bun run test`.
    - The note below it mentions Vitest, Node with `22.22.2`, and that `bun test` is a different
      runner.
    - `git diff main -- AGENTS.md` touches only the "Validation" section.
12. **Scope.** `git diff --stat main` lists only these files:
    - `AGENTS.md`
    - `web/package.json`
    - `web/bun.lock`
    - `web/vite.config.ts`
    - `web/src/test/setup.ts`, `web/src/test/utils.tsx` and `web/src/test/mocks.ts`
    - the five test files from criterion 4
    - `specs/features/025-web-vitest-setup.md`

    `git diff --stat main -- bff api` prints nothing, so the API's and the BFF's validation is
    untouched.

## Out of scope

- **Tests beyond UI-2's list.** No tests for `app.tsx`'s session states (UI-4's gate tests) or
  `token-check.tsx`. No tests that need a real navigation: clicking "Zaloguj się", or a
  successful logout. jsdom doesn't navigate, so don't replace `window.location` to fake one.
- **App code.** No changes to the existing modules in `web/src/`, even to make them easier to
  test. If a case can't pass without an app change, report it instead of changing the app.
- **Helpers from later items.** No theme, router or `mode` option in `renderWithProviders`, and
  no mock factories for clients, categories or campaigns (UI-3, UI-4 and later items).
- **Extra tooling.** No coverage tooling, `@vitest/ui`, a watch script, `globals: true`,
  happy-dom, MSW, `bunfig.toml`, ESLint, husky or a pre-commit hook.
- **Build and run setup.** No Makefile test target and no CI workflow (D21). No changes to
  `web/tsconfig.json`, `web/Containerfile`, `.devcontainer/` or `compose.yaml`.
- **Node install docs.** No instructions in `AGENTS.md` for installing Node, beyond the version
  note.
- **Dependencies.** Don't upgrade or re-range the existing dependencies, and don't declare
  `@testing-library/dom` explicitly (see Assumptions).
- **Older docs.** Don't edit `specs/email-sender/` or older specs in `specs/features/`.

## Assumptions

- **`stubFetch` matches on method plus pathname and ignores the query string.** UI-2 says "by
  method and path". Later list screens send `skip`, `limit` and `search`. Tests read those from
  the recorded request, or answer per query in a handler function.
- **Unknown requests fail the test at its end, not only through a rejected `fetch`.** TanStack
  Query swallows the rejection into an error state, so a rejection alone wouldn't fail the test,
  as UI-2 asks. `onTestFinished` is Vitest's own hook for this, and I checked that it works.
- **`renderWithProviders` takes an options object and returns its `queryClient`, and
  `waitForQueriesToSettle` takes that client.** UI-2 names `waitForQueriesToSettle()` with no
  argument. A module-level "current client" would be hidden state, and later items add their
  options (`mode`, a start route) to the same object.
- **`setup.ts` also calls `vi.unstubAllGlobals()`.** Without it, a test that forgets
  `stubFetch` reuses the previous test's stub, whose unknown-request check has already run.
- **`@testing-library/dom` is not declared.** bun installs it as the peer of
  `@testing-library/react` and `user-event` and pins it in `bun.lock`. Tests import only from
  `@testing-library/react`. UI-2 lists exactly five dependencies.
- **jsdom 30, the current major, even though it needs Node 22.22.2+ (or 24.15+, 26+).** README §4
  says to use each dependency's current major. The dev container's Node 22 feature installs the
  latest 22.x (22.23.3 today). `AGENTS.md` states the requirement, because Vitest doesn't run
  under bun alone.
- **The 401 cases also cover a mutation.** `createQueryClient()` wires the same handler into
  both caches, and UI-2's "a 401 invalidates the session query" doesn't limit it to queries.
  UI-2 lists only the 401 cases, so the retry of other errors isn't tested here.
- **The login-screen test repeats the six messages itself.** `LOGIN_ERROR_MESSAGES` isn't
  exported, and exporting it would change app code. A literal copy also catches an accidental
  change to the copy.
