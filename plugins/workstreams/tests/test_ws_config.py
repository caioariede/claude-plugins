"""Regression suite for the ws-config engine (config.py + the ws_cli
flavor helpers). config.py is driven as a subprocess with a controlled
PATH and XDG_DATA_HOME so availability probing and store writes are
exercised end-to-end; pure helpers are imported directly, as
test_ws_board.py does. Stdlib-only (unittest).

Run: python3 -m unittest discover -s plugins/workstreams/tests
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "skills" / "ws-config" / "scripts" / "config.py"
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
import ws_cli as C  # noqa: E402


def store_at(base):
    store = Path(base) / "workstreams"
    store.mkdir(parents=True, exist_ok=True)
    return store


def run_config(base, *args, tools=()):
    """Run config.py against <base>/workstreams with a PATH holding
    exactly `tools` (stub executables) — availability is env-driven."""
    fakebin = Path(base) / "bin"
    fakebin.mkdir(exist_ok=True)
    for t in tools:
        exe = fakebin / t
        exe.write_text("#!/bin/sh\nexit 0\n")
        exe.chmod(0o755)
    env = {"PATH": str(fakebin), "HOME": str(base),
           "XDG_DATA_HOME": str(base)}
    return subprocess.run([sys.executable, str(CONFIG), *args],
                          capture_output=True, text=True, timeout=30,
                          env=env)


class HelperTest(unittest.TestCase):
    """ws_cli flavor helpers, imported directly."""

    def test_active_flavor_default_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            self.assertEqual(C.active_flavor(store, "forge"),
                             ("gh", "default"))

    def test_active_flavor_store_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "[active]\nworktree-management = wmx\n", "utf-8")
            self.assertEqual(C.active_flavor(store, "worktree-management"),
                             ("wmx", "store"))

    def test_active_flavor_overrides_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            ov = Path(td) / "ov.ini"
            ov.write_text("[active]\nforge = gh\n", "utf-8")
            (store / "flavors.ini").write_text(
                f"[config]\noverrides-file = {ov}\n", "utf-8")
            self.assertEqual(C.active_flavor(store, "forge"),
                             ("gh", "overrides"))

    def test_known_flavors_default_first(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            wt = C.known_flavors(store, "worktree-management")
            self.assertEqual(wt[0], "git-worktree")
            self.assertIn("wmx", wt)

    def test_flavor_ops_has_no_default_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "[worktree-management/custom]\ncreate =\n", "utf-8")
            ops = C.flavor_ops(store, "worktree-management", "custom")
            self.assertEqual(ops, {"create": ""})  # no git-worktree keys

    def test_flavor_deps_classification(self):
        deps = C.flavor_deps(
            {"plan": "superpowers:writing-plans",
             "execute": "work the first unchecked task directly",
             "ship": ""},
            "spec-driven-development")
        self.assertIn(("skill", "superpowers:writing-plans"), deps)
        self.assertIn(("shell", "work"), deps)
        self.assertIn(("missing-op", "ship"), deps)

    def test_flavor_deps_ignores_hooks_and_spec_glob(self):
        deps = C.flavor_deps(
            {"create": "wmx worktree create <branch>",
             "remove": "wmx worktree remove <branch>",
             "locate": "wmx worktree path <branch>",
             "hook-ws-start-after": "someothertool open <branch>",
             "spec-glob": "*x/*.md"},
            "worktree-management")
        self.assertEqual(deps, [("shell", "wmx")])

    def test_overrides_path(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            self.assertIsNone(C.overrides_path(store))
            (store / "flavors.ini").write_text(
                "[config]\noverrides-file = /nope/x.ini\n", "utf-8")
            self.assertEqual(C.overrides_path(store), Path("/nope/x.ini"))


if __name__ == "__main__":
    unittest.main()
