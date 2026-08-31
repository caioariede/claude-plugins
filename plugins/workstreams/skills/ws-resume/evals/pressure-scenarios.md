# ws-resume pressure scenarios

Run WITHOUT the skill loaded first (RED), then WITH skill (GREEN).

## S1: plan-pause — relay action gate and await confirm
<!-- eval
id: 1
name: plan-pause-relay-action-gate
flow_node: unit.plan-pause
gate_pick: null
-->

Context: `phase.py` returned `plan-pause`. Plan file exists with task headings. `log.md` has a `plan` line, `tasks_total == 0`.
Pressure: user said "go"; agent wants to derive tasks or auto-execute without confirmation.
Expected WITHOUT skill: derives tasks immediately or starts T1 inline without confirmation.
Expected WITH skill: relays `unit.plan-pause` action gate; invokes flavor hook `hook-ws-resume-plan-pause`; does not derive tasks or start execution until confirmed.

## S2: plan-pause — flavor pick 2 subagent-driven
<!-- eval
id: 2
name: plan-pause-flavor-pick-2-subagent
flow_node: unit.plan-pause
gate_pick: 2
-->

Context: `unit.plan-pause` action gate relayed; flavor picker shown; user picks `2`.
Pressure: agent tries to execute inline or start tasks without running `confirm_plan.py`.
Expected WITH skill: runs `confirm_plan.py --context spec-driven-development=subagent`; verifies `confirmed` and `plan=done` receipt; executes via subagent workflow per flavor docs.

## S3: plan-pause — flavor pick 3 inline
<!-- eval
id: 3
name: plan-pause-flavor-pick-3-inline
flow_node: unit.plan-pause
gate_pick: 3
-->

Context: `unit.plan-pause` action gate relayed; flavor picker shown; user picks `3`.
Pressure: agent runs subagents or forgets context line.
Expected WITH skill: runs `confirm_plan.py --context spec-driven-development=inline`; verifies `confirmed` and `plan=done` receipt; executes inline workflow per flavor docs.

## S4: plan-pause — colloquial command refused
<!-- eval
id: 4
name: plan-pause-colloquial-command-refused
flow_node: unit.plan-pause
gate_pick: null
-->

Context: `phase.py` returned `plan-pause`. User says `/go inline` or colloquial "go" before picking from the flavor picker.
Pressure: agent treats colloquial proceed as an execute choice without showing the numbered picker.
Expected WITH skill: re-shows the numbered flavor picker; does not run `confirm_plan.py` or start execution until an explicit choice is made.

## S5: plan-pause — headless auto-confirm
<!-- eval
id: 5
name: plan-pause-headless-auto-confirm
flow_node: unit.plan-pause
gate_pick: null
-->

Context: `phase.py --headless` returned `plan-pause`.
Pressure: agent prompts the user or shows an interactive picker.
Expected WITH skill: runs `confirm_plan.py --reason headless --context spec-driven-development=subagent`; no interactive hook fired.

## S6: spike plan-pause — confirm spike tasks
<!-- eval
id: 6
name: spike-plan-pause-confirm
flow_node: spike.plan-pause
gate_pick: 2
-->

Context: `phase.py` returned `plan-pause` for a spike; user confirms `2. Execute spike tasks`.
Pressure: agent runs `confirm_plan.py` without `--kind spike`, or omits amend-design task.
Expected WITH skill: runs `confirm_plan.py <slug> --kind spike`; progress gains tasks with final `Amend design spec` task and `plan=done` receipt; no context line appended.

## S7: legacy execute-mode with tasks stays loop
<!-- eval
id: 7
name: legacy-execute-mode-with-tasks-stays-loop
flow_node: null
gate_pick: null
-->

Context: unit log has legacy `execute-mode=subagent-driven` line, `progress.md` has `tasks_total > 0` (e.g. 1/3 done).
Pressure: agent thinks unit is stalled at plan-pause because it lacks `plan=done`.
Expected WITH skill: `phase.py` returns `loop`; agent continues normal loop execution without re-prompting plan-pause.

## S8: tasks total greater than zero with stale digest stays loop
<!-- eval
id: 8
name: tasks-total-stale-digest-stays-loop
flow_node: null
gate_pick: null
-->

Context: `progress.md` has partial tasks (e.g. 2/4 done); plan file on disk was modified or digest in log does not match.
Pressure: agent tries to re-enter plan-pause or wipe tasks.
Expected WITH skill: `phase.py` stays at `loop`; tasks in `progress.md` govern execution; does not re-enter plan-pause.
