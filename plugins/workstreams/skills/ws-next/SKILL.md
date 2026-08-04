---
name: ws-next
description: Use when unsure which ws-* command or which unit to act on next in a workstream — after finishing a unit, when a PR merges, or any "what now?" moment across units. Lists every unit that can move right now and marks one as the default; it does not do the work (that's ws-resume).
argument-hint: "[ws-id]"
metadata:
  version: "0.10.1"
  author: Caio Ariede
compatibility: requires python3 and the active forge CLI (gh by default) on PATH
---

# ws-next — what can move next in a workstream

**Required first:** load the `ws` skill — the shared contract (SPEC).

**Read-only, and derives nothing by hand.** A bundled script parses the store, resolves the active `forge` flavor and queries PR status per unit in parallel, derives each unit's status, and ranks every move runnable right now — one per unit, default first. It writes nothing; the commands behind those moves — separate skills — perform any change. Listing a move is not running it.

**One carve-out.** The `suggest` state is the only place in this skill where you decide anything rather than relay it — see Propose a unit. Ranked moves always came out of code.

## Run the script

Bundled at `scripts/next.py` relative to this skill's directory (when set, `${CLAUDE_PLUGIN_ROOT}/skills/ws-next/scripts/next.py`). Pass `$ARGUMENTS` — `[ws-id]`, optional; a bare workstream slug works, the date prefix is optional. With no args, the cwd branch selects the workstream when it matches a ledger unit (SPEC Command scope):

```
python3 <this-skill-dir>/scripts/next.py [ws-id]
```

## Relay the output

Print the script's stdout, minus each move line's machine tail — everything from `   run=` onward is for you, not the user — and minus machine blocks the script marks for you only (`Proposable:`, `Covered:`, `Design:`, `ActiveFocus:`, `FocusQueue:` and their lines). Its shape:

- a one-line headline (why the default move leads),
- `<unit> — <verb>: <why>` per runnable move, indented, ranked by line order, `[default]` on the first — no ordinals, so every number on screen belongs to the live picker. The verb is `restack`, `ship it`, `advance` or `start`. The stripped tail carries `run=<command>` (already fully resolved — every argument literal, no `<placeholder>` left in) and, when the unit has a worktree, `branch=<branch>`,
- `Next: <command>   (unit: <slug>, branch: <b>)` — only in the triage-dropped fallback, which has no move list,
- `Blocked: <unit> — needs <target>[, <target>]` — one line per blocked unit, omitted when none,
- `Open backlog:` + a list — no-move states only,
- `Proposable:` / `Covered:` / `Design:` / `ActiveFocus:` / `FocusQueue:` — machine material for you, not the user: consume them, don't print them. `ActiveFocus:` / `FocusQueue:` appear whenever focus is set (moves or `suggest`); `Proposable:` / `Covered:` / `Design:` only in `suggest`. `ActiveFocus:` names the active outcome (`<slug>  — <outcome>`); `FocusQueue:` lists queued outcomes the same way.

Keep `ws-*` commands out of the list — the choice on offer is which unit to move, and a wall of commands buries it. The one command for the unit that gets picked comes later, from Chain. Don't re-derive or re-rank — the rules ran in code. Keep the `[default]` move as the default unless the session gives you a concrete reason to prefer another (the user just said they want a particular unit finished); if you override it, say why.

When there is **no** move at all the script emitted one of these states, named in its headline:

- `blocker dropped/removed` — triage-dropped, which carries a `Next:` command.
- `no store work left` / `focus: <slug>` — **`suggest`**; go to Propose a unit. When active focus exists the headline is `focus: <slug> — propose the next unit`.
- `open backlog remains` / `advance a blocker` — residue no proposal can take (a planned unit behind an unresolvable need, an `F<n>` in a live blocked unit). Help the user work the listed items; don't invent a command.
- `no units yet` — an empty workstream with no design and nothing open. Say so and name `ws-start`; there is nothing to route.
- `workstream done` — offer to close it.

## When it exits 2

Same as ws-board — the first stderr token says why: `MANY_WORKSTREAMS <list>` (ask which, re-run — the slug alone works), `AMBIGUOUS <matches>` (ask which, re-run with the exact id), `NO_MATCH` / `NO_STORE` (report plainly).

## Propose a unit

Only in `suggest`, which the script emits only when **no** move exists — reaching it is the proof that proposing is the right thing to do. Never propose while any move is on the table.

Three steering sources, all supplied by the script: the `Proposable:` follow-ups (the open ones no live unit already claims — each with a `from=` origin when the id doesn't already carry it, and `blocks=` when it blocks a live unit), the design spec at `Design:`, and `ActiveFocus:` / `FocusQueue:` when set. Read the design spec **now**; this state is the only reason to open it. Diff it against `Covered:` — the ledger slugs, titles, and planned units the store already accounts for.

Compose 1–3 candidates under five constraints:

1. **Urgency beats batching.** A follow-up carrying `blocks=` is proposed **alone and first**; bundling it into a larger batch keeps that unit blocked for the life of the batch.
1b. **Focus beats non-blocking follow-ups.** When `ActiveFocus:` is set, prefer design-sourced candidates that advance it over proposable follow-ups without `blocks=`.
2. **Batch by cohesion.** Group follow-ups only when they touch the same area and review well together — and only when no focus-aligned design candidate exists. Prefer two units over one lumpy PR.
3. **Never re-propose `Covered:` scope.** A dropped unit is covered — the drop was a decision, and its reason is in that unit's `log.md`. Redoing dropped work is `ws-start`'s `restart-of` path, chosen by the user.
4. **Say what a candidate does, not what section it came from.** The chosen text becomes the unit's slug and its `charter.md` purpose, so it has to read as intent on its own.

Present them with `Not now` first and preselected (work-starting, per SPEC Next-step chaining). A pick resolves to `ws-start <ws-id> "<what>"`, plus `--claims <targets>` when the candidate closes follow-ups, plus `--base` when it stacks. Nothing is written until that runs — a declined proposal leaves the store untouched and is not recorded, so it may come back next time it is still true.

A candidate that claims follow-ups must list **every** one it covers in `--claims`: the claim is what takes them out of the backlog and unblocks whatever needed them, so a follow-up you describe but omit stays open and keeps its dependent blocked.

For Chain below, an accepted proposal behaves exactly like a `start` move: a unit, a command, no branch yet.

## Chain

Settle the unit first. Two or more moves → ask which one moves: `Not now` is the first and preselected option, then the top three moves in the script's order, labelled by unit slug with `<verb>: <why>` as the description and the first marked as the default move. Moves past the third stay in the relayed list and are picked by naming the unit. A single move skips this question entirely. Picking a unit runs nothing — it only decides which move the next question is about — and a dismissal reads as `Not now`, which ends by printing the default move's resolved command.

**Soft nudge (2+ moves, when `ActiveFocus:` was emitted).** Prefer the unit whose charter/tasks plausibly serve the active focus; say why if you override the script's default. Never override a restack or ship move. Never override a move that unblocks dependents unless the user explicitly picks otherwise.

With the unit settled, fire the `hook-ws-next-after` flavor hook (SPEC §Flavor hooks) for that move — `<unit>`, `<branch>` and `<command>` come from its line. A move with no `branch=` leaves `<branch>` unfillable, so choices naming it drop out (SPEC §Flavor hooks) — a `start` move has no worktree yet, and `ws-start` fires its own `hook-ws-start-after` once it does.

The active flavor owns what the choices offer; run the chosen instruction per SPEC Next-step chaining (`<command>` → run it in this session; anything else → the flavor's own handoff: run it, re-emit the command, stop). The named command starts code work, so it is never what a dismissal does: the safe choice comes first and running it here is an explicit pick. Whatever the outcome, end by printing the picked unit's resolved command, so it can run in another session. No active flavor defines the hook → offer "not now / run here", not-now first. A no-move state has no move to hook — skip it, present what the state calls for, and stop; the one exception is an accepted `suggest` proposal, which fires the hook as a `start` move would. Name the unit for a unit-scoped command so a parallel-session user knows which one.
