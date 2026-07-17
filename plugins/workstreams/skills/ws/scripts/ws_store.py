"""Executable form of the `ws` SPEC: parse the store, derive status.

This module is the machine implementation of the contract prose in
`../SKILL.md`. It reads the durable store (never git/GitHub), so PR
state is passed in by the caller. Keep it pure and side-effect free
apart from reading files — that is what makes the board deterministic
and unit-testable against fixture stores.

Consumers: ws-board today; ws-next later. Both share the derivation
here so the rules live in one place, next to the SPEC.
"""

from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Store location
# ---------------------------------------------------------------------------

def store_root() -> Path:
    """`$XDG_DATA_HOME/workstreams`, else `~/.local/share/workstreams`."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "workstreams"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PR:
    number: Optional[int]
    state: str          # OPEN | MERGED | CLOSED
    is_draft: bool
    base: Optional[str]


@dataclass
class Need:
    nid: str            # N<n> for explicit needs, "base" for the implicit one
    target: str         # raw target text (slug / unit-id / F-id / WF-id)
    note: str = ""


@dataclass
class Followup:
    fid: str            # F<n> or WF<n>
    desc: str
    checked: bool
    origin: str = ""    # unit-id/ws-id that captured it (WF lines only)


@dataclass
class Unit:
    slug: str
    title: str = ""
    repo: str = ""
    branch: str = ""
    stacked_on: Optional[str] = None    # base unit, when base is a unit
    restart_of: Optional[str] = None
    tasks_total: int = 0
    tasks_done: int = 0
    followups: List[Followup] = field(default_factory=list)
    needs: List[Need] = field(default_factory=list)
    dropped: bool = False
    log: List[Tuple[str, str, str]] = field(default_factory=list)  # (ts,kind,payload)
    pr: Optional[PR] = None
    status: str = "building"            # derived

    @property
    def code_complete(self) -> bool:
        # SPEC: >=1 task and every task checked. Zero tasks is NOT
        # code-complete. merged implies code-complete.
        if self.pr and self.pr.state == "MERGED":
            return True
        return self.tasks_total > 0 and self.tasks_done == self.tasks_total


@dataclass
class PlannedUnit:
    slug: str
    base: str = ""
    needs: List[str] = field(default_factory=list)   # raw targets from needs=
    what: str = ""


@dataclass
class Workstream:
    ws_id: str
    name: str
    units: List[Unit] = field(default_factory=list)
    planned: List[PlannedUnit] = field(default_factory=list)
    wf_followups: List[Followup] = field(default_factory=list)  # backlog WF<n>


# ---------------------------------------------------------------------------
# Parsers — one per store file
# ---------------------------------------------------------------------------

_LEDGER_RE = re.compile(r'^-\s+(\S+)\s+(\S+)\s+"([^"]*)"\s*(.*)$')


def parse_units(text: str) -> List[Unit]:
    """Ledger lines: `- <ts> <slug> "<title>" key=value...`.

    Blank and non-matching lines are skipped, so the irregular blank
    lines real ledgers carry between entries are harmless.
    """
    units: List[Unit] = []
    for line in text.splitlines():
        m = _LEDGER_RE.match(line.strip())
        if not m:
            continue
        _ts, slug, title, rest = m.groups()
        u = Unit(slug=slug, title=title)
        for tok in rest.split():
            if "=" not in tok:
                continue
            k, v = tok.split("=", 1)
            if k == "repo":
                u.repo = v
            elif k == "branch":
                u.branch = v
            elif k == "restart-of":
                u.restart_of = v
            elif k == "stacked-on":
                u.stacked_on = v
        units.append(u)
    return units


def _section_of(line: str, headings: Dict[str, str]) -> Optional[str]:
    """Map a `## Heading` line to a section key, else None for non-headings.

    Returns "" for a `##` heading that is not one we parse, so the caller
    can drop into an ignore state (this is what excludes `## Not tracked
    here` and any other stray section).
    """
    if line.startswith("## "):
        return headings.get(line[3:].strip(), "")
    return None


_TASK_RE = re.compile(r'^-\s+\[( |x|X)\]')
_NEED_RE = re.compile(r'^-\s+(N\d+)\s+(.*)$')
_FU_RE = re.compile(r'^-\s+\[( |x|X)\]\s+(F\d+)\s+(.*)$')


def parse_progress(text: str) -> Tuple[int, int, List[Followup], List[Need]]:
    """(tasks_done, tasks_total, in-flight follow-ups, explicit needs).

    Sections may appear in any order; only their headings scope parsing.
    """
    headings = {"Tasks": "tasks", "Follow-ups": "followups", "Needs": "needs"}
    section: Optional[str] = None
    done = total = 0
    fus: List[Followup] = []
    needs: List[Need] = []
    for raw in text.splitlines():
        line = raw.strip()
        sec = _section_of(line, headings)
        if sec is not None:
            section = sec
            continue
        if section == "tasks":
            m = _TASK_RE.match(line)
            if m:
                total += 1
                if m.group(1) in ("x", "X"):
                    done += 1
        elif section == "followups":
            m = _FU_RE.match(line)
            if m:
                fus.append(Followup(fid=m.group(2),
                                    desc=m.group(3).strip(),
                                    checked=m.group(1) in ("x", "X")))
        elif section == "needs":
            m = _NEED_RE.match(line)
            if m:
                target, note = _split_dash(m.group(2))
                needs.append(Need(nid=m.group(1), target=target.strip(),
                                  note=note.strip()))
    return done, total, fus, needs


def _split_dash(text: str) -> Tuple[str, str]:
    """Split a line on the ` — ` (em dash) field separator; the note is
    whatever follows. A plain ` - ` (hyphen) is accepted as a fallback so
    hand-typed notes still parse."""
    for sep in (" — ", " – ", " -- ", " - "):
        if sep in text:
            head, tail = text.split(sep, 1)
            return head, tail
    return text, ""


_FROM_RE = re.compile(r'\(from\s+([^,]+),\s*([^)]*)\)')


def parse_backlog(text: str) -> Tuple[List[PlannedUnit], List[Followup]]:
    """Parse `## Planned units` and `## Follow-ups` only.

    Any other `## Section` drops parsing into ignore; comments, single-`#`
    sub-headers, and blank lines are never items. An item is a checkbox
    bullet under a parsed section.
    """
    headings = {"Planned units": "planned", "Follow-ups": "followups"}
    section: Optional[str] = None
    planned: List[PlannedUnit] = []
    wfs: List[Followup] = []
    for raw in text.splitlines():
        line = raw.strip()
        sec = _section_of(line, headings)
        if sec is not None:
            section = sec
            continue
        if line.startswith("<!--") or not line.startswith("- ["):
            continue
        m = re.match(r'^-\s+\[( |x|X)\]\s+(.*)$', line)
        if not m:
            continue
        checked = m.group(1) in ("x", "X")
        body = m.group(2)
        if section == "planned":
            planned.append(_parse_planned(body))
        elif section == "followups":
            wfs.append(_parse_wf(body, checked))
    return planned, wfs


def _parse_planned(body: str) -> PlannedUnit:
    """`<slug>  base=<b>  [needs=<t>,<t>]  — <what>`.

    Structured fields live before the ` — `; the tail is opaque display
    text. Anything after the dash never carries base=/needs=.
    """
    head, what = _split_dash(body)
    toks = head.split()
    slug = toks[0] if toks else ""
    base = ""
    needs: List[str] = []
    for tok in toks[1:]:
        if tok.startswith("base="):
            base = tok[len("base="):]
        elif tok.startswith("needs="):
            needs = [t for t in tok[len("needs="):].split(",") if t]
    return PlannedUnit(slug=slug, base=base, needs=needs, what=what.strip())


def _parse_wf(body: str, checked: bool) -> Followup:
    """`WF<n>  <desc>  (from <origin>, <ts>)`.

    Origin is located by the `(from ` marker, not the last paren — the
    description itself often contains parentheses. Text trailing the
    origin (e.g. `→ done in X`) is bookkeeping and left in desc.
    """
    toks = body.split(None, 1)
    fid = toks[0] if toks else ""
    rest = toks[1] if len(toks) > 1 else ""
    origin = ""
    m = _FROM_RE.search(rest)
    if m:
        origin = m.group(1).strip()
        rest = rest[:m.start()].strip()
    return Followup(fid=fid, desc=rest.strip(), checked=checked, origin=origin)


def parse_log(text: str) -> List[Tuple[str, str, str]]:
    """Log lines: `- <ts>  <kind>  <payload>` → (ts, kind, payload).

    kind is the token after the timestamp — so `dropped` as a real kind
    is distinct from the word appearing inside a `decision` payload.
    """
    out: List[Tuple[str, str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        parts = line[2:].split(None, 2)
        if not parts:
            continue
        ts = parts[0]
        kind = parts[1] if len(parts) > 1 else ""
        payload = parts[2] if len(parts) > 2 else ""
        out.append((ts, kind, payload))
    return out


# ---------------------------------------------------------------------------
# Loading a workstream from disk
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def load_workstream(ws_dir: Path) -> Workstream:
    """Load everything derivable from the store; PR state is attached
    later by the caller (it owns git/GitHub)."""
    ws_id = ws_dir.name
    name = ws_id
    wm = _read(ws_dir / "workstream.md")
    m = re.search(r'^name:\s*(.+)$', wm, re.MULTILINE)
    if m:
        name = m.group(1).strip()

    ws = Workstream(ws_id=ws_id, name=name)
    ws.units = parse_units(_read(ws_dir / "units.md"))
    ws.planned, ws.wf_followups = parse_backlog(_read(ws_dir / "backlog.md"))

    for u in ws.units:
        udir = ws_dir / "units" / u.slug
        u.tasks_done, u.tasks_total, u.followups, u.needs = parse_progress(
            _read(udir / "progress.md"))
        u.log = parse_log(_read(udir / "log.md"))
        u.dropped = any(kind == "dropped" for _ts, kind, _p in u.log)
    return ws


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------

def apply_pr_state(ws: Workstream, pr_by_branch: Dict[str, Optional[PR]]) -> None:
    for u in ws.units:
        u.pr = pr_by_branch.get(u.branch)


def _slug_of(target: str) -> str:
    """Reduce a unit target to its bare slug (drop a `<ws-id>:` prefix)."""
    return target.split(":")[-1] if ":" in target else target


def _is_followup_target(target: str) -> bool:
    return bool(re.match(r'^WF\d+$', target) or re.search(r':F\d+$', target)
                or re.match(r'^F\d+$', target))


def derive_status(ws: Workstream) -> None:
    """Fill each unit's derived status, first-match-wins per SPEC."""
    by_slug = {u.slug: u for u in ws.units}
    for u in ws.units:
        u.status = _status_for(u, ws, by_slug)


