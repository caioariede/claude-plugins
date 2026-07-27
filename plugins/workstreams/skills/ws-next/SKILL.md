---
name: ws-next
description: Use when unsure which ws-* command or which unit to act on next in a workstream — after finishing a unit, when a PR merges, or any "what now?" moment across units. Lists every unit that can move right now and marks one as the default; it does not do the work (that's ws-resume).
argument-hint: "[ws-id]"
metadata:
  version: "0.7.0"
  author: Caio Ariede
compatibility: requires python3 and the active forge CLI (gh by default) on PATH
---

# ws-next — what can move next in a workstream

**Required first:** load the `ws` skill — the shared contract (SPEC).

**Read-only, and derives nothing by hand.** A bundled script parses the store, resolves the active `forge` flavor and queries PR status per unit in parallel, derives each unit's status, and ranks every move runnable right now — one per unit, default first. It writes nothing; the commands behind those moves — separate skills — perform any change. Listing a move is not running it.

## Run the script

Bundled at `scripts/next.py` relative to this skill's directory (when set, `${CLAUDE_PLUGIN_ROOT}/skills/ws-next/scripts/next.py`). Pass `$ARGUMENTS` — `[ws-id]`, optional; a bare workstream slug works, the date prefix is optional:

```
python3 <this-skill-dir>/scripts/next.py [ws-id]
```

## Relay the output

Print the script's stdout, minus each move line's machine tail — everything from `   run=` onward is for you, not the user. Its shape:

- a one-line headline (why the default move leads),
- `<n>. <unit> — <verb>: <why>` per runnable move, ranked, `[default]` on the first. The stripped tail carries `run=<command>` (already fully resolved — every argument literal, no `<placeholder>` left in) and, when the unit has a worktree, `branch=<branch>`,
- `Next: <command>   (unit: <slug>, branch: <b>)` — only in the triage-dropped fallback, which has no move list,
- `Blocked: <unit> — needs <target>[, <target>]` — one line per blocked unit, omitted when none,
- `Open backlog:` + a list — triage/done states only, where there is no move.

Show units and what they need, never `ws-*` commands. Don't re-derive or re-rank — the rules ran in code. Keep the `[default]` move as the default unless the session gives you a concrete reason to prefer another (the user just said they want a particular unit finished); if you override it, say why. When there is **no** move at all, the script emitted a triage or done state: help the user work the listed items (promote a planned unit, resolve or discard a follow-up, or close the workstream), don't invent a command.

## When it exits 2

Same as ws-board — the first stderr token says why: `MANY_WORKSTREAMS <list>` (ask which, re-run — the slug alone works), `AMBIGUOUS <matches>` (ask which, re-run with the exact id), `NO_MATCH` / `NO_STORE` (report plainly).

## Chain

When the script lists moves, fire the `hook-ws-next-after` flavor hook (SPEC §Flavor hooks) for the default move — `<unit>`, `<branch>` and `<command>` come from that move's line. If the user picks another listed unit instead, re-fire the hook with that move's fills. A move with no `branch=` leaves `<branch>` unfillable, so choices naming it drop out (SPEC §Flavor hooks) — a `start` move has no worktree yet, and `ws-start` fires its own `hook-ws-start-after` once it does.

The active flavor owns what the choices offer; run the chosen instruction per SPEC Next-step chaining (`<command>` → run it in this session; anything else → the flavor's own handoff: run it, re-emit the command, stop). The named command starts code work, so it is never what a dismissal does: the safe choice comes first and running it here is an explicit pick. Whatever the outcome, end by printing the picked unit's resolved command, so it can run in another session. No active flavor defines the hook → offer "not now / run here", not-now first. A triage or done state has no move — skip the hook, present the items, and stop. Name the unit for a unit-scoped command so a parallel-session user knows which one.
