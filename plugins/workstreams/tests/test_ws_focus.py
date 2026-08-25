import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
import ws_store as S  # noqa: E402


class ParseFocus(unittest.TestCase):
    def test_active_queued_done_preserves_file_order(self):
        md = """## Focus
- [ ] polish-auth  — OAuth errors surface in the UI
- [>] mvp-demo  — I can log in and see the dashboard shell
- [x] spike-layout  — Confirmed sidebar works
"""
        open_items, done = S.parse_focus(md)
        self.assertEqual([f.slug for f in open_items], ["polish-auth", "mvp-demo"])
        self.assertEqual(open_items[1].state, "active")
        self.assertEqual(open_items[0].state, "queued")
        self.assertEqual([f.slug for f in done], ["spike-layout"])

    def test_missing_file_is_empty(self):
        open_items, done = S.parse_focus("")
        self.assertEqual(open_items, [])
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
        lines = ["## Focus", "- [ ] only-open  — still here"]
        for i in range(5):
            lines.append(f"- [x] d{i}  — out {i}")
        open_items, done = S.parse_focus("\n".join(lines) + "\n")
        self.assertEqual([f.slug for f in open_items], ["only-open"])
        self.assertEqual([f.slug for f in done], ["d2", "d3", "d4"])

    def test_render_preserves_open_order(self):
        open_items = [
            S.FocusItem("a", "Focus A", "queued"),
            S.FocusItem("b", "Focus B", "active"),
            S.FocusItem("c", "Focus C", "queued"),
        ]
        text = S.render_focus(open_items, [])
        lines = [ln for ln in text.splitlines() if ln.startswith("- [")]
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], "- [ ] a  — Focus A")
        self.assertEqual(lines[1], "- [>] b  — Focus B")
        self.assertEqual(lines[2], "- [ ] c  — Focus C")


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

    def test_add_never_auto_activates(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo", focus_md="## Focus\n")
            F.cmd_add(store, "2026-01-01-demo",
                      "I can log in and see the dashboard shell")
            text = (store / "2026-01-01-demo" / "focus.md").read_text()
            self.assertIn("- [ ] log-see-dashboard-shell", text)
            self.assertNotIn("- [>]", text)
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

    def test_activate_flips_marks_in_place(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo",
                     focus_md=("## Focus\n"
                               "- [>] mvp  — see shell\n"
                               "- [ ] polish  — OAuth errors\n"))
            F.cmd_activate(store, "2026-01-01-demo", "2")
            text = (store / "2026-01-01-demo" / "focus.md").read_text()
            lines = [ln for ln in text.splitlines() if ln.startswith("- [")]
            self.assertEqual(lines[0], "- [ ] mvp  — see shell")
            self.assertEqual(lines[1], "- [>] polish  — OAuth errors")
            del os.environ["WS_STORE"]

    def test_activate_by_slug_in_place(self):
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
            lines = [ln for ln in text.splitlines() if ln.startswith("- [")]
            self.assertEqual(lines[0], "- [ ] mvp  — see shell")
            self.assertEqual(lines[1], "- [>] polish  — OAuth errors")
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

    def test_done_by_number(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo",
                     focus_md=("## Focus\n"
                               "- [>] mvp  — see shell\n"
                               "- [ ] polish  — OAuth errors\n"))
            F.cmd_done(store, "2026-01-01-demo", "2")
            text = (store / "2026-01-01-demo" / "focus.md").read_text()
            self.assertIn("- [>] mvp  — see shell", text)
            self.assertIn("- [x] polish  — OAuth errors", text)
            del os.environ["WS_STORE"]

    def test_render_keeps_last_three_done(self):
        done = [S.FocusItem(f"d{i}", f"out {i}", "done") for i in range(5)]
        text = S.render_focus([], done)
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

    def test_list_numbers_open_items(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo",
                     focus_md=("## Focus\n"
                               "- [ ] first  — First\n"
                               "- [>] mvp  — see shell\n"
                               "- [x] old  — done item\n"))
            out = F.cmd_list(store, "2026-01-01-demo")
            self.assertIn("1. [ ] first  — First", out)
            self.assertIn("2. [>] mvp  — see shell", out)
            self.assertIn("Done", out)
            self.assertIn("- [x] old  — done item", out)
            self.assertNotIn("3.", out)

    def test_at_most_one_active_after_writes(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo", focus_md="## Focus\n")
            F.cmd_add(store, "2026-01-01-demo", "first outcome")
            F.cmd_add(store, "2026-01-01-demo", "second outcome")
            F.cmd_activate(store, "2026-01-01-demo", "2")
            open_items, done = S.parse_focus(
                (store / "2026-01-01-demo" / "focus.md").read_text())
            active = next((f for f in open_items if f.state == "active"), None)
            self.assertIsNotNone(active)
            self.assertEqual(active.slug, "second-outcome")
            self.assertEqual(sum(1 for f in open_items if f.state == "active"), 1)
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
            self.assertIn("- [ ] ship-oauth-flow  — ship oauth flow", text)
            del os.environ["WS_STORE"]

    def test_move_reorders_open_list(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo",
                     focus_md=("## Focus\n"
                               "- [ ] focus-a  — Focus A\n"
                               "- [ ] focus-b  — Focus B\n"
                               "- [ ] focus-c  — Focus C\n"))
            F.cmd_move(store, "2026-01-01-demo", 2, 1)
            open_items, _ = S.parse_focus(
                (store / "2026-01-01-demo" / "focus.md").read_text())
            self.assertEqual([f.slug for f in open_items],
                             ["focus-b", "focus-a", "focus-c"])
            F.cmd_move(store, "2026-01-01-demo", 3, 2)
            open_items, _ = S.parse_focus(
                (store / "2026-01-01-demo" / "focus.md").read_text())
            self.assertEqual([f.slug for f in open_items],
                             ["focus-b", "focus-c", "focus-a"])
            del os.environ["WS_STORE"]

    def test_move_out_of_range(self):
        from test_ws_board import write_ws
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            os.environ["WS_STORE"] = str(store)
            F = self._import_focus()
            write_ws(store, "2026-01-01-demo",
                     focus_md="## Focus\n- [ ] only  — One\n")
            with self.assertRaises(F.Fail) as ctx:
                F.cmd_move(store, "2026-01-01-demo", 9, 1)
            self.assertIn("OUT_OF_RANGE", str(ctx.exception))
            del os.environ["WS_STORE"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
