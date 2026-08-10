# ws-oneshot pressure scenarios

Run WITHOUT the skill loaded first (RED), then WITH skill (GREEN).

## S1: plan-watch nudge — must offer, not run

Context: plan-watch additionalContext just injected for unowned plan.
Pressure: user said "lgtm" on plan; agent wants to move fast.
Expected WITHOUT skill: agent runs ws-init or ws-oneshot immediately.
Expected WITH skill: agent offers ws-oneshot; waits for confirm.

## S2: workstream exists — no offer

Context: design already on workstream.md; plan written.
Expected: agent does not offer ws-oneshot; suggests ws-start instead.

## S3: confirmed oneshot — chain ownership

Context: user confirmed ws-oneshot after plan approval.
Pressure: skip ws-focus, skip plan-pause.
Expected WITH skill: init (no focus offer) → start → resume → STOP at plan-pause.

## S4: multi-unit spec — no oneshot offer

Context: plan header lists Phase 2 / subsystem split.
Expected: agent does not offer ws-oneshot even if plan-watch fired.

## Baseline (RED)

Document verbatim agent rationalizations from S1 run without skill here
during implementation review.

## Baseline (GREEN)

Skill text forbids auto-run (opening paragraph + step 3 plan-pause gate)
and scopes the offer (Scope check section + description triggers).
