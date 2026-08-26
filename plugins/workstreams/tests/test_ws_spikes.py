"""Engine tests for workstream spikes."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))

import ws_store as S  # noqa: E402

from test_ws_board import ledger, mkws, spike_ledger, write_ws  # noqa: E402


class SpikeCompleteTests(unittest.TestCase):
    def test_spike_complete_requires_all_tasks(self):
        sp = S.Spike(slug="audit", tasks_total=2, tasks_done=2)
        self.assertTrue(sp.spike_complete)

    def test_spike_complete_zero_tasks_false(self):
        sp = S.Spike(slug="audit")
        self.assertFalse(sp.spike_complete)

    def test_spike_complete_partial_false(self):
        sp = S.Spike(slug="audit", tasks_total=2, tasks_done=1)
        self.assertFalse(sp.spike_complete)


class SpikeStatusTests(unittest.TestCase):
    def test_blocked_before_complete_when_need_unmet(self):
        perf = S.Spike(slug="perf", tasks_total=2, tasks_done=1)
        audit = S.Spike(
            slug="audit",
            tasks_total=1,
            tasks_done=1,
            needs=[S.Need(nid="N1", target="perf")],
        )
        ws = mkws(spikes=[perf, audit])
        by_slug = {}
        by_spike = {s.slug: s for s in ws.spikes}
        self.assertEqual(
            S.derive_spike_status(audit, ws, by_slug, by_spike),
            "blocked",
        )

    def test_researching_when_zero_tasks(self):
        sp = S.Spike(slug="audit")
        ws = mkws(spikes=[sp])
        by_spike = {sp.slug: sp}
        self.assertEqual(
            S.derive_spike_status(sp, ws, {}, by_spike),
            "researching",
        )

    def test_dropped_spike(self):
        sp = S.Spike(slug="audit", dropped=True)
        ws = mkws(spikes=[sp])
        by_spike = {sp.slug: sp}
        self.assertEqual(
            S.derive_spike_status(sp, ws, {}, by_spike),
            "dropped",
        )


class NeedStateSpikeTests(unittest.TestCase):
    def test_spike_target_satisfied_at_spike_complete(self):
        sp = S.Spike(slug="audit", tasks_total=1, tasks_done=1)
        ws = mkws(spikes=[sp])
        by_slug = {}
        by_spike = {sp.slug: sp}
        satisfied, note = S.need_state("audit", ws, by_slug, by_spike)
        self.assertTrue(satisfied)
        self.assertEqual(note, "")

    def test_pending_spike_not_removed(self):
        ws = mkws(
            planned=[S.PlannedUnit(slug="impl", base="main",
                                   needs=["audit-spike"])],
        )
        by_slug = {}
        by_spike = {}
        satisfied, note = S.need_state("audit-spike", ws, by_slug, by_spike)
        self.assertFalse(satisfied)
        self.assertEqual(note, "pending")

    def test_dropped_spike_note(self):
        sp = S.Spike(slug="audit", dropped=True)
        ws = mkws(spikes=[sp])
        satisfied, note = S.need_state("audit", ws, {}, {sp.slug: sp})
        self.assertFalse(satisfied)
        self.assertEqual(note, "dropped")


class LoadWorkstreamSpikeTests(unittest.TestCase):
    def test_load_spikes_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            write_ws(
                store,
                "2026-01-01-demo",
                spikes_md=spike_ledger('audit  "Audit auth"  repo=o/r'),
                spikes={
                    "audit": {
                        "progress": "## Tasks\n- [x] T1  x\n",
                        "log": "",
                    },
                },
            )
            ws = S.load_workstream(store / "2026-01-01-demo")
            self.assertEqual(len(ws.spikes), 1)
            self.assertEqual(ws.spikes[0].slug, "audit")
            self.assertEqual(ws.spikes[0].tasks_done, 1)
            self.assertTrue(ws.spikes[0].spike_complete)


class WorkstreamDoneSpikeTests(unittest.TestCase):
    def test_active_spike_blocks_done(self):
        sp = S.Spike(slug="audit", tasks_total=1, tasks_done=0)
        ws = mkws(spikes=[sp])
        S.derive_status(ws)
        by_slug = {}
        self.assertFalse(S.workstream_done(ws, by_slug))

    def test_terminal_spike_allows_done_when_no_units(self):
        sp = S.Spike(slug="audit", tasks_total=1, tasks_done=1)
        ws = mkws(spikes=[sp])
        S.derive_status(ws)
        self.assertTrue(S.workstream_done(ws, {}))


class ResumeSpikePhaseTests(unittest.TestCase):
    def _phase(self, spikes, slug):
        ws = mkws(spikes=spikes)
        by_slug = {u.slug: u for u in ws.units}
        by_spike = {s.slug: s for s in ws.spikes}
        return S.resume_spike_phase(by_spike[slug], ws, by_slug, by_spike)

    def test_zero_tasks_is_plan(self):
        self.assertEqual(self._phase([S.Spike(slug="audit")], "audit"), "plan")

    def test_plan_line_no_execute_mode_is_plan_pause(self):
        sp = S.Spike(slug="audit")
        sp.log = [("2026-01-01T00:00Z", "plan", "/tmp/plan.md")]
        self.assertEqual(self._phase([sp], "audit"), "plan-pause")

    def test_partial_tasks_is_loop(self):
        sp = S.Spike(slug="audit", tasks_total=2, tasks_done=1)
        sp.log = [
            ("2026-01-01T00:00Z", "plan", "/tmp/plan.md"),
            ("2026-01-01T00:01Z", "decision", "execute-mode=subagent-driven"),
        ]
        self.assertEqual(self._phase([sp], "audit"), "loop")

    def test_all_tasks_done_is_done(self):
        sp = S.Spike(slug="audit", tasks_total=1, tasks_done=1)
        sp.log = [
            ("2026-01-01T00:00Z", "plan", "/tmp/plan.md"),
            ("2026-01-01T00:01Z", "decision", "execute-mode=subagent-driven"),
        ]
        self.assertEqual(self._phase([sp], "audit"), "done")

    def test_unmet_need_is_blocked(self):
        base = S.Spike(slug="perf", tasks_total=1, tasks_done=0)
        audit = S.Spike(
            slug="audit",
            needs=[S.Need(nid="N1", target="perf")],
        )
        self.assertEqual(self._phase([base, audit], "audit"), "blocked")


class BoardSpikeTests(unittest.TestCase):
    def test_spike_in_progress_column(self):
        sp = S.Spike(slug="audit", tasks_total=2, tasks_done=1)
        ws = mkws(spikes=[sp])
        b = S.build_board(ws)
        self.assertTrue(b.has_spikes)
        self.assertTrue(any("[spike]" in cell for cell in b.in_progress))

    def test_spike_tag_in_done(self):
        sp = S.Spike(slug="audit", tasks_total=1, tasks_done=1)
        ws = mkws(spikes=[sp])
        b = S.build_board(ws)
        self.assertTrue(any("audit [spike]" in cell for cell in b.done))


class EnumerateMovesSpikeTests(unittest.TestCase):
    def test_researching_spike_emits_resume_move(self):
        sp = S.Spike(slug="audit", tasks_total=2, tasks_done=1)
        ws = mkws(spikes=[sp])
        S.derive_status(ws)
        moves = S.enumerate_moves(ws, {})
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0].command, "ws-resume audit")
        self.assertIsNone(moves[0].branch)

    def test_blocked_spike_emits_no_move(self):
        base = S.Spike(slug="perf", tasks_total=1, tasks_done=0)
        audit = S.Spike(
            slug="audit",
            needs=[S.Need(nid="N1", target="perf")],
        )
        ws = mkws(spikes=[base, audit])
        S.derive_status(ws)
        moves = S.enumerate_moves(ws, {})
        slugs = {m.unit for m in moves}
        self.assertIn("perf", slugs)
        self.assertNotIn("audit", slugs)


class CoveredScopeSpikeTests(unittest.TestCase):
    def test_terminal_spike_in_covered(self):
        sp = S.Spike(slug="audit", title="Audit auth", tasks_total=1,
                     tasks_done=1)
        ws = mkws(spikes=[sp])
        S.derive_status(ws)
        covered = S._covered_scope(ws, {})
        self.assertIn("audit — Audit auth (spike)", covered)


class ResolverSpikeTests(unittest.TestCase):
    def test_resolve_target_finds_spike(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            write_ws(
                store,
                "2026-01-01-demo",
                spikes_md=spike_ledger('audit  "Audit"  repo=o/r'),
            )
            import ws_cli as C  # noqa: E402

            t = C.resolve_target(store, "audit")
            self.assertEqual(t.kind, "spike")
            self.assertEqual(t.slug, "audit")


if __name__ == "__main__":
    unittest.main()
