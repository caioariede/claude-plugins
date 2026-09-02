---
name: ws-next
description: Use when unsure which ws-* command or which unit to act on next in a workstream — after finishing a unit, when a PR merges, or any "what now?" moment across units. Lists every unit that can move right now and marks one as the default; it does not do the work (that's ws-resume).
argument-hint: "[ws-id]"
metadata:
  version: "0.24.1"
  author: Caio Ariede
compatibility: requires python3 and the active forge CLI (gh by default) on PATH
---

# ws-next — what can move next in a workstream

**Required first:** load the `ws` skill.

Read-only. The script derives status and ranks every runnable move; relay it and derive nothing by hand.

## Run it

```
python3 <this-skill-dir>/scripts/next.py $ARGUMENTS
```

Exit 2 — the first stderr token says why: `MANY_WORKSTREAMS <list>` / `AMBIGUOUS <matches>` → ask which and re-run (a bare slug works); `NO_MATCH` / `NO_STORE` → report plainly.

## Relay the output

Print stdout minus the parts meant for you:

- each move line's tail from `   run=` onward (`run=<command>`, and `branch=<branch>` when the unit has a worktree);
- the `Proposable:`, `Covered:`, `Design:`, `ActiveFocus:`, `FocusQueue:`, `Stackable:` and `ProposeSummary:` blocks.

Moves are ranked; the first carries `[default]`. Keep the list unnumbered (numbers belong to the picker) and free of `ws-*` commands (the choice is which unit; the command comes from Chain). Don't re-derive or re-rank. Keep `[default]` unless the session gives a concrete reason — the user wants a particular unit finished, or `ActiveFocus:` favors another — and never over a `restack` move or one that unblocks dependents; say why when you override. Never run a `run=` command except through the hook.

**Store-incomplete units** — a `<why>` or `readiness=` containing `plan-pause`, `store incomplete`, or `no tasks planned yet` means no tasks exist in `progress.md` yet. Never call it "in flight", "covered", or "underway"; it still dedups proposals (`Covered:`). When proposing `--base` on it, say dependents stay blocked until the base store is backfilled.

**No moves** — the headline names the state:

- `blocker dropped/removed` — relay its `Next:` command.
- `no store work left` / `focus: <slug>` — `suggest`; go to Propose a unit.
- `open backlog remains` / `advance a blocker` — help the user work the listed items; don't invent a command.
- `no units yet` — name `ws-start`. `workstream done` — offer to close it.

## Propose a unit

Enter in full `suggest`, or when the user picks a **Propose from …** option in Chain.

Material: `Proposable:` follow-ups no live unit claims (`blocks=` names the units one blocks), `Design:` (read the spec at that path — never a URL or paste — and diff it against `Covered:`), `ActiveFocus:` / `FocusQueue:`.

### Strategy picker

Full `suggest` only — a lane picked in Chain skips this. Offer only lanes with material, in this order:

| Lane | When shown |
|------|-----------|
| `{id} — {desc} (blocks {units})` | one per follow-up with `blocks=` |
| `From focus: {slug}` | `ActiveFocus:` set |
| `From design spec` | `Design:` present, no active focus |
| `Unit follow-ups` — or `{id} — {desc}` when exactly one | non-blocking `<slug>:F<n>` |
| `Workstream follow-ups` — or `{id} — {desc}` when exactly one | non-blocking `WF<n>` |

**From focus** reads design when present, else focus outcome + workstream context. Batch lanes group by cohesion; prefer two units over one lumpy PR. Design scope outside the active focus: say so once, offer `ws-focus`.

### Candidate picker

Up to 3 candidates. Never re-propose `Covered:` scope (dropped and superseded units included). Candidate text is intent: it becomes the slug and `charter.md` purpose.

**Stacking (design/focus lanes only)**, from `Stackable:`:

- `--base <slug>` only when the scope clearly depends on unfinished work in a listed entry; otherwise unstacked off the default branch. One candidate per intent, never both variants.
- No eligible base (empty `Stackable:`, or the design implies a unit not listed, e.g. in another repo) → unstacked only, and say so.
- A `--base` candidate's label ends `(stacks on <slug> - <readiness>)`, without ` - <readiness>` when the line has none; no annotation otherwise.

A pick → `ws-start <ws-id> "<what>"`, plus `--claims` naming **every** follow-up it closes (an omitted one stays open and keeps its dependent blocked), plus `--base <slug>` when stacking. Nothing is written until that command runs from the hook.

Declining at any proposal step — dismissing the picker — leaves the store untouched; during Chain, also print the default move's resolved command. An accepted proposal enters Chain as a `start` move: a unit, a command, no branch yet.

## Chain

**Propose options.** When moves exist alongside `Proposable:` / `Covered:` / `Design:`, add one **Propose from …** option per strategy-picker lane — same labels and order, a leading `From ` dropped (`Propose from design spec`, `Propose from WF4 — harden it (blocks dep)`). Never a generic **Propose next unit**.

**Settle the unit.** Two or more moves, or one move with propose options → ask which one moves: the top three moves in script order, labelled by slug with `<verb>: <why>`, the first marked default; then the **Propose from …** options, never default. Moves past the third are picked by naming the unit. One move and no propose options → skip the question. Picking runs nothing; a dismissal prints the default move's resolved command and stops. A **Propose from …** pick goes to the candidate picker for that lane.

**Fire the hook.** Fire `hook-ws-next-after` (SPEC §Flavor hooks) with `<unit>`, `<branch>` and `<command>` from the move's line (`<branch>` is unfillable without `branch=`); run the chosen instruction per SPEC §Next-step chaining. No active flavor defines it → offer "not now / run here", Not now first. Whatever the outcome, end by printing the picked unit's resolved command, naming the unit, so it can run in another session.
