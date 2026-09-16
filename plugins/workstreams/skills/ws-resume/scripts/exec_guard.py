#!/usr/bin/env python3
"""Pre-flight guard for external executors on a ledger unit.

Usage: exec_guard.py [target-id]

Prints one line:
  ok:<phase>           — safe to confirm and implement
  abort:drifted        — run ws-restack / ws-resume first
  abort:blocked        — unmet needs
  abort:<phase>        — plan, prewalk, critic, etc.
Exit 2 when the caller must pick.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Set

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402
import extension_runner as ER  # noqa: E402

_OK_PHASES: Set[str] = {"loop", "plan-pause", "done"}


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
    ws = S.load_workstream(store / ws_id)
    S.apply_pr_state(ws, C.gather_pr_state(ws, store))
    unit = next((u for u in ws.units if u.slug == slug), None)
    if unit is None:
        print(f"NO_MATCH no unit {slug!r} in {ws_id}", file=sys.stderr)
        return 2
    if S.unit_drifted(unit):
        print("abort:drifted")
        return 0
    by_slug = {u.slug: u for u in ws.units}
    ctx = C.build_extension_ctx(store, unit, headless=False)
    pending = lambda slot: ER.pending_for_slot(slot, ctx, store, kind="unit")
    phase = S.resume_phase(unit, ws, by_slug, extension_pending=pending)
    if phase == "blocked":
        print("abort:blocked")
    elif phase in _OK_PHASES:
        print(f"ok:{phase}")
    else:
        print(f"abort:{phase}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
