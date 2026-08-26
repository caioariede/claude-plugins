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

import ws_store as S      # noqa: E402
import ws_cli as C        # noqa: E402
import board as B         # noqa: E402
import next as N          # noqa: E402


def write_ws(store, ws_id, units_md="", spikes_md="", backlog_md="",
             workstream_md="", focus_md="", units=None, spikes=None):
    """units: {slug: {progress, log}} -> writes unit files."""
    d = store / ws_id
    (d / "units").mkdir(parents=True, exist_ok=True)
    (d / "spikes").mkdir(parents=True, exist_ok=True)
    (d / "workstream.md").write_text(
        workstream_md or f"---\nname: {ws_id}\n---\n", "utf-8")
    (d / "units.md").write_text(units_md, "utf-8")
    (d / "spikes.md").write_text(
        spikes_md or f"# Spikes — {ws_id} (append-only)\n", "utf-8")
    (d / "backlog.md").write_text(backlog_md, "utf-8")
    if focus_md:
        (d / "focus.md").write_text(focus_md, "utf-8")
    for slug, files in (units or {}).items():
        ud = d / "units" / slug
        ud.mkdir(parents=True, exist_ok=True)
        (ud / "progress.md").write_text(files.get("progress", ""), "utf-8")
        (ud / "log.md").write_text(files.get("log", ""), "utf-8")
    for slug, files in (spikes or {}).items():
        sd = d / "spikes" / slug
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "progress.md").write_text(files.get("progress", ""), "utf-8")
        (sd / "log.md").write_text(files.get("log", ""), "utf-8")
    return d


def ledger(*rows):
    lines = ["# Units (append-only)"]
    for r in rows:
        lines.append("- 2026-01-01T00:00Z  " + r)
    return "\n".join(lines) + "\n"


def spike_ledger(*rows):
    lines = ["# Spikes — 2026-01-01-demo (append-only)"]
    for r in rows:
        lines.append("- 2026-01-01T00:00Z  " + r)
    return "\n".join(lines) + "\n"


def pr(number, state="OPEN", is_draft=False, base="master"):
    return S.PR(number=number, state=state, is_draft=is_draft, base=base)


def mkws(units=None, spikes=None, planned=None, wfs=None, ws_id="2026-01-01-demo",
         design=""):
    ws = S.Workstream(ws_id=ws_id, name="demo", design=design)
    ws.units = units or []
    ws.spikes = spikes or []
    ws.planned = planned or []
    ws.wf_followups = wfs or []
    return ws


def moves_of(ws):
    S.derive_status(ws)
    return S.enumerate_moves(ws, {u.slug: u for u in ws.units})


def three_move_store(store):
    """One ship, one advance, one planned (no move) -> pr_state map."""
    write_ws(store, "2026-01-01-demo",
             units_md=ledger('a  "A"  repo=o/r  branch=feat-a-2',
                             'b  "B"  repo=o/r  branch=b'),
             backlog_md="## Planned units\n- [ ] p  base=b  — do it\n",
             units={"a": {"progress": "## Tasks\n- [x] T1  x\n- [ ] T2  y\n"},
                    "b": {"progress": "## Tasks\n- [x] T1  x\n"}})
    return {"feat-a-2": None, "b": None}


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

    def test_restack_to_branch_drops_stale_stacked_on_need(self):
        ws = self._ws()
        ws.units[2].dropped = True  # gone
        ws.units.append(S.Unit(
            slug="dependent",
            stacked_on="gone",
            log=[("t1", "created", "base=gone"),
                 ("t2", "restack", "base=master was=gone")],
            pr=pr(10, "OPEN", is_draft=False, base="master"),
            tasks_total=1,
            tasks_done=1,
        ))
        S.derive_status(ws)
        self.assertEqual(ws.units[-1].status, "in-review")

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
    def test_board_shows_active_focus(self):
        ws = mkws()
        ws.active_focus = S.FocusItem("mvp", "see shell", "active")
        ws.focus_queued = [S.FocusItem("q", "later", "queued")]
        b = S.build_board(ws)
        self.assertIn("Focus: mvp", b.focus_line)
        self.assertIn("(+1 queued)", b.focus_line)
        out = B.render_board(b)
        self.assertIn("Focus: mvp — see shell (+1 queued)", out)

    def test_board_shows_empty_focus_placeholder(self):
        ws = S.Workstream(ws_id="w", name="demo")
        ws.units = [S.Unit(slug="a", tasks_total=1, tasks_done=1,
                           pr=pr(1, "MERGED"))]
        out = B.render_board(S.build_board(ws))
        self.assertIn("Focus: — (none set)", out)

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
        # No cwd-branch match → still ask which workstream.
        orig = C.current_branch
        C.current_branch = lambda cwd=None: "main"
        try:
            with self.assertRaises(C.Pick) as cm:
                C.resolve_args(self.store, [])
            self.assertTrue(str(cm.exception).startswith("MANY_WORKSTREAMS"))
        finally:
            C.current_branch = orig

    def test_zero_args_infers_from_cwd_branch(self):
        orig = C.current_branch
        C.current_branch = lambda cwd=None: "bar"
        try:
            self.assertEqual(C.resolve_args(self.store, []),
                             ("2026-01-02-beta", None))
        finally:
            C.current_branch = orig

    def test_infer_workstream_unique_and_ambiguous(self):
        self.assertEqual(C.infer_workstream(self.store, "foo"),
                         "2026-01-01-alpha")
        self.assertIsNone(C.infer_workstream(self.store, "nope"))
        # Same branch name in two workstreams → no unique inference.
        write_ws(self.store, "2026-03-03-gamma",
                 units_md=ledger('other  "O"  repo=o/r  branch=foo'))
        self.assertIsNone(C.infer_workstream(self.store, "foo"))

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

    def test_unit_detail_shows_empty_focus_placeholder(self):
        tmp = tempfile.TemporaryDirectory()
        store = Path(tmp.name)
        write_ws(
            store, "2026-01-01-demo",
            units_md=ledger('a  "A"  repo=o/r  branch=a'),
            units={"a": {"progress": "## Tasks\n- [x] T1  x\n"}})
        out = B.generate(store, "2026-01-01-demo", "a", {"a": None})
        self.assertIn("Focus: — (none set)", out)
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


