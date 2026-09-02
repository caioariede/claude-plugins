#!/usr/bin/env python3
"""Generate ws-next eval outputs and grades for skill-creator review."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WS = ROOT / "skills" / "ws"
NEXT = ROOT / "skills" / "ws-next"
EVALS = NEXT / "evals"
WORKSPACE = NEXT.parent / "ws-next-workspace" / "iteration-1"

sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(EVALS))
sys.path.insert(0, str(ROOT / "tests"))

import ws_store as S  # noqa: E402
from chain_expectations import (  # noqa: E402
    chain_offers_propose,
    chain_propose_options,
    chain_runs_unit_picker,
    propose_source_summary,
)
from lane_expectations import strategy_lanes  # noqa: E402
from test_ws_board import mkws, pr  # noqa: E402

sys.path.insert(0, str(NEXT / "scripts"))
import next as next_mod  # noqa: E402


def scenario(name: str):
    """Build a Decision + rendered script output for named eval."""
    if name == "mid-flight-single-move-chain":
        live = S.Unit(slug="certificate-pdf-polish", tasks_total=6,
                      tasks_done=5)
        ws = mkws([live], design="~/specs/cert-design.md")
        d = S.decide_next(ws)
        return d, next_mod.render_decision(d)

    if name == "restack-keeps-propose":
        drift = S.Unit(slug="top", tasks_total=1, tasks_done=1,
                       pr=pr(5, "OPEN", False, "master"),
                       log=[("t", "created", "base=feat-base")])
        ws = mkws([drift], design="~/specs/x-design.md")
        d = S.decide_next(ws)
        return d, next_mod.render_decision(d)

    if name == "mixed-ship-mid-flight-chain":
        ship = S.Unit(slug="done1", tasks_total=1, tasks_done=1, pr=None)
        live = S.Unit(slug="a", tasks_total=2, tasks_done=1)
        ws = mkws([ship, live], design="~/specs/x-design.md")
        d = S.decide_next(ws)
        return d, next_mod.render_decision(d)

    if name == "blocking-wf-solo-first":
        merged = S.Unit(slug="m", title="did m", tasks_total=1,
                        tasks_done=1, pr=pr(1, "MERGED"))
        dep = S.Unit(slug="dep", needs=[S.Need("N1", "WF4")])
        ws = mkws([merged, dep],
                  wfs=[S.Followup("WF4", "harden it", checked=False)])
        d = S.decide_next(ws)
        return d, next_mod.render_decision(d)

    if name == "design-only-suggest":
        ws = mkws(design="~/specs/x-design.md")
        d = S.decide_next(ws)
        return d, next_mod.render_decision(d)

    if name == "chain-many-followups-summary":
        live = S.Unit(slug="thread-real-signature-method", tasks_total=4,
                      tasks_done=1)
        wfs = [S.Followup(f"WF{i}", f"item {i}", checked=False)
               for i in range(32, 60)]
        ws = mkws([live], wfs=wfs, design="~/specs/signing-design.md")
        d = S.decide_next(ws)
        return d, next_mod.render_decision(d)

    raise KeyError(name)


def grade(name: str, d: S.Decision, rendered: str) -> list[dict]:
    checks: list[tuple[str, bool, str]] = []

    if name == "mid-flight-single-move-chain":
        opts = chain_propose_options(d)
        checks = [
            ("chain picker runs", chain_runs_unit_picker(d),
             f"moves={len(d.moves)} design={d.design!r}"),
            ("propose offered", chain_offers_propose(d),
             f"proposable={len(d.proposable)} covered={len(d.covered)}"),
            ("design attached", bool(d.design),
             f"design={d.design!r}"),
            ("rule is resume", d.rule == "resume", f"rule={d.rule}"),
            ("single propose option",
             opts == ["Propose from design spec"], f"opts={opts}"),
        ]
    elif name == "restack-keeps-propose":
        opts = chain_propose_options(d)
        checks = [
            ("rule is restack", d.rule == "restack", f"rule={d.rule}"),
            ("propose offered alongside restack", chain_offers_propose(d),
             f"design={d.design!r} covered={len(d.covered)}"),
            ("chain picker runs", chain_runs_unit_picker(d),
             f"moves={len(d.moves)}"),
            ("single propose option",
             opts == ["Propose from design spec"], f"opts={opts}"),
        ]
    elif name == "mixed-ship-mid-flight-chain":
        checks = [
            ("two moves", len(d.moves) == 2, f"moves={[m.unit for m in d.moves]}"),
            ("propose offered", chain_offers_propose(d), ""),
            ("design attached", bool(d.design), ""),
        ]
    elif name == "blocking-wf-solo-first":
        lanes = strategy_lanes(d)
        checks = [
            ("WF4 blocking first", lanes[0].startswith("WF4"),
             f"lanes={lanes}"),
        ]
    elif name == "design-only-suggest":
        lanes = strategy_lanes(d)
        checks = [
            ("suggest mode", d.rule == "suggest", f"rule={d.rule}"),
            ("design lane only", lanes == ["From design spec"],
             f"lanes={lanes}"),
        ]
    elif name == "chain-many-followups-summary":
        opts = chain_propose_options(d)
        checks = [
            ("chain picker runs", chain_runs_unit_picker(d), ""),
            ("propose offered", chain_offers_propose(d),
             f"proposable={len(d.proposable)}"),
            ("two chain propose options", len(opts) == 2,
             f"opts={opts}"),
            ("design propose option",
             "Propose from design spec" in opts, f"opts={opts}"),
            ("follow-ups propose option",
             "Propose from Workstream follow-ups" in opts, f"opts={opts}"),
        ]

    return [{"text": t, "passed": p, "evidence": e} for t, p, e in checks]


def main() -> int:
    evals = json.loads((EVALS / "evals.json").read_text())["evals"]
    focus = {5: "mid-flight-single-move-chain",
             6: "restack-keeps-propose",
             7: "mixed-ship-mid-flight-chain",
             8: "chain-many-followups-summary",
             1: "blocking-wf-solo-first",
             2: "design-only-suggest"}

    for ev in evals:
        eid = ev["id"]
        name = ev["name"]
        if eid not in focus:
            continue
        key = focus[eid]
        d, rendered = scenario(key)
        out_dir = WORKSPACE / f"eval-{eid}-{name}" / "with_skill" / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "script_output.txt").write_text(rendered)
        chain = {
            "runs_unit_picker": chain_runs_unit_picker(d),
            "offers_propose": chain_offers_propose(d),
            "strategy_lanes": strategy_lanes(d) if has_proposal(d) else [],
            "chain_propose_options": chain_propose_options(d)
            if chain_offers_propose(d) else [],
        }
        (out_dir / "chain_behavior.json").write_text(
            json.dumps(chain, indent=2))

        meta = {
            "eval_id": eid,
            "eval_name": name,
            "prompt": ev["prompt"],
            "assertions": [g["text"] for g in grade(name, d, rendered)],
        }
        (WORKSPACE / f"eval-{eid}-{name}" / "eval_metadata.json").write_text(
            json.dumps(meta, indent=2))

        grading = {"expectations": grade(name, d, rendered)}
        (WORKSPACE / f"eval-{eid}-{name}" / "with_skill" / "grading.json").write_text(
            json.dumps(grading, indent=2))

    print(f"Wrote eval outputs to {WORKSPACE}")
    return 0


def has_proposal(d: S.Decision) -> bool:
    return bool(d.proposable or d.covered or d.design
                or d.rule in ("suggest", "reconcile-pending"))


if __name__ == "__main__":
    raise SystemExit(main())
