# Superpowers Execute Reference

Governs execution options and loop behavior for the `superpowers` (and `superpowers-prewalk`) `spec-driven-development` flavor.

## Plan-pause picker options

When `phase.py` outputs `plan-pause` and `hook-ws-resume-plan-pause` fires
(units and spikes):

1. **Not now (default)** — stop. No task derivation, no log writes.
2. **Subagent-driven** — run `python3 <ws-resume-skill-dir>/scripts/confirm_plan.py <target-id> --kind <kind> --context spec-driven-development=subagent`. Re-run `phase.py` (enters `loop`).
3. **Inline** — run `python3 <ws-resume-skill-dir>/scripts/confirm_plan.py <target-id> --kind <kind> --context spec-driven-development=inline`. Re-run `phase.py` (enters `loop`).

Use the resolved `kind` from phase resolution (`unit` or `spike`). Never
pick execute mode or start tasks without user confirmation. On colloquial
proceed or named commands (e.g. `/go inline`), re-show the picker.

## Loop execution

When `phase.py` enters `loop`:

- **Units:** check `log.md` for the latest `context spec-driven-development=<mode>` line. `mode=inline` → `superpowers:executing-plans` once across tasks. `mode=subagent-driven` (or no context line) → `superpowers:subagent-driven-development` per task.
- **Spikes:** intrinsic research loop per ws-resume — work plan tasks, write `artifacts/`, amend design on the final task. No flavor execute op.

Check off completed tasks in `progress.md` as work completes.
