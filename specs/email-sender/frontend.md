# Email Sender UI items (UI-1 to UI-13)

Context, tags, the defects (W-xx) and the decisions (D-x) are in `README.md`; the HTTP contract
in `api-contract.md`. Each section is one roadmap item in `roadmap.md`, Phase 5, with Goal,
Requirements, Pitfalls, Depends on and Acceptance criteria.

**UI copy is Polish** (D1). The quoted strings below are the old app's exact copy; keep them
verbatim, as constants in the screen's module. Copy marked *(new copy)* is not in the source:
the old app had no such text, and this spec supplies it. Placeholders in braces
(`{count}`, `{query}`, `{campaignName}`) stand for values; the braces in `{name}`, `{email}`
and `{company}` are literal campaign variables.

Rules for every item:

- Data only through `web/src/services/<area>-api.ts` (zod schemas plus `bffRequest`, paths
  with the `/api` prefix and the contract's exact trailing slashes) and hooks in
  `web/src/hooks/use-<area>.ts`. Each item adds the functions, schemas and hooks it uses, and no
  others.
- Each screen item adds its route and its NavBar entry; nothing links to a screen that doesn't
  exist yet (W-20).
- Every async view has loading, error and empty states. Icon buttons have an `aria-label`,
  dialogs take and return focus, contrast passes WCAG AA in both themes (F12). Every
  `LinearProgress` has an accessible name. A tooltip on a button that can be disabled wraps the
  button in a `<span>`, since MUI shows no tooltip on a disabled button.
- Small screens (F12, D32): every table sits in UI-3's `ScrollableTable`, so it scrolls
  horizontally instead of squeezing the page; headers stack on `xs` (`PageHeader`).
- Counts in copy use UI-5's `pluralPl` with the three Polish forms.
- Tests come with the code (Vitest and Testing Library from UI-2 on, `fetch` stubbed). The item
  ends with `bun run build` and, from UI-2 on, `bun run test` green in `web/`, and the API's and
  BFF's validation untouched.
- Look at each screen in a browser with the stubbed requests from `AGENTS.md` (extended with
  the item's endpoints) in both themes, at desktop width and at 375 px, with its dialogs, forms
  and wizard steps.

---

## UI-1: Replace npm with bun in `web/`

Covers F0 (the tooling part).

### Goal

`web/` installs, builds and runs with bun in every run mode, with one lockfile. No app code
changes.

### Requirements

- `web/package.json`: `"packageManager": "bun@1.4.3"` (pinned; the newest bun when this was
  written). `bun install` writes `web/bun.lock`, which replaces `web/package-lock.json`
  (deleted; W-18: one lockfile).
- `web/Containerfile`: `docker.io/oven/bun:1.4.3-slim` replaces `node:22-slim`; the image's
  `bun` user owns `/app` (as `node` did); `COPY package.json bun.lock ./`;
  `RUN bun install --frozen-lockfile` replaces `npm ci`; the command becomes
  `["bun", "run", "dev", "--host", "0.0.0.0"]`.
- `.devcontainer/Containerfile`: install a pinned bun the way `uv` comes in,
  `COPY --from=docker.io/oven/bun:1.4.3 /usr/local/bin/bun /usr/local/bin/bun`. Node 22 stays (a
  dev container feature) for tools that need it.
- `.devcontainer/post-create.sh`: its `npm ci` line is replaced by
  `(cd web && bun install --frozen-lockfile)`.
- `.devcontainer/post-start.sh` keeps finding the running dev server: check the process command
  line under `bun run dev` (`pgrep -af vite`) and keep or change the `node_modules/.bin/vite`
  pattern so that a second run says "already running".
- `Makefile`: `web` runs `cd web && bun run dev`, `web-build` runs `cd web && bun run build`;
  their help texts follow.
- `AGENTS.md`, every web command becomes bun (each npm command is replaced):
  - "Layout": `bun run build` writes the static bundle;
  - "Setup": `cd web && bun install`, and bun 1.4.3 must be installed on the host;
  - "Run locally": `cd web && bun run dev`; the other-port note uses
    `bun run dev --port <port>`; `make web-build` runs `bun run build`;
  - "Sandbox": `bun run dev` (`make web`) in the port clash note;
  - "Dev container": setup runs `uv sync --frozen` and `bun install --frozen-lockfile`; the
    image includes bun; the devcontainers CLI line uses `bunx @devcontainers/cli up …`;
  - "Validation", `web/`: `bun run build`.

### Pitfalls

- `bun install` without `--frozen-lockfile` may rewrite `bun.lock`; scripts and images always
  pass it. Commit the text `bun.lock` (the default since bun 1.2), not a binary `bun.lockb`.
- The `oven/bun` image has no Node. `bun run` then runs Vite's `#!/usr/bin/env node` bin with
  bun; check that the sandbox's dev server starts and proxies `/bff` and `/api`.
- The dev container image is Debian (glibc): copy bun from the Debian-based `oven/bun` tag,
  never from `-alpine` (musl).
- Keep the bun version the same in `packageManager`, both Containerfiles and `AGENTS.md`.
- Check how arguments reach Vite (`bun run dev --port 5180`) before documenting it.
- `bun test` is bun's own test runner, not Vitest; it matters from UI-2 on.
- An existing dev container must be rebuilt to get bun; `node_modules` is shared with the host
  (the existing `AGENTS.md` note).

### Depends on

Nothing (Phase 4 is done before this phase starts).

### Acceptance criteria

1. `web/bun.lock` exists and has replaced `web/package-lock.json`, which is gone.
2. `cd web && bun install --frozen-lockfile && bun run build` passes on the host.
3. `grep -nE '\bnpm\b|\bnpx\b' AGENTS.md Makefile .devcontainer/*.sh web/Containerfile` prints
   nothing.
4. `make web` serves http://localhost:5173 and signing in through the BFF works; `make sandbox-up`
   does the same in containers.
5. In a rebuilt dev container, post-create installs with bun, post-start starts the dev server,
   and running `.devcontainer/post-start.sh` again prints "already running" for it.

---

## UI-2: Vitest and Testing Library

Covers F10 (the test half), F0 (the test configuration).

### Goal

`web/` has a test runner, test helpers and its first tests, and `bun run test` joins the
validation.

### Requirements

- Dev dependencies: `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`,
  `@testing-library/user-event`.
- `web/vite.config.ts` (`defineConfig` from `vitest/config`): `test: { environment: "jsdom",
  setupFiles: "./src/test/setup.ts", css: true }`. Test files import `describe`, `it`,
  `expect` and `vi` from `vitest` (no globals).
- `web/package.json`: `"test": "vitest run"`.
- `src/test/setup.ts`: `import "@testing-library/jest-dom/vitest"` and `afterEach(cleanup)`.
- `src/test/utils.tsx`: `createTestQueryClient()` (`retry: false, gcTime: 0, staleTime: 0`);
  `renderWithProviders(ui)` wrapping a `QueryClientProvider` (UI-3 adds the theme, UI-4 a
  `MemoryRouter` with a start route); `stubFetch(routes)`, a `vi.stubGlobal("fetch", …)` helper
  that answers by method and path and fails the test on any request it doesn't know;
  `waitForQueriesToSettle()`.
- `src/test/mocks.ts`: factories for the session user and notes (later items add theirs, such
  as `createMockClient(overrides)`).
- First tests, of the code that exists: `bff-client` (sends `X-CSRF` and same-origin
  credentials, throws `ApiError` with the status), `query-client` (a 401 invalidates the session
  query and is not retried), `login-screen` (the `login_error` codes and their messages),
  `header-bar` (name, email, the logout error), `notes-panel` (empty, list, error, the input is
  trimmed).
- `AGENTS.md` "Validation", `web/`: `bun run build` and `bun run test`, and that `bun test` is a
  different runner.

### Pitfalls

- `bun test` runs bun's own runner on `*.test.tsx` and fails on Vitest's and jsdom's APIs; the
  command is `bun run test`.
- Vitest's peer range must include the repo's Vite 8 (Vitest 5 does).
- `bun run build` type-checks the tests too (`tsc --noEmit` covers `src`), with
  `noUncheckedIndexedAccess`.
- No `act()` warnings: await user events and use `findBy*` for async results.
- Tests never reach the network; `stubFetch` fails unknown calls.

### Depends on

UI-1.

### Acceptance criteria

1. `bun run test` runs the new tests and passes; `bun run build` passes.
2. Breaking `bffRequest`'s `X-CSRF` header makes a test fail.
3. A test that calls an unknown endpoint fails with a clear message from `stubFetch`.
4. The test output has no `act()` warnings.
5. `AGENTS.md` lists `bun run test` under "Validation".

---

## UI-3: MUI theme, design tokens, Inter and the shared components

Covers F1.

### Goal

The light and dark "Modern SaaS 2026" theme, its tokens, the Inter font and the shared `ui/`
components the screens use.

### Requirements

- Dependencies: `@mui/material`, `@mui/icons-material`, `@emotion/react`, `@emotion/styled`,
  `@fontsource-variable/inter` (D24: bundled, no Google Fonts).
- `src/theme/tokens.ts`: `getTokens(mode)` with these values.

  | Token | Light | Dark |
  |---|---|---|
  | primary main / light / dark | `#6366f1` / `#818cf8` / `#4f46e5` | `#818cf8` / `#a5b4fc` / `#6366f1` |
  | secondary | `#8b5cf6` / `#a78bfa` / `#7c3aed` | `#a78bfa` / `#c4b5fd` / `#8b5cf6` |
  | success | `#10b981` / `#34d399` / `#059669` | `#34d399` / `#6ee7b7` / `#10b981` |
  | warning | `#f59e0b` / `#fbbf24` / `#d97706` | `#fbbf24` / `#fcd34d` / `#f59e0b` |
  | error | `#ef4444` / `#f87171` / `#dc2626` | `#f87171` / `#fca5a5` / `#ef4444` |
  | info | `#3b82f6` / `#60a5fa` / `#2563eb` | `#60a5fa` / `#93c5fd` / `#3b82f6` |
  | background default / paper / subtle | `#f8fafc` / `#ffffff` / `#f1f5f9` | `#0f172a` / `#1e293b` / `#334155` |
  | text primary / secondary / disabled | `#0f172a` / `#475569` / `#94a3b8` | `#f1f5f9` / `#94a3b8` / `#64748b` |
  | border light / main | `rgba(226,232,240,.8)` / `rgba(203,213,225,.6)` | `rgba(51,65,85,.8)` / `rgba(71,85,105,.6)` |

  - Gradients: primary `linear-gradient(135deg,#6366f1 0%,#8b5cf6 100%)`, secondary
    `linear-gradient(135deg,#8b5cf6 0%,#a855f7 100%)`, success
    `linear-gradient(135deg,#10b981 0%,#34d399 100%)`.
  - Shared: spacing `{xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48}`; border radius
    `{sm: 8, md: 12, lg: 16, xl: 24, full: 9999}`; transitions `fast 150ms`, `normal 200ms`,
    `slow 300ms` with `cubic-bezier(.4,0,.2,1)`, and `spring 400ms cubic-bezier(.34,1.56,.64,1)`.
  - Shadows `sm`, `md`, `lg`, `xl`, one set per mode. The source gives no values; start from
    light `0 1px 2px rgba(15,23,42,.06)`, `0 4px 12px rgba(15,23,42,.08)`,
    `0 12px 24px rgba(15,23,42,.10)`, `0 24px 48px rgba(15,23,42,.12)` and dark
    `0 1px 2px rgba(0,0,0,.30)`, `0 4px 12px rgba(0,0,0,.35)`, `0 12px 24px rgba(0,0,0,.40)`,
    `0 24px 48px rgba(0,0,0,.45)`.
  - Glow: primary `0 8px 24px rgba(99,102,241,.25)` (source); secondary
    `0 8px 24px rgba(139,92,246,.25)` and success `0 8px 24px rgba(16,185,129,.25)` follow the
    same pattern.
  - Typography, Inter: h1 `2.5rem`/800, h2 `2rem`/700, h3 `1.5rem`/700, h4 `1.25rem`/600, then
    h5 `1.125rem`/600 and h6 `1rem`/600 (the source stops at h4).
  - [FIX] Text on a gradient. White on the source's primary gradient fails WCAG AA (4.47:1 on
    `#6366f1`, 4.23:1 on `#8b5cf6`). Where white text sits on a gradient (`GradientButton`, the
    active NavBar entry), use the text gradient `linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%)`
    (the light `primary.dark` and `secondary.dark`; 6.29:1 and 5.70:1) in both modes. The
    source's gradients stay for decoration: the logo square, gradient text, backgrounds.
- `src/theme/theme.ts`: `createAppTheme(mode)` with `cssVariables: true`,
  `shape.borderRadius = 12`, `palette.contrastThreshold: 4.5` (so MUI picks black or white text
  that passes AA on each palette colour), the palette and typography above, and overrides for
  CssBaseline, Button, IconButton, Paper, Card (with CardHeader and CardContent), TextField,
  OutlinedInput, InputLabel, Chip, Dialog (with Title, Content and Actions), TableHead,
  TableRow, TableCell, TablePagination, Tooltip, Alert, Snackbar, Drawer, ListItemButton, Avatar,
  Skeleton, LinearProgress, CircularProgress, Tabs, Tab and Badge, all from the tokens.
- `src/theme/theme-mode-context.tsx`: `ThemeModeProvider` with `{ mode, toggleTheme, isDark }`,
  **dark by default**, stored in `localStorage["themeMode"]` (`light` or `dark`); it wraps the
  MUI `ThemeProvider` and `CssBaseline`. `useThemeMode()` throws outside the provider.
- `src/theme/global-styles.tsx`: `AppGlobalStyles` (`scroll-behavior: smooth`,
  `box-sizing: border-box`, `::selection` in the primary colour, keyframes `fadeIn` (opacity
  0 → 1 and translateY 10px → 0), `slideIn`, `pulse`) and `AppBackground` (fixed,
  `z-index: -1`: radial gradients, indigo at the top and violet bottom right, stronger in dark,
  plus a 64 px grid in `rgba(99,102,241,.02)` light / `.03` dark).
- `main.tsx` imports the font and mounts `ThemeModeProvider`, `AppGlobalStyles` and
  `AppBackground` around the app. `styles.css` keeps its classes but takes its colours from the
  theme's CSS variables (for example `--surface: var(--mui-palette-background-paper)`), so the
  login screen and the notes demo follow the theme instead of the OS setting.
- `src/components/ui/` with an `index.ts`:
  - `PageContainer` (page wrapper: max width, padding);
  - `PageHeader({ title, subtitle?, icon?, breadcrumbs?: {label, href?}[], action? })`, the
    action on the right, stacked on `xs`;
  - `ModernCard({ children, hover = true, gradient = false, noPadding = false, ...PaperProps })`;
  - `StatsCard({ title, value, subtitle?, icon, trend?: {value, label}, color?:
    "primary" | "secondary" | "success" | "warning" | "error" })`;
  - `TableSkeleton({ rows, columns })`;
  - `EmptyState({ icon?, title, description?, action?: {label, onClick} })`;
  - `GradientButton` (`ButtonProps` plus `gradientType: "primary" | "secondary"`);
  - `SearchInput({ value, onChange(value), placeholder = "Szukaj...", fullWidth? })` with a
    clear button (`aria-label` "Wyczyść" *(new copy)*);
  - `LoadingState`, `ErrorState({ error, title? })` (an `Alert severity="error"` with an
    `AlertTitle`);
  - `ScrollableTable({ children })`: a `TableContainer` with `overflow-x: auto` that every
    screen's table sits in, so wide tables scroll horizontally on small screens (F12, D32).
- The source's generic `DataTable` is dropped: each screen's table is its own component, so it
  would be unused.
- `renderWithProviders` (UI-2) adds `ThemeModeProvider` and takes a `mode`.

### Pitfalls

- The current MUI major is newer than the source's MUI 7: check `cssVariables`, the theme
  `colorSchemes` options and the CSS variable names against the installed version.
- No hex colours in components, only tokens and theme values (the old `SendConfirmDialog` had
  them).
- The token check on the notes page counts `localStorage` entries; the `themeMode` entry raises
  it to 1. That is expected, it is not a token, and the token check doesn't change.
- Inter must come from the bundle: no request to Google Fonts (D24).
- Keep the existing screens working; the NavBar and its theme switch come in UI-4.

### Depends on

UI-2.

### Acceptance criteria

1. Tests render `ModernCard`, `EmptyState` and `SearchInput` in both themes; `SearchInput`'s
   clear button empties it.
2. Tests: the default mode is dark; `toggleTheme` switches and stores `themeMode`; a stored
   `light` is restored; `useThemeMode()` outside the provider throws.
3. A test checks with MUI's `getContrastRatio`, in both modes, that these reach at least 4.5:
   `text.primary` and `text.secondary` on `background.default` and `background.paper`; white on
   both stops of the text gradient; each palette colour's `contrastText` on its `main` (the
   status chips).