def _status_for(u: Unit, ws: Workstream, by_slug: Dict[str, Unit]) -> str:
    if u.dropped:
        return "dropped"
    if u.pr and u.pr.state == "MERGED":
        return "merged"
    if unit_needs(u, ws) and _has_unmet_need(u, ws, by_slug):
        return "blocked"
    if u.pr and u.pr.state == "OPEN" and not u.pr.is_draft:
        return "in-review"
    return "building"


def unit_needs(u: Unit, ws: Workstream) -> List[Need]:
    """Explicit needs plus the implicit base need when base is a unit."""
    needs = list(u.needs)
    if u.stacked_on:
        needs.insert(0, Need(nid="base", target=u.stacked_on,
                             note="base"))
    return needs


def need_state(target: str, ws: Workstream,
               by_slug: Dict[str, Unit]) -> Tuple[bool, str]:
    """Return (satisfied, note). note is "dropped" / "removed" / "".

    Unit target → satisfied at code-complete. Follow-up target →
    satisfied when its box is checked; a target that no longer exists is
    unresolvable (removed), not satisfied.
    """
    if _is_followup_target(target):
        fu = _find_followup(target, ws, by_slug)
        if fu is None:
            return False, "removed"
        return fu.checked, ""
    slug = _slug_of(target)
    dep = by_slug.get(slug)
    if dep is not None:
        if dep.dropped:
            return False, "dropped"
        return dep.code_complete, ""
    if any(p.slug == slug for p in ws.planned):
        return False, ""   # planned, not started yet — open, not removed
    return False, "removed"


