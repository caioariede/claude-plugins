#!/usr/bin/env python3
"""ws-resume confirm_plan — derive tasks and append plan=done.

Usage: confirm_plan.py [target-id] [--kind unit|spike] [--type unit|spike]
       [--reason headless] [--context <group>=<value>] [--migrate]

Prints: confirmed T1,T2,... | already-has-tasks | migrated T1,...
        | refused <reason>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402


def _store() -> Path:
    env = os.environ.get("WS_STORE")
    return Path(env) if env else S.store_root()


def _parse_context(raw: Optional[str]) -> Optional[Tuple[str, str]]:
    if not raw:
        return None
    if "=" not in raw:
        return None
    group, value = raw.split("=", 1)
    group, value = group.strip(), value.strip()
    if not group or not value:
        return None
    return group, value


def main(argv: List[str]) -> int:
    store = _store()
    p = argparse.ArgumentParser(prog="confirm_plan.py")
    p.add_argument("target_id", nargs="?", default="")
    p.add_argument("--kind", "--type", choices=("unit", "spike"), default="unit",
                   dest="kind")
    p.add_argument("--reason", default="")
    p.add_argument("--context", default="")
    p.add_argument("--migrate", action="store_true",
                   help="Append plan=done for legacy execute-mode units")
    ns = p.parse_args(argv)
    unit_args = [ns.target_id] if ns.target_id else []
    try:
        ws_id, slug = C.resolve_args(store, unit_args)
    except C.Pick as pick:
        print(str(pick), file=sys.stderr)
        return 2
    if slug is None:
        print("NO_UNIT target required", file=sys.stderr)
        return 2
    if ns.kind == "spike":
        ws = S.load_workstream(store / ws_id)
        sp = next((s for s in ws.spikes if s.slug == slug), None)
        if sp is None:
            print(f"NO_MATCH no spike {slug!r} in {ws_id}", file=sys.stderr)
            return 2
        plan_str = S.latest_plan_from_log(sp.log)
    else:
        ws = S.load_workstream(store / ws_id)
        unit = next((u for u in ws.units if u.slug == slug), None)
        if unit is None:
            print(f"NO_MATCH no unit {slug!r} in {ws_id}", file=sys.stderr)
            return 2
        plan_str = S.latest_plan_log_path(unit)
    if not plan_str:
        print("refused no-plan")
        return 0
    ctx = _parse_context(ns.context or None)
    reason = ns.reason.strip() or None
    status, ids = S.apply_confirm_plan(
        store / ws_id, slug, Path(plan_str), kind=ns.kind,
        reason=reason, context=ctx, migrate_only=ns.migrate)
    if status == "confirmed":
        print(f"confirmed {','.join(ids)}")
    elif status == "migrated":
        print(f"migrated {','.join(ids)}")
    elif status == "already-has-tasks":
        print("already-has-tasks")
    else:
        print(status if status.startswith("refused") else f"refused {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
