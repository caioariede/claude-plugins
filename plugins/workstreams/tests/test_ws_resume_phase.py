"""Tests for ws_store.resume_phase — execute-loop boundary derivation."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))

import ws_store as S  # noqa: E402

PHASE = ROOT / "skills" / "ws-resume" / "scripts" / "phase.py"


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


def load_phase_module():
    spec = importlib.util.spec_from_file_location("phase", PHASE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ResumePhaseTests(unittest.TestCase):
    def phase(self, units, slug):
        w = ws(units)
        by = {x.slug: x for x in units}
        S.derive_status(w)
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

    def test_blocked_beats_loop(self):
        base = u("base", done=0, total=1)
        dep = u("dep", done=0, total=3, stacked_on="base")
        self.assertEqual(self.phase([base, dep], "dep"), "blocked")


class PhaseCliTests(unittest.TestCase):
    def test_prints_loop_for_partial_unit(self):
        mod = load_phase_module()
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            d = store / "2026-01-01-demo"
            (d / "units" / "feat").mkdir(parents=True)
            (d / "workstream.md").write_text("---\nname: demo\n---\n")
            (d / "units.md").write_text(
                '# Units\n- 2026-01-01T00:00Z  feat  "F"  '
                'repo=o/r  branch=feat\n')
            (d / "units" / "feat" / "progress.md").write_text(
                "## Tasks\n- [x] T1  a\n- [ ] T2  b\n")
            (d / "units" / "feat" / "log.md").write_text("# log\n")
            self.assertEqual(
                mod.phase_for(store, "2026-01-01-demo", "feat", {}),
                "loop",
            )


if __name__ == "__main__":
    unittest.main()