def _find_followup(target: str, ws: Workstream,
                   by_slug: Dict[str, Unit]) -> Optional[Followup]:
    if re.match(r'^WF\d+$', target):
        for fu in ws.wf_followups:
            if fu.fid == target:
                return fu
        return None
    # <unit>:F<n> or bare F<n> — a bare F<n> has no owning unit context,
    # so it is only resolvable in the qualified form.
    m = re.match(r'^(.*):(F\d+)$', target)
    if not m:
        return None
    dep = by_slug.get(_slug_of(m.group(1)))
    if dep is None:
        return None
    for fu in dep.followups:
        if fu.fid == m.group(2):
            return fu
    return None


def _has_unmet_need(u: Unit, ws: Workstream,
                    by_slug: Dict[str, Unit]) -> bool:
    for n in unit_needs(u, ws):
        satisfied, _note = need_state(n.target, ws, by_slug)
        if not satisfied:
            return True
    return False


def planned_unmet_needs(p: PlannedUnit, ws: Workstream,
                        by_slug: Dict[str, Unit]) -> List[Tuple[str, str]]:
    """Unmet (target, note) for a planned unit: needs= plus base when base
    names a known unit. A planned unit whose base is a branch has no base
    need."""
    targets = list(p.needs)
    if p.base and _slug_of(p.base) in by_slug:
        targets.insert(0, p.base)
    unmet = []
    for t in targets:
        satisfied, note = need_state(t, ws, by_slug)
        if not satisfied:
            unmet.append((t, note))
    return unmet


