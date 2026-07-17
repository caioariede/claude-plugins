#!/usr/bin/env python3
"""ws-board — render a workstream board from the store, deterministically.

Reads the durable store, resolves the active `forge` flavor and runs its
`pr-status` per unit in parallel, derives status via the shared engine,
and prints a terminal-ready board (or one unit's detail). The skill runs
this and relays the output; the derivation lives in ws/scripts/ws_store.py
so ws-next can reuse it.

Usage: board.py [ws-id] [unit-id]
Exit 2 with a machine-readable first line when the caller must pick
(ambiguous slug, or 0 args with multiple workstreams).
"""

from __future__ import annotations

import concurrent.futures
import configparser
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
import ws_store as S  # noqa: E402

BUILTIN_FLAVORS = (Path(__file__).resolve().parents[2]
                   / "ws" / "references" / "flavors.ini")


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
# Argument resolution
# ---------------------------------------------------------------------------

def list_workstreams(store: Path) -> List[str]:
    if not store.exists():
        return []
    return sorted(d.name for d in store.iterdir()
                  if d.is_dir() and (d / "units.md").exists())


_WS_SLUG_RE = re.compile(r'^\d{4}-\d{2}-\d{2}-(.+)$')


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
        ws_id = ws_hits[0] if len(ws_hits) == 1 else args[0]
        return ws_id, args[1]
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


class Pick(Exception):
    """The caller (a human via the skill) must disambiguate."""


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_board(b: S.Board) -> str:
    head = f"*{b.name}* — {b.merged_count}/{b.total_count} units done"
    if b.complete:
        head += " · ✅ complete"
    lines = [head, ""]

    if b.has_blocked:
        cols = [("⏳ Not started", b.not_started), ("⛔ Blocked", b.blocked),
                ("🔄 In progress", b.in_progress), ("✅ Done", b.done)]
    else:
        cols = [("⏳ Not started", b.not_started),
                ("🔄 In progress", b.in_progress), ("✅ Done", b.done)]

    headers = [h for h, _ in cols]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in cols) + " |")
    depth = max((len(c) for _, c in cols), default=0)
    for i in range(depth):
        row = [(c[i] if i < len(c) else "") for _, c in cols]
        lines.append("| " + " | ".join(row) + " |")

    if b.backlog:
        lines += ["", "📋 *Backlog*", *b.backlog]
    if b.dropped:
        lines += ["", "🗑 *Dropped*", *[f"- {s}" for s in b.dropped]]
    return "\n".join(lines)


def render_unit(ws: S.Workstream, store: Path, unit_slug: str) -> str:
    by_slug = {u.slug: u for u in ws.units}
    u = by_slug.get(unit_slug)
    if u is None:
        return f"unit '{unit_slug}' not found in {ws.ws_id}"
    S.derive_status(ws)
    out = [f"*{u.slug}* — {u.status}" + (f" · #{u.pr.number}"
                                         if u.pr and u.pr.number else ""),
           f"_{u.title}_" if u.title else ""]

    raw = _read(store / ws.ws_id / "units" / u.slug / "progress.md")
    tasks = _section_lines(raw, "Tasks")
    fus = _section_lines(raw, "Follow-ups")
    out += ["", "## Tasks"] + (tasks or ["(none)"])
    out += ["", "## Follow-ups"] + (fus or ["(none)"])

    need_lines = []
    for n in S.unit_needs(u, ws):
        satisfied, note = S.need_state(n.target, ws, by_slug)
        if n.nid == "base" and satisfied:
            continue  # base shown only when it still blocks
        mark = "satisfied" if satisfied else "open"
        if note:
            mark += f", {note}"
        tail = f" — {n.note}" if n.note and n.note != "base" else ""
        need_lines.append(f"- {n.target} [{mark}]{tail}")
    out += ["", "## Needs"] + (need_lines or ["(none)"])

    log = [f"- {ts}  {kind}  {p}" for ts, kind, p in u.log][-6:]
    out += ["", "## Recent log"] + (log or ["(none)"])
    return "\n".join(x for x in out if x is not None)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _section_lines(text: str, name: str) -> List[str]:
    out, inside = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            inside = line[3:].strip() == name
            continue
        if inside and line.startswith("- "):
            out.append(line)
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate(store: Path, ws_id: str, unit_slug: Optional[str],
             pr_state: Dict[str, Optional[S.PR]]) -> str:
    """Pure path used by both main() and the tests."""
    ws = S.load_workstream(store / ws_id)
    S.apply_pr_state(ws, pr_state)
    if unit_slug:
        return render_unit(ws, store, unit_slug)
    return render_board(S.build_board(ws))


def main(argv: List[str]) -> int:
    store = S.store_root()
    try:
        ws_id, unit_slug = resolve_args(store, argv)
    except Pick as p:
        print(str(p), file=sys.stderr)
        return 2
    ws = S.load_workstream(store / ws_id)
    S.apply_pr_state(ws, gather_pr_state(ws, store))
    if unit_slug:
        print(render_unit(ws, store, unit_slug))
    else:
        print(render_board(S.build_board(ws)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
