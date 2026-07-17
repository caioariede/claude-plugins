---
name: ws-next
description: Use when unsure which ws-* command or which unit to act on next in a workstream — after finishing a unit, when a PR merges, or any "what now?" moment across units. Decides the next action; it does not do the work (that's ws-resume).
argument-hint: "[ws-id]"
metadata:
  version: "0.6.0"
  author: Caio Ariede
compatibility: requires python3 and the active forge CLI (gh by default) on PATH
---

# ws-next — recommend the next workstream action

**Required first:** load the `ws` skill — the shared contract (SPEC).

**Read-only, and derives nothing by hand.** A bundled script parses the store, resolves the active `forge` flavor and queries PR status per unit in parallel, derives each unit's status, and applies the SPEC decision table (first match wins) to name the single next command. It writes nothing; the command it names — a separate skill — performs any change. Naming a command is not running it.

## Run the script

Bundled at `scripts/next.py` relative to this skill's directory (when set, `${CLAUDE_PLUGIN_ROOT}/skills/ws-next/scripts/next.py`). Pass `$ARGUMENTS` — `[ws-id]`, optional; a bare workstream slug works, the date prefix is optional:

```
python3 <this-skill-dir>/scripts/next.py [ws-id]
```

## Relay the output

Print the script's stdout as-is. Its shape:

- a one-line headline (why this is the next move),
- `Next: <command>   (unit: <slug>)` — the action to run, already fully resolved (every argument literal, no `<placeholder>` left in),
- `Also unblocked (parallel): <slug>, <slug>` — only when more than one unit is startable now,
- `Blocked: <unit> — needs <target>[, <target>]` — one line per blocked unit, omitted when none,
- `Open backlog:` + a list — triage/done states only, where there is no `Next:` line.

Don't second-guess or re-derive the `Next:` line — the rules ran in code. When there's **no** `Next:` line, the script emitted a triage or done state: help the user work the listed items (promote a planned unit, resolve or discard a follow-up, or close the workstream), don't invent a command.

## When it exits 2

Same as ws-board — the first stderr token says why: `MANY_WORKSTREAMS <list>` (ask which, re-run — the slug alone works), `AMBIGUOUS <matches>` (ask which, re-run with the exact id), `NO_MATCH` / `NO_STORE` (report plainly).

## Chain

When the script emits a `Next:` command, fire the `hook-ws-next-after` flavor hook (SPEC §Flavor hooks) — fill `<unit>`/`<branch>` from the named unit and `<command>` from the `Next:` line verbatim. The active flavor owns what the choices offer; run the chosen instruction per SPEC Next-step chaining (`<command>` → run it in this session; anything else → the flavor's own handoff: run it, re-emit the command, stop). No active flavor defines the hook → default: offer to run it now (default yes), then run it — it works from the current session. A triage or done state (no `Next:`) has no runnable command — skip the hook, present the items, and stop. Name the unit for a unit-scoped command so a parallel-session user knows which one.
