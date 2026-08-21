#!/usr/bin/env python3
"""ws-resume record_merged_via — ship-detect gate pick 2.

Usage: record_merged_via.py <unit-id> branch=<b> sha=<s> [pr=<n>]

Appends merged-via and reconciles tasks. Idempotent per sha.
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
    if len(argv) < 2:
        raise SystemExit(
            "usage: record_merged_via.py <unit-id> branch=<b> sha=<s> "
            "[pr=<n>]")
    store = _store()
    try:
        ws_id, slug = C.resolve_args(store, [argv[0]])
    except C.Pick as p:
        print(str(p), file=sys.stderr)
        return 2
    rec = S.parse_merged_via_payload(" ".join(argv[1:]))
    if rec is None:
        raise SystemExit(
            "usage: record_merged_via.py <unit-id> branch=<b> sha=<s> "
            "[pr=<n>]")
    ws_dir = store / ws_id
    ws = S.load_workstream(ws_dir)
    unit = next((u for u in ws.units if u.slug == slug), None)
    if unit is None:
        print(f"NO_MATCH no unit {slug!r}", file=sys.stderr)
        return 2
    pr = C.gather_pr_state(ws, store, branches={unit.branch}).get(
        unit.branch)
    wrote = S.append_merged_via(ws_dir, slug, rec)
    ids = S.maybe_reconcile_merged_unit(
        ws_dir, slug, pr, merged_via=rec)
    if ids:
        print("recorded merged-via reconciled tasks")
    elif wrote:
        print("recorded merged-via")
    else:
        print("already-consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