# ---------------------------------------------------------------------------
# Board model — the four columns plus backlog / dropped / done-ness
# ---------------------------------------------------------------------------

@dataclass
class Board:
    name: str
    not_started: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    in_progress: List[str] = field(default_factory=list)
    done: List[str] = field(default_factory=list)
    backlog: List[str] = field(default_factory=list)   # rendered lines
    dropped: List[str] = field(default_factory=list)
    merged_count: int = 0
    total_count: int = 0
    complete: bool = False
    has_blocked: bool = False


def _pr_seg(u: Unit) -> str:
    return f" · #{u.pr.number}" if u.pr and u.pr.number else ""


def _gist(text: str, limit: int = 100) -> str:
    """First sentence, else a hard truncation. Mechanical by design —
    the full text lives in the source file; the board stays glanceable."""
    text = " ".join(text.split())
    m = re.search(r'(.+?[.!?])(\s|$)', text)
    if m and len(m.group(1)) <= limit + 20:
        return m.group(1)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def build_board(ws: Workstream) -> Board:
    derive_status(ws)
    by_slug = {u.slug: u for u in ws.units}
    b = Board(name=ws.name)

    ledger_slugs = set(by_slug)
    for u in ws.units:
        if u.status == "merged":
            b.done.append(f"{u.slug}{_pr_seg(u)}")
        elif u.status == "dropped":
            b.dropped.append(u.slug)
        elif u.status == "blocked":
            b.blocked.append(_blocked_cell(u, ws, by_slug))
        else:  # building | in-review
            b.in_progress.append(
                f"{u.slug}{_pr_seg(u)} · {u.tasks_done}/{u.tasks_total}")

    # Planned units with no ledger line yet: blocked vs not-started.
    for p in ws.planned:
        if p.slug in ledger_slugs:
            continue  # derived-done: a ledger unit now owns this slug
        unmet = planned_unmet_needs(p, ws, by_slug)
        if unmet:
            b.blocked.append(_planned_blocked_cell(p, unmet))
        else:
            b.not_started.append(p.slug)

    b.has_blocked = bool(b.blocked)

    # Header counts track the whole board: merged vs every board unit.
    planned_only = [p for p in ws.planned if p.slug not in ledger_slugs]
    b.merged_count = len(b.done)
    b.total_count = len([u for u in ws.units if u.status != "dropped"]) \
        + len(planned_only)

    # Backlog: open in-flight F<n> + open workstream WF<n>.
    for u in ws.units:
        if u.status in ("merged", "dropped"):
            continue
        for fu in u.followups:
            if not fu.checked:
                b.backlog.append(
                    f"- {fu.fid} {_gist(fu.desc)} (follow-up from {u.slug})")
    for fu in ws.wf_followups:
        if not fu.checked:
            origin = fu.origin or ws.ws_id
            b.backlog.append(
                f"- {fu.fid} {_gist(fu.desc)} (follow-up from {origin})")

    b.complete = workstream_done(ws, by_slug)
    return b


