---
name: ws-config
description: Use to view or change workstream flavors — which external tool backs each behavior group (worktree-management, spec-driven-development, forge). Bare/`show` also detects which flavors' tools are installed, flags an active flavor whose tool is missing, and offers to activate detected flavors for unset groups. Set a flavor, point at an overrides file, or scaffold a custom flavor.
argument-hint: "[show | set <group> <flavor> | add <group> <flavor> | set-overrides <path> | list [group]]"
compatibility: requires python3
metadata:
  version: "0.6.0"
  author: Caio Ariede
---

# ws-config — configure flavors

**Required first:** load the `ws` skill — the shared contract (SPEC); its §Flavors defines the groups, operations, file layers, resolution, and Availability this skill works with.

Every verb runs through the bundled engine (relative to this skill's directory; `${CLAUDE_PLUGIN_ROOT}/skills/ws-config/scripts/config.py` when set):

```
python3 <this-skill-dir>/scripts/config.py [show | set <group> <flavor> | add <group> <flavor> | set-overrides <path> | list [group]]
```

No arguments = `show`. The script renders the output, performs all store writes surgically (comments in a hand-edited `flavors.ini` survive), and reconciles the spec-watch script on every run — it reports the reconcile only when something changed. Relay its output, then finish the two parts only a session can do:

## Settle `?` marks (show / list)
The script resolves every shell dep itself (`command -v`) and prints `?` where session knowledge is needed:
- `? requires skill <id> (verify in session)` — installed in this session → available; not installed → missing.
- `? unresolved head "<w>" (prose or missing tool)` — SPEC rule 4 judgment: a prose methodology instruction (the `none` flavor) carries no dep → available; otherwise the tool is missing.
Present the settled result. An **active** flavor left with a missing dep is broken — name the missing tool and the remedy (install it, or `ws-config set <group> <other-flavor>`).

## The offer (show; interactive sessions only — never a subagent/headless run)
Trailing `OFFER <group> <flavor>` lines are the candidates for groups with no explicit `[active]`. Settle `?` candidates first and drop any that settle to missing. Then, per group: one candidate → offer to set it (default yes); several → a choice including keeping the default. Combine all groups into ONE prompt — never sequential asks. Accept → `config.py set <group> <flavor>`; decline → `config.py set <group> <default>` (pins the default, so the offer never repeats); dismissed → nothing. No OFFER lines → no prompt. (Why non-default wins: defaults are the always-available baseline; installing wmx or superpowers signals intent to use it.)

## Errors
Nonzero exit with a machine-readable first stderr token: `UNKNOWN_GROUP`, `UNKNOWN_FLAVOR` (the known flavors are listed), `ALREADY_EXISTS`, `BAD_ARGS`. Relay the message and recover — fix the argument or ask the user.

## Scope
The engine touches only `<store>/flavors.ini` and `<store>/hooks/` (spec-watch reconcile) — never a worktree, never the built-in defs. Everything here is config; nothing derives from git/GitHub.
