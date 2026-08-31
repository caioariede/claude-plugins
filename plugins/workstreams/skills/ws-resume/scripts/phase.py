#!/usr/bin/env python3
"""ws-resume phase — print loop boundary for one unit or spike.

Usage: phase.py [unit-id] [--skip-prewalk] [--skip-critic] [--headless]

Prints one line: blocked | plan | prewalk-config | prewalk | plan-pause |
loop | critic | done  (unit)
  or blocked | plan | plan-pause | loop | done  (spike)
Exit 2 when the caller must pick (same tokens as ws-board).
"""

from __future__ import annotations

import argparse
import hashlib
from functools import partial
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

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


def _prewalk_flags(store: Path, u: S.Unit, *,
                   skip_prewalk: bool, headless: bool) -> dict:
    enabled = C.prewalk_enabled(store)
    activated = C.superpowers_prewalk_activated_at(store)
    grandfather = enabled and S._should_grandfather_prewalk(u, activated)
    return {
        "prewalk_enabled": enabled,
        "skip_prewalk": skip_prewalk,
        "headless": headless,
        "grandfather": grandfather,
        "models_ready": C.prewalk_models_ready(store),
    }


def _tree_digest(store: Path, u: S.Unit) -> Optional[str]:
    if not u.branch or not u.repo:
        return None
    wt = C.locate_worktree(store, u.branch, u.repo)
    if wt is None:
        return None
    base = S.recorded_base(u) or "main"
    try:
        result = subprocess.run(
            ["git", "-C", str(wt), "diff", f"{base}...HEAD"],
            capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return hashlib.sha256(result.stdout).hexdigest()[:8]


def _unit_resume_phase(ws: S.Workstream, u: S.Unit, store: Path, *,
                       skip_prewalk: bool = False, headless: bool = False,
                       skip_critic: bool = False) -> str:
    by_slug = {x.slug: x for x in ws.units}
    flags = _prewalk_flags(store, u, skip_prewalk=skip_prewalk,
                           headless=headless)
    review_enabled = C.review_enabled(store)
    flags.update({
        "review_enabled": review_enabled,
        "skip_critic": skip_critic,
        "grandfather_critic": (
            review_enabled
            and S._should_grandfather_prewalk(
                u, C.ws_critic_activated_at(store))),
        "critic_digest": _tree_digest(store, u),
    })
    return S.resume_phase(u, ws, by_slug, **flags)


def unit_phase(store: Path, ws: S.Workstream, u: S.Unit) -> str:
    """Resume phase for one unit (board / ws-next suffixes)."""
    return _unit_resume_phase(ws, u, store)


def phase_for_unit(store: Path, ws: S.Workstream):
    """Callable ``phase_for`` for board / decide_next."""
    return partial(unit_phase, store, ws)


def phase_for_ws(ws: S.Workstream, slug: str, kind: str, store: Path, *,
                 skip_prewalk: bool = False, headless: bool = False,
                 skip_critic: bool = False) -> str:
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
    return _unit_resume_phase(ws, unit, store, skip_prewalk=skip_prewalk,
                              headless=headless, skip_critic=skip_critic)


def generate(store: Path, ws_id: str, slug: str,
             pr_by_branch: Dict[str, Optional[S.PR]],
             kind: Optional[str] = None, *,
             skip_prewalk: bool = False, headless: bool = False,
             skip_critic: bool = False) -> str:
    """Pure path used by both main() and the tests."""
    ws = S.load_workstream(store / ws_id)
    S.apply_pr_state(ws, pr_by_branch)
    if kind is None:
        kind = C.resolve_kind_in_ws(store, ws_id, slug)
    return phase_for_ws(ws, slug, kind, store, skip_prewalk=skip_prewalk,
                        headless=headless, skip_critic=skip_critic)


def _parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="phase.py")
    p.add_argument("unit_id", nargs="?", default="")
    p.add_argument("--skip-prewalk", action="store_true")
    p.add_argument("--skip-critic", action="store_true")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--emit-gate", action="store_true",
                   help="Emit structured gate definition after phase token")
    return p.parse_args(argv)


def _plan_pause_context(ws: S.Workstream, slug: str, kind: str
                        ) -> Optional[dict]:
    if kind == "spike":
        sp = next((s for s in ws.spikes if s.slug == slug), None)
        plan_path = S.latest_plan_from_log(sp.log) if sp else None
    else:
        unit = next((u for u in ws.units if u.slug == slug), None)
        plan_path = S.latest_plan_log_path(unit) if unit else None
    if not plan_path or not Path(plan_path).exists():
        return None
    ctx: dict = {"plan": plan_path}
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            tasks = S.derive_tasks_from_plan(f.read())
            ctx["tasks"] = [title for _, title in tasks]
    except Exception:
        pass
    return ctx


def main(argv: List[str]) -> int:
    store = _store()
    ns = _parse_args(argv)
    unit_args = [ns.unit_id] if ns.unit_id else []
    try:
        target = _resolve_target(store, unit_args)
        ws = S.load_workstream(store / target.ws_id)
        pr_state = C.gather_pr_state(ws, store)
        S.apply_pr_state(ws, pr_state)
        ph = phase_for_ws(ws, target.slug, target.kind, store,
                           skip_prewalk=ns.skip_prewalk,
                           skip_critic=ns.skip_critic,
                           headless=ns.headless)
        print(ph)
        if ns.emit_gate:
            ctx = (_plan_pause_context(ws, target.slug, target.kind)
                   if ph == "plan-pause" else None)
            gate_block = gate_emit.emit_gate(ph, kind=target.kind, context=ctx)
            if gate_block:
                print(gate_block)
        return 0
    except C.Pick as p:
        print(str(p), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
