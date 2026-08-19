#!/usr/bin/env python3
"""ws-resume prepare_external — plan-pause option 4 store prep.

Usage: prepare_external.py [unit-id]

Derives unchecked T1.. from the plan log path and appends
execute-mode=external. Does not run flavor execute.

Prints: prepared T1,T2,... | already-has-tasks | refused <reason>
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
    plan_str = S.plan_log_path(unit)
    if not plan_str:
        print("refused no-plan")
        return 0
    status, ids = S.apply_external_execute_mode(
        store / ws_id, slug, Path(plan_str))
    if status == "prepared":
        print(f"prepared {','.join(ids)}")
    elif status == "already-has-tasks":
        print("already-has-tasks")
    else:
        print(status if status.startswith("refused") else f"refused {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
