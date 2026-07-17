---
name: ws
description: The shared contract (SPEC) for all ws-* workstream skills — store layout, file formats, IDs, status derivation, restack, and flavors. REQUIRED reading before any ws-* skill acts; every ws-* skill loads this first. Also use when asked how workstreams work, where workstream state lives, or when debugging the workstream store.
metadata:
  version: "0.7.0"
  author: Caio Ariede
---

# Workstreams — shared contract (`ws-*` skills)

Durable, cross-repo tracking for multi-unit work. **Worktrees are disposable code checkouts; all durable state lives in the store below.** This contract is the single source for store layout, file formats, ids, status derivation, and restack — skills reference it, never restate it. Read it before any `ws-*` skill acts.

## Store layout (global — not per repo)
**Store root** `<store>` = `$XDG_DATA_HOME/workstreams`; when `XDG_DATA_HOME` is unset (typical), `~/.local/share/workstreams`.
```
<store>/<ws-id>/
  workstream.md          # metadata only
  units.md               # append-only ledger (unit ↔ repo/branch identity map)
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
| base / did GitHub retarget | GitHub | active `forge` flavor `pr-status` (SPEC §Flavors) |
| PR number + draft/ready/merged | GitHub | active `forge` flavor `pr-status` |
| status | **derived — first match wins** | 1. `dropped` line in log → `dropped` · 2. PR merged → `merged` · 3. has an unmet need (§Dependencies) → `blocked` · 4. PR ready → `in-review` · 5. PR draft or no PR → `building` |
| unit ↔ repo/branch | `units.md` ledger | set once at `ws-start` |
| unit purpose / scope (why it exists) | unit `charter.md` | set once at `ws-start`; read by `ws-resume` |
| tasks + in-flight follow-ups | unit `progress.md` | resolved before this unit's PR merges |
| explicit needs (dependencies) | unit `progress.md` `## Needs` (+ base from ledger) | current set is mutable state; base is the implicit need (§Dependencies) |
| deferred follow-ups + planned units | `backlog.md` | written via `ws-backlog`; outlive the unit (see Follow-up placement) |
| decisions / notes / drop / restack history | `log.md` | append-only |

**Invariants:** log never stores current state; progress never stores history; `charter.md` is static intent (never volatile, never history); nothing volatile (branch/base/PR/status) is stored — derive it live. A planned unit shows as "not started" only until a ledger slug matches it (dedup vs ledger) — "not started" is not a derived unit *status*, it is a backlog item without a ledger line yet.

**Workstream done** (derived — single source; `ws-next` and `ws-board` reference this, never restate it): no unit is **active** (active = derived status `building`, `blocked`, or `in-review`) — every ledger unit is terminal (`merged` or `dropped`) — **and** `backlog.md` carries no open work: no `## Planned units` line without a matching ledger unit, no unchecked `## Follow-ups` (`WF<n>`), and no unit `progress.md` with an unchecked in-flight `F<n>`. Any open item ⇒ **not done**. Dropped units are terminal, not blockers.

## Dependencies (needs / blocked)
A unit's **needs** = `{ base, when base is a unit-id }` ∪ `{ explicit needs }`. base is the **implicit** need — `ws-start --base <unit-id>` declares the dependency; explicit needs are added later via `ws-block`.

**Need target** — each need points at either:
- a **unit** (`<unit-id>` or bare slug) — **satisfied** when that unit is *code-complete*.
- a **follow-up** (`<unit-id>:F<n>` or `WF<n>`) — **satisfied** when that box is checked in its source file.

**code-complete** (derived predicate; never a printed status label): a unit has ≥1 task in `progress.md` `## Tasks` **and** every `## Tasks` box is checked. `## Follow-ups` are ignored; zero tasks is *not* code-complete. `merged` implies code-complete.

**blocked** (derived status): a unit has ≥1 need whose target is not satisfied. A **dropped** target is never code-complete → the dependent is stuck: flag it `(dropped)` and route to triage, never auto-resolve. A follow-up target that is *removed* (deleted, not checked) is likewise unresolvable → same triage.

**Derivation is cross-unit.** Unlike git/PR/log-derived facts, `blocked` reads *other* units' code-complete and status, so status resolution **walks the need graph**. `ws-block` refuses to create a cycle, but a hand-edited store could still hold one — every graph walk carries a **visited-set** and never recurses blindly.

