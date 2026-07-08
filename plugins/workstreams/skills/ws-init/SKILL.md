---
name: ws-init
description: Use when the user needs a new workstream and none exists yet — before starting any unit with ws-start.
---

# ws-init — create a workstream

Read the shared contract first: `${CLAUDE_PLUGIN_ROOT}/ws-shared/SPEC.md`.

**Input:** `$ARGUMENTS` = the workstream name (e.g. `task templates`).

## Steps
1. Compute the `ws-id` per SPEC (IDs & conventions), applying its `-N` collision suffix if the store dir already exists.
2. Create `~/.claude/workstreams/<ws-id>/workstream.md` in the SPEC metadata format. Set `goal` to a one-line restatement of the name; ask the user for the goal only if `$ARGUMENTS` is empty or a single word. Set `design:` to an umbrella spec path only if one exists.
3. Create the empty roster `units.md` (header line only), the `units/` directory, and `backlog.md`. If `design:` names a spec, offer to seed `backlog.md` `## Planned units` from it — one line per intended unit with its `base=` — else leave both sections empty.
4. Report the `id` and that you're in the **hub** (orchestration only). Next (hub→hub): offer to run `ws-next` now (default yes) to surface the first unit to start (SPEC Next-step chaining).

Do not create any unit or worktree here — this only sets up the container.
