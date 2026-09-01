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
  version: "0.2.2"
  author: Caio Ariede
---

# ws-block — manage a unit's dependencies (needs)

**Required first:** load the `ws` skill — SPEC §Dependencies defines needs, targets, `code-complete`, and `blocked`.

**Flow reference:** see visual execution flow in `skills/ws/references/flows/diagrams/block.mmd`.

`ws-block` edits a unit's or spike's **needs** — the dependencies that gate it. `blocked` is the *derived* state (SPEC §Dependencies), never hand-set here: you add or clear needs, and the board/router derive the rest. Workstream-scoped — it touches only the store, runs from any session, and can target a unit or spike other than the one you are in. It targets a **started** (ledger) unit or spike; a not-yet-started planned unit's dependencies live in `backlog.md` `needs=` — edit that line directly (`ws-start` seeds it into `## Needs` once the unit starts, SPEC §File formats).

**Input:** `$ARGUMENTS` =
- `<unit|spike> needs <target> ["note"]` — add a need.
- `<unit|spike> clear N<n>` — remove a need (scope change).

`<unit|spike>` and a unit or spike `<target>` resolve via SPEC §IDs & conventions (bare-slug resolver). A `<target>` is a **unit**, a **spike**, or a **follow-up** id (`<unit-id>:F<n>` or `WF<n>`).

## Steps — add (`needs`)
1. Resolve `<unit|spike>` to its store dir (`<store>/<ws-id>/units/<slug>/` or `spikes/<slug>/`). Resolve `<target>`: a unit target must resolve to a ledger unit **or** a `backlog.md` planned-unit slug; a spike target must resolve to a ledger spike **or** a pending spike reference; a follow-up target must exist as a line in its source file (`<unit-id>:F<n>` in that unit's `progress.md`, `WF<n>` in `backlog.md`). Unresolvable → error and list candidates.
2. **Validate:**
   - reject a **self-need** (`<unit>` equals the unit `<target>`).
   - reject a **cycle** — walk the existing need graph (SPEC §Dependencies) outward from `<target>`; if it reaches `<unit>`, refuse and name the path. Carry a visited-set so a pre-existing hand-edited cycle cannot loop the walk.
3. Append to `<unit|spike>`'s `progress.md` `## Needs` (create the section if absent): `- N<n>  <target>   — <note>`, where `N<n>` is the next monotonic need id for that unit or spike (never reused, even after a clear) — compute it from the high-water mark of `need N<n> →` entries in that entity's `log.md` (append-only), not from the max `N<n>` currently visible in `## Needs`, so a cleared id can't resurface. No checkbox — satisfaction is derived. Drop the ` — <note>` when none is given.
4. Append `decision  need N<n> → <target>` to that entity's `log.md`.

## Steps — clear (`clear N<n>`)
1. Resolve `<unit|spike>`; find the `N<n>` line in its `progress.md` `## Needs`. Missing → error.
2. Remove that line. Do **not** renumber survivors — ids are monotonic and never reused.
3. Append `decision  cleared need N<n> (<target>)` to `log.md`. Clearing is a deliberate scope change (the dependency no longer applies) — not a way to mark a need satisfied; satisfaction is derived and needs no action.

## Scope
Workstream-scoped (SPEC §Command scope) — store-only, runs from any session. It never touches a worktree or git.

## Chain
After the edit, fire `hook-ws-block-after` (SPEC §Flavor hooks) — fills `<unit>`/`<branch>` from the target unit, `<command>` = `ws-next <ws-id>`. No active flavor defines it → default chaining (SPEC §Next-step chaining): offer to run **`ws-next`** now — dependencies changed, so re-route. Mention the affected unit so a parallel-session user knows which one.
