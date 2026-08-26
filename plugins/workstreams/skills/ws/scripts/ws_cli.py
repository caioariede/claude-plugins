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
import time
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


def gather_pr_state(ws: S.Workstream, store: Path,
                    branches: Optional[set] = None) -> Dict[str, Optional[S.PR]]:
    template = resolve_operation(store, "forge", "pr-status")
    result: Dict[str, Optional[S.PR]] = {}
    if not template or ":" in template.split()[0]:
        # A skill:id-style forge can't be driven from here; render without
        # PR state (every unit falls back to `building`).
        return result
    jobs = {u.branch: _fill(template, u.branch, u.repo)
            for u in ws.units
            if u.branch and (branches is None or u.branch in branches)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_run_pr_status, cmd): br
                   for br, cmd in jobs.items()}
        for fut in concurrent.futures.as_completed(futures):
            result[futures[fut]] = fut.result()
    return result


# ---------------------------------------------------------------------------
# Shipped-elsewhere detection (ws-resume reconcile)
# ---------------------------------------------------------------------------

def _run_shell(cmd: str, timeout: int = 25) -> Optional[str]:
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True,
                             text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if out.returncode != 0:
        return None
    return (out.stdout or "").strip() or None


def _run_forge_simple(store: Path, op: str, repo: str,
                      branch: str = "") -> Optional[str]:
    template = resolve_operation(store, "forge", op)
    if not template or ":" in template.split()[0]:
        return None
    cmd = template.replace("<repo>", repo).replace("<branch>", branch)
    return _run_shell(cmd)


def _resolve_tip_sha(unit: S.Unit, wt: Optional[Path]) -> Optional[str]:
    if unit.branch and unit.repo:
        ref = f"refs/heads/{unit.branch}"
        raw = _run_shell(
            f"git ls-remote origin {ref}", timeout=15)
        if raw:
            sha = raw.split()[0].strip()
            if sha:
                return sha
    if wt is not None:
        sha = head_sha(wt)
        return sha or None
    return None


def _git_tip_pair(unit: S.Unit, wt: Optional[Path],
                  default_branch: str
                  ) -> Tuple[Optional[str], Optional[str], bool]:
    tip = _resolve_tip_sha(unit, wt)
    if not tip:
        return None, None, False
    if wt is None:
        contained = _compare_commits(
            unit.repo, default_branch, tip)
        return tip, None, contained
    default_tip = _git_in(wt, "rev-parse", f"origin/{default_branch}",
                          timeout=10) or None
    if not default_tip:
        return tip, None, False
    return tip, default_tip, _is_ancestor(wt, tip, default_tip)


def _is_ancestor(wt: Path, tip: str, target: str) -> bool:
    try:
        out = subprocess.run(
            ["git", "-C", str(wt), "merge-base", "--is-ancestor",
             tip, target],
            capture_output=True, text=True, timeout=10)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    return out.returncode == 0


def _compare_commits(repo: str, base: str, tip: str) -> bool:
    """True when tip is reachable from base (tip is ancestor of base)."""
    cmd = f"gh api repos/{repo}/compare/{base}...{tip} -q .status"
    status = _run_shell(cmd, timeout=25)
    return status in ("behind", "identical")


def _scan_tier_a(store: Path, unit: S.Unit, tip: str,
                 default_branch: str,
                 wt: Optional[Path]) -> Optional[S.MergedVia]:
    template = resolve_operation(store, "forge", "pr-list-merged")
    if not template:
        return None
    cmd = (template.replace("<repo>", unit.repo)
           .replace("<branch>", default_branch))
    raw = _run_shell(cmd, timeout=30)
    if not raw:
        return None
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list):
        return None
    matches: List[S.MergedVia] = []
    for item in items:
        mc = item.get("mergeCommit") or {}
        merge_sha = mc.get("oid") if isinstance(mc, dict) else None
        head = item.get("headRefName") or default_branch
        num = item.get("number")
        if not merge_sha:
            continue
        if wt is not None:
            contained = _is_ancestor(wt, tip, merge_sha)
        else:
            contained = _compare_commits(
                unit.repo, merge_sha, tip)
        if contained:
            matches.append(S.MergedVia(head, tip, num))
    if not matches:
        return None
    return min(matches, key=lambda m: m.pr or 0)


def detect_shipped_elsewhere(
        unit: S.Unit, ws: S.Workstream, store: Path, *,
        pr_state: Optional[Dict[str, Optional[S.PR]]] = None
        ) -> S.MergeDetectResult:
    if S.is_merged(unit):
        return S.MergeDetectResult("already-merged")
    status_tpl = resolve_operation(store, "forge", "pr-status")
    if not status_tpl or ":" in status_tpl.split()[0]:
        return S.MergeDetectResult("unknown-forge")
    if pr_state is None:
        pr_state = gather_pr_state(ws, store, branches={unit.branch})
    ledger_pr = pr_state.get(unit.branch)
    ledger_state = (ledger_pr.state if ledger_pr else None)
    had_ledger_pr = ledger_pr is not None
    default_branch = _run_forge_simple(store, "default-branch", unit.repo)
    if not default_branch:
        return S.MergeDetectResult("unknown-forge")
    wt = locate_worktree(store, unit.branch, unit.repo)
    tip, default_tip, is_ancestor = _git_tip_pair(
        unit, wt, default_branch)
    if not tip:
        return S.MergeDetectResult("unknown-git")
    dismissed = S.ship_detect_dismissed_sha(unit)
    if dismissed and tip == dismissed:
        return S.MergeDetectResult("dismissed")
    if wt is not None and default_tip is None:
        return S.MergeDetectResult("unknown-git")
    tier_a = _scan_tier_a(store, unit, tip, default_branch, wt)
    inp = S.MergeDetectInput(
        tip_sha=tip,
        default_tip_sha=default_tip or "",
        ledger_pr_state=ledger_state,
        tasks_total=unit.tasks_total,
        had_ledger_pr=had_ledger_pr,
        tier_a_match=tier_a,
        is_ancestor=is_ancestor,
        default_branch=default_branch,
    )
    return S.decide_merged_via(inp)


