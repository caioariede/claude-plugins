---
name: ws-board
description: Use when the user wants to see or share where a workstream stands — "show the board", "what's done", "workstream status", "what's blocked", "what's waiting on what".
argument-hint: "[ws-id] [unit-id]"
metadata:
  version: "0.5.2"
  author: Caio Ariede
compatibility: requires python3 and the active forge CLI (gh by default) on PATH
---

# ws-board — workstream board

**Required first:** load the `ws` skill (the SPEC).

Read-only. A bundled script parses the store, resolves the active `forge` flavor and queries PR status per unit in parallel, derives status per the SPEC, and prints a terminal-ready board (or one unit's detail). Run it and relay its output — **derive nothing by hand.** (A `/ws-board` hook renders the same output with no model turn; this path covers natural language, unit detail, and disambiguation.)

## Run it

`scripts/board.py`, relative to this skill's directory (`${CLAUDE_PLUGIN_ROOT}/skills/ws-board/scripts/board.py` when set). Pass `$ARGUMENTS` through — `[ws-id] [unit-id]`, both optional; a bare workstream slug works (date prefix optional):

```
python3 <this-skill-dir>/scripts/board.py [ws-id] [unit-id]
```

A `unit-id` (or a lone bare slug) prints that unit's detail instead of the board.

## Print it verbatim

Print stdout as **bare GFM markdown, never inside a code fence** — a fence makes the terminal show literal `|` pipes instead of a table. The script already lays out one unit per row and adds the ⛔ Blocked column only when a unit is blocked; don't reformat or re-derive it.

## Exit 2 — you pick

The first stderr token says why: `MANY_WORKSTREAMS <list>` (ask which; the slug alone works), `AMBIGUOUS <matches>` (ask which), `NO_MATCH` / `NO_STORE` (report plainly). If `python3` or the forge CLI is missing, the board still renders PR-blind (every unit falls back to `building`) — say so if it looks that way.

## Next step

Per SPEC §Next-step chaining, offer the single best next command (default yes): usually `ws-next` (the router), or `ws-resume <unit>` for an in-progress or blocked unit.