class EnumerateMoves(unittest.TestCase):
    def test_every_in_flight_unit_gets_a_move(self):
        a = S.Unit(slug="a", branch="a", tasks_total=5, tasks_done=2)
        b = S.Unit(slug="b", branch="b", tasks_total=3, tasks_done=1)
        ms = moves_of(mkws([a, b]))
        self.assertEqual([m.unit for m in ms], ["a", "b"])
        self.assertEqual({m.rule for m in ms}, {"resume"})

    def test_resume_why_counts_remaining_tasks(self):
        u = S.Unit(slug="a", branch="a", tasks_total=5, tasks_done=2)
        self.assertEqual(moves_of(mkws([u]))[0].why, "3 of 5 tasks left")

    def test_code_complete_ready_pr_emits_no_move(self):
        u = S.Unit(slug="a", branch="a", tasks_total=1, tasks_done=1,
                   pr=pr(12, "OPEN", False, "master"),
                   log=[("t", "created", "base=master")])
        self.assertEqual(moves_of(mkws([u])), [])

    def test_code_complete_draft_pr_still_resumes(self):
        u = S.Unit(slug="a", branch="a", tasks_total=1, tasks_done=1,
                   pr=pr(12, "OPEN", True, "master"),
                   log=[("t", "created", "base=master")])
        m = moves_of(mkws([u]))[0]
        self.assertEqual((m.rule, m.why), ("resume", "tasks done, PR #12"))

    def test_in_review_with_tasks_left_still_resumes(self):
        u = S.Unit(slug="a", branch="a", tasks_total=2, tasks_done=1,
                   pr=pr(12, "OPEN", False, "master"),
                   log=[("t", "created", "base=master")])
        m = moves_of(mkws([u]))[0]
        self.assertEqual((m.rule, m.why), ("resume", "1 of 2 tasks left"))

    def test_code_complete_ready_pr_still_restacks_when_drifted(self):
        u = S.Unit(slug="a", branch="a", tasks_total=1, tasks_done=1,
                   pr=pr(12, "OPEN", False, "master"),
                   log=[("t", "created", "base=feat-base")])
        ms = moves_of(mkws([u]))
        self.assertEqual([(m.unit, m.rule) for m in ms], [("a", "restack")])

    def test_unit_without_tasks_says_so(self):
        u = S.Unit(slug="a", branch="a")
        self.assertEqual(moves_of(mkws([u]))[0].why, "no tasks planned yet")

    def test_plan_pause_incomplete_why(self):
        u = S.Unit(slug="a", branch="a",
                   log=[("t", "plan", "/tmp/plan.md")])
        self.assertEqual(
            moves_of(mkws([u]))[0].why,
            "plan-pause (store incomplete)")

    def test_resume_headline_uses_why(self):
        u = S.Unit(slug="a", branch="a", repo="o/r",
                   log=[("t", "plan", "/tmp/plan.md")])
        ws = mkws([u], design="~/specs/x.md")
        d = S.decide_next(ws, proposal_repo="o/r")
        self.assertEqual(d.headline, "plan-pause (store incomplete)")

    def test_one_move_per_unit_ship_beats_resume(self):
        u = S.Unit(slug="a", branch="a", tasks_total=2, tasks_done=2)
        ms = moves_of(mkws([u]))
        self.assertEqual([(m.unit, m.rule, m.why) for m in ms],
                         [("a", "ship", "tasks done, no PR")])

    def test_blocked_unit_emits_no_move(self):
        base = S.Unit(slug="base", branch="base", tasks_total=2, tasks_done=1)
        dep = S.Unit(slug="dep", branch="dep", needs=[S.Need("N1", "base")])
        self.assertEqual([m.unit for m in moves_of(mkws([base, dep]))],
                         ["base"])

    def test_blocked_but_drifted_unit_still_restacks(self):
        base = S.Unit(slug="base", branch="base", tasks_total=2, tasks_done=1)
        dep = S.Unit(slug="dep", branch="dep", needs=[S.Need("N1", "base")],
                     pr=pr(2, "OPEN", True, "master"),
                     log=[("t", "created", "base=base")])
        ms = moves_of(mkws([base, dep]))
        self.assertEqual([(m.unit, m.rule) for m in ms],
                         [("dep", "restack"), ("base", "resume")])
        self.assertEqual(ms[0].why, "base moved off base")

    def test_merged_and_dropped_units_emit_nothing(self):
        merged = S.Unit(slug="m", branch="m", tasks_total=1, tasks_done=1,
                        pr=pr(1, "MERGED"))
        gone = S.Unit(slug="g", branch="g", dropped=True)
        self.assertEqual(moves_of(mkws([merged, gone])), [])

    def test_startable_planned_emits_no_move(self):
        ws = mkws(planned=[S.PlannedUnit(slug="p", base="master", what="x")])
        self.assertEqual(moves_of(ws), [])

    def test_planned_blocked_by_needs_emits_nothing(self):
        base = S.Unit(slug="base", branch="base", tasks_total=2, tasks_done=1)
        ws = mkws([base], planned=[S.PlannedUnit(slug="p", base="base",
                                                 what="x")])
        self.assertEqual([m.unit for m in moves_of(ws)], ["base"])

    def test_rank_orders_restack_ship_resume_start(self):
        drift = S.Unit(slug="d", branch="d", tasks_total=1, tasks_done=1,
                       pr=pr(9, "OPEN", False, "master"),
                       log=[("t", "created", "base=feat-x")])
        shipit = S.Unit(slug="s", branch="s", tasks_total=1, tasks_done=1)
        going = S.Unit(slug="g", branch="g", tasks_total=4, tasks_done=1)
        ws = mkws([shipit, going, drift],
                  planned=[S.PlannedUnit(slug="p", base="master", what="x")])
        self.assertEqual([m.rule for m in moves_of(ws)],
                         ["restack", "ship", "resume"])

    def test_equal_rule_ranks_by_dependents_then_ledger(self):
        a = S.Unit(slug="a", branch="a", tasks_total=4, tasks_done=1)
        b = S.Unit(slug="b", branch="b", tasks_total=4, tasks_done=1)
        c = S.Unit(slug="c", branch="c", needs=[S.Need("N1", "b")])
        ms = moves_of(mkws([a, b, c]))
        self.assertEqual([m.unit for m in ms], ["b", "a"])

    def test_planned_keep_backlog_order(self):
        ws = mkws(planned=[S.PlannedUnit(slug="p1", base="master", what="one"),
                           S.PlannedUnit(slug="p2", base="master", what="two")])
        self.assertEqual(moves_of(ws), [])


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
        self.assertNotEqual(d.rule, "start")
        self.assertIn("planned: next-thing", d.open_items[0])

    def test_rule4_no_base_flag_for_default_branch(self):
        ws = self._ws([], planned=[
            S.PlannedUnit(slug="p", base="master", what="x")])
        d = S.decide_next(ws)
        self.assertNotEqual(d.rule, "start")
        self.assertIn("planned: p", d.open_items[0])

    def test_rule4_lists_parallel_startable(self):
        base = S.Unit(slug="base", tasks_total=1, tasks_done=1, pr=pr(1, "MERGED"))
        ws = self._ws([base], planned=[
            S.PlannedUnit(slug="p1", base="master", what="one"),
            S.PlannedUnit(slug="p2", base="master", what="two")])
        d = S.decide_next(ws)
        self.assertNotEqual(d.rule, "start")
        self.assertEqual(d.moves, [])
        self.assertEqual(len(d.open_items), 2)

    def test_default_fields_describe_the_first_move(self):
        a = S.Unit(slug="a", branch="feat-a", tasks_total=4, tasks_done=1)
        b = S.Unit(slug="b", branch="feat-b", tasks_total=2, tasks_done=2)
        d = S.decide_next(self._ws([a, b]))
        self.assertEqual((d.rule, d.unit, d.branch), ("ship", "b", "feat-b"))
        self.assertEqual(d.command, d.moves[0].command)
        self.assertEqual([m.unit for m in d.moves], ["b", "a"])

    def test_terminal_states_carry_no_moves(self):
        merged = S.Unit(slug="m", tasks_total=1, tasks_done=1, pr=pr(1, "MERGED"))
        ws = self._ws([merged], wfs=[S.Followup("WF1", "later", checked=False)])
        d = S.decide_next(ws)
        self.assertEqual((d.rule, d.moves), ("suggest", []))
        self.assertEqual(S.decide_next(self._ws([merged])).moves, [])

    def test_drifted_units_rank_by_dependents(self):
        # Both drifted; b unblocks c, a unblocks nothing, so b leads even
        # though a comes first in the ledger.
        a = S.Unit(slug="a", branch="a", tasks_total=2, tasks_done=1,
                   pr=pr(1, "OPEN", True, "master"),
                   log=[("t", "created", "base=feat-x")])
        b = S.Unit(slug="b", branch="b", tasks_total=2, tasks_done=1,
                   pr=pr(2, "OPEN", True, "master"),
                   log=[("t", "created", "base=feat-y")])
        c = S.Unit(slug="c", branch="c", needs=[S.Need("N1", "b")])
        d = S.decide_next(self._ws([a, b, c]))
        self.assertEqual((d.rule, d.unit), ("restack", "b"))

    def test_triage_dropped_blocker(self):
        gone = S.Unit(slug="gone", tasks_total=1, tasks_done=1, dropped=True)
        dep = S.Unit(slug="dep", needs=[S.Need("N1", "gone")])
        d = S.decide_next(self._ws([gone, dep]))
        self.assertEqual((d.rule, d.command), ("triage-dropped", "ws-block dep clear N1"))

    def test_blocked_lines_reported(self):
        base = S.Unit(slug="base", tasks_total=2, tasks_done=1)  # in progress
        dep = S.Unit(slug="dep", stacked_on="base",
                     pr=pr(2, "OPEN", True, "base"))
        d = S.decide_next(self._ws([base, dep]))
        self.assertEqual(d.rule, "resume")          # advance the blocker
        self.assertTrue(any("dep — needs base" in b for b in d.blocked))

    def test_unit_scoped_rules_carry_the_ledger_branch(self):
        u = S.Unit(slug="a", branch="feat-a", tasks_total=2, tasks_done=1)
        self.assertEqual(S.decide_next(self._ws([u])).branch, "feat-a")

    def test_restack_carries_the_ledger_branch(self):
        u = S.Unit(slug="top", branch="top-2", tasks_total=1, tasks_done=1,
                   pr=pr(5, "OPEN", False, "master"),
                   log=[("t", "created", "base=feat-base")])
        d = S.decide_next(self._ws([u]))
        self.assertEqual((d.rule, d.branch), ("restack", "top-2"))

    def test_start_has_no_branch(self):
        ws = self._ws([], planned=[
            S.PlannedUnit(slug="p", base="master", what="x")])
        d = S.decide_next(ws)
        self.assertNotEqual(d.rule, "start")
        self.assertIsNone(d.branch)
        self.assertIn("planned: p", d.open_items[0])

    def test_closed_pr_code_complete_gets_resume_move(self):
        u = S.Unit(slug="stale", branch="stale", tasks_total=2, tasks_done=2,
                   pr=pr(9, "CLOSED", False, "main"),
                   log=[("t", "created", "base=main")])
        d = S.decide_next(self._ws([u]))
        self.assertEqual(d.rule, "resume")
        self.assertEqual(d.moves[0].unit, "stale")
        self.assertIn("closed", d.moves[0].why.lower())

    def test_closed_pr_does_not_fall_through_to_done(self):
        u = S.Unit(slug="stale", branch="stale", tasks_total=1, tasks_done=1,
                   pr=pr(9, "CLOSED", False, "main"),
                   log=[("t", "created", "base=main")])
        self.assertNotEqual(S.decide_next(self._ws([u])).rule, "done")

    def test_branchless_ledger_line_reports_none(self):
        u = S.Unit(slug="a", tasks_total=2, tasks_done=1)
        self.assertIsNone(S.decide_next(self._ws([u])).branch)


