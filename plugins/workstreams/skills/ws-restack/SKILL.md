---
name: ws-restack
description: Use when a unit's base PR merged and its branch must move onto a new base, or when GitHub auto-retargeted a dependent PR and the local branch needs realigning.
---

# ws-restack — restack a unit

Read the shared contract first: `~/.claude/skills/ws-shared/SPEC.md`.

**Input:** `$ARGUMENTS` = `<unit-id> [<new-base>]` (new-base = a branch or another unit-id).

## Steps
1. Resolve `unit-id` → `branch`, worktree, `repo`, current PR.
2. Resolve `<new-base>`: if **omitted**, use the PR's live `baseRefName` (the GitHub auto-retarget case — the base a merged parent left behind); if it matches a roster unit-id, use that unit's branch; else treat it as a branch. Error only if none resolves.
3. Reconcile per SPEC Restack reconciliation. When *we* initiate (the PR's `baseRefName` is unchanged remotely), also run `gh pr edit <pr> --base <new-base>` first. On conflicts, stop and report.

Auto case (GitHub already retargeted): skip the `gh pr edit` — see SPEC Restack reconciliation.
