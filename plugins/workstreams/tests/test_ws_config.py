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


class ShowTest(unittest.TestCase):
    def test_defaults_render_with_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            store_at(td)
            p = run_config(td, "show", tools=("git", "gh"))
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("worktree-management: git-worktree  (default)",
                          p.stdout)
            self.assertIn("forge: gh  (default)", p.stdout)

    def test_explicit_store_active_marked(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "[active]\nworktree-management = wmx\n", "utf-8")
            p = run_config(td, "show", tools=("git", "gh", "wmx"))
            self.assertIn("worktree-management: wmx  (explicit, store)",
                          p.stdout)

    def test_missing_shell_dep_marks_unresolved(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "[active]\nworktree-management = wmx\n", "utf-8")
            p = run_config(td, "show", tools=("git", "gh"))  # no wmx stub
            self.assertIn('unresolved head "wmx"', p.stdout)

    def test_skill_dep_prints_check_in_session(self):
        with tempfile.TemporaryDirectory() as td:
            store_at(td)
            p = run_config(td, "show", tools=("git", "gh"))
            self.assertIn(
                "? requires skill superpowers:writing-plans "
                "(verify in session)", p.stdout)

    def test_stub_flavor_rendered_but_never_offered(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "[worktree-management/custom]\n"
                "create =\nremove =\nlocate =\n", "utf-8")
            p = run_config(td, "show", tools=("git", "gh"))
            self.assertIn("custom", p.stdout)
            self.assertIn("stub", p.stdout)
            self.assertNotIn("OFFER worktree-management custom", p.stdout)

    def test_unreadable_overrides_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "[config]\noverrides-file = /nope/x.ini\n", "utf-8")
            p = run_config(td, "show", tools=("git", "gh"))
            self.assertIn("UNREADABLE", p.stdout)

    def test_active_hooks_surfaced(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "[active]\nworktree-management = wmx\n", "utf-8")
            p = run_config(td, "show", tools=("git", "gh", "wmx"))
            self.assertIn("hook-ws-start-after", p.stdout)
            self.assertIn("Open <branch> in a new window?", p.stdout)


class OfferTest(unittest.TestCase):
    def test_unset_group_with_available_candidate_offers(self):
        with tempfile.TemporaryDirectory() as td:
            store_at(td)
            p = run_config(td, "show", tools=("git", "gh", "wmx"))
            self.assertIn("OFFER worktree-management wmx", p.stdout)

    def test_pending_skill_candidate_still_offered(self):
        # superpowers deps are skill ids -> '?' -> model settles, so the
        # candidate line is still emitted.
        with tempfile.TemporaryDirectory() as td:
            store_at(td)
            p = run_config(td, "show", tools=("git", "gh"))
            self.assertIn("OFFER spec-driven-development superpowers",
                          p.stdout)

    def test_explicitly_set_group_never_offers(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "[active]\nworktree-management = git-worktree\n", "utf-8")
            p = run_config(td, "show", tools=("git", "gh", "wmx"))
            self.assertNotIn("OFFER worktree-management", p.stdout)

    def test_forge_without_non_default_never_offers(self):
        with tempfile.TemporaryDirectory() as td:
            store_at(td)
            p = run_config(td, "show", tools=("git", "gh"))
            self.assertNotIn("OFFER forge", p.stdout)


class ReconcileTest(unittest.TestCase):
    def test_show_installs_for_superpowers(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "[active]\nspec-driven-development = superpowers\n",
                "utf-8")
            p = run_config(td, "show", tools=("git", "gh"))
            script = store / "hooks" / "spec-watch-superpowers.sh"
            self.assertTrue(script.exists())
            self.assertTrue(os.access(script, os.X_OK))
            content = script.read_text("utf-8")
            self.assertNotIn("@SPEC_GLOB@", content)
            self.assertIn("*specs/*-design.md", content)
            self.assertIn("installed spec-watch-superpowers.sh", p.stdout)

    def test_default_none_removes_scripts(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "hooks").mkdir()
            junk = store / "hooks" / "spec-watch-superpowers.sh"
            junk.write_text("#!/bin/sh\n", "utf-8")
            p = run_config(td, "show", tools=("git", "gh"))
            self.assertFalse(junk.exists())
            self.assertIn("removed spec-watch-superpowers.sh", p.stdout)

    def test_foreign_scripts_removed(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "[active]\nspec-driven-development = superpowers\n",
                "utf-8")
            (store / "hooks").mkdir()
            old = store / "hooks" / "spec-watch-old.sh"
            old.write_text("#!/bin/sh\n", "utf-8")
            run_config(td, "show", tools=("git", "gh"))
            self.assertFalse(old.exists())
            self.assertTrue(
                (store / "hooks" / "spec-watch-superpowers.sh").exists())

    def test_second_run_is_silent(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "[active]\nspec-driven-development = superpowers\n",
                "utf-8")
            run_config(td, "show", tools=("git", "gh"))
            p = run_config(td, "show", tools=("git", "gh"))
            self.assertNotIn("spec-watch reconciled", p.stdout)


