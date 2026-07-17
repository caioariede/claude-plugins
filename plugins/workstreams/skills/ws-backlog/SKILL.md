---
name: ws-backlog
description: >-
  Use when future work surfaces mid-workstream and needs capturing — a bug or
  follow-up out of scope for the unit you're in, a "we should also do X later"
  idea, or a whole unit worth planning. Triggers: "add to backlog", "defer
  this", "note a follow-up", "found a new issue", "capture for later", "plan
  another unit". NOT for plan tasks (T<n> come from planning / ws-resume),
  abandoning a unit (ws-drop), or dependencies (ws-block).
argument-hint: '"<what>" [--defer | --here | --plan --base <x> [--needs a,b]] [--to <unit>] [--ws <ws-id>]'
metadata:
  version: "0.1.0"
  author: Caio Ariede
---

# ws-backlog — capture future work

**Required first:** load the `ws` skill — the shared contract (SPEC) this skill references throughout; §"Follow-up placement" defines the F/WF fork and File formats defines the line shapes.

`ws-backlog` captures work you are **not** doing right now and routes it to the one correct home, so nothing orphans. Three destinations: a unit's `progress.md` `## Follow-ups` (`F<n>`, in-flight — fixed before this unit's PR merges), the workstream's `backlog.md` `## Follow-ups` (`WF<n>`, deferred), or `backlog.md` `## Planned units` (a future unit). It **never** writes `## Tasks` (`T<n>`) — the plan is owned by the `spec-driven-development` flavor, not hand-added. Workstream-scoped, runs from any session (SPEC "Command scope").

**Input:** `$ARGUMENTS` = `"<what>"` plus optional placement flags:
- `--defer` → `WF<n>` (deferred follow-up) · `--here` → `F<n>` in the target unit · `--plan` → a planned unit.
- `--to <unit>` targets a unit (for `--here` / provenance); `--ws <ws-id>` picks the workstream; `--base <x>` / `--needs a,b` supply a planned unit's fields.

## Steps
1. **Locate.** Current unit = the ledger unit whose `branch=` matches `git rev-parse --abbrev-ref HEAD` (scan `<store>/*/units.md`; SPEC bare-slug resolver, by branch). `--to` overrides. Workstream = that unit's, else `--ws`, else the sole workstream, else ask. `WF`/planned are workstream-scoped; only `--here` needs a unit.
2. **Place** (the F/WF fork). A `--defer`/`--here`/`--plan` flag decides it (headless-safe). Otherwise ask: with a current unit — "resolved before `<unit>`'s PR merges?" yes → `--here`, no → `--defer`, "own unit" → `--plan`; with no unit — `--defer` (default) or `--plan`. `--here` with no resolvable unit → error, ask for `--to`.
3. **`--here` → `F<n>`.** Append `- [ ] F<n>  <what>` to the unit's `progress.md` `## Follow-ups` (create the section if absent). `F<n>` = the unit's next monotonic id, from the high-water of `F` ids across `progress.md` + `log.md` notes, never reused (SPEC). Append `note  added F<n>` to that unit's `log.md`.
4. **`--defer` → `WF<n>`.** Append `- [ ] WF<n>  <what>  (from <origin>, <ts>)` to `backlog.md` `## Follow-ups` (create if absent). `<origin>` = the current / `--to` unit-id, else the `<ws-id>` when captured outside any unit (SPEC provenance). `WF<n>` = next monotonic per workstream (high-water = max `WF` ever in `backlog.md`; resolved lines are checked off, never deleted, so the counter can't regress).
5. **`--plan` → planned unit.** Append `- [ ] <slug>  base=<base>  [needs=<a>[,<b>]]  — <what>` to `## Planned units`. `slug = slug(what)`; `base` = `--base` (a unit-id stacks, else a branch), default the active `forge` flavor's `default-branch`. Validate each `--needs` target for self-need / cycle as `ws-start` does — skip and warn on a bad one. **Refuse** if a ledger unit already matches `<slug>` (already started; the line would derive-done at once — SPEC dedup-vs-ledger).
6. **Dedup.** Before appending any follow-up, scan the target section for a near-duplicate (normalized `<what>`); on a match, warn and confirm rather than writing a twin.

## Scope
Workstream-scoped (SPEC "Command scope") — store-only, runs from any session. `--here` writes a unit's `progress.md` / `log.md` **in the store**, never a worktree; the only git touch is reading the current branch to self-locate.

## Chain
Fire `hook-ws-backlog-after` (SPEC §Flavor hooks). No active flavor defines it → default chaining (SPEC Next-step chaining): a **planned unit** was added → offer **`ws-next`** now (a new startable item may re-route); a follow-up (`F`/`WF`) → offer **`ws-board`** to see where it landed. Name the target unit / workstream so a parallel-session user knows which.
