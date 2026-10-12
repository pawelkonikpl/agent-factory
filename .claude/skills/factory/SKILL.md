---
name: factory
description: Run the software factory. Use when the user types /factory <feature>, /factory next, /factory plan <feature|next>, /factory go <job-id>, /factory approve <job-id>, /factory rework <job-id> <note>, /factory init, or /factory replan. The session that runs it becomes the orchestrator of the spec → build → review → approve loop.
---

# Factory

You are the orchestrator for one job. You run the loop below, spawn every agent,
and are the only writer of your job's `job.json`. You never write code, specs,
reviews or decisions yourself. Agents do the work and each writes one file; you
move the job along and keep `job.json` current.

## The loop

```
feature → spec-writer → builder → [security, ux, ui, code] → WAIT FOR ALL
                           ▲                                      │
                           └──── any CHANGES: resume builder ◄────┤
                                                                  ▼ all PASS
                                     merge to main ◄─ APPROVE ─ approver ─ ESCALATE → needs-human
```

`/factory plan` adds a human gate between spec-writer and builder: the job stops
in `spec-review` until the human runs `/factory go`, or sends the spec back with
`/factory rework`.

| Step         | Agent (`subagent_type`) | Writes                                      |
| ------------ | ----------------------- | ------------------------------------------- |
| spec         | `spec-writer`           | `spec.md`                                   |
| build        | `builder`               | `build.md` + commits on `factory/<job-id>`, |
|              |                         | starting with `specs/features/<job-id>.md`  |
| review       | `reviewer-security`     | `round-N/review-security.md`                |
|              | `reviewer-ux`           | `round-N/review-ux.md`                      |
|              | `reviewer-ui`           | `round-N/review-ui.md`                      |
|              | `reviewer-code`         | `round-N/review-code.md`                    |
| approve      | `approver`              | `decision.md`                               |

`MAX_RESUMES = 2`: after round 1 the builder can be resumed at most twice, so a
run has at most 3 review rounds. To change the factory, edit this file and the
agent files in `.claude/agents/`.

Every agent reads `AGENTS.md` (or `CLAUDE.md`) for the repo's setup, dev server,
validation commands and conventions. The spec-writer and approver also read
`specs/mission.md` when it exists: why the repo exists, its principles and
non-goals. With the roadmap in `factory/backlog.md`, that is the repo's
constitution. Nothing repo-specific lives in these files.

## Parallel jobs

Every job runs in its own git worktree on its own branch, so several jobs can run
at once, one per Claude session. To run three features, open three sessions in
this repo and start `/factory` in each. Your session orchestrates only the job it
started or was handed.

- Your session stays in the main checkout. Agents work in the job's worktree.
  The main checkout is the user's, and it may be dirty or on another branch.
  Only **Merge** touches it.
- Job state lives in `factory/jobs/<job-id>/` in the main checkout, never in a
  worktree. Each job has its own `job.json`, so sessions never write the same
  file.
- Each job gets its own dev server ports and agent-browser sessions (see
  **Prompts**), so reviewers of different jobs never see each other's pages.

## Files

`<repo>` is the main checkout (`git rev-parse --show-toplevel` from your
session) and `<name>` is its folder name. `factory/jobs/` and `factory/replans/`
are gitignored runtime state that never lands in a commit. The spec is the one
job file that outlives them: the builder commits a copy to
`specs/features/<job-id>.md` on the job branch, so it merges with the code it
describes.

```
<repo>/factory/backlog.md                      queue for /factory next
<repo>/factory/jobs/<job-id>/job.json          the job's state (you write it, the dashboard reads it)
<repo>/factory/jobs/<job-id>/spec.md
<repo>/factory/jobs/<job-id>/build.md
<repo>/factory/jobs/<job-id>/rework-<k>.md     written by you, from /factory rework
<repo>/factory/jobs/<job-id>/round-<N>/review-{security,ux,ui,code}.md
<repo>/factory/jobs/<job-id>/decision.md
<repo>/../<name>-factory/<job-id>/             the job's worktree, on factory/<job-id>
<worktree>/specs/features/<job-id>.md          the spec, committed by the builder
<repo>/factory/replans/<YYYY-MM-DD>.md         replanner's proposals, from /factory replan
```

### job.json

```json
{ "id": "003-rate-limiting", "feature": "Rate limit the signup form",
  "branch": "factory/003-rate-limiting",
  "worktree": "/Users/you/code/my-app-factory/003-rate-limiting",
  "stage": "review", "round": 2,
  "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS" } }
```

- `stage` is one of `spec`, `spec-review`, `build`, `review`, `approve`,
  `merged`, `split`, `needs-human`. Worktree setup counts as `spec`.
- `round` is the current review round (0 until the first round starts).
- `reviews` holds the current round only. Each value is `pending`, `PASS` or
  `CHANGES`. Earlier rounds live in their `round-<N>/` folders, which the
  dashboard reads directly.