class TerminalFork(unittest.TestCase):
    """suggest / empty / done — reached only when no move exists."""

    def _merged(self, slug="m", followups=None):
        return S.Unit(slug=slug, title=f"did {slug}", tasks_total=1,
                      tasks_done=1, pr=pr(1, "MERGED"),
                      followups=followups or [])

    def test_empty_store_says_no_units_yet(self):
        d = S.decide_next(mkws())
        self.assertEqual(d.rule, "empty")
        self.assertIn("no units yet", d.headline)

    def test_empty_store_with_a_design_proposes_instead(self):
        d = S.decide_next(mkws(design="~/specs/x-design.md"))
        self.assertEqual(d.rule, "suggest")
        self.assertEqual(d.design, "~/specs/x-design.md")
        self.assertEqual(d.proposable, [])

    def test_design_is_read_off_workstream_md(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(store, "2026-01-01-demo", workstream_md=(
                "---\nname: demo\ndesign: ~/specs/x-design.md\n---\n"))
            ws = S.load_workstream(store / "2026-01-01-demo")
            self.assertEqual(ws.design, "~/specs/x-design.md")
            self.assertEqual(S.decide_next(ws).rule, "suggest")

    def test_em_dash_design_placeholder_reads_as_absent(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(store, "2026-01-01-demo",
                     workstream_md="---\nname: demo\ndesign: —\n---\n")
            ws = S.load_workstream(store / "2026-01-01-demo")
            self.assertEqual(ws.design, "")
            self.assertEqual(S.decide_next(ws).rule, "empty")

    def test_orphaned_followup_in_a_merged_unit_is_proposable(self):
        u = self._merged(followups=[S.Followup("F1", "tidy it", checked=False)])
        d = S.decide_next(mkws([u]))
        self.assertEqual(d.rule, "suggest")
        self.assertEqual([(p.fid, p.origin) for p in d.proposable],
                         [("m:F1", "m")])

    def test_nothing_open_is_done(self):
        self.assertEqual(S.decide_next(mkws([self._merged()])).rule, "done")

    def test_code_complete_ready_pr_is_waiting_not_done(self):
        u = S.Unit(slug="a", branch="a", tasks_total=1, tasks_done=1,
                   pr=pr(12, "OPEN", False, "master"),
                   log=[("t", "created", "base=master")])
        d = S.decide_next(mkws([u]))
        self.assertEqual(d.rule, "waiting")
        self.assertEqual(d.moves, [])
        self.assertEqual(d.waiting, ["a — PR #12"])
        self.assertIn("waiting on review", d.headline)

    def test_waiting_with_design_still_suggests(self):
        u = S.Unit(slug="a", branch="a", tasks_total=1, tasks_done=1,
                   pr=pr(12, "OPEN", False, "master"),
                   log=[("t", "created", "base=master")])
        d = S.decide_next(mkws([u], design="~/specs/x-design.md"))
        self.assertEqual(d.rule, "suggest")
        self.assertEqual(d.waiting, ["a — PR #12"])

    def test_open_backlog_reaches_both_readers(self):
        # Open backlog is the user's list, Proposable the assistant's —
        # different readers, so an open follow-up belongs to both.
        ws = mkws([self._merged()],
                  wfs=[S.Followup("WF1", "later", checked=False)])
        d = S.decide_next(ws)
        self.assertEqual(d.open_items, ["WF1 — later"])
        self.assertEqual([p.fid for p in d.proposable], ["WF1"])

    def test_checked_followup_in_a_merged_unit_is_not_proposable(self):
        u = self._merged(followups=[S.Followup("F1", "done", checked=True)])
        self.assertEqual(S.decide_next(mkws([u])).rule, "done")

    def test_followup_in_a_live_unit_is_not_proposable(self):
        # The unit owns it, and it has a resume move of its own.
        live = S.Unit(slug="a", tasks_total=2, tasks_done=1,
                      followups=[S.Followup("F1", "later", checked=False)])
        d = S.decide_next(mkws([live]))
        self.assertEqual(d.rule, "resume")
        self.assertEqual(
            S.proposable_followups(mkws([live]),
                                   {"a": live}), [])

    def test_blocking_followup_is_flagged(self):
        merged = self._merged()
        dep = S.Unit(slug="dep", needs=[S.Need("N1", "WF4")])
        ws = mkws([merged, dep],
                      wfs=[S.Followup("WF4", "harden it", checked=False)])
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "suggest")
        self.assertEqual([(p.fid, p.blocks) for p in d.proposable],
                         [("WF4", ["dep"])])
        self.assertTrue(any("dep — needs WF4" in b for b in d.blocked))

    def test_qualified_need_target_matches_the_bare_proposal_id(self):
        merged = self._merged(followups=[S.Followup("F1", "x", checked=False)])
        dep = S.Unit(slug="dep",
                     needs=[S.Need("N1", "2026-01-01-demo:m:F1")])
        d = S.decide_next(mkws([merged, dep]))
        self.assertEqual([(p.fid, p.blocks) for p in d.proposable],
                         [("m:F1", ["dep"])])

    def test_covered_scope_lists_ledger_and_planned(self):
        merged = self._merged()
        dropped = S.Unit(slug="gone", title="abandoned idea", dropped=True)
        # p carries an unresolvable need, so it makes no start move and
        # cannot suppress the fork.
        ws = mkws([merged, dropped],
                      planned=[S.PlannedUnit(slug="p", base="master",
                                             what="later work",
                                             needs=["WF9"])],
                      design="~/specs/x-design.md")
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "suggest")
        self.assertIn("m — did m", d.covered)
        self.assertIn("gone — abandoned idea", d.covered)   # dropped counts
        self.assertTrue(any(c.startswith("p — later work") for c in d.covered))

    def test_covered_annotates_dropped_with_live_successor(self):
        dropped = S.Unit(slug="auth", title="old auth", dropped=True)
        successor = S.Unit(slug="auth-2", title="new auth",
                           restart_of="auth", branch="auth-2")
        ws = mkws([dropped, successor])
        covered = S._covered_scope(ws, {u.slug: u for u in ws.units})
        self.assertIn("auth — old auth (superseded by auth-2)", covered)
        self.assertIn("auth-2 — new auth", covered)

    def test_covered_annotates_dropped_with_merged_successor(self):
        dropped = S.Unit(slug="auth", title="old auth", dropped=True)
        successor = S.Unit(slug="auth-2", title="new auth",
                           restart_of="auth", branch="auth-2",
                           tasks_total=1, tasks_done=1,
                           pr=pr(1, "MERGED"))
        ws = mkws([dropped, successor], design="~/specs/x-design.md")
        d = S.decide_next(ws)
        self.assertIn("auth — old auth (superseded by auth-2)",
                      d.covered)

    def test_covered_no_annotation_without_successor(self):
        dropped = S.Unit(slug="gone", title="abandoned idea",
                         dropped=True)
        ws = mkws([dropped], design="~/specs/x-design.md")
        d = S.decide_next(ws)
        self.assertIn("gone — abandoned idea", d.covered)
        self.assertNotIn("superseded", " ".join(d.covered))

    def test_open_items_list_planned_and_followups_together(self):
        merged = self._merged()
        ws = mkws([merged],
                      planned=[S.PlannedUnit(slug="p", base="master",
                                             what="stuck", needs=["WF9"])],
                      wfs=[S.Followup("WF1", "later", checked=False)])
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "suggest")
        self.assertEqual([p.fid for p in d.proposable], ["WF1"])
        self.assertEqual(d.open_items,
                         ["planned: p — stuck", "WF1 — later"])

    def test_mid_flight_move_attaches_proposal_alongside(self):
        """Mid-flight resume no longer blocks proposal material."""
        live = S.Unit(slug="a", tasks_total=2, tasks_done=1)
        ws = mkws([live], wfs=[S.Followup("WF1", "later", checked=False)],
                      design="~/specs/x-design.md")
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "resume")
        self.assertEqual(d.design, "~/specs/x-design.md")
        self.assertTrue(d.covered)

    def test_mid_flight_only_move_attaches_proposal_material(self):
        live = S.Unit(slug="a", tasks_total=6, tasks_done=5)
        ws = mkws([live], design="~/specs/x-design.md")
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "resume")
        self.assertEqual(len(d.moves), 1)
        self.assertEqual(d.design, "~/specs/x-design.md")

    def test_terminal_moves_attach_proposal_material(self):
        ship = S.Unit(slug="ship-me", tasks_total=1, tasks_done=1, pr=None)
        advance = S.Unit(slug="adv-me", tasks_total=1, tasks_done=1,
                         pr=pr(5247, is_draft=True))
        ws = mkws([ship, advance], design="~/specs/x-design.md")
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "ship")
        self.assertNotEqual(d.rule, "suggest")
        self.assertEqual(d.design, "~/specs/x-design.md")
        self.assertTrue(d.covered)

    def test_restack_suppresses_proposal_alongside(self):
        drift = S.Unit(slug="top", tasks_total=1, tasks_done=1,
                       pr=pr(5, "OPEN", False, "master"),
                       log=[("t", "created", "base=feat-base")])
        ws = mkws([drift], design="~/specs/x-design.md")
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "restack")
        self.assertEqual((d.proposable, d.covered, d.design), ([], [], ""))

    def test_terminal_moves_no_material_without_source(self):
        ship = S.Unit(slug="done1", tasks_total=1, tasks_done=1, pr=None)
        d = S.decide_next(mkws([ship]))
        self.assertEqual(d.rule, "ship")
        self.assertEqual((d.proposable, d.covered, d.design), ([], [], ""))

    def test_mixed_terminal_and_mid_flight_attaches_proposal(self):
        ship = S.Unit(slug="done1", tasks_total=1, tasks_done=1, pr=None)
        live = S.Unit(slug="a", tasks_total=2, tasks_done=1)
        ws = mkws([ship, live], design="~/specs/x-design.md")
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "ship")
        self.assertEqual(d.design, "~/specs/x-design.md")
        self.assertTrue(d.covered)

    def test_terminal_moves_active_focus_only_attaches_material(self):
        ship = S.Unit(slug="done1", tasks_total=1, tasks_done=1, pr=None)
        ws = mkws([ship])
        ws.active_focus = S.FocusItem("mvp", "see shell", "active")
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "ship")
        self.assertEqual(d.design, "")
        self.assertIsNotNone(d.active_focus)
        self.assertTrue(d.covered)

    def test_unresolvable_planned_need_triages_over_empty(self):
        # No proposable material and no design, but open work remains, so
        # "no units yet" would be wrong advice — triage, not empty.
        ws = mkws(planned=[S.PlannedUnit(slug="p", base="master",
                                             what="x", needs=["WF9"])])
        d = S.decide_next(ws)
        self.assertEqual(d.rule, "triage-backlog")
        self.assertTrue(any("planned: p" in it for it in d.open_items))

    def test_claims_parses_off_the_ledger(self):
        units = S.parse_units(ledger(
            'fu  "close them"  repo=o/r  branch=fu  claims=WF4,m:F1'))
        self.assertEqual(units[0].claims, ["WF4", "m:F1"])

    def test_unknown_ledger_key_is_ignored(self):
        units = S.parse_units(ledger('a  "A"  repo=o/r  branch=a  future=x'))
        self.assertEqual((units[0].repo, units[0].branch), ("o/r", "a"))


