#!/bin/sh
# Spec-watch template (SPEC §Flavors, Spec-watch). ws-config
# installs this as <store>/hooks/spec-watch-<flavor>.sh when
# the active spec-driven-development flavor declares a
# spec-glob, baking the glob into GLOB below; the installed
# copy is the runtime flag the hooks.json wiring checks.
# Suggestion only: no store write, no command runs without
# the user. Runs on file writes — every failure path must
# exit 0 silent and never break the session.

GLOB="@SPEC_GLOB@"

# tool_input.file_path from the PostToolUse JSON on stdin.
path=$(grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | head -1 | cut -d'"' -f4)
[ -n "$path" ] || exit 0

case "$path" in
    $GLOB) ;;
    *) exit 0 ;;
esac

# Installed under <store>/hooks/ — the store is one level up.
store=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd) || exit 0

# Owned check by basename: design: spellings vary (~ vs
# absolute vs symlinked); the dated filename does not.
base=$(basename "$path")
grep -qs "design:.*$base" "$store"/*/workstream.md && exit 0

# A workstream still missing a design is a likelier home for
# this spec than a brand-new workstream — surface the first.
extra=""
nospec=$(grep -Ls '^design:[[:space:]]*[^[:space:]]' \
    "$store"/*/workstream.md 2>/dev/null | head -1)
if [ -n "$nospec" ]; then
    wsid=$(basename "$(dirname "$nospec")")
    extra=" Workstream '$wsid' has no design yet; attaching this spec to it may fit better than a new workstream."
fi

printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"[workstreams] %s looks like a design spec no workstream owns (no workstream.md design: mentions it). If this design implies multiple units/PRs, offer - once the user has reviewed the spec - to run ws-init with it as the design; ws-init only creates the workstream container, planning and execution still follow the active flavor.%s If it is single-PR work, or you already offered this session, say nothing."}}\n' "$path" "$extra"
