---
name: ws-init
description: Use when the user needs a new workstream and none exists yet — before starting any unit with ws-start.
argument-hint: "[workstream name]"
metadata:
  version: "0.5.0"
  author: Caio Ariede
---

# ws-init — create a workstream

**Required first:** load the `ws` skill — it is the shared contract (SPEC) this skill references throughout.

**Input:** `$ARGUMENTS` = the workstream name (e.g. `task templates`).

## Steps
1. Compute the `ws-id` per SPEC (IDs & conventions), applying its `-N` collision suffix if the store dir already exists.
2. Create `<store>/<ws-id>/workstream.md` (store root: SPEC) in the SPEC metadata format. Set `goal` to a one-line restatement of the name; ask the user for the goal only if `$ARGUMENTS` is empty or a single word. Set `design:` to an umbrella spec path only if one exists.
3. Create the empty ledger `units.md` (header line only), the `units/` directory, empty `spikes.md` (header line only), the `spikes/` directory, `backlog.md` with both headings present and empty, and `focus.md` with a `## Focus` header only.
4. Report the `id`. Offer `ws-focus` now (§Next-step chaining — store-only). Do not collect the outcome here; `ws-focus` owns the prompt and `add`. On decline, stop — do not offer `ws-next`.

**Never decompose the design here.** Reading `design:` to invent units — writing them to `## Planned units`, or creating `units/<slug>/` — is out of scope: `ws-start` is the sole creator of units (SPEC Invariants) and `backlog.md` is written via `ws-backlog` (SPEC Source of truth). The design stays the live source of the breakdown, so a snapshot written here would only be a staler second copy. This skill sets up the container and nothing else.
