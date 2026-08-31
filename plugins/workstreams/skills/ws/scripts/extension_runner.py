#!/usr/bin/env python3
"""Spawn extension handlers for ws-resume phase slots."""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import ws_cli as C

EXTENSIONS_FILE = (
    Path(__file__).resolve().parents[1] / "references" / "flows" / "extensions.json"
)
PLUGIN_ROOT = Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def load_extensions() -> List[Dict[str, Any]]:
    if not EXTENSIONS_FILE.exists():
        return []
    with open(EXTENSIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("extensions") or [])


def extension_phase_names() -> List[str]:
    phases: List[str] = []
    for ext in load_extensions():
        phases.extend(ext.get("phases") or [])
    return phases


def expand_skip_tokens(tokens: Set[str]) -> Set[str]:
    """Map extension ids to phase names; pass through unknown tokens."""
    by_id = {ext["id"]: ext for ext in load_extensions()}
    phases: Set[str] = set()
    for token in tokens:
        row = by_id.get(token)
        if row:
            phases |= set(row.get("phases") or [])
        else:
            phases.add(token)
    return phases


def _extension_enabled(store: Path, ext: Dict[str, Any]) -> bool:
    rule = ext.get("enable") or {}
    group = rule.get("group")
    op = rule.get("op")
    expected = rule.get("eq")
    if not group or not op or expected is None:
        return False
    flavor, _ = C.active_flavor(store, group)
    ops, err = C.effective_flavor_ops(store, group, flavor)
    if err:
        return False
    return (ops.get(op) or "").strip() == expected


def _resolve_handler_argv(handler: List[str]) -> List[str]:
    argv = list(handler)
    for i, part in enumerate(argv):
        if i == 0:
            continue
        candidate = PLUGIN_ROOT / part
        if candidate.exists():
            argv[i] = str(candidate)
    return argv


def _should_skip_extension(ext: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    if ctx.get("headless"):
        return True
    meta = (ctx.get("extensions") or {}).get(ext.get("id", "")) or {}
    if meta.get("grandfather"):
        return True
    skip = set(ctx.get("skip") or [])
    return bool(skip & set(ext.get("phases") or []))


def _invoke_handler(ext: Dict[str, Any], slot: str,
                    ctx: Dict[str, Any]) -> Optional[str]:
    argv = _resolve_handler_argv(ext.get("handler") or [])
    if not argv:
        return None
    req = {
        "v": 1,
        "op": "pending",
        "extension": ext.get("id"),
        "slot": slot,
        "ctx": ctx,
    }
    try:
        proc = subprocess.run(
            argv,
            input=json.dumps(req) + "\n",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return None
    try:
        data = json.loads(line[-1])
    except json.JSONDecodeError:
        return None
    phase = data.get("phase")
    allowed = set(ext.get("phases") or [])
    if phase and phase in allowed:
        return phase
    return None


def pending_for_slot(slot: str, ctx: Dict[str, Any], store: Path,
                     *, kind: str = "unit") -> Optional[str]:
    """First pending extension phase for ``slot``, or None."""
    rows = [
        ext for ext in load_extensions()
        if ext.get("slot") == slot and ext.get("kind", "unit") == kind
    ]
    rows.sort(key=lambda e: int(e.get("order") or 0))
    for ext in rows:
        if not _extension_enabled(store, ext):
            continue
        if _should_skip_extension(ext, ctx):
            continue
        phase = _invoke_handler(ext, slot, ctx)
        if phase:
            return phase
    return None
