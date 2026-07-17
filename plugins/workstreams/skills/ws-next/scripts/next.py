#!/usr/bin/env python3
"""ws-next — recommend the next workstream action, deterministically.

Resolves the workstream + PR state via ws_cli, runs the decision table in
the shared engine (ws_store.decide_next), and prints the single next
command plus parallel/blocked context. The skill relays this and drives
the interactive Chain (flavor hook / offer to run); the script only decides.

Usage: next.py [ws-id]
Exit 2 with a machine-readable first line when the caller must pick.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402


def render_decision(d: S.Decision) -> str:
    lines = []
    if d.headline:
        lines.append(d.headline)
    if d.command:
        tail = f"   (unit: {d.unit})" if d.unit else ""
        lines.append(f"Next: {d.command}{tail}")
    if d.also:
        lines.append("Also unblocked (parallel): " + ", ".join(d.also))
    for b in d.blocked:
        lines.append(f"Blocked: {b}")
    if d.open_items:
        lines.append("Open backlog:")
        lines += [f"- {it}" for it in d.open_items]
    return "\n".join(lines)


def generate(store: Path, ws_id: str,
             pr_state: Dict[str, Optional[S.PR]]) -> str:
    """Pure path used by both main() and the tests."""
    ws = S.load_workstream(store / ws_id)
    S.apply_pr_state(ws, pr_state)
    return render_decision(S.decide_next(ws))


def main(argv: List[str]) -> int:
    store = S.store_root()
    try:
        ws_id, _unit = C.resolve_args(store, argv)
    except C.Pick as p:
        print(str(p), file=sys.stderr)
        return 2
    ws = S.load_workstream(store / ws_id)
    S.apply_pr_state(ws, C.gather_pr_state(ws, store))
    print(render_decision(S.decide_next(ws)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
