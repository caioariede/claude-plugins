---
name: ws-focus
description: >-
  Use when the user names what the workstream is trying to achieve next —
  a demo milestone, a user-visible outcome, or a north-star slice. Triggers:
  "set focus", "what are we aiming for", "capture the outcome", "switch
  focus", "done with this focus". NOT for unit tasks (ws-resume / T<n>),
  backlog capture (ws-backlog), or routing which unit moves (ws-next).
argument-hint: 'show | add "<outcome>" | activate <slug> | done [slug] [--ws <ws-id>]'
metadata:
  version: "0.1.1"
  author: Caio Ariede
compatibility: requires python3 on PATH
---

# ws-focus — workstream outcome queue

**Required first:** load the `ws` skill — the shared contract (SPEC) this skill references throughout.

`ws-focus` maintains `<store>/<ws-id>/focus.md` — a **manual** queue of user-visible outcomes that steer `ws-next`'s `suggest` proposals. One line is **active** (`[>]`) at a time; the rest are queued (`[ ]`) or recently done (`[x]`, last three kept). Nothing auto-advances — the user activates the next outcome explicitly. Workstream-scoped, store-only, runs from any session (SPEC "Command scope").

**Input:** a subcommand plus optional `[ws-id]` (bare slug works):
- `show` — print the focus queue.
- `add "<outcome>"` — append; promotes to `[>]` when no active line exists.
- `activate <slug>` — flip marks: target becomes active, prior active returns to queued.
- `done [slug]` — mark done; omit slug to complete the active line.

## Run it

Bundled at `scripts/focus.py` relative to this skill's directory (`${CLAUDE_PLUGIN_ROOT}/skills/ws-focus/scripts/focus.py` when set):

```
python3 <this-skill-dir>/scripts/focus.py show [ws-id]
python3 <this-skill-dir>/scripts/focus.py add [ws-id] "<outcome>"
python3 <this-skill-dir>/scripts/focus.py activate [ws-id] <slug>
python3 <this-skill-dir>/scripts/focus.py done [ws-id] [slug]
```

Pass `$ARGUMENTS` through. Relay `show` stdout as bare markdown. Write subcommands print nothing on success.

## File shape

`focus.md` holds one section:

```
## Focus
- [>] <slug>  — <outcome>
- [ ] <slug>  — <outcome>
- [x] <slug>  — <outcome>
```

`<slug>` = `slug(<outcome>)` per SPEC ids. The em-dash separator matches other store files.

## Exit 2 — you pick

Same tokens as ws-board: `MANY_WORKSTREAMS` (no cwd-branch match), `AMBIGUOUS`, `NO_MATCH`, `NO_STORE`. Focus-specific: `NO_ACTIVE` (done with no active line), `DUPLICATE_SLUG`, `BAD_ARGS`. Zero-arg workstream locate matches ws-board (SPEC Command scope).

## Scope

Workstream-scoped — writes only `focus.md` in the store, never a worktree.

## Chain

Fire `hook-ws-focus-after` (SPEC §Flavor hooks). No active flavor defines it → default chaining (SPEC Next-step chaining): after a **write** (`add`, `activate`, `done`) → offer **`ws-next`** now (focus changed what `suggest` proposes); after **`show`** → offer **`ws-board`** to see unit status alongside the outcome queue. Name the workstream so a parallel-session user knows which.
