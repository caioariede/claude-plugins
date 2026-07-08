# Workstreams — shared contract (`ws-*` skills)

Durable, cross-repo tracking for multi-unit work. **Worktrees are disposable code checkouts; all durable state lives in the store below.** This file is the single source for store layout, file formats, ids, status derivation, and restack — skills reference it, never restate it. Read it before any `ws-*` skill acts.

## Store layout (global — not per repo)
```
~/.claude/workstreams/<ws-id>/
  workstream.md          # metadata only
  units.md               # append-only roster (unit ↔ repo/branch identity map)
  backlog.md             # workstream future work: planned units + deferred follow-ups (mutable)
  units/<unit-id>/
    charter.md           # static: why this unit exists (unit-level workstream.md); set at ws-start, read by ws-resume
    progress.md          # MUTABLE current-state: Tasks + Follow-ups checklists (work-state SoT)
    log.md               # APPEND-ONLY: created, dropped, restack, decision, note
```

## Source of truth — never store what git/GitHub owns
| datum | source of truth | how |
|---|---|---|
| current branch | git (the worktree) | `git rev-parse --abbrev-ref HEAD` |
| base / did GitHub retarget | GitHub | `gh pr view --json baseRefName` |
| PR number + draft/ready/merged | GitHub | `gh pr view --json number,isDraft,state` |
| status | **derived — first match wins** | 1. `dropped` line in log → `dropped` · 2. PR merged → `merged` · 3. PR ready → `in-review` · 4. PR draft or no PR → `building` |
| unit ↔ repo/branch | `units.md` roster | set once at `ws-start` |
| unit purpose / scope (why it exists) | unit `charter.md` | set once at `ws-start`; read by `ws-resume` |
| tasks + in-flight follow-ups | unit `progress.md` | resolved before this unit's PR merges |
| deferred follow-ups + planned units | `backlog.md` | outlive the unit (see Follow-up placement) |
| decisions / notes / drop / restack history | `log.md` | append-only |

**Invariants:** log never stores current state; progress never stores history; `charter.md` is static intent (never volatile, never history); nothing volatile (branch/base/PR/status) is stored — derive it live. A planned unit shows as "not started" only until a roster slug matches it (dedup vs roster) — "not started" is not a derived unit *status*, it is a backlog item without a roster line yet.

## IDs & conventions
- **ws-id** = `<YYYY-MM-DD>-<slug(name)>` = the store dir name (`date -u +%Y-%m-%d`).
- **unit-id** = `slug(what)`; if `units/<slug>/` exists, append `-2`, `-3`… (old kept as history).
- **slug** = lowercase; non-alnum → `-`; collapse repeats; trim.
- **branch** = `feat-<unit-id>` unless the caller supplies one.
- **base** = the repo's default branch — `gh repo view --json defaultBranchRef -q .defaultBranchRef.name` — unless a base is supplied. A supplied base may be another unit-id → that unit's branch (stacking).
- **restart** = re-running `ws-start` with an intent whose slug already exists: the new unit takes the next `-N` suffix and records `restart-of=<original-unit-id>` on its roster line.
- **timestamps** = `date -u +%Y-%m-%dT%H:%MZ`.

## File formats
**`workstream.md`** (static; no log, no status):
```
---
id: <ws-id>
name: <name>
goal: <one line>
design: <optional path to umbrella spec>
created: <ts>
---
```
**`units.md`** (append-only roster; one line per `ws-start`, never edit prior lines):
```
# Units — <ws-id> (append-only)
- <ts>  <unit-id>  "<title>"  repo=<org/repo>  branch=<b>  [restart-of=<id>]  [stacked-on=<id>]
```
**`backlog.md`** (workstream future work; mutable):
```
## Planned units
- [ ] <slug>  base=<unit-id|branch>  — <what>
## Follow-ups
- [ ] WF<n>  <desc>  (from <unit-id>, <ts>)
```
Planned units feed `ws-next` (what to start) and `ws-board` (not-started); a line is derived-done once a roster unit matches its `<slug>` — no manual check-off. Follow-ups here are the workstream home for **deferred** items; check off when resolved or promoted to a planned unit / `ws-start`. `WF<n>` ids are monotonic per workstream.

