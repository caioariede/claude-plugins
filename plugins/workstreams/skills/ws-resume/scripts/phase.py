#!/usr/bin/env python3
"""ws-resume phase — print loop boundary for one unit or spike.

Usage: phase.py [unit-id]

Prints one line: blocked | plan | plan-pause | loop | ship-pause |
draft-pr | done  (unit)
  or blocked | plan | plan-pause | loop | done  (spike)
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


def _resolve_target(store: Path, args: List[str]) -> C.ResolvedTarget:
    ws_id, slug = C.resolve_args(store, args)
    if not slug:
        br = C.current_branch()
        if not br:
            raise C.Pick("NO_MATCH no unit-id and not on a ledger branch")
        hits = C.resolve_branch(store, br)
        if len(hits) != 1:
            raise C.Pick("NO_MATCH cwd branch matches no unique ledger unit")
        ws_id, slug = hits[0]
        return C.ResolvedTarget(ws_id, slug, "unit")
    kind = C.resolve_kind_in_ws(store, ws_id, slug)
    return C.ResolvedTarget(ws_id, slug, kind)


def phase_for_ws(ws: S.Workstream, slug: str, kind: str) -> str:
    by_slug = {u.slug: u for u in ws.units}
    by_spike = {s.slug: s for s in ws.spikes}
    if kind == "spike":
        sp = by_spike.get(slug)
        if sp is None:
            raise C.Pick(f"NO_MATCH no spike {slug!r} in {ws.ws_id}")
        return S.resume_spike_phase(sp, ws, by_slug, by_spike)
    unit = by_slug.get(slug)
    if unit is None:
        raise C.Pick(f"NO_MATCH no unit {slug!r} in {ws.ws_id}")
    return S.resume_phase(unit, ws, by_slug)


def generate(store: Path, ws_id: str, slug: str,
             pr_by_branch: Dict[str, Optional[S.PR]],
             kind: Optional[str] = None) -> str:
    """Pure path used by both main() and the tests."""
    ws = S.load_workstream(store / ws_id)
    S.apply_pr_state(ws, pr_by_branch)
    if kind is None:
        kind = C.resolve_kind_in_ws(store, ws_id, slug)
    return phase_for_ws(ws, slug, kind)


def main(argv: List[str]) -> int:
    store = _store()
    try:
        target = _resolve_target(store, argv)
        ws = S.load_workstream(store / target.ws_id)
        pr_state = C.gather_pr_state(ws, store)
        S.apply_pr_state(ws, pr_state)
        print(phase_for_ws(ws, target.slug, target.kind))
        return 0
    except C.Pick as p:
        print(str(p), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
