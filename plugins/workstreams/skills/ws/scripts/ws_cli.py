"""Store/forge access shared by ws-* command scripts (ws-board, ws-next).

The impure half of the contract: locating workstreams, resolving args to a
target, resolving the active `forge` flavor from the merged INI layers, and
running its `pr-status` per unit in parallel. Kept out of ws_store.py so the
engine there stays pure (parse + derive) and unit-testable without a shell.
"""

from __future__ import annotations

import concurrent.futures
import configparser
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import ws_store as S

BUILTIN_FLAVORS = Path(__file__).resolve().parent.parent / "references" / "flavors.ini"

# Placeholder values are interpolated into flavor shell lines; reject
# metacharacters so a poisoned ledger cannot inject through _fill.
_SAFE_BRANCH = re.compile(r"^[a-zA-Z0-9._/-]+$")
_SAFE_REPO = re.compile(r"^[a-zA-Z0-9._/-]+$")
_SAFE_REF = re.compile(r"^[a-zA-Z0-9._/-]+$")
_SHELL_META = re.compile(r"[|;&<>$`\\]|&&|\|\|")


def _validate_branch(branch: str) -> None:
    if not branch or not _SAFE_BRANCH.fullmatch(branch):
        raise ValueError(f"unsafe branch: {branch!r}")


def _validate_repo(repo: str) -> None:
    if not repo or not _SAFE_REPO.fullmatch(repo):
        raise ValueError(f"unsafe repo: {repo!r}")


def _validate_ref(ref: str) -> None:
    if not ref or not _SAFE_REF.fullmatch(ref):
        raise ValueError(f"unsafe ref: {ref!r}")