def _blocked_cell(u: Unit, ws: Workstream,
                  by_slug: Dict[str, Unit]) -> str:
    parts = []
    for n in unit_needs(u, ws):
        satisfied, note = need_state(n.target, ws, by_slug)
        if satisfied:
            continue
        label = _slug_of(n.target)
        if note:
            label += f" ({note})"
        parts.append(label)
    cell = f"{u.slug} · needs {', '.join(parts)}"
    return cell + _pr_seg(u)


def _planned_blocked_cell(p: PlannedUnit,
                          unmet: List[Tuple[str, str]]) -> str:
    parts = []
    for target, note in unmet:
        label = _slug_of(target)
        if note:
            label += f" ({note})"
        parts.append(label)
    return f"{p.slug} · needs {', '.join(parts)}"


def workstream_done(ws: Workstream, by_slug: Dict[str, Unit]) -> bool:
    """SPEC "Workstream done": no active unit and no open backlog work."""
    active = {"building", "blocked", "in-review"}
    if any(u.status in active for u in ws.units):
        return False
    ledger_slugs = set(by_slug)
    if any(p.slug not in ledger_slugs for p in ws.planned):
        return False
    if any(not fu.checked for fu in ws.wf_followups):
        return False
    for u in ws.units:
        if any(not fu.checked for fu in u.followups):
            return False
    return True


# ---------------------------------------------------------------------------
# Decision engine — ws-next router (SPEC decision table, first match wins)
# ---------------------------------------------------------------------------

DEFAULT_BRANCHES = {"master", "main", "trunk", "develop", "dev"}


def recorded_base(u: Unit) -> Optional[str]:
    """The base on the unit's last created/restack log line — the SPEC's
    'recorded base', never the live PR baseRefName."""
    base = None
    for _ts, kind, payload in u.log:
        if kind in ("created", "restack"):
            m = re.search(r'base=(\S+)', payload)
            if m:
                base = m.group(1)
    return base


def unmet_needs(u: Unit, ws: Workstream,
                by_slug: Dict[str, Unit]) -> List[Tuple[str, str]]:
    """(target, note) for each of the unit's needs that isn't satisfied."""
    out = []
    for n in unit_needs(u, ws):
        satisfied, note = need_state(n.target, ws, by_slug)
        if not satisfied:
            out.append((n.target, note))
    return out


def _drifted(u: Unit) -> bool:
    """PR base moved off the recorded base (GitHub retargeted, or the base
    merged) with no restack reconciling it yet."""
    if not (u.pr and u.pr.base):
        return False
    rb = recorded_base(u)
    return rb is not None and u.pr.base != rb


def _dependents(u: Unit, ws: Workstream, by_slug: Dict[str, Unit]) -> int:
    """How many other units are blocked with an unmet need on `u` — i.e.
    finishing `u` would unblock them. Ranks in-flight work by critical
    path: a unit that unblocks others beats one that unblocks nothing."""
    n = 0
    for v in ws.units:
        if v.slug == u.slug:
            continue
        if any(_slug_of(t) == u.slug for t, _note in unmet_needs(v, ws, by_slug)):
            n += 1
    return n


@dataclass
class Decision:
    rule: str                       # restack|ship|resume|start|triage-*|done
    command: Optional[str] = None   # resolved ws-* command; None for triage/done
    unit: Optional[str] = None      # unit slug when the command is unit-scoped
    also: List[str] = field(default_factory=list)      # parallel-startable
    blocked: List[str] = field(default_factory=list)   # "<unit> — needs ..."
    open_items: List[str] = field(default_factory=list)
    headline: str = ""


def _startable_planned(ws: Workstream,
                       by_slug: Dict[str, Unit]) -> List[PlannedUnit]:
    ledger = set(by_slug)
    return [p for p in ws.planned
            if p.slug not in ledger
            and not planned_unmet_needs(p, ws, by_slug)]


