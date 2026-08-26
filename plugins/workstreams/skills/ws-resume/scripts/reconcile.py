#!/usr/bin/env python3
"""ws-resume reconcile — merged terminal + task reconcile.

Usage: reconcile.py [unit-id]

Exit 0 when nothing to do or reconcile succeeded.
Exit 2 when the caller must pick (same tokens as ws-board).
Prints one line:
  reconciled <task-ids> | already-consistent | not-merged
  unknown-forge | unknown-git
  ship-detect-candidate branch=... sha=... [pr=...]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402


def _store() -> Path:
    env = os.environ.get("WS_STORE")
    return Path(env) if env else S.store_root()


def _reconcile_line(ws_dir: Path, slug: str, pr: Optional[S.PR], *,
                    merged_via: Optional[S.MergedVia] = None) -> str:
    ids = S.maybe_reconcile_merged_unit(
        ws_dir, slug, pr, merged_via=merged_via)
    if ids:
        return f"reconciled {','.join(ids)}"
    return "already-consistent"


def main(argv: List[str]) -> int:
    store = _store()
    try:
        ws_id, slug = C.resolve_args(store, argv)
    except C.Pick as p:
        print(str(p), file=sys.stderr)
        return 2
    ws = S.load_workstream(store / ws_id)
    unit = next((u for u in ws.units if u.slug == slug), None)
    if unit is None:
        print(f"NO_MATCH no unit {slug!r} in {ws_id}", file=sys.stderr)
        return 2
    ws_dir = store / ws_id
    pr_state = C.gather_pr_state(ws, store, branches={unit.branch})
    pr = pr_state.get(unit.branch)
    unit.pr = pr

    if S.is_merged(unit):
        print(_reconcile_line(ws_dir, slug, pr))
        return 0

    result = C.detect_shipped_elsewhere(
        unit, ws, store, pr_state=pr_state)
    if result.outcome in ("unknown-forge", "unknown-git"):
        print(result.outcome)
        return 0
    if result.outcome == "dismissed":
        print("dismissed")
        return 0
    if result.outcome == "tier-a" and result.record:
        S.append_merged_via(ws_dir, slug, result.record)
        print(_reconcile_line(ws_dir, slug, pr, merged_via=result.record))
        return 0
    if result.outcome == "tier-b" and result.record:
        rec = result.record
        line = f"ship-detect-candidate {S.format_merged_via_payload(rec)}"
        print(line)
        return 0

    print("not-merged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
