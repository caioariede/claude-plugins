#!/usr/bin/env python3
"""Generate Mermaid flow diagrams for ws-* skills.

Derives flow diagrams from the authoritative routing paths in ws_store
and optionally decorates nodes with labels from gates.json.

Usage:
  gen_flows.py          # Regenerate .mmd files in references/flows/diagrams/
  gen_flows.py --check  # Verify contract: diagrams, schema, lint, parity, evals
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

import extension_runner as ER

FLOWS_DIR = Path(__file__).resolve().parents[1] / "references" / "flows"
DIAGRAMS_DIR = FLOWS_DIR / "diagrams"
GATES_FILE = FLOWS_DIR / "gates.json"
EXTENSIONS_FILE = FLOWS_DIR / "extensions.json"
EVALS_DIR = Path(__file__).resolve().parents[3] / "skills" / "ws-resume" / "evals"
SCENARIOS_MD = EVALS_DIR / "pressure-scenarios.md"
EVALS_JSON = EVALS_DIR / "evals.json"


def _extension_phases_for_slot(slot: str) -> List[str]:
    phases: List[str] = []
    rows = sorted(
        [e for e in ER.load_extensions() if e.get("slot") == slot],
        key=lambda e: int(e.get("order") or 0),
    )
    for row in rows:
        phases.extend(row.get("phases") or [])
    return phases


EXTENSION_UNIT_PHASES = (
    _extension_phases_for_slot("post_plan")
    + _extension_phases_for_slot("post_scoped_work")
)

UNIT_PHASES = (
    ["blocked", "plan"]
    + _extension_phases_for_slot("post_plan")
    + ["plan-pause", "loop"]
    + _extension_phases_for_slot("post_scoped_work")
    + ["done"]
)

CORE_UNIT_PHASES = [
    p for p in UNIT_PHASES if p not in EXTENSION_UNIT_PHASES
]

SPIKE_PHASES = [
    "blocked",
    "plan",
    "plan-pause",
    "loop",
    "done",
]

NEXT_TERMINAL_STATES = [
    "moves",
    "suggest",
    "open backlog remains",
    "no units yet",
    "workstream done",
]


def load_gates_catalog() -> Dict[str, Any]:
    if GATES_FILE.exists():
        try:
            with open(GATES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {g["id"]: g for g in data.get("gates", [])}
        except Exception:
            return {}
    return {}


def generate_resume_mmd(gates: Optional[Dict[str, Any]] = None) -> str:
    gates = gates or {}

    return """flowchart TD
    %% ws-resume — unit and spike execution flow

    start([Start / ws-resume]) --> resolve[Resolve ws_id, slug, kind]
    resolve --> kind{kind?}

    kind -- unit --> unit_prep[Ensure worktree, restack base, load state]
    kind -- spike --> spike_prep[Load spike store files + umbrella design]

    unit_prep --> blocked_guard[Blocked-awareness guard]
    spike_prep --> blocked_guard

    blocked_guard --> phase_py[phase.py --emit-gate]

    phase_py --> check_terminal{{Dropped or complete?}}
    check_terminal -- Yes --> ws_next([done → chain ws-next])
    check_terminal -- No --> check_needs{{Unmet needs?}}

    check_needs -- Yes --> blocked[blocked]
    blocked --> guard_blocked{{"blocked-override guard (unit or spike)"}}
    guard_blocked -- Confirm override --> check_zero_tasks
    guard_blocked -- Stop --> stop_blocked([stop])

    check_needs -- No --> check_zero_tasks{{Tasks total == 0?}}

    check_zero_tasks -- Yes --> check_plan_line{{Has plan line in log?}}
    check_plan_line -- No --> plan[plan]
    plan --> plan_save[Save plan] --> check_plan_line

    check_plan_line -- Yes --> pre_plan_ext{{Extension gate before plan-pause?}}
    pre_plan_ext -- Yes --> pre_plan_gate(["Flavor extension gate — gates.json"])
    pre_plan_gate --> pre_plan_ext
    pre_plan_ext -- No --> plan_pause(["plan-pause action gate"])
    plan_pause -- Confirm --> confirm_plan["confirm_plan.py --kind unit|spike"]
    confirm_plan --> loop

    check_zero_tasks -- No --> check_scope{{Scoped work complete?}}
    check_scope -- No --> loop[loop]
    loop --> work[Work first unchecked task per plan]
    work --> check_off[Check off in progress.md] --> check_scope
    check_scope -- Yes --> post_loop_ext{{Extension gate before done?}}
    post_loop_ext -- Yes --> post_loop_gate(["Flavor extension gate — gates.json"])
    post_loop_gate --> post_loop_ext
    post_loop_ext -- No --> ws_next

    classDef picker fill:#fef3c7,stroke:#d97706,stroke-width:2px;
    classDef action_stop fill:#fee2e2,stroke:#dc2626,stroke-width:2px;
    classDef terminal fill:#f3f4f6,stroke:#4b5563,stroke-width:2px;
    classDef condition fill:#e0e7ff,stroke:#4f46e5,stroke-width:2px;
    classDef action fill:#dcfce7,stroke:#16a34a,stroke-width:2px;
    classDef guard fill:#fef08a,stroke:#ca8a04,stroke-width:2px;

    class pre_plan_gate,post_loop_gate,plan_pause action_stop;
    class ws_next,stop_blocked terminal;
    class kind,check_terminal,check_needs,check_zero_tasks,check_plan_line,pre_plan_ext,check_scope,post_loop_ext condition;
    class resolve,unit_prep,spike_prep,blocked_guard,phase_py,plan,plan_save,confirm_plan,loop,work,check_off,blocked action;
    class guard_blocked guard;
