"""Regression suite for tools/plugin_version.py, the plugin version
derivation engine. Pure helpers are imported directly; the CLI is
driven as a subprocess against temp plugin trees, as
plugins/workstreams/tests/test_ws_config.py does. Stdlib-only
(unittest).

Run: python3 -m unittest discover -s tools/tests
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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


if __name__ == "__main__":
    unittest.main()
