---
name: ws-focus
description: >-
  Use when the user names what the workstream is trying to achieve next —
  a demo milestone, a user-visible outcome, or a north-star slice. Triggers:
  "set focus", "what are we aiming for", "capture the outcome", "switch
  focus", "done with this focus". NOT for unit tasks (ws-resume / T<n>),
  backlog capture (ws-backlog), or routing which unit moves (ws-next).
argument-hint: 'list | add "<outcome>" | activate <n|slug> | done [n|slug] | move <from> <to> [--ws <ws-id>]'
metadata:
  version: "0.2.3"
  author: Caio Ariede
compatibility: requires python3 on PATH
---

# ws-focus — workstream outcome queue

**Required first:** load the `ws` skill.

`ws-focus` maintains `<store>/<ws-id>/focus.md` — a **manual** queue of user-visible outcomes that steer `ws-next`'s `suggest` proposals. Open focuses preserve insertion order; one line is **active** (`[>]`) at a time; recently done lines (`[x]`, last three kept) trail the open list. Nothing auto-advances — the user activates explicitly.

**Input:** a subcommand plus optional `[ws-id]` (bare slug works):
- `list` — numbered view of open focuses; active marked; done tail below.
- `add "<outcome>"` — append as `[ ]` at end; never auto-activates.
- `activate <n|slug>` — flip marks in place; number from `list`.
- `done [n|slug]` — mark done; omit to complete the active line.
- `move <from> <to>` — reorder open list (1-based positions from `list`).

## Run it

Pass `$ARGUMENTS` through. Relay `list` stdout as bare markdown. Write subcommands print nothing on success.

```
python3 <this-skill-dir>/scripts/focus.py list [ws-id]
python3 <this-skill-dir>/scripts/focus.py add [ws-id] "<outcome>"
python3 <this-skill-dir>/scripts/focus.py activate [ws-id] <n|slug>
python3 <this-skill-dir>/scripts/focus.py done [ws-id] [n|slug]
python3 <this-skill-dir>/scripts/focus.py move [ws-id] <from> <to>
```

## Exit 2 — you pick

Same tokens as ws-board: `MANY_WORKSTREAMS` (no cwd-branch match), `AMBIGUOUS`, `NO_MATCH`, `NO_STORE`. Focus-specific: `NO_ACTIVE` (done with no active line), `DUPLICATE_SLUG`, `OUT_OF_RANGE` (bad number for activate, done, or move), `BAD_ARGS`. Zero-arg workstream locate matches ws-board (SPEC §Command scope).

## Chain

When chained from `ws-init` on an empty queue, prompt for the first outcome (may suggest wording from `workstream.goal`; do not auto-write), run `add`, then suggest `activate`.

Fire `hook-ws-focus-after` (SPEC §Flavor hooks). No active flavor defines it → default chaining (SPEC §Next-step chaining): after **`add`** → suggest **`activate`** (not `ws-next` until something is active); after **`activate`** → offer **`ws-next`**; after **`done`** with open items remaining → list numbered **`activate`** choices; after **`list`** → offer **`ws-board`**. Name the workstream so a parallel-session user knows which.
