#!/usr/bin/env python3
"""Record a per-PR merge audit line in unit log.md.

Usage: record_merged.py [target-id]

Prints: recorded pr=<n> | already pr=<n> | skipped <reason>
Exit 2 when the caller must pick (NO_UNIT / NO_MATCH / Pick).
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
    unit_args = [argv[0]] if argv else []
    try:
        ws_id, slug = C.resolve_args(store, unit_args)
    except C.Pick as pick:
        print(str(pick), file=sys.stderr)
        return 2
    if slug is None:
        print("NO_UNIT target required", file=sys.stderr)
        return 2
    ws_dir = store / ws_id
    ws = S.load_workstream(ws_dir)
    S.apply_pr_state(ws, C.gather_pr_state(ws, store))
    unit = next((u for u in ws.units if u.slug == slug), None)
    if unit is None:
        print(f"NO_MATCH no unit {slug!r} in {ws_id}", file=sys.stderr)
        return 2
    n = S.merged_pr_to_record(unit)
    if n is not None:
        log_path = ws_dir / "units" / unit.slug / "log.md"
        S._append_log_line(log_path, "merged", f"pr={n}")
        print(f"recorded pr={n}")
        return 0
    pr = unit.pr
    state = S.pr_state(pr)
    if state == "MERGED" and isinstance(pr.number, int) \
            and S.merged_logged(unit, pr.number):
        print(f"already pr={pr.number}")
    elif not pr:
        print("skipped no-pr")
    elif state != "MERGED":
        print("skipped not-merged")
    else:
        print("skipped no-number")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
