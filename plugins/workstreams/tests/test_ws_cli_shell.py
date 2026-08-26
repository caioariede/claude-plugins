import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
import ws_cli as C


class TestFillValidation(unittest.TestCase):
    def test_rejects_branch_injection(self):
        tpl = "gh pr view <branch> --repo org/repo"
        self.assertIsNone(C._fill(tpl, "main; rm -rf /", "org/repo"))

    def test_accepts_safe_branch(self):
        tpl = "gh pr view <branch> --repo org/repo"
        self.assertEqual(
            C._fill(tpl, "feat-x", "org/repo"),
            "gh pr view feat-x --repo org/repo")


class TestRunTextCmd(unittest.TestCase):
    def test_rejects_pipes(self):
        self.assertIsNone(C._run_text_cmd("echo ok | jq ."))

    @mock.patch("ws_cli._run_argv", return_value="ok")
    def test_splits_simple_command(self, run_argv):
        self.assertEqual(C._run_text_cmd("gh pr list --repo o/r"), "ok")
        run_argv.assert_called_once()


class TestWmxLocate(unittest.TestCase):
    @mock.patch("ws_cli._run_argv")
    def test_filters_branch_in_python(self, run_argv):
        run_argv.return_value = (
            '[{"branch":"refs/heads/feat-a","path":"/wt/a"},'
            ' {"branch":"refs/heads/feat-b","path":"/wt/b"}]'
        )
        with mock.patch.object(Path, "is_dir", return_value=True):
            p = C._locate_from_wmx_json("feat-b")
        self.assertEqual(p, Path("/wt/b"))


if __name__ == "__main__":
    unittest.main()
