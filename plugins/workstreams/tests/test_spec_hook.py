"""Regression suite for the spec-watch hook (hooks/spec-watch.sh).

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
TEMPLATE = ROOT / "hooks" / "spec-watch.sh"
HOOKS_JSON = ROOT / "hooks" / "hooks.json"
GLOB = "*specs/*-design.md"


def make_store(base):
    store = Path(base) / "workstreams"
    (store / "hooks").mkdir(parents=True)
    return store


def install(store, glob=GLOB, flavor="superpowers"):
    """The shipped reconcile: config.py installs the script when the
    active spec-driven-development flavor declares a spec-glob."""
    (store / "flavors.ini").write_text(
        "[active]\n"
        f"spec-driven-development = {flavor}\n\n"
        f"[spec-driven-development/{flavor}]\n"
        f"spec-glob = {glob}\n", "utf-8")
    p = run_config(store.parent, "show")
    if p.returncode != 0:
        raise AssertionError("config.py show failed: " + p.stderr)
    script = store / "hooks" / f"spec-watch-{flavor}.sh"
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


def run_hook(script, payload):
    stdin = json.dumps(payload) if isinstance(payload, dict) else payload
    p = subprocess.run([str(script)], input=stdin, capture_output=True,
                       text=True, timeout=10)
    return p.returncode, p.stdout


def context_of(out):
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


class SpecWatchTest(unittest.TestCase):
    """The installed script: glob gate, ownership gate, message."""

    def test_non_matching_paths_are_silent(self):
        with tempfile.TemporaryDirectory() as td:
            script = install(make_store(td))
            for path in ("/repo/src/main.py",
                         "/repo/docs/notes.md",
                         "/repo/specs/a-design.txt",
                         "/repo/a-design.md"):     # not under specs/
                rc, out = run_hook(script, {"tool_input":
                                            {"file_path": path}})
                self.assertEqual((rc, out), (0, ""), path)

    def test_unowned_spec_suggests_ws_init(self):
        with tempfile.TemporaryDirectory() as td:
            script = install(make_store(td))
            path = "/repo/docs/superpowers/specs/2026-07-22-foo-design.md"
            rc, out = run_hook(script, {"tool_input": {"file_path": path}})
            self.assertEqual(rc, 0)
            data = json.loads(out)
            hso = data["hookSpecificOutput"]
            self.assertEqual(hso["hookEventName"], "PostToolUse")
            self.assertIn("ws-init", hso["additionalContext"])
            self.assertIn(path, hso["additionalContext"])

    def test_nested_specs_path_matches(self):
        # The user-preference layout: specs/<org>/<repo>/<file>.
        with tempfile.TemporaryDirectory() as td:
            script = install(make_store(td))
            path = "/home/u/.claude/specs/org/repo/2026-07-22-a-design.md"
            rc, out = run_hook(script, {"tool_input": {"file_path": path}})
            self.assertIn("ws-init", out)

    def test_owned_spec_is_silent_across_spellings(self):
        # design: recorded with ~ while the write arrives absolute;
        # basename matching makes the spelling irrelevant.
        with tempfile.TemporaryDirectory() as td:
            store = make_store(td)
            write_ws(store, "2026-07-22-a",
                     design="~/.claude/specs/org/repo/2026-07-22-a-design.md")
            script = install(store)
            path = "/Users/u/.claude/specs/org/repo/2026-07-22-a-design.md"
            rc, out = run_hook(script, {"tool_input": {"file_path": path}})
            self.assertEqual((rc, out), (0, ""))

    def test_designless_workstream_is_offered_as_home(self):
        with tempfile.TemporaryDirectory() as td:
            store = make_store(td)
            write_ws(store, "2026-07-22-a", design="/x/specs/a-design.md")
            write_ws(store, "2026-07-22-b")            # no design line
            script = install(store)
            rc, out = run_hook(script, {"tool_input": {
                "file_path": "/repo/specs/2026-07-22-new-design.md"}})
            text = context_of(out)
            self.assertIn("2026-07-22-b", text)
            self.assertIn("ws-init", text)

    def test_empty_design_line_counts_as_designless(self):
        with tempfile.TemporaryDirectory() as td:
            store = make_store(td)
            write_ws(store, "2026-07-22-a", design="")
            script = install(store)
            rc, out = run_hook(script, {"tool_input": {
                "file_path": "/repo/specs/2026-07-22-new-design.md"}})
            self.assertIn("2026-07-22-a", context_of(out))

    def test_all_owned_store_omits_attach_hint(self):
        with tempfile.TemporaryDirectory() as td:
            store = make_store(td)
            write_ws(store, "2026-07-22-a", design="/x/specs/a-design.md")
            script = install(store)
            rc, out = run_hook(script, {"tool_input": {
                "file_path": "/repo/specs/2026-07-22-new-design.md"}})
            text = context_of(out)
            self.assertIn("ws-init", text)
            self.assertNotIn("2026-07-22-a", text)

    def test_custom_glob_is_honored(self):
        with tempfile.TemporaryDirectory() as td:
            script = install(make_store(td), glob="*plans/*-spec.md")
            rc, out = run_hook(script, {"tool_input": {
                "file_path": "/repo/plans/a-spec.md"}})
            self.assertIn("ws-init", out)
            rc, out = run_hook(script, {"tool_input": {
                "file_path": "/repo/specs/a-design.md"}})
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
            write_ws(store, "2026-07-22-a")
            script = install(store)
            rc, out = run_hook(script, {"tool_input": {
                "file_path": "/repo/specs/2026-07-22-x-design.md"}})
            json.loads(out)  # must not raise


class WiringTest(unittest.TestCase):
    """The hooks.json command: constant-cost existence check that
    execs the installed script — read from the shipped file so the
    tests and the wiring can't drift."""

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
            p = self._run(td, '{"tool_input":{"file_path":"/x/specs/a-design.md"}}')
            self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_installed_script_receives_stdin(self):
        with tempfile.TemporaryDirectory() as td:
            store = make_store(td)
            install(store)
            payload = json.dumps({"tool_input": {
                "file_path": "/repo/specs/2026-07-22-x-design.md"}})
            p = self._run(td, payload)
            self.assertEqual(p.returncode, 0)
            self.assertIn("ws-init", p.stdout)


if __name__ == "__main__":
    unittest.main()
