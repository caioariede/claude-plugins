---
name: ws-spike
description: >-
  Use when starting research or an audit inside a workstream before building
  a unit — store-only, no worktree or PR. Creates a spike that blocks units
  via needs= and ends by amending the umbrella design spec. Trigger on
  "spike", "audit before we build", "research first", "investigate before".
  Requires design: on the workstream. Chain to ws-resume with explicit
  spike id after creation.
argument-hint: '[ws-id] "<what to investigate>" [--slug <slug>] [--spawned-from <unit-id>] [--needs <target>]'
metadata:
  version: "0.1.2"
  author: Caio Ariede
---

# ws-spike — start a spike

**Required first:** load the `ws` skill.

**Flow reference:** see visual execution flow in `skills/ws/references/flows/diagrams/spike.mmd`.

**Input:** `$ARGUMENTS` = `<ws-id> "<what to investigate>"` with optional `--slug <slug>`, `--spawned-from <unit-id>`, and `--needs <target>[,<target>]`.
If `ws-id` is omitted and exactly one workstream exists, use it; otherwise ask which.

**Precondition:** `workstream.md` `design:` must be set and readable. Refuse creation when design is absent (`—` or empty).

## Steps
1. Resolve `ws-id` → `<store>/<ws-id>/`. Compute `slug = slug(what)` per SPEC §IDs & conventions, or take `--slug` when given. Refuse when the slug exists in `units.md`, `spikes.md`, or `backlog.md` `## Planned units`. If `spikes/<slug>/` already exists and the spike is terminal (`complete` or `dropped`) → take the next `-N` suffix and record `restart-of=<slug>` on the ledger line (mirror unit restart). If the spike is still active → confirm resume (`ws-resume`) or restart.
2. Resolve `repo=` from cwd, or from `--spawned-from` unit's ledger `repo=` when given.
3. Create `spikes/<slug>/` with `charter.md`, `progress.md`, `log.md`, and `artifacts/` per SPEC §File formats. Do not create a worktree or branch.
4. **Append** the ledger line to `spikes.md`; append `created` to spike `log.md`.
5. Seed `## Needs` from `--needs` when given — validate each target as `ws-block` does (self-need, cycle): skip bad targets with a warning.
6. **`--spawned-from` only** — copy provenance to charter frontmatter; optionally offer `ws-block <unit> needs <spike>` (user confirms).
7. The spike is provisioned — do **not** print a bootstrap prompt. Offer **`/ws-resume <spike-id>`** now (opt-out; provisioned-spike handoff, SPEC §Next-step chaining). Spike resume is store-scoped — no worktree handoff.

`ws-resume` requires an explicit spike id — zero-arg resume cannot reach a spike (SPEC §Command scope).
