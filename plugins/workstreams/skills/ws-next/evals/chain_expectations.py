#!/usr/bin/env python3
"""Expected Chain picker behavior — re-exports scripts/chain_summary.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from chain_summary import (  # noqa: E402
    chain_offers_propose,
    chain_runs_unit_picker,
    has_proposal_material,
    propose_source_summary,
)

__all__ = [
    "chain_offers_propose",
    "chain_runs_unit_picker",
    "has_proposal_material",
    "propose_source_summary",
]