class ClaimedFollowups(unittest.TestCase):
    """A claim is derived from `claims=`; nothing rewrites a follow-up."""

    def _ws(self, claimer_kw=None, checked=False, dropped=False):
        """One open WF4 plus a unit claiming it, per claimer_kw."""
        claimer = S.Unit(slug="fu", title="close them", claims=["WF4"],
                         dropped=dropped, **(claimer_kw or {}))
        ws = mkws([claimer], wfs=[S.Followup("WF4", "harden it",
                                            checked=checked)])
        S.derive_status(ws)
        return ws, claimer

    def test_a_live_claim_takes_the_followup_out_of_open_work(self):
        ws, _c = self._ws({"tasks_total": 2, "tasks_done": 1})
        fu = ws.wf_followups[0]
        self.assertFalse(fu.checked)          # the box is never touched
        self.assertFalse(S.followup_open("WF4", fu, ws))
        self.assertEqual(S.claimer_of("WF4", ws).slug, "fu")

    def test_a_dropped_claim_reopens_it(self):
        ws, _c = self._ws(dropped=True)
        self.assertTrue(S.followup_open("WF4", ws.wf_followups[0], ws))
        self.assertIsNone(S.claimer_of("WF4", ws))

    def test_a_dependent_clears_at_the_claimers_code_complete(self):
        for done, expect in ((1, False), (2, True)):
            ws, _c = self._ws({"tasks_total": 2, "tasks_done": done})
            ws.units.append(S.Unit(slug="dep", needs=[S.Need("N1", "WF4")]))
            by_slug = {u.slug: u for u in ws.units}
            self.assertEqual(S.need_state("WF4", ws, by_slug)[0], expect)

    def test_a_dropped_claimer_leaves_the_dependent_on_the_box(self):
        # Claim released, so the need falls back to the unchecked box.
        ws, _c = self._ws(dropped=True)
        by_slug = {u.slug: u for u in ws.units}
        self.assertEqual(S.need_state("WF4", ws, by_slug), (False, ""))

    def test_a_qualified_claim_matches_a_bare_target(self):
        owner = S.Unit(slug="m", tasks_total=1, tasks_done=1,
                       pr=pr(1, "MERGED"),
                       followups=[S.Followup("F1", "tidy", checked=False)])
        claimer = S.Unit(slug="fu", claims=["2026-01-01-demo:m:F1"],
                         tasks_total=1, tasks_done=1)
        ws = mkws([owner, claimer])
        S.derive_status(ws)
        self.assertEqual(S.claimer_of("m:F1", ws).slug, "fu")
        self.assertFalse(S.followup_open("m:F1", owner.followups[0], ws))

    def test_a_claimed_followup_is_not_reproposed(self):
        ws, _c = self._ws({"tasks_total": 1, "tasks_done": 1,
                           "pr": pr(1, "MERGED")})
        d = S.decide_next(ws)
        self.assertEqual(d.proposable, [])
        self.assertEqual(d.open_items, [])
        self.assertEqual(d.rule, "done")      # the claim carried it

    def test_a_merged_claimer_lets_the_workstream_finish(self):
        ws, _c = self._ws({"tasks_total": 1, "tasks_done": 1,
                           "pr": pr(1, "MERGED")})
        self.assertTrue(S.workstream_done(ws, {u.slug: u for u in ws.units}))

    def test_a_dropped_claimer_leaves_the_workstream_open(self):
        ws, _c = self._ws(dropped=True)
        self.assertFalse(S.workstream_done(ws, {u.slug: u for u in ws.units}))

    def test_the_board_hides_a_claimed_followup_from_the_backlog(self):
        ws, _c = self._ws({"tasks_total": 2, "tasks_done": 1})
        self.assertEqual(S.build_board(ws).backlog, [])

    def test_a_blocked_line_names_a_qualified_followup_in_full(self):
        owner = S.Unit(slug="m", tasks_total=1, tasks_done=1,
                       pr=pr(1, "MERGED"),
                       followups=[S.Followup("F1", "tidy", checked=False)])
        dep = S.Unit(slug="dep", needs=[S.Need("N1", "2026-01-01-demo:m:F1")])
        d = S.decide_next(mkws([owner, dep]))
        self.assertEqual(d.blocked, ["dep — needs m:F1"])


