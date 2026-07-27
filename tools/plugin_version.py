#!/usr/bin/env python3
"""plugin_version — derive a plugin's version from skill bumps.

A plugin's version bumps the same position as the
highest-severity skill version bump since the last recorded
snapshot. Patch-only skill changes bump the plugin's patch; a
single major among them bumps the plugin's major.

Usage: plugin_version.py <verb> <plugin-dir> [args]
"""

from __future__ import annotations

import re
from typing import Iterable, Tuple

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# Ordered so max() over the ranks picks the strongest bump.
RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}
BY_RANK = {v: k for k, v in RANK.items()}


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
