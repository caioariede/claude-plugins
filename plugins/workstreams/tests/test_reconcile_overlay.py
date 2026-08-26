"""Tests for reconcile overlay in decide_next."""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
import ws_store as S  # noqa: E402
from test_ws_board import mkws, pr  # noqa: E402


def load_next():
    path = ROOT / "skills" / "ws-next" / "scripts" / "next.py"
    spec = importlib.util.spec_from_file_location("next_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class OverlayRankTests(unittest.TestCase):
    def test_overlay_suppresses_resume_for_tier_b(self):
        stale = S.Unit(slug="stale", branch="stale", tasks_total=2,
                       tasks_done=1)
        good = S.Unit(slug="good", branch="good", tasks_total=2, tasks_done=1)
        overlay = {
            "stale": S.ReconcileOverlay(
                "stale", "tier-b",
                S.MergedVia("main", "abc", None)),
        }
        d = S.decide_next(mkws([stale, good]), overlay=overlay)
        self.assertEqual(d.moves[0].unit, "good")
        self.assertFalse(any(m.unit == "stale" for m in d.moves))

    def test_reconcile_pending_when_suggest_blocked(self):
        merged = S.Unit(slug="m", tasks_total=1, tasks_done=1,
                        pr=pr(1, "MERGED"))
        stale = S.Unit(slug="stale", branch="stale", tasks_total=2,
                       tasks_done=2,
                       pr=pr(2, "OPEN", False, "main"))
        overlay = {
            "stale": S.ReconcileOverlay(
                "stale", "tier-b",
                S.MergedVia("main", "abc", None)),
        }
        ws = mkws([merged, stale], design="~/x-design.md")
        d = S.decide_next(ws, overlay=overlay)
        self.assertEqual(d.rule, "reconcile-pending")
        self.assertTrue(d.proposable or d.design)
        self.assertEqual(len(d.reconcile_candidates), 1)

    def test_unknown_forge_overlay_does_not_gate(self):
        u = S.Unit(slug="a", tasks_total=1, tasks_done=1, pr=pr(1, "MERGED"))
        overlay = {"x": S.ReconcileOverlay("x", "unknown-forge", None)}
        ws = mkws([u], wfs=[S.Followup("WF1", "later", checked=False)])
        self.assertEqual(S.decide_next(ws, overlay=overlay).rule, "suggest")

    def test_covered_annotates_reconcile_pending(self):
        stale = S.Unit(slug="stale", title="old work", branch="stale",
                       tasks_total=2, tasks_done=2,
                       pr=pr(2, "OPEN", False, "main"))
        overlay = {
            "stale": S.ReconcileOverlay(
                "stale", "tier-b",
                S.MergedVia("main", "abc", None)),
        }
        ws = mkws([stale], design="~/x-design.md")
        d = S.decide_next(ws, overlay=overlay)
        self.assertTrue(any("(reconcile pending)" in c for c in d.covered))


class NextRenderTests(unittest.TestCase):
    def test_reconcile_candidates_block(self):
        next_mod = load_next()
        d = S.Decision(
            rule="reconcile-pending",
            headline="reconcile before proposing — 1 unit(s) may have shipped elsewhere",
            reconcile_candidates=[
                S.ReconcileOverlay("stale", "tier-b",
                                   S.MergedVia("main", "abc", None)),
            ],
        )
        out = next_mod.render_decision(d)
        self.assertIn("ReconcileCandidates:", out)
        self.assertIn("stale", out)
        self.assertIn("outcome=tier-b", out)


if __name__ == "__main__":
    unittest.main()
