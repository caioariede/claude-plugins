"""Tests for stackable base helpers (ws_store)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
import ws_store as S


def pr(number, state="OPEN", is_draft=False, base="master"):
    return S.PR(number=number, state=state, is_draft=is_draft, base=base)


def u(slug, *, done=0, total=0, pr_obj=None, repo="o/r", branch=None,
      log=None):
    unit = S.Unit(slug=slug, branch=branch or slug, repo=repo)
    unit.tasks_done, unit.tasks_total = done, total
    unit.pr = pr_obj
    if log:
        unit.log = log
    return unit


class TestUnitReadiness(unittest.TestCase):
    def test_code_complete_returns_none(self):
        unit = u("a", done=4, total=4, pr_obj=pr(1, "OPEN", True))
        S.derive_status(S.Workstream(ws_id="w", name="w", units=[unit]))
        self.assertIsNone(S.unit_readiness(unit))

    def test_building_with_tasks(self):
        unit = u("a", done=1, total=4)
        S.derive_status(S.Workstream(ws_id="w", name="w", units=[unit]))
        self.assertEqual(S.unit_readiness(unit), "3 of 4 tasks left")

    def test_building_no_tasks(self):
        unit = u("a")
        S.derive_status(S.Workstream(ws_id="w", name="w", units=[unit]))
        self.assertEqual(S.unit_readiness(unit), "no tasks planned yet")

    def test_plan_pause_store_incomplete(self):
        unit = u("a", log=[("t", "plan", "/tmp/plan.md")])
        S.derive_status(S.Workstream(ws_id="w", name="w", units=[unit]))
        self.assertEqual(S.unit_readiness(unit),
                         "plan-pause (store incomplete)")

    def test_complete_code_complete_returns_none(self):
        unit = u("a", done=2, total=2, pr_obj=pr(42, "OPEN", False))
        S.derive_status(S.Workstream(ws_id="w", name="w", units=[unit]))
        self.assertEqual(unit.status, "complete")
        self.assertIsNone(S.unit_readiness(unit))


class TestStackableBases(unittest.TestCase):
    def _ws(self, units, **kw):
        ws = S.Workstream(ws_id="w", name="w", units=units, **kw)
        S.derive_status(ws)
        return ws, {u.slug: u for u in units}

    def test_excludes_dropped_complete_blocked_drifted(self):
        base = u("base", done=1, total=2)
        dropped = u("gone", repo="o/r")
        dropped.dropped = True
        complete = u("m", done=1, total=1, pr_obj=pr(1, "MERGED"))
        blocked = u("dep", repo="o/r")
        blocked.needs = [S.Need("N1", "base")]
        drifted = u("d", done=1, total=2, pr_obj=pr(2, "OPEN", True, "master"),
                    log=[("t", "created", "base=feat-d")])
        ws, by = self._ws([base, dropped, complete, blocked, drifted])
        got = S.stackable_bases(ws, "o/r")
        self.assertEqual([b.slug for b in got], ["base"])

    def test_repo_filter_case_insensitive(self):
        a = u("a", repo="Org/Repo")
        b = u("b", repo="other/r")
        ws, by = self._ws([a, b])
        got = S.stackable_bases(ws, "org/repo")
        self.assertEqual([x.slug for x in got], ["a"])

    def test_none_proposal_repo_returns_empty(self):
        a = u("a")
        ws, by = self._ws([a])
        self.assertEqual(S.stackable_bases(ws, None), [])

    def test_empty_repo_field_excluded(self):
        bad = u("bad", repo="")
        ws, by = self._ws([bad])
        self.assertEqual(S.stackable_bases(ws, "o/r"), [])


class TestDecideNextStackable(unittest.TestCase):
    def test_suggest_with_design_emits_stackable(self):
        inflight = u("base", done=1, total=3, repo="o/r")
        ws = S.Workstream(ws_id="w", name="w", units=[inflight],
                          design="~/specs/x.md")
        d = S.decide_next(ws, proposal_repo="o/r")
        self.assertIsNotNone(d.stackable)
        self.assertEqual(d.stackable[0].slug, "base")

    def test_followup_only_suggest_omits_stackable(self):
        merged = S.Unit(slug="m", branch="m", repo="o/r",
                        tasks_total=1, tasks_done=1, pr=pr(1, "MERGED"),
                        log=[("t", "created", "base=master")])
        ws = S.Workstream(ws_id="w", name="w", units=[merged],
                          wf_followups=[S.Followup("WF1", "later", checked=False)])
        d = S.decide_next(ws, proposal_repo="o/r")
        self.assertIsNone(d.stackable)

    def test_restack_suppresses_stackable(self):
        inflight = u("a", done=1, total=2, repo="o/r",
                     pr_obj=pr(1, "OPEN", True, "master"),
                     log=[("t", "created", "base=feat-a")])
        ws = S.Workstream(ws_id="w", name="w", units=[inflight],
                          design="~/specs/x.md")
        d = S.decide_next(ws, proposal_repo="o/r")
        self.assertIsNone(d.stackable)


class TestRenderStackable(unittest.TestCase):
    def test_renders_tagged_lines(self):
        sys.path.insert(0, str(ROOT / "skills" / "ws-next" / "scripts"))
        import next as N
        d = S.Decision(
            rule="suggest",
            headline="no store work left — propose the next unit",
            design="~/x.md",
            stackable=[S.StackBase("base", "o/r", "feat-base",
                                   "2 of 4 tasks left")],
        )
        out = N.render_decision(d)
        self.assertIn("Stackable:", out)
        self.assertIn(
            "- base  repo=o/r  branch=feat-base  readiness=2 of 4 tasks left",
            out)

    def test_empty_stackable_emits_header_only(self):
        sys.path.insert(0, str(ROOT / "skills" / "ws-next" / "scripts"))
        import next as N
        d = S.Decision(rule="suggest", design="~/x.md", stackable=[])
        out = N.render_decision(d)
        self.assertIn("Stackable:", out)
        self.assertNotIn("readiness=", out)

    def test_none_stackable_omits_block(self):
        sys.path.insert(0, str(ROOT / "skills" / "ws-next" / "scripts"))
        import next as N
        d = S.Decision(rule="suggest", stackable=None)
        self.assertNotIn("Stackable:", N.render_decision(d))


if __name__ == "__main__":
    unittest.main()