"""


def _deprecated_resume_diagrams() -> Set[str]:
    return {"resume-unit.mmd", "resume-spike.mmd"}


def generate_next_terminal_mmd(gates: Optional[Dict[str, Any]] = None) -> str:
    gates = gates or {}
    return """flowchart TD
    %% ws-next decision engine and terminal states

    start([Start / ws-next]) --> derive[Derive status across units & spikes]
    derive --> check_moves{Runnable moves exist?}
    
    check_moves -- Yes --> rank_moves[Rank moves: restack > resume > start]
    rank_moves --> moves[Emit move list: default leading + Chain options]
    moves --> chain_pick{User selection in Chain}
    chain_pick -- Run move --> execute_move[Execute ws-resume / restack / start]
    chain_pick -- Propose lane --> propose_picker[Propose candidate picker]
    chain_pick -- Not now --> stop_moves([stop])
    
    check_moves -- No --> check_triage{Blocker dropped/removed only?}
    check_triage -- Yes --> triage_drop[blocker dropped/removed: route to ws-block]
    
    check_triage -- No --> check_unresolvable{Open backlog / unresolvable needs?}
    check_unresolvable -- Yes --> backlog_remains["open backlog remains / advance a blocker"]
    
    check_unresolvable -- No --> check_propose{Active focus, design, or open follow-ups?}
    check_propose -- Yes --> suggest["suggest: Propose next unit (strategy & candidate pickers)"]
    
    check_propose -- No --> check_empty_store{Empty workstream & no design?}
    check_empty_store -- Yes --> no_units["no units yet: offer ws-start"]
    check_empty_store -- No --> check_all_terminal{All units/spikes terminal & backlog empty?}
    check_all_terminal -- Yes --> ws_done["workstream done: offer to close"]
    check_all_terminal -- No --> fallback_suggest[suggest]

    classDef terminal fill:#f3f4f6,stroke:#4b5563,stroke-width:2px;
    classDef condition fill:#e0e7ff,stroke:#4f46e5,stroke-width:2px;
    classDef action fill:#dcfce7,stroke:#16a34a,stroke-width:2px;
    classDef state fill:#fef3c7,stroke:#d97706,stroke-width:2px;

    class done,stop_moves terminal;
    class check_moves,check_triage,check_unresolvable,check_propose,check_empty_store,check_all_terminal,chain_pick condition;
    class derive,rank_moves,moves,execute_move,propose_picker action;
    class triage_drop,backlog_remains,suggest,no_units,ws_done,fallback_suggest state;
