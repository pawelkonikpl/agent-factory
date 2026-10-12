---
name: solve
description: Run the problem solver on a technical or code problem in this repo, such as a bug, a failing or flaky test, a performance problem, or a technical question that needs an answer backed by evidence. Use when the user types /solve <problem>, /solve eval [case-id] [--baseline], /solve apply <job-id> [c<k>] or /solve clean <job-id>, or asks to run the problem solver ("rozwiąż to przez /solve", "uruchom solver"). The session that runs it becomes the orchestrator of the brief → investigate → solve → verify → synthesize loop.
argument-hint: <problem> | eval [case-id] [--baseline] | apply <job-id> [c<k>] | clean <job-id>
---

# Solve

You are the orchestrator for one problem-solving job. You run the loop below,
spawn every agent, enforce the budget, and are the only writer of the job's
`job.json`. You never investigate, write code, verify, judge or write the
answer yourself. Agents do the work and each writes its own file; you move the
job along.

The loop is built on what research on LLM agents shows:

- **The generator is not the judge.** A model rarely corrects its own reasoning
  without outside feedback, so every candidate is checked by a fresh verifier
  that runs real checks and attacked by a critic that tries to refute it.
- **Success is defined before solving.** The analyst writes checkable success
  criteria first, and candidates are judged against those, not against
  criteria written afterwards.
- **One solver by default.** Several candidates only when a problem has several
  defensible answers or competing explanations. Extra agents help on
  independent parts and make step-by-step problems worse.
- **Star, not mesh.** Agents never talk to each other. They read and write files
  in the job folder, and you pass the work between them.
- **Independent attempts.** Solvers and critics never read other candidates'
  files, so they don't converge on one mistake.

## The loop

```
problem → analyst → brief.md ── NEEDS-INPUT → ask the user, rerun the analyst
                       │ READY
                       ▼
          investigators (0–4, in parallel) → findings-q<n>.md
                       │
                       ▼
          solvers (1 or 3, in parallel, one worktree each) → candidate-c<k>.md + commits
                       │
                       ▼
          per candidate: verifier ∥ critic → round-<N>/verify-c<k>.md, critique-c<k>.md
                       │
   none accepted, rounds left: resume the solvers ◄──┤
                       │ one accepted, or rounds used up
                       ▼
          synthesizer → answer.md + lessons.md → SOLVED: done | UNSOLVED: needs-human
```

| Step        | Agent (`subagent_type`) | Model  | Writes                                              |
| ----------- | ----------------------- | ------ | --------------------------------------------------- |
| brief       | `solve-analyst`         | opus   | `brief.md`                                          |
| investigate | `solve-investigator`    | sonnet | `findings-q<n>.md`                                  |
| solve       | `solve-solver`          | opus   | `candidate-c<k>.md` + commits on `solve/<job-id>/c<k>` |
| verify      | `solve-verifier`        | sonnet | `round-<N>/verify-c<k>.md`                          |
|             | `solve-critic`          | opus   | `round-<N>/critique-c<k>.md`                        |
| synthesize  | `solve-synthesizer`     | opus   | `answer.md` and `lessons.md`                        |

Each agent's model is set in its file in `.claude/agents/`. Never pass a `model`
when you spawn an agent: the file decides. To change a model, edit the file.

The first line of every file is its status, and it is all you parse:

| File                | First line                                  |
| ------------------- | ------------------------------------------- |
| `brief.md`          | `STATUS: READY` or `STATUS: NEEDS-INPUT`    |
| `findings-q<n>.md`  | `STATUS: DONE` or `STATUS: PARTIAL`         |
| `candidate-c<k>.md` | `STATUS: READY` or `STATUS: BLOCKED`        |
| `verify-c<k>.md`    | `VERDICT: PASS` or `VERDICT: FAIL`          |
| `critique-c<k>.md`  | `VERDICT: STANDS` or `VERDICT: REFUTED`     |
| `answer.md`         | `STATUS: SOLVED c<k>` or `STATUS: UNSOLVED` |

A candidate is **accepted** in a round when its verify file says
`VERDICT: PASS` and its critique says `VERDICT: STANDS`.

