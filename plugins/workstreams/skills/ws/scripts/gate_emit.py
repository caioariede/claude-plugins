#!/usr/bin/env python3
"""Gate emitter for ws-* skills.

Renders structured gate blocks from references/flows/gates.json when
--emit-gate is passed to phase.py or other ws scripts.

Usage:
  gate_emit.py <phase> [--kind <kind>] [--overlay <overlay>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

GATES_PATH = Path(__file__).resolve().parents[1] / "references" / "flows" / "gates.json"


def load_catalog(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    target = path or GATES_PATH
    if not target.exists():
        return []
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("gates", [])
    except Exception:
        return []


def find_gate(phase: str, kind: str = "unit", overlay: Optional[str] = None,
              catalog: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    gates = catalog if catalog is not None else load_catalog()
    for g in gates:
        trig = g.get("trigger", {})
        if overlay and trig.get("overlay") == overlay and trig.get("kind", kind) == kind:
            return g
        if not overlay and trig.get("phase") == phase and trig.get("kind", kind) == kind:
            return g
    return None


def format_gate_block(gate: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
    lines = [f"--- GATE: {gate['id']} ---", f"kind: {gate.get('kind', 'picker')}"]
    
    if "prompt" in gate:
        lines.append(f"prompt: {gate['prompt']}")
    
    if context:
        lines.append("context:")
        for k, v in context.items():
            if isinstance(v, list):
                lines.append(f"  {k}:")
                for item in v:
                    lines.append(f"    - {item}")
            else:
                lines.append(f"  {k}: {v}")

    if "options" in gate:
        lines.append("options:")
        for opt in gate["options"]:
            lines.append(f"  {opt['n']}. {opt['label']}")

    if "action" in gate:
        lines.append(f"action: {gate['action']}")
    if "stop" in gate:
        lines.append(f"stop: {'true' if gate['stop'] else 'false'}")

    lines.append("--- END GATE ---")
    return "\n".join(lines)


def emit_gate(phase: str, kind: str = "unit", overlay: Optional[str] = None,
              context: Optional[Dict[str, Any]] = None,
              catalog: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    gate = find_gate(phase, kind=kind, overlay=overlay, catalog=catalog)
    if not gate:
        return None
    return format_gate_block(gate, context=context)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="gate_emit.py")
    parser.add_argument("phase", help="Phase name")
    parser.add_argument("--kind", default="unit", choices=["unit", "spike"], help="Target kind")
    parser.add_argument("--overlay", default=None, help="Overlay name (e.g. drift)")
    args = parser.parse_args(argv)

    block = emit_gate(args.phase, kind=args.kind, overlay=args.overlay)
    if block:
        print(block)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
