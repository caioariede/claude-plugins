#!/usr/bin/env python3
"""Expected strategy lanes from a Decision — mirrors ws-next/SKILL.md rules."""

from __future__ import annotations

from typing import List

import ws_store as S


def _is_unit_fu(fid: str) -> bool:
    return ":F" in fid


def strategy_lanes(d: S.Decision) -> List[str]:
    """Return lane labels the skill should offer (excluding Not now)."""
    lanes: List[str] = []
    blocking = [p for p in d.proposable if p.blocks]
    unit_fu = [p for p in d.proposable if not p.blocks and _is_unit_fu(p.fid)]
    ws_fu = [p for p in d.proposable if not p.blocks and not _is_unit_fu(p.fid)]

    for p in blocking:
        lanes.append(f"{p.fid} — {p.desc} (blocks {', '.join(p.blocks)})")

    if d.active_focus:
        lanes.append(f"From focus: {d.active_focus.slug}")

    if d.design and not d.active_focus:
        lanes.append("From design spec")

    if len(unit_fu) >= 2:
        lanes.append("Unit follow-ups")
    elif len(unit_fu) == 1:
        p = unit_fu[0]
        lanes.append(f"{p.fid} — {p.desc}")

    if len(ws_fu) >= 2:
        lanes.append("Workstream follow-ups")
    elif len(ws_fu) == 1:
        p = ws_fu[0]
        lanes.append(f"{p.fid} — {p.desc}")

    return lanes
