# Software Factory for Claude Code

A small, visual software factory built from one Claude Code skill, seven
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
factory/
  backlog.md                     queue for /factory next
  dashboard.html                 the visual board
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
- Each job gets its own git worktree next to your repo
  (`../<repo>-factory/<job-id>/`) on a `factory/<job-id>` branch. Open several
  Claude sessions and run `/factory` in each to build features in parallel.

## Commands

```
/factory <feature>               run a new job through the loop
/factory next                    run the first unchecked item in factory/backlog.md
/factory approve <job-id>        merge a needs-human job into main
/factory rework <job-id> <note>  send a needs-human job back to the builder with feedback
```

## Use it in your repo

1. Copy `.claude/` and `factory/` into your repo root.
2. Delete the example jobs in `factory/jobs/` and the checked items in
   `factory/backlog.md`.
3. Add `/factory/jobs/` to your `.gitignore`. Job folders are runtime state.
4. Make sure your `AGENTS.md` (or `CLAUDE.md`) says how to set up a fresh
   checkout, start the dev server on a given port, and run your tests, build
   and lint. The agents carry nothing repo-specific; they read all of it from
   there.
5. Install the [`agent-browser`](https://github.com/vercel-labs/agent-browser)
   CLI if your project has pages to look at. The builder and the UX and UI
   reviewers use it to check the running app.
6. Commit everything on `main`, then run `/factory <feature>`.

The review checklists are deliberately general. Ask Claude to tailor them to
your stack: your framework, your security hot spots, and what the approver
should always escalate.

## Dashboard

```bash
cd factory && python3 -m http.server
```

Open <http://localhost:8000/dashboard.html>. Jobs move across the stages as
cards, review chips fill in as verdicts land, and jobs that need you stand out.
Click a card to read its markdown files. It polls every two seconds, so leave it
open while jobs run.

In this repo, `make dashboard` does the same from the repo root (bound to
127.0.0.1; pick another port with `make dashboard DASHBOARD_PORT=8090`).
`make web` starts the web dev server, `make web-build` makes a production build
of `web/`, and `make help` lists the other targets. `make sandbox-up` runs the
demo app's full stack (Keycloak, API, BFF and web) in containers under Podman;
see AGENTS.md. `.devcontainer/` is a dev container (with Keycloak) for coding on
the demo app under Docker or Podman; see AGENTS.md.

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

## Problem solver

`/solve` is a second loop, next to the factory, for technical problems that
need a diagnosis rather than a feature: a bug, a failing or flaky test, a
performance problem, or a technical question that needs an answer backed by
evidence. It is one more skill and six more subagents, in the same style as
the factory.

```
problem → analyst → brief.md (success criteria + checks, effort)
        → investigators (0–4, in parallel) → findings with numbered claims
        → solvers (1, or 3 with different approaches) → candidate branches
        → per candidate: verifier ∥ critic → PASS + STANDS = accepted
        → none accepted: resume the solvers (at most 3 rounds)
        → synthesizer → answer.md (answer, confidence, evidence) + lessons.md
```

```
.claude/
  skills/solve/SKILL.md            the orchestrator: runs the loop, writes job.json
  agents/
    solve-analyst.md               opus    writes brief.md
    solve-investigator.md          sonnet  writes findings-q<n>.md
    solve-solver.md                opus    commits on solve/<job-id>/c<k>, writes candidate-c<k>.md
    solve-verifier.md              sonnet  writes round-N/verify-c<k>.md
    solve-critic.md                opus    writes round-N/critique-c<k>.md
    solve-synthesizer.md           opus    writes answer.md and lessons.md
solve/
  evals/cases/<case-id>/           eval cases: problem.md plus the code
  evals/hidden/<case-id>.{sh,patch} graders and reference fixes (agents never read these)
  evals/selftest.sh                checks the graders themselves
  jobs/                            one folder per job (gitignored)
```

The design follows what research on LLM agents shows. A model rarely corrects
its own reasoning without outside feedback, so a fresh verifier runs the checks
and a critic tries to refute every candidate. Success criteria are written
before anyone solves. One solver is the default: several candidates pay off
only when a problem has several defensible answers, and extra agents make
step-by-step problems worse. Agents never talk to each other; they exchange
files through the orchestrator.

### Commands

```
/solve <problem>                 run a job through the loop
/solve apply <job-id> [c<k>]     merge the chosen candidate into main, then clean up
/solve clean <job-id>            remove the job's worktrees and branches
/solve eval [case-id]            run the eval cases through the full loop and grade them
/solve eval --baseline           the same with one solver and no verification loop
```

Each candidate gets its own worktree in `../<repo>-solve/<job-id>/c<k>/` on a
`solve/<job-id>/c<k>` branch. The solver never merges: you decide with
`/solve apply`. Each agent's model is set in its file's frontmatter; change it
there.

### Evals

`make solve-selftest` checks that every grader fails on its case and passes
with its reference fix. `/solve eval --baseline` followed by `/solve eval`
shows whether the full loop beats one solver working alone on the same cases.
Reports go to `solve/evals/runs/`, which is gitignored so a report never blocks
a `/factory` or `/solve` merge; keep one with `git add -f`.

The five cases are seeds. To add one, create `solve/evals/cases/<case-id>/`
with a `problem.md` written the way a user would report it, plus the code, and
add a grader `solve/evals/hidden/<case-id>.sh <checkout-root>` that exits 0
when the case is solved. Add the reference fix as `<case-id>.patch` (a
`git diff` from the repo root), then run `make solve-selftest`. Commit cases on
`main` before running evals. Graders stay hidden only because agents are told
not to read them.
