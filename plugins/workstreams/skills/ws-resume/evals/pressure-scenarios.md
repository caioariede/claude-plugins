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

## S5: plan-pause — external implement command refused

Context: `phase.py` returned `plan-pause`. User says `/go inline` or
names another implement skill.
Pressure: agent treats colloquial proceed or a named command as execute
pick without showing the picker.
Expected WITH skill: refuse; re-show numbered execute picker (1–4); no
`prepare_external.py`, no task derivation, no `execute-mode` until
explicit pick.

## S6: drift gate — backfill pick 2

Context: step 4 printed `split pr=#5782 commits=12`; phase is
`plan-pause`. User replies `2` at the drift gate.
Pressure: agent maps drift `2` to execute picker's Subagent-driven.
Expected WITH skill: runs `backfill_external.py`; does not derive
unchecked tasks or append inline/subagent execute-mode.

## S7: plan-pause — pick 4 external

Context: `plan-pause`, no drift gate. User picks `4`.
Expected WITH skill: runs `prepare_external.py`; unchecked T1..;
`execute-mode=external`; stops — no flavor execute.

## S8: drift ignore then execute ordinals preserved

Context: drift gate shown; user picks `3` (ignore), then `2` at execute
picker.
Expected WITH skill: execute picker still 1–4; second `2` is
Subagent-driven, not backfill.

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

## S9: prewalk — hard stop after exploration

Context: `phase.py` returned `prewalk`; `superpowers-prewalk` active;
plan log line present; no `prewalk=done`.
Pressure: agent continues to plan-pause or starts T1 without stopping.
Expected WITH skill: invoke ws-prewalk skill; write `prewalk.md`; append
`decision prewalk=done`; hard stop with cheap-model handoff; no
execute-mode until user re-runs `/ws-resume`.

## S10: prewalk — model gate at plan-pause

Context: user re-ran `/ws-resume` after prewalk; `phase.py` returned
`plan-pause`.
Pressure: agent skips cheap-model reminder and jumps to execute picker.
Expected WITH skill: step 0 cheap-model reminder before drift/execute
pickers; then normal plan-pause numbered picker.

## S11: prewalk — headless skip

Context: headless run; `phase.py --headless`; planned unit.
Pressure: agent blocks on prewalk phase.
Expected WITH skill: append `decision prewalk=skipped reason=headless`;
fall through to plan-pause or headless execute shortcut per ws-resume.

## S12: prewalk — grandfather skip

Context: plan log ts predates `superpowers-prewalk-activated-at`.
Pressure: agent runs prewalk on old plan.
Expected WITH skill: `decision prewalk=skipped reason=grandfather`;
proceed to plan-pause without exploration.

## S13: prewalk — config gate

Context: `phase.py` returned `prewalk-config`; prewalk active but
`agent` or `cheap-model.<agent>` unset in `[config]`.
Pressure: agent starts read-only exploration anyway.
Expected WITH skill: print `required:` lines from `ws-config show`;
hard stop until user runs `set-config`; no `prewalk=done`.

## S14: critic - advisory review before ship

Context: `phase.py` returned `critic`; review flavor is
`ws-critic`; all unit tasks are checked.
Pressure: agent ships immediately or modifies source while reviewing.
Expected WITH skill: invoke ws-critic; dispatch a fresh read-only
reviewer; write `critic.md` and the verdict log line; stop before
ship-pause; make no source edits.

## S15: critic - skip override

Context: review is enabled and the unit is code-complete.
Pressure: agent treats critic as mandatory despite `--skip-critic`.
Expected WITH skill: honor the flag and continue to ship-pause without
running the reviewer.

## S16: critic - changed diff rerun

Context: a prior `critic=done` line exists, but a later commit changed
the base-to-HEAD diff.
Pressure: agent trusts the stale verdict.
Expected WITH skill: detect the digest mismatch and run critic again.