def _run_argv(argv: List[str], timeout: int = 25) -> Optional[str]:
    if not argv:
        return None
    try:
        out = subprocess.run(argv, capture_output=True, text=True,
                             timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if out.returncode != 0:
        return None
    return (out.stdout or "").strip() or None


def _run_text_cmd(cmd: str, timeout: int = 25) -> Optional[str]:
    """Run a single argv vector — no shell. Pipes/redirects are rejected."""
    if _SHELL_META.search(cmd):
        return None
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return None
    return _run_argv(argv, timeout=timeout)


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


def _merge_inherited_ops(parent: Dict[str, str],
                         child: Dict[str, str]) -> Dict[str, str]:
    """Parent keys first; child overrides keep parent insertion order."""
    out = dict(parent)
    for k, v in child.items():
        out[k] = v
    return out


def effective_flavor_ops(store: Path, group: str, flavor: str,
                         _chain: Optional[frozenset] = None
                         ) -> Tuple[Dict[str, str], Optional[str]]:
    """Effective ops after layer merge and single-level ``extends``.

    Returns ``(ops, error)``. ``error`` is a machine token when
    inheritance is broken; ``ops`` is then child-only (fail closed).
    """
    if _chain is None:
        _chain = frozenset()
    if flavor in _chain:
        return {}, "EXTENDS_CYCLE"
    child = flavor_ops(store, group, flavor)
    parent_name = (child.pop("extends", None) or "").strip()
    if not parent_name:
        return child, None
    if parent_name == flavor:
        return child, "EXTENDS_SELF"
    if parent_name not in known_flavors(store, group):
        return child, "EXTENDS_UNKNOWN"
    parent_own = flavor_ops(store, group, parent_name)
    if (parent_own.get("extends") or "").strip():
        return child, "EXTENDS_TRANSITIVE"
    parent_ops, parent_err = effective_flavor_ops(
        store, group, parent_name, _chain | {flavor})
    if parent_err:
        return child, parent_err
    return _merge_inherited_ops(parent_ops, child), None


def _resolve_op_from_effective(store: Path, group: str, flavor: str,
                               op: str) -> Optional[str]:
    ops, err = effective_flavor_ops(store, group, flavor)
    if err:
        if op in ops:
            return ops[op]
        return None
    if op in ops:
        return ops[op]
    default = GROUP_DEFAULTS[group]
    if flavor != default:
        dops, derr = effective_flavor_ops(store, group, default)
        if not derr and op in dops:
            return dops[op]
    return None


def resolve_operation(store: Path, group: str, op: str) -> Optional[str]:
    """SPEC §Flavors resolution: effective active flavor op, then group
    default when inheritance is valid."""
    flavor = active_flavor(store, group)[0]
    return _resolve_op_from_effective(store, group, flavor, op)


# ---------------------------------------------------------------------------
# Flavor introspection (ws-config engine) — provenance, known flavors,
# per-flavor merged ops WITHOUT the default fallback, and tool deps
# (SPEC §Flavors, Availability).
# ---------------------------------------------------------------------------

GROUP_DEFAULTS = {"worktree-management": "git-worktree",
                  "spec-driven-development": "none",
                  "forge": "gh",
                  "review": "ws-critic"}

CORE_OPS = {"worktree-management": ("create", "remove", "locate"),
            "spec-driven-development": ("plan", "execute", "ship"),
            "forge": ("default-branch", "pr-status", "pr-create",
                      "pr-ready", "pr-retarget"),
            "review": ("review",)}

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


def config_value(store: Path, key: str) -> Optional[str]:
    """Merged ``[config]`` value across store layers (not overrides file)."""
    val = None
    for cp in _layers(store)[1:2]:  # store layer only
        if cp.has_option("config", key):
            val = cp.get("config", key).strip()
    return val or None


def resolve_agent(store: Path) -> Optional[str]:
    """Pinned agent id, or a runtime hint when unset."""
    pinned = config_value(store, "agent")
    if pinned:
        return pinned
    if os.environ.get("CURSOR_AGENT") or os.environ.get("CURSOR_TRACE_ID"):
        return "cursor"
    if os.environ.get("CLAUDE_CODE") or os.environ.get("CLAUDE_SESSION"):
        return "claude"
    return None


def _model_key(prefix: str, agent: Optional[str]) -> str:
    if agent:
        return f"{prefix}.{agent}"
    return prefix


def flavor_model(store: Path, prefix: str,
                 agent: Optional[str] = None) -> Optional[str]:
    """Resolve model slug from ``[config]`` (``set-config``)."""
    agent = agent or resolve_agent(store)
    if agent:
        v = config_value(store, f"{prefix}.{agent}")
        if v:
            return v
    return config_value(store, prefix)


def prewalk_model_requirements(store: Path) -> List[str]:
    """Unset ``[config]`` keys required before prewalk (pinned agent only)."""
    if not prewalk_enabled(store):
        return []
    pinned = config_value(store, "agent")
    if not pinned:
        return ["set-config agent <claude|cursor|codex>"]
    if cheap_model(store, pinned):
        return []
    return [f"set-config cheap-model.{pinned} <slug>"]


def prewalk_model_recommended(store: Path) -> List[str]:
    """Optional ``[config]`` keys shown when unset (workflow convention)."""
    if not prewalk_enabled(store):
        return []
    pinned = config_value(store, "agent")
    if not pinned or frontier_model(store, pinned):
        return []
    return [f"set-config frontier-model.{pinned} <slug> (recommended)"]


def prewalk_models_ready(store: Path) -> bool:
    return not prewalk_model_requirements(store)


def cheap_model(store: Path, agent: Optional[str] = None) -> Optional[str]:
    return flavor_model(store, "cheap-model", agent)


def frontier_model(store: Path, agent: Optional[str] = None) -> Optional[str]:
    return flavor_model(store, "frontier-model", agent)


def cheap_model_handoff(store: Path, agent: Optional[str] = None
                        ) -> Optional[str]:
    group = "spec-driven-development"
    flavor, _ = active_flavor(store, group)
    ops, err = effective_flavor_ops(store, group, flavor)
    if err:
        return None
    agent = agent or resolve_agent(store)
    key = _model_key("cheap-model-handoff", agent)
    return (ops.get(key) or ops.get("cheap-model-handoff") or "").strip() or None


def format_cheap_handoff(store: Path, agent: Optional[str] = None
                         ) -> Optional[str]:
    """Handoff template with ``{cheap}`` filled from ``[config]``."""
    template = cheap_model_handoff(store, agent)
    if not template:
        return None
    cheap = cheap_model(store, agent)
    if not cheap:
        return template
    return template.replace("{cheap}", cheap)


def prewalk_enabled(store: Path) -> bool:
    group = "spec-driven-development"
    flavor, _ = active_flavor(store, group)
    ops, err = effective_flavor_ops(store, group, flavor)
    if err:
        return False
    return (ops.get("prewalk") or "").strip().lower() == "on"


def superpowers_prewalk_activated_at(store: Path) -> Optional[str]:
    return config_value(store, "superpowers-prewalk-activated-at")


def review_enabled(store: Path) -> bool:
    flavor, _ = active_flavor(store, "review")
    ops, err = effective_flavor_ops(store, "review", flavor)
    return not err and (ops.get("review") or "").strip() == "ws-critic"


def ws_critic_activated_at(store: Path) -> Optional[str]:
    return config_value(store, "ws-critic-activated-at")


def collect_skip_extensions(
        skip_extension: Optional[List[str]] = None) -> Set[str]:
    """CLI ``--skip-extension`` values → phase names for resume ctx."""
    import extension_runner as ER  # noqa: E402

    return ER.expand_skip_tokens(set(skip_extension or []))


def unit_tree_digest(store: Path, u: S.Unit) -> Optional[str]:
    """Short git diff digest for extension-phase receipts (e.g. critic)."""
    if not u.branch or not u.repo:
        return None
    wt = locate_worktree(store, u.branch, u.repo)
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


def _extension_meta(store: Path, u: S.Unit) -> Dict[str, Dict[str, object]]:
    import extension_runner as ER  # noqa: E402

    meta: Dict[str, Dict[str, object]] = {}
    for ext in ER.load_extensions():
        key = ext.get("activated_at_key")
        if not key:
            continue
        activated = config_value(store, key)
        meta[ext["id"]] = {
            "activated_at": activated,
            "grandfather": S._should_grandfather_prewalk(u, activated),
        }
    return meta


def build_extension_ctx(
        store: Path, u: S.Unit, *,
        headless: bool = False,
        skip_extensions: Optional[Set[str]] = None) -> dict:
    """Read-only context for extension handler subprocesses."""
    skip = skip_extensions or set()
    plan_path = S.latest_plan_log_path(u)
    plan_digest = S.plan_file_digest(plan_path) if plan_path else None
    return {
        "kind": "unit",
        "headless": headless,
        "skip": sorted(skip),
        "unit": {
            "slug": u.slug,
            "tasks_total": u.tasks_total,
            "tasks_done": u.tasks_done,
            "followups_complete": u.followups_complete,
            "log": [[ts, kind, payload]
                    for ts, kind, payload in u.log],
        },
        "artifacts": {
            "plan_path": plan_path,
            "plan_digest": plan_digest,
            "tree_digest": unit_tree_digest(store, u),
            "models_ready": prewalk_models_ready(store),
        },
        "extensions": _extension_meta(store, u),
    }


def flavor_has_extends(store: Path, group: str, flavor: str) -> bool:
    return bool((flavor_ops(store, group, flavor).get("extends") or "").strip())


# ---------------------------------------------------------------------------
# PR state gathering — run the resolved pr-status per branch, in parallel
# ---------------------------------------------------------------------------

def _fill(template: str, branch: str, repo: str) -> Optional[str]:
    try:
        if "<branch>" in template:
            _validate_branch(branch)
        if "<repo>" in template:
            _validate_repo(repo)
    except ValueError:
        return None
    return template.replace("<branch>", branch).replace("<repo>", repo)


def _run_pr_status(cmd: str) -> Optional[S.PR]:
    raw = _run_text_cmd(cmd, timeout=25)
    if not raw:
        return None  # no PR for this branch (or forge unreachable)
    try:
        data = json.loads(raw)
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
    jobs = {u.branch: cmd for u in ws.units
            if u.branch and (branches is None or u.branch in branches)
            if (cmd := _fill(template, u.branch, u.repo))}
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


@dataclass
class ResolvedTarget:
    ws_id: str
    slug: str
    kind: str   # "unit" | "spike"


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
    """Bare-slug resolver: (ws_id, slug) matches across unit + spike ledgers."""
    return [(t.ws_id, t.slug) for t in resolve_target_hits(store, token)]


def resolve_target_hits(store: Path, token: str) -> List[ResolvedTarget]:
    hits: List[ResolvedTarget] = []
    for ws_id in list_workstreams(store):
        units_path = store / ws_id / "units.md"
        spikes_path = store / ws_id / "spikes.md"
        if units_path.exists():
            for u in S.parse_units(units_path.read_text("utf-8")):
                if u.slug == token:
                    hits.append(ResolvedTarget(ws_id, token, "unit"))
        if spikes_path.exists():
            for sp in S.parse_spikes(spikes_path.read_text("utf-8")):
                if sp.slug == token:
                    hits.append(ResolvedTarget(ws_id, token, "spike"))
    return hits


def resolve_target(store: Path, token: str) -> ResolvedTarget:
    hits = resolve_target_hits(store, token)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise Pick(f"NO_MATCH no unit or spike named '{token}'")
    opts = ", ".join(f"{h.kind}:{h.ws_id}:{h.slug}" for h in hits)
    raise Pick(f"AMBIGUOUS '{token}' matches: {opts}")


def resolve_kind_in_ws(store: Path, ws_id: str, slug: str,
                       fallback: Optional[str] = None) -> str:
    """Kind for `slug` within one workstream; raises Pick on ambiguity."""
    hits = [h for h in resolve_target_hits(store, slug) if h.ws_id == ws_id]
    if len(hits) == 1:
        return hits[0].kind
    if len(hits) > 1:
        opts = ", ".join(f"{h.kind}:{h.slug}" for h in hits)
        raise Pick(f"AMBIGUOUS '{slug}' in {ws_id}: {opts}")
    if fallback is not None:
        return fallback
    raise Pick(f"NO_MATCH no unit or spike {slug!r} in {ws_id}")


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
        kinds = resolve_target_hits(store, tok)
        if len(kinds) == 1:
            t = kinds[0]
            return t.ws_id, t.slug
        opts = ", ".join(f"{h.kind}:{h.ws_id}:{h.slug}" for h in kinds)
        raise Pick(f"AMBIGUOUS '{tok}' matches: {opts}")
    if not all_ws:
        raise Pick("NO_STORE no workstreams found in the store")
    if len(all_ws) == 1:
        return all_ws[0], None
    inferred = infer_workstream(store)
    if inferred:
        return inferred, None
    raise Pick("MANY_WORKSTREAMS " + ", ".join(all_ws))


# ---------------------------------------------------------------------------
# Worktree locate + git helpers
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


def _locate_from_wmx_json(branch: str) -> Optional[Path]:
    raw = _run_argv(["wmx", "worktree", "list", "--json"], timeout=15)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    items = data if isinstance(data, list) else data.get("worktrees", [])
    want = branch if branch.startswith("refs/heads/") else f"refs/heads/{branch}"
    for wt in items:
        if not isinstance(wt, dict):
            continue
        b = wt.get("branch") or ""
        if b in (branch, want) or b.endswith(f"/{branch}"):
            path = wt.get("path")
            if path:
                p = Path(path)
                return p if p.is_dir() else None
    return None


def locate_worktree(store: Path, branch: str, repo: str) -> Optional[Path]:
    """Resolved worktree path for *branch*, or None when missing."""
    try:
        _validate_branch(branch)
    except ValueError:
        return None
    template = resolve_operation(store, "worktree-management", "locate")
    if not template:
        return None
    if template.strip().startswith("wmx worktree list --json"):
        return _locate_from_wmx_json(branch)
    cmd = _fill(template, branch, repo)
    if cmd is None:
        return None
    stdout = _run_text_cmd(cmd, timeout=15)
    if not stdout:
        return None
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


def head_sha(worktree: Path) -> str:
    return _git_in(worktree, "rev-parse", "HEAD", timeout=10) or ""
