#!/usr/bin/env python3
"""ws-focus — read and write a workstream's focus.md queue.

Manual lifecycle: at most one `[>]` active line on every write. Parses
and renders via ws_store; resolves the workstream via ws_cli.

Usage:
  focus.py show [ws-id]
  focus.py add [ws-id] "<outcome>"
  focus.py activate [ws-id] <slug>
  focus.py done [ws-id] [slug]

Exit 2 when the caller must pick or correct the request.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ws" / "scripts"))
import ws_store as S   # noqa: E402
import ws_cli as C     # noqa: E402


class Fail(Exception):
    pass


def _store() -> Path:
    env = os.environ.get("WS_STORE")
    return Path(env) if env else S.store_root()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _focus_path(store: Path, ws_id: str) -> Path:
    return store / ws_id / "focus.md"


def _load(store: Path, ws_id: str) -> Tuple[Optional[S.FocusItem],
                                            List[S.FocusItem],
                                            List[S.FocusItem]]:
    return S.parse_focus(_read(_focus_path(store, ws_id)))


def _render(active: Optional[S.FocusItem],
            queued: List[S.FocusItem],
            done: List[S.FocusItem]) -> str:
    lines = ["## Focus"]
    for item in ([active] if active else []) + queued + done[-3:]:
        mark = {"active": ">", "queued": " ", "done": "x"}[item.state]
        lines.append(f"- [{mark}] {item.slug}  — {item.outcome}")
    return "\n".join(lines) + "\n"


def _write(store: Path, ws_id: str,
           active: Optional[S.FocusItem],
           queued: List[S.FocusItem],
           done: List[S.FocusItem]) -> None:
    path = _focus_path(store, ws_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render(active, queued, done), encoding="utf-8")


def cmd_show(store: Path, ws_id: str) -> str:
    active, queued, done = _load(store, ws_id)
    return _render(active, queued, done).rstrip("\n")


def cmd_add(store: Path, ws_id: str, outcome: str) -> str:
    slug = S.make_slug(outcome)
    active, queued, done = _load(store, ws_id)
    item = S.FocusItem(slug=slug, outcome=outcome.strip(), state="queued")
    if active is None:
        item.state = "active"
        active = item
    else:
        queued.append(item)
    _write(store, ws_id, active, queued, done)
    return slug


def cmd_activate(store: Path, ws_id: str, slug: str) -> None:
    active, queued, done = _load(store, ws_id)
    if active and active.slug == slug:
        return
    target: Optional[S.FocusItem] = None
    new_queued: List[S.FocusItem] = []
    for item in queued:
        if item.slug == slug:
            target = item
        else:
            new_queued.append(item)
    if target is None:
        raise Fail(f"NO_MATCH focus slug '{slug}' not in queue")
    if active:
        active.state = "queued"
        new_queued.insert(0, active)
    target.state = "active"
    _write(store, ws_id, target, new_queued, done)


def cmd_done(store: Path, ws_id: str, slug: Optional[str] = None) -> None:
    active, queued, done = _load(store, ws_id)
    if slug is None:
        if active is None:
            raise Fail("NO_ACTIVE no active focus to complete")
        slug = active.slug
    item: Optional[S.FocusItem] = None
    if active and active.slug == slug:
        item = active
        active = None
    else:
        kept: List[S.FocusItem] = []
        for q in queued:
            if q.slug == slug:
                item = q
            else:
                kept.append(q)
        queued = kept
    if item is None:
        raise Fail(f"NO_MATCH focus slug '{slug}' not open")
    item.state = "done"
    done.append(item)
    _write(store, ws_id, active, queued, done)


def _resolve_ws(store: Path, prefix: List[str]) -> str:
    ws_id, _unit = C.resolve_args(store, prefix)
    return ws_id


def _parse_ws_slug(store: Path, rest: List[str],
                   slug_optional: bool) -> Tuple[str, Optional[str]]:
    if len(rest) >= 2:
        return _resolve_ws(store, [rest[0]]), rest[1]
    if len(rest) == 1:
        if slug_optional and len(C.resolve_workstream(store, rest[0])) == 1:
            return C.resolve_workstream(store, rest[0])[0], None
        ws_id = _resolve_ws(store, [])
        return ws_id, rest[0]
    return _resolve_ws(store, []), None


def _parse_add(store: Path, rest: List[str]) -> Tuple[str, str]:
    if not rest:
        raise Fail("BAD_ARGS add requires an outcome")
    if len(rest) >= 2 and len(C.resolve_workstream(store, rest[0])) == 1:
        return C.resolve_workstream(store, rest[0])[0], " ".join(rest[1:])
    ws_id = _resolve_ws(store, rest[:1] if len(rest) == 1 else [])
    outcome = rest[0] if len(rest) == 1 else " ".join(rest[1:])
    return ws_id, outcome


def main(argv: List[str]) -> int:
    if not argv:
        print("BAD_ARGS missing verb", file=sys.stderr)
        return 2
    store = _store()
    verb, rest = argv[0], argv[1:]
    try:
        if verb == "show":
            ws_id = _resolve_ws(store, rest)
            print(cmd_show(store, ws_id))
            return 0
        if verb == "add":
            ws_id, outcome = _parse_add(store, rest)
            cmd_add(store, ws_id, outcome)
            return 0
        if verb == "activate":
            ws_id, slug = _parse_ws_slug(store, rest, slug_optional=False)
            if slug is None:
                raise Fail("BAD_ARGS activate requires a slug")
            cmd_activate(store, ws_id, slug)
            return 0
        if verb == "done":
            ws_id, slug = _parse_ws_slug(store, rest, slug_optional=True)
            cmd_done(store, ws_id, slug)
            return 0
        raise Fail(f"BAD_ARGS unknown verb {verb!r}")
    except C.Pick as p:
        print(str(p), file=sys.stderr)
        return 2
    except Fail as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
