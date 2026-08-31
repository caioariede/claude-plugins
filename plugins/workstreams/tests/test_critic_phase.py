"""Critic phase insertion and digest binding."""

import tempfile
import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import ws_store as S  # noqa: E402
from test_extension_handlers import (  # noqa: E402
    _complete_unit, _resume, _store_critic, _unit, _ws,
)


class CriticPhaseTest(unittest.TestCase):
    def test_code_complete_unit_enters_critic(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_critic(td)
            unit = _complete_unit()
            self.assertEqual(_resume(unit, _ws([unit]), store), "critic")

    def test_matching_digest_skips_critic(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_critic(td)
            unit = _complete_unit(log=[
                ("2026-01-02T00:00Z", "decision",
                 "critic=done verdict=READY digest=deadbeef"),
            ])
            self.assertEqual(_resume(unit, _ws([unit]), store), "done")

    def test_changed_digest_reopens_critic(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_critic(td)
            unit = _complete_unit(log=[
                ("2026-01-02T00:00Z", "decision",
                 "critic=done verdict=READY digest=deadbeef"),
            ])
            self.assertEqual(
                _resume(unit, _ws([unit]), store, tree_digest="cafebabe"),
                "critic")

    def test_skip_critic_bypasses_phase(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_critic(td)
            unit = _complete_unit()
            self.assertEqual(
                _resume(unit, _ws([unit]), store, skip={"critic"}),
                "done")

    def test_grandfather_critic_bypasses_phase(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_critic(td)
            (store / "flavors.ini").write_text(
                "[active]\nreview = ws-critic\n"
                "[config]\nws-critic-activated-at = 2026-02-01T00:00Z\n",
                "utf-8",
            )
            unit = _complete_unit(log=[
                ("2026-01-01T00:00Z", "plan", "/tmp/plan.md"),
            ])
            self.assertEqual(_resume(unit, _ws([unit]), store), "done")

    def test_review_disabled_bypasses_phase(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "workstreams"
            store.mkdir()
            (store / "flavors.ini").write_text(
                "[active]\nreview = off\n", "utf-8")
            unit = _complete_unit()
            self.assertEqual(_resume(unit, _ws([unit]), store), "done")

    def test_readiness_suffix_for_critic(self):
        self.assertEqual(S.unit_readiness(_unit(), phase="critic"),
                         "critic (reviewing)")

    def test_unit_board_suffix_critic(self):
        u = _unit()
        self.assertEqual(S.unit_board_suffix(u, phase="critic"),
                         "critic (reviewing)")

    def test_none_digest_skips_critic(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_critic(td)
            unit = _complete_unit()
            self.assertEqual(
                _resume(unit, _ws([unit]), store, tree_digest=None),
                "done")


if __name__ == "__main__":
    unittest.main()
