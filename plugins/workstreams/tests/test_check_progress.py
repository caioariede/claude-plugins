"""Tests for apply_check_progress and task check-off."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))

import ws_store as S  # noqa: E402
from test_ws_board import ledger, spike_ledger, write_ws  # noqa: E402


class CheckProgressTests(unittest.TestCase):
    def test_checks_task_ids(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u  "U"  repo=o/r  branch=u'),
                units={
                    "u": {
                        "progress": (
                            "## Tasks\n"
                            "- [ ] T1  Foo\n"
                            "- [ ] T2  Bar\n\n"
                            "## Follow-ups\n\n## Needs\n"
                        ),
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_check_progress(ws_dir, "u", ["T1"])
            self.assertEqual(status, "checked")
            self.assertEqual(ids, ["T1"])
            prog = (ws_dir / "units" / "u" / "progress.md").read_text(
                encoding="utf-8")
            self.assertIn("- [x] T1  Foo", prog)
            self.assertIn("- [ ] T2  Bar", prog)

    def test_idempotent_already_checked(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u  "U"  repo=o/r  branch=u'),
                units={
                    "u": {
                        "progress": "## Tasks\n- [x] T1  Foo\n\n## Follow-ups\n\n## Needs\n",
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_check_progress(ws_dir, "u", ["T1"])
            self.assertEqual(status, "already-checked")
            self.assertEqual(ids, ["T1"])

    def test_refuses_missing_id(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u  "U"  repo=o/r  branch=u'),
                units={
                    "u": {
                        "progress": "## Tasks\n- [ ] T1  Foo\n\n## Follow-ups\n\n## Needs\n",
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_check_progress(ws_dir, "u", ["T9"])
            self.assertEqual(status, "refused missing:T9")
            self.assertEqual(ids, [])

    def test_refuses_empty_ids(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u  "U"  repo=o/r  branch=u'),
                units={"u": {"progress": "## Tasks\n\n## Follow-ups\n\n## Needs\n"}},
            )
            status, ids = S.apply_check_progress(
                store / "2026-01-01-demo", "u", [])
            self.assertEqual(status, "refused empty-ids")
            self.assertEqual(ids, [])

    def test_checks_followup_on_unit(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u  "U"  repo=o/r  branch=u'),
                units={
                    "u": {
                        "progress": (
                            "## Tasks\n- [x] T1  Foo\n\n"
                            "## Follow-ups\n- [ ] F1  Fix nit\n\n## Needs\n"
                        ),
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_check_progress(ws_dir, "u", ["F1"])
            self.assertEqual(status, "checked")
            self.assertEqual(ids, ["F1"])
            prog = (ws_dir / "units" / "u" / "progress.md").read_text(
                encoding="utf-8")
            self.assertIn("- [x] F1  Fix nit", prog)

    def test_tasks_done_checks_all_unchecked_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u  "U"  repo=o/r  branch=u'),
                units={
                    "u": {
                        "progress": (
                            "## Tasks\n"
                            "- [x] T1  Foo\n"
                            "- [ ] T2  Bar\n"
                            "- [ ] T3  Baz\n\n"
                            "## Follow-ups\n- [ ] F1  Open\n\n## Needs\n"
                        ),
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_check_progress(
                ws_dir, "u", S.unchecked_task_ids(
                    (ws_dir / "units" / "u" / "progress.md").read_text(
                        encoding="utf-8")))
            self.assertEqual(status, "checked")
            self.assertEqual(ids, ["T2", "T3"])
            prog = (ws_dir / "units" / "u" / "progress.md").read_text(
                encoding="utf-8")
            self.assertIn("- [x] T2  Bar", prog)
            self.assertIn("- [x] T3  Baz", prog)
            self.assertIn("- [ ] F1  Open", prog)

    def test_spike_task_only(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            write_ws(
                store,
                "2026-01-01-demo",
                spikes_md=spike_ledger('s  "S"  repo=o/r'),
                spikes={
                    "s": {
                        "progress": "## Tasks\n- [ ] T1  Research\n\n## Needs\n",
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_check_progress(
                ws_dir, "s", ["T1"], kind="spike")
            self.assertEqual(status, "checked")
            self.assertEqual(ids, ["T1"])

    def test_code_complete_unit_emits_no_ws_next_move(self):
        from test_ws_board import mkws, moves_of, pr  # noqa: E402
        u = S.Unit(slug="a", branch="a", tasks_total=2, tasks_done=2,
                   pr=pr(12, "OPEN", False, "master"),
                   log=[("t", "created", "base=master")])
        self.assertEqual(moves_of(mkws([u])), [])


if __name__ == "__main__":
    unittest.main()
