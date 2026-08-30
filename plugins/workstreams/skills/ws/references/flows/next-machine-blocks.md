# ws-next Machine Blocks Reference

Reference of machine-readable data blocks emitted by `next.py` for consumption by the `ws-next` skill (stripped before relaying to the user).

## Blocks Overview

| Block Header | Emitted When | Description / Format |
|---|---|---|
| `run=<command>` | Suffix on each runnable move line | Fully resolved execution command for the move. |
| `branch=<branch>` | Suffix on move line (when unit has worktree) | Target branch associated with the unit. |
| `Proposable:` | Strategy lanes exist (suggest or non-restack moves) | Follow-up candidates (`WF<n>` or `<slug>:F<n>`) open for proposal. |
| `Covered:` | Follow-up / design proposal active | Ledger slugs, titles, and planned units already accounted for in the store. |
| `Design:` | Spec-driven workstream with design path | Path to umbrella design spec from `workstream.md`. |
| `ActiveFocus:` | Focus queue is non-empty and has an active item | The active focus item (`<slug> — <outcome>`). |
| `FocusQueue:` | Queued focuses exist | Pending focus items following the active one. |
| `Stackable:` | Focus / design proposal with active in-flight units | Eligible base units for stacking proposals (`<slug> repo=<o/r> branch=<b> [readiness=...]`). |
| `ProposeSummary:` | Proposal lanes available | Informational summary of composable proposal lanes. |
| `ReconcileCandidates:` | Ship evidence found on default branch | Units that must be reconciled via `ws-resume <slug>` before proposing new work. |

## Consumption Rules

1. **Strip Before Display**: Never output raw machine blocks to the user.
2. **Deterministic Derivation**: Use `Stackable:` to validate `--base` candidates and ensure same-repo constraints.
3. **Reconcile Gating**: When `ReconcileCandidates:` is emitted, hard-gate `Propose a unit` until candidates are cleared.
