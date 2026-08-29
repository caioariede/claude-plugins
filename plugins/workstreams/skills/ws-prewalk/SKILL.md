---
name: ws-prewalk
description: Run read-only codebase exploration for a workstream unit after planning and before execute-mode selection. Invoked by ws-resume when spec-driven-development/superpowers-prewalk is active.
metadata:
  version: "0.1.2"
  author: Caio Ariede
---

# ws-prewalk — read-only unit exploration

**Required first:** load the `ws` skill. Parent session only — never invoke `/ws-resume` from a subagent.

## When this runs

After a unit plan is saved (`plan` log line exists) and before plan-pause execute-mode selection, when the active flavor has `prewalk = on` (typically `superpowers-prewalk`).

## Steps

1. Read unit `charter.md`, design spec, and plan file (`log.md` `plan` line path).
2. Compute plan digest: sha256 of plan file, first 8 hex chars.
3. Dispatch a **read-only explore subagent** scoped to the plan.
   - Allowed: Read, Grep, Glob (read-only).
   - Forbidden: Write, Edit, Bash that mutates repo or store.
4. Subagent returns: file map, symbols/patterns, plan-vs-code deltas, open questions.
5. **On replan-recommended:** append `note prewalk: replan recommended — <reason>`; hard stop (no `prewalk=done`).
6. **On success:**
   - Write `units/<slug>/prewalk.md` (max ~200 lines; paths and symbols, not secrets).
   - Optionally append `## Exploration Findings` on the plan file when needed.
   - Append `decision prewalk=done plan=<abs-path> digest=<8-hex>` to `log.md`.
7. Hard stop. Print:

```
PREWALK READY
Exploration: <prewalk.md path>

Switch to your cheap model, then re-run /ws-resume <unit>.
Recommended: <format_cheap_handoff from ws_cli, or ws-config show if unset>
```

Use `ws_cli.format_cheap_handoff(store)` — flavor handoff template with `{cheap}` from `[config]`.

## Read-only advisory

Exploration is skill-enforced read-only, not engine-enforced. The parent session must not edit source during prewalk.
