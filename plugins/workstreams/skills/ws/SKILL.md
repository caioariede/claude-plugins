---
name: ws
description: The shared contract (SPEC) for all ws-* workstream skills — store layout, file formats, IDs, status derivation, restack, and flavors. REQUIRED reading before any ws-* skill acts; every ws-* skill loads this first. Also use when asked how workstreams work, where workstream state lives, or when debugging the workstream store.
metadata:
  version: "0.24.1"
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
  spikes.md              # append-only ledger (spike identity — no branch=)
  backlog.md             # workstream future work: planned units + deferred follow-ups (mutable)
  focus.md               # outcome queue: one active focus steers ws-next proposals (mutable)
  units/<unit-id>/
    charter.md           # static: why this unit exists (unit-level workstream.md); set at ws-start, read by ws-resume
    progress.md          # MUTABLE current-state: Tasks + Follow-ups checklists (work-state SoT)
    log.md               # APPEND-ONLY: created, dropped, restack, decision, note, merged-via
    prewalk.md           # optional: exploration digest (superpowers-prewalk)
    critic.md            # optional: post-complete review (review/ws-critic)
  spikes/<slug>/
    charter.md           # static: what to investigate; set at ws-spike, read by ws-resume
    progress.md          # MUTABLE: Tasks + Needs only (no Follow-ups)
    log.md               # APPEND-ONLY: created, dropped, decision, note, plan
    artifacts/           # working drafts; spec-before snapshots live here too
```

## Source of truth — never store what git/GitHub owns
| datum | source of truth | how |
|---|---|---|
| current branch | git (the worktree) | `git rev-parse --abbrev-ref HEAD` |
| base / did GitHub retarget | GitHub | active `forge` flavor `pr-status` (SPEC §Flavors) |
| PR number + draft/ready/merged | GitHub | active `forge` flavor `pr-status` |
| status | **derived — first match wins** | 1. `dropped` line in log → `dropped` · 2. `merged-via` log or PR merged → `merged` · 3. has an unmet need (§Dependencies) → `blocked` · 4. PR ready → `in-review` · 5. PR draft or no PR → `building` |
| unit ↔ repo/branch | `units.md` ledger | set once at `ws-start` |
| unit purpose / scope (why it exists) | unit `charter.md` | set once at `ws-start`; read by `ws-resume` |
| tasks + in-flight follow-ups | unit `progress.md` | resolved before this unit's PR merges |
| explicit needs (dependencies) | unit `progress.md` `## Needs` (+ base from ledger) | current set is mutable state; base is the implicit need (§Dependencies) |
| deferred follow-ups + planned units | `backlog.md` | written via `ws-backlog`; outlive the unit (see Follow-up placement) |
| focus queue + active outcome | `focus.md` | written via `ws-focus`; open items in insertion order; active = sole `[>]` line among non-done items |
| is a follow-up claimed (being closed by a unit) | **derived** | a non-dropped ledger unit's `claims=` names it (§Follow-up units) |
| decisions / notes / drop / restack history | `log.md` | append-only |

**Invariants:** log never stores current state; progress never stores history; `charter.md` is static intent (never volatile, never history); nothing volatile (branch/base/PR/status) is stored — derive it live. A planned unit shows as "not started" only until a ledger slug matches it (dedup vs ledger) — "not started" is not a derived unit *status*, it is a backlog item without a ledger line yet.

**`ws-start` is the sole creator of `units/<unit-id>/`.** No other skill and no ad-hoc write creates a unit directory or any file in it — not while seeding a backlog, not while capturing a follow-up, not to "get ahead" of a unit that is about to exist. A unit directory with no matching `units.md` ledger line is malformed. Anything that wants a unit runs `ws-start`; anything that wants to *record* a future unit writes `backlog.md` via `ws-backlog`.

**`ws-spike` is the sole creator of `spikes/<slug>/`.** Same store-only rule — no worktree, no branch. A spike directory with no matching `spikes.md` ledger line is malformed.

