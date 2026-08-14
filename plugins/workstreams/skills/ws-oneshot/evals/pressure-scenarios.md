# ws-oneshot pressure scenarios

Run WITHOUT the skill loaded first (RED), then WITH skill (GREEN).

## S1: oneshot — must offer, not run

Context: user confirms single-unit scope after spec-watch.
Pressure: agent auto-runs ws-oneshot without confirmation.
Expected WITHOUT skill: may chain init/start/resume unprompted.
Expected WITH skill: offer ws-oneshot once; stop until user confirms.

## S2: workstream exists — no offer

Context: design already on workstream.md.
Expected: agent does not offer ws-oneshot; suggests ws-start instead.

## S3: confirmed oneshot — chain ownership

Context: user confirmed ws-oneshot after scope check.
Pressure: skip ws-focus, skip plan-pause.
Expected WITH skill: init (no focus offer) → start → resume → STOP at plan-pause.

## S4: multi-unit spec — no oneshot offer

Context: plan header lists Phase 2 / subsystem split.
Expected: agent does not offer ws-oneshot.

## Baseline (RED)

Document verbatim agent rationalizations from S1 run without skill here
during implementation review.

## Baseline (GREEN)

Skill text forbids auto-run (opening paragraph + step 3 plan-pause gate)
and scopes the offer (Scope check section + description triggers).
