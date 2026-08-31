"""Critic phase insertion and digest binding."""

import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))

import ws_store as S  # noqa: E402


def _unit(log=None, tasks_total=1, tasks_done=1):
    return S.Unit(
        slug="u", repo="o/r", branch="u", dropped=False,
        tasks_total=tasks_total, tasks_done=tasks_done,
        log=log or [], followups=[], needs=[])


def _ws(unit):
    return S.Workstream(ws_id="2026-01-01-ws", name="ws",
                        units=[unit], spikes=[])


class CriticPhaseTest(unittest.TestCase):
    def test_code_complete_unit_enters_critic(self):
        unit = _unit()
        self.assertEqual(
            S.resume_phase(unit, _ws(unit), {"u": unit},
                           review_enabled=True, critic_digest="deadbeef"),
            "critic")

    def test_matching_digest_skips_critic(self):
        unit = _unit(log=[
            ("2026-01-02T00:00Z", "decision",
             "critic=done verdict=READY digest=deadbeef"),
        ])
        self.assertEqual(
            S.resume_phase(unit, _ws(unit), {"u": unit},
                           review_enabled=True, critic_digest="deadbeef"),
            "done")

    def test_changed_digest_reopens_critic(self):
        unit = _unit(log=[
            ("2026-01-02T00:00Z", "decision",
             "critic=done verdict=READY digest=deadbeef"),
        ])
        self.assertEqual(
            S.resume_phase(unit, _ws(unit), {"u": unit},
                           review_enabled=True, critic_digest="cafebabe"),
            "critic")

    def test_skip_critic_bypasses_phase(self):
        unit = _unit()
        self.assertEqual(
            S.resume_phase(unit, _ws(unit), {"u": unit},
                           review_enabled=True, skip_critic=True),
            "done")

    def test_grandfather_critic_bypasses_phase(self):
        unit = _unit()
        self.assertEqual(
            S.resume_phase(unit, _ws(unit), {"u": unit},
                           review_enabled=True, grandfather_critic=True),
            "done")

    def test_review_disabled_bypasses_phase(self):
        unit = _unit()
        self.assertEqual(
            S.resume_phase(unit, _ws(unit), {"u": unit},
                           critic_digest="deadbeef"),
            "done")

    def test_readiness_suffix_for_critic(self):
        self.assertEqual(S.unit_readiness(_unit(), phase="critic"),
                         "critic (reviewing)")

    def test_unit_board_suffix_critic(self):
        u = _unit()
        self.assertEqual(S.unit_board_suffix(u, phase="critic"),
                         "critic (reviewing)")

    def test_none_digest_skips_critic(self):
        unit = _unit()
        self.assertEqual(
            S.resume_phase(unit, _ws(unit), {"u": unit},
                           review_enabled=True, critic_digest=None),
            "done")
