# Mission

Why this repo exists, who it serves, and the principles every spec respects.
With `AGENTS.md` (how to set up, run and test it) and the roadmap in
`factory/backlog.md`, this is the repo's constitution. What each feature does and
why is in `specs/features/`.

## Why this repo exists

Two things that grow together:

1. **The software factory** (`.claude/`, `factory/`): a small, visual
   spec → build → review → approve loop for Claude Code that can be copied into
   any repo.
2. **The OAuth/OIDC Backend-for-Frontend demo** (`bff/`, `api/`, `web/`,
   `keycloak/`): a full-stack app the factory builds on. It shows a browser app
   signing in with OIDC without ever handling tokens, and gives the factory real
   code, real security concerns and real pages to work on. The app built on the
   BFF is the Email Sender: clients, categories and email campaigns sent through
   the user's own SMTP server, specified in `specs/email-sender/`. It sits
   alongside the original notes demo.

## Who it is for

- Developers who want feature work done by agents, with a human only at the
  decisions that need one.
- Developers learning the Backend-for-Frontend pattern for OAuth/OIDC.

## Principles

A feature that has to break one of these says so in its spec's Assumptions, so
the approver escalates it.

- Tokens never reach the browser. The BFF is the OAuth confidential client and
  keeps tokens in its server-side session; the SPA holds only an HttpOnly
  session cookie.
- The SPA talks to the backend only through `/bff/*` and `/api/*` (the BFF
  proxy). The backend is API-only and serves no frontend files.
- Everything here is for development. Demo users, demo secrets and the dev
  Keycloak realm live in git; real secrets only ever go in ignored `.env` files.
- Everything the repo starts listens on 127.0.0.1 only: dev servers, the
  dashboard and published container ports. Demo credentials are in git, so
  nothing may be reachable from the local network.
- The stack runs three ways: on the host, in the sandbox and in the dev
  container. A change to how it runs keeps all three working and documented in
  `AGENTS.md`.
- UI copy is Polish. Code, docs and specs are English.
- The factory stays generic: its skill and agent files carry nothing
  repo-specific and read it from `AGENTS.md`, this file and `specs/`.
- The smallest change that fully meets the request, with no speculative options.

## Non-goals

- Production deployment: hosting, TLS, CI/CD, a production Keycloak, a shared
  session store.
- Real user management. The demo realm is the user store.
- A general agent framework. The factory stays one skill, a few agents and
  markdown files that a newcomer understands in a few minutes.