Merge ordering (a stacked unit cannot merge before its base) stays owned by git/GitHub + restack — `blocked` means "cannot proceed with work," satisfied at code-complete, distinct from the merge gate.

## IDs & conventions
- **ws-id** = `<YYYY-MM-DD>-<slug(name)>` = the store dir name (`date -u +%Y-%m-%d`).
- **unit-id** = `<ws-id>:<slug(what)>` — globally unique by construction. On disk
  the unit lives at `<store>/<ws-id>/units/<slug>/`; the `<ws-id>:`
  prefix is the typed, global handle.
- **bare-slug resolver** — any command taking a unit accepts a bare `<slug>` and
  resolves it by scanning `<store>/*/units.md`: exactly one match →
  use it; more than one → list the matches and require the `<ws-id>:` prefix; none
  → error. Skills reference this rule; never restate it.
- **slug** = lowercase; non-alnum → `-`; collapse repeats; trim.
- **branch** = `<slug>` unless the caller supplies one. Git refnames disallow
  `:`, so the branch is not the canonical id. If `<slug>` already exists in the
  target repo (local or remote) — including when the slug matches the base
  branch — disambiguate with `-N`, a repo-scoped git check separate from
  unit-id uniqueness.
- **base** = the repo's default branch — the active `forge` flavor's `default-branch` (SPEC §Flavors) — unless a base is supplied. A supplied base may be a unit-id → that unit's branch (stacking).
- **repo** (`ws-start`) = resolved by precedence: (1) explicit `--repo org/repo`;
  (2) if `--base` is a unit-id, that unit's repo (stacking requires the same repo);
  (3) else the git repo `ws-start` runs in (cwd). Error only when an explicit
  `--repo` contradicts a `--base` unit's repo.
- **restart** = re-running `ws-start` with an intent whose slug already exists in
  the same workstream: the new unit takes the next `-N` slug suffix (`<slug>-2`)
  and records `restart-of=<slug>` on its ledger line. `-N` means restart only —
  reused slugs in different workstreams do not collide, because the `<ws-id>`
  namespace separates them.
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
**`units.md`** (append-only ledger; one line per `ws-start`, never edit prior lines).
The line's own id is the bare `<slug>` (canonical id = `<this-ws-id>:<slug>`).
`restart-of` is always same-workstream → bare `<slug>`. `stacked-on` uses the
canonical `<ws-id>:<slug>` when the base is in another workstream, bare `<slug>`
when the base is in this one:
```
# Units — <ws-id> (append-only)
- <ts>  <slug>  "<title>"  repo=<org/repo>  branch=<b>  [restart-of=<slug>]  [stacked-on=<ws-id>:<slug> | <slug>]
```
**`backlog.md`** (workstream future work; mutable):
```
## Planned units
- [ ] <slug>  base=<unit-id|branch>  [needs=<target>[,<target>]]  — <what>
## Follow-ups
- [ ] WF<n>  <desc>  (from <unit-id|ws-id>, <ts>)
```
Planned units feed `ws-next` (what to start) and `ws-board` (not-started); a line is derived-done once a ledger unit matches its `<slug>` — no manual check-off. Follow-ups here are the workstream home for **deferred** items; check off when resolved or promoted to a planned unit / `ws-start`. `WF<n>` ids are monotonic per workstream; the origin is the capturing unit-id, or the `<ws-id>` when captured outside any unit (`ws-backlog`). `needs=` carries dependencies **beyond** base (bare targets, no notes); `ws-start` seeds them into the started unit's `progress.md` `## Needs` (§Dependencies).

**Parse contract (machine-read).** `ws-board` (later `ws-next`) parse the store deterministically via `scripts/ws_store.py`, bundled with this skill, so these formats are a machine contract — keep fields structured. Parsing is deliberately tolerant. In `backlog.md` only `## Planned units` and `## Follow-ups` are read, by exact heading; any other `##` section (e.g. a stray `## Not tracked here`) is ignored wholesale. Within a read section an item is a single-line `- [ ]`/`- [x]` bullet; comments, single-`#` sub-headers, and blank lines are skipped, so humans keep them freely. A planned line keeps its structured fields (`base=`, `needs=`) **before** the ` — ` separator; everything after is opaque display text and never carries them. A follow-up's origin is the `(from <origin>, <ts>)` parenthetical, found by the `(from ` marker — the description itself may contain parens — and any resolution text trailing it (`→ done in X`) is ignored. In `log.md`, `dropped` is the line **kind** (the token after the timestamp), distinct from the word appearing inside a `decision`/`note` payload.

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

