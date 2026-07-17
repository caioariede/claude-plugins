#!/usr/bin/env python3
"""Cross-runtime fast-path for the `/ws-board` command.

The logic here is runtime-agnostic; the only runtime-specific bit is the
block/inject JSON, chosen by `--format`. A thin wiring file per runtime
points its prompt-submit hook at this script:
  - Claude Code: hooks/hooks.json  → UserPromptSubmit → --format=claude
  - Cursor:      hooks/hooks-cursor.json → beforeSubmitPrompt → --format=cursor
Adding a runtime is a new wiring file plus a branch in `_payload`.

Everything else — natural-language triggering, unit detail, disambiguation,
next-step chaining — stays with the ws-board skill (itself runtime-agnostic).
Both paths call the same board.py: one engine, two front doors.

Contract: on a clean board render (board.py exit 0) block the prompt and
show the board — no model turn, no tokens. On anything else (not our
command, ambiguity, error, timeout) stay out of the way and let the prompt
through to the skill. This runs on every prompt, so every failure path must
fall through; it must never break submission.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

_CMD = re.compile(r'^\s*/(?:workstreams:)?ws-board\b(.*)$', re.DOTALL)
BOARD = (Path(__file__).resolve().parent.parent
         / "skills" / "ws-board" / "scripts" / "board.py")


def command_args(prompt: str):
    """The `/ws-board` argument list, or None if this isn't that command."""
    m = _CMD.match(prompt.strip())
    return m.group(1).split() if m else None


def _payload(fmt: str, block: bool, text: str = ""):
    """Runtime-specific hook output. block=False means 'let it through'."""
    if fmt == "cursor":
        return {"continue": False, "user_message": text} if block \
            else {"continue": True}
    # claude: block carries the output in reason; silence == proceed.
    return {"decision": "block", "reason": text} if block else None


def decide(prompt: str, fmt: str, run_board):
    """Pure decision → the payload dict to emit (or None to stay silent).
    run_board(args) -> (returncode, stdout)."""
    args = command_args(prompt)
    if args is None:
        return _payload(fmt, block=False)
    try:
        rc, out = run_board(args)
    except Exception:
        return _payload(fmt, block=False)
    if rc != 0 or not out.strip():
        return _payload(fmt, block=False)   # ambiguity / error → skill
    return _payload(fmt, block=True, text=out.rstrip())


def _run_board(args):
    r = subprocess.run([sys.executable, str(BOARD), *args],
                       capture_output=True, text=True, timeout=15)
    return r.returncode, r.stdout


def main():
    fmt = "claude"
    for a in sys.argv[1:]:
        if a.startswith("--format="):
            fmt = a.split("=", 1)[1]
    try:
        prompt = json.load(sys.stdin).get("prompt") or ""
    except Exception:
        prompt = ""
    payload = decide(prompt, fmt, _run_board)
    if payload is not None:
        print(json.dumps(payload))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never break prompt submission
    sys.exit(0)
