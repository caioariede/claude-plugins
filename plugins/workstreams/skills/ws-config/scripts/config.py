#!/usr/bin/env python3
"""ws-config — deterministic flavor-config engine.

Renders show/list from the merged INI layers, performs validated
surgical writes (set / add / set-overrides) on <store>/flavors.ini,
and reconciles the spec-watch hook script on every run — including
after a failed verb, so healing never depends on typing the command
right. The skill runs this and relays the output; the session
settles only the `?` marks (skill deps, prose-vs-missing-tool) and
runs the interactive offer from the OFFER lines (prefix-addressed —
their position in the output carries no meaning).

Usage: config.py [show | set <group> <flavor> | set-config <key> <value>
                  | add <group> <flavor> | set-overrides <path> | list [group]]
Exit 2 with a machine-readable first stderr token (UNKNOWN_GROUP,
UNKNOWN_FLAVOR, ALREADY_EXISTS, BAD_ARGS, BAD_STORE) when the caller
must correct the request or repair the store file.
"""

from __future__ import annotations

import configparser
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = PLUGIN_ROOT / "hooks" / "spec-watch.sh"

MARK = {"ok": "✓", "maybe": "?", "stub": "✗"}

# Flavor names land in INI section headers and shell-adjacent contexts;
# globs are substituted into a double-quoted sh string. Both charsets
# exclude quotes, whitespace, and expansion characters by construction.
FLAVOR_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
SPEC_GLOB_RE = re.compile(r"[A-Za-z0-9_*?./\[\]-]+")
SET_CONFIG_KEYS = frozenset({"agent"})
SET_CONFIG_PREFIXES = ("cheap-model.", "frontier-model.",
                       "cheap-model-handoff.")
INTERNAL_CONFIG_KEYS = frozenset({"superpowers-prewalk-activated-at"})


class Fail(Exception):
    """User-correctable error; str() starts with the machine token."""


# ---------------------------------------------------------------------------
# Availability (SPEC §Flavors, Availability)
# ---------------------------------------------------------------------------

def flavor_state(ops: Dict[str, str], group: str):
    """(verdict, notes) — verdict 'ok'|'maybe'|'stub'. Notes carry the
    rendered `?` annotations the session must settle. A 'ws' dep is a
    bundled ws-* skill and never a mark."""
    notes: List[str] = []
    verdict = "ok"
    for kind, val in C.flavor_deps(ops, group):
        if kind == "missing-op":
            return "stub", [f"stub (empty op: {val})"]
        if kind == "skill":
            verdict = "maybe"
            notes.append(f"? requires skill {val} (verify in session)")
        elif kind == "shell" and not shutil.which(val):
            verdict = "maybe"
            notes.append(f'? unresolved head "{val}" '
                         "(prose or missing tool)")
    return verdict, notes


def _effective_ops(store: Path, group: str,
                   flavor: str) -> Tuple[Dict[str, str], Optional[str]]:
    return C.effective_flavor_ops(store, group, flavor)


def _hook_companion_lints(ops: Dict[str, str]) -> List[str]:
    """Orphaned hook companions after merge."""
    notes: List[str] = []
    for k in ops:
        if not k.startswith("hook-") or "." not in k:
            continue
        base = k.split(".")[0]
        if not (ops.get(base) or "").strip():
            notes.append(f"orphan hook companion {k} (no base {base})")
    return notes


def _unknown_active_groups(store: Path) -> List[str]:
    unknown: List[str] = []
    cp = C._load_ini(store / "flavors.ini")
    if cp.has_section("active"):
        for g in cp.options("active"):
            if g not in C.CORE_OPS:
                unknown.append(g)
    ov = C.overrides_path(store)
    if ov is not None and ov.exists():
        ocp = C._load_ini(ov)
        if ocp.has_section("active"):
            for g in ocp.options("active"):
                if g not in C.CORE_OPS:
                    unknown.append(g)
    return sorted(set(unknown))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _hook_lines(ops: Dict[str, str]) -> List[str]:
    out = []
    # A choices-mode hook may define no base instruction at all, so the
    # hook's own name comes from any key it owns, dotted or not.
    for h in sorted({k.split(".")[0] for k in ops if k.startswith("hook-")}):
        prompt = ops.get(f"{h}.prompt")
        prefix = f"{h}.choices."
        # Merged-key order is the picker's order — the first choice is
        # the safe one, so the listing must not re-sort it.
        names = [k[len(prefix):] for k in ops
                 if k.startswith(prefix) and not k.endswith(".desc")]
        if prompt and names:
            opts = " · ".join(
                f"{n}: {ops.get(prefix + n + '.desc', n)}" for n in names)
            out.append(f'{h} — "{prompt}" ({opts})')
        elif prompt:
            out.append(f'{h} — "{prompt}" (yes/no)')
        else:
            out.append(f"{h} (unconditional)")
    return out


