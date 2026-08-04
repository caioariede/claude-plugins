import os
import sys
import tempfile
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

    def test_make_slug_drops_filler_and_caps_words(self):
        self.assertEqual(
            S.make_slug("Add a retry wrapper to the Stripe webhook handler "
                        "so duplicate events are ignored"),
            "add-retry-wrapper-stripe",
        )

    def test_make_slug_caps_chars_at_word_boundary(self):
        slug = S.make_slug("reconcile subscription entitlements nightly")
        self.assertEqual(slug, "reconcile-subscription")
        self.assertLessEqual(len(slug), 32)

    def test_make_slug_keeps_all_filler_input(self):
        self.assertEqual(S.make_slug("the and of"), "the-and-of")

    def test_make_slug_empty_input(self):
        self.assertEqual(S.make_slug("!!!"), "focus")

    def test_parse_focus_caps_done_history(self):
        lines = ["## Focus"]
        for i in range(5):
            lines.append(f"- [x] d{i}  — out {i}")
        active, queued, done = S.parse_focus("\n".join(lines) + "\n")
        self.assertIsNone(active)
        self.assertEqual([f.slug for f in done], ["d2", "d3", "d4"])


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

    def test_moves_emit_active_focus(self):
        u = S.Unit(slug="a", branch="a", tasks_total=2, tasks_done=1, pr=None)
        ws = S.Workstream(ws_id="2026-01-01-demo", name="demo")
        ws.units = [u]
        ws.active_focus = S.FocusItem("mvp", "see shell", "active")
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "resume")
        self.assertIsNotNone(d.active_focus)
        self.assertEqual(d.active_focus.slug, "mvp")

    def test_suggest_when_only_active_focus(self):
        ws = S.Workstream(ws_id="2026-01-01-demo", name="demo")
        ws.active_focus = S.FocusItem("mvp", "see shell", "active")
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "suggest")
        self.assertIn("focus: mvp", d.headline)

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


class FocusScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "skills" / "ws-focus" / "scripts"))

    def _import_focus(self):
        import importlib
        import focus as F
        return importlib.reload(F)

    def test_add_promotes_when_no_active(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo", focus_md="## Focus\n")
            F.cmd_add(store, "2026-01-01-demo",
                      "I can log in and see the dashboard shell")
            text = (store / "2026-01-01-demo" / "focus.md").read_text()
            self.assertIn("- [>] log-see-dashboard-shell", text)
            self.assertNotIn("- [ ]", text)
            del os.environ["WS_STORE"]

    def test_add_queues_when_active(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo",
                     focus_md=("## Focus\n"
                               "- [>] mvp  — see shell\n"))
            F.cmd_add(store, "2026-01-01-demo", "OAuth errors surface")
            text = (store / "2026-01-01-demo" / "focus.md").read_text()
            self.assertIn("- [>] mvp  — see shell", text)
            self.assertIn("- [ ] oauth-errors-surface  — OAuth errors surface",
                          text)
            del os.environ["WS_STORE"]

    def test_activate_flips_marks(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo",
                     focus_md=("## Focus\n"
                               "- [>] mvp  — see shell\n"
                               "- [ ] polish  — OAuth errors\n"))
            F.cmd_activate(store, "2026-01-01-demo", "polish")
            text = (store / "2026-01-01-demo" / "focus.md").read_text()
            self.assertIn("- [>] polish  — OAuth errors", text)
            self.assertIn("- [ ] mvp  — see shell", text)
            self.assertNotRegex(text, r"- \[>\].*mvp")
            del os.environ["WS_STORE"]

    def test_done_active_without_slug(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo",
                     focus_md="## Focus\n- [>] mvp  — see shell\n")
            F.cmd_done(store, "2026-01-01-demo")
            text = (store / "2026-01-01-demo" / "focus.md").read_text()
            self.assertIn("- [x] mvp  — see shell", text)
            self.assertNotIn("- [>]", text)
            del os.environ["WS_STORE"]

    def test_done_by_slug(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo",
                     focus_md=("## Focus\n"
                               "- [>] mvp  — see shell\n"
                               "- [ ] polish  — OAuth errors\n"))
            F.cmd_done(store, "2026-01-01-demo", "polish")
            text = (store / "2026-01-01-demo" / "focus.md").read_text()
            self.assertIn("- [>] mvp  — see shell", text)
            self.assertIn("- [x] polish  — OAuth errors", text)
            del os.environ["WS_STORE"]

    def test_render_keeps_last_three_done(self):
        done = [S.FocusItem(f"d{i}", f"out {i}", "done") for i in range(5)]
        text = S.render_focus(None, [], done)
        self.assertIn("d2", text)
        self.assertIn("d4", text)
        self.assertNotIn("d0", text)
        self.assertNotIn("d1", text)

    def test_add_rejects_duplicate_slug(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo",
                     focus_md=("## Focus\n"
                               "- [ ] oauth-errors  — OAuth errors\n"))
            with self.assertRaises(F.Fail) as ctx:
                F.cmd_add(store, "2026-01-01-demo", "OAuth errors!")
            self.assertIn("DUPLICATE_SLUG", str(ctx.exception))
            del os.environ["WS_STORE"]

    def test_show_renders_focus(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo",
                     focus_md="## Focus\n- [>] mvp  — see shell\n")
            out = F.cmd_show(store, "2026-01-01-demo")
            self.assertIn("## Focus", out)
            self.assertIn("- [>] mvp  — see shell", out)

    def test_at_most_one_active_after_writes(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo", focus_md="## Focus\n")
            F.cmd_add(store, "2026-01-01-demo", "first outcome")
            F.cmd_add(store, "2026-01-01-demo", "second outcome")
            F.cmd_activate(store, "2026-01-01-demo",
                           "second-outcome")
            active, queued, done = S.parse_focus(
                (store / "2026-01-01-demo" / "focus.md").read_text())
            self.assertIsNotNone(active)
            self.assertEqual(active.slug, "second-outcome")
            self.assertEqual(sum(1 for f in queued if f.state == "active"), 0)
            del os.environ["WS_STORE"]

    def test_add_cli_sole_workstream_quoted_outcome(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo", focus_md="## Focus\n")
            rc = F.main(["add", "ship oauth flow"])
            self.assertEqual(rc, 0)
            text = (store / "2026-01-01-demo" / "focus.md").read_text()
            self.assertIn("- [>] ship-oauth-flow  — ship oauth flow", text)
            del os.environ["WS_STORE"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
