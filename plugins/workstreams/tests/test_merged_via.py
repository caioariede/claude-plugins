"""Tests for merged-via log parsing and is_merged predicate."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
import ws_store as S  # noqa: E402


def unit(log=None, pr=None, **kw):
    defaults = dict(slug="u", branch="feat-u", tasks_total=2, tasks_done=0)
    defaults.update(kw)
    u = S.Unit(**defaults)
    u.log = log or []
    u.pr = pr
    return u


class MergedViaParseTests(unittest.TestCase):
    def test_parses_latest_merged_via(self):
        u = unit(log=[
            ("2026-01-01T00:00Z", "created", "base=main"),
            ("2026-01-02T00:00Z", "merged-via",
             "branch=feat-ship sha=abc123 pr=42"),
        ])
        rec = S.merged_via_record(u)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.branch, "feat-ship")
        self.assertEqual(rec.sha, "abc123")
        self.assertEqual(rec.pr, 42)

    def test_is_merged_from_log_without_pr(self):
        u = unit(log=[
            ("2026-01-01T00:00Z", "merged-via",
             "branch=master sha=deadbeef"),
        ])
        self.assertTrue(S.is_merged(u))

    def test_is_merged_from_forge_pr(self):
        u = unit(pr=S.PR(number=1, state="MERGED", is_draft=False,
                          base="main"))
        self.assertTrue(S.is_merged(u))

    def test_not_merged_open_pr_no_log(self):
        u = unit(pr=S.PR(number=1, state="OPEN", is_draft=False,
                          base="main"))
        self.assertFalse(S.is_merged(u))


class IsMergedDerivationTests(unittest.TestCase):
    def test_code_complete_with_merged_via_zero_tasks(self):
        u = unit(log=[
            ("2026-01-01T00:00Z", "merged-via",
             "branch=master sha=abc"),
        ], tasks_total=0, tasks_done=0)
        self.assertTrue(u.code_complete)

    def test_status_merged_from_log_only(self):
        u = unit(log=[
            ("2026-01-01T00:00Z", "merged-via",
             "branch=master sha=abc"),
        ], pr=S.PR(number=9, state="OPEN", is_draft=False, base="main"))
        ws = S.Workstream(ws_id="w", name="w", units=[u])
        S.derive_status(ws)
        self.assertEqual(u.status, "merged")

    def test_resume_phase_done_on_merged_via(self):
        u = unit(log=[
            ("2026-01-01T00:00Z", "merged-via",
             "branch=master sha=abc"),
        ])
        u.pr = None
        ws = S.Workstream(ws_id="w", name="w", units=[u])
        by = {u.slug: u}
        self.assertEqual(S.resume_phase(u, ws, by), "done")

    def test_dependent_unblocks_on_merged_via_base(self):
        base = unit(log=[
            ("2026-01-01T00:00Z", "merged-via",
             "branch=master sha=abc"),
        ], slug="base", tasks_total=2, tasks_done=0)
        dep = S.Unit(slug="dep", stacked_on="base", tasks_total=1,
                     tasks_done=0)
        ws = S.Workstream(ws_id="w", name="w", units=[base, dep])
        by = {u.slug: u for u in ws.units}
        satisfied, _ = S.need_state("base", ws, by)
        self.assertTrue(satisfied)


class NextRouterTests(unittest.TestCase):
    def test_merged_via_unit_emits_no_move(self):
        u = unit(log=[
            ("2026-01-01T00:00Z", "merged-via",
             "branch=feat-ship sha=abc"),
        ], title="Shipped elsewhere", tasks_total=1, tasks_done=0,
           pr=S.PR(number=1, state="OPEN", is_draft=False, base="main"))
        ws = S.Workstream(ws_id="w", name="w", units=[u])
        S.derive_status(ws)
        d = S.decide_next(ws)
        self.assertEqual(d.moves, [])
        self.assertNotEqual(d.rule, "ship")


if __name__ == "__main__":
    unittest.main()
