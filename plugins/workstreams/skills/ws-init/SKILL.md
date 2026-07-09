---
name: ws-init
description: Use when the user needs a new workstream and none exists yet — before starting any unit with ws-start.
argument-hint: [workstream name]
---

# ws-init — create a workstream

**Required first:** load the `ws` skill — it is the shared contract (SPEC) this skill references throughout.

**Input:** `$ARGUMENTS` = the workstream name (e.g. `task templates`).

## Steps
1. Compute the `ws-id` per SPEC (IDs & conventions), applying its `-N` collision suffix if the store dir already exists.
2. Create `<store>/<ws-id>/workstream.md` (store root: SPEC) in the SPEC metadata format. Set `goal` to a one-line restatement of the name; ask the user for the goal only if `$ARGUMENTS` is empty or a single word. Set `design:` to an umbrella spec path only if one exists.
3. Create the empty ledger `units.md` (header line only), the `units/` directory, and `backlog.md`. If `design:` names a spec, offer to seed `backlog.md` `## Planned units` from it — one line per intended unit with its `base=` — else leave both sections empty.
4. Report the `id`. Offer to run `ws-next` now (default yes) to surface the first unit to start (SPEC Next-step chaining).

Do not create any unit or worktree here — this only sets up the container.
