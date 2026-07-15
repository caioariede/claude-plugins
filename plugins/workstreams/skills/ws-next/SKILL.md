---
name: ws-next
description: Use when unsure which ws-* command or which unit to act on next in a workstream — after finishing a unit, when a PR merges, or any "what now?" moment across units. Decides the next action; it does not do the work (that's ws-resume).
argument-hint: "[ws-id]"
metadata:
  version: "0.3.0"
  author: Caio Ariede
---

# ws-next — recommend the next workstream action

**Required first:** load the `ws` skill — the shared contract (SPEC). **Read-only** — it derives and recommends; it writes nothing.

## What it does

Reads the ledger (`units.md`) and each unit's **derived status** (SPEC status rules) and prints THE single next command and any units unblocked in parallel. It does not mutate the store — the command it names does.

## Decision table (first match wins)

| # | If | Then |
|---|----|------|
| 1 | a **created** unit's base PR merged / GitHub retargeted it, and its branch isn't rebased yet | `ws-restack <unit>` |
| 2 | a unit's tasks are **all checked** but it has **no PR** | `ws-resume <unit>` — it ships a done unit (opens the PR) |
| 3 | a unit is **in progress** (unchecked tasks) | `ws-resume <unit>` |
| 4 | a **backlog** planned unit whose base is **merged/`main`** and it's **not yet on the ledger** | `ws-start <ws> "<what>" --base <dep>` |
| 5 | no **active** unit, **but** `backlog.md` has open items — a planned unit rule 4 couldn't start, or an open `WF<n>`/`F<n>` follow-up | **not done — triage:** `ws-start` a worth-doing item, or check off / discard the rest in `backlog.md` / the unit's `progress.md`. **List the open items.** |
| 6 | no **active** unit **and** no open backlog item (SPEC "Workstream done") | workstream done — close it |

Rule 4's planned units live in `backlog.md` `## Planned units`. Rule 5 is where a **deferred follow-up** (`WF<n>`) or an unstarted planned unit gets resolved: promote a worth-doing one to a unit (`ws-start`, then check it off in `backlog.md`), or discard the rest. Rule 6 fires only once nothing open remains — "active" is the SPEC term (`building`/`in-review`), reused here, not re-listed.

## Emitting the command

Walk the rules first; write the `Next:` line **last** — never lead with a guess you then reason away. The emitted line must be the winning rule's command, verbatim.

```
Next: <one resolved command>   (unit: <slug>)   ← name the unit when the command is unit-scoped
Also unblocked (parallel): <unit>, <unit>       ← only when rule 4 has >1 qualifying unit
```

Emit exactly **one** clean, executable line:
- every argument a **literal** — no `<ws>` / `<unit>` / `<base>` placeholders left in;
- no retracted or false-start lines, no "wait"/"hold on" in the final answer; if you revise mid-reasoning, re-emit the whole command cleanly from the final decision;
- `ws-start <ws-id> "<what>" [--base <unit-id|branch>]` — the **first positional is the workstream id**, the unit is slugged from the quoted `"<what>"`, and `--base` is a merged dependency's unit-id or branch. Never put a unit name in the first slot.

Rule 2 fires **only** when a unit has **no PR AND every task checked** — emit `ws-resume <unit>`, which ships a done unit. Any unchecked task ⇒ rule 3, also `ws-resume <unit>` — the verb is idempotent, so state decides ship vs. continue. `ws-next` never opens the PR itself; it names the verb that does.

## Rules agents get wrong — say the counter out loud

- **Tasks done + no PR ⇒ SHIP, don't spin.** 6/6 checked with no PR ⇒ `ws-resume <unit>` — it ships a done unit (opens the PR). Do NOT `ws-start` the next unit yet — an un-opened PR is unshipped work.
- **A merged base ⇒ START the dependent, not restack it.** When a base PR merged and its dependents are **not yet created**, `ws-start` them. `ws-restack` is ONLY for a dependent that **already exists** and drifted. And when more than one unit shares a satisfied base, **list them all** — do not tunnel onto one.
- **All units merged ≠ workstream done.** A merged stack with open backlog still has real remaining work — unstarted planned units, deferred follow-ups. Closing the workstream strands it. Merged units clear the *unit* side; `backlog.md` is the other half of the gate — both must be clear (rule 6), else it's rule 5 (triage).

## Red flags — you're about to answer wrong

- Emitting a raw PR-open command or methodology skill (whatever the active flavors resolve to) for a 6/6-no-PR unit → name `ws-resume <unit>` instead; the router emits `ws-*` verbs only.
- Recommending `ws-restack` for a dependent that isn't created yet → that's a `ws-start`.
- Naming one startable unit when two share a satisfied base → **list both**.
- Emitting "workstream done — close it" while `backlog.md` has open items → that's rule 5 (triage the backlog), not rule 6.

## Scope

Every command here runs from any session (SPEC "Command scope"). Unit-scoped
commands (`ws-resume`, `ws-restack`) self-locate their worktree; the rest touch
only the store + GitHub. Name the unit for a unit-scoped recommendation so a
parallel-session user knows which one — never mandate a place to run it.

## Chain
After naming the command, offer to run it now (default yes), then run it — it works from the current session. Mention the unit for a unit-scoped command (SPEC Next-step chaining).
