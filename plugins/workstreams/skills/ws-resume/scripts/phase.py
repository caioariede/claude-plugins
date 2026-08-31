#!/usr/bin/env python3
"""ws-resume phase — print loop boundary for one unit or spike.

Usage: phase.py [unit-id] [--skip-extension PHASE] [--headless]

Prints one phase token from ``ws_store.resume_phase`` / ``resume_spike_phase``,
then optionally a gate block from ``gates.json`` when ``--emit-gate`` is set.
Exit 2 when the caller must pick (same tokens as ws-board).
"""

from __future__ import annotations

import argparse
from functools import partial
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402
import gate_emit       # noqa: E402


def _store() -> Path:
    env = os.environ.get("WS_STORE")
    return Path(env) if env else S.store_root()


def _resolve_target(store: Path, args: List[str]) -> C.ResolvedTarget:
    ws_id, slug = C.resolve_args(store, args)
    if not slug:
        br = C.current_branch()
        if not br:
            raise C.Pick("NO_MATCH no unit-id and not on a ledger branch")
        hits = C.resolve_branch(store, br)
        if len(hits) != 1:
            raise C.Pick("NO_MATCH cwd branch matches no unique ledger unit")
        ws_id, slug = hits[0]
        return C.ResolvedTarget(ws_id, slug, "unit")
    kind = C.resolve_kind_in_ws(store, ws_id, slug)
    return C.ResolvedTarget(ws_id, slug, kind)


def _unit_resume_phase(ws: S.Workstream, u: S.Unit, store: Path, *,
                       headless: bool = False,
                       skip_extensions: Optional[Set[str]] = None) -> str:
    by_slug = {x.slug: x for x in ws.units}
    kwargs = C.unit_resume_phase_kwargs(
        store, u, headless=headless, skip_extensions=skip_extensions)
    return S.resume_phase(u, ws, by_slug, **kwargs)


def unit_phase(store: Path, ws: S.Workstream, u: S.Unit) -> str:
    """Resume phase for one unit (board / ws-next suffixes)."""
    return _unit_resume_phase(ws, u, store)


def phase_for_unit(store: Path, ws: S.Workstream):
    """Callable ``phase_for`` for board / decide_next."""
    return partial(unit_phase, store, ws)


def phase_for_ws(ws: S.Workstream, slug: str, kind: str, store: Path, *,
                 headless: bool = False,
                 skip_extensions: Optional[Set[str]] = None) -> str:
    by_spike = {s.slug: s for s in ws.spikes}
    if kind == "spike":
        sp = by_spike.get(slug)
        if sp is None:
            raise C.Pick(f"NO_MATCH no spike {slug!r} in {ws.ws_id}")
        by_slug = {u.slug: u for u in ws.units}
        return S.resume_spike_phase(sp, ws, by_slug, by_spike)
    unit = {u.slug: u for u in ws.units}.get(slug)
    if unit is None:
        raise C.Pick(f"NO_MATCH no unit {slug!r} in {ws.ws_id}")
    return _unit_resume_phase(ws, unit, store, headless=headless,
                              skip_extensions=skip_extensions)


def generate(store: Path, ws_id: str, slug: str,
             pr_by_branch: Dict[str, Optional[S.PR]],
             kind: Optional[str] = None, *,
             headless: bool = False,
             skip_extensions: Optional[Set[str]] = None) -> str:
    """Pure path used by both main() and the tests."""
    ws = S.load_workstream(store / ws_id)
    S.apply_pr_state(ws, pr_by_branch)
    if kind is None:
        kind = C.resolve_kind_in_ws(store, ws_id, slug)
    return phase_for_ws(ws, slug, kind, store, headless=headless,
                        skip_extensions=skip_extensions)


def _parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="phase.py")
    p.add_argument("unit_id", nargs="?", default="")
    p.add_argument("--skip-extension", action="append", dest="skip_extension",
                   metavar="PHASE",
                   help="Bypass one extension phase (repeatable; see gates.json)")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--emit-gate", action="store_true",
                   help="Emit structured gate definition after phase token")
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    store = _store()
    ns = _parse_args(argv)
    unit_args = [ns.unit_id] if ns.unit_id else []
    skip_extensions = C.collect_skip_extensions(ns.skip_extension)
    try:
        target = _resolve_target(store, unit_args)
        ws = S.load_workstream(store / target.ws_id)
        pr_state = C.gather_pr_state(ws, store)
        S.apply_pr_state(ws, pr_state)
        ph = phase_for_ws(ws, target.slug, target.kind, store,
                           headless=ns.headless,
                           skip_extensions=skip_extensions)
        print(ph)
        if ns.emit_gate:
            ctx = gate_emit.gate_context(ph, ws, target.slug, target.kind)
            gate_block = gate_emit.emit_gate(
                ph, kind=target.kind, context=ctx)
            if gate_block:
                print(gate_block)
        return 0
    except C.Pick as p:
        print(str(p), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
