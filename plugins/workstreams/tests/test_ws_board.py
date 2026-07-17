"""Regression suite for the ws-board engine + renderer.

Stdlib-only (unittest) so it runs anywhere python3 does, matching the
scripts' zero-dependency stance. Fixtures are built on disk in a temp
store so we exercise the real file parsers, not mocks.

Run: python3 -m unittest discover -s plugins/workstreams/tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-board" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-next" / "scripts"))
sys.path.insert(0, str(ROOT / "hooks"))

import ws_store as S      # noqa: E402
import ws_cli as C        # noqa: E402
import board as B         # noqa: E402
import next as N          # noqa: E402
import board_hook as H    # noqa: E402


def write_ws(store, ws_id, units_md="", backlog_md="", workstream_md="",
             units=None):
    """units: {slug: {progress, log}} -> writes unit files."""
    d = store / ws_id
    (d / "units").mkdir(parents=True, exist_ok=True)
    (d / "workstream.md").write_text(
        workstream_md or f"---\nname: {ws_id}\n---\n", "utf-8")
    (d / "units.md").write_text(units_md, "utf-8")
    (d / "backlog.md").write_text(backlog_md, "utf-8")
    for slug, files in (units or {}).items():
        ud = d / "units" / slug
        ud.mkdir(parents=True, exist_ok=True)
        (ud / "progress.md").write_text(files.get("progress", ""), "utf-8")
        (ud / "log.md").write_text(files.get("log", ""), "utf-8")
    return d


def ledger(*rows):
    lines = ["# Units (append-only)"]
    for r in rows:
        lines.append("- 2026-01-01T00:00Z  " + r)
    return "\n".join(lines) + "\n"


def pr(number, state="OPEN", is_draft=False, base="master"):
    return S.PR(number=number, state=state, is_draft=is_draft, base=base)


class ParseLog(unittest.TestCase):
    def test_dropped_kind_not_substring(self):
        log = ("- 2026-01-01T00:00Z  created base=master\n"
               "- 2026-01-02T00:00Z  decision  dropped the retry path\n")
        parsed = S.parse_log(log)
        self.assertEqual([k for _t, k, _p in parsed], ["created", "decision"])
        self.assertFalse(any(k == "dropped" for _t, k, _p in parsed))

    def test_real_dropped_line(self):
        log = "- 2026-01-01T00:00Z  dropped merged+pushed to origin/main\n"
        self.assertTrue(any(k == "dropped" for _t, k, _p in S.parse_log(log)))


class ParseBacklog(unittest.TestCase):
    def test_ignores_comments_headers_and_foreign_sections(self):
        md = (
            "## Planned units\n"
            "<!-- a comment that is not an item -->\n"
            "# — a sub-header, single hash —\n"
            "- [ ] real-unit  base=master  — do the thing\n"
            "\n"
            "## Not tracked here (decoupled)\n"
            "- [ ] should-be-ignored  base=master  — noise\n"
            "\n"
            "## Follow-ups\n"
            "- [ ] WF1  desc with (parens) inside  (from unit-a, 2026-01-01T00:00Z)\n"
            "- [x] WF2  done one  (from ws, 2026-01-02T00:00Z) → promoted\n"
        )
        planned, wfs = S.parse_backlog(md)
        self.assertEqual([p.slug for p in planned], ["real-unit"])
        self.assertEqual([w.fid for w in wfs], ["WF1", "WF2"])
        self.assertEqual(wfs[0].origin, "unit-a")
        self.assertIn("(parens)", wfs[0].desc)
        self.assertFalse(wfs[0].checked)
        self.assertTrue(wfs[1].checked)

    def test_planned_fields_before_dash(self):
        planned, _ = S.parse_backlog(
            "## Planned units\n"
            "- [ ] b  base=a  needs=x,y  — build (blocked: later)\n")
        p = planned[0]
        self.assertEqual((p.slug, p.base, p.needs), ("b", "a", ["x", "y"]))
        self.assertEqual(p.what, "build (blocked: later)")


class CodeComplete(unittest.TestCase):
    def test_zero_tasks_not_complete(self):
        u = S.Unit(slug="x", tasks_total=0, tasks_done=0)
        self.assertFalse(u.code_complete)

    def test_all_checked_complete(self):
        self.assertTrue(S.Unit(slug="x", tasks_total=3, tasks_done=3).code_complete)
        self.assertFalse(S.Unit(slug="x", tasks_total=3, tasks_done=2).code_complete)

    def test_merged_implies_complete(self):
        u = S.Unit(slug="x", tasks_total=0, tasks_done=0, pr=pr(1, "MERGED"))
        self.assertTrue(u.code_complete)


class StatusPrecedence(unittest.TestCase):
    def _ws(self, **unit_kw):
        ws = S.Workstream(ws_id="w", name="w")
        ws.units = [S.Unit(slug="u", **unit_kw)]
        S.derive_status(ws)
        return ws.units[0].status

    def test_dropped_wins(self):
        u = S.Unit(slug="u", dropped=True, pr=pr(1, "MERGED"))
        ws = S.Workstream(ws_id="w", name="w", units=[u])
        S.derive_status(ws)
        self.assertEqual(u.status, "dropped")

    def test_merged(self):
        self.assertEqual(self._ws(pr=pr(1, "MERGED")), "merged")

    def test_in_review_ready_pr(self):
        self.assertEqual(self._ws(pr=pr(1, "OPEN", is_draft=False)), "in-review")

    def test_building_draft_pr(self):
        self.assertEqual(self._ws(pr=pr(1, "OPEN", is_draft=True)), "building")

    def test_building_no_pr(self):
        self.assertEqual(self._ws(pr=None), "building")


class BlockedDerivation(unittest.TestCase):
    def _ws(self):
        # a: complete; b: incomplete; dropped_dep: dropped
        ws = S.Workstream(ws_id="w", name="w")
        ws.units = [
            S.Unit(slug="a", tasks_total=1, tasks_done=1),
            S.Unit(slug="incomplete", tasks_total=2, tasks_done=1),
            S.Unit(slug="gone", tasks_total=1, tasks_done=1, dropped=True),
        ]
        return ws

    def test_base_need_incomplete_blocks(self):
        ws = self._ws()
        ws.units.append(S.Unit(slug="dependent", stacked_on="incomplete"))
        S.derive_status(ws)
        self.assertEqual(ws.units[-1].status, "blocked")

    def test_base_need_complete_ok(self):
        ws = self._ws()
        ws.units.append(S.Unit(slug="dependent", stacked_on="a",
                               pr=pr(9, "OPEN", is_draft=True)))
        S.derive_status(ws)
        self.assertEqual(ws.units[-1].status, "building")

    def test_dropped_target_noted(self):
        ws = self._ws()
        d = S.Unit(slug="dependent", needs=[S.Need("N1", "gone")])
        ws.units.append(d)
        by = {u.slug: u for u in ws.units}
        satisfied, note = S.need_state("gone", ws, by)
        self.assertFalse(satisfied)
        self.assertEqual(note, "dropped")

    def test_planned_target_is_open_not_removed(self):
        ws = self._ws()
        ws.planned = [S.PlannedUnit(slug="future")]
        by = {u.slug: u for u in ws.units}
        self.assertEqual(S.need_state("future", ws, by), (False, ""))

    def test_missing_target_is_removed(self):
        ws = self._ws()
        by = {u.slug: u for u in ws.units}
        self.assertEqual(S.need_state("nowhere", ws, by), (False, "removed"))

    def test_followup_need_checked(self):
        ws = self._ws()
        ws.wf_followups = [S.Followup("WF1", "d", checked=True)]
        by = {u.slug: u for u in ws.units}
        self.assertEqual(S.need_state("WF1", ws, by), (True, ""))
        ws.wf_followups[0].checked = False
        self.assertEqual(S.need_state("WF1", ws, by), (False, ""))


class BoardRendering(unittest.TestCase):
    def test_no_blocked_column_when_none(self):
        ws = S.Workstream(ws_id="w", name="demo")
        ws.units = [S.Unit(slug="a", tasks_total=1, tasks_done=1,
                           pr=pr(1, "MERGED"))]
        out = B.render_board(S.build_board(ws))
        self.assertIn("| ⏳ Not started | 🔄 In progress | ✅ Done |", out)
        self.assertNotIn("⛔ Blocked", out)

    def test_blocked_column_appears(self):
        ws = S.Workstream(ws_id="w", name="demo")
        ws.units = [S.Unit(slug="a", tasks_total=2, tasks_done=1),
                    S.Unit(slug="b", stacked_on="a")]
        out = B.render_board(S.build_board(ws))
        self.assertIn("⛔ Blocked", out)
        self.assertIn("b · needs a", out)

    def test_header_counts_and_complete(self):
        ws = S.Workstream(ws_id="w", name="demo")
        ws.units = [S.Unit(slug="a", tasks_total=1, tasks_done=1,
                           pr=pr(1, "MERGED"))]
        b = S.build_board(ws)
        self.assertEqual((b.merged_count, b.total_count), (1, 1))
        self.assertTrue(b.complete)
        self.assertIn("1/1 units done · ✅ complete", B.render_board(b))

    def test_open_backlog_blocks_complete(self):
        ws = S.Workstream(ws_id="w", name="demo")
        ws.units = [S.Unit(slug="a", tasks_total=1, tasks_done=1,
                           pr=pr(1, "MERGED"))]
        ws.wf_followups = [S.Followup("WF1", "later work", checked=False)]
        b = S.build_board(ws)
        self.assertFalse(b.complete)
        self.assertIn("📋 *Backlog*", B.render_board(b))

    def test_planned_dedup_vs_ledger(self):
        ws = S.Workstream(ws_id="w", name="demo")
        ws.units = [S.Unit(slug="a", tasks_total=1, tasks_done=1)]
        ws.planned = [S.PlannedUnit(slug="a", base="master"),
                      S.PlannedUnit(slug="b", base="master")]
        b = S.build_board(ws)
        self.assertNotIn("a", b.not_started)   # ledger owns it now
        self.assertIn("b", b.not_started)
        self.assertEqual(b.total_count, 2)     # a (ledger) + b (planned-only)


class Gist(unittest.TestCase):
    def test_first_sentence(self):
        self.assertEqual(S._gist("Do the thing. Then more."), "Do the thing.")

    def test_truncates_long_run_on(self):
        long = "x" * 200
        self.assertTrue(S._gist(long).endswith("…"))
        self.assertLessEqual(len(S._gist(long)), 101)


class ArgResolver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Path(self.tmp.name)
        write_ws(self.store, "2026-01-01-alpha",
                 units_md=ledger('foo  "Foo"  repo=o/r  branch=foo'))
        write_ws(self.store, "2026-01-02-beta",
                 units_md=ledger('bar  "Bar"  repo=o/r  branch=bar'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_ws_id_arg(self):
        self.assertEqual(C.resolve_args(self.store, ["2026-01-01-alpha"]),
                         ("2026-01-01-alpha", None))

    def test_ws_slug_resolves_without_date(self):
        # Users name a workstream by slug, not the dated dir name.
        self.assertEqual(C.resolve_args(self.store, ["alpha"]),
                         ("2026-01-01-alpha", None))

    def test_ambiguous_ws_slug_raises_pick(self):
        write_ws(self.store, "2026-03-03-alpha",
                 units_md=ledger('baz  "Baz"  repo=o/r  branch=baz'))
        with self.assertRaises(C.Pick):
            C.resolve_args(self.store, ["alpha"])  # two dated 'alpha' ws

    def test_two_args_ws_slug_resolves(self):
        self.assertEqual(C.resolve_args(self.store, ["alpha", "foo"]),
                         ("2026-01-01-alpha", "foo"))

    def test_bare_slug_resolves(self):
        self.assertEqual(C.resolve_args(self.store, ["bar"]),
                         ("2026-01-02-beta", "bar"))

    def test_unknown_raises_pick(self):
        with self.assertRaises(C.Pick):
            C.resolve_args(self.store, ["nope"])

    def test_zero_args_many_raises_pick(self):
        with self.assertRaises(C.Pick):
            C.resolve_args(self.store, [])

    def test_two_args_passthrough(self):
        self.assertEqual(
            C.resolve_args(self.store, ["2026-01-01-alpha", "foo"]),
            ("2026-01-01-alpha", "foo"))

    def test_two_args_unknown_ws_raises_pick(self):
        # Guards the hook: garbage like "/ws-board show me" must not render.
        with self.assertRaises(C.Pick):
            C.resolve_args(self.store, ["show", "me"])


class EndToEnd(unittest.TestCase):
    """Full generate() over a fixture store with injected PR state."""

    def test_board_from_disk(self):
        tmp = tempfile.TemporaryDirectory()
        store = Path(tmp.name)
        write_ws(
            store, "2026-01-01-demo",
            units_md=ledger(
                'base  "Base"  repo=o/r  branch=base',
                'top   "Top"   repo=o/r  branch=top  stacked-on=base'),
            backlog_md=("## Planned units\n"
                        "- [ ] later  base=master  — future work\n"
                        "## Follow-ups\n"
                        "- [ ] WF1  clean up later  (from base, 2026-01-01T00:00Z)\n"),
            units={
                "base": {"progress": "## Tasks\n- [x] T1  a\n- [x] T2  b\n"},
                "top": {"progress": "## Tasks\n- [ ] T1  c\n"},
            })
        pr_state = {"base": pr(10, "MERGED"), "top": pr(11, "OPEN", True)}
        out = B.generate(store, "2026-01-01-demo", None, pr_state)
        self.assertIn("base · #10", out)          # done
        self.assertIn("top · #11 · 0/1", out)     # in progress, base merged
        self.assertIn("later", out)               # not started
        self.assertIn("WF1", out)                 # open backlog
        self.assertNotIn("✅ complete", out)      # backlog keeps it open
        tmp.cleanup()


class RecordedBase(unittest.TestCase):
    def test_last_created_or_restack_wins(self):
        u = S.Unit(slug="x", log=[
            ("t1", "created", "base=feat-a"),
            ("t2", "note", "did stuff"),
            ("t3", "restack", "base=master was=feat-a"),
        ])
        self.assertEqual(S.recorded_base(u), "master")

    def test_none_without_a_base_line(self):
        u = S.Unit(slug="x", log=[("t1", "note", "hi")])
        self.assertIsNone(S.recorded_base(u))


class DecideNext(unittest.TestCase):
    def _ws(self, units, planned=None, wfs=None):
        ws = S.Workstream(ws_id="2026-01-01-demo", name="demo")
        ws.units = units
        ws.planned = planned or []
        ws.wf_followups = wfs or []
        return ws

    def test_rule1_restack_on_drift(self):
        u = S.Unit(slug="top", tasks_total=1, tasks_done=1,
                   pr=pr(5, "OPEN", False, "master"),
                   log=[("t", "created", "base=feat-base")])
        d = S.decide_next(self._ws([u]))
        self.assertEqual((d.rule, d.command), ("restack", "ws-restack top"))

    def test_no_restack_when_base_matches(self):
        u = S.Unit(slug="top", tasks_total=1, tasks_done=1,
                   pr=pr(5, "OPEN", False, "master"),
                   log=[("t", "created", "base=master")])
        self.assertNotEqual(S.decide_next(self._ws([u])).rule, "restack")

    def test_rule2_ship_before_rule3_resume(self):
        prog = S.Unit(slug="prog", tasks_total=2, tasks_done=1, pr=None)
        done = S.Unit(slug="done1", tasks_total=1, tasks_done=1, pr=None)
        d = S.decide_next(self._ws([prog, done]))
        self.assertEqual((d.rule, d.unit), ("ship", "done1"))

    def test_rule3_resume_in_progress(self):
        u = S.Unit(slug="a", tasks_total=2, tasks_done=1, pr=None)
        self.assertEqual(S.decide_next(self._ws([u])).command, "ws-resume a")

    def test_rule3_prefers_critical_path(self):
        # a and b both in progress; c is blocked needing b, so finishing b
        # unblocks c. b wins even though a is earlier in the ledger.
        a = S.Unit(slug="a", tasks_total=2, tasks_done=1, pr=None)
        b = S.Unit(slug="b", tasks_total=2, tasks_done=1, pr=None)
        c = S.Unit(slug="c", needs=[S.Need("N1", "b")])
        d = S.decide_next(self._ws([a, b, c]))
        self.assertEqual((d.rule, d.unit), ("resume", "b"))

    def test_rule4_start_stacked_planned(self):
        base = S.Unit(slug="base", tasks_total=1, tasks_done=1, pr=pr(1, "MERGED"))
        ws = self._ws([base], planned=[
            S.PlannedUnit(slug="next-thing", base="base", what="do the thing")])
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "start")
        self.assertEqual(d.command,
                         'ws-start 2026-01-01-demo "do the thing" --base base')

    def test_rule4_no_base_flag_for_default_branch(self):
        ws = self._ws([], planned=[
            S.PlannedUnit(slug="p", base="master", what="x")])
        self.assertEqual(S.decide_next(ws).command,
                         'ws-start 2026-01-01-demo "x"')

    def test_rule4_lists_parallel_startable(self):
        base = S.Unit(slug="base", tasks_total=1, tasks_done=1, pr=pr(1, "MERGED"))
        ws = self._ws([base], planned=[
            S.PlannedUnit(slug="p1", base="master", what="one"),
            S.PlannedUnit(slug="p2", base="master", what="two")])
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "start")
        self.assertEqual(len(d.also), 1)

    def test_triage_dropped_blocker(self):
        gone = S.Unit(slug="gone", tasks_total=1, tasks_done=1, dropped=True)
        dep = S.Unit(slug="dep", needs=[S.Need("N1", "gone")])
        d = S.decide_next(self._ws([gone, dep]))
        self.assertEqual((d.rule, d.command), ("triage-dropped", "ws-block dep clear N1"))

    def test_rule5_open_backlog_not_done(self):
        merged = S.Unit(slug="m", tasks_total=1, tasks_done=1, pr=pr(1, "MERGED"))
        ws = self._ws([merged], wfs=[S.Followup("WF1", "later", checked=False)])
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "triage-backlog")
        self.assertTrue(any("WF1" in it for it in d.open_items))

    def test_rule6_done(self):
        merged = S.Unit(slug="m", tasks_total=1, tasks_done=1, pr=pr(1, "MERGED"))
        self.assertEqual(S.decide_next(self._ws([merged])).rule, "done")

    def test_blocked_lines_reported(self):
        base = S.Unit(slug="base", tasks_total=2, tasks_done=1)  # in progress
        dep = S.Unit(slug="dep", stacked_on="base",
                     pr=pr(2, "OPEN", True, "base"))
        d = S.decide_next(self._ws([base, dep]))
        self.assertEqual(d.rule, "resume")          # advance the blocker
        self.assertTrue(any("dep — needs base" in b for b in d.blocked))


class NextEndToEnd(unittest.TestCase):
    def test_resume_in_flight_from_disk(self):
        tmp = tempfile.TemporaryDirectory()
        store = Path(tmp.name)
        write_ws(store, "2026-01-01-demo",
                 units_md=ledger('a  "A"  repo=o/r  branch=a'),
                 units={"a": {"progress": "## Tasks\n- [x] T1  x\n- [ ] T2  y\n"}})
        out = N.generate(store, "2026-01-01-demo", {"a": None})
        self.assertIn("Next: ws-resume a", out)
        tmp.cleanup()


class HookFastPath(unittest.TestCase):
    def test_command_args_matches_and_extracts(self):
        self.assertEqual(H.command_args("/ws-board"), [])
        self.assertEqual(H.command_args("  /ws-board  foo "), ["foo"])
        self.assertEqual(H.command_args("/ws-board a b"), ["a", "b"])
        self.assertEqual(H.command_args("/workstreams:ws-board x"), ["x"])

    def test_command_args_ignores_non_command(self):
        self.assertIsNone(H.command_args("show me the board"))
        self.assertIsNone(H.command_args("/ws-boardx"))          # word boundary
        self.assertIsNone(H.command_args("tell me /ws-board"))   # not at start

    def test_block_on_clean_render_claude(self):
        p = H.decide("/ws-board demo", "claude", lambda a: (0, "BOARD\n"))
        self.assertEqual(p, {"decision": "block", "reason": "BOARD"})

    def test_block_on_clean_render_cursor(self):
        p = H.decide("/ws-board demo", "cursor", lambda a: (0, "BOARD\n"))
        self.assertEqual(p, {"continue": False, "user_message": "BOARD"})

    def test_passthrough_when_not_command(self):
        self.assertIsNone(H.decide("hello", "claude", lambda a: (0, "x")))
        self.assertEqual(H.decide("hello", "cursor", lambda a: (0, "x")),
                         {"continue": True})

    def test_passthrough_on_exit2_disambiguation(self):
        # board.py exit 2 (needs a human pick) must fall through, not block.
        self.assertIsNone(H.decide("/ws-board", "claude", lambda a: (2, "")))

    def test_passthrough_on_error(self):
        def boom(a):
            raise RuntimeError("gh down")
        self.assertIsNone(H.decide("/ws-board x", "claude", boom))


if __name__ == "__main__":
    unittest.main(verbosity=2)
