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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402
from chain_summary import chain_offers_propose, propose_source_summary  # noqa: E402


# Display verbs for the four move rules; the ws-* command itself rides
# the machine tail, which the skill strips before showing the list.
_VERB = {"restack": "restack", "ship": "ship it", "resume": "advance"}


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
    for w in d.waiting:
        lines.append(f"Waiting: {w}")
    if d.open_items:
        lines.append("Open backlog:")
        lines += [f"- {it}" for it in d.open_items]
    # `suggest` material — for the assistant composing the proposal, not
    # for the user; the skill consumes these blocks instead of relaying
    # them, the same way it strips each move's run= tail.
    if d.proposable:
        lines.append("Proposable:")
        for p in d.proposable:
            # A unit-scoped id already carries its origin as the prefix.
            origin = ("" if p.fid.startswith(f"{p.origin}:")
                      else f"  from={p.origin}")
            blocks = f"  blocks={','.join(p.blocks)}" if p.blocks else ""
            lines.append(f"- {p.fid}{origin}{blocks}  {p.desc}")
    if d.covered:
        lines.append("Covered:")
        lines += [f"- {c}" for c in d.covered]
    if d.design:
        lines.append(f"Design: {d.design}")
    if d.active_focus:
        lines.append(f"ActiveFocus: {S.focus_item_text(d.active_focus)}")
    if d.focus_queue:
        lines.append("FocusQueue:")
        for f in d.focus_queue:
            lines.append(f"- {S.focus_item_text(f)}")
    if chain_offers_propose(d):
        summary = propose_source_summary(d)
        if summary:
            lines.append(f"ProposeSummary: {summary}")
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
