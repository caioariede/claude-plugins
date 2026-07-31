import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
import ws_store as S  # noqa: E402


class ParseFocus(unittest.TestCase):
    def test_active_queued_done(self):
        md = """## Focus
- [>] mvp-demo  — I can log in and see the dashboard shell
- [ ] polish-auth  — OAuth errors surface in the UI
- [x] spike-layout  — Confirmed sidebar works
"""
        active, queued, done = S.parse_focus(md)
        self.assertEqual(active.slug, "mvp-demo")
        self.assertEqual(active.outcome, "I can log in and see the dashboard shell")
        self.assertEqual(active.state, "active")
        self.assertEqual([f.slug for f in queued], ["polish-auth"])
        self.assertEqual([f.slug for f in done], ["spike-layout"])

    def test_missing_file_is_empty(self):
        active, queued, done = S.parse_focus("")
        self.assertIsNone(active)
        self.assertEqual(queued, [])
        self.assertEqual(done, [])

    def test_make_slug(self):
        self.assertEqual(S.make_slug("OAuth errors surface!"), "oauth-errors-surface")


class PlannedDemoted(unittest.TestCase):
    def test_planned_no_longer_start_move(self):
        ws = S.Workstream(ws_id="2026-01-01-demo", name="demo")
        ws.planned = [S.PlannedUnit(slug="p", base="master", what="x")]
        S.derive_status(ws)
        moves = S.enumerate_moves(ws, {})
        self.assertEqual(moves, [])


class FocusEmission(unittest.TestCase):
    def test_suggest_includes_active_focus(self):
        ws = S.Workstream(ws_id="2026-01-01-demo", name="demo", design="/spec.md")
        ws.active_focus = S.FocusItem("mvp", "see the shell", "active")
        ws.focus_queued = [S.FocusItem("next", "polish", "queued")]
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "suggest")
        self.assertIsNotNone(d.active_focus)
        self.assertEqual(d.active_focus.slug, "mvp")
        self.assertEqual(len(d.focus_queue), 1)

    def test_next_renders_focus_blocks(self):
        import tempfile
        from test_ws_board import write_ws
        sys.path.insert(0, str(ROOT / "skills" / "ws-next" / "scripts"))
        import next as N  # noqa: E402
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            write_ws(store, "2026-01-01-demo",
                     focus_md="## Focus\n- [>] mvp  — see shell\n- [ ] later  — polish\n",
                     workstream_md="---\nname: demo\ndesign: /x\n---\n")
            out = N.generate(store, "2026-01-01-demo", {})
            self.assertIn("ActiveFocus: mvp  — see shell", out)
            self.assertIn("FocusQueue:", out)
            self.assertIn("- later  — polish", out)


class LoadFocus(unittest.TestCase):
    def test_load_workstream_reads_focus(self):
        import tempfile
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            write_ws(store, "2026-01-01-demo",
                     focus_md="## Focus\n- [>] demo  — ship it\n")
            ws = S.load_workstream(store / "2026-01-01-demo")
            self.assertIsNotNone(ws.active_focus)
            self.assertEqual(ws.active_focus.slug, "demo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
