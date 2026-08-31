---
name: ws-resume
description: The single verb for advancing a unit or spike at any stage — run it right after ws-start or ws-spike, to continue half-done tasks, ship a finished unit, or run a store-only research spike to spec amend. Idempotent — safe to run anytime. For deciding which target comes next, use ws-next.
argument-hint: "[unit-id|spike-id]"
metadata:
  version: "0.17.0"
  author: Caio Ariede
---

# ws-resume — resume a unit or spike

**Subagent guard:** if invoked from a subagent context, refuse and direct the parent session to run `/ws-resume`.

**Required first:** load the `ws` skill — it is the shared contract (SPEC) this skill references throughout.

**Flow reference:** see visual decision diagrams in `skills/ws/references/flows/diagrams/resume-unit.mmd` and `resume-spike.mmd`.

**Input:** `$ARGUMENTS` = `[unit-id|spike-id]`. Resolve via the SPEC bare-slug resolver → `(ws_id, slug, kind)`. If omitted, infer a **unit** from the current worktree's branch by scanning `<store>/*/units.md` — **spikes always require an explicit id** (zero-arg cannot reach a spike).

## Dispatch by kind

After resolving `(ws_id, slug, kind)`:

| Step | Unit path | Spike path |
|------|-----------|------------|
| `reconcile.py` / ship-detect | yes | **skip** |
| Worktree ensure / `gather_pr_state` | yes | **skip** (store-scoped) |
| `phase.py` | full (incl. ship) | spike branch (no ship/draft-pr) |
| Execute | flavor `execute` in worktree | **intrinsic research loop** (below) |
| Terminal | ship / PR-ready | spec amend + derived `complete` |

---

## Unit path