4. A test renders a wide table in `ScrollableTable` and finds its container scrolls horizontally
   (`overflow-x: auto`).
5. In a browser, the login screen and the notes page use the dark theme with Inter, and the
   network panel shows no font request to another origin.
6. `bun run build` and `bun run test` pass.

---

## UI-4: App shell

Covers F3, F2 (the ErrorBoundary), F0 (the page title).

### Goal

Routing, the NavBar and the layout, with the notes demo on its own route, behind the existing
session gate.

### Requirements

- Dependencies: `react-router` (since v7 `react-router-dom` only re-exports it) and
  `react-error-boundary`.
- Provider order, outside in: `QueryClientProvider` → `ThemeModeProvider` (with UI-3's
  `AppGlobalStyles` and `AppBackground`) → `BrowserRouter` → the session gate → the routes.
  `main.tsx` keeps `StrictMode` and adds the `ErrorBoundary`. (UI-5 adds the error notification
  provider below the theme.)
- The session gate replaces the source's `ProtectedRoute` (D12) and keeps today's `App` states:
  "Sprawdzanie sesji…", "Nie udało się sprawdzić sesji.", the login screen, or the layout.
- Routes in this item: `/` redirects to `/notes` (UI-7 changes it to `/clients`); `/notes`
  shows `NotesPanel` and `TokenCheck` unchanged; any other path redirects to `/`. Each screen
  item adds its own route.