**`units/<unit-id>/charter.md`** (static — the unit-level `workstream.md`; no log, no status, nothing volatile). Written once at `ws-start`, read by `ws-resume` to reconstruct the unit's intent with no chat scrollback:
```
---
design: <design spec path | —>
---
<purpose: what this unit ships, and that it builds on whatever the base branch
already provides — don't reimplement it. Specific deliverables are scoped at
plan time against the design; the charter is the north star, not the plan.>
```
Re-scope is a deliberate human edit here (rare) — like editing `workstream.md`'s goal — not churn.

**`units/<unit-id>/progress.md`** (mutable; checklists only — no branch/status/PR, those derive):
```
## Tasks
- [ ] T1  <desc>
## Follow-ups
- [ ] F1  <desc>
```
Task/follow-up ids (`T1`, `F1`) are monotonic per unit and never reused, even after check-off or removal.

**`units/<unit-id>/log.md`** (append-only): `- <ts>  <kind>  <payload>`
kinds: `created base=<b>` · `dropped <reason>` · `restack base=<new> was=<old>` · `decision <text>` · `note <text>`

**`ws-resume` is idempotent:** its actions are conditioned on the state it finds, and it appends a log line only on a *genuine* transition (plan / restack / decision / work note) — a no-op resume writes nothing. Never append a bare "resumed" line; the append-only log must not grow per invocation.

## Follow-up placement
When you note a follow-up, ask: will it be resolved before **this** unit's PR merges?
- **Yes** (you'll fix it in this unit before marking the PR ready) → unit `progress.md` `## Follow-ups` (`F<n>`).
- **No** (merge now, address later — it outlives this unit) → `backlog.md` `## Follow-ups` (`- [ ] WF<n>  <desc>  (from <unit-id>, <ts>)`).

A deferred item left in a unit that is about to merge becomes an orphaned checkbox in a dead unit nobody actions; in the backlog it stays visible and can graduate into a planned unit.

## Restack reconciliation (the one rebase definition)
A unit's **recorded base** = the base on its last `created`/`restack` log line (never the live PR `baseRefName`, which GitHub may have moved). To move a unit onto `<new-base>`:
```
OLD=$(git merge-base HEAD origin/<recorded-base>)
git fetch
git rebase --onto origin/<new-base> $OLD
```
Then append `restack base=<new-base> was=<recorded-base>` to `log.md`.

**Gate:** compare `gh pr view --json baseRefName` to the recorded base. If it is **unchanged** remotely, we are initiating — also run `gh pr edit <pr> --base <new-base>` first. If it has **already changed** (GitHub auto-retargeted when a base PR merged), skip the `gh pr edit`. Only `ws-restack` (explicit) and `ws-resume` (on detecting drift) reconcile; `ws-board` is read-only and never reconciles.

## Sessions — hub vs unit

Two roles, two places — this is where work actually runs:

- **Hub** = your launch session (in the main repo). **Orchestration only:** `ws-init`, `ws-start`, `ws-restack`, `ws-next`, `ws-board`, `ws-drop`. No code work here.
- **Unit window** = the tmux window `ws-start --focus` opened, cwd = that unit's worktree. **Execution:** `ws-resume`, opening the PR, coding.

After `ws-start` creates a unit, the work happens in its window — not the hub. `ws-resume` runs there. `ws-next` names both the command and which of the two to run it in.

## Next-step chaining
Every `ws-*` skill ends by naming the single best next command. **Same-session** (hub→hub): offer to run it now (default yes), then run it. **Cross-window** (hub→unit or unit→hub): name the command + its window — never auto-run. `ws-next` is the router; defer to it when the next step isn't singular.

## Worktree = code only
Never write store files into a worktree. Find a unit's worktree via the roster branch (+ wmx). Drop and recreate worktrees freely — progress survives in the store.
