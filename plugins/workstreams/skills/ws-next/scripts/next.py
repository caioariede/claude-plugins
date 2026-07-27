#!/usr/bin/env python3
"""ws-next — recommend the next workstream action, deterministically.

Resolves the workstream + PR state via ws_cli, ranks every runnable move
in the shared engine (ws_store.decide_next), and prints them in rank
order with the first marked default. Ordinals are deliberately absent:
the skill's picker owns the numbers on screen. The skill relays this and
drives the interactive Chain (unit pick, then the flavor hook); the
script only decides.

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


# Display verbs for the four move rules; the ws-* command itself rides
# the machine tail, which the skill strips before showing the list.
_VERB = {"restack": "restack", "ship": "ship it",
         "resume": "advance", "start": "start"}


def render_decision(d: S.Decision) -> str:
    lines = []
    if d.headline:
        lines.append(d.headline)
    for i, m in enumerate(d.moves):
        mark = "   [default]" if i == 0 else ""
        tail = f"   run={m.command}"
        if m.branch:
            tail += f"   branch={m.branch}"
        lines.append(f"  {m.unit} — {_VERB[m.rule]}: {m.why}{mark}{tail}")
    if d.command and not d.moves:
        bits = [f"unit: {d.unit}"] if d.unit else []
        if d.branch:
            bits.append(f"branch: {d.branch}")
        tail = f"   ({', '.join(bits)})" if bits else ""
        lines.append(f"Next: {d.command}{tail}")
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
