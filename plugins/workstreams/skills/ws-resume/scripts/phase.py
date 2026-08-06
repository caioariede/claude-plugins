#!/usr/bin/env python3
"""ws-resume phase — print loop boundary for one unit.

Usage: phase.py [unit-id]

Prints one line: blocked | loop | ship-pause | draft-pr | done
Exit 2 when the caller must pick (same tokens as ws-board).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402


def _store() -> Path:
    env = os.environ.get("WS_STORE")
    return Path(env) if env else S.store_root()


def _resolve_unit(store: Path, args: List[str]) -> tuple[str, str]:
    ws_id, slug = C.resolve_args(store, args)
    if slug:
        return ws_id, slug
    br = C.current_branch()
    if not br:
        raise C.Pick("NO_MATCH no unit-id and not on a ledger branch")
    hits = C.resolve_branch(store, br)
    if len(hits) != 1:
        raise C.Pick("NO_MATCH cwd branch matches no unique ledger unit")
    return hits[0]


def phase_for(store: Path, ws_id: str, slug: str,
              pr_by_branch: Dict[str, Optional[S.PR]]) -> str:
    ws = S.load_workstream(store / ws_id)
    S.apply_pr_state(ws, pr_by_branch)
    by = {u.slug: u for u in ws.units}
    unit = by.get(slug)
    if unit is None:
        raise C.Pick(f"NO_MATCH no unit {slug!r} in {ws_id}")
    S.derive_status(ws)
    return S.resume_phase(unit, ws, by)


def main(argv: List[str]) -> int:
    store = _store()
    try:
        ws_id, slug = _resolve_unit(store, argv)
        ws = S.load_workstream(store / ws_id)
        pr_state = C.gather_pr_state(ws, store)
        print(phase_for(store, ws_id, slug, pr_state))
        return 0
    except C.Pick as p:
        print(str(p), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
