---
name: ws-board
description: Use when the user wants to see or share where a workstream stands — "show the board", "what's done", "workstream status", "what's blocked", "what's waiting on what".
argument-hint: "[ws-id] [unit-id]"
metadata:
  version: "0.7.2"
  author: Caio Ariede
compatibility: requires python3 and the active forge CLI (gh by default) on PATH
---

# ws-board — workstream board

**Required first:** load the `ws` skill.

Read-only. A bundled script parses the store, resolves the active `forge` flavor and queries PR status per unit in parallel, derives status per SPEC §Source of truth, and prints a terminal-ready board (or one unit's detail). Run it and relay its output — **derive nothing by hand.**

## Run it

`scripts/board.py`, relative to this skill's directory (`${CLAUDE_PLUGIN_ROOT}/skills/ws-board/scripts/board.py` when set). Pass `$ARGUMENTS` through — `[ws-id] [unit-id]`, both optional; a bare workstream slug works (date prefix optional). With no args, the cwd branch selects the workstream when it matches a ledger unit (SPEC §Command scope); otherwise `MANY_WORKSTREAMS`:

```
python3 <this-skill-dir>/scripts/board.py [ws-id] [unit-id]
```

A `unit-id` or spike bare slug prints that target's detail instead of the board. Spikes show `[spike]` in the title — no PR sections.

## Print it verbatim

Print stdout as **bare GFM markdown, never inside a code fence** — a fence makes the terminal show literal `|` pipes instead of a table. The script already lays out one unit per row and adds the ⛔ Blocked column only when a unit is blocked; don't reformat or re-derive it. A focus line always sits between the header and the kanban table; `(none set)` means no active outcome.

## Exit 2 — you pick

The first stderr token says why: `MANY_WORKSTREAMS <list>` (no cwd-branch match and more than one workstream — ask which; the slug alone works), `AMBIGUOUS <matches>` (ask which), `NO_MATCH` / `NO_STORE` (report plainly). If `python3` or the forge CLI is missing, the board still renders PR-blind (every unit falls back to `building`) — say so if it looks that way.

## Next step

Per SPEC §Next-step chaining, offer `ws-next` — read-only. It is the only command this skill names: the board reports, the router decides which unit moves and what that takes. Offer it bare, in board and unit-detail mode alike; never name `ws-resume` here, not even for an in-progress or blocked unit.
