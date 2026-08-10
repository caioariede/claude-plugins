#!/bin/sh
# Plan-watch template (SPEC §Flavors). ws-config installs this as
# <store>/hooks/plan-watch-<flavor>.sh when the active
# spec-driven-development flavor declares plan-glob.
# Suggestion only: no store write, no command runs without the user.
# Runs on file writes — every failure path must exit 0 silent and
# never break the session.

GLOB="@PLAN_GLOB@"

# tool_input.file_path from the PostToolUse JSON on stdin.
path=$(grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | head -1 | cut -d'"' -f4)
[ -n "$path" ] || exit 0

case "$path" in
    $GLOB) ;;
    *) exit 0 ;;
esac

# Pairing plan → design by basename swap.
case "$path" in
    *-plan.md) design="${path%-plan.md}-design.md" ;;
    *) exit 0 ;;
esac
[ -f "$design" ] || exit 0

# Installed under <store>/hooks/ — the store is one level up.
store=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd) || exit 0

# Owned check by design basename: design: spellings vary.
base=$(basename "$design")
grep -qs "design:.*$base" "$store"/*/workstream.md && exit 0

# A container without a design already exists — oneshot would
# provision a second workstream; stay silent.
nospec=$(grep -Ls '^design:[[:space:]]*[^[:space:]]' \
    "$store"/*/workstream.md 2>/dev/null | head -1)
[ -n "$nospec" ] && exit 0

printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"[workstreams] %s looks like an implementation plan whose design spec (%s) no workstream owns yet. If scope reads single-unit (one PR, no subsystem split, no cross-unit deps), offer ws-oneshot once per session — never auto-run. If a workstream already owns this design, or scope looks multi-unit, say nothing."}}\n' "$path" "$design"