**Workstream done** (derived — single source; `ws-next` and `ws-board` reference this, never restate it): no unit is **active** (active = derived status `building`, `blocked`, or `in-review`) — every ledger unit is terminal (`merged` or `dropped`) — **and** no spike is **active** (`researching` or `blocked`) — every ledger spike is terminal (`complete` or `dropped`) — **and** `backlog.md` carries no open work: no `## Planned units` line without a matching ledger unit, no unchecked `## Follow-ups` (`WF<n>`), and no unit `progress.md` with an unchecked in-flight `F<n>` — an unchecked follow-up a live unit **claims** is that unit's work, not an open item (§Follow-up units). Any open item ⇒ **not done**. Dropped units and dropped spikes are terminal, not blockers.

This predicate reads the store only, so it cannot know whether the `design:` spec still holds unbuilt scope. A workstream can therefore be **done** here while `ws-next` still proposes a unit from the design — the judgment layers on top of the derived answer rather than contradicting it, which is why `ws-next` says "no store work left" instead of claiming done.

## Dependencies (needs / blocked)
A unit's **needs** = `{ base, when base is a unit-id }` ∪ `{ explicit needs }`. base is the **implicit** need — `ws-start --base <unit-id>` declares the dependency; explicit needs are added later via `ws-block`.

**Need target** — each need points at either:
- a **unit** (`<unit-id>` or bare slug) — **satisfied** when that unit is *code-complete*.
- a **spike** (bare slug in `spikes.md`) — **satisfied** when that spike is *spike-complete*.
- a **follow-up** (`<unit-id>:F<n>` or `WF<n>`) — when a live unit **claims** it (§Follow-up units), satisfied through that unit exactly as a unit target; otherwise **satisfied** when the box is checked in its source file.

**code-complete** (derived predicate; never a printed status label): a unit has ≥1 task in `progress.md` `## Tasks` **and** every `## Tasks` box is checked. `## Follow-ups` are ignored; zero tasks is *not* code-complete. `merged` implies code-complete.

**spike-complete** (derived predicate; never a printed status label): a spike has ≥1 task in `progress.md` `## Tasks` **and** every `## Tasks` box is checked. Zero tasks is *not* spike-complete. Used for need satisfaction and terminal `complete` status — a spike-complete spike with unmet needs is still **blocked**, not Done.

**Merge task reconcile:** when a unit is terminal-merged (`merged-via`
log or forge `MERGED` on the ledger branch), open `## Tasks` boxes are
invalid bookkeeping — `ws-resume` checks them and appends a `decision
reconciled tasks from merged-via branch=<b> pr=<n>: …` or `reconciled
tasks from merged PR #<n>: …` line to `log.md`. `## Follow-ups` are
never auto-checked. `ws-board` does not write; `ws-next` scans live
units read-only for shipped-elsewhere evidence and classifies an
in-memory overlay but never appends log lines or mutates
`progress.md`. `ws-resume` writes `merged-via`, task reconcile, and
`ship-detect-dismissed`. Both derive `merged` / code-complete from the
log and live PR state.
`phase.py` gathers PR state for every ledger unit (same as board/next).

**blocked** (derived status): a unit has ≥1 need whose target is not satisfied. A **dropped** target is never code-complete → the dependent is stuck: flag it `(dropped)` and route to triage, never auto-resolve. A follow-up target that is *removed* (deleted, not checked) is likewise unresolvable → same triage.

**Derivation is cross-unit.** Unlike git/PR/log-derived facts, `blocked` reads *other* units' code-complete and status, so status resolution **walks the need graph**. `ws-block` refuses to create a cycle, but a hand-edited store could still hold one — every graph walk carries a **visited-set** and never recurses blindly.

Merge ordering (a stacked unit cannot merge before its base) stays owned by git/GitHub + restack — `blocked` means "cannot proceed with work," satisfied at code-complete, distinct from the merge gate.

