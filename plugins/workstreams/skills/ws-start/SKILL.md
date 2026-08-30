---
name: ws-start
description: Use when starting a new unit of work in an existing workstream (its own worktree + ledger entry). Run ws-init first if no workstream exists.
argument-hint: '[ws-id] "[what this unit does]" [--base <unit-id|branch>] [--repo <org/repo>] [--claims <a,b>] [--slug <slug>]'
metadata:
  version: "0.7.1"
  author: Caio Ariede
---

# ws-start — start a unit

**Required first:** load the `ws` skill — it is the shared contract (SPEC) this skill references throughout.

**Flow reference:** see visual execution flow in `skills/ws/references/flows/diagrams/start.mmd`.

**Input:** `$ARGUMENTS` = `<ws-id> <what this unit does>` with optional `--base <unit-id|branch>`, `--claims <target>[,<target>]` (the follow-ups this unit exists to close — SPEC §Follow-up units), and `--slug <slug>` (name the unit and branch yourself instead of deriving from `<what>`).
If `ws-id` is omitted and exactly one workstream exists, use it; otherwise ask which.

## Steps
1. Resolve `ws-id` → `<store>/<ws-id>/` (store root: SPEC). Compute `slug = slug(what)` — short by construction, per SPEC §IDs — or take `--slug` when given (sanitized, not shortened). Refuse when the slug exists in `spikes.md` (SPEC §IDs — promotion uses a distinct slug). The unit-id is `<ws-id>:<slug>` (per SPEC IDs). The full `<what>` is not lost to shortening: it is the ledger `"<title>"` and the `charter.md` purpose. If `units/<slug>/` already exists → **confirm**: resume the existing unit (`ws-resume`) or start fresh. A fresh start takes the next `-N` slug suffix and records `restart-of=<slug>` on its ledger line (per SPEC).
2. Resolve `repo` by SPEC precedence: `--repo` wins; else if `--base` is a unit-id, use that unit's repo; else the cwd repo. Error if an explicit `--repo` contradicts a `--base` unit's repo. `base` = the repo default branch (per SPEC) unless `--base` is given — or, absent `--base`, a matching `backlog.md` `## Planned units` line's `base=` (that line supplies both `base=` and `needs=`; the latter is seeded in step 5). If `--base` is a unit-id, resolve it to that unit's branch (stacking → record `stacked-on` in canonical form when cross-workstream).
3. Create the worktree via the active `worktree-management` flavor's `create` (SPEC §Flavors), for branch `<slug>` off `<base>`. Disambiguate the branch with `-N` if `<slug>` already exists in the target repo (per SPEC). Do not steal the current session's focus.
4. **Append** the ledger line to `units.md` (SPEC format: bare `<slug>` id, `repo=`, `branch=`; include `restart-of=` / `stacked-on=` / `claims=` when applicable).
5. Create `units/<unit-id>/charter.md`, `progress.md`, and `log.md` per SPEC File formats; append the `created base=<base>` log line. The `charter.md` `purpose` = the `<what>` verbatim + the standing clause "build on whatever the base branch already ships — don't reimplement it"; `design:` = copied from `workstream.md`. Writing the intent to the store (not a printed prompt) is what lets `ws-resume` reconstruct it later; leave the *specific* deliverables to be scoped at plan time against the design. If `backlog.md` `## Planned units` has a line whose `<slug>` matches this unit and it carries `needs=<target>[,…]`, seed each target as an `N<n>` line in the new `progress.md` `## Needs` (§Dependencies) — bare targets, no notes — so the planned dependency survives the planned→started transition. Validate each seeded target as `ws-block` does (self-need, cycle — SPEC §Dependencies): skip a self-referential or cycle-forming target and warn, rather than writing it verbatim. The `--base <unit-id>` dependency is the **implicit** need and is **not** duplicated here (it derives from the ledger).
6. **`--claims` only** — validate the targets per SPEC §Follow-up units and **refuse the whole flag** if any is bad, rather than claiming a subset. Then copy each claimed follow-up's text into `charter.md`'s purpose, so `ws-resume` can plan the unit with no scrollback (its source lines stay where they are). The claim itself is the `claims=` field written in step 4 — **nothing else is written anywhere**, in this unit or any other: claimed-ness is derived.
7. The unit is provisioned and its intent is in `charter.md` — do **not** print a bootstrap prompt. Fire `hook-ws-start-after` (SPEC §Flavors; interactive sessions only) — this is the where-to-continue handoff: if it opens a new window, tell the user to run **`/ws-resume`** there; if they stay (or the hook does not fire), offer to run **`/ws-resume`** in the current session now (opt-out — provisioned-unit handoff, §Next-step chaining). `/ws-resume` is the single verb from here on — it reads `charter.md` + the design and **plans** an unplanned unit (writing `T1..` into `progress.md`), **continues** a half-done one, and **ships** a finished one.

`ws-resume` self-locates the worktree, so the unit's work runs wherever you run it — see SPEC "Command scope".
