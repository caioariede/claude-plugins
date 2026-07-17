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

import ws_store as S      # noqa: E402
import board as B         # noqa: E402


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
        self.assertEqual(B.resolve_args(self.store, ["2026-01-01-alpha"]),
                         ("2026-01-01-alpha", None))

    def test_bare_slug_resolves(self):
        self.assertEqual(B.resolve_args(self.store, ["bar"]),
                         ("2026-01-02-beta", "bar"))

    def test_unknown_raises_pick(self):
        with self.assertRaises(B.Pick):
            B.resolve_args(self.store, ["nope"])

    def test_zero_args_many_raises_pick(self):
        with self.assertRaises(B.Pick):
            B.resolve_args(self.store, [])

    def test_two_args_passthrough(self):
        self.assertEqual(
            B.resolve_args(self.store, ["2026-01-01-alpha", "foo"]),
            ("2026-01-01-alpha", "foo"))


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
