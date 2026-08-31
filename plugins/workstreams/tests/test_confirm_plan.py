"""Tests for confirm_plan derivation and receipt latching."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-resume" / "scripts"))

import ws_store as S  # noqa: E402
from test_ws_board import ledger, spike_ledger, write_ws  # noqa: E402


class ConfirmPlanTests(unittest.TestCase):
    def test_confirm_plan_derives_and_appends_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            plan = store / "plan.md"
            plan.write_text("### Task 1: Foo\n### Task 2: Bar\n", encoding="utf-8")
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u  "U"  repo=o/r  branch=u'),
                units={
                    "u": {
                        "progress": "## Tasks\n\n## Follow-ups\n\n## Needs\n",
                        "log": f"- 2026-01-01T00:00Z  plan  {plan}\n",
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_confirm_plan(ws_dir, "u", plan)
            self.assertEqual(status, "confirmed")
            self.assertEqual(ids, ["T1", "T2"])

            log_text = (ws_dir / "units" / "u" / "log.md").read_text(encoding="utf-8")
            self.assertIn("plan=done", log_text)
            self.assertIn(f"plan={plan}", log_text)
            self.assertIn("digest=", log_text)

            prog_text = (ws_dir / "units" / "u" / "progress.md").read_text(encoding="utf-8")
            self.assertIn("- [ ] T1  Foo", prog_text)
            self.assertIn("- [ ] T2  Bar", prog_text)

    def test_confirm_plan_idempotent_when_tasks_exist(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            plan = store / "plan.md"
            plan.write_text("### Task 1: Foo\n", encoding="utf-8")
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u  "U"  repo=o/r  branch=u'),
                units={
                    "u": {
                        "progress": "## Tasks\n- [ ] T1  Foo\n\n## Follow-ups\n\n## Needs\n",
                        "log": f"- 2026-01-01T00:00Z  plan  {plan}\n",
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_confirm_plan(ws_dir, "u", plan)
            self.assertEqual(status, "already-has-tasks")
            self.assertEqual(ids, [])

    def test_confirm_plan_spike_adds_amend_task(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            plan = store / "plan.md"
            plan.write_text("### Task 1: Spike work\n", encoding="utf-8")
            write_ws(
                store,
                "2026-01-01-demo",
                spikes_md=spike_ledger('s  "S"  repo=o/r'),
                spikes={
                    "s": {
                        "progress": "## Tasks\n\n## Needs\n",
                        "log": f"- 2026-01-01T00:00Z  plan  {plan}\n",
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_confirm_plan(ws_dir, "s", plan, kind="spike")
            self.assertEqual(status, "confirmed")
            self.assertEqual(ids, ["T1", "T2"])

            prog_text = (ws_dir / "spikes" / "s" / "progress.md").read_text(encoding="utf-8")
            self.assertIn(f"- [ ] T2  {S.SPIKE_AMEND_TASK}", prog_text)

    def test_confirm_plan_never_receipt_on_bad_plan(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            missing = store / "nonexistent.md"
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u  "U"  repo=o/r  branch=u'),
                units={
                    "u": {
                        "progress": "## Tasks\n\n## Follow-ups\n\n## Needs\n",
                        "log": f"- 2026-01-01T00:00Z  plan  {missing}\n",
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_confirm_plan(ws_dir, "u", missing)
            self.assertEqual(status, "refused no-plan")
            self.assertEqual(ids, [])

            log_text = (ws_dir / "units" / "u" / "log.md").read_text(encoding="utf-8")
            self.assertNotIn("plan=done", log_text)

    def test_headless_confirm_writes_context_and_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            plan = store / "plan.md"
            plan.write_text("### Task 1: Auto work\n", encoding="utf-8")
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u  "U"  repo=o/r  branch=u'),
                units={
                    "u": {
                        "progress": "## Tasks\n\n## Follow-ups\n\n## Needs\n",
                        "log": f"- 2026-01-01T00:00Z  plan  {plan}\n",
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_confirm_plan(
                ws_dir,
                "u",
                plan,
                reason="headless",
                context=("spec-driven-development", "subagent"),
            )
            self.assertEqual(status, "confirmed")
            self.assertEqual(ids, ["T1"])

            log_text = (ws_dir / "units" / "u" / "log.md").read_text(encoding="utf-8")
            self.assertIn("reason=headless", log_text)
            self.assertIn("context spec-driven-development=subagent", log_text)

    def test_migrate_appends_plan_done_for_legacy_execute_mode(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            plan = store / "plan.md"
            plan.write_text("### Task 1: Foo\n", encoding="utf-8")
            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u  "U"  repo=o/r  branch=u'),
                units={
                    "u": {
                        "progress": "## Tasks\n- [ ] T1  Foo\n\n## Follow-ups\n\n## Needs\n",
                        "log": (
                            f"- 2026-01-01T00:00Z  plan  {plan}\n"
                            "- 2026-01-01T00:01Z  decision  execute-mode=subagent-driven\n"
                        ),
                    },
                },
            )
            ws_dir = store / "2026-01-01-demo"
            status, ids = S.apply_confirm_plan(
                ws_dir, "u", plan, migrate_only=True)
            self.assertEqual(status, "migrated")
            self.assertEqual(ids, ["T1"])
            log_text = (ws_dir / "units" / "u" / "log.md").read_text(encoding="utf-8")
            self.assertIn("plan=done", log_text)
            self.assertEqual(
                (ws_dir / "units" / "u" / "progress.md").read_text(encoding="utf-8"),
                "## Tasks\n- [ ] T1  Foo\n\n## Follow-ups\n\n## Needs\n",
            )

            # Re-running migrate is idempotent
            status2, _ = S.apply_confirm_plan(
                ws_dir, "u", plan, migrate_only=True)
            self.assertEqual(status2, "already-has-tasks")


if __name__ == "__main__":
    unittest.main()