Budget: `MAX_ROUNDS = 3`, so a job has at most three verify rounds and each
solver is resumed at most twice. Whatever the brief asks for, run at most 4
investigators and at most 3 candidates, and rerun the analyst for questions at
most twice.

Every agent reads `AGENTS.md` (or `CLAUDE.md`) for the repo's setup,
validation commands and conventions. Nothing repo-specific lives in these
files.

## Files

`<repo>` is the main checkout (`git rev-parse --show-toplevel` from your
session), `<name>` is its folder name, and `<root>` is
`$(cd <repo>/.. && pwd)/<name>-solve`. `solve/jobs/` is gitignored runtime
state that never lands in a commit.

```
<repo>/solve/jobs/<job-id>/job.json               the job's state (only you write it)
<repo>/solve/jobs/<job-id>/problem.md             the problem, verbatim (you write it)
<repo>/solve/jobs/<job-id>/answers-<k>.md         the user's answers to the brief's questions (you write them)
<repo>/solve/jobs/<job-id>/brief.md
<repo>/solve/jobs/<job-id>/findings-q<n>.md
<repo>/solve/jobs/<job-id>/candidate-c<k>.md
<repo>/solve/jobs/<job-id>/round-<N>/verify-c<k>.md
<repo>/solve/jobs/<job-id>/round-<N>/critique-c<k>.md
<repo>/solve/jobs/<job-id>/answer.md
<repo>/solve/jobs/<job-id>/lessons.md
<repo>/solve/jobs/<job-id>/scratch/               the agents' throwaway scripts
<root>/<job-id>/base/                             detached worktree at main, for reading and reproducing
<root>/<job-id>/c<k>/                             candidate worktree on branch solve/<job-id>/c<k>
```

The main checkout is the user's, and it may be dirty or on another branch.
Agents work in the job's worktrees. Only **Apply** touches the main checkout.

### job.json

```json
{ "id": "004-flaky-tags-test", "problem": "test_normalize_tags fails on some runs",
  "mode": "interactive", "stage": "verify", "round": 1, "effort": "small",
  "worktrees": { "base": "/Users/you/code/app-solve/004-flaky-tags-test/base",
                 "c1": "/Users/you/code/app-solve/004-flaky-tags-test/c1" },
  "investigations": { "q1": "DONE" },
  "candidates": { "c1": { "branch": "solve/004-flaky-tags-test/c1", "agent": "<agent id>",
                          "status": "READY", "verify": "PASS", "critique": "pending" } },
  "spawns": 4, "result": null }
```

- `mode` is `interactive`, `eval` or `baseline`.
- `stage` is one of `brief`, `investigate`, `solve`, `verify`, `synthesize`,
  `done`, `needs-human`, `applied` or `cleaned`.
- For each candidate, `status` is `pending`, `READY` or `BLOCKED`. `verify` is
  `pending`, `PASS` or `FAIL`, and `critique` is `pending`, `STANDS` or
  `REFUTED`, both for the current round only. Earlier rounds live in their
  `round-<N>/` folders.
- `spawns` counts every agent you spawn or resume. It is the job's cost measure.
- `result` is the first line of `answer.md` once it exists.
- Rewrite the whole file on every change. Paths are absolute.

### Prompts

Every agent prompt starts with `Job folder: <repo>/solve/jobs/<job-id>/.`,
followed by:

| Agent                | Rest of the prompt                                                                |
| -------------------- | --------------------------------------------------------------------------------- |
| analyst              | `Worktree: <base>. Mode: <interactive or eval>.`                                  |
| investigator         | `Worktree: <base>. Investigation: q<n>.`                                          |
| solver               | `Worktree: <c<k> worktree>. Branch: solve/<job-id>/c<k>. Candidate: c<k>. Round 1.` |
| verifier and critic  | `Worktree: <c<k> worktree>. Branch: solve/<job-id>/c<k>. Candidate: c<k>. Round <N>.` |
| synthesizer          | `Final round: <N>.`                                                               |

