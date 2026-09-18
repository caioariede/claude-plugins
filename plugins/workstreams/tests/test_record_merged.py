"""Per-PR merged log audit (ws_store + record_merged CLI)."""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-resume" / "scripts"))

import ws_store as S  # noqa: E402
from test_ws_board import ledger, pr, write_ws  # noqa: E402


def unit_with_log(log, pr_obj=None):
    u = S.Unit(slug="a", branch="a", repo="o/r")
    u.log = log
    u.pr = pr_obj
    return u


class MergedLogged(unittest.TestCase):
    def test_kind_merged_pr_field_matches(self):
        u = unit_with_log([("t", "merged", "pr=10")])
        self.assertTrue(S.merged_logged(u, 10))
        self.assertFalse(S.merged_logged(u, 101))

    def test_note_mentioning_pr_does_not_count(self):
        u = unit_with_log([("t", "note", "see pr=10 later")])
        self.assertFalse(S.merged_logged(u, 10))

    def test_pr_10_does_not_match_pr_101_payload(self):
        u = unit_with_log([("t", "merged", "pr=101")])
        self.assertFalse(S.merged_logged(u, 10))
        self.assertTrue(S.merged_logged(u, 101))


class MergedPrToRecord(unittest.TestCase):
    def test_merged_pr_number_returns_n(self):
        u = unit_with_log(
            [("t", "created", "base=feat-x")],
            pr(12, "MERGED", False, "master"))
        self.assertEqual(S.merged_pr_to_record(u), 12)

    def test_already_logged_returns_none(self):
        u = unit_with_log(
            [("t", "merged", "pr=12")],
            pr(12, "MERGED", False, "master"))
        self.assertIsNone(S.merged_pr_to_record(u))

    def test_open_pr_returns_none(self):
        u = unit_with_log([], pr(12, "OPEN", True, "master"))
        self.assertIsNone(S.merged_pr_to_record(u))

    def test_closed_pr_returns_none(self):
        u = unit_with_log([], pr(12, "CLOSED", False, "master"))
        self.assertIsNone(S.merged_pr_to_record(u))

    def test_missing_number_returns_none(self):
        u = unit_with_log([], S.PR(None, "MERGED", False, "master"))
        self.assertIsNone(S.merged_pr_to_record(u))


class RecordMergedCli(unittest.TestCase):
    def test_appends_once_then_already(self):
        import record_merged as RM  # noqa: E402
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(
                store, "2026-01-01-demo",
                units_md=ledger('a  "A"  repo=o/r  branch=a'),
                units={"a": {
                    "progress": "## Tasks\n- [ ] T1  x\n",
                    "log": "- 2026-01-01T00:00Z  created  base=feat-x\n",
                }})
            merged = pr(12, "MERGED", False, "master")
            env = {**os.environ, "WS_STORE": str(store)}
            with mock.patch.dict(os.environ, env, clear=False), \
                 mock.patch("record_merged.C.gather_pr_state",
                            return_value={"a": merged}):
                out1 = io.StringIO()
                out2 = io.StringIO()
                with mock.patch("sys.stdout", out1):
                    first = RM.main(["a"])
                with mock.patch("sys.stdout", out2):
                    second = RM.main(["a"])
            self.assertEqual(first, 0)
            self.assertEqual(second, 0)
            self.assertIn("recorded pr=12", out1.getvalue())
            self.assertIn("already pr=12", out2.getvalue())
            log_path = (store / "2026-01-01-demo" / "units" / "a"
                        / "log.md")
            merged_lines = [
                (kind, payload) for _ts, kind, payload
                in S.parse_log(log_path.read_text(encoding="utf-8"))
                if kind == "merged"]
            self.assertEqual(merged_lines, [("merged", "pr=12")])
