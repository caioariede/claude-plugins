---
name: ws-board
description: Use when the user wants to see or share where a workstream stands — "show the board", "what's done", "workstream status".
---

# ws-board — workstream board

Read the shared contract first: `${CLAUDE_PLUGIN_ROOT}/ws-shared/SPEC.md`.

**Input:** `$ARGUMENTS` = `[ws-id] [unit-id]`. A lone token that matches a store dir name is the `ws-id`, else it is a `unit-id` resolved via the SPEC bare-slug resolver. With 0 args and one workstream, use it; with 0 args and more than one, list them and ask which.

This skill is **read-only** — it derives everything and writes nothing.

## Steps
1. Read the `units.md` ledger and `backlog.md`. For each ledger unit derive its **status** per SPEC status rules and its **task/follow-up counts** from `progress.md`.
2. Render markdown grouped by state — copy-paste ready:
   ```
   *<name>* — <merged>/<total> units done

   ✅ Done          • <title> — #<pr>
   🔄 In progress   • <title> — #<pr> (<state>) · <done>/<total> tasks
   ⏳ Not started   • <slug>   base=<...>
   🗑 Dropped       • <title>
   ```
   "Not started" = `backlog.md` `## Planned units` whose `<slug>` has **no
   matching ledger unit** (dedup vs ledger — starting one drops it from this
   row automatically). Then list open follow-ups: per-unit in-flight
   (`F#` + unit) and workstream-deferred from `backlog.md` (`WF#`).
3. With a `unit-id`: print that unit's full `progress.md` checklist plus recent `log.md` notes.