class SuggestRendering(unittest.TestCase):
    def test_material_renders_for_the_assistant(self):
        tmp = tempfile.TemporaryDirectory()
        store = Path(tmp.name)
        write_ws(store, "2026-01-01-demo",
                 workstream_md=("---\nname: demo\n"
                                "design: ~/specs/x-design.md\n---\n"),
                 units_md=ledger('m  "did m"  repo=o/r  branch=m'),
                 backlog_md=("## Follow-ups\n"
                             "- [ ] WF4  harden it  (from m, 2026-01-01T00:00Z)\n"),
                 units={"m": {"progress": "## Tasks\n- [x] T1  x\n",
                              "log": "- t  created base=master\n"}})
        out = N.generate(store, "2026-01-01-demo",
                         {"m": pr(1, "MERGED")})
        self.assertIn("no store work left", out)
        self.assertIn("Proposable:\n- WF4  from=m  harden it", out)
        self.assertIn("Covered:\n- m — did m", out)
        self.assertIn("Design: ~/specs/x-design.md", out)
        tmp.cleanup()

    def test_no_material_emitted_when_a_move_exists(self):
        tmp = tempfile.TemporaryDirectory()
        store = Path(tmp.name)
        out = N.generate(store, "2026-01-01-demo", three_move_store(store))
        for marker in ("Proposable:", "Covered:", "Design:"):
            self.assertNotIn(marker, out)
        tmp.cleanup()


