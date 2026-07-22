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
    # The parser's default section is renamed to a sentinel no file
    # will contain, so a literal [DEFAULT] in a hand-edited file stays
    # an ordinary section instead of bleeding its keys into every
    # flavor's merged ops.
    cp = configparser.ConfigParser(interpolation=None, delimiters=("=",),
                                   strict=False,
                                   default_section="~defaults-disabled~")
    cp.optionxform = str  # keys are case-sensitive here
    if path.exists():
        cp.read(path, encoding="utf-8")
    return cp


def _overrides_from(cp: configparser.ConfigParser) -> Optional[Path]:
    """The [config] overrides-file path in a loaded store layer; None
    when unset or emptied (an empty value means 'no overrides', not
    '.')."""
    if cp.has_option("config", "overrides-file"):
        val = cp.get("config", "overrides-file").strip()
        if val:
            return Path(os.path.expanduser(val))
    return None


def _layers(store: Path) -> List[configparser.ConfigParser]:
    """Built-in → store → overrides, low to high precedence."""
    store_cp = _load_ini(store / "flavors.ini")
    layers = [_load_ini(BUILTIN_FLAVORS), store_cp]
    ov = _overrides_from(store_cp)
    if ov is not None and ov.exists():
        layers.append(_load_ini(ov))
    return layers


def resolve_operation(store: Path, group: str, op: str) -> Optional[str]:
    """SPEC §Flavors resolution: the active flavor's op, merged per key
    across layers, falling back to the group default flavor's op."""
    layers = _layers(store)
    flavor = active_flavor(store, group)[0]
    for section in (f"{group}/{flavor}",
                    f"{group}/{GROUP_DEFAULTS[group]}"):
        instr = None
        for cp in layers:
            if cp.has_option(section, op):
                instr = cp.get(section, op).strip()
        if instr is not None:
            return instr
    return None


# ---------------------------------------------------------------------------
# Flavor introspection (ws-config engine) — provenance, known flavors,
# per-flavor merged ops WITHOUT the default fallback, and tool deps
# (SPEC §Flavors, Availability).
# ---------------------------------------------------------------------------

GROUP_DEFAULTS = {"worktree-management": "git-worktree",
                  "spec-driven-development": "none",
                  "forge": "gh"}

CORE_OPS = {"worktree-management": ("create", "remove", "locate"),
            "spec-driven-development": ("plan", "execute", "ship"),
            "forge": ("default-branch", "pr-status", "pr-create",
                      "pr-ready", "pr-retarget")}

_LAYER_NAMES = ("built-in", "store", "overrides")


def active_flavor(store: Path, group: str) -> Tuple[str, str]:
    """(flavor, provenance) — provenance names the highest layer that
    sets [active] group, or 'default' when none does."""
    flavor, prov = GROUP_DEFAULTS[group], "default"
    for cp, name in zip(_layers(store), _LAYER_NAMES):
        if cp.has_option("active", group):
            flavor, prov = cp.get("active", group).strip(), name
    return flavor, prov


def known_flavors(store: Path, group: str) -> List[str]:
    """Flavors defined for `group` in any layer, default flavor first."""
    out: List[str] = []
    for cp in _layers(store):
        for sec in cp.sections():
            g, _, f = sec.partition("/")
            if g == group and f and f not in out:
                out.append(f)
    d = GROUP_DEFAULTS[group]
    if d in out:
        out.remove(d)
        out.insert(0, d)
    return out


def flavor_ops(store: Path, group: str, flavor: str) -> Dict[str, str]:
    """[group/flavor] merged per key across layers. Deliberately NO
    default-flavor fallback: Availability judges a flavor on its own
    keys, so a scaffolded stub stays visibly empty."""
    sec = f"{group}/{flavor}"
    ops: Dict[str, str] = {}
    for cp in _layers(store):
        if cp.has_section(sec):
            for k, v in cp.items(sec):
                ops[k] = (v or "").strip()
    return ops


def flavor_deps(ops: Dict[str, str], group: str) -> List[Tuple[str, str]]:
    """Tool deps of the group's core operations only — spec-glob,
    hook-*, and companion keys never contribute (SPEC Availability).
    Kinds: ('shell', head) / ('skill', id) / ('ws', cmd) /
    ('missing-op', op) for an empty or absent core op."""
    deps: List[Tuple[str, str]] = []
    seen = set()
    for op in CORE_OPS[group]:
        instr = (ops.get(op) or "").strip()
        if not instr:
            deps.append(("missing-op", op))
            continue
        head = instr.split()[0]
        if head.startswith("ws-"):
            d = ("ws", head)
        elif re.fullmatch(r"[A-Za-z0-9_-]+:[A-Za-z0-9_-]+", head):
            d = ("skill", head)
        else:
            d = ("shell", head)
        if d not in seen:
            seen.add(d)
            deps.append(d)
    return deps


def overrides_path(store: Path) -> Optional[Path]:
    """The [config] overrides-file path from the store layer, or None."""
    return _overrides_from(_load_ini(store / "flavors.ini"))


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
    template = resolve_operation(store, "forge", "pr-status")
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