"""


def generate_oneshot_mmd(gates: Optional[Dict[str, Any]] = None) -> str:
    return """flowchart TD
    %% ws-oneshot single-unit entry flow

    start([Start / ws-oneshot]) --> check_scope{Scope check: single PR & no existing ws?}
    check_scope -- No --> ws_init_fallback[Suggest ws-init / multi-unit]
    check_scope -- Yes --> step1[1. ws-init: create store & design]
    step1 --> step2[2. ws-start: create unit & worktree]
    step2 --> step3[3. ws-resume: auto-plan & pause gate]
    step3 --> plan_pause{plan-pause gate}
    plan_pause --> normal_resume([Enter normal ws-resume loop])
"""


def generate_start_mmd(gates: Optional[Dict[str, Any]] = None) -> str:
    return """flowchart TD
    %% ws-start unit provisioning flow

    start([Start / ws-start]) --> resolve[Resolve ws-id, slug, repo, base]
    resolve --> check_exists{units/slug exists?}
    check_exists -- Yes --> confirm_restart{Confirm resume or restart-of}
    confirm_restart --> create_wt[Create worktree for branch]
    check_exists -- No --> create_wt
    create_wt --> append_ledger[Append to units.md]
    append_ledger --> init_store[Create charter.md, progress.md, log.md]
    init_store --> check_claims{Has --claims?}
    check_claims -- Yes --> record_claims[Record claims & copy to purpose]
    check_claims -- No --> handoff
    record_claims --> handoff[Fire hook-ws-start-after / offer ws-resume]
    handoff --> resume([Run ws-resume])