class NextEndToEnd(unittest.TestCase):
    def test_lists_every_move_ranked_with_a_default(self):
        tmp = tempfile.TemporaryDirectory()
        store = Path(tmp.name)
        out = N.generate(store, "2026-01-01-demo", three_move_store(store))
        self.assertIn("  b — ship it: tasks done, no PR   [default]"
                      "   run=ws-resume b   branch=b", out)
        self.assertIn("  a — advance: 1 of 2 tasks left"
                      "   run=ws-resume a   branch=feat-a-2", out)
        self.assertNotIn("p — start", out)
        # Rank rides line order now that no ordinal carries it.
        self.assertLess(out.index("  b — ship it"), out.index("  a — advance"))
        self.assertNotIn("Next:", out)
        tmp.cleanup()

    def test_move_lines_carry_no_ordinals(self):
        # Every number on screen belongs to the live picker; a numbered
        # move list collides with its option numbers.
        tmp = tempfile.TemporaryDirectory()
        store = Path(tmp.name)
        out = N.generate(store, "2026-01-01-demo", three_move_store(store))
        for line in out.splitlines():
            self.assertNotRegex(line, r"^\s*\d+\.")
        tmp.cleanup()

    def test_start_move_carries_no_branch(self):
        tmp = tempfile.TemporaryDirectory()
        store = Path(tmp.name)
        write_ws(store, "2026-01-01-demo",
                 backlog_md="## Planned units\n- [ ] p  base=master  — do it\n")
        out = N.generate(store, "2026-01-01-demo", {})
        self.assertIn("no active unit; open backlog remains — triage", out)
        self.assertIn("- planned: p — do it", out)
        self.assertNotIn("p — start", out)
        self.assertNotIn("branch=", out)
        tmp.cleanup()

    def test_waiting_ready_pr_renders_waiting_lines(self):
        tmp = tempfile.TemporaryDirectory()
        store = Path(tmp.name)
        write_ws(store, "2026-01-01-demo",
                 units_md=ledger('a  "A"  repo=o/r  branch=a'),
                 units={"a": {"progress": "## Tasks\n- [x] T1  x\n",
                              "log": "- t  created base=master\n"}})
        out = N.generate(store, "2026-01-01-demo",
                         {"a": pr(12, "OPEN", False, "master")})
        self.assertIn("waiting on review — nothing to advance", out)
        self.assertIn("Waiting: a — PR #12", out)
        self.assertNotIn(" — advance:", out)
        tmp.cleanup()

    def test_triage_fallback_keeps_the_next_line(self):
        tmp = tempfile.TemporaryDirectory()
        store = Path(tmp.name)
        write_ws(store, "2026-01-01-demo",
                 units_md=ledger('gone  "G"  repo=o/r  branch=gone',
                                 'dep  "D"  repo=o/r  branch=dep'),
                 units={"gone": {"progress": "## Tasks\n- [x] T1  x\n",
                                 "log": "- 2026-01-02T00:00Z  dropped "
                                        "superseded\n"},
                        "dep": {"progress": "## Tasks\n- [x] T1  x\n"
                                            "## Needs\n- N1  gone\n"}})
        out = N.generate(store, "2026-01-01-demo", {"gone": None, "dep": None})
        self.assertIn("Next: ws-block dep clear N1   (unit: dep, branch: dep)",
                      out)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
