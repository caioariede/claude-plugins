"""Tests for decide_merged_via and detect_shipped_elsewhere."""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
import ws_store as S  # noqa: E402
import ws_cli as C  # noqa: E402


def inp(**kw):
    defaults = dict(
        tip_sha="aaa",
        default_tip_sha="bbb",
        ledger_pr_state="OPEN",
        tasks_total=2,
        had_ledger_pr=True,
        tier_a_match=None,
        is_ancestor=False,
        default_branch="main",
    )
    defaults.update(kw)
    return S.MergeDetectInput(**defaults)


class DecideMergedViaTests(unittest.TestCase):
    def test_tier_a_when_match(self):
        rec = S.MergedVia("feat-x", "aaa", 99)
        r = S.decide_merged_via(inp(tier_a_match=rec))
        self.assertEqual(r.outcome, "tier-a")
        self.assertEqual(r.record, rec)

    def test_tier_b_when_ancestor_and_tasks(self):
        r = S.decide_merged_via(inp(
            tip_sha="old", default_tip_sha="new",
            is_ancestor=True, tasks_total=2,
        ))
        self.assertEqual(r.outcome, "tier-b")
        self.assertEqual(r.record.sha, "old")
        self.assertEqual(r.record.branch, "main")

    def test_not_shipped_when_tip_is_default(self):
        r = S.decide_merged_via(inp(
            tip_sha="same", default_tip_sha="same",
            is_ancestor=True, tasks_total=2,
        ))
        self.assertEqual(r.outcome, "not-shipped")

    def test_not_shipped_when_not_ancestor(self):
        r = S.decide_merged_via(inp(is_ancestor=False, tasks_total=2))
        self.assertEqual(r.outcome, "not-shipped")

    def test_tier_b_requires_tasks_or_had_pr(self):
        r = S.decide_merged_via(inp(
            tip_sha="old", default_tip_sha="new",
            is_ancestor=True, tasks_total=0, had_ledger_pr=False,
        ))
        self.assertEqual(r.outcome, "not-shipped")


class DetectShippedElsewhereTests(unittest.TestCase):
    def _unit(self):
        u = S.Unit(slug="spike", branch="spike", repo="o/r",
                   tasks_total=2, tasks_done=2)
        u.log = [("2026-01-01T00:00Z", "created", "base=main")]
        return u

    @mock.patch("ws_cli.resolve_operation", return_value="gh cmd")
    @mock.patch("ws_cli._scan_tier_a")
    @mock.patch("ws_cli._git_tip_pair")
    @mock.patch("ws_cli._run_forge_simple")
    def test_tier_a_result(self, forge, pair, scan, _resolve):
        u = self._unit()
        ws = S.Workstream(ws_id="w", name="w", units=[u])
        forge.return_value = "main"
        pair.return_value = ("abc123", "def456", True)
        scan.return_value = S.MergedVia("feat-x", "abc123", 12)
        pr_state = {"spike": S.PR(number=1, state="OPEN",
                                   is_draft=False, base="main")}
        result = C.detect_shipped_elsewhere(
            u, ws, Path("/tmp/store"), pr_state=pr_state)
        self.assertEqual(result.outcome, "tier-a")
        self.assertEqual(result.record.branch, "feat-x")
        self.assertEqual(result.record.sha, "abc123")
        self.assertEqual(result.record.pr, 12)

    @mock.patch("ws_cli.resolve_operation", return_value=None)
    def test_unknown_forge_when_no_template(self, _resolve):
        u = self._unit()
        ws = S.Workstream(ws_id="w", name="w", units=[u])
        result = C.detect_shipped_elsewhere(u, ws, Path("/tmp/store"))
        self.assertEqual(result.outcome, "unknown-forge")


if __name__ == "__main__":
    unittest.main()