def decide_next(ws: Workstream) -> Decision:
    """The single best next action, first-match-wins per the SPEC table.
    Blocked units are never resumed — the router advances their blocker."""
    derive_status(ws)
    by_slug = {u.slug: u for u in ws.units}

    blocked_lines = []
    for u in ws.units:
        if u.status != "blocked":
            continue
        labels = []
        for target, note in unmet_needs(u, ws, by_slug):
            lab = _slug_of(target)
            if note:
                lab += f" ({note})"
            labels.append(lab)
        blocked_lines.append(f"{u.slug} — needs {', '.join(labels)}")

    def out(rule, command=None, unit=None, also=None, open_items=None,
            headline=""):
        return Decision(rule=rule, command=command, unit=unit, also=also or [],
                        blocked=blocked_lines, open_items=open_items or [],
                        headline=headline)

    # 1 — branch drifted off its recorded base (retarget / base merged).
    for u in ws.units:
        if u.status not in ("merged", "dropped") and _drifted(u):
            return out("restack", f"ws-restack {u.slug}", u.slug,
                       headline="base moved; rebase before proceeding")

    # In-flight units, critical path first: one that unblocks others beats
    # one that unblocks nothing (stable, so ledger order breaks ties).
    ordered = sorted(
        [u for u in ws.units if u.status in ("building", "in-review")],
        key=lambda u: -_dependents(u, ws, by_slug))

    # 2 — tasks all checked but no PR: ship it (ws-resume opens the PR).
    for u in ordered:
        if u.code_complete and not u.pr:
            return out("ship", f"ws-resume {u.slug}", u.slug,
                       headline="tasks done, no PR — ship it")

    # 3 — in progress (building/in-review, not blocked): advance it.
    if ordered:
        u = ordered[0]
        return out("resume", f"ws-resume {u.slug}", u.slug,
                   headline="advance the in-flight unit")

    # 4 — a startable planned unit (needs satisfied, no ledger line yet).
    startable = _startable_planned(ws, by_slug)
    if startable:
        p = startable[0]
        cmd = f'ws-start {ws.ws_id} "{p.what or p.slug}"'
        if p.base and p.base not in DEFAULT_BRANCHES:
            cmd += f" --base {p.base}"
        return out("start", cmd, p.slug,
                   also=[q.slug for q in startable[1:]],
                   headline="start the next planned unit")

    # triage — a unit blocked ONLY by dropped/removed targets can't clear on
    # its own; route to ws-block ahead of backlog triage (it stays active).
    for u in ws.units:
        if u.status != "blocked":
            continue
        unmet = unmet_needs(u, ws, by_slug)
        if unmet and all(note in ("dropped", "removed") for _t, note in unmet):
            nids = [n.nid for n in unit_needs(u, ws)
                    if n.nid != "base"
                    and need_state(n.target, ws, by_slug)[1]
                    in ("dropped", "removed")]
            cmd = (f"ws-block {u.slug} clear {nids[0]}" if nids
                   else f"ws-restack {u.slug}")
            return out("triage-dropped", cmd, u.slug,
                       headline="blocker dropped/removed — re-point or clear")

    # 5 — no runnable step, but open backlog / blocked units remain: triage.
    open_items = []
    ledger = set(by_slug)
    for p in ws.planned:
        if p.slug not in ledger:
            open_items.append(f"planned: {p.slug} — {_gist(p.what)}")
    for u in ws.units:
        for fu in u.followups:
            if not fu.checked:
                open_items.append(f"{u.slug}:{fu.fid} — {_gist(fu.desc)}")
    for fu in ws.wf_followups:
        if not fu.checked:
            open_items.append(f"{fu.fid} — {_gist(fu.desc)}")
    if blocked_lines or open_items:
        head = ("no active unit; open backlog remains — triage"
                if open_items and not blocked_lines
                else "no runnable step — advance a blocker or triage backlog")
        return out("triage-backlog", None, None, open_items=open_items,
                   headline=head)

    # 6 — nothing active, nothing open.
    return out("done", None, None, headline="workstream done — close it")
