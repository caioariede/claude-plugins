---
name: ws-config
description: Use to view or change workstream flavors — which external tool backs each behavior group (worktree-management, spec-driven-development, forge). Bare/`show` also detects which flavors' tools are installed, flags an active flavor whose tool is missing, and offers to activate detected flavors for unset groups. Set a flavor, point at an overrides file, or scaffold a custom flavor.
argument-hint: "[show | set <group> <flavor> | add <group> <flavor> | set-overrides <path> | list [group]]"
metadata:
  version: "0.5.0"
  author: Caio Ariede
---

# ws-config — configure flavors

**Required first:** load the `ws` skill — the shared contract (SPEC); its §Flavors defines the groups, operations, file layers, and resolution this skill edits.

**Input:** `$ARGUMENTS`:
- *(none)* / `show`
- `set <group> <flavor>`
- `set-overrides <path>`
- `list [group]`
- `add <group> <flavor>`

Store file: `<store>/flavors.ini` (store root: SPEC). Built-in defs (read-only): the `ws` skill's bundled `references/flavors.ini`.

## show (default)
Print the effective `[active]` per group — store `[active]` if set, else the default (`worktree-management`=`git-worktree`, `spec-driven-development`=`none`, `forge`=`gh`) — marking each value explicit (store/overrides `[active]`) or default, and which layers are in play: built-in (always), store (if the file exists), overrides (if `[config] overrides-file` is set; mark it unreadable if the path is missing). Also surface any `hook-*` operations the active flavors define (base, `.prompt`, `.choices`), so the user sees which lifecycle prompts are live (SPEC §Flavors).

**Detection.** Compute availability (SPEC §Flavors, Availability) for every known flavor in every layer and annotate each group's flavor list with it. An active flavor — explicit or default — with an unresolved dep is flagged broken, naming the missing tool and the remedy (install it, or `ws-config set <group> <other-flavor>`).

**Offer** *(interactive sessions only — never a subagent/headless run, same rule as SPEC flavor hooks)*. For each group with no explicit `[active]` entry: exactly one available non-default flavor → offer to set it (default yes); two or more → present a choice that includes keeping the default; none available → no offer, the default is simply in effect. Combine all unset groups into one prompt — never sequential asks. An accepted choice writes through `set` below, so validation and the spec-watch reconcile run in the same pass. **Declining pins the default**: write that group's default explicitly into `[active]`, making the choice deliberate so the offer never repeats. A dismissed prompt writes nothing. (Why non-default wins: defaults are the always-available baseline; installing wmx or superpowers signals intent to use it.)

## set <group> <flavor>
Validate `<group>` is one of the three and `[<group>/<flavor>]` is defined in some layer (built-in / store / overrides). Reject an unknown flavor, listing the known ones for that group. Then write/update `[active]` `<group> = <flavor>` in the store file, creating the file and `[active]` section if absent. Confirm the new value. If the flavor is defined but unavailable (SPEC §Flavors, Availability), warn — the tool may be installed later — and set it anyway.

## set-overrides <path>
Write `overrides-file = <path>` under `[config]` in the store file (create as needed). Warn if `<path>` does not exist yet — allowed; it may be created later. Confirm.

## list [group]
List the flavors per group (built-in + store + overrides) with each flavor's operations resolved per SPEC §Flavors — including any `hook-*` operations with their `.prompt` / `.choices.<name>.desc` companions. With a `<group>` argument, list only that group.

## add <group> <flavor>
Scaffold a `[<group>/<flavor>]` section stub in the store file with the group's operation keys (per SPEC §Flavors) left empty, for the user to fill. Do not activate it — tell the user to run `ws-config set <group> <flavor>` when ready.

## Spec-watch reconcile (every run)
After any command above, sync the installed spec-watch script to the merged INI (SPEC §Flavors, Spec-watch) — running `ws-config` is what heals a hand-edited `flavors.ini`:
1. Resolve the active `spec-driven-development` flavor and its `spec-glob`.
2. `spec-glob` defined → install/refresh `<store>/hooks/spec-watch-<flavor>.sh` from the plugin template (from this skill's directory: `../../hooks/spec-watch.sh`), substituting `@SPEC_GLOB@` with the glob, `chmod +x`. Remove any *other* `spec-watch-*.sh` there.
3. No `spec-glob` → remove every `<store>/hooks/spec-watch-*.sh`.

The end state is always: script present iff the merged declaration says so. Mention the reconcile in output only when it changed something.

## Scope
Edits touch only `<store>/flavors.ini` and `<store>/hooks/` (the spec-watch reconcile) — never a worktree, never the built-in defs. Everything here is config; nothing derives from git/GitHub.
