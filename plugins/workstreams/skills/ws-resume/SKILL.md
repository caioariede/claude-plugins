---
name: ws-resume
description: The single verb for advancing a unit or spike at any stage — run it right after ws-start or ws-spike, to continue half-done tasks, finish scoped work, or run a store-only research spike to spec amend. Idempotent — safe to run anytime. For deciding which target comes next, use ws-next.
argument-hint: "[unit-id|spike-id]"
metadata:
  version: "0.19.0"
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
| Worktree ensure / `gather_pr_state` | yes | **skip** (store-scoped) |
| `phase.py` | full unit loop | spike branch |
| Execute | flavor `execute` in worktree | **intrinsic research loop** (below) |
| Terminal | scoped work complete or dropped | spec amend + derived `complete` |

---

## Unit path

### Steps

1. Resolve the unit → `ws-id`, `repo`, `branch`. (With no argument, infer the unit from the current worktree's branch.)
2. Ensure the worktree exists and self-locate into it (SPEC "Command scope"):
   - already inside it (branch matches) → continue;
   - worktree exists but you're elsewhere → `cd` into it in the current session;
   - worktree gone but branch exists → recreate it via the active `worktree-management` flavor's `create` for `<branch>` off `<base>`, then work there;
   - branch also gone → fresh start off the repo default branch (per SPEC); the store's progress is your restart baseline.
3. Reconcile base per SPEC Restack reconciliation — if the active `forge` flavor's `pr-status` base differs from the unit's recorded base, realign and append a `restack` line.
4. Load state: read `charter.md` (why this unit exists + its `design:`), `progress.md` (Tasks + Follow-ups), and `log.md` (recent notes); run `git log -5` and the repo's verification command to confirm the code state.
5. **Blocked-awareness guard:** before advancing (plan/execute), derive the unit's needs — implicit base + `## Needs` (SPEC §Dependencies). If any is unmet, the unit is **blocked**: surface it — name the unmet target(s) and warn the unit is blocked — then require explicit confirmation to proceed anyway. `ws-resume` is the intentional override path: it warns, it does not silently proceed, and it does not hard-refuse.
6. Derive phase — do not infer planning or execute boundaries from `progress.md` alone:

```
python3 <this-skill-dir>/scripts/phase.py [unit-id] --emit-gate [--headless]
```

`phase.py` owns phase ordering, including optional flavor extension gates
before plan-pause and after the task/follow-up loop (SPEC §Flavor
extension phases). Optional bypass flags live on `phase.py --help`, not
here.

When `phase.py` outputs a structured gate block (`--- GATE: ... ---`),
relay its prompt and options (§Pause gates), run the gate `action` (SPEC
§Gate actions), fire any flavor hooks for that gate, and **hard stop**
when the gate sets `stop: true`.

| Phase | Flavor hooks | Action |
|-------|--------------|--------|
| `plan` | `hook-ws-resume-unplanned-before`, `hook-ws-resume-unplanned-after` | **Plan only — no code, no tasks.** Read `charter.md` and its `design:` spec; note what the base branch already ships. Resolve the unit plan path via SPEC §Plan path (`<design-dir>/<bare-slug>-plan.md` — not the design-basename swap). If **that** path already exists and `log.md` lacks a `plan` line → append `plan` only, re-run phase.py, stop at the next gate-bearing phase. Else: fire unplanned hooks (interactive); run the flavor `plan` op through plan save (`writing-plans` for superpowers — **stop before its Execution Handoff**; plan-pause owns that gate); fire unplanned-after. Append `plan <absolute-path>` to `log.md` when absent. Do **not** derive `T1..`, do **not** touch source files. Re-run phase.py. **`none` flavor:** its `plan` op writes `T1..` inline and skips plan-pause. **Headless** (hooks skip): resolve plan path, run `plan` if no file yet, append `plan`, run `confirm_plan.py --reason headless --context spec-driven-development=subagent`, enter execute. |
| *extension* | per gate / active flavor (SPEC §Flavor hooks) | Any other `phase.py` token with a matching gate in `gates.json`: relay the gate block, run its `action`, fire defined `hook-ws-resume-*` hooks, stop when `stop: true`, re-run phase.py on resume. |
| `plan-pause` | `hook-ws-resume-plan-pause` | Relay gate; on confirmation run `confirm_plan.py` per `await_plan_confirm` action; re-run phase.py (enters `loop`). Never derive tasks or start T1 without user confirmation. Colloquial proceed words (`/go`, etc.): re-show the picker. **Headless:** `confirm_plan.py [unit-id] --reason headless --context spec-driven-development=subagent`. |
| `loop` | `hook-ws-resume-loop-before` (once per invocation, when not just cleared plan-pause) | Run execute for the first unchecked task or follow-up per the active flavor's execute policy (see `<ws-skill-dir>/references/superpowers-execute.md` for superpowers). Enter the execute loop (below). |
| `blocked` | — | Blocked-awareness guard; stop. |
| `done` | — | Chain to `ws-next` (below). |

**Plan convention:** Last execute task owns verification.

## Pause gates

Every number on screen belongs to the live picker — context blocks use
no ordinals (same rule as ws-next move relay). Gates are defined in
`skills/ws/references/flows/gates.json` and emitted via `--emit-gate`.

**plan-pause gate** (`unit.plan-pause`) — relays the plan path and
unnumbered task preview from context, then fires
`hook-ws-resume-plan-pause`. Task derivation and log receipt are
performed atomically by `confirm_plan.py`.

User picks by number. Option **1** is preselected on dismiss. Colloquial
proceed words (`go`, `yes`, `lgtm`) are not numbered picks — re-show the
picker and wait. Never number task previews — plan `### Task N:` ordinals
stay in the file, not on screen.

## Execute

Follow the active flavor's execute policy. For superpowers, see
`<ws-skill-dir>/references/superpowers-execute.md`.

## Execute loop

After execute action, check off the completed item in `progress.md`
(`- [x] T<n>` or `- [x] F<n>`) before re-running phase derivation:

```
python3 <this-skill-dir>/scripts/phase.py [unit-id]
```

Then act on the phase table above (`loop` → repeat execute; gate phases → stop for user).

## Next

Chain to `ws-next` only when phase is `done`. Do not offer `ws-next` as the sole handoff while phase is `loop`.

---

## Spike path

Store-scoped — no worktree, no forge PR state.

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
| `loop` | **Intrinsic research loop** — no flavor execute. Session stays store-scoped; repo is read-only except the umbrella `design:` path. Writes go to `artifacts/` and the design spec only. Work the first unchecked task; check off in `progress.md`; re-run phase.py. |
| `blocked` | Blocked-awareness guard; stop. |
| `done` | Chain to `ws-next`. |

**Spec amend (final task):** before editing `design:`, copy it to `artifacts/spec-before-<ts>.md`. Only one spike per workstream may hold an unchecked "Amend design spec" task — refuse a second concurrent amend. Apply findings under `## Spike: <slug>` or inline; write `artifacts/amendment-<ts>.md`; append `decision spec-amended <summary>`; check off the task. Missing/unwritable design → block check-off; append `decision spec-amend-failed <reason>` if attempted.