**`units/<unit-id>/progress.md`** (mutable current-state — no branch/status/PR, those derive):
```
## Tasks
- [ ] T1  <desc>
## Follow-ups
- [ ] F1  <desc>
## Needs
- N1  <target>   — <note>
```
`T<n>`/`F<n>`/`N<n>` ids are monotonic per unit and never reused, even after check-off or removal. `## Needs` lines have **no checkbox** — a need's satisfied/open state is *derived* from its target (§Dependencies), never hand-marked; remove a line only on a genuine scope change (append a `decision` to `log.md`). `<target>` = a unit-id/bare-slug or a follow-up id (`<unit-id>:F<n>` / `WF<n>`); the note is optional free text.

**`units/<unit-id>/log.md`** (append-only): `- <ts>  <kind>  <payload>`
kinds: `created base=<b>` · `dropped <reason>` · `restack base=<new> was=<old>` · `decision <text>` · `note <text>`

**`ws-resume` is idempotent:** its actions are conditioned on the state it finds, and it appends a log line only on a *genuine* transition (plan / restack / decision / work note) — a no-op resume writes nothing. Never append a bare "resumed" line; the append-only log must not grow per invocation.

## Follow-up placement
When you note a follow-up, ask: will it be resolved before **this** unit's PR merges?
- **Yes** (you'll fix it in this unit before marking the PR ready) → unit `progress.md` `## Follow-ups` (`F<n>`).
- **No** (merge now, address later — it outlives this unit) → `backlog.md` `## Follow-ups` (`- [ ] WF<n>  <desc>  (from <unit-id|ws-id>, <ts>)`).

A deferred item left in a unit that is about to merge becomes an orphaned checkbox in a dead unit nobody actions; in the backlog it stays visible and can graduate into a planned unit.

`ws-backlog` is the standalone capture verb for both placements from any session; `ws-resume` records them inline while working the unit — both write the same shapes.

## Restack reconciliation (the one rebase definition)
A unit's **recorded base** = the base on its last `created`/`restack` log line (never the live PR `baseRefName`, which GitHub may have moved). To move a unit onto `<new-base>`:
```
OLD=$(git merge-base HEAD origin/<recorded-base>)
git fetch
git rebase --onto origin/<new-base> $OLD
```
Then append `restack base=<new-base> was=<recorded-base>` to `log.md`.

**Gate:** compare the active `forge` flavor's `pr-status` base to the recorded base. If it is **unchanged** remotely, we are initiating — also run the `forge` flavor's `pr-retarget` first. If it has **already changed** (GitHub auto-retargeted when a base PR merged), skip the `pr-retarget`. Only `ws-restack` (explicit) and `ws-resume` (on detecting drift) reconcile; `ws-board` is read-only and never reconciles.

## Command scope

Every `ws-*` command runs from **any session** and self-locates — the workflow
reads identically whether you use one session or many. This contract defines no
central "hub" and never says "run this here, that there." A dedicated
orchestration terminal is your own convention to name, not a role defined here.

- **Workstream-scoped** — touches only the global store + GitHub (`ws-init`,
  `ws-start`, `ws-next`, `ws-board`, `ws-drop`, `ws-block`). Runs from anywhere.
- **Unit-scoped** — git operations on one unit's branch, so it resolves that
  unit's worktree first (`ws-resume`, `ws-restack`). `ws-resume` `cd`s into the
  worktree in the current session (already inside → continue); `ws-restack`
  operates via `git -C <worktree>`. A per-unit multiplexer window is optional
  ergonomics for parallel work, never required.

## Next-step chaining
Every `ws-*` skill ends by naming the single best next command and **offering to
run it now (default yes)**. A skill may delegate this offer to a flavor hook
(§Flavor hooks) — when an active flavor defines it, the hook's prompt replaces
the default offer, and the chosen instruction is all that runs. What the choices
offer is the flavor's business; the skill only distinguishes outcomes: a choice
resolving to `<command>` runs the command in this session; any other choice is
the flavor handing the work off its own way — run it, re-emit the command, and
stop. No flavor defines the hook → the default offer above. The skill may
*mention* the relevant unit so a parallel-session user knows where they would
go — informational, not a precondition to running. `ws-next` is the router;
defer to it when the next step isn't singular.

## Worktree = code only
Never write store files into a worktree. Find a unit's worktree via the ledger branch, using the active `worktree-management` flavor's `locate` (SPEC §Flavors). Drop and recreate worktrees freely — progress survives in the store.

## Flavors
External tools are pluggable via **flavors** — skills never hardwire wmx / superpowers / gh. A **group** is a fixed behavior category (defined by the skills); a **flavor** is one implementation; an **operation** is a named slot a flavor fills with a one-line instruction (a shell command, or a `skill:id` to invoke). Exactly one flavor per group is **active** (global). Skills resolve an operation at each coupling point and follow it — read here, never restated in skills. A flavor swaps only mechanism/methodology; ws bookkeeping (progress/log/ledger/PR-ready) is intrinsic and stays in the skills.

**Groups & operations**
- `worktree-management` — `create` (worktree+branch `<branch>` off `<base>`) · `remove` (`<branch>`) · `locate` (worktree path for `<branch>`).
- `spec-driven-development` — `plan` (charter+design → `T1..`) · `execute` (first unchecked task) · `ship` (open the PR).
- `forge` — `default-branch` · `pr-status` (number+draft/ready/merged+base for `<branch>`) · `pr-create` (`<branch>`→`<base>`) · `pr-ready` (`<pr>`) · `pr-retarget` (`<pr>`→`<new-base>`).

**Files (INI), merged low→high precedence**
1. built-in — `references/flavors.ini`, bundled with this `ws` skill
2. store — `<store>/flavors.ini` (`[config]`, `[active]`, custom sections)
3. overrides — path from store `[config] overrides-file=<path>` (optional)

`[active]` maps `group = flavor`; `[group/flavor]` maps `operation = instruction`.

**Resolution** (group `G`, operation `O`)
1. active flavor = merged `[active] G` → else default (`git-worktree` / `none` / `gh`).
2. instruction = `[G/<flavor>] O` merged **per key** across layers (overrides > store > built-in).
3. missing after merge → the group **default flavor's** `O`; an optional op no layer defines → skip.
4. `word:word` → invoke as a skill; a `ws-*` command line (e.g. `ws-resume <unit>`) → invoke that skill with those arguments; else run as shell. Fill `<branch> <base> <path> <repo> <pr> <new-base>` from context; hook instructions and their `.prompt`/`.choices` may also use `<unit>` (the target unit id) and `<command>` (the firing skill's resolved next command).

**Flavor hooks** — a flavor may react at a skill's lifecycle point. A **hook** is an optional operation named `hook-<skill>-<event>` (e.g. `hook-ws-start-after`); each skill documents the events it fires. At an event, and **only in an interactive session** (never a subagent/headless run), the skill fires that hook from every **active** flavor — across all groups, in group order (`worktree-management`, `spec-driven-development`, `forge`) — that defines it. Companion keys, valid only on `hook-*` operations: `<hook>.prompt` (a question; its presence makes the hook interactive) · `<hook>.choices.<name>` (an option's instruction; empty = skip) · `<hook>.choices.<name>.desc` (its picker description — label is `<name>`). **Modes:** no `.prompt` → run the base instruction unconditionally · `.prompt` without `.choices` → binary (Yes runs the base instruction, No skips) · `.prompt` with `.choices` → present the 2–4 options and run the chosen one (base ignored). A dismissed prompt skips. Base and `.choices` values resolve as any instruction (rule 4). `hook-`, `.prompt` and `.choices.` are reserved on operation keys, and an option `<name>` may not be `prompt`.

`overrides-file` set but unreadable → warn, skip that layer. `gh` is the assumed baseline — there is no git-only forge; a non-GitHub user adds a custom forge flavor via the overrides file. Configure with `/ws-config`.
