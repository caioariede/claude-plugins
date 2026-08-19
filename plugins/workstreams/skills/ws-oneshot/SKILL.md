---
name: ws-oneshot
description: Use when approved spec/plan scope looks like a single unit, no workstream exists yet, and the user confirmed the oneshot offer — not for multi-unit workstreams or when a workstream already owns the design.
argument-hint: '"<workstream name>" ["<unit purpose>"] [--design <spec-path>]'
metadata:
  version: "0.2.0"
  author: Caio Ariede
---

# ws-oneshot — single-unit workstream entry

**Required first:** load the `ws` skill — the shared contract (SPEC) this skill references throughout.

Shorthand for confirmed single-unit entry: `ws-init` → `ws-start` →
`ws-resume` in one chain. Never invoke without user confirmation —
agent judgment only **offer** this skill.

**Input:** `$ARGUMENTS` = `"<workstream name>" ["<unit purpose>"]` with
optional `--design <absolute-spec-path>` when the design path is not
already in session context.

## Scope check (before offering — agent-side)

Offer only when **all** hold:
- No workstream's `design:` claims this spec basename.
- Spec/plan did not split into independent subsystems.
- One PR boundary — no Phase 2 / follow-up unit in plan header.
- No `needs=` on work that does not exist yet.

Dismissal or multi-unit signals → use `ws-init` at spec time instead.

## Steps

1. **ws-init** — pass workstream name; set `design:` from `--design` or
   the approved spec path. **Do not** offer `ws-focus` — oneshot owns
   the chain.
2. **ws-start** — `<ws-id> "<unit purpose>"`; omit purpose → use plan
   goal line or spec one-liner.
   Do not assume a plan file exists before this chain. First `ws-resume`
   runs `writing-plans` and saves to `<design-dir>/<slug>-plan.md` unless
   that slug path already exists from a prior partial run.
3. **ws-resume** — run immediately; suppress intermediate opt-in
   handoffs from steps 1–2. **Stop at `plan-pause`** (superpowers) or
   the execute entry (`none` flavor). Do not skip execute-mode choice.

After `plan-pause`: normal `ws-resume` behavior — no special oneshot
rules. Option **4** (execute outside ws-resume) or drift backfill on
return apply the same as any session. Scope growth → `ws-backlog`
during work, `ws-next` after ship.

## Chain

At `plan-pause`, offer execute-mode choice per ws-resume. Do not offer
`ws-next` until the unit reaches `done`.