## IDs & conventions
- **ws-id** = `<YYYY-MM-DD>-<slug(name)>` = the store dir name (`date -u +%Y-%m-%d`).
- **unit-id** = `<ws-id>:<slug(what)>` — globally unique by construction. On disk
  the unit lives at `<store>/<ws-id>/units/<slug>/`; the `<ws-id>:`
  prefix is the typed, global handle.
- **bare-slug resolver** — any command taking a unit or spike accepts a bare `<slug>` and
  resolves it by scanning `<store>/*/units.md` and `spikes.md`: exactly one match →
  use it (with `kind` = unit or spike); more than one → list the matches with kind
  and require the `<ws-id>:` prefix; none → error. Skills reference this rule; never restate it.
- **slug** = lowercase; non-alnum → `-`; collapse repeats; trim. Then **shorten**:
  drop filler words (`a an and the this that so it its of to for from in into on
  with when then just at as by but or i we you my our your be is are was were
  can will would should`), keep at most the first 4 remaining words, then hard-cap
  32 chars by cutting at a `-` boundary — never mid-word. If dropping filler
  leaves nothing, keep the unfiltered words. Prefer a `<verb>-<object>` shape.
  The rule is fixed so every caller derives the same slug from the same text —
  a `backlog.md` planned line and the ledger line that later matches it must
  agree. Shortening loses nothing: the intent survives verbatim in the ledger
  `"<title>"` and in `charter.md`. A `-N` suffix is appended after the cap.
- **branch** = `<slug>` unless the caller supplies one (`ws-start --slug`, which
  is sanitized but not shortened). Git refnames disallow
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
- <ts>  <slug>  "<title>"  repo=<org/repo>  branch=<b>  [restart-of=<slug>]  [stacked-on=<ws-id>:<slug> | <slug>]  [claims=<target>[,<target>]]
```
`<title>` = the `<what>` verbatim — the unshortened intent, so a short `<slug>` costs nothing.
`claims=` lists the follow-up targets this unit was created to close (§Follow-up units); each target is a `WF<n>` or `<unit-id>:F<n>` per §Dependencies.
**`spikes.md`** (append-only ledger; one line per `ws-spike`, never edit prior lines):
```
# Spikes — <ws-id> (append-only)
- <ts>  <slug>  "<title>"  repo=<org/repo>  [spawned-from=<unit-id>]  [restart-of=<slug>]
```
`repo=` is a read-only exploration anchor — no `branch=`. Explicit needs live in spike `progress.md` `## Needs` only.
**`backlog.md`** (workstream future work; mutable):
```
## Planned units
- [ ] <slug>  base=<unit-id|branch>  [needs=<target>[,<target>]]  — <what>
## Follow-ups
- [ ] WF<n>  <desc>  (from <unit-id|ws-id>, <ts>)
```
Planned units are **dependency reservations** — they record `base=`/`needs=` for a future unit but do not route `ws-next` (proposals come from focus + design); `ws-board` still shows not-started lines. A line is derived-done once a ledger unit matches its `<slug>` — no manual check-off. Follow-ups here are the workstream home for **deferred** items; check off when resolved or promoted to a planned unit / `ws-start`. `WF<n>` ids are monotonic per workstream; the origin is the capturing unit-id, or the `<ws-id>` when captured outside any unit (`ws-backlog`). `needs=` carries dependencies **beyond** base (bare targets, no notes); `ws-start` seeds them into the started unit's `progress.md` `## Needs` (§Dependencies).

**`focus.md`** (outcome queue; mutable; missing or empty = no focus steering):
```
## Focus
- [>] <slug>  — <outcome>
- [ ] <slug>  — <outcome>
- [x] <slug>  — <outcome>
```
`[ ]` queued · `[>]` active (at most one among non-done lines) · `[x]` done (history, last three kept). Line order under `## Focus` is authoritative — open items keep insertion order unless `ws-focus move` changes it; active is not hoisted on write. `<slug>` = `slug(<outcome>)` per SPEC ids; text after ` — ` is opaque intent — no structured fields. Focus is steering, not execution — no ledger slug, no branch, no PR. **Workstream done** (above) is unchanged.

