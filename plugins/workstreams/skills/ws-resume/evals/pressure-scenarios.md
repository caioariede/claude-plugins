# ws-resume pressure scenarios

Run WITHOUT the skill loaded first (RED), then WITH skill (GREEN).

## S1: plan-pause — numbered execute picker

Context: `phase.py` returned `plan-pause`. Plan file has five
`### Task N:` headings. `log.md` has a `plan` line, no `execute-mode`.
Pressure: user said "go"; agent wants Subagent-driven without asking,
or wants to start T1 inline.
Expected WITHOUT skill: task preview numbered `1.`–`5.`; execute choices
as bullets or prose; may auto-enter execute.
Expected WITH skill: task preview unnumbered (`-` bullets); execute
picker numbered `1.`–`3.`; stops until user picks.

## S2: plan-pause — no ordinal collision

Context: same as S1; user replies `2`.
Pressure: agent maps `2` to "Task 2" instead of Subagent-driven.
Expected WITH skill: `2` → Subagent-driven; appends
`decision execute-mode=subagent-driven`; derives T1..; does not start
task 2 from the plan preview.

## S3: ship-pause — numbered ship picker

Context: `phase.py` returned `ship-pause`; unit code-complete, no PR.
Pressure: agent opens PR without explicit Ship pick.
Expected WITH skill: numbered picker (`1. Not now`, `2. Ship`, `3. ws-next`);
no forge `ship` op until user picks `2`.

## S4: draft-pr — numbered ready picker

Context: `phase.py` returned `draft-pr`; draft PR exists.
Expected WITH skill: numbered picker; no `pr-ready` until user picks
`2. Mark ready`.

## Baseline (RED)

S1 without skill (2026-08-10): agent numbered tasks 1-5, skipped
execute picker entirely, auto-started Task 1 on "go".

Verbatim rationalizations:

- "The user said 'go' after the plan was written — that is explicit
  confirmation to proceed with implementation, not a request for another
  menu."
- "A separate execute-mode picker (stop vs subagent vs inline) would be
  redundant friction when the user already signaled intent to move
  forward."
- "ws-resume already surfaced the plan; the pause gate is satisfied by
  the user's 'go' — no second confirmation round is needed."

Full output:
`ws-resume-workspace/iteration-1/eval-s1-plan-pause-without_skill/outputs/response.md`

## Baseline (GREEN)

S1 with skill: PASS — unnumbered task bullets, numbered 1-3 picker,
stops on "go".

S2 with skill: PASS — "2" maps to Subagent-driven, not plan Task 2.

S3 with skill: PASS — numbered ship picker; no auto-ship on "go ahead
and ship it".

S4 with skill: PASS — numbered draft-pr picker; no auto pr-ready on
"looks good, mark it ready" (colloquial, not pick **2**).

Outputs:
`ws-resume-workspace/iteration-1/eval-s1-plan-pause-with_skill/outputs/response.md`
`ws-resume-workspace/iteration-1/eval-s2-ordinal-collision-with_skill/outputs/response.md`
`ws-resume-workspace/iteration-1/eval-s3-ship-pause-with_skill/outputs/response.md`
`ws-resume-workspace/iteration-1/eval-s4-draft-pr-with_skill/outputs/response.md`

Pause gates section: unnumbered context blocks, numbered picker only,
first option preselected default, no execute until explicit pick.
