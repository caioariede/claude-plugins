"""Prewalk phase insertion and digest binding."""

import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-resume" / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import ws_store as S  # noqa: E402
import ws_cli as C  # noqa: E402
from test_extension_handlers import _resume, _store_prewalk, _unit, _ws  # noqa: E402


class PrewalkPhaseTest(unittest.TestCase):
    def test_planned_unit_prewalk_when_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_prewalk(td)
            with tempfile.NamedTemporaryFile("w", delete=False, suffix="-plan.md") as f:
                f.write("plan body")
                path = f.name
            u = _unit(log=[("2026-01-02T00:00Z", "plan", path)])
            ws = _ws([u])
            self.assertEqual(_resume(u, ws, store, models_ready=True), "prewalk")

    def test_prewalk_done_skips_to_plan_pause(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_prewalk(td)
            with tempfile.NamedTemporaryFile("w", delete=False) as f:
                f.write("plan body")
                path = f.name
            u = _unit(log=[
                ("2026-01-02T00:00Z", "plan", path),
                ("2026-01-02T00:01Z", "decision",
                 f"prewalk=done plan={path} digest="
                 + S.plan_file_digest(path)),
            ])
            ws = _ws([u])
            self.assertEqual(_resume(u, ws, store), "plan-pause")

    def test_grandfather_skips_prewalk(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_prewalk(td)
            (store / "flavors.ini").write_text(
                "[active]\nspec-driven-development = superpowers-prewalk\n"
                "[config]\nsuperpowers-prewalk-activated-at = 2026-02-01T00:00Z\n",
                "utf-8",
            )
            u = _unit(log=[("2026-01-01T00:00Z", "plan", "/tmp/old-plan.md")])
            ws = _ws([u])
            self.assertEqual(_resume(u, ws, store), "plan-pause")

    def test_skip_prewalk_flag(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_prewalk(td)
            u = _unit(log=[("2026-01-02T00:00Z", "plan", "/tmp/plan.md")])
            ws = _ws([u])
            self.assertEqual(
                _resume(u, ws, store, skip={"prewalk", "prewalk-config"}),
                "plan-pause")

    def test_headless_skips_prewalk(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_prewalk(td)
            with tempfile.NamedTemporaryFile("w", delete=False, suffix="-plan.md") as f:
                f.write("plan body")
                path = f.name
            u = _unit(log=[("2026-01-02T00:00Z", "plan", path)])
            ws = _ws([u])
            self.assertEqual(_resume(u, ws, store, headless=True), "plan-pause")

    def test_prewalk_config_when_models_unset(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_prewalk(td)
            (store / "flavors.ini").write_text(
                "[active]\nspec-driven-development = superpowers-prewalk\n"
                "[config]\nagent = claude\n",
                "utf-8",
            )
            with tempfile.NamedTemporaryFile("w", delete=False, suffix="-plan.md") as f:
                f.write("plan body")
                path = f.name
            u = _unit(log=[("2026-01-02T00:00Z", "plan", path)])
            ws = _ws([u])
            self.assertEqual(_resume(u, ws, store), "prewalk-config")

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
            store = _store_prewalk(td)
            self.assertTrue(C.prewalk_enabled(store))
            ops, err = C.effective_flavor_ops(
                store, "spec-driven-development", "superpowers-prewalk")
            self.assertIsNone(err)
            self.assertEqual(ops.get("prewalk"), "on")
            self.assertIn("hook-ws-resume-prewalk", ops)


if __name__ == "__main__":
    unittest.main()