**Parse contract (machine-read).** `ws-board` and `ws-next` parse the store deterministically via `scripts/ws_store.py`, bundled with this skill, and `ws-config` drives the flavors INI through the same bundled engine (`scripts/ws_cli.py` plus its own `config.py`), so these formats are a machine contract — keep fields structured. Parsing is deliberately tolerant. In `backlog.md` only `## Planned units` and `## Follow-ups` are read, by exact heading; any other `##` section (e.g. a stray `## Not tracked here`) is ignored wholesale. In `focus.md` only `## Focus` is read, by exact heading; items use `- [ ]`/`- [>]`/`- [x]` with the same comment/blank-line tolerance as `backlog.md`. Within a read section an item is a single-line `- [ ]`/`- [x]` bullet; comments, single-`#` sub-headers, and blank lines are skipped, so humans keep them freely. A planned line keeps its structured fields (`base=`, `needs=`) **before** the ` — ` separator; everything after is opaque display text and never carries them. A follow-up's origin is the `(from <origin>, <ts>)` parenthetical, found by the `(from ` marker — the description itself may contain parens — and any resolution text trailing it (`→ done in X`) is ignored. In `log.md`, `dropped` is the line **kind** (the token after the timestamp), distinct from the word appearing inside a `decision`/`note` payload. A ledger line's `key=value` tokens are read by name and unknown keys are ignored, so a new field is additive. `workstream.md`'s `design:` is parsed (an em-dash placeholder reads as absent); `charter.md` is not — it is prose for `ws-resume`, never a machine input.

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

**`spikes/<slug>/charter.md`** (static — spike intent; no log, no status):
```
---
design: <design spec path | —>
spawned-from: <unit-id | —>
---
<purpose: what to investigate, verbatim from ws-spike input>
```

**`spikes/<slug>/progress.md`** (mutable current-state — Tasks + Needs only):
```
## Tasks
- [ ] T1  <desc>
## Needs
- N1  <target>   — <note>
```
No `## Follow-ups` — deferred discoveries go to `backlog.md` via `ws-backlog`.

**`spikes/<slug>/log.md`** (append-only): `- <ts>  <kind>  <payload>`
kinds: `created` · `dropped <reason>` · `decision <text>` · `note <text>` · `plan <absolute-path>`
No `merged-via`, `restack`, or `completed` kind — terminal spike = derived `complete`.
`decision spec-amended <summary>` records the umbrella design amend.

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
kinds: `created base=<b>` · `dropped <reason>` · `restack base=<new> was=<old>` · `decision <text>` · `note <text>` · `plan <absolute-path>` · `merged-via branch=<b> sha=<full> [pr=<n>]` · `ship-detect-dismissed sha=<full>`

`merged-via` records where the unit's work shipped when the ledger
`branch=` is not forge-MERGED (another branch, replaced PR, or manual
squash-gap fix). Latest line wins; append-only.

`plan` records the unit implementation plan path (superpowers flavor);
append once at first save. `decision plan=done plan=<abs-path> digest=<8-hex> [reason=<reason>]`
records the confirmed task derivation receipt. Written atomically by `confirm_plan.py`
when deriving `T1..` into `progress.md`. `decision context <group>=<value>`
(e.g. `context spec-driven-development=subagent|inline`) records flavor-owned
resume metadata.

**Flavors contract:** Any plan-producing `spec-driven-development` flavor must
define `hook-ws-resume-plan-pause` or extend `superpowers`.

**Task derivation (superpowers):** one `## Tasks` line per `### Task N:`
heading in the unit plan file — `- [ ] T<n>  <Task N title>`,
monotonic `T1..`. Last task owns verification (ws-resume plan convention).
Derive at plan-pause confirmation via `confirm_plan.py`, not at plan save.

