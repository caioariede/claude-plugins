"""Tests for ws_store.resume_phase — execute-loop boundary derivation."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-resume" / "scripts"))

import phase as P  # noqa: E402
import ws_store as S  # noqa: E402
from test_ws_board import ledger, write_ws  # noqa: E402


def u(slug, *, done=0, total=0, pr=None, stacked_on=None, needs=None,
      dropped=False):
    unit = S.Unit(slug=slug, branch=slug, repo="o/r", stacked_on=stacked_on)
    unit.tasks_done, unit.tasks_total = done, total
    unit.pr = pr
    unit.dropped = dropped
    unit.needs = needs or []
    return unit


def ws(units):
    w = S.Workstream(ws_id="2026-01-01-demo", name="demo")
    w.units = units
    return w


class ResumePhaseTests(unittest.TestCase):
    def phase(self, units, slug):
        w = ws(units)
        by = {x.slug: x for x in units}
        return S.resume_phase(by[slug], w, by)

    def test_partial_tasks_no_pr_is_loop(self):
        a = u("a", done=2, total=5)
        self.assertEqual(self.phase([a], "a"), "loop")

    def test_code_complete_no_pr_is_ship_pause(self):
        a = u("a", done=3, total=3)
        self.assertEqual(self.phase([a], "a"), "ship-pause")

    def test_code_complete_draft_pr_is_draft_pr(self):
        a = u("a", done=2, total=2,
              pr=S.PR(number=1, state="OPEN", is_draft=True, base="master"))
        self.assertEqual(self.phase([a], "a"), "draft-pr")

    def test_code_complete_ready_pr_is_done(self):
        a = u("a", done=1, total=1,
              pr=S.PR(number=2, state="OPEN", is_draft=False, base="master"))
        self.assertEqual(self.phase([a], "a"), "done")

    def test_merged_is_done(self):
        a = u("a", done=1, total=1,
              pr=S.PR(number=3, state="MERGED", is_draft=False, base="master"))
        self.assertEqual(self.phase([a], "a"), "done")

    def test_unmet_need_is_blocked_even_with_partial_tasks(self):
        base = u("base", done=0, total=2)
        dep = u("dep", done=1, total=4, stacked_on="base")
        self.assertEqual(self.phase([base, dep], "dep"), "blocked")


class PhaseCliTests(unittest.TestCase):
    def test_generate_loop_for_partial_unit(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('feat  "F"  repo=o/r  branch=feat'),
                units={
                    "feat": {
                        "progress": "## Tasks\n- [x] T1  a\n- [ ] T2  b\n",
                        "log": "# log\n",
                    },
                },
            )
            self.assertEqual(
                P.generate(store, "2026-01-01-demo", "feat", {}),
                "loop",
            )


if __name__ == "__main__":
    unittest.main()
