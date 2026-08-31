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
import phase as P      # noqa: E402
import ws_store as S   # noqa: E402
from test_ws_board import ledger, write_ws  # noqa: E402


class GateEmitTests(unittest.TestCase):
    def test_load_catalog(self):
        gates = GE.load_catalog()
        self.assertGreaterEqual(len(gates), 9)
        ids = {g["id"] for g in gates}
        self.assertIn("unit.plan-pause", ids)
        self.assertIn("unit.ship-pause", ids)
        self.assertIn("unit.draft-pr", ids)
        self.assertIn("unit.ship-detect", ids)
        self.assertIn("unit.blocked-override", ids)
        self.assertIn("unit.prewalk", ids)
        self.assertIn("unit.critic", ids)
        self.assertIn("spike.plan-pause", ids)
        self.assertIn("spike.blocked-override", ids)

    def test_find_gate(self):
        g = GE.find_gate("plan-pause", kind="unit")
        self.assertIsNotNone(g)
        self.assertEqual(g["id"], "unit.plan-pause")

        g_spike = GE.find_gate("plan-pause", kind="spike")
        self.assertIsNotNone(g_spike)
        self.assertEqual(g_spike["id"], "spike.plan-pause")

        g_ship_detect = GE.find_gate("ship-detect", kind="unit", overlay="ship-detect")
        self.assertIsNotNone(g_ship_detect)
        self.assertEqual(g_ship_detect["id"], "unit.ship-detect")

        g_none = GE.find_gate("nonexistent", kind="unit")
        self.assertIsNone(g_none)

    def test_plan_pause_is_action_gate(self):
        g = GE.find_gate("plan-pause", kind="unit")
        self.assertIsNotNone(g)
        self.assertEqual(g["kind"], "action")
        self.assertTrue(g["stop"])
        self.assertNotIn("options", g)

    def test_format_gate_block_picker(self):
        gate = {
            "id": "unit.ship-pause",
            "kind": "picker",
            "prompt": "How do you want to proceed?",
            "options": [
                {"n": 1, "label": "Not now (default)"},
                {"n": 2, "label": "Ship"},
            ],
        }
        block = GE.format_gate_block(gate)
        expected = "\n".join([
            "--- GATE: unit.ship-pause ---",
            "kind: picker",
            "prompt: How do you want to proceed?",
            "options:",
            "  1. Not now (default)",
            "  2. Ship",
            "--- END GATE ---",
        ])
        self.assertEqual(block, expected)

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

    def test_emit_gate_helper(self):
        block = GE.emit_gate("ship-pause", kind="unit")
        self.assertIsNotNone(block)
        self.assertTrue(block.startswith("--- GATE: unit.ship-pause ---"))
        self.assertTrue(block.endswith("--- END GATE ---"))

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

            cmd = [
                sys.executable,
                str(ROOT / "skills" / "ws-resume" / "scripts" / "phase.py"),
                "u1",
                "--emit-gate",
            ]
            env = dict(os.environ, WS_STORE=td)
            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
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


if __name__ == "__main__":
    unittest.main()
