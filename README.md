# Software Factory for Claude Code

A small, visual software factory built from one Claude Code skill, nine
subagents and plain markdown files. You type `/factory <feature>` and agents
write a spec, build it on its own branch, review it from four angles, and either
merge it to `main` or hand it to you.

```
feature → spec-writer → builder → [security, ux, ui, code] → WAIT FOR ALL
                           ▲                                      │
                           └──── any CHANGES: resume builder ◄────┤
                                                                  ▼ all PASS
                                     merge to main ◄─ APPROVE ─ approver ─ ESCALATE → needs-human
```

This folder is laid out like a repo root, so you can copy it straight into
yours.

```
.claude/
  skills/factory/SKILL.md        the orchestrator: runs the loop, writes job.json
  agents/                        one file per agent in the loop
    spec-writer.md               opus    writes spec.md
    builder.md                   opus    commits on factory/<job-id>, writes build.md
    reviewer-security.md         opus    writes round-N/review-security.md
    reviewer-ux.md               sonnet  writes round-N/review-ux.md
    reviewer-ui.md               sonnet  writes round-N/review-ui.md
    reviewer-code.md             sonnet  writes round-N/review-code.md
    approver.md                  opus    writes decision.md
    replanner.md                 opus    writes factory/replans/<date>.md (/factory replan)
    constitution-writer.md       opus    drafts AGENTS.md, specs/mission.md, backlog phases (/factory init)
factory/
  backlog.md                     queue for /factory next
  dashboard.html                 the visual board
  serve.py                       serves the dashboard, takes its Approve / Rework requests
  jobs/                          one folder per job (two examples included)
BUILD_PROMPT.md                  the prompt that built the original factory
```

## How it works

- The Claude Code session that runs `/factory` becomes the orchestrator. It
  spawns every agent and is the only writer of the job's `job.json`.
- Agents get their context from files, not the conversation, and each writes
  only its own file. Every review starts with `VERDICT: PASS` or
  `VERDICT: CHANGES`; `decision.md` starts with `APPROVE` or `ESCALATE`.
- The four reviewers run in parallel. A round is done only when all four files
  exist. If any says CHANGES, the same builder is resumed (at most twice).
- The builder's first commit is the spec, at `specs/features/<job-id>.md`, so
  every merged feature keeps its spec in the repo next to its code. The rest of
  the job folder is runtime state that stays out of git.
- When a request is really several jobs, the spec-writer splits it: it lists
  them as backlog items instead of writing a spec, and the factory adds them to
  `factory/backlog.md` for `/factory next`.
- Each job gets its own git worktree next to your repo
  (`../<repo>-factory/<job-id>/`) on a `factory/<job-id>` branch. Open several
  Claude sessions and run `/factory` in each to build features in parallel.

## Commands

```
/factory <feature>               run a new job through the loop
/factory next                    run the first unchecked item in factory/backlog.md
/factory plan <feature|next>     the same, but stop after the spec for you to read it
/factory go <job-id>             build a job whose spec you have read
/factory approve <job-id>        merge a needs-human job into main
/factory rework <job-id> <note>  send a job back with feedback: to the spec-writer
                                 from spec review, to the builder from needs-human
/factory init                    once per repo: draft the missing constitution
/factory replan                  between jobs: propose changes to the roadmap,
                                 the constitution and the factory itself
```

Use `/factory plan` when the request leaves product decisions open, or when a
wrong spec would be expensive. The job waits in **Spec review** on the
dashboard; edit `spec.md` by hand if you like, then run `/factory go`.

Run `/factory replan` every few jobs. The replanner reads the jobs finished since
the last replan and proposes edits: backlog items that are done or too big,
docs that merged work made stale, and review findings that keep recurring and
belong in an earlier step. It edits nothing; you pick what gets applied.

## Use it in your repo

1. Copy `.claude/` and `factory/` into your repo root.
2. Delete the example jobs in `factory/jobs/` and the checked items in
   `factory/backlog.md`.
3. Add `/factory/jobs/` and `/factory/replans/` to your `.gitignore`. They are
   runtime state.
4. Run `/factory init`. It drafts, from your code, whatever is missing of the
   repo's constitution: `AGENTS.md` (how to set up a fresh checkout, start the
   dev server on a given port, and run your tests, build and lint),
   `specs/mission.md` (why the repo exists, its principles and non-goals) and
   phases in `factory/backlog.md` (a `## ` heading with the goal below it).
   Read and correct the drafts. The agents carry nothing repo-specific; they
   read all of it from there. The spec-writer keeps specs within the mission
   and the approver escalates any change that breaks it.
5. Install the [`agent-browser`](https://github.com/vercel-labs/agent-browser)
   CLI if your project has pages to look at. The builder and the UX and UI
   reviewers use it to check the running app.
6. Commit everything on `main`, then run `/factory <feature>`.

The review checklists are deliberately general. Ask Claude to tailor them to
your stack: your framework, your security hot spots, and what the approver
should always escalate.

## Dashboard

```bash
python3 factory/serve.py            # from the repo root; --port 8090 for another port
```

Open <http://127.0.0.1:8000/dashboard.html>. Jobs move across the stages as
cards, review chips fill in as verdicts land, and jobs that need you stand out.
Click a card to read its markdown files. It polls every two seconds, so leave it
open while jobs run.

A card in **Needs human** has **Approve** and **Rework** buttons. Approve asks
for confirmation; Rework opens a note field for the builder. Either one writes
`factory/jobs/<job-id>/human-request.json`, and the card then shows the request
as sent. The orchestrator session waiting on that job picks the file up, deletes
it, and runs `/factory approve` or `/factory rework` for you. The server never
merges, runs git or touches `job.json`. Typing the commands still works.

`serve.py` uses only the Python standard library and serves `factory/` like
`http.server`. It listens on 127.0.0.1 only. A request is accepted only with an
`Origin` of `http://127.0.0.1:<port>` or `http://localhost:<port>` and the
token the server generates at each start and puts into the dashboard page, so
other websites can't make it write anything. It refuses a second request while
one is waiting.

In this repo, `make dashboard` runs it from the repo root (pick another port
with `make dashboard DASHBOARD_PORT=8090`).
`make web` starts the web dev server, `make web-build` makes a production build
of `web/`, and `make help` lists the other targets. `make sandbox-up` runs the
demo app's full stack (Keycloak, PostgreSQL, smtp4dev, API, BFF and web) in containers
under Podman; see AGENTS.md. `.devcontainer/` is a dev container (with Keycloak,
PostgreSQL and smtp4dev) for coding on the demo app under Docker or Podman; see AGENTS.md.

## The example jobs

Both came from running the factory on [zazencodes.com](https://zazencodes.com),
a Vue + Firebase site. Serve the dashboard from this folder to click through
them.

- **001-blog-reading-time** passed all four reviews in round 1, but the approver
  escalated it because it edited a prerender script, which counts as a deploy
  change. A human read `decision.md` and ran `/factory approve`.
- **002-not-found-page** passed review and the approver merged it to `main` on
  its own.

## BUILD_PROMPT.md

The prompt used to build the original factory, kept verbatim for reference.
If you are copying this folder as a template, ignore it.

The factory has grown since then: it now runs each job in its own git worktree
and gives every job its own `job.json`, instead of the single `board.json` the
prompt describes, so several jobs can run at once.