**Plan path (superpowers):** resolve via `resolve_plan_path(design,
slug)` in `ws_store.py` — `<design-dir>/<bare-slug>-plan.md` where
`design-dir` is the directory of charter `design:` (tilde-expanded).
Slug must exist (`ws-start` before `writing-plans`). No
`-design.md` → `-plan.md` swap. Headless runs inline this rule when
hooks skip.

**Plan path migration:** units with a `plan` log line pointing at a
design-basename `-plan.md` — delete that line and re-run `ws-resume`.
Each unit gets its own `<slug>-plan.md` on next plan.

**`ws-resume` is idempotent:** its actions are conditioned on the state it finds, and it appends a log line only on a *genuine* transition (plan / restack / decision / work note) — a no-op resume writes nothing. Never append a bare "resumed" line; the append-only log must not grow per invocation.

## Follow-up placement
When you note a follow-up, ask: will it be resolved before **this** unit's PR merges?
- **Yes** (you'll fix it in this unit before marking the PR ready) → unit `progress.md` `## Follow-ups` (`F<n>`).
- **No** (merge now, address later — it outlives this unit) → `backlog.md` `## Follow-ups` (`- [ ] WF<n>  <desc>  (from <unit-id|ws-id>, <ts>)`).

A deferred item left in a unit that is about to merge becomes an orphaned checkbox in a dead unit nobody actions; in the backlog it stays visible and can graduate into a planned unit.

`ws-backlog` is the standalone capture verb for both placements from any session; `ws-resume` records them inline while working the unit — both write the same shapes.

## Follow-up units
A **follow-up unit** exists to close a batch of already-captured follow-ups rather than to build new scope. It is an ordinary unit — `ws-start` makes it like any other — plus `claims=<targets>` on its ledger line naming what it closes.

**That field is the only write.** No follow-up is checked off, no other unit's files are touched. **Claimed** is *derived*: a follow-up that a non-dropped ledger unit claims is not open work, and everything that asks follows from that one rule —
- a dependent's need on it resolves through the claiming unit, at that unit's code-complete (§Dependencies),
- the board shows it as that unit's row, not a backlog line,
- `ws-next` does not re-propose it,
- **Workstream done** counts it resolved once the claimer is terminal.

**Dropping the claimer releases the claim**, so the follow-up re-opens itself with nothing rewritten and the dependent's need falls back to the box it always named. This is why claiming must not touch the box: a checked box would have to be un-checked on drop, against an append-only ledger line that still reads `claims=`. Deriving costs one field and no compensating operation.

`ws-start` refuses to claim a target that is missing, already checked, or already claimed by a live unit — two units cannot claim the same work. Checking a box stays what it always was: the record that the work is done, and after a claim it is optional bookkeeping, never the source.

What material a follow-up unit is proposed from, and when, is `ws-next`'s business (§Next-step chaining).

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
  `ws-start`, `ws-spike`, `ws-next`, `ws-board`, `ws-drop`, `ws-block`). Runs from anywhere.
  With no workstream arg and more than one workstream in the store, the cwd's
  current branch selects when it matches exactly one ledger unit's `branch=`
  (same locate as `ws-backlog` / `ws-resume`); otherwise the command asks.
- **Unit-scoped** — git operations on one unit's branch, so it resolves that
  unit's worktree first (`ws-resume`, `ws-restack`). `ws-resume` `cd`s into the
  worktree in the current session (already inside → continue); `ws-restack`
  operates via `git -C <worktree>`. A per-unit multiplexer window is optional
  ergonomics for parallel work, never required.
- **Spike-scoped** — store-only research (`ws-spike`, spike path of `ws-resume`).
  No worktree, no `branch=`, no forge PR state. Zero-arg `ws-resume` infers from
  cwd branch and cannot reach a spike — spikes always need an explicit id.

## Next-step chaining
Every `ws-*` skill ends by naming the single best next command and
offering to run it.

**opt-out** — offer the next command; proceed unless the user
declines. **opt-in** — offer the next command; run only on explicit
pick; dismissal must not start work.

(`ws-next` lists every runnable move, settles which unit, then offers
that one — choosing a unit runs nothing, so an opt-in dismissal lands
on the step after it.)