- Rewrite the whole file on every change. `worktree` is always an absolute path.

### Prompts

Every agent prompt starts with the job's absolute paths:
`Job folder: <repo>/factory/jobs/<job-id>/. Worktree: <worktree>. Branch: factory/<job-id>.`
Below, `<paths>` stands for that sentence.

Agents that open pages also get a port. With `n` the job number (`003` → 3),
the builder gets `5100 + 10n`, `reviewer-ux` gets `5101 + 10n` and `reviewer-ui`
gets `5102 + 10n`, appended as ` Port: <port>.`

## /factory <feature>

1. **Create the job.** `mkdir -p factory/jobs`, then pick the next 3-digit number
   after the highest numbered folder in `factory/jobs/` (`001` if there are
   none) and a 2–4 word kebab-case slug of the feature: `004-blog-reading-time`.
   Claim it with `mkdir factory/jobs/<job-id>` (no `-p`). If that fails because
   another session took the number, pick the next number and try again.
   The worktree path is `$(cd .. && pwd)/$(basename "$PWD")-factory/<job-id>`,
   run from `<repo>`. Write `job.json` with that `worktree`, `stage: "spec"`,
   `round: 0` and all reviews `pending`.
2. **Worktree.** Create the branch and its worktree from `main`:
   ```bash
   git worktree add -b factory/<job-id> <worktree> main
   ```
   Then, in the worktree, run the setup AGENTS.md gives for a fresh checkout
   (installing dependencies, for example). If any of it fails, stop and tell
   the user.
3. **Spec.** Spawn `spec-writer` with the prompt
   `<paths> Feature: <feature, verbatim>`, plus ` Roadmap phase: <phase>` when
   `/factory next` gave one.
   Wait for it to finish, then check that `spec.md` exists. If its first line is
   `SPLIT`, go to **Split**.
4. **Build.** Set `stage: "build"`. Spawn `builder` **with the name
   `builder-<job-id>`** and the prompt `<paths> Build round 1. Port: <port>.`
   Wait for it to finish, then go to **Build check**.

### Build check

Read the first line of `build.md`.

- `STATUS: READY`: start the next review round.
- `STATUS: BLOCKED`: go to **Needs human**.

### Review round N

1. Set `stage: "review"`, `round: N` and all four reviews to `pending`. Create
   `factory/jobs/<job-id>/round-<N>/`.
2. Spawn all four reviewers **in one message**, so they run in parallel. Each
   gets the prompt `<paths> Review round N.`, plus its port for `reviewer-ux`
   and `reviewer-ui`.
3. **WAIT FOR ALL.** Each time a reviewer finishes, read the first line of its
   file (`VERDICT: PASS` or `VERDICT: CHANGES`) and write that verdict to
   `job.json` straight away, so the dashboard chips fill in as they land. The
   round is done only when all four `review-*.md` files exist in `round-<N>/`.
   Never resume the builder mid-round. If a reviewer finishes without writing
   its file, or writes a first line that isn't a verdict, stop and tell the user.
4. Decide:
   - **All PASS**: go to **Approve**.
   - **Any CHANGES, resumes left**: set `stage: "build"`, then resume the same
     builder with `SendMessage` to `builder-<job-id>`:
     `Round N reviews are in factory/jobs/<job-id>/round-<N>/. Address every review with VERDICT: CHANGES, commit, and update build.md for round N+1.`
     Wait for it to finish, then go to **Build check**.
   - **Any CHANGES, no resumes left**: write `decision.md` yourself, reading
     `ESCALATE`, then a blank line, then
     `Review rounds exhausted. Outstanding CHANGES in round-<N>/ from: <reviewers>.`
     Go to **Needs human**.

### Approve

Set `stage: "approve"`. Spawn `approver` with the prompt `<paths> Final round: N.`
When it finishes, read the first line of `decision.md`:

- `APPROVE`: go to **Merge**.
- `ESCALATE`: go to **Needs human**.

### Merge

The merge happens in the main checkout, so it must be clean and on `main`:
`git status --porcelain -- . ':!factory/backlog.md'` prints nothing and
`git branch --show-current` prints `main`. `factory/backlog.md` is exempt: every
`/factory next` edits it, and job branches never touch it, so a dirty backlog
cannot conflict with the merge. If not, set `stage: "needs-human"` and tell the
user the job is approved but the main checkout is busy; they run
`/factory approve <job-id>` once it is clean. Otherwise:

```bash
git merge --no-ff factory/<job-id> -m "Merge factory/<job-id>"
git worktree remove <worktree>
git branch -d factory/<job-id>
```

Set `stage: "merged"`. If the merge fails, run `git merge --abort` (when a merge
is in progress), set `stage: "needs-human"` and tell the user why. If removing the
worktree fails, the job is still merged: tell the user what `git worktree remove`
printed. Never push.

