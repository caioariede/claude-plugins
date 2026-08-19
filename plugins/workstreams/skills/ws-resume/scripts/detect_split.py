#!/usr/bin/env python3
"""ws-resume detect_split — read-only store/git drift check.

Usage: detect_split.py [unit-id]

Prints one line:
  no-split
  split pr=#N commits=N
  unknown-pr

Exit 0 always (skill interprets output).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402


def _store() -> Path:
    env = os.environ.get("WS_STORE")
    return Path(env) if env else S.store_root()


def detect(unit: S.Unit, ws: S.Workstream, store: Path) -> str:
    if not S.store_split_eligible(unit):
        return "no-split"
    if C.active_flavor(store, "spec-driven-development")[0] == "none":
        return "no-split"
    if not unit.branch or not unit.repo:
        return "no-split"
    pr_state = C.gather_pr_state(ws, store, branches={unit.branch})
    pr = pr_state.get(unit.branch)
    if pr is None:
        return "unknown-pr"
    if pr.state != "OPEN":
        return "no-split"
    wt = C.locate_worktree(store, unit.branch, unit.repo)
    if wt is None:
        return "no-split"
    base = S.recorded_base(unit)
    if not base:
        return "no-split"
    commits = C.commits_ahead(wt, base)
    if commits is None or commits <= 0:
        return "no-split"
    n = pr.number if pr.number is not None else "?"
    return f"split pr=#{n} commits={commits}"


def main(argv: List[str]) -> int:
    store = _store()
    try:
        ws_id, slug = C.resolve_args(store, argv)
    except C.Pick as p:
        print(str(p), file=sys.stderr)
        return 2
    if slug is None:
        print("NO_UNIT unit required", file=sys.stderr)
        return 2
    ws = S.load_workstream(store / ws_id)
    unit = next((u for u in ws.units if u.slug == slug), None)
    if unit is None:
        print(f"NO_MATCH no unit {slug!r} in {ws_id}", file=sys.stderr)
        return 2
    print(detect(unit, ws, store))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
