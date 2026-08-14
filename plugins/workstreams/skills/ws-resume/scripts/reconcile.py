#!/usr/bin/env python3
"""ws-resume reconcile — check open tasks when unit PR is merged.

Usage: reconcile.py [unit-id]

Exit 0 when nothing to do or reconcile succeeded.
Exit 2 when the caller must pick (same tokens as ws-board).
Prints one line: reconciled <task-ids> | already-consistent | not-merged
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
    ws = S.load_workstream(store / ws_id)
    by = {u.slug: u for u in ws.units}
    unit = by.get(slug)
    if unit is None:
        print(f"NO_MATCH no unit {slug!r} in {ws_id}", file=sys.stderr)
        return 2
    pr_state = C.gather_pr_state(ws, store, branches={unit.branch})
    pr = pr_state.get(unit.branch)
    if not pr or pr.state != "MERGED":
        print("not-merged")
        return 0
    ws_dir = store / ws_id
    prog_path = ws_dir / "units" / slug / "progress.md"
    try:
        raw = prog_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raw = ""
    _, open_ids = S.reconcile_tasks_on_merge(raw)
    if not open_ids:
        print("already-consistent")
        return 0
    if S.maybe_reconcile_merged_unit(ws_dir, slug, pr):
        print(f"reconciled {','.join(open_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
