"""Tests for plan task derivation and progress writes."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
import ws_store as S


PLAN = """\
# Plan

### Task 1: First thing

Do it.

### Task 3: Third

Later.

### Task 2: Second

Middle.
"""


class DeriveTasksTests(unittest.TestCase):
    def test_normal_plan(self):
        got = S.derive_tasks_from_plan(PLAN)
        self.assertEqual(got, [(1, "First thing"), (2, "Second"),
                               (3, "Third")])

    def test_gaps_ok(self):
        text = "### Task 1: a\n\n### Task 5: b\n"
        self.assertEqual(S.derive_tasks_from_plan(text),
                         [(1, "a"), (5, "b")])

    def test_duplicate_raises(self):
        text = "### Task 1: a\n\n### Task 1: b\n"
        with self.assertRaises(S.PlanParseError):
            S.derive_tasks_from_plan(text)

    def test_empty_raises(self):
        with self.assertRaises(S.PlanParseError):
            S.derive_tasks_from_plan("# no tasks\n")


class WriteTasksTests(unittest.TestCase):
    def test_writes_checked_tasks(self):
        raw = "## Tasks\n\n## Follow-ups\n- [ ] F1  x\n\n## Needs\n"
        tasks = [(1, "a"), (2, "b")]
        new, wrote = S.write_tasks_to_progress(raw, tasks, checked=True)
        self.assertTrue(wrote)
        self.assertIn("- [x] T1  a", new)
        self.assertIn("- [x] T2  b", new)
        self.assertIn("- [ ] F1  x", new)

    def test_writes_unchecked(self):
        raw = "## Tasks\n\n## Follow-ups\n\n## Needs\n"
        new, wrote = S.write_tasks_to_progress(
            raw, [(1, "x")], checked=False)
        self.assertTrue(wrote)
        self.assertIn("- [ ] T1  x", new)

    def test_refuses_when_tasks_exist(self):
        raw = "## Tasks\n- [ ] T1  old\n\n## Follow-ups\n\n## Needs\n"
        new, wrote = S.write_tasks_to_progress(
            raw, [(2, "new")], checked=False)
        self.assertFalse(wrote)
        self.assertEqual(new, raw)


if __name__ == "__main__":
    unittest.main()
