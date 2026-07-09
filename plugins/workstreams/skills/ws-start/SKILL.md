---
name: ws-start
description: Use when starting a new unit of work in an existing workstream (its own worktree + ledger entry). Run ws-init first if no workstream exists.
argument-hint: '[ws-id] "[what this unit does]" [--base <unit-id|branch>] [--repo <org/repo>]'
---

# ws-start — start a unit

**Required first:** load the `ws` skill — it is the shared contract (SPEC) this skill references throughout.

**Input:** `$ARGUMENTS` = `<ws-id> <what this unit does>` with optional `--base <unit-id|branch>`.
If `ws-id` is omitted and exactly one workstream exists, use it; otherwise ask which.

## Steps
1. Resolve `ws-id` → `<store>/<ws-id>/` (store root: SPEC). Compute `slug = slug(what)`; the unit-id is `<ws-id>:<slug>` (per SPEC IDs). If `units/<slug>/` already exists → **confirm**: resume the existing unit (`ws-resume`) or start fresh. A fresh start takes the next `-N` slug suffix and records `restart-of=<slug>` on its ledger line (per SPEC).
2. Resolve `repo` by SPEC precedence: `--repo` wins; else if `--base` is a unit-id, use that unit's repo; else the cwd repo. Error if an explicit `--repo` contradicts a `--base` unit's repo. `base` = the repo default branch (per SPEC) unless `--base` is given; if `--base` is a unit-id, resolve it to that unit's branch (stacking → record `stacked-on` in canonical form when cross-workstream).
3. Create the worktree via the active `worktree-management` flavor's `create` (SPEC §Flavors), for branch `<slug>` off `<base>`. Disambiguate the branch with `-N` if `<slug>` already exists in the target repo (per SPEC). Do not steal the current session's focus.
4. **Append** the ledger line to `units.md` (SPEC format: bare `<slug>` id, `repo=`, `branch=`; include `restart-of=` / `stacked-on=` when applicable).
5. Create `units/<unit-id>/charter.md`, `progress.md`, and `log.md` per SPEC File formats; append the `created base=<base>` log line. The `charter.md` `purpose` = the `<what>` verbatim + the standing clause "build on whatever the base branch already ships — don't reimplement it"; `design:` = copied from `workstream.md`. Writing the intent to the store (not a printed prompt) is what lets `ws-resume` reconstruct it later; leave the *specific* deliverables to be scoped at plan time against the design.
6. The unit is provisioned and its intent is in `charter.md` — do **not** print a bootstrap prompt. Fire `hook-ws-start-after` (SPEC §Flavors; interactive sessions only) — this is the where-to-continue handoff: if it opens a new window, tell the user to run **`/ws-resume`** there; if they stay (or the hook does not fire), offer to run **`/ws-resume`** in the current session now (default yes). `/ws-resume` is the single verb from here on — it reads `charter.md` + the design and **plans** an unplanned unit (writing `T1..` into `progress.md`), **continues** a half-done one, and **ships** a finished one.

`ws-resume` self-locates the worktree, so the unit's work runs wherever you run it — see SPEC "Command scope".
