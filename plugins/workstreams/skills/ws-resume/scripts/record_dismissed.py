#!/usr/bin/env python3
"""ws-resume record_dismissed — ship-detect gate pick 1.

Usage: record_dismissed.py <unit-id> sha=<s>
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402

_SHA_RE = re.compile(r"\bsha=([0-9a-f]+)\b")


def _store() -> Path:
    env = os.environ.get("WS_STORE")
    return Path(env) if env else S.store_root()


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("usage: record_dismissed.py <unit-id> sha=<s>")
    store = _store()
    try:
        ws_id, slug = C.resolve_args(store, [argv[0]])
    except C.Pick as p:
        print(str(p), file=sys.stderr)
        return 2
    m = _SHA_RE.search(" ".join(argv[1:]))
    if not m:
        raise SystemExit("usage: record_dismissed.py <unit-id> sha=<s>")
    sha = m.group(1)
    wrote = S.append_ship_detect_dismissed(store / ws_id, slug, sha)
    print(f"dismissed sha={sha}" if wrote else f"already-dismissed sha={sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
