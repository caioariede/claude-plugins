#!/usr/bin/env python3
"""ws-board — render a workstream board from the store, deterministically.

Resolves args + PR state via ws_cli, derives status via the shared engine
(ws_store), and prints a terminal-ready board (or one unit's detail). The
skill runs this and relays the output.

Usage: board.py [ws-id] [unit-id]
Exit 2 with a machine-readable first line when the caller must pick
(ambiguous slug, or 0 args with multiple workstreams).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws-resume" / "scripts"))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402
import phase as P      # noqa: E402


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_board(b: S.Board) -> str:
    label = "items done" if b.has_spikes else "units done"
    head = f"*{b.name}* — {b.merged_count}/{b.total_count} {label}"
    if b.complete:
        head += " · ✅ complete"
    lines = [head, ""]

    lines.append(b.focus_line)
    lines.append("")

    if b.has_blocked:
        cols = [("⏳ Not started", b.not_started), ("⛔ Blocked", b.blocked),
                ("🔄 In progress", b.in_progress), ("✅ Done", b.done)]
    else:
        cols = [("⏳ Not started", b.not_started),
                ("🔄 In progress", b.in_progress), ("✅ Done", b.done)]

    headers = [h for h, _ in cols]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in cols) + " |")
    depth = max((len(c) for _, c in cols), default=0)
    for i in range(depth):
        row = [(c[i] if i < len(c) else "") for _, c in cols]
        lines.append("| " + " | ".join(row) + " |")

    if b.backlog:
        lines += ["", "📋 *Backlog*", *b.backlog]
    if b.dropped:
        lines += ["", "🗑 *Dropped*", *[f"- {s}" for s in b.dropped]]
    return "\n".join(lines)


def render_unit(ws: S.Workstream, store: Path, unit_slug: str) -> str:
    by_slug = {u.slug: u for u in ws.units}
    u = by_slug.get(unit_slug)
    if u is None:
        return f"unit '{unit_slug}' not found in {ws.ws_id}"
    S.derive_status(ws)
    out = [f"*{u.slug}* — {u.status}" + (f" · #{u.pr.number}"
                                         if u.pr and u.pr.number else ""),
           f"_{u.title}_" if u.title else ""]

    out += ["", S.focus_line_for(ws)]

    raw = _read(store / ws.ws_id / "units" / u.slug / "progress.md")
    tasks = _section_lines(raw, "Tasks")
    fus = _section_lines(raw, "Follow-ups")
    out += ["", "## Tasks"] + (tasks or ["(none)"])
    out += ["", "## Follow-ups"] + (fus or ["(none)"])

    need_lines = []
    for n in S.unit_needs(u, ws):
        satisfied, note = S.need_state(n.target, ws, by_slug)
        if n.nid == "base" and satisfied:
            continue  # base shown only when it still blocks
        mark = "satisfied" if satisfied else "open"
        if note:
            mark += f", {note}"
        tail = f" — {n.note}" if n.note and n.note != "base" else ""
        need_lines.append(f"- {n.target} [{mark}]{tail}")
    out += ["", "## Needs"] + (need_lines or ["(none)"])

    log = [f"- {ts}  {kind}  {p}" for ts, kind, p in u.log][-6:]
    out += ["", "## Recent log"] + (log or ["(none)"])
    return "\n".join(x for x in out if x is not None)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _section_lines(text: str, name: str) -> List[str]:
    out, inside = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            inside = line[3:].strip() == name
            continue
        if inside and line.startswith("- "):
            out.append(line)
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render_spike(ws: S.Workstream, store: Path, spike_slug: str) -> str:
    by_slug = {u.slug: u for u in ws.units}
    by_spike = {s.slug: s for s in ws.spikes}
    sp = by_spike.get(spike_slug)
    if sp is None:
        return f"spike '{spike_slug}' not found in {ws.ws_id}"
    S.derive_status(ws)
    out = [f"*{sp.slug}* [spike] — {sp.status}",
           f"_{sp.title}_" if sp.title else ""]

    out += ["", S.focus_line_for(ws)]

    raw = _read(store / ws.ws_id / "spikes" / sp.slug / "progress.md")
    tasks = _section_lines(raw, "Tasks")
    out += ["", "## Tasks"] + (tasks or ["(none)"])

    need_lines = []
    for n in S.spike_needs(sp):
        satisfied, note = S.need_state(n.target, ws, by_slug, by_spike)
        mark = "satisfied" if satisfied else "open"
        if note:
            mark += f", {note}"
        tail = f" — {n.note}" if n.note else ""
        need_lines.append(f"- {n.target} [{mark}]{tail}")
    out += ["", "## Needs"] + (need_lines or ["(none)"])

    log = [f"- {ts}  {kind}  {p}" for ts, kind, p in sp.log][-6:]
    out += ["", "## Recent log"] + (log or ["(none)"])
    return "\n".join(x for x in out if x is not None)


def generate(store: Path, ws_id: str, unit_slug: Optional[str],
             pr_state: Dict[str, Optional[S.PR]]) -> str:
    """Pure path used by both main() and the tests."""
    ws = S.load_workstream(store / ws_id)
    S.apply_pr_state(ws, pr_state)
    if not unit_slug:
        return render_board(
            S.build_board(ws, phase_for=P.phase_for_unit(store, ws)))
    kind = C.resolve_kind_in_ws(store, ws_id, unit_slug, fallback="unit")
    if kind == "spike":
        return render_spike(ws, store, unit_slug)
    return render_unit(ws, store, unit_slug)


def main(argv: List[str]) -> int:
    store = S.store_root()
    try:
        ws_id, unit_slug = C.resolve_args(store, argv)
    except C.Pick as p:
        print(str(p), file=sys.stderr)
        return 2
    ws = S.load_workstream(store / ws_id)
    print(generate(store, ws_id, unit_slug, C.gather_pr_state(ws, store)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
