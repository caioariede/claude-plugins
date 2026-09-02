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
metadata:
  version: "0.6.4"
  author: Caio Ariede
---

# ws-drop — drop (abandon) a unit

**Required first:** load the `ws` skill.

**Input:** `$ARGUMENTS` = `<unit-id>` or `<spike-id>` (bare slug).

`ws-drop` **abandons** a unit or spike — its work is not being kept. It appends a `dropped` line, and that line is what makes the unit derive to `dropped` status (SPEC §Source of truth, first-match-wins). So this is the wrong tool for a *finished* unit: a `complete` unit that gets dropped reads as abandoned on the board even though it shipped. Removing a worktree and dropping a unit are different things — the first is cheap, code-only cleanup (the work lives on in its branch / `main`); the second records that the work was thrown away.

## Steps
1. **Guard — is the target already done?** Resolve `(ws_id, slug, kind)` via SPEC §IDs & conventions (bare-slug resolver). **Unit:** derive status (SPEC §Source of truth). If **complete**, do **not** drop — explain and stop. **Spike:** if status is **complete**, do **not** drop — delivered research would leave Done (same guard). Proceed only when the work is genuinely being **abandoned**.
2. Resolve the target. **Units:** `branch`, worktree path, `repo`, open PR. **Spikes:** store dir only — no worktree. **Show exactly what will be removed** and require explicit confirmation. **Dependents check:** scan units **and spikes** whose `progress.md` `## Needs` target this slug; scan `backlog.md` planned `needs=`; scan ledger units whose implicit base is this unit (`stacked-on=`, `created base=`). Warn and list dependents; require confirmation.
3. **Units only:** tear down the worktree via the active `worktree-management` flavor's `remove` (SPEC §Flavors). Then delete the **local** branch. Do **not** delete the remote branch or close the PR unless the user asks. **Spikes:** skip worktree/branch teardown.
4. Append a `dropped <reason>` log line per SPEC §File formats. **Keep** `progress.md` and the ledger line. Unit deferred follow-ups survive in `backlog.md`; spike has no follow-ups. Dropping does **not** release blocked dependents — they show `(dropped)`.

Restart = run `ws-start` with the same intent; it versions the id and records `restart-of` per SPEC §IDs & conventions.
