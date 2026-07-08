---
name: ws-resume
description: The single verb for advancing a unit at any stage — run it right after ws-start (it reads the unit's charter and plans from the design), to continue a half-done unit's tasks, or to ship a finished one; it also reopens a gone worktree and reconciles a drifted base. Idempotent — safe to run anytime, it does the next right thing for the state it finds. You know which unit; for deciding which unit comes next, that is ws-next.
---

# ws-resume — resume a unit

Read the shared contract first: `${CLAUDE_PLUGIN_ROOT}/ws-shared/SPEC.md`.

**Input:** `$ARGUMENTS` = `[unit-id]`. If omitted, infer it from the current worktree's branch by scanning `~/.claude/workstreams/*/units.md`.

## Steps
1. Resolve `unit-id` → `ws-id`, `repo`, `branch` from the ledger.
2. Ensure the worktree exists:
   - already inside it (branch matches) → continue;
   - worktree gone but branch exists → `wmx window open <branch>` (or `wmx worktree create <branch> --base <base>`);
   - branch also gone → fresh start off the repo default branch (per SPEC); the store's progress is your restart baseline.
3. Reconcile base per SPEC Restack reconciliation — if `gh pr view --json baseRefName` differs from the unit's recorded base, realign and append a `restack` line.
4. Load state: read `charter.md` (why this unit exists + its `design:`), `progress.md` (Tasks + Follow-ups), and `log.md` (recent notes); run `git log -5` and the repo's verification command to confirm the code state.
5. Detect the unit's state and take the one right next action — **announce it first, then act.** Actions are conditioned on the state, so re-running is safe: it never repeats a finished step, and it writes to the store only on a genuine transition (never a bare "resumed" line — see SPEC idempotency note).
   - **Unplanned** (`## Tasks` empty): read `charter.md` and its `design:` spec, note what the base branch already ships (build on it, don't redo it), then plan with **superpowers:writing-plans** — write the tasks as `T1..` into `progress.md`. Then proceed as "in progress".
   - **In progress** (some `T#` unchecked): continue at the first unchecked task via **superpowers:subagent-driven-development** — update `progress.md`, append decisions/notes to `log.md`, record follow-ups per SPEC "Follow-up placement" (deferred → `backlog.md`).
   - **Done** (every `T#` checked) **with no PR** (per `gh`): the work is finished but unshipped — ship it with **superpowers:finishing-a-development-branch**.
   - If a `stacked-on` unit is not yet merged (per `gh`), surface it and let the user decide before proceeding.

## Next
After the action, name the hub follow-up: back in the **hub**, `ws-next` (cross-window — name it, don't auto-run here; SPEC Next-step chaining).