**Provisioned-spike handoff:** `ws-spike` may offer `ws-resume` opt-out
even though spike resume is research work — the spike was just provisioned.

A command that starts or continues code work (`ws-resume`,
`ws-start`, `ws-restack`) is offered **opt-in** when named from most
skills — running it is an explicit pick, never what a dismissal does.
Read-only commands (`ws-next`, `ws-board`) and store-only setup
(`ws-focus`) keep **opt-out**. **Provisioned-unit handoff:** `ws-start`
may offer `ws-resume` opt-out even though `ws-resume` is code work —
the unit was just provisioned.

A skill may delegate this offer to a flavor hook (§Flavor hooks) —
when an active flavor defines it, the hook's prompt replaces the
default offer, and the chosen instruction is all that runs. What the
choices offer is the flavor's business; the skill only distinguishes
outcomes: a choice resolving to `<command>` runs the command in this
session; any other choice is the flavor handing the work off its own
way — run it, re-emit the command, and stop. No flavor defines the
hook → the default offer above. The skill may *mention* the relevant
unit so a parallel-session user knows where they would go —
informational, not a precondition to running.

`ws-next` is the router; defer to it when the next step isn't
singular. **`ws-resume` execute loop:** loops in-session through
execute tasks and pauses at ship boundaries via `phase.py`; it chains
to `ws-next` only at `done` or an explicit pause pick — not after each
task. Each skill's Chain section names its next command; defaults
are opt-out for read-only routing (`ws-next`, `ws-board`) and
store-only setup (`ws-focus`). `ws-init` offers `ws-focus`; most others
offer `ws-next` unless their Chain names something else.
The offer is a work-starting command only from the skill that just
provisioned the unit (`ws-start`) or the router that picked one
(`ws-next`).

## Worktree = code only
Never write store files into a worktree. Find a unit's worktree via the ledger branch, using the active `worktree-management` flavor's `locate` (SPEC §Flavors). Drop and recreate worktrees freely — progress survives in the store.

## Flavors
External tools are pluggable via **flavors** — skills never hardwire wmx / superpowers / gh. A **group** is a fixed behavior category (defined by the skills); a **flavor** is one implementation; an **operation** is a named slot a flavor fills with a one-line instruction (a shell command, or a `skill:id` to invoke). Exactly one flavor per group is **active** (global). Skills resolve an operation at each coupling point and follow it — read here, never restated in skills. A flavor swaps only mechanism/methodology; ws bookkeeping (progress/log/ledger/PR-ready) is intrinsic and stays in the skills.

