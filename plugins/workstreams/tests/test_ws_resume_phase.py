"""Tests for ws_store.resume_phase — execute-loop boundary derivation."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-resume" / "scripts"))

import phase as P  # noqa: E402
import ws_store as S  # noqa: E402
from test_ws_board import ledger, write_ws  # noqa: E402


def u(slug, *, done=0, total=0, followups=None, pr=None, stacked_on=None,
      needs=None, dropped=False):
    unit = S.Unit(slug=slug, branch=slug, repo="o/r", stacked_on=stacked_on)
    unit.tasks_done, unit.tasks_total = done, total
    unit.followups = followups or []
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

    def test_unit_complete_is_done(self):
        a = u("a", done=3, total=3)
        self.assertEqual(self.phase([a], "a"), "done")

    def test_tasks_done_open_followup_is_loop(self):
        a = u("a", done=2, total=2,
              followups=[S.Followup("F1", "fix", checked=False)])
        self.assertEqual(self.phase([a], "a"), "loop")

    def test_unit_complete_with_followups_is_done(self):
        a = u("a", done=2, total=2,
              followups=[S.Followup("F1", "fix", checked=True)])
        self.assertEqual(self.phase([a], "a"), "done")

    def test_unmet_need_is_blocked_even_with_partial_tasks(self):
        base = u("base", done=0, total=2)
        dep = u("dep", done=1, total=4, stacked_on="base")
        self.assertEqual(self.phase([base, dep], "dep"), "blocked")

    def test_no_plan_no_tasks_is_plan(self):
        a = u("a")
        self.assertEqual(self.phase([a], "a"), "plan")

    def test_plan_line_no_tasks_is_plan_pause(self):
        a = u("a")
        a.log = [("2026-01-01T00:00Z", "plan", "/tmp/plan.md")]
        self.assertEqual(self.phase([a], "a"), "plan-pause")

    def test_plan_done_receipt_without_tasks_still_plan_pause(self):
        a = u("a")
        a.log = [
            ("2026-01-01T00:00Z", "plan", "/tmp/plan.md"),
            ("2026-01-01T00:01Z", "decision",
             "plan=done plan=/tmp/plan.md digest=deadbeef"),
        ]
        self.assertEqual(self.phase([a], "a"), "plan-pause")

    def test_execute_mode_no_tasks_still_plan_pause(self):
        a = u("a")
        a.log = [
            ("2026-01-01T00:00Z", "plan", "/tmp/plan.md"),
            ("2026-01-01T00:01Z", "decision", "execute-mode=subagent-driven"),
        ]
        self.assertEqual(self.phase([a], "a"), "plan-pause")

    def test_tasks_without_plan_is_loop(self):
        a = u("a", done=0, total=3)
        self.assertEqual(self.phase([a], "a"), "loop")

    def test_stale_digest_with_tasks_stays_loop(self):
        a = u("a", done=1, total=4)
        a.log = [
            ("2026-01-01T00:00Z", "plan", "/tmp/old-plan.md"),
            ("2026-01-01T00:01Z", "decision",
             "plan=done plan=/tmp/old-plan.md digest=aaaa0000"),
        ]
        self.assertEqual(self.phase([a], "a"), "loop")

    def test_execute_mode_partial_tasks_is_loop(self):
        a = u("a", done=1, total=4)
        a.log = [
            ("2026-01-01T00:00Z", "plan", "/tmp/plan.md"),
            ("2026-01-01T00:01Z", "decision", "execute-mode=subagent-driven"),
        ]
        self.assertEqual(self.phase([a], "a"), "loop")

    def test_none_flavor_tasks_without_plan_or_execute_is_loop(self):
        a = u("a", done=0, total=3)
        self.assertEqual(self.phase([a], "a"), "loop")

    def test_external_mode_all_checked_is_done(self):
        a = u("a", done=2, total=2)
        a.log = [
            ("2026-01-01T00:00Z", "plan", "/tmp/plan.md"),
            ("2026-01-01T00:01Z", "decision", "execute-mode=external"),
        ]
        self.assertEqual(self.phase([a], "a"), "done")

    def test_external_mode_partial_tasks_is_loop(self):
        a = u("a", done=1, total=3)
        a.log = [
            ("2026-01-01T00:00Z", "plan", "/tmp/plan.md"),
            ("2026-01-01T00:01Z", "decision", "execute-mode=external"),
        ]
        self.assertEqual(self.phase([a], "a"), "loop")


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


class PhaseCliCompleteTests(unittest.TestCase):
    def test_complete_unit_returns_done(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger(
                    'spike  "S"  repo=o/r  branch=spike',
                    'dep  "D"  repo=o/r  branch=dep  stacked-on=spike'),
                units={
                    "spike": {
                        "progress": "## Tasks\n- [x] T1\n- [x] T2\n",
                    },
                    "dep": {"progress": "## Tasks\n- [ ] T1\n"},
                },
            )
            self.assertEqual(
                P.generate(store, "2026-01-01-demo", "spike", {}),
                "done",
            )
            self.assertEqual(
                P.generate(store, "2026-01-01-demo", "dep", {}),
                "loop",
            )

    def test_complete_base_unblocks_dependent(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger(
                    'spike  "S"  repo=o/r  branch=spike',
                    'dep  "D"  repo=o/r  branch=dep  stacked-on=spike'),
                units={
                    "spike": {
                        "progress": "## Tasks\n- [x] T1\n- [x] T2\n",
                    },
                    "dep": {
                        "progress": "## Tasks\n- [ ] T1\n",
                        "log": (
                            "# log\n"
                            "- 2026-01-01T00:00Z  plan  /tmp/plan.md\n"
                            "- 2026-01-01T00:01Z  decision  "
                            "execute-mode=subagent-driven\n"
                        ),
                    },
                },
            )
            self.assertNotEqual(
                P.generate(store, "2026-01-01-demo", "dep", {}),
                "blocked",
            )


class ResumeSpikePhaseCliTests(unittest.TestCase):
    def test_generate_loop_for_partial_spike(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            from test_ws_board import spike_ledger, write_ws  # noqa: E402

            write_ws(
                store,
                "2026-01-01-demo",
                spikes_md=spike_ledger('audit  "Audit"  repo=o/r'),
                spikes={
                    "audit": {
                        "progress": "## Tasks\n- [x] T1  a\n- [ ] T2  b\n",
                        "log": (
                            "# log\n"
                            "- 2026-01-01T00:00Z  plan  /tmp/plan.md\n"
                            "- 2026-01-01T00:01Z  decision  "
                            "execute-mode=subagent-driven\n"
                        ),
                    },
                },
            )
            self.assertEqual(
                P.generate(store, "2026-01-01-demo", "audit", {}, kind="spike"),
                "loop",
            )


if __name__ == "__main__":
    unittest.main()