def _layers_line(store: Path) -> str:
    parts = ["built-in ✓"]
    parts.append("store ✓" if (store / "flavors.ini").exists()
                 else "store — (absent)")
    ov = C.overrides_path(store)
    if ov is None:
        parts.append("overrides — (not set)")
    elif ov.exists() and os.access(ov, os.R_OK):
        parts.append(f"overrides ✓ ({ov})")
    else:
        parts.append(f"overrides ✗ UNREADABLE ({ov}) — layer skipped")
    return "layers: " + " · ".join(parts)


def cmd_show(store: Path) -> int:
    lines = ["workstream flavors — effective [active]", ""]
    offers: List[str] = []
    for unk in _unknown_active_groups(store):
        lines.append(f"warning: unknown [active] group {unk!r} — "
                     "ignored (legacy config?)")
    agent = C.resolve_agent(store)
    pinned = C.config_value(store, "agent")
    if agent:
        lines.append(f"agent: {agent}"
                     + (" (pinned)" if pinned else " (detected)"))
    for req in C.prewalk_model_requirements(store):
        lines.append(f"required: {req}")
    for rec in C.prewalk_model_recommended(store):
        lines.append(f"recommended: {rec}")
    if C.prewalk_enabled(store) and pinned:
        cheap = C.cheap_model(store, pinned)
        frontier = C.frontier_model(store, pinned)
        if cheap:
            lines.append(f"cheap-model ({pinned}): {cheap}")
        if frontier:
            lines.append(f"frontier-model ({pinned}): {frontier}")
    lines.append("")
    for group in C.CORE_OPS:
        flavor, prov = C.active_flavor(store, group)
        known = C.known_flavors(store, group)
        prov_txt = "default" if prov == "default" else f"explicit, {prov}"
        lines.append(f"{group}: {flavor}  ({prov_txt})")
        if flavor not in known:
            lines.append(f"  ✗ {flavor} (active but not defined in any "
                         f"layer — fix with ws-config set {group} "
                         "<flavor>)")
        active_ops: Dict[str, str] = {}
        active_err: Optional[str] = None
        for f in known:
            ops, err = _effective_ops(store, group, f)
            if f == flavor:
                active_ops, active_err = ops, err
            if err:
                verdict, notes = "stub", [f"stub (extends: {err})"]
            else:
                verdict, notes = flavor_state(ops, group)
            ext = C.flavor_has_extends(store, group, f)
            ext_mark = " extends" if ext else ""
            lines.append(f"  {MARK[verdict]} {f}{ext_mark}")
            lines += [f"      {n}" for n in notes]
            if (prov == "default" and f != C.GROUP_DEFAULTS[group]
                    and verdict != "stub" and not ext):
                offers.append(f"OFFER {group} {f}")
        if active_err:
            lines.append(f"  warning: active flavor extends error: "
                         f"{active_err}")
        for n in _hook_companion_lints(active_ops):
            lines.append(f"  warning: {n}")
        for h in _hook_lines(active_ops):
            lines.append(f"  hook: {h}")
        lines.append("")
    lines.append(_layers_line(store))
    print("\n".join(lines))
    for o in offers:
        print(o)
    return 0


def cmd_list(store: Path, group: Optional[str]) -> int:
    if group:
        _require_group(group)
    out: List[str] = []
    for g in ([group] if group else list(C.CORE_OPS)):
        active, _ = C.active_flavor(store, g)
        out.append(f"## {g}")
        for fl in C.known_flavors(store, g):
            ops, err = _effective_ops(store, g, fl)
            if err:
                verdict, notes = "stub", [f"stub (extends: {err})"]
            else:
                verdict, notes = flavor_state(ops, g)
            star = " (active)" if fl == active else ""
            out.append(f"[{g}/{fl}] {MARK[verdict]}{star}")
            own = C.flavor_ops(store, g, fl)
            if own.get("extends"):
                out.append(f"  extends = {own['extends']}")
            for k, v in ops.items():
                if k == "extends":
                    continue
                out.append(f"  {k} = {v}")
            out += [f"  {n}" for n in notes]
            out.append("")
    print("\n".join(out).rstrip())
    return 0


