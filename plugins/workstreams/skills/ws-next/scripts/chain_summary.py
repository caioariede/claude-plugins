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


def propose_source_summary(d: S.Decision) -> str:
    """Tail after 'from ' on the Chain Propose next unit option."""
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
