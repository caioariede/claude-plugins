"""Tests for gen_flows diagram generation and checks."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))

import gen_flows as GF  # noqa: E402


class GenFlowsTests(unittest.TestCase):
    def test_core_unit_phases_in_diagram(self):
        diagrams = GF.get_all_diagrams()
        resume_mmd = diagrams["resume.mmd"]
        for phase in GF.CORE_UNIT_PHASES:
            self.assertIn(
                phase,
                resume_mmd,
                f"Expected phase {phase!r} to appear in resume.mmd",
            )

    def test_all_spike_phases_in_diagram(self):
        diagrams = GF.get_all_diagrams()
        resume_mmd = diagrams["resume.mmd"]
        for phase in GF.SPIKE_PHASES:
            self.assertIn(
                phase,
                resume_mmd,
                f"Expected phase {phase!r} to appear in resume.mmd",
            )

    def test_resume_diagram_covers_both_kinds(self):
        resume_mmd = GF.get_all_diagrams()["resume.mmd"]
        self.assertIn("unit_prep", resume_mmd)
        self.assertIn("spike_prep", resume_mmd)
        self.assertNotIn("resume-unit.mmd", resume_mmd)
        self.assertNotIn("resume-spike.mmd", resume_mmd)

    def test_next_terminal_states_in_diagram(self):
        diagrams = GF.get_all_diagrams()
        next_mmd = diagrams["next-terminal.mmd"]
        for state in GF.NEXT_TERMINAL_STATES:
            self.assertIn(
                state,
                next_mmd,
                f"Expected state {state!r} to appear in next-terminal.mmd",
            )

    def test_all_diagrams_generated(self):
        diagrams = GF.get_all_diagrams()
        expected_diagrams = {
            "resume.mmd",
            "next-terminal.mmd",
            "oneshot.mmd",
            "start.mmd",
            "spike.mmd",
            "block.mmd",
            "drop.mmd",
            "focus.mmd",
        }
        self.assertEqual(set(diagrams.keys()), expected_diagrams)

    def test_check_diagrams_clean(self):
        self.assertTrue(GF.check_diagrams())

    def test_cli_check_exits_zero(self):
        cmd = [sys.executable, str(ROOT / "skills" / "ws" / "scripts" / "gen_flows.py"), "--check"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"stderr: {res.stderr}\nstdout: {res.stdout}")

    def test_evals_json_up_to_date(self):
        cmd = [sys.executable, str(ROOT / "skills" / "ws-resume" / "evals" / "gen_evals.py"), "--check"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"stderr: {res.stderr}\nstdout: {res.stdout}")


if __name__ == "__main__":
    unittest.main()
