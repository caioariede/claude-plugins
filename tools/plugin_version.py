#!/usr/bin/env python3
"""plugin_version — derive a plugin's version from skill bumps.

A plugin's version bumps the same position as the
highest-severity skill version bump since the last recorded
snapshot. Patch-only skill changes bump the plugin's patch; a
single major among them bumps the plugin's major.

Usage: plugin_version.py <verb> <plugin-dir> [args]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# Ordered so max() over the ranks picks the strongest bump.
RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}
BY_RANK = {v: k for k, v in RANK.items()}

PLUGIN_JSON = ".claude-plugin/plugin.json"
SNAPSHOT_JSON = ".claude-plugin/skill-versions.json"

# Matches `  version: "0.15.0"` in a SKILL.md metadata block.
SKILL_VERSION_RE = re.compile(
    r'^\s*version:\s*"([^"]*)"\s*$', re.MULTILINE)

# Matches the guide's version line, which carries major.minor only.
STAMP_RE = re.compile(r'<p class="version">Version\s+([0-9.]+)')


class Fail(Exception):
    """Malformed input. Message starts with a machine-readable token."""


def parse(s: str) -> Tuple[int, int, int]:
    m = VERSION_RE.match(s)
    if not m:
        raise Fail("BAD_VERSION not X.Y.Z: " + repr(s))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def fmt(v: Tuple[int, int, int]) -> str:
    return "%d.%d.%d" % v


def series(version: str) -> str:
    major, minor, _ = parse(version)
    return "%d.%d" % (major, minor)


def severity(old: Tuple[int, int, int],
             new: Tuple[int, int, int]) -> str:
    if new < old:
        raise Fail("BACKWARDS %s -> %s" % (fmt(old), fmt(new)))
    if new[0] != old[0]:
        return "major"
    if new[1] != old[1]:
        return "minor"
    if new[2] != old[2]:
        return "patch"
    return "none"


def worst(sevs: Iterable[str]) -> str:
    return BY_RANK[max([RANK[s] for s in sevs] + [0])]


def apply_bump(cur: Tuple[int, int, int],
               sev: str) -> Tuple[int, int, int]:
    if sev == "major":
        return (cur[0] + 1, 0, 0)
    if sev == "minor":
        return (cur[0], cur[1] + 1, 0)
    if sev == "patch":
        return (cur[0], cur[1], cur[2] + 1)
    return cur


def _read_json(path: Path) -> Dict[str, object]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise Fail("MISSING_FILE " + str(path))
    except ValueError as e:
        raise Fail("BAD_JSON %s: %s" % (path, e))


def _write_json(path: Path, obj: Dict[str, object]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def read_skill_versions(plugin_dir: Path) -> Dict[str, str]:
    skills = plugin_dir / "skills"
    if not skills.is_dir():
        raise Fail("BAD_PLUGIN no skills/ under " + str(plugin_dir))
    out = {}
    for md in sorted(skills.glob("*/SKILL.md")):
        m = SKILL_VERSION_RE.search(md.read_text())
        rel = md.relative_to(plugin_dir)
        if not m:
            raise Fail("NO_VERSION no version: field in " + str(rel))
        try:
            parse(m.group(1))
        except Fail as e:
            raise Fail("%s in %s" % (str(e), rel))
        out[md.parent.name] = m.group(1)
    return out


def read_plugin_version(plugin_dir: Path) -> str:
    path = plugin_dir / PLUGIN_JSON
    if not path.is_file():
        raise Fail("BAD_PLUGIN no plugin.json under " + str(plugin_dir))
    raw = _read_json(path).get("version")
    if not isinstance(raw, str):
        raise Fail("BAD_PLUGIN version is not a string in " + str(path))
    parse(raw)
    return raw


def read_snapshot(plugin_dir: Path) -> Optional[Dict[str, object]]:
    path = plugin_dir / SNAPSHOT_JSON
    if not path.is_file():
        return None
    snap = _read_json(path)
    if not isinstance(snap.get("plugin"), str) \
            or not isinstance(snap.get("skills"), dict):
        raise Fail("BAD_SNAPSHOT needs plugin + skills keys: "
                   + str(path))
    return snap


def expected_version(snapshot: Dict[str, object],
                     live: Dict[str, str]) -> Tuple[str, str]:
    """The version the plugin should carry, and the severity that got
    it there. A skill present only in the snapshot was removed, which
    breaks its callers; one present only in the tree is new."""
    was = snapshot["skills"]
    sevs = []
    for name in sorted(set(was) | set(live)):
        if name not in live:
            sevs.append("major")
        elif name not in was:
            sevs.append("minor")
        else:
            try:
                sevs.append(severity(parse(was[name]),
                                     parse(live[name])))
            except Fail as e:
                raise Fail("%s for skill %s" % (str(e), name))
    overall = worst(sevs)
    base = parse(str(snapshot["plugin"]))
    return (fmt(apply_bump(base, overall)), overall)


def cmd_check(plugin_dir: Path) -> int:
    live = read_skill_versions(plugin_dir)
    have = read_plugin_version(plugin_dir)
    snap = read_snapshot(plugin_dir)
    if snap is None:
        print("no %s; run: just bump-plugin-version" % SNAPSHOT_JSON,
              file=sys.stderr)
        return 1
    if parse(have) < parse(str(snap["plugin"])):
        raise Fail("BACKWARDS plugin.json %s is below snapshot %s"
                   % (have, snap["plugin"]))
    want, overall = expected_version(snap, live)
    if have == want:
        print("plugin version OK (%s)" % have)
        return 0
    print("plugin version drift: plugin.json=%s, expected %s "
          "(highest skill bump: %s)" % (have, want, overall),
          file=sys.stderr)
    print("run: just bump-plugin-version", file=sys.stderr)
    return 1


def write_plugin_version(plugin_dir: Path, version: str) -> None:
    path = plugin_dir / PLUGIN_JSON
    doc = _read_json(path)
    doc["version"] = version
    _write_json(path, doc)


def write_snapshot(plugin_dir: Path, plugin_version: str,
                   skills: Dict[str, str]) -> None:
    _write_json(plugin_dir / SNAPSHOT_JSON,
                {"plugin": plugin_version,
                 "skills": {k: skills[k] for k in sorted(skills)}})


def cmd_bump(plugin_dir: Path) -> int:
    live = read_skill_versions(plugin_dir)
    have = read_plugin_version(plugin_dir)
    snap = read_snapshot(plugin_dir)
    if snap is None:
        write_snapshot(plugin_dir, have, live)
        print("seeded %s at plugin %s (%d skills), no bump"
              % (SNAPSHOT_JSON, have, len(live)))
        return 0
    if parse(have) < parse(str(snap["plugin"])):
        raise Fail("BACKWARDS plugin.json %s is below snapshot %s"
                   % (have, snap["plugin"]))
    want, overall = expected_version(snap, live)
    was = snap["skills"]
    for name in sorted(set(was) | set(live)):
        if name not in live:
            print("  - %-12s %s -> removed  major" % (name, was[name]))
        elif name not in was:
            print("  + %-12s %s          minor" % (name, live[name]))
        elif was[name] != live[name]:
            print("    %-12s %s -> %s  %s"
                  % (name, was[name], live[name],
                     severity(parse(was[name]), parse(live[name]))))
    if overall == "none":
        print("no skill version moved; plugin stays %s" % have)
        return 0
    write_plugin_version(plugin_dir, want)
    write_snapshot(plugin_dir, want, live)
    print("highest = %s; plugin %s -> %s" % (overall, have, want))
    return 0


def cmd_set(plugin_dir: Path, version: str) -> int:
    parse(version)
    live = read_skill_versions(plugin_dir)
    have = read_plugin_version(plugin_dir)
    if parse(version) < parse(have):
        raise Fail("BACKWARDS %s is below plugin.json %s"
                   % (version, have))
    write_plugin_version(plugin_dir, version)
    write_snapshot(plugin_dir, version, live)
    print("plugin %s -> %s (snapshot rebased)" % (have, version))
    return 0


def read_stamp(path: Path) -> str:
    if not path.is_file():
        raise Fail("MISSING_FILE " + str(path))
    m = STAMP_RE.search(path.read_text())
    if not m:
        raise Fail("NO_STAMP no version line in " + str(path))
    return m.group(1)


def cmd_series(plugin_dir: Path) -> int:
    print(series(read_plugin_version(plugin_dir)))
    return 0


def cmd_check_guide(plugin_dir: Path, html: Path) -> int:
    want = series(read_plugin_version(plugin_dir))
    have = read_stamp(html)
    if have == want:
        print("guide version OK (%s)" % have)
        return 0
    print("guide version drift: expected %s, stamp has %s"
          % (want, have), file=sys.stderr)
    print("run: just gen-guide-pdf", file=sys.stderr)
    return 1


def main(argv: List[str]) -> int:
    try:
        if len(argv) < 2:
            raise Fail("BAD_ARGS usage: plugin_version.py <verb> "
                       "<plugin-dir> [args]")
        verb, rest = argv[0], argv[1:]
        plugin_dir = Path(rest[0])
        args = rest[1:]
        if verb == "check" and not args:
            return cmd_check(plugin_dir)
        if verb == "bump" and not args:
            return cmd_bump(plugin_dir)
        if verb == "set" and len(args) == 1:
            return cmd_set(plugin_dir, args[0])
        if verb == "series" and not args:
            return cmd_series(plugin_dir)
        if verb == "check-guide" and len(args) == 1:
            return cmd_check_guide(plugin_dir, Path(args[0]))
        raise Fail("BAD_ARGS unknown verb/arity: " + " ".join(argv))
    except Fail as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
