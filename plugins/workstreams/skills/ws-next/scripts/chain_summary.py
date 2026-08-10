"""Chain picker expectations — mirrors ws-next SKILL.md Chain section."""

from __future__ import annotations

from typing import List

import ws_store as S


def has_proposal_material(d: S.Decision) -> bool:
    return bool(d.proposable or d.covered or d.design)


def chain_offers_propose(d: S.Decision) -> bool:
    return bool(d.moves) and has_proposal_material(d)


def chain_runs_unit_picker(d: S.Decision) -> bool:
    return len(d.moves) >= 2 or (
        len(d.moves) == 1 and has_proposal_material(d))


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


def chain_propose_option(lane: str) -> str:
    tail = lane[5:] if lane.startswith("From ") else lane
    return f"Propose from {tail}"


def chain_propose_options(d: S.Decision) -> List[str]:
    if not chain_offers_propose(d):
        return []
    return [chain_propose_option(lane) for lane in strategy_lanes(d)]


def propose_source_summary(d: S.Decision) -> str:
    """Informational summary of proposal sources (machine-only)."""
    parts: List[str] = []
    n = len(d.proposable)
    if n == 1:
        parts.append(d.proposable[0].fid)
    elif n == 2:
        parts.append(f"{d.proposable[0].fid}, {d.proposable[1].fid}")
    elif n >= 3:
        parts.append(f"{n} follow-ups")
    if d.design:
        parts.append("design")
    if d.active_focus:
        parts.append(f"focus: {d.active_focus.slug}")
    return ", ".join(parts)