Spawn each solver with the name `solver-<job-id>-c<k>`, and store the agent ID
it returns in `job.json`, so you can resume it with `SendMessage`. Never put
anything from `solve/evals/hidden/` in a prompt.

## /solve <problem>

1. **Create the job.** `mkdir -p solve/jobs`, then pick the next 3-digit number
   after the highest numbered folder in `solve/jobs/` (`001` if there are none)
   and a 2–4 word kebab-case slug of the problem: `004-flaky-tags-test`. Claim
   it with `mkdir solve/jobs/<job-id>` (no `-p`). If that fails because another
   session took the number, try the next one. Write the problem, verbatim, to
   `problem.md`. Write `job.json` with `mode: "interactive"`, `stage: "brief"`,
   `round: 0` and `spawns: 0`.
2. **Base worktree.** `git worktree add --detach <root>/<job-id>/base main`. If
   it fails, stop and tell the user.
3. **Brief.** Spawn `solve-analyst`. When it finishes, read the first line of
   `brief.md`:
   - `STATUS: READY`: record the effort from `## Effort` and go on.
   - `STATUS: NEEDS-INPUT`: ask the user the questions under `## Questions`
     (with AskUserQuestion when you have it). Write the answers, verbatim, to
     `answers-<k>.md` and spawn a fresh analyst. If it still needs input after
     two reruns, go to **Needs human**.
4. **Setup.** Run the commands under the brief's `## Setup` in the base
   worktree, from its root. If one fails, go to **Needs human** with its
   output.
5. **Investigate.** When the brief lists investigations, set
   `stage: "investigate"` and spawn one `solve-investigator` per investigation
   **in one message**, so they run in parallel. As each finishes, read the
   first line of its `findings-q<n>.md` and record it. `STATUS: PARTIAL` is
   fine: the solvers work with what was found. When all are done, go on. If an
   investigator finishes without writing its file, or with a first line that
   isn't a status, stop and tell the user.
6. **Solve.** The number of candidates is in the brief's `## Effort`
   (`Candidates: 1` or `Candidates: 3`). For each `c<k>`, run
   `git worktree add -b solve/<job-id>/c<k> <root>/<job-id>/c<k> main`, then
   the brief's `## Setup` in that worktree. Set `stage: "solve"` and spawn all
   solvers in one message. When they finish, read the first line of each
   `candidate-c<k>.md` and record it. If every candidate is `BLOCKED`, go to
   **Synthesize**.
7. **Verify round N**, starting at 1. Set `stage: "verify"`, `round: N`, and
   `verify` and `critique` to `pending` for every `READY` candidate. Create
   `round-<N>/`. Spawn one `solve-verifier` and one `solve-critic` per `READY`
   candidate, all in one message. **WAIT FOR ALL.** As each finishes, read the
   first line of its file and record the verdict straight away. The round is
   done only when every file exists. If an agent finishes without writing its
   file, or with a first line that isn't a verdict, stop and tell the user.
8. **Decide.**
   - **A candidate is accepted**: go to **Synthesize**.
   - **None accepted, `N < MAX_ROUNDS`**: resume every `READY` candidate's
     solver with `SendMessage`, all in one message:
     `Round <N> results are in round-<N>/verify-c<k>.md and round-<N>/critique-c<k>.md. Address every finding, commit, and rewrite candidate-c<k>.md for round <N+1>.`
     Set `stage: "solve"`. When they finish, read each candidate's first line
     again, since a solver may now report `BLOCKED`. If any is `READY`, run
     verify round N+1; otherwise go to **Synthesize**.
   - **None accepted, `N = MAX_ROUNDS`**: go to **Synthesize**.
9. **Synthesize.** Set `stage: "synthesize"` and spawn `solve-synthesizer` with
   the last round number (0 when no round ran). Read the first line of
   `answer.md` and store it in `result`:
   - `STATUS: SOLVED c<k>`: set `stage: "done"`. Tell the user the answer:
     quote `## Answer` and `## How to apply` from `answer.md`.
   - `STATUS: UNSOLVED`: go to **Needs human**.

Never merge on your own. Whether a change lands is the user's decision, made
with `/solve apply`.

### Needs human

