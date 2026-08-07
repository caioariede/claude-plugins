---
name: ws-resume
description: The single verb for advancing a unit at any stage — run it right after ws-start (it reads the unit's charter and plans from the design), to continue a half-done unit's tasks, or to ship a finished one; it also reopens a gone worktree and reconciles a drifted base. Idempotent — safe to run anytime, it does the next right thing for the state it finds. You know which unit; for deciding which unit comes next, that is ws-next.
argument-hint: "[unit-id]"
metadata:
  version: "0.6.1"
  author: Caio Ariede
---

# ws-resume — resume a unit

**Required first:** load the `ws` skill — it is the shared contract (SPEC) this skill references throughout.

**Input:** `$ARGUMENTS` = `[unit-id]`. If omitted, infer it from the current worktree's branch by scanning `<store>/*/units.md` (store root: SPEC).

## Steps
1. Resolve the unit via the SPEC bare-slug resolver → `ws-id`, `repo`, `branch`. (With no argument, infer the unit from the current worktree's branch.)
2. Ensure the worktree exists and self-locate into it (SPEC "Command scope"):
   - already inside it (branch matches) → continue;
   - worktree exists but you're elsewhere → `cd` into it in the current session;
   - worktree gone but branch exists → recreate it via the active `worktree-management` flavor's `create` for `<branch>` off `<base>`, then work there;
   - branch also gone → fresh start off the repo default branch (per SPEC); the store's progress is your restart baseline.
3. Reconcile base per SPEC Restack reconciliation — if the active `forge` flavor's `pr-status` base differs from the unit's recorded base, realign and append a `restack` line.
4. Load state: read `charter.md` (why this unit exists + its `design:`), `progress.md` (Tasks + Follow-ups), and `log.md` (recent notes); run `git log -5` and the repo's verification command to confirm the code state.
5. Detect the unit's state and take the one right next action — **announce it first, then act.** Actions are conditioned on the state, so re-running is safe: it never repeats a finished step, and it writes to the store only on a genuine transition (never a bare "resumed" line — see SPEC idempotency note).
   - **Blocked-awareness guard:** before advancing (plan/execute), derive the unit's needs — implicit base + `## Needs` (SPEC §Dependencies). If any is unmet, the unit is **blocked**: surface it — name the unmet target(s) and warn the unit is blocked — then require explicit confirmation to proceed anyway. `ws-resume` is the intentional override path: it warns, it does not silently proceed, and it does not hard-refuse.
   - **Unplanned** (`## Tasks` empty): read `charter.md` and its `design:` spec; note what the base branch already ships. Resolve the unit plan path (SPEC §Plan path). If the plan file already exists → **sync only:** append `plan` to `log.md`, derive `T1..` into `progress.md`; skip the `plan` op. Else: fire `hook-ws-resume-unplanned-before` (interactive); run the flavor `plan` op (`writing-plans` + handoff for superpowers); fire `hook-ws-resume-unplanned-after`. **Headless** (hooks skip): resolve plan path, set session context for the plan op, run `plan` if no file yet, then sync store. Record `decision execute-mode=…` from the handoff. Do not add ship/lint/PR task lines. Enter execute (below). `none` flavor skips hooks; its `plan` op writes `T1..` inline.
   - **In progress** (some `T#` unchecked): unless this invocation just finished unplanned planning, fire `hook-ws-resume-loop-before` once (superpowers). Run execute for the first unchecked task (below). Enter the execute loop (below).
   - If a `stacked-on` unit is not yet merged (per the active `forge` flavor's `pr-status`), surface it and let the user decide before proceeding at ship-pause.

## Execute

**Superpowers execute mode** (from `decision execute-mode=…` in `log.md`):
- `inline` → run `executing-plans` **once** this invocation (batch + checkpoints), then phase.py. Do not re-invoke inside the loop.
- default / `subagent-driven` → flavor `execute` on the first unchecked task, then the loop below.

## Execute loop

After execute action, run phase derivation — do not infer from `progress.md`:

```
python3 <this-skill-dir>/scripts/phase.py [unit-id]
```

| Phase | Action |
|-------|--------|
| `loop` | Announce first unchecked task; run flavor `execute`; update store; repeat from phase.py. No `ws-next`. |
| `ship-pause` | Summarize; offer **Not now** (preselected), **Ship `<unit>`** (ship flavor), **`ws-next`**. On Ship, re-run phase.py. |
| `draft-pr` | Offer **Not now** (preselected), **Mark ready** (forge `pr-ready`), **`ws-next`**. On Mark ready, re-run phase.py. |
| `blocked` | Blocked-awareness guard; stop. |
| `done` | Chain to `ws-next` (below). |

**Plan convention:** Last execute task owns verification; opening the PR is ship-pause when `code_complete`.

**No auto-ship:** At `code_complete` with no PR, never run the ship flavor until the user picks **Ship** at ship-pause.

## Next

Chain to `ws-next` only when phase is `done`, when the user picks `ws-next` at a pause, or after ship/mark-ready leaves phase `done` (§Next-step chaining). Do not offer `ws-next` as the sole handoff while phase is `loop`.
