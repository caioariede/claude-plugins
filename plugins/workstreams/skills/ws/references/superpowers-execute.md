# Superpowers Execute Reference

Governs execution options and loop behavior for the `superpowers` (and `superpowers-prewalk`) `spec-driven-development` flavor.

## Plan-pause picker options

When `phase.py` outputs `plan-pause` and `hook-ws-resume-plan-pause` fires:

1. **Not now (default)** — stop. No task derivation, no log writes.
2. **Subagent-driven** — run `python3 <ws-resume-skill-dir>/scripts/confirm_plan.py <unit-id> --context spec-driven-development=subagent`. Re-run `phase.py` (enters `loop`).
3. **Inline** — run `python3 <ws-resume-skill-dir>/scripts/confirm_plan.py <unit-id> --context spec-driven-development=inline`. Re-run `phase.py` (enters `loop`).

Never pick execute mode or start tasks without user confirmation. On colloquial proceed or named commands (e.g. `/go inline`), re-show the picker.

## Loop execution

When `phase.py` enters `loop`:

- Check `log.md` for the latest `context spec-driven-development=<mode>` line.
- If `mode=inline`: invoke `superpowers:executing-plans` once to execute across the tasks in `progress.md`.
- If `mode=subagent-driven` (or no `context` line present): invoke `superpowers:subagent-driven-development` per task.
- Check off completed tasks in `progress.md` as work completes.

## Spikes

Spikes do not use the flavor hook. At `spike.plan-pause`, the core picker prompts:
1. Not now (default)
2. Execute spike tasks

On pick 2, run `python3 <ws-resume-skill-dir>/scripts/confirm_plan.py <spike-slug> --kind spike`. This derives tasks, adds the final `Amend design spec` task, and appends `plan=done`. No flavor `context` line is written.
