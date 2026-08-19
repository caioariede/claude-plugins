"""Tests for store/git split detection and external backfill."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-resume" / "scripts"))
import ws_store as S  # noqa: E402
import detect_split as D  # noqa: E402
import backfill_external as B  # noqa: E402
from test_ws_board import ledger, write_ws  # noqa: E402


PLAN = "### Task 1: alpha\n\n### Task 2: beta\n"


class DetectSplitTests(unittest.TestCase):
    def _unit(self, **kw):
        u = S.Unit(slug="feat", branch="feat", repo="o/r", **kw)
        u.log = kw.get("log") or [
            ("t", "plan", "/tmp/plan.md"),
        ]
        return u

    def test_no_split_without_plan(self):
        u = self._unit(log=[])
        ws = S.Workstream(ws_id="ws", name="ws", units=[u])
        self.assertEqual(D.detect(u, ws, Path("/tmp")), "no-split")

    @mock.patch("detect_split.C.active_flavor", return_value=("superpowers", "default"))
    @mock.patch("detect_split.C.locate_worktree", return_value=Path("/wt"))
    @mock.patch("detect_split.C.commits_ahead", return_value=3)
    @mock.patch("detect_split.C.gather_pr_state")
    def test_split_with_open_pr_and_commits(self, gpr, _ca, _loc, _fl):
        u = self._unit(log=[
            ("t", "created", "base=main"),
            ("t", "plan", "/tmp/plan.md"),
        ])
        ws = S.Workstream(ws_id="ws", name="ws", units=[u])
        gpr.return_value = {
            "feat": S.PR(number=5782, state="OPEN", is_draft=False,
                          base="main"),
        }
        out = D.detect(u, ws, Path("/tmp"))
        self.assertEqual(out, "split pr=#5782 commits=3")

    @mock.patch("detect_split.C.active_flavor", return_value=("superpowers", "default"))
    @mock.patch("detect_split.C.gather_pr_state")
    def test_unknown_pr(self, gpr, _fl):
        u = self._unit()
        ws = S.Workstream(ws_id="ws", name="ws", units=[u])
        gpr.return_value = {"feat": None}
        self.assertEqual(D.detect(u, ws, Path("/tmp")), "unknown-pr")

    @mock.patch("detect_split.C.active_flavor", return_value=("superpowers", "default"))
    @mock.patch("detect_split.C.locate_worktree", return_value=Path("/wt"))
    @mock.patch("detect_split.C.commits_ahead", return_value=0)
    @mock.patch("detect_split.C.gather_pr_state")
    def test_no_split_zero_commits(self, gpr, _ca, _loc, _fl):
        u = self._unit(log=[
            ("t", "created", "base=main"),
            ("t", "plan", "/tmp/plan.md"),
        ])
        ws = S.Workstream(ws_id="ws", name="ws", units=[u])
        gpr.return_value = {
            "feat": S.PR(number=1, state="OPEN", is_draft=False, base="main"),
        }
        self.assertEqual(D.detect(u, ws, Path("/tmp")), "no-split")


class BackfillExternalTests(unittest.TestCase):
    def test_apply_external_backfill_happy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            udir = root / "units" / "feat"
            udir.mkdir(parents=True)
            (udir / "progress.md").write_text(
                "## Tasks\n\n## Follow-ups\n\n## Needs\n", encoding="utf-8")
            (udir / "log.md").write_text("# log\n", encoding="utf-8")
            plan = root / "plan.md"
            plan.write_text(PLAN, encoding="utf-8")
            pr = S.PR(number=99, state="OPEN", is_draft=False, base="main")
            status, ids = S.apply_external_backfill(
                root, "feat", plan, pr, head_sha="abc1234")
            self.assertEqual(status, "backfilled")
            self.assertEqual(ids, ["T1", "T2"])
            prog = (udir / "progress.md").read_text(encoding="utf-8")
            self.assertIn("- [x] T1  alpha", prog)
            log = (udir / "log.md").read_text(encoding="utf-8")
            self.assertIn("execute-mode=external", log)
            self.assertIn("PR #99", log)

    def test_cli_backfill(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            os.environ["WS_STORE"] = str(store)
            plan = store / "plan.md"
            plan.write_text(PLAN, encoding="utf-8")
            try:
                write_ws(
                    store,
                    "2026-01-01-demo",
                    units_md=ledger(
                        'feat  "F"  repo=o/r  branch=feat',
                    ),
                    units={
                        "feat": {
                            "progress": "## Tasks\n\n## Follow-ups\n\n## Needs\n",
                            "log": (
                                "# log\n"
                                f"- t  created  base=main\n"
                                f"- t  plan  {plan}\n"
                            ),
                        },
                    },
                )
                import ws_cli as C
                original = C.gather_pr_state

                def fake(ws, st, branches=None):
                    return {"feat": S.PR(number=5, state="OPEN",
                                          is_draft=False, base="main")}

                C.gather_pr_state = fake
                C.locate_worktree = lambda *a: store
                C.head_sha = lambda *a: "deadbeef"
                try:
                    code = B.main(["feat"])
                finally:
                    C.gather_pr_state = original
                self.assertEqual(code, 0)
                prog = (store / "2026-01-01-demo" / "units" / "feat"
                        / "progress.md").read_text(encoding="utf-8")
                self.assertIn("- [x] T1  alpha", prog)
            finally:
                os.environ.pop("WS_STORE", None)


if __name__ == "__main__":
    unittest.main()
