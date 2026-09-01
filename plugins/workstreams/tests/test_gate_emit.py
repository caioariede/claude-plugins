"""Tests for gate_emit catalog and --emit-gate integrations."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "ws-resume" / "scripts"))

import gate_emit as GE  # noqa: E402
from test_ws_board import ledger, spike_ledger, write_ws  # noqa: E402

PHASE_PY = ROOT / "skills" / "ws-resume" / "scripts" / "phase.py"


def _phase_emit(store_td: str, target_id: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PHASE_PY), target_id, "--emit-gate"],
        env={**os.environ, "WS_STORE": store_td},
        capture_output=True,
        text=True,
    )


class GateEmitTests(unittest.TestCase):
    def test_load_catalog(self):
        gates = GE.load_catalog()
        self.assertGreaterEqual(len(gates), 9)
        ids = {g["id"] for g in gates}
        self.assertIn("unit.plan-pause", ids)
        self.assertIn("unit.blocked-override", ids)
        self.assertIn("unit.prewalk", ids)
        self.assertIn("unit.critic", ids)
        self.assertIn("unit.done", ids)
        self.assertIn("spike.plan-pause", ids)
        self.assertIn("spike.blocked-override", ids)
        self.assertIn("spike.done", ids)

    def test_find_gate(self):
        g = GE.find_gate("plan-pause", kind="unit")
        self.assertIsNotNone(g)
        self.assertEqual(g["id"], "unit.plan-pause")

        g_spike = GE.find_gate("plan-pause", kind="spike")
        self.assertIsNotNone(g_spike)
        self.assertEqual(g_spike["id"], "spike.plan-pause")

        g_none = GE.find_gate("nonexistent", kind="unit")
        self.assertIsNone(g_none)

    def test_plan_pause_is_action_gate(self):
        g = GE.find_gate("plan-pause", kind="unit")
        self.assertIsNotNone(g)
        self.assertEqual(g["kind"], "action")
        self.assertTrue(g["stop"])
        self.assertNotIn("options", g)

    def test_done_is_action_gate(self):
        for kind in ("unit", "spike"):
            g = GE.find_gate("done", kind=kind)
            self.assertIsNotNone(g)
            self.assertEqual(g["kind"], "action")
            self.assertTrue(g["stop"])
            self.assertEqual(g["action"], "chain_ws_next")

    def test_format_gate_block_with_context(self):
        gate = {
            "id": "unit.plan-pause",
            "kind": "picker",
            "prompt": "How do you want to execute?",
            "options": [
                {"n": 1, "label": "Not now (default)"},
                {"n": 2, "label": "Subagent"},
            ],
        }
        context = {
            "plan": "/tmp/plan.md",
            "tasks": ["T1 title", "T2 title"],
        }
        block = GE.format_gate_block(gate, context=context)
        self.assertIn("context:\n  plan: /tmp/plan.md\n  tasks:\n    - T1 title\n    - T2 title", block)

    def test_phase_cli_emit_gate(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td)
            plan_file = store / "plan.md"
            plan_file.write_text("### Task 1: Setup\n### Task 2: Build\n")

            write_ws(
                store,
                "2026-01-01-demo",
                units_md=ledger('u1  "Unit 1"  repo=o/r'),
                units={
                    "u1": {
                        "progress": "## Tasks\n",
                        "log": f"# log\n- 2026-01-01T00:00Z  plan  {plan_file}\n",
                    },
                },
            )

            res = _phase_emit(td, "u1")
            self.assertEqual(res.returncode, 0, f"stderr: {res.stderr}")
            lines = res.stdout.strip().splitlines()
            self.assertEqual(lines[0], "plan-pause")
            self.assertIn("--- GATE: unit.plan-pause ---", res.stdout)
            self.assertIn("kind: action", res.stdout)
            self.assertIn("prompt: Plan saved", res.stdout)
            self.assertIn("action: await_plan_confirm", res.stdout)
            self.assertIn("stop: true", res.stdout)
            self.assertIn("Setup", res.stdout)
            self.assertIn("Build", res.stdout)

    def test_done_gate_emit_unit(self):
        with tempfile.TemporaryDirectory() as td:
            write_ws(
                Path(td),
                "2026-01-01-demo",
                units_md=ledger('u1  "Unit 1"  repo=o/r'),
                units={
                    "u1": {
                        "progress": "## Tasks\n- [x] T1  Setup\n",
                        "log": "# log\n",
                    },
                },
            )

            res = _phase_emit(td, "u1")
            self.assertEqual(res.returncode, 0, f"stderr: {res.stderr}")
            self.assertEqual(res.stdout.strip().splitlines()[0], "done")
            self.assertIn("--- GATE: unit.done ---", res.stdout)
            self.assertIn("ws_id: 2026-01-01-demo", res.stdout)
            self.assertIn("slug: u1", res.stdout)

    def test_done_gate_emit_spike(self):
        with tempfile.TemporaryDirectory() as td:
            write_ws(
                Path(td),
                "2026-01-01-demo",
                spikes_md=spike_ledger('audit  "Audit"  repo=o/r'),
                spikes={
                    "audit": {
                        "progress": "## Tasks\n- [x] T1  Research\n",
                        "log": "# log\n",
                    },
                },
            )

            res = _phase_emit(td, "audit")
            self.assertEqual(res.returncode, 0, f"stderr: {res.stderr}")
            self.assertEqual(res.stdout.strip().splitlines()[0], "done")
            self.assertIn("--- GATE: spike.done ---", res.stdout)

    def test_loop_phase_emits_no_done_gate(self):
        with tempfile.TemporaryDirectory() as td:
            write_ws(
                Path(td),
                "2026-01-01-demo",
                units_md=ledger('u1  "Unit 1"  repo=o/r'),
                units={
                    "u1": {
                        "progress": "## Tasks\n- [x] T1  Setup\n- [ ] T2  Build\n",
                        "log": (
                            "# log\n"
                            "- 2026-01-01T00:00Z  plan  /tmp/plan.md\n"
                        ),
                    },
                },
            )

            res = _phase_emit(td, "u1")
            self.assertEqual(res.returncode, 0, f"stderr: {res.stderr}")
            self.assertEqual(res.stdout.strip().splitlines()[0], "loop")
            self.assertNotIn("--- GATE:", res.stdout)


if __name__ == "__main__":
    unittest.main()
