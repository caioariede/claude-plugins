"""Prewalk phase insertion and digest binding."""

import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-resume" / "scripts"))

import ws_store as S  # noqa: E402
import ws_cli as C  # noqa: E402
import phase as P  # noqa: E402


def _unit(slug="u", log=None, tasks_total=0, tasks_done=0):
    return S.Unit(
        slug=slug, repo="o/r", branch=slug, dropped=False,
        tasks_total=tasks_total, tasks_done=tasks_done,
        log=log or [], followups=[], needs=[])


def _ws(units):
    return S.Workstream(ws_id="2026-01-01-ws", name="ws", units=units,
                        spikes=[])


class PrewalkPhaseTest(unittest.TestCase):
    def test_planned_unit_prewalk_when_enabled(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix="-plan.md") as f:
            f.write("plan body")
            path = f.name
        u = _unit(log=[
            ("2026-01-02T00:00Z", "plan", path),
        ])
        ws = _ws([u])
        by = {u.slug: u}
        phase = S.resume_phase(u, ws, by, prewalk_enabled=True)
        self.assertEqual(phase, "prewalk")

    def test_prewalk_done_skips_to_plan_pause(self):
        u = _unit(log=[
            ("2026-01-02T00:00Z", "plan", "/tmp/plan.md"),
            ("2026-01-02T00:01Z", "decision",
             "prewalk=done plan=/tmp/plan.md digest=deadbeef"),
        ])
        ws = _ws([u])
        by = {u.slug: u}
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("plan body")
            path = f.name
        u.log = [
            ("2026-01-02T00:00Z", "plan", path),
            ("2026-01-02T00:01Z", "decision",
             f"prewalk=done plan={path} digest="
             + S.plan_file_digest(path)),
        ]
        phase = S.resume_phase(u, ws, by, prewalk_enabled=True)
        self.assertEqual(phase, "plan-pause")

    def test_grandfather_skips_prewalk(self):
        u = _unit(log=[
            ("2026-01-01T00:00Z", "plan", "/tmp/old-plan.md"),
        ])
        ws = _ws([u])
        by = {u.slug: u}
        phase = S.resume_phase(u, ws, by, prewalk_enabled=True,
                               grandfather=True)
        self.assertEqual(phase, "plan-pause")

    def test_skip_prewalk_flag(self):
        u = _unit(log=[("2026-01-02T00:00Z", "plan", "/tmp/plan.md")])
        ws = _ws([u])
        by = {u.slug: u}
        phase = S.resume_phase(u, ws, by, prewalk_enabled=True,
                               skip_prewalk=True)
        self.assertEqual(phase, "plan-pause")

    def test_headless_skips_prewalk(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix="-plan.md") as f:
            f.write("plan body")
            path = f.name
        u = _unit(log=[("2026-01-02T00:00Z", "plan", path)])
        ws = _ws([u])
        by = {u.slug: u}
        phase = S.resume_phase(u, ws, by, prewalk_enabled=True,
                               headless=True)
        self.assertEqual(phase, "plan-pause")

    def test_prewalk_config_when_models_unset(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix="-plan.md") as f:
            f.write("plan body")
            path = f.name
        u = _unit(log=[("2026-01-02T00:00Z", "plan", path)])
        ws = _ws([u])
        by = {u.slug: u}
        phase = S.resume_phase(u, ws, by, prewalk_enabled=True,
                               models_ready=False)
        self.assertEqual(phase, "prewalk-config")

    def test_unit_board_suffix_prewalk(self):
        u = _unit(log=[("2026-01-02T00:00Z", "plan", "/tmp/p.md")])
        self.assertEqual(S.unit_board_suffix(u, phase="prewalk"),
                         "prewalk (exploring)")

    def test_unit_board_suffix_prewalk_config(self):
        u = _unit(log=[("2026-01-02T00:00Z", "plan", "/tmp/p.md")])
        self.assertEqual(S.unit_board_suffix(u, phase="prewalk-config"),
                         "prewalk (config required)")

    def test_bundled_superpowers_prewalk_extends(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "workstreams"
            store.mkdir()
            (store / "flavors.ini").write_text(
                "[active]\nspec-driven-development = superpowers-prewalk\n",
                "utf-8")
            self.assertTrue(C.prewalk_enabled(store))
            ops, err = C.effective_flavor_ops(
                store, "spec-driven-development", "superpowers-prewalk")
            self.assertIsNone(err)
            self.assertEqual(ops.get("prewalk"), "on")
            self.assertIn("hook-ws-resume-prewalk", ops)


if __name__ == "__main__":
    unittest.main()