## Steps
1. Resolve the unit → `ws-id`, `repo`, `branch`. (With no argument, infer the unit from the current worktree's branch.)
2. **Merged terminal** — run before worktree ensure and restack. Run
reconcile; it honors `merged-via` in the log, detects
shipped-elsewhere evidence, and reconciles tasks when terminal:

```
python3 <this-skill-dir>/scripts/reconcile.py [unit-id] --emit-gate
```

Print the script line (`reconciled …` / `already-consistent` /
`not-merged` / `unknown-forge` / `unknown-git` / `ship-detect-candidate
branch=… sha=…`). When terminal (`reconciled`, `already-consistent`,
or after tier-A auto-record), stop — no worktree recreate, plan, or
execute. On `ship-detect-candidate`, relay the **ship-detect gate**
(§Pause gates) emitted by `--emit-gate` before continuing. Chain to `ws-next` when `done`
(§Next).
3. Ensure the worktree exists and self-locate into it (SPEC "Command scope"):
   - already inside it (branch matches) → continue;
   - worktree exists but you're elsewhere → `cd` into it in the current session;
   - worktree gone but branch exists → recreate it via the active `worktree-management` flavor's `create` for `<branch>` off `<base>`, then work there;
   - branch also gone → fresh start off the repo default branch (per SPEC); the store's progress is your restart baseline.
4. Reconcile base per SPEC Restack reconciliation — if the active `forge` flavor's `pr-status` base differs from the unit's recorded base, realign and append a `restack` line.
5. Load state: read `charter.md` (why this unit exists + its `design:`), `progress.md` (Tasks + Follow-ups), and `log.md` (recent notes); run `git log -5` and the repo's verification command to confirm the code state.
6. **Blocked-awareness guard:** before advancing (plan/execute), derive the unit's needs — implicit base + `## Needs` (SPEC §Dependencies). If any is unmet, the unit is **blocked**: surface it — name the unmet target(s) and warn the unit is blocked — then require explicit confirmation to proceed anyway. `ws-resume` is the intentional override path: it warns, it does not silently proceed, and it does not hard-refuse.
7. Derive phase — do not infer planning or execute boundaries from `progress.md` alone:

```
python3 <this-skill-dir>/scripts/phase.py [unit-id] --emit-gate [--skip-prewalk] [--skip-critic] [--headless]
```

**Headless** sessions: pass `--headless` (phase falls through; append `decision prewalk=skipped reason=headless` when entering plan-pause from a skipped prewalk path).

When `phase.py` outputs a structured gate block (`--- GATE: ... ---`), relay its prompt and options directly to the user (§Pause gates).

| Phase | Action |
|-------|--------|
| `plan` | **Plan only — no code, no tasks.** Read `charter.md` and its `design:` spec; note what the base branch already ships. Resolve the unit plan path via SPEC §Plan path (`<design-dir>/<bare-slug>-plan.md` — not the design-basename swap). If **that** path already exists and `log.md` lacks a `plan` line → append `plan` only, re-run phase.py, stop at `plan-pause`, `prewalk-config`, or `prewalk` when enabled. Else: fire `hook-ws-resume-unplanned-before` (interactive); run the flavor `plan` op through plan save (`writing-plans` for superpowers — **stop before its Execution Handoff**; plan-pause owns that gate); fire `hook-ws-resume-unplanned-after`. Append `plan <absolute-path>` to `log.md` when absent. Do **not** derive `T1..`, do **not** touch source files. Re-run phase.py. **`none` flavor:** its `plan` op writes `T1..` inline and skips this gate. **Headless** (hooks skip): resolve plan path, run `plan` if no file yet, append `plan`, run `confirm_plan.py --reason headless --context spec-driven-development=subagent`, enter execute. |
| `prewalk-config` | Prewalk is active but `[config]` is incomplete (`ws-config show` `required:` lines). Print each requirement; tell user to run `ws-config set-config …`, then re-run `/ws-resume`. **Hard stop** — no exploration until `agent` and `cheap-model.<agent>` are pinned. |
| `prewalk` | When active flavor has `prewalk = on` (typically `superpowers-prewalk`): fire `hook-ws-resume-prewalk` (interactive); invoke the **ws-prewalk** skill — read-only exploration, write `units/<slug>/prewalk.md`, append `decision prewalk=done plan=<path> digest=<8-hex>`. **Hard stop** — print `format_cheap_handoff` from ws_cli (flavor handoff template + `[config]` cheap slug); user switches model and re-runs `/ws-resume`. No source edits. |
| `critic` | When active review flavor is `ws-critic`: fire `hook-ws-resume-critic` (interactive); invoke **ws-critic** for a fresh, read-only adversarial review of the charter, design, plan, diff, and tests. The parent writes `critic.md` and `decision critic=done verdict=... digest=<8-hex>`. Advisory only; hard stop, then continue to `ship-pause`. |
| `plan-pause` | **Step 0 (prewalk path):** when resuming after prewalk or when prewalk was skipped/grandfathered, remind user to use cheap model if not already switched (`ws-config show` cheap-model line). Then relay the **plan-pause** action gate block from `phase.py --emit-gate`. Fire `hook-ws-resume-plan-pause` (interactive). On confirmation, run `python3 <this-skill-dir>/scripts/confirm_plan.py [unit-id] [--context <group>=<value>]`. Re-run phase.py (enters `loop`). Never derive tasks or start T1 without user confirmation. Colloquial proceed words (`/go`, etc.): re-show the picker. **Headless:** run `confirm_plan.py [unit-id] --reason headless --context spec-driven-development=subagent`. |
| `loop` | Unless this invocation just cleared `plan-pause`, fire `hook-ws-resume-loop-before` once (superpowers). Run execute for the first unchecked task per the active flavor's execute policy (see `<ws-skill-dir>/references/superpowers-execute.md` for superpowers). Enter the execute loop (below). |
| `ship-pause` | Relay the **ship-pause** gate block from `phase.py --emit-gate` (§Pause gates). On **2**, run ship flavor, re-run phase.py. If a `stacked-on` unit is not yet merged (per the active `forge` flavor's `pr-status`), surface it and let the user decide. On **3**, chain to `ws-next`. |
| `draft-pr` | Relay the **draft-pr** gate block from `phase.py --emit-gate` (§Pause gates). On **2**, run forge `pr-ready`, re-run phase.py. On **3**, chain to `ws-next`. |
| `blocked` | Blocked-awareness guard; stop. |
| `done` | Chain to `ws-next` (below). |

**Plan convention:** Last execute task owns verification; opening the PR is ship-pause when `code_complete`.

**No auto-ship:** At `code_complete` with no PR, never run the ship flavor until the user picks **2** at ship-pause.

## Pause gates

Every number on screen belongs to the live picker — context blocks use
no ordinals (same rule as ws-next move relay). Gates and pickers are defined
in `skills/ws/references/flows/gates.json` and emitted via `--emit-gate`.

**ship-detect gate** (`unit.ship-detect`) — emitted by `reconcile.py --emit-gate` only when step 2 printed `ship-detect-candidate
branch=… sha=…`. Context block has no ordinals:

```
Work may already be on the default branch (ledger tip is behind default).

1. Not now (default)
2. Record merged-via and reconcile tasks
3. Continue resume — not shipped yet
```

Pick **1** → `python3 <this-skill-dir>/scripts/record_dismissed.py [unit-id] sha=<s>` using the candidate sha from the step 2 `ship-detect-candidate` line; print its line; fall through or stop per user intent. Pick **2** → `python3 <this-skill-dir>/scripts/record_merged_via.py [unit-id] branch=<b> sha=<s> [pr=<n>]` using the candidate fields from the step 2 `ship-detect-candidate` line; print its line; chain to `ws-next` if phase is `done`. Pick **3** → fall through. Never auto-record without pick **2**.

**plan-pause gate** (`unit.plan-pause`) — emitted by `phase.py --emit-gate`.
Relays the plan path and unnumbered task preview from context, then fires
the active flavor's execute hook (`hook-ws-resume-plan-pause`). Task derivation
and log receipt are performed atomically by `confirm_plan.py`.

**ship-pause gate** (`unit.ship-pause`) — emitted by `phase.py --emit-gate`.
Summarize unit state, include the latest critic verdict and `critic.md` path
when present, then relay prompt and options 1–3.

**draft-pr gate** (`unit.draft-pr`) — emitted by `phase.py --emit-gate`.
Summarize PR state, then relay prompt and options 1–3.

User picks by number. Option **1** is preselected on dismiss. Colloquial
proceed words (`go`, `yes`, `lgtm`, `ship it`) are not numbered picks —
re-show the picker and wait. Never number task previews — plan
`### Task N:` ordinals stay in the file, not on screen.

## Execute

Follow the active flavor's execute policy. For superpowers, see
`<ws-skill-dir>/references/superpowers-execute.md`.

## Execute loop

After execute action, check off the completed task in `progress.md`
(`- [x] T<n>`) before re-running phase derivation:

```
python3 <this-skill-dir>/scripts/phase.py [unit-id]
```

Then act on the phase table above (`loop` → repeat execute; pauses → stop for user).

## Next

Chain to `ws-next` only when phase is `done`, when the user picks `ws-next` at a pause, or after ship/mark-ready leaves phase `done` (§Next-step chaining). Do not offer `ws-next` as the sole handoff while phase is `loop`.

---

## Spike path

Store-scoped — no worktree, no forge PR state, no reconcile/ship.

1. Load `spikes/<slug>/charter.md`, `progress.md`, `log.md`; read umbrella `design:` from `workstream.md`.
2. **Blocked-awareness guard** — same as units: surface unmet needs, require confirmation to override.
3. Derive phase:

```
python3 <this-skill-dir>/scripts/phase.py <spike-id> --emit-gate
```

| Phase | Action |
|-------|--------|
| `plan` | **Plan only.** Read `charter.md` + umbrella `design:`. Resolve plan path via SPEC §Plan path. Run flavor `plan` op (research scope — no product-code file map). Append `plan <absolute-path>` when absent. Re-run phase.py → `plan-pause`. |
| `plan-pause` | Relay `spike.plan-pause` gate block. On pick **2** (Execute spike tasks): run `python3 <this-skill-dir>/scripts/confirm_plan.py <spike-slug> --kind spike`. Progress gains derived tasks and the final **"Amend design spec"** task; `log.md` gains `plan=done` receipt. Re-run phase.py → `loop`. |
| `loop` | **Intrinsic research loop** — no flavor execute/ship. Session stays store-scoped; repo is read-only except the umbrella `design:` path. Writes go to `artifacts/` and the design spec only. Work the first unchecked task; check off in `progress.md`; re-run phase.py. |
| `blocked` | Blocked-awareness guard; stop. |
| `done` | Chain to `ws-next`. |

**Spec amend (final task):** before editing `design:`, copy it to `artifacts/spec-before-<ts>.md`. Only one spike per workstream may hold an unchecked "Amend design spec" task — refuse a second concurrent amend. Apply findings under `## Spike: <slug>` or inline; write `artifacts/amendment-<ts>.md`; append `decision spec-amended <summary>`; check off the task. Missing/unwritable design → block check-off; append `decision spec-amend-failed <reason>` if attempted.
