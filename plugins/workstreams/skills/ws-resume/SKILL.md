---
name: ws-resume
description: The single verb for advancing a unit at any stage — run it right after ws-start (it reads the unit's charter and plans from the design), to continue a half-done unit's tasks, or to ship a finished one; it also reopens a gone worktree and reconciles a drifted base. Idempotent — safe to run anytime, it does the next right thing for the state it finds. You know which unit; for deciding which unit comes next, that is ws-next.
argument-hint: "[unit-id]"
metadata:
  version: "0.7.0"
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
5. **Blocked-awareness guard:** before advancing (plan/execute), derive the unit's needs — implicit base + `## Needs` (SPEC §Dependencies). If any is unmet, the unit is **blocked**: surface it — name the unmet target(s) and warn the unit is blocked — then require explicit confirmation to proceed anyway. `ws-resume` is the intentional override path: it warns, it does not silently proceed, and it does not hard-refuse.
6. Derive phase — do not infer planning or execute boundaries from `progress.md` alone:

```
python3 <this-skill-dir>/scripts/phase.py [unit-id]
```

| Phase | Action |
|-------|--------|
| `plan` | **Plan only — no code, no tasks, no execute-mode.** Read `charter.md` and its `design:` spec; note what the base branch already ships. Resolve the unit plan path (SPEC §Plan path). If the plan file already exists and `log.md` lacks a `plan` line → append `plan` only, re-run phase.py, stop at `plan-pause`. Else: fire `hook-ws-resume-unplanned-before` (interactive); run the flavor `plan` op through plan save (`writing-plans` for superpowers — **stop before its Execution Handoff**; plan-pause owns that gate); fire `hook-ws-resume-unplanned-after`. Append `plan <absolute-path>` to `log.md` when absent. Do **not** derive `T1..`, do **not** append `execute-mode`, do **not** touch source files. Re-run phase.py → `plan-pause`. **`none` flavor:** its `plan` op writes `T1..` inline and skips this gate. **Headless** (hooks skip): resolve plan path, run `plan` if no file yet, append `plan`, default `execute-mode=subagent-driven`, derive tasks, enter execute. |
| `plan-pause` | Summarize the plan path and task headings (read the plan file — do not derive into `progress.md` yet). Offer **Not now** (preselected), **Subagent-driven**, **Inline**. On **Not now**, stop. On **Subagent-driven** / **Inline**: derive `T1..` into `progress.md` (SPEC task derivation), append `decision execute-mode=subagent-driven` or `execute-mode=inline`, re-run phase.py, enter execute (below). Never pick an execute mode or start T1 without the user's choice. |
| `loop` | Unless this invocation just cleared `plan-pause`, fire `hook-ws-resume-loop-before` once (superpowers). Run execute for the first unchecked task (below). Enter the execute loop (below). |
| `ship-pause` | Summarize; offer **Not now** (preselected), **Ship `<unit>`** (ship flavor), **`ws-next`**. On Ship, re-run phase.py. If a `stacked-on` unit is not yet merged (per the active `forge` flavor's `pr-status`), surface it and let the user decide. |
| `draft-pr` | Offer **Not now** (preselected), **Mark ready** (forge `pr-ready`), **`ws-next`**. On Mark ready, re-run phase.py. |
| `blocked` | Blocked-awareness guard; stop. |
| `done` | Chain to `ws-next` (below). |

**Plan convention:** Last execute task owns verification; opening the PR is ship-pause when `code_complete`.

**No auto-ship:** At `code_complete` with no PR, never run the ship flavor until the user picks **Ship** at ship-pause.

## Execute

**Superpowers execute mode** (from `decision execute-mode=…` in `log.md`):
- `inline` → run `executing-plans` **once** this invocation (batch + checkpoints), then phase.py. Do not re-invoke inside the loop.
- default / `subagent-driven` → flavor `execute` on the first unchecked task, then the loop below. **The parent session coordinates only** — dispatch a fresh subagent per task; do not implement task steps inline in the parent.

## Execute loop

After execute action, re-run phase derivation:

```
python3 <this-skill-dir>/scripts/phase.py [unit-id]
```

Then act on the phase table above (`loop` → repeat execute; pauses → stop for user).

## Next

Chain to `ws-next` only when phase is `done`, when the user picks `ws-next` at a pause, or after ship/mark-ready leaves phase `done` (§Next-step chaining). Do not offer `ws-next` as the sole handoff while phase is `loop`.
