---
name: ws-critic
description: Use after all implementation tasks are complete and before verification or finishing the development branch. Perform a fresh-context, read-only, adversarial review of the complete implementation against the approved design, requirements, and implementation plan.
metadata:
  version: "0.1.0"
  author: Caio Ariede
---

# ws-critic - post-complete adversarial review

**Required first:** load the `ws` skill. Parent session only - never
invoke `/ws-resume` from a subagent.

## When this runs

`ws-resume` invokes this skill for a unit in the `critic` phase,
after all implementation tasks are complete and before `ship-pause`.
The review is advisory and additive to superpowers reviews.

## Review context

Do not rely on the implementation conversation or implementer's
reasoning. Read:

1. The unit `charter.md` and its `design:` spec, when present.
2. The plan file from the unit `log.md`, when present.
3. The complete diff from the unit's recorded base to `HEAD`.
4. Relevant surrounding code and tests.

With the `none` planning flavor, review the charter, task checklist,
diff, and relevant tests when no plan file exists. Note missing
context in the report; do not skip the review.

## Procedure

1. Compute the tree digest in the unit worktree:
   `sha256(git diff {base}...HEAD stdout)[:8]`, where `{base}` is
   the unit's recorded base branch (default `main`). Run git in the
   worktree located by the active worktree-management flavor, not the
   process cwd. This must match `phase.py` so `critic=done` binds.
2. Dispatch one fresh read-only reviewer subagent.
3. Give it the charter, design, plan, complete diff, and relevant
   code and tests.
4. Require the output format below.
5. Write the returned report to `units/<slug>/critic.md`.
6. Append:

```
- <ts>  decision  critic=done verdict=<READY|READY_WITH_MINOR_NOTES|NOT_READY> digest=<8-hex>
```

7. Stop and let `ws-resume` continue to `ship-pause`.

The parent session owns store writes. The reviewer must not edit source,
tests, the workstream store, or the working tree.

## Reviewer prompt

Review the completed implementation as an independent senior engineer.
Try to disprove that it is ready to ship. Do not improve code generally.
Find concrete reasons not to ship.

Check requirements, correctness, architecture, tests, error paths,
security, performance, regressions, and scope. Do not manufacture
issues or report subjective preferences.

### Blocking

For each Critical or Important issue, report:

- severity
- file and line
- problem
- why it matters
- expected behavior or suggested direction

### Non-blocking

Include only useful Minor issues.

### Missing Requirements

List design or plan requirements not implemented.

### Verdict

Choose exactly one:

- READY
- READY WITH MINOR NOTES
- NOT READY

`NOT READY` is advisory. Ship-pause still lets the user decide whether
to fix findings, skip review, or ship.

## Digest and reruns

The decision binds to the tree digest for the current base-to-`HEAD`
diff. A later commit changes the digest and causes another review.
Do not edit implementation files after the review. If fixes are made,
run `/ws-resume` again so the new diff receives a fresh review.
