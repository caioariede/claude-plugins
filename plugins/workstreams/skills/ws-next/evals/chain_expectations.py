#!/usr/bin/env python3
"""Expected Chain picker behavior from a Decision — mirrors ws-next Chain."""

from __future__ import annotations

import ws_store as S


def has_proposal_material(d: S.Decision) -> bool:
    return bool(d.proposable or d.covered or d.design)


def chain_offers_propose(d: S.Decision) -> bool:
    """True when Chain should list Propose next unit."""
    return bool(d.moves) and has_proposal_material(d)


def chain_runs_unit_picker(d: S.Decision) -> bool:
    """True when Chain settles the unit before the hook."""
    return len(d.moves) >= 2 or (len(d.moves) == 1 and has_proposal_material(d))
