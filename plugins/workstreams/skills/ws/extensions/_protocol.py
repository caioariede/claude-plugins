#!/usr/bin/env python3
"""Shared stdin/stdout JSON helpers for ws extension handlers."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, Dict, List, Optional


def unit_log(ctx: Dict[str, Any]) -> List[List[str]]:
    return ctx.get("unit", {}).get("log") or []


def read_request() -> Dict[str, Any]:
    line = sys.stdin.readline()
    if not line:
        raise ValueError("empty request")
    return json.loads(line)


def write_response(phase: Optional[str]) -> None:
    sys.stdout.write(json.dumps({"phase": phase}) + "\n")
    sys.stdout.flush()


def run_pending(handler: Callable[[Dict[str, Any]], Optional[str]]) -> int:
    try:
        req = read_request()
        if req.get("op") != "pending":
            write_response(None)
            return 0
        write_response(handler(req.get("ctx") or {}))
        return 0
    except Exception:
        write_response(None)
        return 1