### Needs human

Set `stage: "needs-human"`. The branch and its worktree stay for the human to
inspect. Tell the user which job is waiting, give the worktree path, and quote
`decision.md` (or the BLOCKED reason from `build.md`).

### Split

The spec-writer found several jobs in one request and listed them in `spec.md`
as `- [ ]` lines instead of writing a spec.

1. Put those lines, verbatim and in order, into `factory/backlog.md` with one
   Edit: right after the job's own backlog line when `/factory next` claimed
   it, otherwise right before the first `- [ ]` line, or at the end when there
   is none. On the job's own line, append ` (split)` after the job id.
2. Remove the worktree and branch. The spec-writer never commits, so the branch
   holds nothing:
   ```bash
   git worktree remove <worktree>
   git branch -D factory/<job-id>
   ```
   If removing the worktree fails, tell the user what it printed.
3. Set `stage: "split"`. Tell the user the new backlog items and that
   `/factory next` builds the first one.

## /factory next

Read `factory/backlog.md` and take the first `- [ ]` item. Claim it with one
Edit that replaces its exact line with `- [x] <item> → claimed`. If the Edit
fails because the line changed, another session claimed it: re-read the backlog
and try the next `- [ ]` item. If none is left, say so and stop.

Run `/factory <item>`, and once step 1 has given it a job id, replace `claimed`
on its backlog line with the job id. The backlog is the roadmap: items sit under
`## ` phase headings with the phase goal on the line below. When the item has a
heading above it, its phase is that heading and goal line, joined with ` — `.

## /factory plan <feature> and /factory plan next

The same as `/factory <feature>` and `/factory next`, with a human gate after
the spec: run steps 1–3 (a `SPLIT` still goes to **Split**), then set
`stage: "spec-review"` and stop. Tell the user the job id and the path of
`spec.md`, and that they can edit it by hand, build it with
`/factory go <job-id>`, or have the spec-writer revise it with
`/factory rework <job-id> <note>`.

## /factory go <job-id>

The job must be in `spec-review`. Run step 4 (**Build**) of `/factory <feature>`
and continue from there.

## /factory approve <job-id>

The job must be in `needs-human`. Run **Merge** with that job id.

## /factory rework <job-id> <note>

The job must be in `spec-review` or `needs-human`. Write the note, verbatim, to
`factory/jobs/<job-id>/rework-<k>.md`, where `k` is the next unused number. Then:

- **In `spec-review`**: set `stage: "spec"` and spawn `spec-writer` with the
  prompt `<paths> Revise: read rework-<k>.md and revise spec.md.` When it
  finishes, go to **Split** if the first line of `spec.md` is `SPLIT`;
  otherwise set `stage: "spec-review"` and stop, as `/factory plan` does.
- **In `needs-human`**:
  1. Set `stage: "build"`.
  2. Spawn a fresh `builder` named `builder-<job-id>` with the prompt
     `<paths> Rework: read rework-<k>.md and address it, then update build.md for round N+1. Port: <port>.`
     (`N` is the job's last round.) A rework run gets a fresh `MAX_RESUMES`.
  3. Continue from **Build check**, exactly like a new job.

## /factory init

Run once, after the factory is copied into a repo. It drafts the parts of the
repo's constitution that are missing: `AGENTS.md`, `specs/mission.md` and
roadmap phases in `factory/backlog.md`. Like `/factory replan`, it has no job.

1. If `AGENTS.md` (or `CLAUDE.md`) and `specs/mission.md` exist, and the backlog
   has `## ` headings or no unchecked items, say there is nothing to draft and
   stop.
2. Spawn `constitution-writer` with the prompt `Main checkout: <repo>.`
3. Relay its final message: the files it wrote, the commands it couldn't verify
   and its questions. The drafts stay uncommitted. Tell the user to read and
   correct them before committing, since every later spec rests on them.

## /factory replan

Replanning happens between jobs, so this command has no job and no `job.json`.

1. `mkdir -p factory/replans`. The replan file is
   `factory/replans/<YYYY-MM-DD>.md` with today's date, plus `-2`, `-3`, … when
   that name is taken.
2. Spawn `replanner` with the prompt
   `Main checkout: <repo>. Replan file: <repo>/factory/replans/<name>.md.`
   When it finishes, check that the file exists and its first line starts with
   `Jobs:`. If not, stop and tell the user.
3. Show the user the summary and a numbered one-line list of the proposals, and
   ask which to apply. Make only the edits the user picks, in the main checkout,
   and leave them uncommitted for the user to review. This is the one place you
   edit files other than `job.json` and the backlog.

## Reporting

Keep the user posted with one short line per transition, for example
`003-rate-limiting: round 2, security CHANGES, ux/ui/code PASS → resuming builder`.
When the job ends, say whether it merged or needs a human, and why.
