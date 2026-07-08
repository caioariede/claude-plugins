---
name: ws-config
description: Use to view or change workstream flavors — which external tool backs each behavior group (worktree-management, spec-driven-development, forge). Show the active selection, set a flavor, point at an overrides file, or scaffold a custom flavor.
---

# ws-config — configure flavors

Read the shared contract first: `${CLAUDE_PLUGIN_ROOT}/ws-shared/SPEC.md` — §Flavors defines the groups, operations, file layers, and resolution this skill edits.

**Input:** `$ARGUMENTS`:
- *(none)* / `show`
- `set <group> <flavor>`
- `set-overrides <path>`
- `list [group]`
- `add <group> <flavor>`

Store file: `~/.claude/workstreams/flavors.ini`. Built-in defs (read-only): `${CLAUDE_PLUGIN_ROOT}/ws-shared/flavors.ini`.

## show (default)
Print the effective `[active]` per group — store `[active]` if set, else the default (`worktree-management`=`git-worktree`, `spec-driven-development`=`none`, `forge`=`gh`) — and which layers are in play: built-in (always), store (if the file exists), overrides (if `[config] overrides-file` is set; mark it unreadable if the path is missing).

## set <group> <flavor>
Validate `<group>` is one of the three and `[<group>/<flavor>]` is defined in some layer (built-in / store / overrides). Reject an unknown flavor, listing the known ones for that group. Then write/update `[active]` `<group> = <flavor>` in the store file, creating the file and `[active]` section if absent. Confirm the new value.

## set-overrides <path>
Write `overrides-file = <path>` under `[config]` in the store file (create as needed). Warn if `<path>` does not exist yet — allowed; it may be created later. Confirm.

## list [group]
List the flavors per group (built-in + store + overrides) with each flavor's operations resolved per SPEC §Flavors. With a `<group>` argument, list only that group.

## add <group> <flavor>
Scaffold a `[<group>/<flavor>]` section stub in the store file with the group's operation keys (per SPEC §Flavors) left empty, for the user to fill. Do not activate it — tell the user to run `ws-config set <group> <flavor>` when ready.

## Scope
Edits touch only `~/.claude/workstreams/flavors.ini` — never a worktree, never the built-in defs. Everything here is config; nothing derives from git/GitHub.
