#!/usr/bin/env python3
"""ws-resume check_progress — mark tasks or follow-ups checked.

Usage: check_progress.py [target-id] T1 [T2 ...]
       check_progress.py [target-id] --tasks-done
       check_progress.py [target-id] --kind unit|spike

Prints: checked T1,T2 | already-checked T1 | refused <reason>
Exit 2 when the caller must pick.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402


def _store() -> Path:
    env = os.environ.get("WS_STORE")
    return Path(env) if env else S.store_root()


def main(argv: List[str]) -> int:
    store = _store()
    p = argparse.ArgumentParser(prog="check_progress.py")
    p.add_argument("target_id", nargs="?", default="")
    p.add_argument("ids", nargs="*", metavar="T1")
    p.add_argument("--kind", "--type", choices=("unit", "spike"), default="unit",
                   dest="kind")
    p.add_argument("--tasks-done", action="store_true",
                   help="Check every unchecked T<n> in ## Tasks")
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
    ws_dir = store / ws_id
    sub = "spikes" if ns.kind == "spike" else "units"
    prog_path = ws_dir / sub / slug / "progress.md"
    if ns.tasks_done:
        ids = S.unchecked_task_ids(
            prog_path.read_text(encoding="utf-8") if prog_path.is_file()
            else "")
        if not ids:
            print("already-checked")
            return 0
    else:
        ids = list(ns.ids)
    status, checked = S.apply_check_progress(
        ws_dir, slug, ids, kind=ns.kind)
    if status == "checked":
        print(f"checked {','.join(checked)}")
    elif status == "already-checked":
        print(f"already-checked {','.join(checked)}")
    else:
        print(status if status.startswith("refused") else f"refused {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
