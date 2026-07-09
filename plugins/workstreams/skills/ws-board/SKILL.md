---
name: ws-board
description: Use when the user wants to see or share where a workstream stands — "show the board", "what's done", "workstream status".
argument-hint: [ws-id] [unit-id]
---

# ws-board — workstream board

Read the shared contract first: `${CLAUDE_PLUGIN_ROOT}/ws-shared/SPEC.md`.

**Input:** `$ARGUMENTS` = `[ws-id] [unit-id]`. A lone token that matches a store dir name is the `ws-id`, else it is a `unit-id` resolved via the SPEC bare-slug resolver. With 0 args and one workstream, use it; with 0 args and more than one, list them and ask which.

This skill is **read-only** — it derives everything and writes nothing.

## Steps
1. Read the `units.md` ledger and `backlog.md`. For each ledger unit derive its **status** per SPEC status rules and its **done/total task counts** from `progress.md` `## Tasks` (checked / total).
2. Render the board — copy-paste ready. This lands in a **terminal**, so every unit needs a real newline. Markdown table cells can't hold newlines, and `<br>` shows up as a literal `<br>` — so never stack units inside one cell. Give each unit its **own table row** instead: one unit per column per row, padding shorter columns with blank cells so the rows line up.
   ```
   *<name>* — <merged>/<total> units done

   | Not started | In progress | Done |
   | --- | --- | --- |
   | <slug> | <slug> · #<pr> · <done>/<total> | <slug> · #<pr> |
   | <slug> |  | <slug> · #<pr> |
   ```
   The header's `<merged>/<total>` counts **board units**: `<merged>` = the Done column, `<total>` = every unit on the board (ledger units + not-started planned). It tracks the whole workstream, not just started units.

   Column contents:
   - **Not started** — `backlog.md` `## Planned units` slugs with **no matching ledger unit** (dedup vs ledger — starting one drops it from this column automatically). Slug only.
   - **In progress** — ledger units whose status is `building` or `in-review`: `<slug> · #<pr> · <done>/<total>`. No PR opened yet → drop the `· #<pr>` segment.
   - **Done** — ledger units whose status is `merged`: `<slug> · #<pr>`.

   Then, **only when it has items**, below the table — Backlog first, Dropped last:
   ```
   *Backlog*
   - F<n> <desc> (<unit>)
   - WF<n> <desc>

   *Dropped*
   - <slug>
   ```
   **Backlog** = open follow-ups: per-unit in-flight (`F<n>` from unit `progress.md`, tagged with its unit) plus workstream-deferred (`WF<n>` from `backlog.md`). Trim each `<desc>` to a one-line summary (the gist — first sentence or less) so the board stays glanceable; the full text lives in `backlog.md` / the unit's `progress.md`. **Dropped** = ledger units with status `dropped`. Omit a header entirely when it has nothing — an empty section is noise, not information.
3. With a `unit-id`: print that unit's full `progress.md` checklist plus recent `log.md` notes.