# ---------------------------------------------------------------------------
# Surgical store-file writes — comments and unrelated lines survive
# ---------------------------------------------------------------------------

def set_key(store: Path, section: str, key: str, value: str) -> None:
    """Replace `key = …` inside [section], insert it into the section,
    or append the section — touching nothing else in the file. Targets
    the LAST occurrence of the section and of the key, mirroring
    configparser's duplicate-merge (last wins), so the written value is
    always the effective one. Section names match exactly, unstripped,
    for the same reader-parity reason."""
    f = store / "flavors.ini"
    lines = (f.read_text("utf-8").splitlines(keepends=True)
             if f.exists() else [])
    sec_re = re.compile(r"^\[(.+)\]\s*$")
    key_re = re.compile(rf"^\s*{re.escape(key)}\s*=")
    last_start = None
    for i, line in enumerate(lines):
        m = sec_re.match(line)
        if m and m.group(1) == section:
            last_start = i
    if last_start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if lines:
            lines.append("\n")
        lines += [f"[{section}]\n", f"{key} = {value}\n"]
    else:
        end = len(lines)
        for j in range(last_start + 1, len(lines)):
            if sec_re.match(lines[j]):
                end = j
                break
        key_idx = None
        for j in range(last_start + 1, end):
            if key_re.match(lines[j]):
                key_idx = j
        if key_idx is not None:
            lines[key_idx] = f"{key} = {value}\n"
        else:
            if not lines[end - 1].endswith("\n"):
                lines[end - 1] += "\n"
            lines.insert(end, f"{key} = {value}\n")
    store.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(lines), "utf-8")


def _require_group(group: str) -> None:
    if group not in C.CORE_OPS:
        raise Fail(f"UNKNOWN_GROUP '{group}'; groups: "
                   + ", ".join(C.CORE_OPS))


def _require_set_config_key(key: str) -> None:
    if key in SET_CONFIG_KEYS or key in INTERNAL_CONFIG_KEYS:
        return
    if any(key.startswith(p) for p in SET_CONFIG_PREFIXES):
        return
    raise Fail(f"BAD_ARGS unknown config key {key!r}")


def cmd_set_config(store: Path, key: str, value: str) -> int:
    _require_set_config_key(key)
    set_key(store, "config", key, value)
    print(f"[config] {key} = {value}")
    return 0


def _maybe_record_prewalk_activation(store: Path, group: str,
                                     flavor: str) -> None:
    if group == "spec-driven-development" and flavor == "superpowers-prewalk":
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        set_key(store, "config", "superpowers-prewalk-activated-at", ts)


def cmd_set(store: Path, group: str, flavor: str) -> int:
    _require_group(group)
    known = C.known_flavors(store, group)
    if flavor not in known:
        raise Fail(f"UNKNOWN_FLAVOR '{flavor}' for {group}; known: "
                   + ", ".join(known))
    set_key(store, "active", group, flavor)
    _maybe_record_prewalk_activation(store, group, flavor)
    print(f"[active] {group} = {flavor}")
    effective, eff_prov = C.active_flavor(store, group)
    if effective != flavor:
        print(f"warning: the {eff_prov} layer sets {group} = {effective}"
              " — the store value is shadowed and will not take effect")
    ops, err = _effective_ops(store, group, flavor)
    if err:
        print(f"warning: extends error {err} — flavor unavailable")
        return 0
    verdict, notes = flavor_state(ops, group)
    if verdict == "stub":
        print("warning: " + "; ".join(notes)
              + " — fill the operations before use")
    else:
        for n in notes:
            print(n)     # `?` marks — the session settles them
    for req in C.prewalk_model_requirements(store):
        print(f"required: {req}")
    return 0


