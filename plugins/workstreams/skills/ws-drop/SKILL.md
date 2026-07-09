---
name: ws-drop
description: >-
  Use when the user wants to abandon or tear down a workstream unit whose work
  is NOT being kept — remove its worktree + local branch and log it dropped.
  Do NOT reach for this to "clean up" a unit that is already done or merged:
  dropping logs abandonment and mislabels shipped work — a completed unit's
  worktree is just removed via the active worktree-management flavor's remove,
  no drop. Trigger on "drop/abandon this unit", "kill this worktree", "give up
  on X" — but confirm the unit isn't already merged first.
argument-hint: "[unit-id]"
---

# ws-drop — drop (abandon) a unit

**Required first:** load the `ws` skill — it is the shared contract (SPEC) this skill references throughout.

**Input:** `$ARGUMENTS` = `<unit-id>`.

`ws-drop` **abandons** a unit — its work is not being kept. It appends a `dropped` line, and that line is what makes the unit derive to `dropped` status (SPEC, first-match-wins). So this is the wrong tool for a *finished* unit: a merged unit that gets dropped reads as abandoned on the board even though it shipped. Removing a worktree and dropping a unit are different things — the first is cheap, code-only cleanup (the work lives on in its branch / `main`); the second records that the work was thrown away.

## Steps
1. **Guard — is the unit already done?** Derive its status (SPEC). If the work is **merged** (its PR merged, or it was fast-forwarded into its base / `main`), do **not** drop it. It shipped; appending a `dropped` line would mislabel it as abandoned and hide it from the "done" tally. A completed unit's worktree is simply disposable — tear it down via the active `worktree-management` flavor's `remove` (no `dropped` log; the ledger line + `progress.md` stay as the shipped record). Explain this and stop. Proceed past this step only when the work is genuinely being **abandoned** — unmerged and unwanted.
2. Resolve the unit via the SPEC bare-slug resolver → `branch`, worktree path, `repo`, and any open PR. **Show exactly what will be removed** (worktree path, local branch, whether a PR/remote branch exists) and require explicit confirmation.
3. Tear down the worktree via the active `worktree-management` flavor's `remove` (SPEC §Flavors). Then delete the **local** branch. Do **not** delete the remote branch or close the PR unless the user asks.
4. Append a `dropped <reason>` log line per SPEC File formats. **Keep** `progress.md` and the ledger line — they are the reconciliation record. The unit's **deferred** follow-ups already live in `backlog.md` and survive the drop; its in-flight `progress.md` follow-ups go dormant with it.

Restart = run `ws-start` with the same intent; it versions the id and records `restart-of` per SPEC.
