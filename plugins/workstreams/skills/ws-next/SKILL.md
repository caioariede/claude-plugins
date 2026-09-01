---
name: ws-next
description: Use when unsure which ws-* command or which unit to act on next in a workstream — after finishing a unit, when a PR merges, or any "what now?" moment across units. Lists every unit that can move right now and marks one as the default; it does not do the work (that's ws-resume).
argument-hint: "[ws-id]"
metadata:
  version: "0.22.2"
  author: Caio Ariede
compatibility: requires python3 and the active forge CLI (gh by default) on PATH
---

# ws-next — what can move next in a workstream

**Required first:** load the `ws` skill.

**Read-only, and derives nothing by hand.** A bundled script parses the store, resolves the active `forge` flavor and queries PR status per unit in parallel, scans live units read-only for shipped-elsewhere evidence, derives each unit's and spike's status, and ranks every move runnable right now — one per unit or spike, default first. It never appends log lines or mutates `progress.md`; the commands behind those moves — separate skills — perform any change. Listing a move is not running it.

**Two carve-outs.** Ranked moves always came out of code. **Propose a unit** is the only place you compose new work — in full `suggest` (no moves) or when the user picks a **Propose from …** option from Chain (non-restack moves plus proposal material from the script).

## Run it

Pass `$ARGUMENTS` — `[ws-id]`, optional; a bare workstream slug works, the date prefix is optional. With no args, the cwd branch selects the workstream when it matches a ledger unit (SPEC §Command scope):

```
python3 <this-skill-dir>/scripts/next.py [ws-id]
```

## Relay the output

Print the script's stdout, minus each move line's machine tail — everything from `   run=` onward is for you, not the user — and minus machine blocks the script marks for you only (`Proposable:`, `Covered:`, `Design:`, `ActiveFocus:`, `FocusQueue:`, `Stackable:`, `ReconcileCandidates:` and their lines). Never run a stripped `run=` command unless the user explicitly picks that move or a Chain option that resolves to `<command>` — relaying output is not execution. Its shape:

- a one-line headline (why the default move leads),
- `<unit> — <verb>: <why>` per runnable move, indented, ranked by line order, `[default]` on the first — no ordinals, so every number on screen belongs to the live picker. The verb is `restack`, `ship it`, `advance` or `start`. Spike moves use the same shape; spike `run=` has no `branch=` tail. The stripped tail carries `run=<command>` (already fully resolved — every argument literal, no `<placeholder>` left in) and, when the unit has a worktree, `branch=<branch>`,
- `Next: <command>   (unit: <slug>, branch: <b>)` — only in the triage-dropped fallback, which has no move list,
- `Blocked: <unit> — needs <target>[, <target>]` — one line per blocked unit or `<slug> [spike] — needs …` per blocked spike, omitted when none,
- `Waiting: <unit> — PR #<n>` — one line per code-complete ready-PR unit with no move, omitted when none,
- `Open backlog:` + a list — no-move states only,
- `Proposable:` / `Covered:` / `Design:` / `ActiveFocus:` / `FocusQueue:` / `Stackable:` / `ProposeSummary:` — machine material for you, not the user: consume them, don't print them. `ActiveFocus:` / `FocusQueue:` appear whenever focus is set (moves or `suggest`); `Proposable:` / `Covered:` / `Design:` appear in `suggest` or alongside non-restack moves (see Chain). `Stackable:` lists valid `--base` unit-ids for design/focus proposals (tagged `repo=`, `branch=`, optional `readiness=`); empty when gated but none eligible, omitted when not in design/focus proposal mode. `ProposeSummary:` summarizes available proposal sources for you — consume it, don't relay it. `ActiveFocus:` names the active outcome (`<slug>  — <outcome>`); `FocusQueue:` lists queued outcomes the same way.

Keep `ws-*` commands out of the list — the choice on offer is which unit to move, and a wall of commands buries it. The one command for the unit that gets picked comes later, from Chain. Don't re-derive or re-rank — the rules ran in code. Keep the `[default]` move as the default unless the session gives you a concrete reason to prefer another (the user just said they want a particular unit finished); if you override it, say why.

**Store/git guardrails** — when a move's `<why>` or a `Stackable:` line's `readiness=` contains `plan-pause`, `store incomplete`, or `no tasks planned yet`:
- Never describe that unit as "in flight", "covered", or "implementation underway."
- When proposing `--base` on such a unit, state explicitly that **dependents stay blocked until the base store is backfilled** (tasks checked in `progress.md`).
- Do not change `Covered:` semantics — ledger dedup still applies.
- When `ReconcileCandidates:` is present, tell the user to run
  `ws-resume <slug>` for each listed unit before Propose a unit.
  Hard-gate Propose a unit and Chain **Propose from …** options until
  candidates are cleared. Still relay moves, Waiting, and Blocked.

When there is **no** move at all the script emitted one of these states, named in its headline:

- `blocker dropped/removed` — triage-dropped, which carries a `Next:` command.
- `reconcile before proposing` — **`reconcile-pending`**; ship evidence
  found for one or more units. Relay the headline and tell the user to
  run `ws-resume <slug>` per `ReconcileCandidates:` before proposing.
  Do not enter Propose a unit.
- `no store work left` / `focus: <slug>` — **`suggest`**; go to Propose a unit. When active focus exists the headline is `focus: <slug> — propose the next unit`.
- `open backlog remains` / `advance a blocker` — residue no proposal can take (a planned unit behind an unresolvable need, an `F<n>` in a live blocked unit). Help the user work the listed items; don't invent a command.
- `waiting on review` — every live unit is code-complete with a ready PR; nothing for the agent to advance. Relay the `Waiting:` lines; don't invent a command.
- `no units yet` — an empty workstream with no design and nothing open. Say so and name `ws-start`; there is nothing to route.
- `workstream done` — offer to close it.

## When it exits 2

Same as ws-board — the first stderr token says why: `MANY_WORKSTREAMS <list>` (ask which, re-run — the slug alone works), `AMBIGUOUS <matches>` (ask which, re-run with the exact id), `NO_MATCH` / `NO_STORE` (report plainly).

## Propose a unit

Enter this section in full `suggest` (no moves) or when the user picks a **Propose from …** option from Chain. Never enter it while a **`restack`** move exists — base drift suppresses proposal. Mid-flight `resume` no longer blocks.

Steering material comes from the script: `Proposable:` follow-ups (open ones no live unit claims — `blocks=` when one blocks a live unit), `Design:`, and `ActiveFocus:` / `FocusQueue:` when set. Read the design spec when `Design:` is emitted — the path is `workstream.md` `design:` from the store (workstream-owner path on disk), not an arbitrary URL or user paste; diff it against `Covered:` — ledger slugs, titles, and planned units the store already accounts for.

Split `Proposable:` by id shape: `WF<n>` → workstream follow-ups; `<slug>:F<n>` → unit follow-ups (`from=` confirms origin when the id doesn't carry it).

### Strategy picker

Ask which lane before composing — **full `suggest` only**. When the user picked a lane from the Chain unit picker, skip this section and compose for that lane. `Not now` first and preselected; show only lanes with material.

Order: blocking follow-ups solo first (`{id} — {desc} (blocks {units})`); when the headline names focus (`focus: <slug>`), put `From focus: {slug}` before non-blocking follow-up lanes; then the rest.

| Lane | When shown |
|------|-----------|
| `{id} — {desc} (blocks {units})` | follow-up with `blocks=` |
| `From focus: {slug}` | `ActiveFocus:` set |
| `From design spec` | `Design:` present, no active focus |
| `Unit follow-ups` | 2+ non-blocking `<slug>:F<n>` |
| `{id} — {desc}` | exactly one non-blocking follow-up |
| `Workstream follow-ups` | 2+ non-blocking `WF<n>` |
| `Not now` | always |

**From focus** reads design when present, else focus outcome + workstream context. Batch lanes group by cohesion (no checklist); prefer two units over one lumpy PR. If design has scope outside the active focus, mention once — proceed or run `ws-focus` first.

### Candidate picker

After a lane, compose up to 3 candidates:

1. **Never re-propose `Covered:` scope.** Dropped units and superseded lines stay covered; redo via `ws-start`'s `restart-of` path.
2. **Candidate text is intent** — it becomes slug and `charter.md` purpose.

**Design/focus lanes only** — consume `Stackable:` when composing (not follow-up lanes; those use `(blocks {units})` instead):

- Stack only when design/focus scope clearly depends on unfinished work in a `Stackable:` entry; otherwise propose unstacked off the default branch. One candidate per intent, not stacked and unstacked variants.
- Pick `--base <slug>` only from `Stackable:` lines matching the proposal repo. Never `--base` a unit not listed. Non-unit `--base <branch>` is out of scope here.
- Any candidate with `--base` must append `(stacks on <slug> - <readiness>)` to the picker label. Omit ` - <readiness>` when the line has no `readiness=` field. Unstacked candidates: no stack annotation. Annotation iff `--base` (biconditional).
- When `Stackable:` is present but empty: propose unstacked only; if design implies stacking, say no same-repo in-flight base is available.
- If design implies stacking on another repo's unit: say so; offer unstacked or same-repo alternative — never cross-repo `--base`.

Present with `Not now` first (opt-in, SPEC §Next-step chaining). Pick → `ws-start <ws-id> "<what>"`, plus `--claims` when closing follow-ups, plus `--base <slug>` when stacking per the rules above. Nothing is written until that runs.

Declining at any proposal step leaves the store untouched. During Chain, also print the default move's resolved command — same as dismissing the unit question.

A candidate that claims follow-ups must list **every** one it covers in `--claims`: the claim is what takes them out of the backlog and unblocks whatever needed them, so a follow-up you describe but omit stays open and keeps its dependent blocked.

For Chain below, an accepted proposal behaves exactly like a `start` move: a unit, a command, no branch yet.

## Chain

**Detecting proposal in Chain.** When `moves` is non-empty and the script emitted any of `Proposable:` / `Covered:` / `Design:` (machine blocks you consume, not relay), non-restack moves may carry proposal material — offer one **Propose from …** option per composable lane (see below).

Build each Chain propose option from `strategy_lanes()` — same labels and order as the strategy picker, prefixed `Propose from ` with a leading `From ` stripped from the lane when present. Examples: `Propose from design spec`, `Propose from workstream follow-ups`, `Propose from WF4 — harden it (blocks dep)`. One lane → one option; two or more → one option per lane — never a generic **Propose next unit**. `ProposeSummary:` is informational only.

Settle the unit first. Two or more moves, **or** one move with proposal material alongside → ask which one moves: `Not now` is the first and preselected option, then the top three moves in the script's order, labelled by unit slug with `<verb>: <why>` as the description and the first marked as the default move, then each **Propose from …** option last when proposal material is present (never preselected, never default). Moves past the third stay in the relayed list and are picked by naming the unit. A single move with no proposal material skips this question entirely. Picking a unit runs nothing — it only decides which move the next question is about — and a dismissal reads as `Not now`, which ends by printing the default move's resolved command. Picking a **Propose from …** option goes to the candidate picker for that lane; an accepted proposal fires `hook-ws-next-after` like a `start` move.

**Soft nudge (2+ moves, when `ActiveFocus:` was emitted).** Prefer the unit whose charter/tasks plausibly serve the active focus; say why if you override the script's default. Never override a restack or ship move. Never override a move that unblocks dependents unless the user explicitly picks otherwise.

With the unit settled, fire the `hook-ws-next-after` flavor hook (SPEC §Flavor hooks) for that move — `<unit>`, `<branch>` and `<command>` come from its line. A move with no `branch=` leaves `<branch>` unfillable, so choices naming it drop out (SPEC §Flavor hooks) — a `start` move has no worktree yet, and `ws-start` fires its own `hook-ws-start-after` once it does.

The active flavor owns what the choices offer; run the chosen instruction per SPEC §Next-step chaining (`<command>` → run it in this session; anything else → the flavor's own handoff: run it, re-emit the command, stop). The named command starts code work, so it is never what a dismissal does: the safe choice comes first and running it here is an explicit pick. Whatever the outcome, end by printing the picked unit's resolved command, so it can run in another session. No active flavor defines the hook → offer "not now / run here" (opt-in — Not now first). A no-move state has no move to hook — skip it, present what the state calls for, and stop; the exception is Propose a unit (full `suggest` or an accepted **Propose from …** pick), which fires the hook as a `start` move would. Name the unit for a unit-scoped command so a parallel-session user knows which one.
