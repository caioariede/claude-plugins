"""Eval assertions for ws-next strategy picker lanes."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-next" / "evals"))

import ws_store as S  # noqa: E402
from chain_expectations import (  # noqa: E402
    chain_offers_propose,
    chain_runs_unit_picker,
    propose_source_summary,
)
from lane_expectations import strategy_lanes  # noqa: E402
from test_ws_board import mkws, pr  # noqa: E402


class StrategyLaneEvals(unittest.TestCase):
    def test_blocking_wf_solo_first(self):
        merged = S.Unit(slug="m", title="did m", tasks_total=1,
                        tasks_done=1, pr=pr(1, "MERGED"))
        dep = S.Unit(slug="dep", needs=[S.Need("N1", "WF4")])
        ws = mkws([merged, dep],
                  wfs=[S.Followup("WF4", "harden it", checked=False)])
        d = S.decide_next(ws)
        lanes = strategy_lanes(d)
        self.assertEqual(lanes[0], "WF4 — harden it (blocks dep)")
        self.assertNotIn("Workstream follow-ups", lanes)

    def test_design_only_suggest(self):
        d = S.decide_next(mkws(design="~/specs/x-design.md"))
        lanes = strategy_lanes(d)
        self.assertEqual(lanes, ["From design spec"])

    def test_focus_before_followups(self):
        merged = S.Unit(slug="m", title="did m", tasks_total=1,
                        tasks_done=1, pr=pr(1, "MERGED"))
        ws = mkws([merged],
                  wfs=[S.Followup("WF1", "later", checked=False)],
                  design="~/specs/x-design.md")
        ws.active_focus = S.FocusItem("mvp", "see shell", "active")
        d = S.decide_next(ws)
        lanes = strategy_lanes(d)
        self.assertIn("focus:", d.headline)
        focus_i = lanes.index("From focus: mvp")
        wf_i = lanes.index("WF1 — later")
        self.assertLess(focus_i, wf_i)

    def test_skill_documents_chain_decline(self):
        skill = (ROOT / "skills" / "ws-next" / "SKILL.md").read_text()
        self.assertIn("Declining at any proposal step", skill)
        self.assertIn("print the default move's resolved command", skill)

    def test_mid_flight_single_move_offers_propose_in_chain(self):
        live = S.Unit(slug="cert", tasks_total=6, tasks_done=5)
        ws = mkws([live], design="~/specs/cert-design.md")
        d = S.decide_next(ws)
        self.assertTrue(chain_offers_propose(d))
        self.assertTrue(chain_runs_unit_picker(d))

    def test_restack_suppresses_chain_propose(self):
        drift = S.Unit(slug="top", tasks_total=1, tasks_done=1,
                       pr=pr(5, "OPEN", False, "master"),
                       log=[("t", "created", "base=feat-base")])
        ws = mkws([drift], design="~/specs/x-design.md")
        d = S.decide_next(ws)
        self.assertFalse(chain_offers_propose(d))
        self.assertFalse(chain_runs_unit_picker(d))

    def test_mixed_ship_and_mid_flight_offers_propose(self):
        ship = S.Unit(slug="done1", tasks_total=1, tasks_done=1, pr=None)
        live = S.Unit(slug="a", tasks_total=2, tasks_done=1)
        ws = mkws([ship, live], design="~/specs/x-design.md")
        d = S.decide_next(ws)
        self.assertTrue(chain_offers_propose(d))
        self.assertTrue(chain_runs_unit_picker(d))

    def test_propose_summary_design_only(self):
        live = S.Unit(slug="cert", tasks_total=6, tasks_done=5)
        d = S.decide_next(mkws([live], design="~/specs/cert-design.md"))
        self.assertEqual(propose_source_summary(d), "design")

    def test_propose_summary_many_followups(self):
        live = S.Unit(slug="a", tasks_total=4, tasks_done=1)
        wfs = [S.Followup(f"WF{i}", "x", checked=False) for i in range(32, 60)]
        d = S.decide_next(mkws([live], wfs=wfs,
                               design="~/specs/signing-design.md"))
        self.assertEqual(propose_source_summary(d),
                         "28 follow-ups, design")

    def test_next_emits_propose_summary_in_chain(self):
        sys.path.insert(0, str(ROOT / "skills" / "ws-next" / "scripts"))
        import next as N  # noqa: E402
        live = S.Unit(slug="a", tasks_total=4, tasks_done=1)
        wfs = [S.Followup(f"WF{i}", "x", checked=False) for i in range(32, 60)]
        ws = mkws([live], wfs=wfs, design="~/specs/signing-design.md")
        out = N.render_decision(S.decide_next(ws))
        self.assertIn("ProposeSummary: 28 follow-ups, design", out)


if __name__ == "__main__":
    unittest.main()
