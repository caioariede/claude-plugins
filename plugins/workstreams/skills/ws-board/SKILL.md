---
name: ws-board
description: Use when the user wants to see or share where a workstream stands — "show the board", "what's done", "workstream status", "what's blocked", "what's waiting on what".
argument-hint: "[ws-id] [unit-id]"
metadata:
  version: "0.5.1"
  author: Caio Ariede
compatibility: requires python3 and the active forge CLI (gh by default) on PATH
---

# ws-board — workstream board

**Required first:** load the `ws` skill — the shared contract (SPEC) this skill relies on.

This skill is **read-only** and **derives nothing by hand.** A bundled script parses the store, resolves the active `forge` flavor and queries PR status for every unit in parallel, derives status per the SPEC, and prints a terminal-ready board (or one unit's detail). Your job is to run it and relay its output — the deterministic work lives in `ws/scripts/ws_store.py`, shared so `ws-next` can reuse it.

## Run the script

It ships at `scripts/board.py` relative to this skill's directory (when set, `${CLAUDE_PLUGIN_ROOT}/skills/ws-board/scripts/board.py`). Pass `$ARGUMENTS` straight through — `[ws-id] [unit-id]`, both optional:

```
python3 <this-skill-dir>/scripts/board.py [ws-id] [unit-id]
```

With a `unit-id` (or a lone bare slug that resolves to one) it prints that unit's detail — checklist, needs with derived state, recent log — instead of the board.

## Print the output verbatim

Print stdout **as bare GFM markdown, never inside a code fence.** A fence makes the terminal show literal `|` pipes instead of a rendered table. The script already emits one unit per row with real newlines, and includes the ⛔ Blocked column only when a unit is blocked — don't reformat, re-wrap, or re-derive it.

## When it exits 2

The script couldn't choose a target on its own; the first stderr token says why:

- `MANY_WORKSTREAMS <list>` — no args and more than one workstream. Show the list, ask which, re-run with that `ws-id` (its slug alone works — the date prefix is optional).
- `AMBIGUOUS <matches>` — a slug matches more than one workstream (same slug, different dates) or more than one unit. Show the matches, ask which, and re-run with the exact id (for a unit, pass `<ws-id>` and `<slug>` as two args).
- `NO_MATCH` / `NO_STORE` — report it plainly; there is nothing to show.

If `python3` or the forge CLI is missing, or the forge is unreachable, the board still renders — every unit without resolvable PR state simply falls back to `building`. Say so if the result looks PR-blind.

## Next step

Per SPEC §Next-step chaining, end by offering the single best next command (default yes). The board is a read; the natural next move is `ws-next` (the router — what to start next) or `ws-resume <unit>` for an in-progress or blocked unit. Defer to `ws-next` when the next step isn't singular.
