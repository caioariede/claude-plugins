"""Store/forge access shared by ws-* command scripts (ws-board, ws-next).

The impure half of the contract: locating workstreams, resolving args to a
target, resolving the active `forge` flavor from the merged INI layers, and
running its `pr-status` per unit in parallel. Kept out of ws_store.py so the
engine there stays pure (parse + derive) and unit-testable without a shell.
"""

from __future__ import annotations

import concurrent.futures
import configparser
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import ws_store as S

BUILTIN_FLAVORS = Path(__file__).resolve().parent.parent / "references" / "flavors.ini"


# ---------------------------------------------------------------------------
# Flavor resolution (forge pr-status) — the SPEC's INI merge, in code
# ---------------------------------------------------------------------------

def _load_ini(path: Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None, delimiters=("=",),
                                   strict=False)
    cp.optionxform = str  # keys are case-sensitive here
    if path.exists():
        cp.read(path, encoding="utf-8")
    return cp


def _layers(store: Path) -> List[configparser.ConfigParser]:
    """Built-in → store → overrides, low to high precedence."""
    layers = [_load_ini(BUILTIN_FLAVORS)]
    store_cp = _load_ini(store / "flavors.ini")
    layers.append(store_cp)
    if store_cp.has_option("config", "overrides-file"):
        ov = Path(os.path.expanduser(store_cp.get("config", "overrides-file")))
        if ov.exists():
            layers.append(_load_ini(ov))
    return layers


def resolve_operation(store: Path, group: str, op: str,
                      default_flavor: str) -> Optional[str]:
    layers = _layers(store)
    flavor = default_flavor
    for cp in layers:
        if cp.has_option("active", group):
            flavor = cp.get("active", group).strip()
    for section in (f"{group}/{flavor}", f"{group}/{default_flavor}"):
        instr = None
        for cp in layers:
            if cp.has_option(section, op):
                instr = cp.get(section, op).strip()
        if instr is not None:
            return instr
    return None


# ---------------------------------------------------------------------------
# PR state gathering — run the resolved pr-status per branch, in parallel
# ---------------------------------------------------------------------------

def _fill(template: str, branch: str, repo: str) -> str:
    return template.replace("<branch>", branch).replace("<repo>", repo)


def _run_pr_status(cmd: str) -> Optional[S.PR]:
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True,
                             text=True, timeout=25)
    except subprocess.TimeoutExpired:
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None  # no PR for this branch (or forge unreachable)
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    return S.PR(number=data.get("number"),
               state=(data.get("state") or "").upper(),
               is_draft=bool(data.get("isDraft")),
               base=data.get("baseRefName"))


def gather_pr_state(ws: S.Workstream, store: Path) -> Dict[str, Optional[S.PR]]:
    template = resolve_operation(store, "forge", "pr-status", "gh")
    result: Dict[str, Optional[S.PR]] = {}
    if not template or ":" in template.split()[0]:
        # A skill:id-style forge can't be driven from here; render without
        # PR state (every unit falls back to `building`).
        return result
    jobs = {u.branch: _fill(template, u.branch, u.repo)
            for u in ws.units if u.branch}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_run_pr_status, cmd): br
                   for br, cmd in jobs.items()}
        for fut in concurrent.futures.as_completed(futures):
            result[futures[fut]] = fut.result()
    return result


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------

class Pick(Exception):
    """The caller (a human via the skill) must disambiguate."""


_WS_SLUG_RE = re.compile(r'^\d{4}-\d{2}-\d{2}-(.+)$')


def list_workstreams(store: Path) -> List[str]:
    if not store.exists():
        return []
    return sorted(d.name for d in store.iterdir()
                  if d.is_dir() and (d / "units.md").exists())


def resolve_workstream(store: Path, token: str) -> List[str]:
    """Match a workstream by full id (dir name) or by its date-stripped
    slug — users name a workstream by slug ('scoped-user-sessions'), not
    the dated id. Exact id wins outright; slug matches can collide across
    dates, so more than one is ambiguous."""
    hits = []
    for ws_id in list_workstreams(store):
        if ws_id == token:
            return [ws_id]
        m = _WS_SLUG_RE.match(ws_id)
        if m and m.group(1) == token:
            hits.append(ws_id)
    return hits


def resolve_slug(store: Path, token: str) -> List[Tuple[str, str]]:
    """Bare-slug resolver: (ws_id, slug) matches across all unit ledgers."""
    hits = []
    for ws_id in list_workstreams(store):
        units = S.parse_units((store / ws_id / "units.md").read_text("utf-8"))
        for u in units:
            if u.slug == token:
                hits.append((ws_id, token))
    return hits


def resolve_args(store: Path, args: List[str]) -> Tuple[str, Optional[str]]:
    """Return (ws_id, unit_slug|None). Raises Pick when the caller must
    choose. A workstream matches by full id or date-stripped slug; else a
    lone token falls through to the unit bare-slug resolver."""
    all_ws = list_workstreams(store)
    if len(args) >= 2:
        ws_hits = resolve_workstream(store, args[0])
        if len(ws_hits) == 1:
            return ws_hits[0], args[1]
        if len(ws_hits) > 1:
            raise Pick(f"AMBIGUOUS workstream '{args[0]}' matches: "
                       + ", ".join(ws_hits))
        raise Pick(f"NO_MATCH no workstream '{args[0]}'")
    if len(args) == 1:
        tok = args[0]
        ws_hits = resolve_workstream(store, tok)
        if len(ws_hits) == 1:
            return ws_hits[0], None
        if len(ws_hits) > 1:
            raise Pick(f"AMBIGUOUS workstream '{tok}' matches: "
                       + ", ".join(ws_hits))
        hits = resolve_slug(store, tok)
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise Pick(f"NO_MATCH no workstream or unit named '{tok}'")
        opts = ", ".join(f"{w}:{s}" for w, s in hits)
        raise Pick(f"AMBIGUOUS unit '{tok}' matches: {opts}")
    if not all_ws:
        raise Pick("NO_STORE no workstreams found in the store")
    if len(all_ws) == 1:
        return all_ws[0], None
    raise Pick("MANY_WORKSTREAMS " + ", ".join(all_ws))
