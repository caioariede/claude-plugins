"""Tests for resolve_plan_path — unit-scoped plan paths."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))

import ws_store as S  # noqa: E402


class ResolvePlanPathTests(unittest.TestCase):
    def test_tilde_design(self):
        got = S.resolve_plan_path(
            "~/.claude/specs/org/repo/2026-08-13-foo-design.md",
            "my-unit",
        )
        self.assertEqual(
            got,
            Path.home() / ".claude/specs/org/repo/my-unit-plan.md",
        )

    def test_absolute_design_without_design_suffix(self):
        got = S.resolve_plan_path("/tmp/specs/feature.md", "api-slice")
        self.assertEqual(got, Path("/tmp/specs/api-slice-plan.md"))

    def test_slug_with_hyphens(self):
        got = S.resolve_plan_path(
            "/tmp/2026-08-13-public-signing-verify-design.md",
            "signing-verify-api",
        )
        self.assertEqual(
            got,
            Path("/tmp/signing-verify-api-plan.md"),
        )

    def test_empty_design_raises(self):
        with self.assertRaises(ValueError):
            S.resolve_plan_path("", "slug")

    def test_empty_slug_raises(self):
        with self.assertRaises(ValueError):
            S.resolve_plan_path("/tmp/foo-design.md", "")


if __name__ == "__main__":
    unittest.main()
