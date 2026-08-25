#!/usr/bin/env python3
"""ws-focus — read and write a workstream's focus.md queue.

Manual lifecycle: at most one `[>]` active line on every write. Parses
and renders via ws_store; resolves the workstream via ws_cli.

Usage:
  focus.py list [ws-id]
  focus.py add [ws-id] "<outcome>"
  focus.py activate [ws-id] <n|slug>
  focus.py done [ws-id] [n|slug]
  focus.py move [ws-id] <from> <to>

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


def _focus_path(store: Path, ws_id: str) -> Path:
    return store / ws_id / "focus.md"


def _load(store: Path, ws_id: str) -> Tuple[List[S.FocusItem], List[S.FocusItem]]:
    return S.parse_focus(S._read(_focus_path(store, ws_id)))


def _open_slugs(open_items: List[S.FocusItem]) -> set:
    return {item.slug for item in open_items}


def _write(store: Path, ws_id: str,
           open_items: List[S.FocusItem],
           done: List[S.FocusItem]) -> None:
    path = _focus_path(store, ws_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(S.render_focus(open_items, done), encoding="utf-8")


def _resolve_open_target(open_items: List[S.FocusItem], arg: str) -> int:
    if arg.isdigit():
        n = int(arg)
        if n < 1 or n > len(open_items):
            raise Fail(f"OUT_OF_RANGE position {n} not in 1..{len(open_items)}")
        return n - 1
    for i, item in enumerate(open_items):
        if item.slug == arg:
            return i
    raise Fail(f"NO_MATCH focus target {arg!r} not in open list")


def cmd_list(store: Path, ws_id: str) -> str:
    open_items, done = _load(store, ws_id)
    lines = ["## Focus"]
    for i, item in enumerate(open_items, start=1):
        mark = ">" if item.state == "active" else " "
        lines.append(f"{i}. [{mark}] {S.focus_item_text(item)}")
    if done:
        lines.append("")
        lines.append("Done")
        lines.extend(f"- [x] {S.focus_item_text(item)}" for item in done)
    return "\n".join(lines)


def cmd_add(store: Path, ws_id: str, outcome: str) -> None:
    outcome = outcome.strip()
    if not outcome:
        raise Fail("BAD_ARGS add requires a non-empty outcome")
    slug = S.make_slug(outcome)
    open_items, done = _load(store, ws_id)
    if slug in _open_slugs(open_items):
        raise Fail(f"DUPLICATE_SLUG focus slug {slug!r} already open")
    open_items.append(S.FocusItem(slug=slug, outcome=outcome, state="queued"))
    _write(store, ws_id, open_items, done)


def cmd_activate(store: Path, ws_id: str, target: str) -> None:
    open_items, done = _load(store, ws_id)
    idx = _resolve_open_target(open_items, target)
    if open_items[idx].state == "active":
        return
    for item in open_items:
        if item.state == "active":
            item.state = "queued"
    open_items[idx].state = "active"
    _write(store, ws_id, open_items, done)


def cmd_done(store: Path, ws_id: str, target: Optional[str] = None) -> None:
    open_items, done = _load(store, ws_id)
    if target is None:
        active_idx = next((i for i, f in enumerate(open_items)
                           if f.state == "active"), None)
        if active_idx is None:
            raise Fail("NO_ACTIVE no active focus to complete")
        idx = active_idx
    else:
        idx = _resolve_open_target(open_items, target)
    item = open_items.pop(idx)
    item.state = "done"
    done.append(item)
    _write(store, ws_id, open_items, done)


def cmd_move(store: Path, ws_id: str, from_pos: int, to_pos: int) -> None:
    open_items, done = _load(store, ws_id)
    n = len(open_items)
    if from_pos < 1 or from_pos > n or to_pos < 1 or to_pos > n:
        raise Fail(f"OUT_OF_RANGE move {from_pos} {to_pos} not in 1..{n}")
    item = open_items.pop(from_pos - 1)
    open_items.insert(to_pos - 1, item)
    _write(store, ws_id, open_items, done)


def _resolve_ws(store: Path, prefix: List[str]) -> str:
    ws_id, _unit = C.resolve_args(store, prefix)
    return ws_id


def _parse_ws_target(store: Path, rest: List[str],
                     target_optional: bool) -> Tuple[str, Optional[str]]:
    if len(rest) >= 2:
        return _resolve_ws(store, [rest[0]]), rest[1]
    if len(rest) == 1:
        if target_optional:
            hits = C.resolve_workstream(store, rest[0])
            if len(hits) == 1:
                return hits[0], None
        ws_id = _resolve_ws(store, [])
        return ws_id, rest[0]
    return _resolve_ws(store, []), None


def _parse_add(store: Path, rest: List[str]) -> Tuple[str, str]:
    if not rest:
        raise Fail("BAD_ARGS add requires an outcome")
    if len(rest) >= 2:
        hits = C.resolve_workstream(store, rest[0])
        if len(hits) == 1:
            return hits[0], " ".join(rest[1:])
        return _resolve_ws(store, []), " ".join(rest)
    return _resolve_ws(store, []), rest[0]


def _parse_move(store: Path, rest: List[str]) -> Tuple[str, int, int]:
    if len(rest) < 2:
        raise Fail("BAD_ARGS move requires from and to positions")
    if len(rest) >= 3:
        try:
            from_pos = int(rest[1])
            to_pos = int(rest[2])
        except ValueError:
            raise Fail("BAD_ARGS move positions must be integers")
        return _resolve_ws(store, [rest[0]]), from_pos, to_pos
    try:
        from_pos = int(rest[0])
        to_pos = int(rest[1])
    except ValueError:
        raise Fail("BAD_ARGS move positions must be integers")
    return _resolve_ws(store, []), from_pos, to_pos


def main(argv: List[str]) -> int:
    if not argv:
        print("BAD_ARGS missing verb", file=sys.stderr)
        return 2
    store = _store()
    verb, rest = argv[0], argv[1:]
    try:
        if verb == "list":
            ws_id = _resolve_ws(store, rest)
            print(cmd_list(store, ws_id))
            return 0
        if verb == "add":
            ws_id, outcome = _parse_add(store, rest)
            cmd_add(store, ws_id, outcome)
            return 0
        if verb == "activate":
            ws_id, target = _parse_ws_target(store, rest, target_optional=False)
            if target is None:
                raise Fail("BAD_ARGS activate requires a number or slug")
            cmd_activate(store, ws_id, target)
            return 0
        if verb == "done":
            ws_id, target = _parse_ws_target(store, rest, target_optional=True)
            cmd_done(store, ws_id, target)
            return 0
        if verb == "move":
            ws_id, from_pos, to_pos = _parse_move(store, rest)
            cmd_move(store, ws_id, from_pos, to_pos)
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
