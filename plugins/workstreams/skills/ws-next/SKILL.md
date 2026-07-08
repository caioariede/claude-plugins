---
name: ws-next
description: Use when unsure which ws-* command or which unit to act on next in a workstream — after finishing a unit, when a PR merges, or any "what now?" moment across units. Decides the next action; it does not do the work (that's ws-resume).
---

# ws-next — recommend the next workstream action

Read `${CLAUDE_PLUGIN_ROOT}/ws-shared/SPEC.md` first. **Read-only** — it derives and recommends; it writes nothing.

## What it does

Reads the ledger (`units.md`) and each unit's **derived status** (SPEC status rules) and prints THE single next command, which session to run it in, and any units that are unblocked in parallel. It does not mutate the store — the command it names does.

## Decision ladder (first match wins)

| # | If | Then | Session |
|---|----|------|---------|
| 1 | a **created** unit's base PR merged / GitHub retargeted it, and its branch isn't rebased yet | `ws-restack <unit>` | hub |
| 2 | a unit's tasks are **all checked** but it has **no PR** | **open its PR** (`gh pr create`, or superpowers:finishing-a-development-branch) | unit window |
| 3 | a unit is **in progress** (unchecked tasks) | `ws-resume <unit>` | unit window |
| 4 | a **backlog** planned unit whose base is **merged/`main`** and it's **not yet on the ledger** | `ws-start <ws> "<what>" --base <dep>` | hub |
| 5 | every unit is merged | workstream done — close it | hub |

Rung 4's planned units live in `backlog.md` `## Planned units`. When the stack is otherwise idle, a **deferred follow-up** (`WF#` in `backlog.md`) worth doing is promotable — recommend `ws-start` a unit for it (then check it off in `backlog.md`).

## Emitting the command

Walk the ladder first; write the `Next:` line **last** — never lead with a guess you then reason away. The emitted line must be the winning rung's command, verbatim.

```
Next: <one resolved command> — run in <the hub | the unit's window>.
Also unblocked (parallel): <unit>, <unit>   ← only when rung 4 has >1 qualifying unit
```

Emit exactly **one** clean, executable line:
- every argument a **literal** — no `<ws>` / `<unit>` / `<base>` placeholders left in;
- no retracted or false-start lines, no "wait"/"hold on" in the final answer; if you revise mid-reasoning, re-emit the whole command cleanly from the final decision;
- `ws-start <ws-id> "<what>" [--base <unit-id|branch>]` — the **first positional is the workstream id**, the unit is slugged from the quoted `"<what>"`, and `--base` is a merged dependency's unit-id or branch. Never put a unit name in the first slot.

Rung 2 (open the PR) fires **only** when a unit has **no PR AND every task checked**. Any unchecked task ⇒ rung 3 (`ws-resume`), not a PR.

## Two rungs agents get wrong — say the counter out loud

- **Tasks done + no PR ⇒ SHIP, don't spin.** 6/6 checked with no PR means **open the PR** in the unit's window. Do NOT `ws-resume` it again (the work is done), and do NOT `ws-start` the next unit yet — an un-opened PR is unshipped work.
- **A merged base ⇒ START the dependent, not restack it.** When a base PR merged and its dependents are **not yet created**, `ws-start` them. `ws-restack` is ONLY for a dependent that **already exists** and drifted. And when more than one unit shares a satisfied base, **list them all** (each its own window) — do not tunnel onto one.

## Red flags — you're about to answer wrong

- Recommending `ws-resume` on a unit that's 6/6 with no PR → **open the PR** instead.
- Recommending `ws-restack` for a dependent that isn't created yet → that's a `ws-start`.
- Naming one startable unit when two share a satisfied base → **list both**.

## Session model

Orchestration (`ws-init`, `ws-start`, `ws-restack`, `ws-next`, `ws-board`) runs in the **hub** (your launch session). Execution (`ws-resume`, opening the PR, coding) runs in the **unit's own window**. `ws-next` names both the command and where it belongs.

## Chain
After naming the command: hub command (`ws-start`/`ws-restack`) → offer to run it now (default yes), then run it. Unit-window command (`ws-resume` / open PR) → name the window; don't auto-run (SPEC Next-step chaining).
