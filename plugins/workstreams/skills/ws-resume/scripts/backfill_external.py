#!/usr/bin/env python3
"""ws-resume backfill_external — confirm-only store backfill.

Usage: backfill_external.py [unit-id]

Prints one line:
  backfilled T1,T2,...
  already-consistent
  already-has-tasks
  refused <reason>

Exit 0 on success paths; 2 when the caller must pick.
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
    if not S.store_split_eligible(unit):
        print("refused not-eligible")
        return 0
    plan_str = S.plan_log_path(unit)
    if not plan_str:
        print("refused no-plan")
        return 0
    pr_state = C.gather_pr_state(ws, store, branches={unit.branch})
    pr = pr_state.get(unit.branch) if unit.branch else None
    if pr is None:
        print("refused unknown-pr")
        return 0
    if pr.state != "OPEN":
        print("already-consistent")
        return 0
    wt = (C.locate_worktree(store, unit.branch, unit.repo)
          if unit.branch and unit.repo else None)
    sha = C.head_sha(wt) if wt else ""
    status, ids = S.apply_external_backfill(
        store / ws_id, slug, Path(plan_str), pr, head_sha=sha)
    if status == "backfilled":
        print(f"backfilled {','.join(ids)}")
    elif status == "already-has-tasks":
        print("already-has-tasks")
    elif status.startswith("refused"):
        print(status)
    else:
        print(f"refused {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