"""


def generate_spike_mmd(gates: Optional[Dict[str, Any]] = None) -> str:
    return """flowchart TD
    %% ws-spike spike provisioning flow

    start([Start / ws-spike]) --> check_design{workstream.md design set?}
    check_design -- No --> refuse[Refuse: requires design spec]
    check_design -- Yes --> resolve[Resolve ws-id, slug, repo]
    resolve --> init_spike_store[Create spikes/slug: charter, progress, log, artifacts]
    init_spike_store --> append_ledger[Append to spikes.md]
    append_ledger --> seed_needs{Has --needs?}
    seed_needs -- Yes --> record_needs[Seed ## Needs in progress.md]
    seed_needs -- No --> offer_resume
    record_needs --> offer_resume[Offer ws-resume spike-id]
    offer_resume --> resume([Run ws-resume spike-id])
"""


def generate_block_mmd(gates: Optional[Dict[str, Any]] = None) -> str:
    return """flowchart TD
    %% ws-block dependency management flow

    start([Start / ws-block]) --> mode{Command mode}
    mode -- "needs (add)" --> resolve_target[Resolve unit/spike & target]
    resolve_target --> validate{Check self-need & cycle graph}
    validate -- Invalid --> refuse_cycle[Refuse: self-need or cycle detected]
    validate -- Valid --> append_need[Append monotonic N&lt;n&gt; to ## Needs]
    append_need --> log_decision[Append decision need N&lt;n&gt; to log.md]
    log_decision --> chain_next([Offer ws-next])

    mode -- "clear N<n>" --> resolve_clear[Resolve unit/spike & N<n>]
    resolve_clear --> remove_need[Remove N&lt;n&gt; line from ## Needs]
    remove_need --> log_clear[Append decision cleared need to log.md]
    log_clear --> chain_next
"""


def generate_drop_mmd(gates: Optional[Dict[str, Any]] = None) -> str:
    return """flowchart TD
    %% ws-drop abandonment flow

    start([Start / ws-drop]) --> check_status{Unit complete or spike complete?}
    check_status -- Yes --> refuse_complete[Refuse: work already finished]
    check_status -- No --> scan_dependents[Scan dependent units, spikes & backlog]
    scan_dependents --> confirm{Confirm teardown with user}
    confirm -- No --> abort([Stop / abort])
    confirm -- Yes --> check_kind{Kind?}
    check_kind -- Unit --> remove_wt[Remove worktree & delete local branch]
    check_kind -- Spike --> append_drop[Append dropped log line]
    remove_wt --> append_drop
    append_drop --> done([Unit / spike marked dropped])
"""


def generate_focus_mmd(gates: Optional[Dict[str, Any]] = None) -> str:
    return """flowchart TD
    %% ws-focus outcome queue flow

    start([Start / ws-focus]) --> subcmd{Subcommand}
    subcmd -- list --> read_focus[Read and format focus.md numbered list]
    subcmd -- "add <outcome>" --> append_focus[Append unchecked - [ ] outcome]
    subcmd -- "activate <n|slug>" --> flip_active[Mark active [>] and clear others]
    subcmd -- "done [n|slug]" --> mark_done[Mark [x] and move to done tail]
    subcmd -- "move <from> <to>" --> reorder[Reorder open focus list]
    append_focus --> update_store[Write focus.md]
    flip_active --> update_store
    mark_done --> update_store
    reorder --> update_store
    update_store --> finish([Done])
    read_focus --> finish
"""


def get_all_diagrams() -> Dict[str, str]:
    gates = load_gates_catalog()
    return {
        "resume.mmd": generate_resume_mmd(gates),
        "next-terminal.mmd": generate_next_terminal_mmd(gates),
        "oneshot.mmd": generate_oneshot_mmd(gates),
        "start.mmd": generate_start_mmd(gates),
        "spike.mmd": generate_spike_mmd(gates),
        "block.mmd": generate_block_mmd(gates),
        "drop.mmd": generate_drop_mmd(gates),
        "focus.mmd": generate_focus_mmd(gates),
    }


def write_diagrams() -> None:
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    diagrams = get_all_diagrams()
    for stale in _deprecated_resume_diagrams():
        path = DIAGRAMS_DIR / stale
        if path.exists():
            path.unlink()
            print(f"removed {path}")
    for filename, content in diagrams.items():
        out_path = DIAGRAMS_DIR / filename
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"wrote {out_path}")


def check_diagrams() -> bool:
    diagrams = get_all_diagrams()
    clean = True
    for filename, expected in diagrams.items():
        path = DIAGRAMS_DIR / filename
        if not path.exists():
            print(f"MISSING: {path} does not exist", file=sys.stderr)
            clean = False
            continue
        with open(path, "r", encoding="utf-8") as f:
            actual = f.read()
        if actual != expected:
            print(f"STALE: {path} differs from generated flow", file=sys.stderr)
            clean = False
    return clean


def check_catalog_schema() -> bool:
    if not GATES_FILE.exists():
        print(f"MISSING: {GATES_FILE} does not exist", file=sys.stderr)
        return False
    try:
        with open(GATES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"INVALID JSON: {GATES_FILE}: {e}", file=sys.stderr)
        return False

    if data.get("version") != 1:
        print("INVALID SCHEMA: gates.json version must be 1", file=sys.stderr)
        return False

    gates = data.get("gates", [])
    if not isinstance(gates, list) or len(gates) == 0:
        print("INVALID SCHEMA: gates.json must contain non-empty gates list", file=sys.stderr)
        return False

    seen_ids: Set[str] = set()
    clean = True
    for g in gates:
        gid = g.get("id")
        if not gid or not isinstance(gid, str):
            print(f"INVALID GATE: missing or non-string id in {g}", file=sys.stderr)
            clean = False
            continue
        if gid in seen_ids:
            print(f"DUPLICATE GATE ID: {gid!r}", file=sys.stderr)
            clean = False
        seen_ids.add(gid)

        kind = g.get("kind")
        if kind not in ("picker", "action", "guard"):
            print(f"INVALID KIND: {gid} has kind {kind!r}", file=sys.stderr)
            clean = False

        trig = g.get("trigger")
        if not isinstance(trig, dict) or not (trig.get("phase") or trig.get("overlay")):
            print(f"INVALID TRIGGER: {gid} trigger must have 'phase' or 'overlay'", file=sys.stderr)
            clean = False

        if kind in ("picker", "guard"):
            if not g.get("prompt"):
                print(f"MISSING PROMPT: {gid} requires prompt string", file=sys.stderr)
                clean = False
            options = g.get("options")
            if not isinstance(options, list) or len(options) < 2:
                print(f"INVALID OPTIONS: {gid} requires at least 2 options", file=sys.stderr)
                clean = False
            else:
                for idx, opt in enumerate(options, 1):
                    if opt.get("n") != idx or not opt.get("label"):
                        print(f"INVALID OPTION: {gid} option {idx} malformed: {opt}", file=sys.stderr)
                        clean = False

        if kind == "action":
            if not g.get("action"):
                print(f"MISSING ACTION: {gid} requires action field", file=sys.stderr)
                clean = False
            if "stop" not in g:
                print(f"MISSING STOP: {gid} requires stop boolean", file=sys.stderr)
                clean = False

    return clean


def check_presence_lint() -> bool:
    gates = load_gates_catalog()
    diagrams = get_all_diagrams()
    all_mmd = "\n".join(diagrams.values())
    clean = True

    for gid, g in gates.items():
        # Check that gate id or phase appears in diagrams
        phase = g.get("trigger", {}).get("phase")
        overlay = g.get("trigger", {}).get("overlay")
        if phase in EXTENSION_UNIT_PHASES:
            if "Flavor extension gate" in diagrams.get("resume.mmd", ""):
                continue
        if gid not in all_mmd and (not phase or phase not in all_mmd) and (not overlay or overlay not in all_mmd):
            print(f"PRESENCE LINT: Gate {gid!r} not referenced in any .mmd flow", file=sys.stderr)
            clean = False

    return clean


def check_scenario_parity() -> bool:
    if not SCENARIOS_MD.exists():
        return True
    try:
        from gen_evals import parse_scenarios
    except ImportError:
        sys.path.insert(0, str(EVALS_DIR))
        from gen_evals import parse_scenarios

    with open(SCENARIOS_MD, "r", encoding="utf-8") as f:
        text = f.read()

    evals = parse_scenarios(text)
    gates = load_gates_catalog()
    clean = True

    for ev in evals:
        fn = ev.get("flow_node")
        if fn and fn not in gates:
            print(f"SCENARIO PARITY: S{ev['id']} flow_node {fn!r} not found in gates.json", file=sys.stderr)
            clean = False

    return clean


def check_evals_clean() -> bool:
    if not SCENARIOS_MD.exists() or not EVALS_JSON.exists():
        return True
    try:
        from gen_evals import generate_evals_json
    except ImportError:
        sys.path.insert(0, str(EVALS_DIR))
        from gen_evals import generate_evals_json

    expected = generate_evals_json()
    with open(EVALS_JSON, "r", encoding="utf-8") as f:
        actual = f.read()
    if actual != expected:
        print(f"STALE EVALS: {EVALS_JSON} does not match pressure-scenarios.md", file=sys.stderr)
        return False
    return True


def check_extensions_parity() -> bool:
    if not EXTENSIONS_FILE.exists():
        print(f"MISSING: {EXTENSIONS_FILE} does not exist", file=sys.stderr)
        return False
    try:
        with open(EXTENSIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"INVALID JSON: {EXTENSIONS_FILE}: {e}", file=sys.stderr)
        return False
    gates = load_gates_catalog()
    gate_phases = {
        (g.get("trigger", {}).get("phase"),
         g.get("trigger", {}).get("kind", "unit"))
        for g in gates.values()
        if g.get("trigger", {}).get("phase")
    }
    clean = True
    for ext in data.get("extensions") or []:
        kind = ext.get("kind", "unit")
        for phase in ext.get("phases") or []:
            if (phase, kind) not in gate_phases:
                print(
                    f"EXTENSION PARITY: phase {phase!r} ({kind}) "
                    f"from {ext.get('id')!r} missing in gates.json",
                    file=sys.stderr,
                )
                clean = False
    return clean


SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"
WS_SPEC_FILE = SKILLS_DIR / "ws" / "SKILL.md"

SPEC_SECTION_REF_RE = re.compile(
    r"SPEC §(.+?)(?=\)|,|\.(?:\s|$)| — | \(|\s\(|;|:|$)"
)

_FORBIDDEN_VERB_PATTERNS = [
    (re.compile(r"\(SPEC\)"), "(SPEC)"),
    (re.compile(r"per SPEC(?! §)"), "per SPEC without §"),
    (re.compile(r"(?<!SPEC )§"), "bare §"),
    (re.compile(r"\bsee SPEC(?! §)"), "see SPEC"),
    (re.compile(r'SPEC "[^"]+"'), 'SPEC "section"'),
    (re.compile(r"\bSPEC (?!§)[A-Za-z]"), "SPEC without §"),
]


def _spec_section_prefixes() -> Set[str]:
    sections: Set[str] = set()
    with open(WS_SPEC_FILE, encoding="utf-8") as f:
        for line in f:
            if line.startswith("## "):
                title = line[3:].strip()
                prefix = re.split(r" [(—]", title, maxsplit=1)[0]
                sections.add(prefix)
    return sections


def _valid_section_ref(name: str, sections: Set[str]) -> bool:
    name = name.strip()
    if name in sections:
        return True
    return any(
        name.startswith(s + " ") or name.startswith(s + "(")
        for s in sections
    )


def _skill_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :]
    return text


def check_spec_refs() -> bool:
    sections = _spec_section_prefixes()
    clean = True

    spec_body = _skill_body(WS_SPEC_FILE)
    if "SPEC §" in spec_body:
        print(
            "SPEC REF: ws/SKILL.md body uses SPEC § (use § only)",
            file=sys.stderr,
        )
        clean = False

    for skill_dir in sorted(SKILLS_DIR.glob("ws-*/")):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        rel = skill_md.relative_to(SKILLS_DIR)
        body = _skill_body(skill_md)
        for pattern, label in _FORBIDDEN_VERB_PATTERNS:
            if pattern.search(body):
                print(
                    f"SPEC REF: {rel} forbidden pattern {label!r}",
                    file=sys.stderr,
                )
                clean = False
        for match in SPEC_SECTION_REF_RE.finditer(body):
            ref = match.group(1).strip()
            if not _valid_section_ref(ref, sections):
                print(
                    f"SPEC REF: {rel} unknown section SPEC §{ref!r}",
                    file=sys.stderr,
                )
                clean = False
    return clean


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="gen_flows.py")
    parser.add_argument("--check", action="store_true", help="Check contract: diagrams, schema, lint, parity, evals")
    args = parser.parse_args(argv)

    if args.check:
        ok_diag = check_diagrams()
        ok_schema = check_catalog_schema()
        ok_lint = check_presence_lint()
        ok_parity = check_scenario_parity()
        ok_extensions = check_extensions_parity()
        ok_evals = check_evals_clean()
        ok_spec_refs = check_spec_refs()

        if not (ok_diag and ok_schema and ok_lint and ok_parity
                and ok_extensions and ok_evals and ok_spec_refs):
            print("check-flows: FAILED — flow checks failed", file=sys.stderr)
            return 1
        print("check-flows: OK")
        return 0

    write_diagrams()
    return 0


if __name__ == "__main__":
    sys.exit(main())
