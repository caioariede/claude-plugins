---
name: ws-block
description: >-
  Use when a workstream unit must wait on another before it can proceed —
  record, view, or remove a dependency: "B needs A", "B is blocked by A", "B
  can't start until A is done", "B waits on A's login work". Reach for it the
  moment a dependency surfaces mid-build, not only at planning time: add a
  need, clear one when scope changes, and let the board/router show what's
  blocked. A need targets a whole unit (met when its tasks are done) or a
  specific follow-up. NOT for abandoning a unit (that's ws-drop) or rebasing
  onto a merged base (ws-restack).
argument-hint: '<unit> needs <target> ["note"] | <unit> clear N<n>'
metadata:
  version: "0.1.0"
  author: Caio Ariede
---

# ws-block — manage a unit's dependencies (needs)

**Required first:** load the `ws` skill — the shared contract (SPEC) this skill references throughout; §Dependencies defines needs, targets, `code-complete`, and `blocked`.

`ws-block` edits a unit's **needs** — the dependencies that gate it. `blocked` is the *derived* state (SPEC §Dependencies), never hand-set here: you add or clear needs, and the board/router derive the rest. Workstream-scoped — it touches only the store, runs from any session, and can target a unit other than the one you are in, including a not-yet-started planned unit.

**Input:** `$ARGUMENTS` =
- `<unit> needs <target> ["note"]` — add a need.
- `<unit> clear N<n>` — remove a need (scope change).

`<unit>` and a unit `<target>` resolve via the SPEC bare-slug resolver. A `<target>` is a **unit** (id or bare slug) or a **follow-up** id (`<unit-id>:F<n>` or `WF<n>`).

## Steps — add (`needs`)
1. Resolve `<unit>` to its store dir (`<store>/<ws-id>/units/<slug>/`). Resolve `<target>`: a unit target must resolve to a ledger unit **or** a `backlog.md` planned-unit slug; a follow-up target must exist as a line in its source file (`<unit-id>:F<n>` in that unit's `progress.md`, `WF<n>` in `backlog.md`). Unresolvable → error and list candidates.
2. **Validate:**
   - reject a **self-need** (`<unit>` equals the unit `<target>`).
   - reject a **cycle** — walk the existing need graph (SPEC §Dependencies) outward from `<target>`; if it reaches `<unit>`, refuse and name the path. Carry a visited-set so a pre-existing hand-edited cycle cannot loop the walk.
3. Append to the unit's `progress.md` `## Needs` (create the section if absent): `- N<n>  <target>   — <note>`, where `N<n>` is the unit's next monotonic need id (never reused, even after a clear). No checkbox — satisfaction is derived. Drop the ` — <note>` when none is given.
4. Append `decision  need N<n> → <target>` to the unit's `log.md`.

## Steps — clear (`clear N<n>`)
1. Resolve `<unit>`; find the `N<n>` line in its `progress.md` `## Needs`. Missing → error.
2. Remove that line. Do **not** renumber survivors — ids are monotonic and never reused.
3. Append `decision  cleared need N<n> (<target>)` to `log.md`. Clearing is a deliberate scope change (the dependency no longer applies) — not a way to mark a need satisfied; satisfaction is derived and needs no action.

## Scope
Workstream-scoped (SPEC "Command scope") — store-only, runs from any session. It never touches a worktree or git.

## Chain
After the edit, fire `hook-ws-block-after` (SPEC §Flavor hooks) — fills `<unit>`/`<branch>` from the target unit, `<command>` = `ws-next <ws-id>`. No active flavor defines it → default chaining (SPEC Next-step chaining): offer to run **`ws-next`** now (default yes) — dependencies changed, so re-route. Mention the affected unit so a parallel-session user knows which one.
