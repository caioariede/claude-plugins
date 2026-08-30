"""Tests for merged-unit progress.md task reconciliation."""

import sys
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-resume" / "scripts"))
import ws_store as S  # noqa: E402
import reconcile as R  # noqa: E402
from test_ws_board import ledger, write_ws  # noqa: E402


class ReconcileTasksTests(unittest.TestCase):
    def test_ship_detect_dismissed_sha(self):
        u = S.Unit(slug="x", branch="x", repo="o/r",
                   log=[("t", "ship-detect-dismissed", "sha=abc123")])
        self.assertEqual(S.ship_detect_dismissed_sha(u), "abc123")

    def test_flips_open_tasks_only(self):
        raw = (
            "## Tasks\n"
            "- [x] T1  a\n"
            "- [ ] T2  b\n"
            "## Follow-ups\n"
            "- [ ] F1  later\n"
        )
        new, ids = S.reconcile_tasks_on_merge(raw)
        self.assertEqual(ids, ["T2"])
        self.assertIn("- [x] T2  b", new)
        self.assertIn("- [ ] F1  later", new)

    def test_no_op_when_all_checked(self):
        raw = "## Tasks\n- [x] T1  a\n"
        new, ids = S.reconcile_tasks_on_merge(raw)
        self.assertEqual(ids, [])
        self.assertEqual(new, raw)

    def test_no_tasks_section(self):
        raw = "## Follow-ups\n- [ ] F1  x\n"
        new, ids = S.reconcile_tasks_on_merge(raw)
        self.assertEqual(ids, [])
        self.assertEqual(new, raw)


class MaybeReconcileTests(unittest.TestCase):
    def test_writes_progress_and_log(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            udir = root / "units" / "feat"
            udir.mkdir(parents=True)
            (udir / "progress.md").write_text(
                "## Tasks\n- [x] T1  a\n- [ ] T2  b\n", encoding="utf-8")
            (udir / "log.md").write_text("# log\n", encoding="utf-8")
            pr = S.PR(number=42, state="MERGED", is_draft=False, base="main")
            changed = S.maybe_reconcile_merged_unit(root, "feat", pr)
            self.assertEqual(changed, ["T2"])
            prog = (udir / "progress.md").read_text(encoding="utf-8")
            self.assertIn("- [x] T2  b", prog)
            log = (udir / "log.md").read_text(encoding="utf-8")
            self.assertIn("reconciled tasks from merged PR #42: T2", log)

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            udir = root / "units" / "feat"
            udir.mkdir(parents=True)
            (udir / "progress.md").write_text(
                "## Tasks\n- [x] T1  a\n", encoding="utf-8")
            (udir / "log.md").write_text("# log\n", encoding="utf-8")
            pr = S.PR(number=1, state="MERGED", is_draft=False, base="main")
            self.assertEqual(S.maybe_reconcile_merged_unit(root, "feat", pr), [])

    def test_skips_non_merged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            udir = root / "units" / "feat"
            udir.mkdir(parents=True)
            (udir / "progress.md").write_text(
                "## Tasks\n- [ ] T1  a\n", encoding="utf-8")
            pr = S.PR(number=1, state="OPEN", is_draft=False, base="main")
            self.assertEqual(S.maybe_reconcile_merged_unit(root, "feat", pr), [])

    def test_reconcile_on_merged_via_log(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            udir = root / "units" / "feat"
            udir.mkdir(parents=True)
            (udir / "progress.md").write_text(
                "## Tasks\n- [ ] T1  a\n", encoding="utf-8")
            (udir / "log.md").write_text(
                "- 2026-01-01T00:00Z  merged-via  "
                "branch=master sha=abc pr=7\n",
                encoding="utf-8")
            u = S.Unit(slug="feat", log=S.parse_log(
                (udir / "log.md").read_text(encoding="utf-8")))
            mv = S.merged_via_record(u)
            changed = S.maybe_reconcile_merged_unit(
                root, "feat", None, merged_via=mv)
            self.assertEqual(changed, ["T1"])
            self.assertIn("- [x] T1  a",
                          (udir / "progress.md").read_text(encoding="utf-8"))
            self.assertIn("merged-via branch=master", (
                udir / "log.md").read_text(encoding="utf-8"))


class ReconcileCliTests(unittest.TestCase):
    def test_cli_reconciles_merged_unit(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            os.environ["WS_STORE"] = str(store)
            try:
                write_ws(
                    store,
                    "2026-01-01-demo",
                    units_md=ledger('spike  "S"  repo=o/r  branch=spike'),
                    units={
                        "spike": {
                            "progress": "## Tasks\n- [ ] T6  verify\n",
                        },
                    },
                )
                import ws_cli as C
                original = C.gather_pr_state

                def fake(ws, st, branches=None):
                    return {"spike": S.PR(number=9, state="MERGED",
                                          is_draft=False, base="main")}

                C.gather_pr_state = fake
                try:
                    code = R.main(["spike"])
                finally:
                    C.gather_pr_state = original
                self.assertEqual(code, 0)
                prog = (store / "2026-01-01-demo" / "units" / "spike"
                        / "progress.md").read_text(encoding="utf-8")
                self.assertIn("- [x] T6  verify", prog)
            finally:
                os.environ.pop("WS_STORE", None)


if __name__ == "__main__":
    unittest.main()
