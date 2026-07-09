---
name: ws-restack
description: Use when a unit's base PR merged and its branch must move onto a new base, or when GitHub auto-retargeted a dependent PR and the local branch needs realigning.
argument-hint: [unit-id] [new-base]
---

# ws-restack — restack a unit

Read the shared contract first: `${CLAUDE_PLUGIN_ROOT}/ws-shared/SPEC.md`.

**Input:** `$ARGUMENTS` = `<unit-id> [<new-base>]` (new-base = a branch or another unit-id).

## Steps
1. Resolve the unit via the SPEC bare-slug resolver → `branch`, worktree, `repo`, current PR. Runs from any session: operate on the worktree via `git -C <worktree>` (SPEC "Command scope") — do not move the current session.
2. Resolve `<new-base>`: if **omitted**, use the PR's live base from the active `forge` flavor's `pr-status` (the GitHub auto-retarget case — the base a merged parent left behind); if it matches a ledger unit-id, use that unit's branch; else treat it as a branch. Error only if none resolves.
3. Reconcile per SPEC Restack reconciliation. When *we* initiate (the PR's base is unchanged remotely), also run the active `forge` flavor's `pr-retarget` first. On conflicts, stop and report.

Auto case (GitHub already retargeted): skip the `pr-retarget` — see SPEC Restack reconciliation.
