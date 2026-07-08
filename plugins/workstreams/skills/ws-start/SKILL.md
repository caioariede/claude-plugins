---
name: ws-start
description: Use when starting a new unit of work in an existing workstream (its own worktree + roster entry). Run ws-init first if no workstream exists.
---

# ws-start — start a unit

Read the shared contract first: `${CLAUDE_PLUGIN_ROOT}/ws-shared/SPEC.md`.

**Input:** `$ARGUMENTS` = `<ws-id> <what this unit does>` with optional `--base <unit-id|branch>`.
If `ws-id` is omitted and exactly one workstream exists, use it; otherwise ask which.

## Steps
1. Resolve `ws-id` → `~/.claude/workstreams/<ws-id>/`. Compute `unit-id = slug(what)`. If `units/<unit-id>/` already exists → **confirm**: resume the existing unit (`ws-resume`) or start fresh. A fresh start takes the next `-N` suffix and records `restart-of=<original-unit-id>` on its roster line (per SPEC).
2. `base` = the repo default branch (per SPEC) unless `--base` is given; if `--base` is a unit-id, resolve it to that unit's branch (stacking → record `stacked-on`).
3. Create the worktree + window: `wmx worktree create feat-<unit-id> --base <base> --focus`.
4. **Append** the roster line to `units.md` (SPEC format; include `restart-of=` / `stacked-on=` when applicable).
5. Create `units/<unit-id>/charter.md`, `progress.md`, and `log.md` per SPEC File formats; append the `created base=<base>` log line. The `charter.md` `purpose` = the `<what>` verbatim + the standing clause "build on whatever the base branch already ships — don't reimplement it"; `design:` = copied from `workstream.md`. Writing the intent to the store (not a printed prompt) is what lets `ws-resume` reconstruct it later; leave the *specific* deliverables to be scoped at plan time against the design.
6. The unit is provisioned and its intent is in `charter.md` — do **not** print a bootstrap prompt. Tell the user: switch to the new window, launch `claude` if wmx didn't autostart it, and run **`/ws-resume`**. That is the single verb from here on — it reads `charter.md` + the design and **plans** an unplanned unit (writing `T1..` into `progress.md`), **continues** a half-done one, and **ships** a finished one.

The unit's work runs in that new window (execution); the hub stays for orchestration — see SPEC "Sessions — hub vs unit".
