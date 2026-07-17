---
name: ws-board
description: Use when the user wants to see or share where a workstream stands — "show the board", "what's done", "workstream status", "what's blocked", "what's waiting on what".
argument-hint: "[ws-id] [unit-id]"
metadata:
  version: "0.4.0"
  author: Caio Ariede
---

# ws-board — workstream board

**Required first:** load the `ws` skill — it is the shared contract (SPEC) this skill references throughout.

**Input:** `$ARGUMENTS` = `[ws-id] [unit-id]`. A lone token that matches a store dir name is the `ws-id`, else it is a `unit-id` resolved via the SPEC bare-slug resolver. With 0 args and one workstream, use it; with 0 args and more than one, list them and ask which.

This skill is **read-only** — it derives everything and writes nothing.

## Steps
1. Read the `units.md` ledger and `backlog.md`. For each ledger unit derive its **status** per SPEC status rules and its **done/total task counts** from `progress.md` `## Tasks` (checked / total).
2. Render the board for on-screen reading — output it as **bare GFM markdown, never inside a fenced code block**. A code fence makes the terminal print literal `|` pipes instead of a rendered table; the fenced blocks below delimit the templates for this doc only — don't reproduce the fence in your output. This lands in a **terminal**, so every unit needs a real newline. Markdown table cells can't hold newlines, and `<br>` shows up as a literal `<br>` — so never stack units inside one cell. Give each unit its **own table row** instead: one unit per column per row, padding shorter columns with blank cells so the rows line up.
   ```
   *<name>* — <merged>/<total> units done[ · ✅ complete]

   | ⏳ Not started | ⛔ Blocked | 🔄 In progress | ✅ Done |
   | --- | --- | --- | --- |
   | <slug> | <slug> · needs <target>[, <target>][ · #<pr>] | <slug> · #<pr> · <done>/<total> | <slug> · #<pr> |
   | <slug> |  |  | <slug> · #<pr> |
   ```
   The **⛔ Blocked** column appears **only when ≥1 unit is blocked** — omit the column (header + separator + cells) entirely otherwise, leaving the original three-column board.

   The header's `<merged>/<total>` counts **board units**: `<merged>` = the Done column, `<total>` = every unit on the board — ledger units plus planned units with no matching ledger line, whether they land in Not-started or ⛔ Blocked. It tracks the whole workstream, not just started units.

   Append ` · ✅ complete` to the header **only when SPEC "Workstream done" holds** — defer to that definition, do not re-list its conditions here. Without the ✅, an N/N `<merged>/<total>` means the units merged but the workstream is **not** done: open backlog remains, shown in the 📋 Backlog section below.

   Column contents:
   - **Not started** — `backlog.md` `## Planned units` slugs with **no matching ledger unit** whose needs are **all satisfied** (§Dependencies). Slug only. (A blocked planned unit goes to ⛔ Blocked instead.)
   - **⛔ Blocked** — any unit with ≥1 unmet need (§Dependencies): a ledger unit whose derived status is `blocked`, or a planned unit (no ledger line) with an unmet need. Render `<slug> · needs <target>[, <target>][ · #<pr>]` — append ` · #<pr>` only when the unit has an open PR; a dropped/removed target shows `needs <target> (dropped)`.
   - **In progress** — ledger units whose status is `building` or `in-review` **and not blocked**: `<slug> · #<pr> · <done>/<total>`. No PR opened yet → drop the `· #<pr>` segment.
   - **Done** — ledger units whose status is `merged`: `<slug> · #<pr>`.

   Then, **only when it has items**, below the table — Backlog first, Dropped last:
   ```
   📋 *Backlog*
   - F<n> <gist> (follow-up from <unit>)
   - WF<n> <gist> (follow-up from <unit>)

   🗑 *Dropped*
   - <slug>
   ```
   **Backlog** = open follow-ups: per-unit in-flight (`F<n>` from a unit's `progress.md`) plus workstream-deferred (`WF<n>` from `backlog.md`). End each with `(follow-up from <unit>)` so its origin is visible — an `F<n>`'s origin is the unit whose `progress.md` holds it; a `WF<n>`'s is the `(from <unit-id|ws-id>, <ts>)` recorded on its `backlog.md` line. Trim each `<desc>` to a one-line summary (the gist — first sentence or less) so the board stays glanceable; the full text lives in the source file. **Dropped** = ledger units with status `dropped`. Omit a header entirely when it has nothing — an empty section is noise, not information.
3. With a `unit-id`: print that unit's full `progress.md` checklist (Tasks + Follow-ups), its `## Needs` with each need's target, derived satisfied/open state and note (§Dependencies) — plus the implicit base need when it is unmet, so a base-blocked unit's detail shows the dependency the ⛔ Blocked column already counts — plus recent `log.md` notes.
