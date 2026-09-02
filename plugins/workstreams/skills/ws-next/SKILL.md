---
name: ws-next
description: Use when unsure which ws-* command or which unit to act on next in a workstream — after finishing a unit, when a PR merges, or any "what now?" moment across units. Lists every unit that can move right now and marks one as the default; it does not do the work (that's ws-resume).
argument-hint: "[ws-id]"
metadata:
  version: "0.24.0"
  author: Caio Ariede
compatibility: requires python3 and the active forge CLI (gh by default) on PATH
---

# ws-next — what can move next in a workstream

**Required first:** load the `ws` skill.

Read-only. A bundled script derives status and ranks every move runnable right now — one per unit or spike, default first. Relay it; derive nothing by hand. Listing a move is not running it, and the only place you compose new work is Propose a unit.

## Run it

Pass `$ARGUMENTS` — `[ws-id]`, optional; a bare workstream slug works, the date prefix is optional. With no args, the cwd branch selects the workstream when it matches a ledger unit (SPEC §Command scope):

```
python3 <this-skill-dir>/scripts/next.py [ws-id]
```

Exit 2 — the first stderr token says why: `MANY_WORKSTREAMS <list>` (ask which, re-run — the slug alone works), `AMBIGUOUS <matches>` (ask which, re-run with the exact id), `NO_MATCH` / `NO_STORE` (report plainly).

## Relay the output

Print stdout minus the machine parts, which are for you, not the user:

- each move line's tail — everything from `   run=` onward: `run=<command>` (fully resolved) and `branch=<branch>` when the unit has a worktree;
- the `Proposable:`, `Covered:`, `Design:`, `ActiveFocus:`, `FocusQueue:`, `Stackable:` and `ProposeSummary:` blocks.

Move lines read `<unit> — <verb>: <why>` (verb `restack` or `advance`), ranked by line order, `[default]` on the first. Keep them unnumbered — every number on screen belongs to the live picker — and keep `ws-*` commands out of the list: the choice on offer is which unit to move, and the one command for the picked unit comes from Chain. Don't re-derive or re-rank. Keep the `[default]` move as the default unless the session gives a concrete reason to prefer another (the user just said they want a particular unit finished); if you override it, say why. Never run a `run=` command unless the user explicitly picks that move or a Chain option that resolves to `<command>`.

**Store-incomplete units** — a `<why>` or `readiness=` containing `plan-pause`, `store incomplete`, or `no tasks planned yet` means the unit's tasks are not in `progress.md` yet. Never describe it as "in flight", "covered", or "implementation underway"; it still dedups proposals (`Covered:`). When proposing `--base` on it, state that dependents stay blocked until the base store is backfilled.

**No moves** — the headline names the state:

- `blocker dropped/removed` — carries a `Next:` command; relay it.
- `no store work left` / `focus: <slug>` — `suggest`; go to Propose a unit.
- `open backlog remains` / `advance a blocker` — residue no proposal can take. Help the user work the listed items; don't invent a command.
- `no units yet` — name `ws-start`. `workstream done` — offer to close it.

## Propose a unit

Enter in full `suggest` (no moves), or when the user picks a **Propose from …** option in Chain.

Material comes from the script: `Proposable:` follow-ups no live unit claims (`blocks=` names the units one blocks; `WF<n>` are workstream follow-ups, `<slug>:F<n>` unit follow-ups), `Design:` (read the spec at that path — not a URL or user paste — and diff it against `Covered:`), and `ActiveFocus:` / `FocusQueue:` (the active outcome and the queued ones).

### Strategy picker

Full `suggest` only — a lane picked in Chain skips this. Offer only lanes with material, in this order:

| Lane | When shown |
|------|-----------|
| `{id} — {desc} (blocks {units})` | one per follow-up with `blocks=` |
| `From focus: {slug}` | `ActiveFocus:` set |
| `From design spec` | `Design:` present, no active focus |
| `Unit follow-ups` — or `{id} — {desc}` when exactly one | non-blocking `<slug>:F<n>` |
| `Workstream follow-ups` — or `{id} — {desc}` when exactly one | non-blocking `WF<n>` |

**From focus** reads design when present, else focus outcome + workstream context. Batch lanes group by cohesion; prefer two units over one lumpy PR. If design has scope outside the active focus, mention it once — proceed or run `ws-focus` first.

### Candidate picker

Compose up to 3 candidates. Never re-propose `Covered:` scope — dropped and superseded units stay covered; redo goes through `ws-start`'s `restart-of` path. Candidate text is intent: it becomes the slug and `charter.md` purpose.

**Stacking (design/focus lanes only)** — consume `Stackable:`:

- Stack only when the scope clearly depends on unfinished work in a `Stackable:` entry; otherwise propose unstacked off the default branch. One candidate per intent, not stacked and unstacked variants.
- `--base <slug>` only from a `Stackable:` line. Never a unit not listed, never cross-repo (say so; offer unstacked or a same-repo alternative), never a non-unit branch.
- A `--base` candidate's label ends `(stacks on <slug> - <readiness>)`, dropping ` - <readiness>` when the line has none; no annotation otherwise.
- `Stackable:` present but empty → unstacked only; if design implies stacking, say no same-repo in-flight base is available.

A pick → `ws-start <ws-id> "<what>"`, plus `--claims` listing **every** follow-up the candidate closes (an omitted one stays open and keeps its dependent blocked), plus `--base <slug>` when stacking. Nothing is written until that command runs from the hook.

Declining at any proposal step — dismissing the picker — leaves the store untouched. During Chain, also print the default move's resolved command — same as dismissing the unit question. An accepted proposal is a `start` move for Chain: a unit, a command, no branch yet.

## Chain

**Propose options.** When moves exist and the script emitted any of `Proposable:` / `Covered:` / `Design:`, build one **Propose from …** option per strategy-picker lane — same labels and order, prefixed `Propose from `, a leading `From ` dropped: `Propose from design spec`, `Propose from Workstream follow-ups`, `Propose from WF4 — harden it (blocks dep)`. Never a generic **Propose next unit**. `ProposeSummary:` is informational only.

**Settle the unit.** Two or more moves, or one move with propose options → ask which one moves: the top three moves in script order, labelled by slug with `<verb>: <why>` as description, the first marked default; then the **Propose from …** options last, never default. Moves past the third stay in the relayed list and are picked by naming the unit. One move and no propose options → skip the question. Picking a unit runs nothing — the hook below is the only gate; a dismissal ends by printing the default move's resolved command. A **Propose from …** pick goes to the candidate picker for that lane.

With `ActiveFocus:` and 2+ moves, prefer the unit whose charter/tasks serve the focus and say why when that overrides the default — never over a `restack` move, and never over a move that unblocks dependents unless the user picks otherwise.

**Fire the hook.** With the unit settled, fire `hook-ws-next-after` (SPEC §Flavor hooks) with `<unit>`, `<branch>` and `<command>` from its line; a move without `branch=` leaves `<branch>` unfillable. Run the chosen instruction per SPEC §Next-step chaining. No active flavor defines the hook → offer "not now / run here" (opt-in, Not now first). Whatever the outcome, end by printing the picked unit's resolved command, naming the unit, so it can run in another session. No-move states have nothing to hook — present what the state calls for and stop; Propose a unit is the exception and fires the hook as a `start` move.
