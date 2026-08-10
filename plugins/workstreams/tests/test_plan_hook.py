"""Regression suite for the plan-watch hook (hooks/plan-watch.sh).

Drives the real sh script via subprocess, installed into a temp
store exactly the way ws-config does it (glob substituted,
chmod +x), so the tests exercise the shipped artifact — plus the
hooks.json wiring line, read from the shipped file so the two
can't drift. Stdlib-only (unittest), matching the suite's
zero-dependency stance.

Run: python3 -m unittest discover -s plugins/workstreams/tests
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_ws_config import run_config

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "hooks" / "plan-watch.sh"
HOOKS_JSON = ROOT / "hooks" / "hooks.json"
PLAN_GLOB = "*specs/*-plan.md"


def make_store(base):
    store = Path(base) / "workstreams"
    (store / "hooks").mkdir(parents=True)
    return store


def install(store, glob=PLAN_GLOB, flavor="superpowers"):
    """The shipped reconcile: config.py installs the script when the
    active spec-driven-development flavor declares a plan-glob."""
    (store / "flavors.ini").write_text(
        "[active]\n"
        f"spec-driven-development = {flavor}\n\n"
        f"[spec-driven-development/{flavor}]\n"
        f"spec-glob = *specs/*-design.md\n"
        f"plan-glob = {glob}\n",
        "utf-8",
    )
    p = run_config(store.parent, "show")
    if p.returncode != 0:
        raise AssertionError("config.py show failed: " + p.stderr)
    script = store / "hooks" / f"plan-watch-{flavor}.sh"
    if not script.exists():
        raise AssertionError("config.py reconcile did not install "
                             + script.name)
    return script


def write_ws(store, ws_id, design=None):
    """design: None = no line at all, "" = empty line, str = path."""
    d = store / ws_id
    d.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"id: {ws_id}", f"name: {ws_id}"]
    if design is not None:
        lines.append(f"design: {design}".rstrip())
    lines += ["---", ""]
    (d / "workstream.md").write_text("\n".join(lines), "utf-8")
    return d


def write_design(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("# design\n", "utf-8")


def run_hook(script, payload):
    stdin = json.dumps(payload) if isinstance(payload, dict) else payload
    p = subprocess.run([str(script)], input=stdin, capture_output=True,
                       text=True, timeout=10)
    return p.returncode, p.stdout


def context_of(out):
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


class PlanWatchTest(unittest.TestCase):
    """The installed script: glob gate, design gate, ownership gate."""

    def test_non_matching_paths_are_silent(self):
        with tempfile.TemporaryDirectory() as td:
            script = install(make_store(td))
            for path in ("/repo/src/main.py",
                         "/repo/specs/a-plan.txt",
                         "/repo/a-plan.md"):
                rc, out = run_hook(script, {"tool_input":
                                            {"file_path": path}})
                self.assertEqual((rc, out), (0, ""), path)

    def test_unowned_plan_suggests_ws_oneshot(self):
        with tempfile.TemporaryDirectory() as td:
            store = make_store(td)
            design = f"{td}/specs/org/repo/2026-08-10-foo-design.md"
            plan = f"{td}/specs/org/repo/2026-08-10-foo-plan.md"
            write_design(design)
            script = install(store)
            rc, out = run_hook(script, {"tool_input": {"file_path": plan}})
            self.assertEqual(rc, 0)
            self.assertIn("ws-oneshot", context_of(out))
            self.assertIn(plan, context_of(out))

    def test_missing_design_is_silent(self):
        with tempfile.TemporaryDirectory() as td:
            script = install(make_store(td))
            plan = "/repo/specs/2026-08-10-foo-plan.md"
            rc, out = run_hook(script, {"tool_input": {"file_path": plan}})
            self.assertEqual((rc, out), (0, ""))

    def test_owned_design_is_silent(self):
        with tempfile.TemporaryDirectory() as td:
            store = make_store(td)
            design = f"{td}/specs/org/repo/2026-08-10-foo-design.md"
            plan = f"{td}/specs/org/repo/2026-08-10-foo-plan.md"
            write_ws(store, "2026-08-10-foo",
                     design=f"{td}/specs/org/repo/2026-08-10-foo-design.md")
            write_design(design)
            script = install(store)
            rc, out = run_hook(script, {"tool_input": {"file_path": plan}})
            self.assertEqual((rc, out), (0, ""))

    def test_custom_glob_is_honored(self):
        with tempfile.TemporaryDirectory() as td:
            script = install(make_store(td), glob="*plans/*-plan.md")
            design = f"{td}/plans/a-design.md"
            plan = f"{td}/plans/a-plan.md"
            write_design(design)
            rc, out = run_hook(script, {"tool_input": {"file_path": plan}})
            self.assertIn("ws-oneshot", out)
            rc, out = run_hook(script, {"tool_input": {
                "file_path": f"{td}/specs/a-plan.md"}})
            self.assertEqual(out, "")

    def test_garbage_stdin_is_silent(self):
        with tempfile.TemporaryDirectory() as td:
            script = install(make_store(td))
            for stdin in ("not json", "{}", ""):
                rc, out = run_hook(script, stdin)
                self.assertEqual((rc, out), (0, ""), repr(stdin))

    def test_output_is_valid_json(self):
        with tempfile.TemporaryDirectory() as td:
            store = make_store(td)
            design = f"{td}/specs/2026-08-10-x-design.md"
            plan = f"{td}/specs/2026-08-10-x-plan.md"
            write_design(design)
            script = install(store)
            rc, out = run_hook(script, {"tool_input": {"file_path": plan}})
            json.loads(out)


class PlanWiringTest(unittest.TestCase):
    """The hooks.json command: runs spec-watch then plan-watch."""

    def _command(self):
        data = json.loads(HOOKS_JSON.read_text("utf-8"))
        hook = data["hooks"]["PostToolUse"][0]
        self.assertEqual(hook["matcher"], "Write|Edit")
        return hook["hooks"][0]["command"]

    def _run(self, xdg, stdin):
        env = {"PATH": os.environ["PATH"], "HOME": "/nonexistent",
               "XDG_DATA_HOME": xdg}
        return subprocess.run(["sh", "-c", self._command()], input=stdin,
                              capture_output=True, text=True, timeout=10,
                              env=env)

    def test_not_installed_is_silent(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._run(td, '{"tool_input":{"file_path":"/x/specs/a-plan.md"}}')
            self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_plan_watch_receives_stdin_when_installed(self):
        with tempfile.TemporaryDirectory() as td:
            store = make_store(td)
            design = f"{td}/specs/2026-08-10-x-design.md"
            plan = f"{td}/specs/2026-08-10-x-plan.md"
            write_design(design)
            install(store)
            payload = json.dumps({"tool_input": {"file_path": plan}})
            p = self._run(td, payload)
            self.assertEqual(p.returncode, 0)
            self.assertIn("ws-oneshot", p.stdout)


if __name__ == "__main__":
    unittest.main()