- The layout: `NavBar` plus a `<main>` with the `fadeIn .4s` animation.
- `NavBar` (`src/components/layout/nav-bar.tsx`), a permanent `Drawer`, **280 px** wide and
  **80 px** collapsed, with a 0.3 s transition:
  - logo: a 44 px gradient square with the `Campaign` icon; the name "Email Sender" in
    gradient text and the caption "Marketing Platform", both hidden when collapsed;
  - buttons: the theme switch (tooltip "Jasny motyw" in dark mode, "Ciemny motyw" in light
    mode) and collapse (tooltip "Zwiń menu" / "Rozwiń menu");
  - sections "Menu" and "Inne", built from one list of entries (label, path, icon, the paths
    that make it active). This item adds one entry under "Inne": "Notatki" *(new copy)*
    (`/notes`, icon `StickyNote2`). A section without entries isn't shown. The screen items add
    "Klienci" (`/clients`, `People`), "Kategorie" (`/categories`, `Category`) and "Kampanie"
    (`/campaigns`, `Campaign`) to "Menu", and "Ustawienia" (`/settings`) to "Inne", in that
    order;
  - entries are links (`component={NavLink}`) with `aria-current="page"` on the active one;
  - the active entry follows the location: the text gradient (UI-3), white text and the glow; an
    inactive entry moves `translateX(4px)` on hover; collapsed entries show their label as a
    tooltip;
  - [FIX W-20, D9] no "Pomoc" (`/help`) and no "Import klientów";
  - the user section at the bottom: an avatar with the initial of `user.name` (falling back to
    `email`, then `sub`), the name and the email from `GET /bff/session`. It is a button with
    the `aria-label` "Menu użytkownika" *(new copy)*. Clicking opens a menu
    with "Wyloguj", which runs the existing logout mutation; a failed logout shows the existing
    "Nie udało się wylogować. Spróbuj ponownie." (UI-8 adds "Ustawienia"; "Profil" stays hidden,
    D12.)
- Small screens (D32): below MUI's `md` breakpoint a top `AppBar` shows a menu button
  (`aria-label` "Otwórz menu" *(new copy)*) and "Email Sender". The NavBar becomes a temporary
  `Drawer`, 280 px wide and expanded, that closes when an entry is chosen, on Escape or on a
  click outside; the collapse button is hidden there. The page then uses the full width.
- `header-bar.tsx` is removed: its user display and logout move into the NavBar, with its
  tests.
- `ErrorBoundary` (react-error-boundary): the fallback is an `Alert severity="error"` with
  "**Coś poszło nie tak:** {message}" and a "Spróbuj ponownie" button that calls
  `window.location.reload()`.
- `index.html`: `<title>Email Sender</title>` (`lang="pl"` stays); the login screen's heading
  becomes "Email Sender" (its explanation of the BFF stays).
- `styles.css` drops the `body` padding and the `#root` width and grid, which would squeeze the
  layout; the notes and login classes stay. The notes route sits in `PageContainer`, and the
  login screen keeps a centred card at most 640 px wide, so neither stretches edge to edge.
- `AGENTS.md` "Layout", `web/`: the static host also falls back to `index.html` for the SPA's
  routes.

### Pitfalls

- `/bff/*` are full-page navigations (`window.location.assign`), never router links; the router
  must not handle them. The Vite proxy serves `/bff` and `/api` before the SPA.
- Deep links (`/notes`) need the `index.html` fallback; Vite's dev server has it.
- The NavBar list is the only place entries are declared, so later items add one line each.
- `user.name` and `user.email` can be `null`.

### Depends on

UI-3.

### Acceptance criteria

1. Routing tests (`MemoryRouter`): `/` → `/notes`; an unknown path → `/`; the "Notatki" entry is
   active on `/notes`.
2. NavBar tests: collapsing narrows it and shows tooltips; the theme switch toggles the mode;
   the user section shows the initial, name and email; "Wyloguj" calls `POST /bff/logout`; a
   failed logout shows the error.