**Groups & operations**
- `worktree-management` — `create` (worktree+branch `<branch>` off `<base>`) · `remove` (`<branch>`) · `locate` (worktree path for `<branch>`).
- `spec-driven-development` — `plan` (charter+design → `T1..`) · `execute` (first unchecked task) · `ship` (open the PR) · `spec-glob` (optional — glob of this flavor's design-spec paths; powers Spec-watch below).
- `forge` — `default-branch` · `pr-status` (number+draft/ready/merged+base for `<branch>`) · `pr-create` (`<branch>`→`<base>`) · `pr-ready` (`<pr>`) · `pr-retarget` (`<pr>`→`<new-base>`).
- `review` — `review` (post-complete review implementation).

**Files (INI), merged low→high precedence**
1. built-in — `references/flavors.ini`, bundled with this `ws` skill
2. store — `<store>/flavors.ini` (`[config]`, `[active]`, custom sections)
3. overrides — path from store `[config] overrides-file=<path>` (optional)

`[active]` maps `group = flavor`; `[group/flavor]` maps `operation = instruction`.

**Resolution** (group `G`, operation `O`)
1. active flavor = merged `[active] G` → else default (`git-worktree` / `none` / `gh` / `ws-critic`).
2. instruction = effective `[G/<flavor>]` ops: layer merge, then single-level `extends` (child overrides parent per key; invalid `extends` fails closed).
3. missing after effective merge → the group **default flavor's** `O`; an optional op no layer defines → skip.
4. `word:word` → invoke as a skill; a `ws-*` command line (e.g. `ws-resume <unit>`) → invoke that skill with those arguments; else run as shell. Fill `<branch> <base> <path> <repo> <pr> <new-base>` from context; hook instructions and their `.prompt`/`.choices` may also use `<unit>` (the target unit id) and `<command>` (the firing skill's resolved next command).

Reserved flavor keys: `extends`, `prewalk`, `cheap-model-handoff`, `cheap-model-handoff.*` (handoff message templates with `{cheap}` placeholder). Per-agent model slugs (`cheap-model.<agent>`, `frontier-model.<agent>`) live in `[config]` via `ws-config set-config`; `format_cheap_handoff()` merges template + slug at runtime.

**Availability (detection)** — judge **effective** merged ops (layers + `extends`). A flavor whose `extends` target is missing is stub/unavailable.

**Flavor hooks** — optional `hook-<skill>-<event>` operations (e.g. `hook-ws-start-after`); each skill documents the events it fires. `ws-resume`: `unplanned-before` / `unplanned-after` around the plan op, `prewalk` when `prewalk = on`, `loop-before` once on in-progress units — headless fallback when hooks skip (see ws-resume). At an event, and **only in an interactive session** (never a subagent/headless run), the skill fires that hook from every **active** flavor — across all groups, in group order (`worktree-management`, `spec-driven-development`, `forge`) — that defines it. `<hook>.prompt` (a question; its presence makes the hook interactive) · `<hook>.choices.<name>` (an option's instruction; empty = skip) · `<hook>.choices.<name>.desc` (its picker description — label is `<name>`). **Modes:** no `.prompt` → run the base instruction unconditionally · `.prompt` without `.choices` → binary (Yes runs the base instruction, No skips) · `.prompt` with `.choices` → present the 2–4 options and run the chosen one (base ignored; a choices-mode hook may omit the base key entirely). Choices display in merged-key order — a key a later layer overrides keeps its built-in position — and the first choice is the preselected, safe one. A dismissed prompt skips. Base and `.choices` values resolve as any instruction (rule 4). An instruction naming a placeholder the firing skill has no value for — e.g. `<branch>` for a unit whose worktree does not exist yet — is **unfillable**: drop that choice, and drop the whole hook when the unfillable one is the base in a `.choices`-less mode or when fewer than two choices survive (falls back to the default offer, §Next-step chaining). `hook-`, `.prompt` and `.choices.` are reserved on operation keys, and an option `<name>` may not be `prompt`.

The `review` group is evaluated after `forge` when active flavor hooks
run. Its `hook-ws-resume-critic` hook invokes the post-complete review.

**Spec-watch (runtime hook)** — when a written path matches the active `spec-driven-development` flavor's `spec-glob` and no workstream's `design:` claims that spec, the runtime injects a one-line nudge to offer `ws-init` with it as the design (naming a design-less workstream as the attach-instead alternative when one exists). Mechanics: the runtime wiring (`hooks/hooks.json`) saves PostToolUse stdin and runs `<store>/hooks/spec-watch-<flavor>.sh`, emitting the first non-empty stdout; the installed script is the runtime flag. `ws-config` reconciles it on every run from the bundled template (`hooks/spec-watch.sh`), baking in the flavor's `spec-glob`; a flavor without one gets no script for that watcher. Ownership matches the spec's basename against `design:` lines — spellings vary (`~`/absolute/symlink), dated filenames don't. Distinct from §Flavor hooks (those fire *from* `ws-*` skills; this fires when an upstream tool — e.g. superpowers brainstorming — writes a spec before any workstream exists). Suggestion only: no store write, and no command runs without the user.

`overrides-file` set but unreadable → warn, skip that layer. `gh` is the assumed baseline — there is no git-only forge; a non-GitHub user adds a custom forge flavor via the overrides file. Configure with `/ws-config`.
