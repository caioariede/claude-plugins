import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
import ws_cli as C


class TestNormalizeRepoUrl(unittest.TestCase):
    def test_https(self):
        self.assertEqual(
            C._normalize_repo_url("https://github.com/Org/Repo.git"),
            "org/repo")

    def test_ssh_scp(self):
        self.assertEqual(
            C._normalize_repo_url("git@github.com:Org/Repo.git"),
            "org/repo")

    def test_ssh_url(self):
        self.assertEqual(
            C._normalize_repo_url("ssh://git@github.com/org/repo"),
            "org/repo")


if __name__ == "__main__":
    unittest.main()