3. Gate tests: checking, error, the login screen when signed out, the layout when signed in.
4. A component that throws shows the ErrorBoundary fallback.
5. In a browser with the stubbed session, the shell, the notes page and the collapse work in
   both themes, and the page title is "Email Sender".
6. At 375 px: the top bar shows, the menu button opens and closes the drawer, choosing an entry
   closes it, and the login screen and the notes page fit the width with no sideways scrolling.
   A test renders the small-screen layout (a mocked `md` media query) and checks the same.
7. NavBar entries are links, and the active one has `aria-current="page"`.
8. `bun run build` and `bun run test` pass.

---

## UI-5: Error handling and API plumbing

Covers F2 (the core).

### Goal

One way to turn API errors into Polish messages and show them, the shared `Page` schema, the
query defaults and `useDebounce`.

### Requirements

- `src/services/bff-client.ts`:
  - `ApiError` gains `detail: string | ValidationIssue[] | null`, read from the JSON body's
    `detail` (or `message`) when there is one;
  - a `204` response calls `parser.parse(undefined)`, so `DELETE` calls pass `z.undefined()`.
- `src/services/page.ts`: `pageSchema(item)` → `z.object({ items: z.array(item), total:
  z.number().int().nonnegative() })` and the `Page<T>` type.
- `src/utils/error-message.ts` `getErrorMessage(error)`:
  - 400 and 422: a `detail` array's `msg` values joined with `, `, or the `detail` text; without
    one "Dane są nieprawidłowe";
  - 403 (the BFF's CSRF check): "Brak uprawnień do tego zasobu";
  - 404: "Nie znaleziono zasobu";
  - 5xx (including the BFF's 502): "Wystąpił błąd serwera. Spróbuj ponownie później.";
  - anything else, network errors included: `detail` or "Wystąpił nieoczekiwany błąd".
  The source's 401, 409 and 429 messages are dropped: a 401 shows the login screen (D12), and
  nothing in this stack answers 409 or 429.
- `src/components/layout/error-notification.tsx`: `ErrorNotificationProvider` and
  `useErrorNotification()` → `showError(message)`; one `Snackbar` at the top centre,
  `autoHideDuration` 5000, a `Slide` down, an `Alert severity="error" variant="filled"` (radius
  16 px, a red gradient, backdrop blur, `translateY(-2px)` on hover) with a close button. The
  hook throws outside the provider. The provider sits below `ThemeModeProvider`.
- `src/query-client.ts`:
  - `setGlobalErrorHandler(handler)`; the query and mutation caches' `onError` keeps
    invalidating the session on 401 and otherwise calls the handler, unless the query's or
    mutation's `meta.skipGlobalError` is true (typed through TanStack Query's `Register`);
  - `ErrorHandlerInitializer`, under the provider, registers `showError(getErrorMessage(e))`;
  - defaults: `refetchOnWindowFocus: false`, `retry: 1` (never on 401), `staleTime: 5 min`.
    The session query keeps its own `staleTime`.
- The session, notes and logout queries and mutations set `meta.skipGlobalError`: their
  screens already show their own errors.
- `src/hooks/use-debounce.ts`: `useDebounce<T>(value, delay = 500)`.
- `src/utils/plural.ts`: `pluralPl(n, one, few, many)`: `one` for 1; `few` when `n % 10` is 2 to
  4 and `n % 100` is not 12 to 14; `many` otherwise (0, 5 to 21, 25, …). Every count in copy
  uses it.
- Session expiry: when a 401 from a query or mutation brings the login screen back, it shows
  "Sesja wygasła. Zaloguj się ponownie." *(new copy)* above the sign-in button. A first visit
  without a session (`authenticated: false`, no 401) shows no such message.

### Pitfalls

- A screen that shows an error inline (a duplicate name at the field, the settings alerts) sets
  `meta.skipGlobalError`, so the message doesn't appear twice.
- FastAPI's validation errors are `422` with a `detail` array; domain errors are `400` with a
  string (the contract's §0).
- The source's axios interceptors, token refresh and `/login` redirect don't exist here (D12):
  `bffRequest` is the only `fetch`.

### Depends on

UI-4.

### Acceptance criteria

1. `getErrorMessage` tests for each status above, an array `detail`, a string `detail` and a
   network error.
2. `bffRequest` tests: `detail` is parsed; a 204 returns `undefined`.
3. A failing query shows the snackbar with the mapped message; a 401 shows no snackbar and
   brings back the login screen; a query with `meta.skipGlobalError` shows none.
4. `useDebounce` with fake timers returns the new value only after 500 ms.
5. A failing query is retried once, a 401 never.
6. `pluralPl` tests for 0, 1, 2, 5, 12, 22 and 25.
7. After a 401 the login screen shows the session-expired message; on a fresh signed-out visit it
   doesn't.
8. `bun run build` and `bun run test` pass.

---

## UI-6: Categories screen

Covers F4.

### Goal

The "Kategorie" screen: list, add, rename and delete categories.

### Requirements

- Dependency `react-hook-form`.
- `src/services/categories-api.ts`: `categorySchema` (`id, name, createdAt, updatedAt`),
  `fetchCategories()`, `createCategory({ name })`, `updateCategory({ id, name })`,
  `deleteCategory(id)` (`GET`/`POST /api/categories/`, `PUT`/`DELETE /api/categories/{id}`).
- `src/hooks/use-categories.ts`: `useCategories()` (key `["categories"]`) and the three
  mutations, which invalidate `["categories"]` and `["clients"]`.
- Route `/categories` and the NavBar entry "Kategorie" (`Category` icon) under "Menu".
- The screen: `PageContainer` → `PageHeader` "Kategorie" with the action "Dodaj kategorię"
  *(new copy; the source names only the button's role)* → the list. Loading: `LoadingState`;
  error: `ErrorState` "Nie udało się załadować kategorii"; no categories: `EmptyState` "Brak kategorii" *(new copy)* with the add action.
- Table: columns **"ID" · "Nazwa kategorii" · "Akcje"** (icon buttons with `aria-label` "Edytuj kategorię" and "Usuń kategorię" *(new copy)*).
- `CategoryFormModal`: title "Dodaj nową kategorię" / "Edytuj kategorię"; one field "Nazwa kategorii" (required: "Nazwa kategorii jest wymagana" *(new copy)*; at most 64 characters);
  buttons "Anuluj" and "Dodaj" / "Zapisz" ("Zapisywanie…" while saving). [FIX] A 400 for a taken
  name shows its `detail` at the field (the mutation sets `meta.skipGlobalError`).
- `DeleteConfirmDialog` in `src/components/ui/` (shared with clients and campaigns, the text
  passed in): here "Czy na pewno chcesz usunąć kategorię „{categoryName}”?" plus [FIX]
  "Klienci przypisani do tej kategorii stracą ją." *(new copy)*; buttons "Anuluj" and "Usuń"
  ("Usuwanie…").
- A successful save or delete closes the dialog.

### Pitfalls

- `DELETE` answers 204 with no body (UI-5's `bffRequest` handles it).
- Don't pass names into the dialog under another component's prop name (the old code passed a
  campaign name as `clientName`); the shared dialog takes `title` and `message`.

### Depends on

UI-5, API-4.

### Acceptance criteria

1. Tests: the list renders; adding, renaming and deleting call the right endpoints and refresh
   the list; a duplicate name shows the API's message at the field and no snackbar; the empty,
   loading and error states.
2. In a browser with stubbed `/api/categories/` calls: the screen, both dialogs and the NavBar
   entry work in both themes and from the keyboard.
3. `bun run build` and `bun run test` pass.

---

## UI-7: Clients screen

Covers F5.

### Goal

The "Klienci" screen, the app's start page: a searchable, paginated client list with add, edit
and delete.

### Requirements

- `src/services/clients-api.ts`: `clientSchema` (the contract's `ClientSchema`),
  `fetchClients({ skip, limit, search })` → `Page<Client>`, `createClient(payload)`,
  `updateClient({ id, client })`, `deleteClient(id)`.
- `src/hooks/use-clients.ts`: `useClients(params)` (key `["clients", params]`) and the three
  mutations, which invalidate `["clients"]`.
- Route `/clients`; `/` now redirects there. NavBar entry "Klienci" (`People`) first under
  "Menu".
- Header: `PageHeader` "Klienci", subtitle "Zarządzaj bazą klientów ({count} klient/klientów)"
  (`pluralPl(count, "klient", "klientów", "klientów")`; `count` is the list's `total`), action
  `GradientButton` "Dodaj klienta"; the list below in a `ModernCard`.
- The list: `SearchInput` with the placeholder "Szukaj po nazwie, emailu, telefonie, firmie lub kategoriach…", debounced 500 ms. Loading: `TableSkeleton rows=5 columns=6`. No clients:
  `EmptyState` "Brak klientów" / "Nie masz jeszcze żadnych klientów. Dodaj pierwszego klienta, aby zacząć." with the action "Dodaj klienta". No search results: "Brak wyników" / "Nie znaleziono klientów pasujących do frazy „{query}”". Error: `ErrorState`.
- Table: **"Klient"** (an avatar with the initial and the company name) · **"Email"** ·
  **"Telefon"** ("—", greyed, when empty) · **"Kategorie"** (chips; "—" when none) ·
  **"Akcje"** (edit and delete icon buttons, `aria-label` "Edytuj klienta" / "Usuń klienta"
  *(new copy)*). [NEW] An inactive client shows the chip "Nieaktywny" *(new copy)*.
- Pagination: `TablePagination` with the options `[5, 10, 25, 50]`, 10 by default, the labels
  "Wierszy na stronie:" and "{from}-{to} z {count}". [FIX W-08, W-09] Paging and search run on
  the server (`skip`, `limit`, `search`, `total`); a new search goes back to page 0. No
  client-side filtering.
- `ClientFormModal` (react-hook-form, `mode: "onBlur"`), title "Dodaj klienta" / "Edytuj klienta", fields:
  - "Nazwa firmy" (required: "Nazwa firmy jest wymagana");
  - "Email" (required: "Email jest wymagany"; pattern `^[^\s@]+@[^\s@]+\.[^\s@]+$`:
    "Nieprawidłowy format email");
  - "Telefon";
  - "Kategorie" (a multi-select with removable chips, from `useCategories`);
  - [FIX W-01] "Dodatkowe adresy email", "Adres" and "Notatki" *(new copy)*, and [NEW] a switch
    "Aktywny" *(new copy)* (`isActive`, on by default).
  Buttons "Anuluj" and "Zapisz" (disabled while `!isDirty` or saving; "Zapisywanie…"). The
  form resets each time it opens. **`PUT` always sends every field** (W-01). A 400 "Client with email … already exists" shows at the email field.
- `DeleteConfirmDialog`: "Potwierdź usunięcie" / "Czy na pewno chcesz usunąć klienta **{clientName}**? Tej operacji nie można cofnąć." with "Anuluj" / "Usuń" ("Usuwanie…").
- A save or delete closes the dialog and refreshes the list.

### Pitfalls

- W-01: an edit that drops `additionalEmails`, `address` or `notes` clears them on the server.
- Keep the page in range after a delete empties the last page.
- The debounced value, not every keystroke, goes into the query key.

### Depends on

UI-6, API-5.

### Acceptance criteria

1. Tests (the old project had about 70 assertions in 4 files; keep that scope): rendering,
   debounced search sent to the API, pagination (`skip`/`limit` and the labels), the form's
   validations, edit mode filled from the client, `isDirty`, the full `PUT` payload, the
   duplicate email at the field, deleting, and the loading, empty, no-results and error states.
2. `/` opens the clients screen.
3. In a browser with stubbed `/api/clients/` and `/api/categories/` calls: the screen works in
   both themes and from the keyboard.
4. `bun run build` and `bun run test` pass.

---

## UI-8: SMTP settings screen

Covers F9.

### Goal

The "Ustawienia" screen: each user saves their SMTP settings and sends a test email.

### Requirements

- `src/services/smtp-config-api.ts`: `fetchEmailConfig()` (returns `null` when neither
  `smtpServer` nor `smtpUser` is set; otherwise the form values with `smtpPassword: ""`, never
  the password, and port 587 when unset), `updateEmailConfig(partial)` → `{ message }`,
  `testEmailConfig({ recipient })` → `{ success, message }`.
- `src/hooks/use-smtp-config.ts`: `useSmtpConfig()` (key `["smtpConfig"]`),
  `useUpdateSmtpConfig()` and `useTestSmtpConfig()`, which invalidate `["smtpConfig"]`; both
  mutations set `meta.skipGlobalError` (the screen shows its own alerts).
- Route `/settings`; NavBar entry "Ustawienia" under "Inne", before "Notatki"; the user menu
  gains "Ustawienia" (→ `/settings`) above "Wyloguj".
- The screen: a centred header (the `Settings` icon in an 80 px gradient square, the title
  "Ustawienia", the description "Konfiguracja serwera email SMTP"), then a card "Konfiguracja SMTP" with the `Email` icon:
  - "Serwer SMTP" (placeholder `smtp.gmail.com`);
  - "Port SMTP" (a number, placeholder `587`);
  - the `smtpUseTls` switch labelled "Użyj TLS (obecnie: włączone/wyłączone)" (the
    "obecnie" part only when settings exist), on by default, with [FIX W-13] the helper text
    "Szyfruj połączenie — port 587: STARTTLS, port 465: SSL";
  - "Email / Nazwa użytkownika" (placeholder `user@example.com`);
  - "Hasło" (placeholder "Hasło aplikacyjne", helper "Podaj hasło aplikacyjne SMTP", a
    show/hide button with the `Visibility` icon, `aria-label` "Pokaż hasło" / "Ukryj hasło"
    *(new copy)*);
  - the button "Zapisz konfigurację" (`Save` icon; "Zapisywanie…").
- A second card "Testuj połączenie", "Wyślij testową wiadomość email, aby sprawdzić poprawność konfiguracji SMTP": the field "Adres email do testu" (placeholder `test@example.com`) and the
  button "Testuj" (`Send` icon; "Wysyłanie…").
- Behaviour:
  - `GET /api/config/smtp` fills the form; **the password is never prefilled** and is cleared
    after saving;
  - save validation: "Serwer SMTP, port i nazwa użytkownika są wymagane"; "Hasło jest wymagane dla nowej konfiguracji" when no `smtpUser` is saved yet; [FIX] no email format check on the
    SMTP login;
  - only changed or non-empty fields are sent; an empty password means "don't change";
  - success: a green alert with the response's `message`, gone after 5 s; failure: a red alert
    with `detail`, or "Nie udało się zaktualizować konfiguracji" / "Test połączenia nie powiódł się";
  - test validation: "Podaj adres email do testu"; "Nieprawidłowy format adresu email";
  - loading: a centred `CircularProgress`.
- [ADAPT, D18] No client-side timeout: the API answers the test within 8 s, inside the BFF's
  10 s.

### Pitfalls

- The saved password is never sent back, so "has settings" is decided by `smtpServer` or
  `smtpUser`, not by the password.
- A partial `PUT` must not send an empty password, which the API rejects.
- The success texts are the API's English messages, shown as they come (D1).

### Depends on

UI-5, API-7, API-8.

### Acceptance criteria

1. Tests (the old `Settings.test.tsx` had 13 cases): rendering, filling from the API, the
   validations, the partial save payload, the password never prefilled and cleared after
   saving, the test email's success and failure, the alert texts.
2. The NavBar entry and the user menu item open the screen.
3. With `make docker-up`, the API and the BFF running, a signed-in user saves the smtp4dev values
   from `AGENTS.md`, sends a test email, and it shows up at http://localhost:5080.
4. `bun run build` and `bun run test` pass.

---

## UI-9: Campaign list

Covers F6 without the send and resend.

### Goal

The "Kampanie" screen: a searchable, paginated campaign table with status chips, stats, clone
and delete.

### Requirements

- Dependency `date-fns` (locale `pl`).
- `src/services/campaigns-api.ts`: `campaignSchema` with the status enum including `sending`,
  the recipients and the nullable stats; `fetchCampaigns({ skip, limit, search })` →
  `Page<Campaign>`, `fetchCampaign(id)`, `createCampaign(payload)`, `deleteCampaign(id)`,
  and `cloneCampaign(campaign)`, which builds `{ name: "{name} (kopia)", subject, content,
  recipientIds: recipients[].clientId }` (no `scheduledFor`) and calls `createCampaign`.
- `src/hooks/use-campaigns.ts`: `useCampaigns(params)` (key `["campaigns", params]`),
  `useCampaign(id)` (key `["campaigns", id]`), and the delete and clone mutations, which
  invalidate `["campaigns"]`.
- Route `/campaigns`; NavBar entry "Kampanie" (`Campaign`) after "Kategorie".
- Header: `PageHeader` "Kampanie", subtitle "Zarządzaj kampaniami email ({count} kampania/kampanii)" (`pluralPl(count, "kampania", "kampanie", "kampanii")`; the source has no "kampanie" form, so "3 kampanii" was wrong). (UI-11 adds the action "Nowa kampania".)
- Search (debounced 500 ms; on the server: name, subject, content) and pagination as in UI-7.
- Table: **"Nazwa"** · **"Temat"** · **"Odbiorcy"** ("{n} odbiorca/odbiorców":
  `pluralPl(n, "odbiorca", "odbiorców", "odbiorców")`) · **"Data utworzenia"** (`format(date, "P", { locale: pl })`) ·
  **"Status"** (chips: `sent` "Wysłana" green, `failed` "Błąd" red, `scheduled` "Zaplanowana"
  primary, `draft` "Szkic" grey, `sending` "W trakcie" *(new copy)* info) · **"Statystyki"**
  (chips "Wysłane: {n}", "Błędy: {n}" when above 0, "Oczekujące: {n}" when above 0, "Odbite: {n}" when above 0, and one `LinearProgress` of `stats.successRate` with the `aria-label` "Odsetek wysłanych" *(new copy)*; UI-10 shows the send progress in the same bar while `sending`) · **"Akcje"**.
- Actions in this item: "Klonuj kampanię" on every row [PARITY] (cloning only reads the
  campaign, so `sending` rows can be cloned too); "Usuń" on every row except `sending`. [FIX] The
  old UI hid "Usuń" on `sent` rows, but its own note says deleting follows the backend, which
  allows every status; the API refuses only `sending` (D17). (UI-10 adds "Wyślij kampanię" and
  "Wyślij ponownie", UI-12 "Edytuj", UI-13 the link on the name.)
- Clone: a snackbar "Kampania „{campaignName}” została sklonowana". Result snackbars here and
  in UI-10 sit at the bottom, last 4 s and use `variant="filled"`.
- Delete: `DeleteConfirmDialog` "Potwierdź usunięcie" / "Czy na pewno chcesz usunąć kampanię **{campaignName}**? Tej operacji nie można cofnąć." *(new copy, after the clients dialog)*.
- [FIX] An error shows a plain `ErrorState` with the button "Spróbuj ponownie" (refetch), not
  the old "Backend API Niedostępny" banner.
- [FIX] IDs are numbers in the schema; no casts.

### Pitfalls

- The API returns `sending` campaigns (a send started elsewhere): the schema and the chips must
  accept it.
- The edit page, the wizard and the email log don't exist yet: no links to them in this item.
- `["campaigns", params]` and `["campaigns", id]` share the prefix, so invalidating
  `["campaigns"]` refreshes both.

### Depends on

UI-6, UI-7, API-9.

### Acceptance criteria

1. Tests: each status's chip and colour; the stats chips' visibility rules; the actions per
   status; clone sends the right payload and shows the snackbar; delete with the dialog;
   debounced search and pagination; the error state's retry.
2. In a browser with a stubbed `/api/campaigns/` list covering all five statuses: the screen
   works in both themes, and at 375 px the table scrolls sideways inside its card.
3. `bun run build` and `bun run test` pass.

---

## UI-10: Campaign send and resend with status polling

Covers F6 (the send part).

### Goal

Send and resend a campaign from the list, and watch it while the API sends in the background
(D17).

### Requirements

- `campaigns-api.ts`: `sendCampaign(id)` and `resendCampaign({ campaignId, recipientIds? })`
  (body `{ recipientIds }` or `{}`), both → the `202` campaign.
- Hooks: `useSendCampaign()` and `useResendCampaign()` put the returned campaign into
  `["campaigns", id]` and invalidate `["campaigns"]`; both set `meta.skipGlobalError` (the page
  shows the result).
- Row actions: `draft` → "Wyślij kampanię"; `failed` → "Wyślij ponownie" (to every failed
  recipient). Both are disabled while the campaign is `sending` or its request is running
  (tooltip "Wysyłanie…", on a `<span>` around the button).
- Send: with no recipients, the snackbar "Nie można wysłać kampanii bez odbiorców"; otherwise
  `SendConfirmDialog`: title "Potwierdź wysyłkę kampanii", "Czy na pewno chcesz wysłać kampanię **{campaignName}**?", a box "Szczegóły:" with "• Temat: {subject}" and "• Liczba odbiorców: {n}" and the chip "{n} email/emaili zostanie wysłany" (`pluralPl(n, "{n} email zostanie wysłany", "{n} emaile zostaną wysłane", "{n} emaili zostanie wysłanych")`; the last two forms are *(new copy)*), buttons "Anuluj" and "Wyślij teraz"
  ("Wysyłanie…"; both disabled during the request).
- After the `202`: the row shows the chip "W trakcie", and the stats column's one bar becomes a
  determinate `LinearProgress` of `stats.progressPercentage` with the `aria-label` "Postęp wysyłki" *(new copy)* (instead of UI-9's `successRate`). Each `sending` row polls
  `GET /api/campaigns/{id}` with TanStack Query's `refetchInterval` (2000 ms while
  `status === "sending"`, else `false`). When polling sees the final status, the page
  invalidates `["campaigns"]`, `["emails"]` and `["emailStats"]`.
- Failed polls: the poll query sets `meta.skipGlobalError` and `retry: false` and keeps the last
  campaign it got. After 3 failed polls in a row, the row hides its bar and shows the warning
  "Nie można odświeżyć postępu. Odśwież stronę." *(new copy)*. Polling goes on every 2 s, and
  the first successful poll removes the warning and brings the bar back. No error snackbar
  repeats every 2 s.
- Result snackbars (bottom, 4 s, filled) for sends and resends started on this page, when
  polling sees the final status, with `successCount = stats.sent` and `failedCount =
  stats.failed`:
  - `failedCount === 0` → success "Kampania wysłana — {successCount} wiadomości" (resend:
    "Kampania wysłana pomyślnie — {successCount} wiadomości");
  - `successCount > 0` → warning "Wysłano częściowo: {successCount} wysłanych, {failedCount} błędów";
  - otherwise error "Wysyłka nieudana — sprawdź konfigurację SMTP" (resend: "Wysyłka nieudana — {failedCount} błędów").
  A campaign that was already `sending` when the page loaded is polled and refreshed, without a
  snackbar.
- An HTTP error when starting shows its `detail`, except that a `detail` containing
  `current status: sent` shows the success "Kampania została już pomyślnie wysłana"; without a
  `detail`: "Błąd podczas wysyłania kampanii" / "Błąd podczas ponownego wysyłania kampanii".
  When the `detail` starts with "SMTP configuration not found", the snackbar also has the action
  "Przejdź do ustawień" *(new copy)*, which opens `/settings`.

### Pitfalls

- Stop polling when the status leaves `sending` or the row unmounts; never poll a campaign that
  isn't `sending`.
- The stats are the whole campaign's, so a resend's snackbar counts every recipient, not only
  this run.
- A second click must not start a second send: the button is disabled, and the API answers 400
  "current status: sending" anyway.

### Depends on

UI-9, API-11, API-12.

### Acceptance criteria

1. Tests with fake timers and a stubbed API that answers `sending` twice and then the final
   campaign: the chip "W trakcie" and the progress show, polling runs every 2 s and stops, and
   each of the three snackbars (success, partial, failure) appears for send and resend with the
   right texts.
2. Tests: the no-recipients snackbar; the dialog's texts and disabled buttons; the `current
   status: sent` case; the buttons are disabled while `sending`; `["emails"]` and
   `["emailStats"]` are invalidated at the end; a `sending` row shows one bar, of
   `progressPercentage`; the "Przejdź do ustawień" action opens `/settings`.
3. Tests with fake timers and a poll that fails 3 times, then succeeds: no error snackbar, the
   warning shows after the third failure, and it goes away with the bar back after the success.
4. End to end with `make docker-up`, the API and the BFF, smtp4dev configured: sending a seeded
   campaign shows "W trakcie", then "Wysłana", and the mail arrives in smtp4dev.
5. `bun run build` and `bun run test` pass.

---

## UI-11: Campaign wizard (create)

Covers F7.

### Goal

Create a campaign in four steps, with a sanitized preview.

### Requirements

- Dependency `dompurify`.
- Route `/campaigns/new`; the campaign list's header gains the action "Nowa kampania" (→
  `/campaigns/new`).
- Header: "Nowa kampania email" / "Utwórz i wyślij nową kampanię emailową do wybranych odbiorców".
- `CampaignWizard({ steps, onSubmit, onCancel, isSubmitting, submitLabel })`
  (`src/components/campaigns/wizard/`): an MUI `Stepper` (the `CheckCircle` icon on finished
  steps), the step description under it, validation of the step on "Dalej" (error: "Wypełnij wszystkie wymagane pola przed przejściem dalej"; on submit: "Wypełnij wszystkie wymagane pola przed utworzeniem kampanii"), buttons "Anuluj", "Wstecz", "Dalej", and on the last step
  "Utwórz kampanię" ("Zapisywanie…").
- One react-hook-form form: `name, subject, content, recipientIds, scheduledFor`. Steps:
  1. **"Podstawowe informacje"** (description "Nazwij kampanię i ustaw temat" *(new copy)*):
     "Nazwa kampanii" (required: "Nazwa kampanii jest wymagana"; helper "Nazwa widoczna tylko dla Ciebie, nie dla odbiorców"), "Temat wiadomości email" (required: "Temat email jest wymagany"; helper "To zobaczą odbiorcy w skrzynce odbiorczej"), "Data wysyłki"
     (`datetime-local`, optional; helper "Data jest tylko zapisywana — kampania nie zostanie wysłana automatycznie." *(new copy)*). Valid when `name && subject`. [FIX, D6] The new helper replaces the source's "Pozostaw puste aby zapisać jako szkic do późniejszej wysyłki", which suggests that a date schedules the send; nothing sends at that date.
  2. **"Treść wiadomości"** (description "Napisz treść wiadomości" *(new copy)*): an alert with
     the variables `{name}`, `{email}`, `{company}` (monospace chips) and "Użyj tych zmiennych aby spersonalizować wiadomość dla każdego odbiorcy" (the API substitutes them, D3); the
     content field (required: "Treść email jest wymagana"; placeholder "Cześć {name}, …");
     [FIX W-06, D4] tabs "Edycja" / "Podgląd" and the hint "Możesz użyć HTML. Zwykły tekst zostanie zamieniony na HTML z zachowaniem nowych linii." *(new copy)*. Valid when
     `content`.
  3. **"Wybierz odbiorców"** (description "Określ kto otrzyma tę wiadomość"): the heading
     "Wybierz odbiorców" / "Dodaj odbiorców według kategorii lub wybierz indywidualnie"; tabs
     **"Kategorie"** (empty: "Brak dostępnych kategorii") and **"Klienci"** (search "Szukaj klienta…"); checkbox lists; a panel "Podsumowanie" with "Wybrani odbiorcy:" and the count,
     and "Wybierz co najmniej jednego odbiorcę" at zero. Valid with at least one recipient.
  4. **"Przejrzyj i zatwierdź"** (description "Sprawdź wszystko przed zapisaniem" *(new
     copy)*): the heading "Sprawdź i zatwierdź" / "Przejrzyj wszystkie szczegóły przed utworzeniem kampanii"; the fields "Nazwa kampanii", "Temat wiadomości", "Status wysyłki"
     (always the chip "Zapisz jako szkic"; with a date, the plain text "Zapisana data wysyłki: {date}" *(new copy)* next to it), the content preview, "{n} odbiorca/odbiorców",
     "Wiadomość zostanie wysłana do {n} osoby/osób" (`pluralPl(n, "osoby", "osób", "osób")`) and
     the recipient list. [FIX, D6] The source showed the chip "Zaplanowana" when a date was set;
     the campaign is saved as a draft either way, so that chip would promise a send that never
     happens.
- Recipient selection [FIX]: the state is one set of `selectedClientIds`. Toggling a category
  adds or removes its active clients; a category shows as checked when all its active clients
  are selected. The result is the union of category and individual choices [PARITY]. Category
  membership comes from each client's `categories`.
- Clients for step 3: every client, fetched page by page (`limit=1000`) until `total` is
  reached [FIX: the old `limit: 1000` cut larger bases]. Inactive clients are listed with the
  chip "Nieaktywny" and are not added by category toggles.
- [FIX W-03] Both previews render the content sanitized with DOMPurify.
- Submit: `createCampaign({ name, subject, content, recipientIds, scheduledFor })` with
  `scheduledFor` as an ISO string or left out; on success invalidate `["campaigns"]`, go to
  `/campaigns` and show the snackbar "Kampania została utworzona" *(new copy)*. "Anuluj" goes
  back to `/campaigns`.

### Pitfalls

- W-03: never `dangerouslySetInnerHTML` without DOMPurify; `<script>` and `on*` attributes must
  not reach the DOM.
- `datetime-local` has no timezone: convert with `new Date(value).toISOString()`.
- `scheduledFor` is stored only; nothing will send at that time (D6). The copy must not promise
  a scheduled send: no "Zaplanowana" chip in the wizard.
- Keep each step under about 250 lines; the old wizard was the largest component.
- Keyboard: the stepper buttons, tabs and checkboxes work without a mouse (F12).

### Depends on

UI-9, UI-7, API-9.

### Acceptance criteria

1. Tests: moving between steps and each step's validation message; the submit message.
2. Tests of the selection logic: a category selects its active clients; deselecting one client
   unchecks the category but keeps the others; the union of categories and clients.
3. The request payload, with and without a date.
4. Sanitizing: content with `<script>` and `<img onerror>` renders neither in the preview.
5. In a browser with stubbed clients, categories and `POST /api/campaigns/`, the wizard works
   end to end in both themes and from the keyboard.
6. `bun run build` and `bun run test` pass.

---

## UI-12: Campaign wizard (edit)

Covers F7 (the edit mode).

### Goal

Edit a `draft` campaign with the same wizard.

### Requirements

- Route `/campaigns/edit/:id`; the campaign list's rows gain "Edytuj" for `draft` only [FIX
  W-16].
- Header: "Edytuj: {campaignName}" / "Zaktualizuj szczegóły kampanii emailowej". Step 3 is
  named "Zaktualizuj odbiorców", step 4 "Przejrzyj zmiany"; the submit button is "Zapisz zmiany".
- Load the campaign with `useCampaign(id)` (a `CircularProgress` meanwhile). Not found: an alert
  "Kampania o ID **{id}** nie została znaleziona" and the button "Powrót do kampanii". Not a
  `draft`: the alert "Można edytować tylko kampanie w statusie szkicu." *(new copy)* and the same
  button.
- The form starts from the campaign: `recipientIds` from `recipients[].clientId`,
  `scheduledFor` converted to a local `datetime-local` value.
- Submit: `updateCampaign(id, payload)` (`PUT /api/campaigns/{id}`); a cleared date sends
  `"scheduledFor": null` (the API clears it); then invalidate `["campaigns"]`, go to
  `/campaigns` and show the snackbar "Kampania została zapisana" *(new copy)*. A 400 ("Only draft campaigns can be modified", "Campaign is being sent") shows
  through the global snackbar.

### Pitfalls

- An omitted `scheduledFor` means "unchanged" and `null` means "clear" (the contract's
  `CampaignUpdateSchema`).
- Initialise categories from the selected clients with the same rule as in UI-11; no heuristics
  (the old edit mode guessed them).

### Depends on

UI-11.

### Acceptance criteria

1. Tests: the form starts from the campaign's data; the payload; clearing the date sends `null`;
   the not-found and non-draft alerts; "Edytuj" shows only for drafts; the success snackbar.
2. In a browser with stubbed calls, editing a draft works in both themes.
3. `bun run build` and `bun run test` pass.

---

## UI-13: Email log screen

Covers F8.

### Goal

A campaign's email log: its stats, a paginated list, and resending one failed email.

### Requirements

- `src/services/emails-api.ts`: `emailSchema`, `emailStatsSchema`, `fetchEmails({ skip,
  limit, search, campaignId })` → `Page<Email>` (`GET /api/emails/?campaign_id=…`),
  `fetchEmailStats(campaignId)` (`GET /api/emails/stats/?campaign_id=…`; never computed in the
  browser, W-09), `resendEmail(id)`.
- `src/hooks/use-emails.ts`: `useEmails(params)` (key `["emails", params]`),
  `useEmailStats(campaignId)` (key `["emailStats", campaignId]`), `useResendEmail()`, which
  invalidates `["emails"]` and `["emailStats"]`. Both queries use `staleTime: 0`, so opening the
  log always shows the current rows, even after a send that finished while the list wasn't
  polling.
- Route `/emails?campaignId={id}`; without the parameter it redirects to `/campaigns`. [FIX] The
  only entry is the campaign list: the name of a `sent` **or `failed`** campaign links here
  (D26). No NavBar entry; on this route "Kampanie" is active. No global log (its old code was
  unreachable and is not ported).
- `EmailsHeader`: a back button (tooltip "Wróć do kampanii"; `navigate(-1)` when the app has
  history, else `/campaigns`, so a reload or a pasted link never leaves the app), breadcrumbs
  "Kampanie" › {campaignName} (from `useCampaign`), the title "Historia Emaili", the subtitle
  "Przeglądaj historię wysłanych emaili ({n} email/emaile/emaili)"
  (`pluralPl(n, "email", "emaile", "emaili")`; the old code wrongly gave "emaile" for 0, and the
  source's rule "2 to 4" missed 22 to 24).
- `EmailStatsCards`: `StatsCard`s for **"Łącznie" · "Wysłane" · "Błędy" · "Oczekujące" ·
  "Odrzucone"** (= `bounced`), with loading and error states. [D8] "Otwarte" and "Kliknięcia"
  are hidden.
- Search: `SearchInput` (default placeholder), debounced, on the server.
- Table: **"Kampania"** · **"Temat"** · **"Odbiorca"** (client name and email) · **"Status"** ·
  **"Wysłano"** · **"Akcje"**. [D8] The old "Aktywność" column (opened and clicked) is hidden.
  - Status: `sent` green "Wysłany" ("Dostarczony" when `deliveredAt` is set); `failed` red
    "Błąd" with the error message below; `bounced` orange "Odrzucony"; `sending` primary
    "Wysyłanie"; anything else grey "Oczekujący". Every `EmailStatus` value is handled.
  - Dates `dd MMM yyyy, HH:mm` (locale `pl`), "—" when empty.
  - "Wyślij ponownie" only for `failed`, behind [FIX] a dialog (not `window.confirm`): "Czy na pewno chcesz wysłać ponownie email do {clientName}?" with "Anuluj" and "Wyślij ponownie".
- [FIX] Server pagination with the options 25, 50 and 100 (25 by default) and the UI-7 labels;
  the old view loaded up to 10 000 rows.
- States: "Brak emaili dla tej kampanii" / "Ta kampania nie ma jeszcze wysłanych emaili.";
  "Brak wyników" / "Nie znaleziono emaili pasujących do frazy „{query}”".

### Pitfalls

- The single resend is synchronous and takes up to 8 s: keep the dialog's button in a loading
  state until it answers.
- `delivered` is not a status; it is `deliveredAt != null`.
- Use `campaign_id` (snake_case) in the query string.

### Depends on

UI-9, API-10, API-13.

### Acceptance criteria

1. Tests: every status's label and colour; "Wyślij ponownie" only for `failed`; the resend
   dialog calls `POST /api/emails/{id}/resend` and refreshes; the `campaignId` reaches the API
   as `campaign_id`; no parameter redirects to `/campaigns`; the subtitle's three plural forms;
   the empty and no-results states; "Otwarte" and "Kliknięcia" are absent; the back button goes
   to `/campaigns` when the log is the first page; the breadcrumbs name the campaign.
2. The names of `sent` and `failed` campaigns link to the log; "Kampanie" is active there.
3. End to end with smtp4dev: after a partial failure, the log shows the failed email, and
   resending it after fixing the settings turns it into "Wysłany".
4. `bun run build` and `bun run test` pass.