def cmd_add(store: Path, group: str, flavor: str) -> int:
    _require_group(group)
    if not FLAVOR_NAME_RE.fullmatch(flavor):
        raise Fail(f"BAD_ARGS invalid flavor name '{flavor}' — use "
                   "letters, digits, '.', '_', '-'")
    if flavor in C.known_flavors(store, group):
        raise Fail(f"ALREADY_EXISTS [{group}/{flavor}] is already "
                   "defined in some layer — a store stub would shadow "
                   "its operations per key")
    f = store / "flavors.ini"
    text = f.read_text("utf-8") if f.exists() else ""
    block = "\n".join([f"[{group}/{flavor}]"]
                      + [f"{op} =" for op in C.CORE_OPS[group]]) + "\n"
    store.mkdir(parents=True, exist_ok=True)
    sep = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
    f.write_text(text + sep + block, "utf-8")
    print(f"scaffolded [{group}/{flavor}] — fill its operations, then: "
          f"ws-config set {group} {flavor}")
    return 0


def cmd_set_overrides(store: Path, path: str) -> int:
    if not path.strip() or any(ch in path for ch in "\n\r"):
        raise Fail(f"BAD_ARGS invalid overrides path {path!r}")
    set_key(store, "config", "overrides-file", path)
    print(f"[config] overrides-file = {path}")
    if not Path(os.path.expanduser(path)).exists():
        print("warning: path does not exist yet "
              "(allowed — it may be created later)")
    return 0


# ---------------------------------------------------------------------------
# Runtime hook reconcile (SPEC §Flavors) — every run
# ---------------------------------------------------------------------------

def _reconcile_watch(store: Path, *, glob_key: str, prefix: str,
                     template: Path, placeholder: str) -> Optional[str]:
    flavor, _ = C.active_flavor(store, "spec-driven-development")
    # The active flavor's OWN glob only — a flavor without one gets no
    # script, so no rule-3 fallback here.
    ops, err = _effective_ops(store, "spec-driven-development", flavor)
    if err:
        glob = ""
    else:
        glob = (ops.get(glob_key) or "").strip()
    changed: List[str] = []
    if glob and not SPEC_GLOB_RE.fullmatch(glob):
        # Substituted into a double-quoted sh string in the hook template;
        # anything outside the safe charset could inject shell on every
        # Write/Edit. Refuse to install.
        changed.append(f"invalid {glob_key} {glob!r} ignored — script "
                       "not installed")
        glob = ""
    hooks = store / "hooks"
    keep: Optional[Path] = None
    if glob:
        keep = hooks / f"{prefix}-{flavor}.sh"
        want = template.read_text("utf-8").replace(placeholder, glob)
        if not keep.exists() or keep.read_text("utf-8") != want:
            hooks.mkdir(parents=True, exist_ok=True)
            keep.write_text(want, "utf-8")
            changed.append(f"installed {keep.name}")
        keep.chmod(0o755)
    if hooks.is_dir():
        for p in sorted(hooks.glob(f"{prefix}-*.sh")):
            if keep is None or p != keep:
                p.unlink()
                changed.append(f"removed {p.name}")
    return "; ".join(changed) if changed else None


def reconcile(store: Path) -> Optional[str]:
    return _reconcile_watch(store, glob_key="spec-glob", prefix="spec-watch",
                            template=TEMPLATE, placeholder="@SPEC_GLOB@")


def _emit_reconcile(store: Path) -> None:
    msg = reconcile(store)
    if msg:
        print(f"spec-watch reconciled: " + msg)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: List[str]) -> int:
    store = S.store_root()
    verb, args = (argv[0], argv[1:]) if argv else ("show", [])
    rc = 0
    try:
        try:
            if verb == "show" and not args:
                rc = cmd_show(store)
            elif verb == "set" and len(args) == 2:
                rc = cmd_set(store, args[0], args[1])
            elif verb == "set-config" and len(args) == 2:
                rc = cmd_set_config(store, args[0], args[1])
            elif verb == "add" and len(args) == 2:
                rc = cmd_add(store, args[0], args[1])
            elif verb == "set-overrides" and len(args) == 1:
                rc = cmd_set_overrides(store, args[0])
            elif verb == "list" and len(args) <= 1:
                rc = cmd_list(store, args[0] if args else None)
            else:
                raise Fail("BAD_ARGS unknown verb/arity: "
                           + " ".join([verb] + args))
        except Fail as e:
            print(str(e), file=sys.stderr)
            rc = 2
        # Every run heals the spec-watch script, a failed verb included.
        # OFFER lines are prefix-addressed (^OFFER), so output order is
        # free and the reconcile message may land after them.
        _emit_reconcile(store)
    except configparser.Error as e:
        print("BAD_STORE " + str(e).replace("\n", " "), file=sys.stderr)
        return 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