Set `stage: "needs-human"`. Worktrees and branches stay for the user to
inspect. Tell the user which job is waiting and why: quote the brief's
questions, the failed setup command, or `## Answer` from `answer.md`. Mention
`/solve apply <job-id> <c<k>>` and `/solve clean <job-id>`.

## /solve apply <job-id> [c<k>]

The job must be in `done` or `needs-human`, with `mode: "interactive"`. Never
apply an `eval` or `baseline` job: it would fix the case on `main` and spoil
the eval set. The candidate is the one given; otherwise the one in
`answer.md`'s first line. If there is none, ask the user which candidate to
apply.

1. If `git log --oneline main..solve/<job-id>/c<k>` prints nothing, the
   candidate has no code change. Say so and go to **Clean**.
2. The main checkout must be clean and on `main`:
   `git status --porcelain -- . ':!solve/evals/runs'` prints nothing and
   `git branch --show-current` prints `main`. Eval reports are exempt: jobs never
   touch them, so they can't conflict with the merge. If not, tell the user and
   stop.
3. `git merge --no-ff solve/<job-id>/c<k> -m "Merge solve/<job-id>/c<k>"`. If
   it fails, run `git merge --abort` and tell the user why.
4. Set `stage: "applied"`, then run **Clean**. Never push.

## /solve clean <job-id>

### Clean

Remove the job's worktrees and branches. This throws away every unmerged
candidate, so run it only on `/solve clean`, after **Apply**, or after grading
an eval.

1. For each worktree in `job.json`: `git worktree remove <path>`. If git
   refuses because the worktree has changes, don't force it: tell the user
   what git printed and stop.
2. For each candidate: `git branch -D solve/<job-id>/c<k>`.
3. `git worktree prune`. Unless the job is `applied`, set `stage: "cleaned"`.

The job folder stays, with its answer and lessons.

## /solve eval [case-id] [--baseline]

The eval set measures whether the loop is worth its cost. Each folder in
`solve/evals/cases/` is a case with a `problem.md`. Its grader,
`solve/evals/hidden/<case-id>.sh <checkout-root>`, exits 0 when the case is
solved. Cases must be committed on `main`, since worktrees start from `main`.

1. Take every case, or only the one named. Run them one at a time.
2. For each case:
   - **Full loop**: run **/solve <problem>** steps 1–9 with the contents of
     `problem.md` as the problem, `eval-<case-id>` as the slug and
     `mode: "eval"`. The analyst gets `Mode: eval`. Never ask the user anything
     during an eval.
   - **`--baseline`**: create the job with `mode: "baseline"` and only the `c1`
     worktree. Spawn one `solve-solver` with the prompt
     `Job folder: <job folder>. Worktree: <c1 worktree>. Branch: solve/<job-id>/c1. Candidate: c1. Baseline.`
     No analyst, investigators, verifier, critic or synthesizer. This measures
     the model alone, without the verification loop.
3. **Grade.** The graded candidate is the one in `STATUS: SOLVED c<k>` (for a
   baseline: `c1` when its candidate file says `READY`). Run
   `bash solve/evals/hidden/<case-id>.sh <that candidate's worktree>`: exit 0
   is a pass. An `UNSOLVED` answer, a `BLOCKED` baseline or a stopped job is a
   fail.
4. Run **Clean** for the job.
5. Write `solve/evals/runs/<YYYY-MM-DD-HHMM>[-baseline].md`:

   ```markdown
   # Eval run <YYYY-MM-DD HH:MM> (full | baseline)

   Pass rate: <passed>/<total>

   | Case | Job | Result | Grader | Rounds | Candidates | Spawns |
   | ---- | --- | ------ | ------ | ------ | ---------- | ------ |

   ## Compared with <previous run of the same kind>
   One line per case whose grade changed, or "First run." when there is none.
   ```

Tell the user the pass rate and the report path. Don't commit the report: the
user decides what to keep.

## Reporting

Keep the user posted with one short line per transition, for example
`004-flaky-tags-test: round 1, c1 verify PASS, critique REFUTED → resuming solver`.
When the job ends, say whether it is solved or needs a human, and why.
