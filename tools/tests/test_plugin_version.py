"""Regression suite for tools/plugin_version.py, the plugin version
derivation engine. Pure helpers are imported directly; the CLI is
driven as a subprocess against temp plugin trees, as
plugins/workstreams/tests/test_ws_config.py does. Stdlib-only
(unittest).

Run: python3 -m unittest discover -s tools/tests
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "plugin_version.py"
sys.path.insert(0, str(ROOT / "tools"))
import plugin_version as P  # noqa: E402


class ParseTest(unittest.TestCase):
    def test_parses_three_parts(self):
        self.assertEqual(P.parse("0.15.3"), (0, 15, 3))

    def test_parses_multi_digit(self):
        self.assertEqual(P.parse("10.150.2"), (10, 150, 2))

    def test_fmt_round_trips(self):
        self.assertEqual(P.fmt(P.parse("1.2.3")), "1.2.3")

    def test_rejects_two_parts(self):
        with self.assertRaises(P.Fail) as cm:
            P.parse("0.15")
        self.assertTrue(str(cm.exception).startswith("BAD_VERSION"))

    def test_rejects_four_parts(self):
        with self.assertRaises(P.Fail):
            P.parse("0.15.3.1")

    def test_rejects_non_numeric(self):
        with self.assertRaises(P.Fail):
            P.parse("0.15.x")

    def test_rejects_prerelease_suffix(self):
        with self.assertRaises(P.Fail):
            P.parse("1.0.0-rc1")

    def test_rejects_empty(self):
        with self.assertRaises(P.Fail):
            P.parse("")

    def test_rejects_negative(self):
        with self.assertRaises(P.Fail):
            P.parse("0.-1.0")


class SeverityTest(unittest.TestCase):
    def test_none_when_equal(self):
        self.assertEqual(P.severity((0, 15, 0), (0, 15, 0)), "none")

    def test_patch(self):
        self.assertEqual(P.severity((0, 15, 0), (0, 15, 1)), "patch")

    def test_minor(self):
        self.assertEqual(P.severity((0, 15, 0), (0, 16, 0)), "minor")

    def test_major(self):
        self.assertEqual(P.severity((0, 15, 0), (1, 0, 0)), "major")

    def test_minor_wins_when_patch_resets(self):
        self.assertEqual(P.severity((0, 9, 3), (0, 10, 0)), "minor")

    def test_major_wins_when_minor_and_patch_reset(self):
        self.assertEqual(P.severity((0, 9, 3), (1, 0, 0)), "major")

    def test_skipping_multiple_minors_is_still_minor(self):
        self.assertEqual(P.severity((0, 9, 0), (0, 11, 0)), "minor")

    def test_backwards_patch_raises(self):
        with self.assertRaises(P.Fail) as cm:
            P.severity((0, 15, 1), (0, 15, 0))
        self.assertTrue(str(cm.exception).startswith("BACKWARDS"))

    def test_backwards_minor_raises(self):
        with self.assertRaises(P.Fail):
            P.severity((0, 16, 0), (0, 15, 9))


class WorstTest(unittest.TestCase):
    def test_empty_is_none(self):
        self.assertEqual(P.worst([]), "none")

    def test_all_none(self):
        self.assertEqual(P.worst(["none", "none"]), "none")

    def test_minor_beats_patch(self):
        self.assertEqual(P.worst(["patch", "minor"]), "minor")

    def test_order_independent(self):
        self.assertEqual(P.worst(["minor", "patch"]), "minor")

    def test_major_beats_everything(self):
        self.assertEqual(
            P.worst(["patch", "minor", "major", "none"]), "major")


class ApplyBumpTest(unittest.TestCase):
    def test_none_leaves_version_alone(self):
        self.assertEqual(P.apply_bump((0, 15, 3), "none"), (0, 15, 3))

    def test_patch_increments_patch(self):
        self.assertEqual(P.apply_bump((0, 15, 3), "patch"), (0, 15, 4))

    def test_minor_resets_patch(self):
        self.assertEqual(P.apply_bump((0, 15, 3), "minor"), (0, 16, 0))

    def test_major_resets_minor_and_patch(self):
        self.assertEqual(P.apply_bump((0, 15, 3), "major"), (1, 0, 0))


class SeriesTest(unittest.TestCase):
    def test_drops_patch(self):
        self.assertEqual(P.series("0.15.3"), "0.15")

    def test_zero_minor(self):
        self.assertEqual(P.series("1.0.0"), "1.0")

    def test_does_not_confuse_multi_digit_minor(self):
        self.assertEqual(P.series("0.150.0"), "0.150")


def make_plugin(base, plugin_version, skills, snapshot=None):
    """Build a minimal plugin tree. `skills` maps name -> version.
    `snapshot` is written only when given; pass a dict shaped like
    {"plugin": "0.1.0", "skills": {...}}.
    """
    root = Path(base) / "plugins" / "demo"
    (root / ".claude-plugin").mkdir(parents=True)
    write_json(root / ".claude-plugin" / "plugin.json",
               {"name": "demo", "version": plugin_version})
    for name, version in skills.items():
        d = root / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\nname: %s\nmetadata:\n  version: \"%s\"\n---\n\nBody.\n"
            % (name, version))
    if snapshot is not None:
        write_json(root / ".claude-plugin" / "skill-versions.json",
                   snapshot)
    return root


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def read_json(path):
    return json.loads(Path(path).read_text())


def run_cli(*args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)] + [str(a) for a in args],
        capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


class ReadSkillVersionsTest(unittest.TestCase):
    def test_reads_every_skill(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.2.0",
                               {"ws": "0.2.0", "ws-next": "0.1.3"})
            self.assertEqual(P.read_skill_versions(root),
                             {"ws": "0.2.0", "ws-next": "0.1.3"})

    def test_missing_version_field_names_the_file(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.1.0", {"ws": "0.1.0"})
            (root / "skills" / "ws" / "SKILL.md").write_text(
                "---\nname: ws\n---\n\nNo version here.\n")
            with self.assertRaises(P.Fail) as cm:
                P.read_skill_versions(root)
            msg = str(cm.exception)
            self.assertTrue(msg.startswith("NO_VERSION"))
            self.assertIn("ws/SKILL.md", msg)

    def test_malformed_version_names_the_file(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.1.0", {"ws": "0.1"})
            with self.assertRaises(P.Fail) as cm:
                P.read_skill_versions(root)
            self.assertIn("ws/SKILL.md", str(cm.exception))

    def test_skill_dir_without_skill_md_is_ignored(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.1.0", {"ws": "0.1.0"})
            (root / "skills" / "scratch").mkdir()
            self.assertEqual(P.read_skill_versions(root), {"ws": "0.1.0"})


class ExpectedVersionTest(unittest.TestCase):
    def snap(self, plugin, skills):
        return {"plugin": plugin, "skills": skills}

    def test_no_change_holds_the_version(self):
        snap = self.snap("0.15.0", {"ws": "0.15.0", "ws-next": "0.9.0"})
        got = P.expected_version(snap, {"ws": "0.15.0",
                                        "ws-next": "0.9.0"})
        self.assertEqual(got, ("0.15.0", "none"))

    def test_patch_only(self):
        snap = self.snap("0.15.0", {"ws": "0.15.0", "ws-next": "0.9.0"})
        got = P.expected_version(snap, {"ws": "0.15.0",
                                        "ws-next": "0.9.1"})
        self.assertEqual(got, ("0.15.1", "patch"))

    def test_minor_wins_over_patch(self):
        snap = self.snap("0.15.0", {"ws": "0.15.0", "ws-next": "0.9.0",
                                    "ws-board": "0.5.4"})
        got = P.expected_version(snap, {"ws": "0.15.0",
                                        "ws-next": "0.10.0",
                                        "ws-board": "0.5.5"})
        self.assertEqual(got, ("0.16.0", "minor"))

    def test_major_wins_over_minor(self):
        snap = self.snap("0.15.0", {"ws": "0.15.0", "ws-next": "0.9.0"})
        got = P.expected_version(snap, {"ws": "1.0.0",
                                        "ws-next": "0.10.0"})
        self.assertEqual(got, ("1.0.0", "major"))

    def test_added_skill_is_minor(self):
        snap = self.snap("0.15.0", {"ws": "0.15.0"})
        got = P.expected_version(snap, {"ws": "0.15.0",
                                        "ws-audit": "0.1.0"})
        self.assertEqual(got, ("0.16.0", "minor"))

    def test_removed_skill_is_major(self):
        snap = self.snap("0.15.0", {"ws": "0.15.0",
                                    "ws-board": "0.5.4"})
        got = P.expected_version(snap, {"ws": "0.15.0"})
        self.assertEqual(got, ("1.0.0", "major"))

    def test_backwards_skill_names_the_skill(self):
        snap = self.snap("0.15.0", {"ws": "0.15.0"})
        with self.assertRaises(P.Fail) as cm:
            P.expected_version(snap, {"ws": "0.14.0"})
        msg = str(cm.exception)
        self.assertTrue(msg.startswith("BACKWARDS"))
        self.assertIn("ws", msg)


class CheckTest(unittest.TestCase):
    def test_consistent_tree_passes(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0", {"ws": "0.15.0", "ws-next": "0.9.0"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0",
                                     "ws-next": "0.9.0"}})
            rc, out, err = run_cli("check", root)
            self.assertEqual(rc, 0, err)
            self.assertIn("0.15.0", out)

    def test_drifted_tree_exits_1_and_names_the_command(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0", {"ws": "0.15.0", "ws-next": "0.9.1"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0",
                                     "ws-next": "0.9.0"}})
            rc, out, err = run_cli("check", root)
            self.assertEqual(rc, 1)
            self.assertIn("0.15.1", err)
            self.assertIn("bump", err)

    def test_absent_snapshot_exits_1_and_names_bump(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.15.0", {"ws": "0.15.0"})
            rc, out, err = run_cli("check", root)
            self.assertEqual(rc, 1)
            self.assertIn("bump", err)

    def test_plugin_below_snapshot_exits_2(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.14.0", {"ws": "0.15.0"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0"}})
            rc, out, err = run_cli("check", root)
            self.assertEqual(rc, 2)
            self.assertIn("BACKWARDS", err)

    def test_unknown_verb_exits_2(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.1.0", {"ws": "0.1.0"})
            rc, out, err = run_cli("frobnicate", root)
            self.assertEqual(rc, 2)
            self.assertIn("BAD_ARGS", err)

    def test_missing_plugin_dir_exits_2(self):
        rc, out, err = run_cli("check", "/nonexistent/plugin")
        self.assertEqual(rc, 2)
        self.assertIn("BAD_PLUGIN", err)


class BumpTest(unittest.TestCase):
    def test_seeds_an_absent_snapshot_without_bumping(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.15.0",
                               {"ws": "0.15.0", "ws-next": "0.9.0"})
            rc, out, err = run_cli("bump", root)
            self.assertEqual(rc, 0, err)
            self.assertIn("seeded", out)
            snap = read_json(root / ".claude-plugin"
                             / "skill-versions.json")
            self.assertEqual(snap["plugin"], "0.15.0")
            self.assertEqual(snap["skills"],
                             {"ws": "0.15.0", "ws-next": "0.9.0"})
            self.assertEqual(
                read_json(root / ".claude-plugin"
                          / "plugin.json")["version"], "0.15.0")

    def test_no_op_when_nothing_moved(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0", {"ws": "0.15.0"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0"}})
            rc, out, err = run_cli("bump", root)
            self.assertEqual(rc, 0, err)
            self.assertEqual(
                read_json(root / ".claude-plugin"
                          / "plugin.json")["version"], "0.15.0")

    def test_running_twice_is_idempotent(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0", {"ws": "0.15.1"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0"}})
            run_cli("bump", root)
            run_cli("bump", root)
            self.assertEqual(
                read_json(root / ".claude-plugin"
                          / "plugin.json")["version"], "0.15.1")

    def test_patch_bump_writes_both_files(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0", {"ws": "0.15.0", "ws-next": "0.9.1"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0",
                                     "ws-next": "0.9.0"}})
            rc, out, err = run_cli("bump", root)
            self.assertEqual(rc, 0, err)
            self.assertEqual(
                read_json(root / ".claude-plugin"
                          / "plugin.json")["version"], "0.15.1")
            snap = read_json(root / ".claude-plugin"
                             / "skill-versions.json")
            self.assertEqual(snap["plugin"], "0.15.1")
            self.assertEqual(snap["skills"]["ws-next"], "0.9.1")

    def test_minor_beats_patch_across_skills(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0",
                {"ws-next": "0.10.0", "ws-board": "0.5.5"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws-next": "0.9.0",
                                     "ws-board": "0.5.4"}})
            rc, out, err = run_cli("bump", root)
            self.assertEqual(rc, 0, err)
            self.assertEqual(
                read_json(root / ".claude-plugin"
                          / "plugin.json")["version"], "0.16.0")

    def test_bump_reports_each_moved_skill(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0",
                {"ws-next": "0.10.0", "ws-board": "0.5.4"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws-next": "0.9.0",
                                     "ws-board": "0.5.4"}})
            rc, out, err = run_cli("bump", root)
            self.assertEqual(rc, 0, err)
            self.assertIn("ws-next", out)
            self.assertIn("minor", out)
            self.assertIn("0.16.0", out)

    def test_bump_leaves_check_passing(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0", {"ws": "0.16.0"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0"}})
            run_cli("bump", root)
            rc, out, err = run_cli("check", root)
            self.assertEqual(rc, 0, err)

    def test_backwards_skill_exits_2_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0", {"ws": "0.14.0"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0"}})
            rc, out, err = run_cli("bump", root)
            self.assertEqual(rc, 2)
            self.assertIn("BACKWARDS", err)
            self.assertEqual(
                read_json(root / ".claude-plugin"
                          / "plugin.json")["version"], "0.15.0")

    def test_preserves_other_plugin_json_keys(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0", {"ws": "0.15.1"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0"}})
            path = root / ".claude-plugin" / "plugin.json"
            write_json(path, {"name": "demo", "description": "d",
                              "version": "0.15.0",
                              "author": {"name": "A"}})
            run_cli("bump", root)
            got = read_json(path)
            self.assertEqual(list(got),
                             ["name", "description", "version",
                              "author"])
            self.assertEqual(got["author"], {"name": "A"})
            self.assertEqual(got["version"], "0.15.1")


class SetTest(unittest.TestCase):
    def test_writes_both_files_and_leaves_check_passing(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0", {"ws": "0.15.0"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0"}})
            rc, out, err = run_cli("set", root, "1.0.0")
            self.assertEqual(rc, 0, err)
            self.assertEqual(
                read_json(root / ".claude-plugin"
                          / "plugin.json")["version"], "1.0.0")
            snap = read_json(root / ".claude-plugin"
                             / "skill-versions.json")
            self.assertEqual(snap["plugin"], "1.0.0")
            rc, out, err = run_cli("check", root)
            self.assertEqual(rc, 0, err)

    def test_rejects_a_malformed_version(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0", {"ws": "0.15.0"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0"}})
            rc, out, err = run_cli("set", root, "1.0")
            self.assertEqual(rc, 2)
            self.assertIn("BAD_VERSION", err)

    def test_rejects_going_backwards(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(
                base, "0.15.0", {"ws": "0.15.0"},
                snapshot={"plugin": "0.15.0",
                          "skills": {"ws": "0.15.0"}})
            rc, out, err = run_cli("set", root, "0.14.0")
            self.assertEqual(rc, 2)
            self.assertIn("BACKWARDS", err)


GUIDE_HTML = (
    '<html><body>\n'
    '<h1>Guide</h1>\n'
    '<p class="version">Version %s · July 2026</p>\n'
    '</body></html>\n'
)


class VersionVerbTest(unittest.TestCase):
    def test_prints_full_semver(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.15.3", {"ws": "0.15.3"})
            rc, out, err = run_cli("version", root)
            self.assertEqual(rc, 0, err)
            self.assertEqual(out.strip(), "0.15.3")


class SeriesVerbTest(unittest.TestCase):
    def test_prints_major_minor(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.15.3", {"ws": "0.15.3"})
            rc, out, err = run_cli("series", root)
            self.assertEqual(rc, 0, err)
            self.assertEqual(out.strip(), "0.15")


class CheckGuideTest(unittest.TestCase):
    def guide(self, root, stamp):
        path = root / "guide.html"
        path.write_text(GUIDE_HTML % stamp)
        return path

    def test_matching_full_version_passes(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.15.0", {"ws": "0.15.0"})
            html = self.guide(root, "0.15.0")
            rc, out, err = run_cli("check-guide", root, html)
            self.assertEqual(rc, 0, err)

    def test_patch_mismatch_exits_1(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.15.7", {"ws": "0.15.7"})
            html = self.guide(root, "0.15.0")
            rc, out, err = run_cli("check-guide", root, html)
            self.assertEqual(rc, 1)
            self.assertIn("0.15.7", err)
            self.assertIn("gen-guide-pdf", err)

    def test_series_only_stamp_exits_1(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.15.0", {"ws": "0.15.0"})
            html = self.guide(root, "0.15")
            rc, out, err = run_cli("check-guide", root, html)
            self.assertEqual(rc, 1)
            self.assertIn("0.15.0", err)

    def test_stale_minor_exits_1(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.16.0", {"ws": "0.16.0"})
            html = self.guide(root, "0.15.0")
            rc, out, err = run_cli("check-guide", root, html)
            self.assertEqual(rc, 1)
            self.assertIn("0.16.0", err)
            self.assertIn("gen-guide-pdf", err)

    def test_multi_digit_minor_is_not_a_prefix_match(self):
        """`grep -q "Version 0.15"` passes on `Version 0.150`. Exact
        token comparison is what closes that hole."""
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.15.0", {"ws": "0.15.0"})
            html = self.guide(root, "0.150")
            rc, out, err = run_cli("check-guide", root, html)
            self.assertEqual(rc, 1)
            self.assertIn("0.15.0", err)

    def test_absent_stamp_exits_2(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.15.0", {"ws": "0.15.0"})
            html = root / "guide.html"
            html.write_text("<html><body>No stamp.</body></html>\n")
            rc, out, err = run_cli("check-guide", root, html)
            self.assertEqual(rc, 2)
            self.assertIn("NO_STAMP", err)

    def test_absent_html_exits_2(self):
        with tempfile.TemporaryDirectory() as base:
            root = make_plugin(base, "0.15.0", {"ws": "0.15.0"})
            rc, out, err = run_cli("check-guide", root,
                                   root / "nope.html")
            self.assertEqual(rc, 2)
            self.assertIn("MISSING_FILE", err)


if __name__ == "__main__":
    unittest.main()