def scan_reconcile_overlay(
        ws: S.Workstream, store: Path, *,
        budget_s: float = 8.0) -> Dict[str, S.ReconcileOverlay]:
    """Read-only ship scan for live non-merged units."""
    deadline = time.monotonic() + budget_s
    pr_state = gather_pr_state(ws, store)
    overlay: Dict[str, S.ReconcileOverlay] = {}
    for u in ws.units:
        if time.monotonic() > deadline:
            break
        if u.dropped or S.is_merged(u):
            continue
        result = detect_shipped_elsewhere(
            u, ws, store, pr_state=pr_state)
        if not S._overlay_outcome_gates(result.outcome):
            continue
        overlay[u.slug] = S.ReconcileOverlay(
            u.slug, result.outcome, result.record)
    return overlay


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


def current_branch(cwd: Optional[Path] = None) -> Optional[str]:
    """HEAD branch in cwd, or None when detached / not a git repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=5)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if out.returncode != 0:
        return None
    br = (out.stdout or "").strip()
    if not br or br == "HEAD":
        return None
    return br


_REPO_SCP = re.compile(r"^[^@]+@[^:]+:(.+?)(?:\.git)?$")
_REPO_HTTPS = re.compile(r"(?:https?|ssh)://[^/]+/(.+?)(?:\.git)?/?$")


def _normalize_repo_url(url: str) -> Optional[str]:
    url = (url or "").strip()
    if not url:
        return None
    m = _REPO_SCP.match(url)
    if m:
        return m.group(1).lower()
    m = _REPO_HTTPS.match(url)
    if m:
        return m.group(1).lower()
    if "/" in url and "://" not in url and "@" not in url:
        return url.removesuffix(".git").lower()
    return None


def current_repo(cwd: Optional[Path] = None) -> Optional[str]:
    """Normalized org/repo from origin, or None."""
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=5)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if out.returncode != 0:
        return None
    return _normalize_repo_url((out.stdout or "").strip())


def resolve_branch(store: Path, branch: str) -> List[Tuple[str, str]]:
    """Ledger units whose branch= matches — (ws_id, slug) pairs."""
    hits = []
    for ws_id in list_workstreams(store):
        units = S.parse_units((store / ws_id / "units.md").read_text("utf-8"))
        for u in units:
            if u.branch == branch:
                hits.append((ws_id, u.slug))
    return hits


def infer_workstream(store: Path, branch: Optional[str] = None
                     ) -> Optional[str]:
    """Workstream owning the cwd branch's ledger unit, when unique.

    Same locate as ws-backlog / ws-resume: match `git` HEAD (or an
    explicit `branch`) against ledger `branch=` across the store.
    Returns None when missing, ambiguous, or unmatched.
    """
    br = branch if branch is not None else current_branch()
    if not br:
        return None
    ws_ids = list(dict.fromkeys(w for w, _ in resolve_branch(store, br)))
    return ws_ids[0] if len(ws_ids) == 1 else None


def resolve_args(store: Path, args: List[str]) -> Tuple[str, Optional[str]]:
    """Return (ws_id, unit_slug|None). Raises Pick when the caller must
    choose. A workstream matches by full id or date-stripped slug; else a
    lone token falls through to the unit bare-slug resolver. With no args
    and multiple workstreams, the cwd branch selects when it matches
    exactly one ledger unit (SPEC Command scope)."""
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
    inferred = infer_workstream(store)
    if inferred:
        return inferred, None
    raise Pick("MANY_WORKSTREAMS " + ", ".join(all_ws))


# ---------------------------------------------------------------------------
# Worktree locate + git drift helpers (ws-resume detect_split)
# ---------------------------------------------------------------------------

def _parse_git_worktree_porcelain(text: str, branch: str) -> Optional[Path]:
    want = f"refs/heads/{branch}"
    path: Optional[str] = None
    for line in text.splitlines():
        if line.startswith("worktree "):
            path = line.split(" ", 1)[1].strip()
        elif line.startswith("branch ") and line.strip().endswith(want):
            if path:
                return Path(path)
        elif line == "":
            path = None
    return None


def locate_worktree(store: Path, branch: str, repo: str) -> Optional[Path]:
    """Resolved worktree path for *branch*, or None when missing."""
    template = resolve_operation(store, "worktree-management", "locate")
    if not template:
        return None
    cmd = _fill(template, branch, repo)
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True,
                             text=True, timeout=15)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    stdout = out.stdout.strip()
    if stdout.startswith("worktree ") or "\nworktree " in stdout:
        return _parse_git_worktree_porcelain(stdout, branch)
    p = Path(stdout.splitlines()[0].strip())
    return p if p.is_dir() else None


def _git_in(worktree: Path, *args: str, timeout: int = 15) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(worktree), *args],
            capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if out.returncode != 0:
        return None
    return (out.stdout or "").strip()


def commits_ahead(worktree: Path, base: str) -> Optional[int]:
    """Commits on HEAD not in ``origin/<base>``; None when git fails."""
    raw = _git_in(worktree, "rev-list", "--count", f"origin/{base}..HEAD")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def head_sha(worktree: Path) -> str:
    return _git_in(worktree, "rev-parse", "HEAD", timeout=10) or ""
