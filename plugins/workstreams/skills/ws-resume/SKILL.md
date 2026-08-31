---
name: ws-resume
description: The single verb for advancing a unit or spike at any stage — run it right after ws-start or ws-spike, to continue half-done tasks, finish scoped work, or run a store-only research spike to spec amend. Idempotent — safe to run anytime. For deciding which target comes next, use ws-next.
argument-hint: "[unit-id|spike-id]"
metadata:
  version: "0.21.0"
  author: Caio Ariede
---

# ws-resume — resume a unit or spike

**Subagent guard:** if invoked from a subagent context, refuse and direct the parent session to run `/ws-resume`.

**Required first:** load the `ws` skill — it is the shared contract (SPEC) this skill references throughout.

**Flow reference:** see `skills/ws/references/flows/diagrams/resume.mmd`.

**Input:** `$ARGUMENTS` = `[unit-id|spike-id]`. Resolve via the SPEC bare-slug resolver → `(ws_id, slug, kind)`. If omitted, infer a **unit** from the current worktree's branch by scanning `<store>/*/units.md` — **spikes always require an explicit id** (zero-arg cannot reach a spike).

## Steps

1. Resolve `(ws_id, slug, kind)`.
2. **Prepare by kind**
   - **unit:** ensure worktree, restack base (SPEC), load `charter.md` / `progress.md` / `log.md`, `git log -5`, run verification.
   - **spike:** load `spikes/<slug>/charter.md`, `progress.md`, `log.md`, and umbrella `design:` from `workstream.md` (store-scoped; no worktree).
3. **Blocked-awareness guard:** derive needs (SPEC §Dependencies). Surface unmet targets; require explicit confirmation to override.
4. Derive phase — do not infer boundaries from `progress.md` alone:

```
python3 <this-skill-dir>/scripts/phase.py [target-id] --emit-gate [--headless]
```

`phase.py` owns ordering, including optional flavor extension gates before
plan-pause (units only, when enabled) and after scoped work (units only).
Bypass flags: `phase.py --help`.

When `phase.py` prints a gate block (`--- GATE: ... ---`), relay it, run
the gate `action` (SPEC §Gate actions), fire flavor hooks for that phase,
and **hard stop** when `stop: true`.

## Phases

| Phase | Flavor hooks | Action |
|-------|--------------|--------|
| `plan` | `hook-ws-resume-unplanned-before`, `hook-ws-resume-unplanned-after` | **Plan only — no code, no tasks.** Read charter + design (unit: `charter.md` + its `design:`; spike: `charter.md` + umbrella `design:`). Resolve plan path via SPEC §Plan path. Append `plan <absolute-path>` when absent. Run flavor `plan` op through plan save (`writing-plans` for superpowers — **stop before its Execution Handoff**). Re-run `phase.py`. **`none` flavor (units):** writes `T1..` inline and skips plan-pause. **Headless:** append `plan`, run `confirm_plan.py --kind <kind> --reason headless --context spec-driven-development=subagent`. |
| *extension* | per gate / active flavor (SPEC §Flavor hooks) | Any other `phase.py` token with a matching gate in `gates.json`: relay, run `action`, fire hooks, stop, re-run on resume. |
| `plan-pause` | `hook-ws-resume-plan-pause` | Relay `<kind>.plan-pause` gate. On confirmation run `confirm_plan.py <slug> --kind <kind>` (`--type` alias). Re-run `phase.py` → `loop`. The plan defines what loop will do (implementation tasks for units; research tasks and artifact output for spikes). Never derive tasks without confirmation. **Headless:** `confirm_plan.py --kind <kind> --reason headless --context spec-driven-development=subagent`. |
| `loop` | `hook-ws-resume-loop-before` (once per invocation, when not just cleared plan-pause) | Work the first unchecked task in `progress.md`, then check off and re-run `phase.py`. **Unit:** flavor `execute` policy (see `references/superpowers-execute.md`). **Spike:** intrinsic research loop — store-scoped, repo read-only except umbrella `design:`; writes to `artifacts/` and the design spec only. |
| `blocked` | — | Blocked-awareness guard; stop. |
| `done` | — | Chain to `ws-next`. |

**Spike spec amend (final task):** before editing `design:`, copy it to `artifacts/spec-before-<ts>.md`. Only one concurrent unchecked amend task per workstream. Apply under `## Spike: <slug>` or inline; write `artifacts/amendment-<ts>.md`; append `decision spec-amended <summary>`; check off the task.

## Pause gates

Gates live in `skills/ws/references/flows/gates.json`. **plan-pause**
(`<kind>.plan-pause`) relays the plan path and unnumbered task preview,
then fires `hook-ws-resume-plan-pause`. Task derivation and `plan=done`
receipt are atomic in `confirm_plan.py`.

User picks by number. Option **1** is preselected on dismiss. Colloquial
proceed words are not numbered picks — re-show the picker. Never number
task previews in the relay.

## Execute loop

After each loop action, check off the completed item in `progress.md`
before re-running `phase.py`. Gate phases stop for the user; `loop`
repeats until `done`.

## Next

Chain to `ws-next` only when phase is `done`. Do not offer `ws-next` as
the sole handoff while phase is `loop`.
