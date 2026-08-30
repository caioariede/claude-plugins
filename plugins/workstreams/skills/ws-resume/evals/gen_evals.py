#!/usr/bin/env python3
"""Generate evals.json from pressure-scenarios.md.

pressure-scenarios.md is the single authoritative source for ws-resume
eval definitions. This script parses scenario sections and generates
machine-readable evals.json.

Usage:
  gen_evals.py          # Regenerate evals.json
  gen_evals.py --check  # Verify evals.json is up-to-date
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

EVALS_DIR = Path(__file__).resolve().parent
SCENARIOS_MD = EVALS_DIR / "pressure-scenarios.md"
EVALS_JSON = EVALS_DIR / "evals.json"


def parse_scenarios(text: str) -> List[Dict[str, Any]]:
    # Matches ## S<num>: <title>
    # followed by optional <!-- eval ... --> block
    # Context: ...
    # Pressure: ...
    # Expected WITH skill: ...
    sections = re.split(r'\n(?=## S\d+:)', text)
    evals: List[Dict[str, Any]] = []

    for sec in sections:
        header_match = re.search(r'## S(\d+):\s*(.+)', sec)
        if not header_match:
            continue
        num = int(header_match.group(1))
        title = header_match.group(2).strip()

        # Extract metadata from comment if present
        meta_match = re.search(r'<!--\s*eval\s*\n(.*?)\s*-->', sec, re.DOTALL)
        meta: Dict[str, Any] = {}
        if meta_match:
            for line in meta_match.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if v == "null":
                        meta[k] = None
                    elif v.isdigit():
                        meta[k] = int(v)
                    else:
                        meta[k] = v

        name = meta.get("name") or re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        flow_node = meta.get("flow_node")
        gate_pick = meta.get("gate_pick")

        context_match = re.search(r'Context:\s*(.*?)(?=\n(?:Pressure:|Expected|$))', sec, re.DOTALL)
        pressure_match = re.search(r'Pressure:\s*(.*?)(?=\n(?:Context:|Expected|$))', sec, re.DOTALL)
        expected_match = re.search(r'Expected WITH skill:\s*(.*?)(?=\n(?:##|Context:|Pressure:|\Z))', sec, re.DOTALL)

        context = context_match.group(1).strip() if context_match else ""
        pressure = pressure_match.group(1).strip() if pressure_match else ""
        expected = expected_match.group(1).strip() if expected_match else ""

        # Collapse multi-line whitespace in prompts/expectations
        context_clean = " ".join(context.split())
        pressure_clean = " ".join(pressure.split())
        prompt = f"{context_clean}; {pressure_clean}".strip("; ")
        expected_clean = " ".join(expected.split())

        eval_item: Dict[str, Any] = {
            "id": num,
            "name": name,
            "prompt": prompt,
            "expected_output": expected_clean,
        }
        if flow_node is not None:
            eval_item["flow_node"] = flow_node
        if gate_pick is not None:
            eval_item["gate_pick"] = gate_pick

        evals.append(eval_item)

    evals.sort(key=lambda x: x["id"])
    return evals


def generate_evals_json() -> str:
    with open(SCENARIOS_MD, "r", encoding="utf-8") as f:
        content = f.read()
    evals = parse_scenarios(content)
    data = {
        "skill_name": "ws-resume",
        "evals": evals,
    }
    return json.dumps(data, indent=2) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="gen_evals.py")
    parser.add_argument("--check", action="store_true", help="Check that evals.json matches pressure-scenarios.md")
    args = parser.parse_args(argv)

    generated = generate_evals_json()
    if args.check:
        if not EVALS_JSON.exists():
            print(f"MISSING: {EVALS_JSON} does not exist", file=sys.stderr)
            return 1
        with open(EVALS_JSON, "r", encoding="utf-8") as f:
            current = f.read()
        if current != generated:
            print(f"STALE: {EVALS_JSON} does not match pressure-scenarios.md", file=sys.stderr)
            return 1
        print("check-evals: OK")
        return 0

    with open(EVALS_JSON, "w", encoding="utf-8") as f:
        f.write(generated)
    print(f"wrote {EVALS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