class WriteTest(unittest.TestCase):
    def test_set_writes_active_and_preserves_comments(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            (store / "flavors.ini").write_text(
                "# my note\n[active]\n"
                "spec-driven-development = superpowers\n", "utf-8")
            p = run_config(td, "set", "worktree-management", "wmx",
                           tools=("git", "gh", "wmx"))
            self.assertEqual(p.returncode, 0, p.stderr)
            text = (store / "flavors.ini").read_text("utf-8")
            self.assertIn("# my note\n", text)
            self.assertIn("worktree-management = wmx", text)
            self.assertIn("spec-driven-development = superpowers", text)

    def test_set_replaces_existing_line_once(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            run_config(td, "set", "forge", "gh", tools=("git", "gh"))
            p = run_config(td, "set", "forge", "gh", tools=("git", "gh"))
            self.assertEqual(p.returncode, 0, p.stderr)
            text = (store / "flavors.ini").read_text("utf-8")
            self.assertEqual(text.count("forge = gh"), 1)

    def test_set_creates_file_when_absent(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            p = run_config(td, "set", "forge", "gh", tools=("git", "gh"))
            self.assertEqual(p.returncode, 0, p.stderr)
            text = (store / "flavors.ini").read_text("utf-8")
            self.assertIn("[active]", text)
            self.assertIn("forge = gh", text)

    def test_set_unknown_flavor_token_and_known_list(self):
        with tempfile.TemporaryDirectory() as td:
            store_at(td)
            p = run_config(td, "set", "forge", "nope", tools=("git", "gh"))
            self.assertEqual(p.returncode, 2)
            self.assertTrue(p.stderr.startswith("UNKNOWN_FLAVOR"),
                            p.stderr)
            self.assertIn("gh", p.stderr)

    def test_set_unknown_group_token(self):
        with tempfile.TemporaryDirectory() as td:
            store_at(td)
            p = run_config(td, "set", "nope", "gh", tools=("git", "gh"))
            self.assertEqual(p.returncode, 2)
            self.assertTrue(p.stderr.startswith("UNKNOWN_GROUP"), p.stderr)

    def test_set_unavailable_flavor_warns_but_writes(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            p = run_config(td, "set", "worktree-management", "wmx",
                           tools=("git", "gh"))  # wmx not on PATH
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("warning", p.stdout)
            self.assertIn("worktree-management = wmx",
                          (store / "flavors.ini").read_text("utf-8"))

    def test_add_appends_scaffold_without_activating(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            p = run_config(td, "add", "forge", "gitlab",
                           tools=("git", "gh"))
            self.assertEqual(p.returncode, 0, p.stderr)
            text = (store / "flavors.ini").read_text("utf-8")
            self.assertIn("[forge/gitlab]", text)
            for op in ("default-branch", "pr-status", "pr-create",
                       "pr-ready", "pr-retarget"):
                self.assertIn(f"{op} =", text)
            self.assertNotIn("[active]", text)

    def test_add_duplicate_errors(self):
        with tempfile.TemporaryDirectory() as td:
            store_at(td)
            run_config(td, "add", "forge", "gitlab", tools=("git", "gh"))
            p = run_config(td, "add", "forge", "gitlab",
                           tools=("git", "gh"))
            self.assertEqual(p.returncode, 2)
            self.assertTrue(p.stderr.startswith("ALREADY_EXISTS"),
                            p.stderr)

    def test_set_overrides_writes_and_warns_on_missing_path(self):
        with tempfile.TemporaryDirectory() as td:
            store = store_at(td)
            target = str(Path(td) / "ov.ini")
            p = run_config(td, "set-overrides", target,
                           tools=("git", "gh"))
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn(f"overrides-file = {target}",
                          (store / "flavors.ini").read_text("utf-8"))
            self.assertIn("warning", p.stdout)

    def test_bad_args_token(self):
        with tempfile.TemporaryDirectory() as td:
            store_at(td)
            p = run_config(td, "frobnicate", tools=("git", "gh"))
            self.assertEqual(p.returncode, 2)
            self.assertTrue(p.stderr.startswith("BAD_ARGS"), p.stderr)


if __name__ == "__main__":
    unittest.main()
