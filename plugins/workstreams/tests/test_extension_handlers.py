"""Integration tests for extension phase handlers and runner."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ws" / "scripts"))

import extension_runner as ER  # noqa: E402
import ws_cli as C  # noqa: E402
import ws_store as S  # noqa: E402

PLUGIN_ROOT = ROOT
PREWALK = PLUGIN_ROOT / "skills" / "ws" / "extensions" / "prewalk"
CRITIC = PLUGIN_ROOT / "skills" / "ws" / "extensions" / "critic"


def _invoke(handler: Path, ctx: dict, *, ext_id: str, slot: str) -> str:
    req = {"v": 1, "op": "pending", "extension": ext_id, "slot": slot, "ctx": ctx}
    proc = subprocess.run(
        [sys.executable, str(handler)],
        input=json.dumps(req) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout.strip())["phase"]


def _ws(units):
    return S.Workstream(ws_id="2026-01-01-ws", name="ws", units=units,
                        spikes=[])


def _unit(log=None, tasks_total=0, tasks_done=0):
    return S.Unit(
        slug="u", repo="o/r", branch="u", dropped=False,
        tasks_total=tasks_total, tasks_done=tasks_done,
        log=log or [], followups=[], needs=[])


def _complete_unit(log=None):
    return _unit(log=log, tasks_total=1, tasks_done=1)


def _store_prewalk(td: str) -> Path:
    store = Path(td) / "workstreams"
    store.mkdir()
    (store / "flavors.ini").write_text(
        "[active]\nspec-driven-development = superpowers-prewalk\n",
        "utf-8",
    )
    return store


def _store_critic(td: str) -> Path:
    store = Path(td) / "workstreams"
    store.mkdir()
    (store / "flavors.ini").write_text(
        "[active]\nreview = ws-critic\n",
        "utf-8",
    )
    return store


def _resume(u, ws, store, *, headless=False, skip=None, tree_digest="deadbeef",
            models_ready=None):
    by = {u.slug: u}
    ctx = C.build_extension_ctx(
        store, u, headless=headless, skip_extensions=skip or set())
    if tree_digest is not None:
        ctx["artifacts"]["tree_digest"] = tree_digest
    if models_ready is not None:
        ctx["artifacts"]["models_ready"] = models_ready
    pending = lambda slot: ER.pending_for_slot(slot, ctx, store, kind="unit")
    return S.resume_phase(u, ws, by, extension_pending=pending)


class ExtensionHandlerTests(unittest.TestCase):
    def test_prewalk_handler_returns_prewalk(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix="-plan.md") as f:
            f.write("plan body")
            path = f.name
        digest = S.plan_file_digest(path)
        ctx = {
            "skip": [],
            "artifacts": {
                "plan_path": path,
                "plan_digest": digest,
                "models_ready": True,
            },
            "unit": {"log": [["ts", "plan", path]]},
        }
        self.assertEqual(_invoke(PREWALK, ctx, ext_id="prewalk", slot="post_plan"),
                         "prewalk")

    def test_critic_handler_returns_critic(self):
        ctx = {
            "skip": [],
            "artifacts": {"tree_digest": "deadbeef"},
            "unit": {"log": []},
        }
        self.assertEqual(
            _invoke(CRITIC, ctx, ext_id="critic", slot="post_scoped_work"),
            "critic")


class ExtensionRunnerTests(unittest.TestCase):
    def test_expand_skip_id_to_phases(self):
        phases = ER.expand_skip_tokens({"prewalk"})
        self.assertEqual(phases, {"prewalk-config", "prewalk"})

    def test_resume_prewalk_via_runner(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_prewalk(td)
            with tempfile.NamedTemporaryFile("w", delete=False, suffix="-plan.md") as f:
                f.write("plan body")
                path = f.name
            u = _unit(log=[("ts", "plan", path)])
            ws = S.Workstream(ws_id="w", name="w", units=[u], spikes=[])
            self.assertEqual(_resume(u, ws, store, models_ready=True), "prewalk")

    def test_resume_critic_via_runner(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store_critic(td)
            u = _complete_unit()
            ws = S.Workstream(ws_id="w", name="w", units=[u], spikes=[])
            self.assertEqual(_resume(u, ws, store), "critic")


if __name__ == "__main__":
    unittest.main()
