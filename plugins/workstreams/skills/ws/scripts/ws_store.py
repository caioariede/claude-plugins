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
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Store location
# ---------------------------------------------------------------------------

def store_root() -> Path:
    """`$XDG_DATA_HOME/workstreams`, else `~/.local/share/workstreams`."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "workstreams"


def resolve_plan_path(design: str, slug: str) -> Path:
    """Unit plan path: ``<design-dir>/<bare-slug>-plan.md``."""
    d = design.strip()
    if not d or d in ("—", "-"):
        raise ValueError("design path is empty")
    s = slug.strip()
    if not s:
        raise ValueError("slug is empty")
    return Path(d).expanduser().parent / f"{s}-plan.md"


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
class MergedVia:
    branch: str
    sha: str
    pr: Optional[int] = None


_MERGED_VIA_RE = re.compile(
    r'branch=(\S+)\s+sha=(\S+)(?:\s+pr=(\d+))?')


def parse_merged_via_payload(text: str) -> Optional[MergedVia]:
    m = _MERGED_VIA_RE.search(text)
    if not m:
        return None
    pr = int(m.group(3)) if m.group(3) else None
    return MergedVia(branch=m.group(1), sha=m.group(2), pr=pr)


def format_merged_via_payload(rec: MergedVia) -> str:
    payload = f"branch={rec.branch} sha={rec.sha}"
    if rec.pr is not None:
        payload += f" pr={rec.pr}"
    return payload


def merged_via_record(u: Unit) -> Optional[MergedVia]:
    for _ts, kind, payload in reversed(u.log):
        if kind != "merged-via":
            continue
        rec = parse_merged_via_payload(payload)
        if rec is not None:
            return rec
    return None


def effective_merged_via(u: Unit) -> Optional[MergedVia]:
    """Honor merged-via only when the unit had shippable work."""
    rec = merged_via_record(u)
    if rec is None:
        return None
    if u.tasks_total <= 0 and not (
            u.pr is not None and u.pr.state == "MERGED"):
        return None
    return rec


def is_merged(u: Unit) -> bool:
    if effective_merged_via(u) is not None:
        return True
    return u.pr is not None and u.pr.state == "MERGED"


@dataclass
class MergeDetectInput:
    tip_sha: str
    default_tip_sha: str
    ledger_pr_state: Optional[str]
    tasks_total: int
    had_ledger_pr: bool
    tier_a_match: Optional[MergedVia] = None
    is_ancestor: bool = False
    default_branch: str = ""


@dataclass
class MergeDetectResult:
    outcome: str
    record: Optional[MergedVia] = None


def decide_merged_via(inp: MergeDetectInput) -> MergeDetectResult:
    if inp.ledger_pr_state == "MERGED":
        return MergeDetectResult("already-merged")
    if inp.tip_sha == inp.default_tip_sha:
        return MergeDetectResult("not-shipped")
    if inp.tasks_total <= 0 and not inp.had_ledger_pr:
        return MergeDetectResult("not-shipped")
    if inp.tier_a_match is not None:
        return MergeDetectResult("tier-a", inp.tier_a_match)
    if not inp.is_ancestor:
        return MergeDetectResult("not-shipped")
    branch = inp.default_branch or "default"
    return MergeDetectResult(
        "tier-b",
        MergedVia(branch=branch, sha=inp.tip_sha),
    )


def append_merged_via(ws_dir: Path, slug: str, rec: MergedVia) -> bool:
    """Append merged-via when absent for this sha; return True if written."""
    prior = merged_via_record(_unit_from_log(ws_dir, slug))
    if prior and prior.sha == rec.sha:
        return False
    log_path = ws_dir / "units" / slug / "log.md"
    _append_log_line(log_path, "merged-via", format_merged_via_payload(rec))
    return True


def _unit_from_log(ws_dir: Path, slug: str) -> Unit:
    log_path = ws_dir / "units" / slug / "log.md"
    return Unit(slug=slug, log=parse_log(_read(log_path)))


def ship_detect_dismissed_sha(u: Unit) -> Optional[str]:
    for _ts, kind, payload in reversed(u.log):
        if kind != "ship-detect-dismissed":
            continue
        m = re.search(r"\bsha=([0-9a-f]+)\b", payload)
        if m:
            return m.group(1)
    return None


def append_ship_detect_dismissed(ws_dir: Path, slug: str, sha: str) -> bool:
    if ship_detect_dismissed_sha(_unit_from_log(ws_dir, slug)) == sha:
        return False
    log_path = ws_dir / "units" / slug / "log.md"
    _append_log_line(log_path, "ship-detect-dismissed", f"sha={sha}")
    return True


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
    claims: List[str] = field(default_factory=list)  # follow-up targets
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
        if is_merged(self):
            return True
        return self.tasks_total > 0 and self.tasks_done == self.tasks_total


@dataclass
class Spike:
    slug: str
    title: str = ""
    repo: str = ""
    spawned_from: Optional[str] = None
    restart_of: Optional[str] = None
    tasks_total: int = 0
    tasks_done: int = 0
    needs: List[Need] = field(default_factory=list)
    dropped: bool = False
    log: List[Tuple[str, str, str]] = field(default_factory=list)
    status: str = "researching"         # derived

    @property
    def spike_complete(self) -> bool:
        return self.tasks_total > 0 and self.tasks_done == self.tasks_total


@dataclass
class PlannedUnit:
    slug: str
    base: str = ""
    needs: List[str] = field(default_factory=list)   # raw targets from needs=
    what: str = ""


@dataclass
class FocusItem:
    slug: str
    outcome: str
    state: str  # queued | active | done


@dataclass
class Workstream:
    ws_id: str
    name: str
    design: str = ""                    # workstream.md design: path, verbatim
    units: List[Unit] = field(default_factory=list)
    spikes: List[Spike] = field(default_factory=list)
    planned: List[PlannedUnit] = field(default_factory=list)
    wf_followups: List[Followup] = field(default_factory=list)  # backlog WF<n>
    active_focus: Optional[FocusItem] = None
    focus_queued: List[FocusItem] = field(default_factory=list)


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
            elif k == "claims":
                u.claims = [t for t in v.split(",") if t]
        units.append(u)
    return units


def parse_spikes(text: str) -> List[Spike]:
    """Ledger lines: `- <ts> <slug> "<title>" key=value...`."""
    spikes: List[Spike] = []
    for line in text.splitlines():
        m = _LEDGER_RE.match(line.strip())
        if not m:
            continue
        _ts, slug, title, rest = m.groups()
        sp = Spike(slug=slug, title=title)
        for tok in rest.split():
            if "=" not in tok:
                continue
            k, v = tok.split("=", 1)
            if k == "repo":
                sp.repo = v
            elif k == "spawned-from":
                sp.spawned_from = v
            elif k == "restart-of":
                sp.restart_of = v
        spikes.append(sp)
    return spikes


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


def parse_progress(text: str, *,
                   include_followups: bool = True
                   ) -> Tuple[int, int, List[Followup], List[Need]]:
    """(tasks_done, tasks_total, in-flight follow-ups, explicit needs).

    Sections may appear in any order; only their headings scope parsing.
    """
    headings: Dict[str, str] = {"Tasks": "tasks", "Needs": "needs"}
    if include_followups:
        headings["Follow-ups"] = "followups"
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


_TASK_LINE_RE = re.compile(
    r'^(-\s+\[)( |x|X)(\]\s+(T\d+)\s+(.*))$')

_PLAN_TASK_HEADING_RE = re.compile(r'^### Task (\d+):\s*(.*)$', re.MULTILINE)


class PlanParseError(ValueError):
    """Plan file lacks usable ``### Task N:`` headings."""


def derive_tasks_from_plan(text: str) -> List[Tuple[int, str]]:
    """One ``(n, title)`` per ``### Task N:`` heading, sorted by *n*."""
    tasks: List[Tuple[int, str]] = []
    seen: set[int] = set()
    for m in _PLAN_TASK_HEADING_RE.finditer(text):
        n = int(m.group(1))
        title = m.group(2).strip()
        if n in seen:
            raise PlanParseError(f"duplicate task number T{n}")
        seen.add(n)
        tasks.append((n, title))
    if not tasks:
        raise PlanParseError("no ### Task N: headings in plan")
    tasks.sort(key=lambda x: x[0])
    return tasks


def write_tasks_to_progress(raw: str, tasks: List[Tuple[int, str]], *,
                            checked: bool) -> Tuple[str, bool]:
    """Rebuild ``## Tasks``; preserve follow-ups and needs.

    Returns ``(new_text, wrote)``. ``wrote`` is false when ``## Tasks``
    already carries task lines.
    """
    headings = {"Tasks": "tasks", "Follow-ups": "followups",
                "Needs": "needs"}
    sections: Dict[str, List[str]] = {
        "tasks": [], "followups": [], "needs": []}
    section: Optional[str] = None
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        sec = _section_of(line, headings)
        if sec is not None:
            section = sec if sec else None
            continue
        if section and line.startswith("- "):
            sections[section].append(raw_line)
    if sections["tasks"]:
        return raw, False
    mark = "x" if checked else " "
    task_lines = [f"- [{mark}] T{n}  {title}" for n, title in tasks]
    fu = sections["followups"]
    need = sections["needs"]
    out: List[str] = ["## Tasks"] + task_lines
    out.append("")
    out.append("## Follow-ups")
    out.extend(fu)
    out.append("")
    out.append("## Needs")
    out.extend(need)
    if raw.endswith("\n"):
        out.append("")
    return "\n".join(out), True


def plan_log_path(u: Unit) -> Optional[str]:
    for _ts, kind, payload in u.log:
        if kind == "plan":
            return payload.strip()
    return None


def latest_plan_log_path(u: Unit) -> Optional[str]:
    path: Optional[str] = None
    for _ts, kind, payload in u.log:
        if kind == "plan":
            path = payload.strip()
    return path


def store_split_eligible(u: Unit) -> bool:
    """Store can lag git when a plan exists but the unit is not complete."""
    return (not u.dropped and not u.code_complete and _has_plan_line(u))


def reconcile_tasks_on_merge(text: str) -> Tuple[str, List[str]]:
    """Check open ## Tasks boxes; leave follow-ups/needs untouched."""
    headings = {"Tasks": "tasks", "Follow-ups": "followups",
                "Needs": "needs"}
    section: Optional[str] = None
    reconciled: List[str] = []
    out: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        sec = _section_of(line, headings)
        if sec is not None:
            section = sec
            out.append(raw)
            continue
        if section == "tasks":
            m = _TASK_LINE_RE.match(line)
            if m and m.group(2) == " ":
                reconciled.append(m.group(4))
                out.append(f"{m.group(1)}x{m.group(3)}")
                continue
        out.append(raw)
    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + suffix, reconciled


def _append_log_line(log_path: Path, kind: str, payload: str) -> None:
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"- {ts}  {kind}  {payload}\n"
    if log_path.exists():
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)
    else:
        log_path.write_text(f"# log\n{line}", encoding="utf-8")


def _reconcile_source_label(pr: Optional[PR],
                            merged_via: Optional[MergedVia]) -> str:
    if merged_via is not None:
        return f"merged-via {format_merged_via_payload(merged_via)}"
    if pr and pr.number is not None:
        return f"merged PR #{pr.number}"
    return "merged"


def maybe_reconcile_merged_unit(ws_dir: Path, slug: str,
                                pr: Optional[PR], *,
                                merged_via: Optional[MergedVia] = None
                                ) -> List[str]:
    """Check open task boxes when terminal-merged; return reconciled ids."""
    udir = ws_dir / "units" / slug
    log_path = udir / "log.md"
    if merged_via is None:
        u = Unit(slug=slug, log=parse_log(_read(log_path)))
        merged_via = merged_via_record(u)
    if merged_via is None and not (pr and pr.state == "MERGED"):
        return []
    prog_path = udir / "progress.md"
    raw = _read(prog_path)
    new_text, ids = reconcile_tasks_on_merge(raw)
    if not ids:
        return []
    prog_path.write_text(new_text, encoding="utf-8")
    _append_log_line(
        log_path, "decision",
        f"reconciled tasks from {_reconcile_source_label(pr, merged_via)}: "
        f"{', '.join(ids)}")
    return ids


def _append_log_lines(log_path: Path,
                      entries: List[Tuple[str, str]]) -> None:
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    block = "".join(f"- {ts}  {kind}  {payload}\n"
                    for kind, payload in entries)
    if log_path.exists():
        log_path.write_text(
            log_path.read_text(encoding="utf-8") + block, encoding="utf-8")
    else:
        log_path.write_text(f"# log\n{block}", encoding="utf-8")


def apply_external_backfill(ws_dir: Path, slug: str, plan_path: Path,
                            pr: PR, *, head_sha: str = "") -> Tuple[str, List[str]]:
    """Confirm-only backfill: checked tasks + execute-mode=external."""
    return _apply_external_tasks(
        ws_dir, slug, plan_path, checked=True, pr=pr, head_sha=head_sha)


def apply_external_execute_mode(ws_dir: Path, slug: str,
                                plan_path: Path) -> Tuple[str, List[str]]:
    """Plan-pause option 4: unchecked tasks + execute-mode=external."""
    return _apply_external_tasks(ws_dir, slug, plan_path, checked=False)


def _apply_external_tasks(ws_dir: Path, slug: str, plan_path: Path, *,
                          checked: bool,
                          pr: Optional[PR] = None,
                          head_sha: str = "") -> Tuple[str, List[str]]:
    udir = ws_dir / "units" / slug
    prog_path = udir / "progress.md"
    log_path = udir / "log.md"
    raw = _read(prog_path)
    _, total, _, _ = parse_progress(raw)
    if total > 0:
        return "already-has-tasks", []
    try:
        plan_text = plan_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "refused no-plan", []
    try:
        tasks = derive_tasks_from_plan(plan_text)
    except PlanParseError:
        return "refused bad-plan", []
    new_text, wrote = write_tasks_to_progress(raw, tasks, checked=checked)
    if not wrote:
        return "already-has-tasks", []
    prog_path.write_text(new_text, encoding="utf-8")
    ids = [f"T{n}" for n, _ in tasks]
    log_entries: List[Tuple[str, str]] = [
        ("decision", "execute-mode=external")]
    if checked and pr is not None:
        sha_bit = f", sha={head_sha[:7]}" if head_sha else ""
        pr_n = pr.number if pr.number is not None else "?"
        log_entries.append((
            "decision",
            "reconciled tasks from external implement "
            f"(PR #{pr_n}{sha_bit}): {', '.join(ids)}"))
    _append_log_lines(log_path, log_entries)
    status = "backfilled" if checked else "prepared"
    return status, ids


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


_SLUG_FILLER = {
    "a", "an", "and", "the", "this", "that", "so", "it", "its", "of", "to",
    "for", "from", "in", "into", "on", "with", "when", "then", "just",
    "at", "as", "by", "but", "or",
    "i", "we", "you", "my", "our", "your",
    "be", "is", "are", "was", "were", "can", "will", "would", "should",
}
_SLUG_MAX_WORDS = 4
_SLUG_MAX_CHARS = 32


def make_slug(text: str) -> str:
    """SPEC §IDs slug: sanitize, drop filler, cap words then chars."""
    words = [w for w in re.split(r'[^a-z0-9]+', text.lower()) if w]
    if not words:
        return "focus"

    # Filler only shortens; it never empties the slug
    kept = [w for w in words if w not in _SLUG_FILLER] or words
    s = "-".join(kept[:_SLUG_MAX_WORDS])

    # Cap at a word boundary, never mid-word
    if len(s) > _SLUG_MAX_CHARS:
        s = s[:_SLUG_MAX_CHARS].rsplit('-', 1)[0]
    return s.strip('-') or kept[0][:_SLUG_MAX_CHARS]


_FOCUS_STATE = {" ": "queued", ">": "active", "x": "done", "X": "done"}
_FOCUS_MARK = {"active": ">", "queued": " ", "done": "x"}


def parse_focus(text: str) -> Tuple[List[FocusItem], List[FocusItem]]:
    headings = {"Focus": "focus"}
    section: Optional[str] = None
    open_items: List[FocusItem] = []
    done: List[FocusItem] = []
    for raw in text.splitlines():
        line = raw.strip()
        sec = _section_of(line, headings)
        if sec is not None:
            section = sec
            continue
        if section != "focus" or not line.startswith("- ["):
            continue
        m = re.match(r'^-\s+\[( |x|X|>)\]\s+(.*)$', line)
        if not m:
            continue
        mark = m.group(1)
        slug, outcome = _split_dash(m.group(2).strip())
        slug = slug.strip()
        if not slug:
            slug = make_slug(outcome)
        item = FocusItem(slug=slug, outcome=outcome.strip(),
                         state=_FOCUS_STATE[mark])
        if item.state == "done":
            done.append(item)
        else:
            open_items.append(item)
    return open_items, done[-3:]


def focus_item_text(item: FocusItem) -> str:
    return f"{item.slug}  — {item.outcome}"


def format_focus_line(item: FocusItem) -> str:
    mark = _FOCUS_MARK[item.state]
    return f"- [{mark}] {focus_item_text(item)}"


def render_focus(open_items: List[FocusItem],
                 done: List[FocusItem]) -> str:
    lines = ["## Focus"]
    lines.extend(format_focus_line(item) for item in open_items)
    lines.extend(format_focus_line(item) for item in done[-3:])
    return "\n".join(lines) + "\n"


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
    dm = re.search(r'^design:\s*(.+)$', wm, re.MULTILINE)
    design = dm.group(1).strip() if dm else ""
    if design in ("—", "-"):
        design = ""

    ws = Workstream(ws_id=ws_id, name=name, design=design)
    ws.units = parse_units(_read(ws_dir / "units.md"))
    ws.planned, ws.wf_followups = parse_backlog(_read(ws_dir / "backlog.md"))
    open_items, _done = parse_focus(_read(ws_dir / "focus.md"))
    ws.active_focus = next((f for f in open_items if f.state == "active"),
                           None)
    ws.focus_queued = [f for f in open_items if f.state != "active"]

    for u in ws.units:
        udir = ws_dir / "units" / u.slug
        u.tasks_done, u.tasks_total, u.followups, u.needs = parse_progress(
            _read(udir / "progress.md"))
        u.log = parse_log(_read(udir / "log.md"))
        u.dropped = any(kind == "dropped" for _ts, kind, _p in u.log)
    ws.spikes = parse_spikes(_read(ws_dir / "spikes.md"))
    for sp in ws.spikes:
        sdir = ws_dir / "spikes" / sp.slug
        sp.tasks_done, sp.tasks_total, _, sp.needs = parse_progress(
            _read(sdir / "progress.md"), include_followups=False)
        sp.log = parse_log(_read(sdir / "log.md"))
        sp.dropped = any(kind == "dropped" for _ts, kind, _p in sp.log)
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


_UNIT_FU_RE = re.compile(r'^(.*):(F\d+)$')   # <unit>:F<n>, unit part greedy


def _is_followup_target(target: str) -> bool:
    return bool(re.match(r'^WF\d+$', target) or re.search(r':F\d+$', target)
                or re.match(r'^F\d+$', target))


def _fu_key(target: str) -> str:
    """Canonical follow-up id: `WF<n>`, or `<bare-slug>:F<n>`.

    Need targets and `claims=` entries spell a unit-scoped follow-up
    either way the SPEC allows (`<ws-id>:<slug>:F<n>` or `<slug>:F<n>`);
    proposals use the bare form, so every side normalizes through here.
    """
    m = _UNIT_FU_RE.match(target)
    return f"{_slug_of(m.group(1))}:{m.group(2)}" if m else target


def claimer_of(fid: str, ws: Workstream) -> Optional[Unit]:
    """The unit whose `claims=` covers this follow-up, else None.

    A dropped unit releases its claim — that is what re-opens a claimed
    follow-up when its unit is abandoned, with nothing rewritten.
    """
    for u in ws.units:
        if not u.dropped and fid in {_fu_key(c) for c in u.claims}:
            return u
    return None


def followup_open(fid: str, fu: Followup, ws: Workstream) -> bool:
    """Is this follow-up still open work?

    Open unless its box is checked or a live unit claims it. A claimed
    follow-up is that unit's business: while the unit is active it counts
    as active work, and once the unit is terminal the claim carries the
    resolution. The single source for "open follow-up" — `workstream_done`,
    the board's backlog, `ws-next`'s open items and its proposals all ask
    here.
    """
    return not fu.checked and claimer_of(fid, ws) is None


def _by_spike(ws: Workstream) -> Dict[str, Spike]:
    return {s.slug: s for s in ws.spikes}


def spike_needs(sp: Spike) -> List[Need]:
    return list(sp.needs)


def derive_spike_status(sp: Spike, ws: Workstream,
                        by_slug: Dict[str, Unit],
                        by_spike: Dict[str, Spike]) -> str:
    if sp.dropped:
        return "dropped"
    if spike_needs(sp) and _has_unmet_spike_need(sp, ws, by_slug, by_spike):
        return "blocked"
    if sp.spike_complete:
        return "complete"
    return "researching"


def _has_unmet_spike_need(sp: Spike, ws: Workstream,
                          by_slug: Dict[str, Unit],
                          by_spike: Dict[str, Spike]) -> bool:
    for n in spike_needs(sp):
        satisfied, _note = need_state(n.target, ws, by_slug, by_spike)
        if not satisfied:
            return True
    return False


def derive_status(ws: Workstream) -> None:
    """Fill each unit's and spike's derived status, first-match-wins."""
    by_slug = {u.slug: u for u in ws.units}
    by_spike = _by_spike(ws)
    for u in ws.units:
        u.status = _status_for(u, ws, by_slug, by_spike)
    for sp in ws.spikes:
        sp.status = derive_spike_status(sp, ws, by_slug, by_spike)


def _status_for(u: Unit, ws: Workstream, by_slug: Dict[str, Unit],
                by_spike: Dict[str, Spike]) -> str:
    if u.dropped:
        return "dropped"
    if is_merged(u):
        return "merged"
    if unit_needs(u, ws) and _has_unmet_need(u, ws, by_slug, by_spike):
        return "blocked"
    if u.pr and u.pr.state == "OPEN" and not u.pr.is_draft:
        return "in-review"
    return "building"


def unit_needs(u: Unit, ws: Workstream) -> List[Need]:
    """Explicit needs plus the implicit base need when base is a unit."""
    needs = list(u.needs)
    by_slug = {x.slug: x for x in ws.units}
    base = recorded_base(u) or u.stacked_on
    if base and _slug_of(base) in by_slug:
        needs.insert(0, Need(nid="base", target=base, note="base"))
    return needs


def pending_spike_slugs(ws: Workstream) -> set:
    """Slugs referenced in needs= but absent from both ledgers."""
    ledger = {u.slug for u in ws.units} | {s.slug for s in ws.spikes}
    pending: set = set()
    for u in ws.units:
        for n in u.needs:
            if _is_followup_target(n.target):
                continue
            slug = _slug_of(n.target)
            if slug not in ledger:
                pending.add(slug)
    for sp in ws.spikes:
        for n in sp.needs:
            if _is_followup_target(n.target):
                continue
            slug = _slug_of(n.target)
            if slug not in ledger:
                pending.add(slug)
    for p in ws.planned:
        for t in p.needs:
            slug = _slug_of(t)
            if slug not in ledger:
                pending.add(slug)
    return pending


def need_state(target: str, ws: Workstream,
               by_slug: Dict[str, Unit],
               by_spike: Optional[Dict[str, Spike]] = None) -> Tuple[bool, str]:
    """Return (satisfied, note). note is "dropped" / "pending" / "removed" / "".

    Unit target → satisfied at code-complete. Spike target → satisfied at
    spike-complete. Follow-up target → claimed or checked. Pending spike
    slug → open, not removed.
    """
    if by_spike is None:
        by_spike = _by_spike(ws)
    if _is_followup_target(target):
        fu = _find_followup(target, ws, by_slug)
        if fu is None:
            return False, "removed"
        claimer = claimer_of(_fu_key(target), ws)
        if claimer is not None:
            return claimer.code_complete, ""
        return fu.checked, ""
    slug = _slug_of(target)
    dep = by_slug.get(slug)
    if dep is not None:
        if dep.dropped:
            return False, "dropped"
        return dep.code_complete, ""
    dep_spike = by_spike.get(slug)
    if dep_spike is not None:
        if dep_spike.dropped:
            return False, "dropped"
        return dep_spike.spike_complete, ""
    if any(p.slug == slug for p in ws.planned):
        return False, ""   # planned unit, not started — open, not removed
    if slug in pending_spike_slugs(ws):
        return False, "pending"
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
    m = _UNIT_FU_RE.match(target)
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
                    by_slug: Dict[str, Unit],
                    by_spike: Dict[str, Spike]) -> bool:
    for n in unit_needs(u, ws):
        satisfied, _note = need_state(n.target, ws, by_slug, by_spike)
        if not satisfied:
            return True
    return False


def _has_plan_line(u: Unit) -> bool:
    return plan_log_path(u) is not None


def _has_execute_mode(u: Unit) -> bool:
    return any(
        kind == "decision" and payload.startswith("execute-mode=")
        for _ts, kind, payload in u.log
    )


def plan_file_digest(path: str) -> Optional[str]:
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()[:8]


def _first_plan_log_ts(u: Unit) -> Optional[str]:
    for ts, kind, _payload in u.log:
        if kind == "plan":
            return ts
    return None


def _has_prewalk_skipped(u: Unit, reason: str) -> bool:
    needle = f"prewalk=skipped reason={reason}"
    return any(
        kind == "decision" and needle in payload
        for _ts, kind, payload in u.log
    )


def _has_valid_prewalk_done(u: Unit, plan_path: str,
                            digest: str) -> bool:
    for _ts, kind, payload in reversed(u.log):
        if kind != "decision" or not payload.startswith("prewalk=done"):
            continue
        if f"plan={plan_path}" not in payload:
            continue
        if f"digest={digest}" not in payload:
            continue
        return True
    return False


def _has_critic_skipped(u: Unit, reason: str) -> bool:
    needle = f"critic=skipped reason={reason}"
    return any(
        kind == "decision" and needle in payload
        for _ts, kind, payload in u.log
    )


def _has_valid_critic_done(u: Unit, digest: Optional[str]) -> bool:
    if not digest:
        return False
    for _ts, kind, payload in reversed(u.log):
        if kind != "decision" or not payload.startswith("critic=done"):
            continue
        if f"digest={digest}" in payload:
            return True
    return False


def _pending_prewalk_phase(u: Unit, plan_path: Optional[str],
                           digest: Optional[str], *,
                           models_ready: bool) -> Optional[str]:
    if not plan_path or not digest:
        return None
    if _has_valid_prewalk_done(u, plan_path, digest):
        return None
    if _has_prewalk_skipped(u, "headless"):
        return None
    if (_has_prewalk_skipped(u, "grandfather")
            or _has_prewalk_skipped(u, "split")):
        return None
    return "prewalk-config" if not models_ready else "prewalk"


def _pending_critic_phase(u: Unit, digest: Optional[str]) -> Optional[str]:
    if not digest:
        return None
    if _has_valid_critic_done(u, digest):
        return None
    if (_has_critic_skipped(u, "headless")
            or _has_critic_skipped(u, "grandfather")
            or _has_critic_skipped(u, "flag")):
        return None
    return "critic"


def _should_grandfather_prewalk(u: Unit, activated_at: Optional[str]) -> bool:
    if not activated_at:
        return False
    plan_ts = _first_plan_log_ts(u)
    if not plan_ts:
        return False
    return plan_ts < activated_at


def resume_phase(u: Unit, ws: Workstream,
                 by_slug: Dict[str, Unit], *,
                 prewalk_enabled: bool = False,
                 skip_prewalk: bool = False,
                 headless: bool = False,
                 split_skip: bool = False,
                 grandfather: bool = False,
                 models_ready: bool = True,
                 review_enabled: bool = False,
                 skip_critic: bool = False,
                 grandfather_critic: bool = False,
                 critic_digest: Optional[str] = None) -> str:
    """Phase for ws-resume loop control.

    First match: blocked > plan > prewalk-config > prewalk > plan-pause >
    loop > ship-pause > draft-pr > done. Planning gates on a ``plan`` log
    line plus an ``execute-mode`` decision — not on empty tasks alone.
    """
    if u.dropped or is_merged(u):
        return "done"
    by_spike = _by_spike(ws)
    if _has_unmet_need(u, ws, by_slug, by_spike):
        return "blocked"
    if not _has_execute_mode(u):
        if _has_plan_line(u):
            if (prewalk_enabled and not skip_prewalk and not headless
                    and not split_skip and not grandfather):
                plan_path = latest_plan_log_path(u)
                digest = (plan_file_digest(plan_path)
                          if plan_path else None)
                prewalk = _pending_prewalk_phase(
                    u, plan_path, digest, models_ready=models_ready)
                if prewalk:
                    return prewalk
            return "plan-pause"
        if u.tasks_total == 0:
            return "plan"
        if not u.code_complete:
            return "loop"
    if not u.code_complete:
        return "loop"
    if (review_enabled and not skip_critic and not headless
            and not grandfather_critic):
        critic = _pending_critic_phase(u, critic_digest)
        if critic:
            return critic
    if u.pr is None:
        return "ship-pause"
    if u.pr.is_draft:
        return "draft-pr"
    return "done"


def _spike_has_plan_line(sp: Spike) -> bool:
    return any(kind == "plan" for _ts, kind, _p in sp.log)


def _spike_has_execute_mode(sp: Spike) -> bool:
    return any(
        kind == "decision" and payload.startswith("execute-mode=")
        for _ts, kind, payload in sp.log
    )


def resume_spike_phase(sp: Spike, ws: Workstream,
                       by_slug: Dict[str, Unit],
                       by_spike: Dict[str, Spike]) -> str:
    """Phase for spike ws-resume: blocked | plan | plan-pause | loop | done."""
    if sp.dropped:
        return "done"
    if _has_unmet_spike_need(sp, ws, by_slug, by_spike):
        return "blocked"
    if not _spike_has_execute_mode(sp):
        if _spike_has_plan_line(sp):
            return "plan-pause"
        if sp.tasks_total == 0:
            return "plan"
    if not sp.spike_complete:
        return "loop"
    return "done"


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
    has_spikes: bool = False
    focus_line: str = ""


def focus_line_for(ws: Workstream) -> str:
    if not ws.active_focus:
        return "Focus: — (none set)"
    f = ws.active_focus
    line = f"Focus: {f.slug} — {f.outcome}"
    n = len(ws.focus_queued)
    if n:
        line += f" (+{n} queued)"
    return line


def _pr_seg(u: Unit) -> str:
    mv = effective_merged_via(u)
    if mv and mv.pr:
        return f" · #{mv.pr} via {mv.branch}"
    return f" · #{u.pr.number}" if u.pr and u.pr.number else ""


def _gist(text: str, limit: int = 100) -> str:
    """First sentence, else a hard truncation. Mechanical by design —
    the full text lives in the source file; the board stays glanceable."""
    text = " ".join(text.split())
    m = re.search(r'(.+?[.!?])(\s|$)', text)
    if m and len(m.group(1)) <= limit + 20:
        return m.group(1)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _spike_tag(slug: str) -> str:
    return f"{slug} [spike]"


def _spike_progress_seg(sp: Spike) -> str:
    if sp.tasks_total == 0:
        return " · not planned"
    return f" · {sp.tasks_done}/{sp.tasks_total}"


def build_board(ws: Workstream,
                phase_for: Optional[Callable[[Unit], str]] = None) -> Board:
    derive_status(ws)
    by_slug = {u.slug: u for u in ws.units}
    by_spike = _by_spike(ws)
    b = Board(name=ws.name, has_spikes=bool(ws.spikes))

    ledger_slugs = set(by_slug)
    for u in ws.units:
        if u.status == "merged":
            b.done.append(f"{u.slug}{_pr_seg(u)}")
        elif u.status == "dropped":
            b.dropped.append(u.slug)
        elif u.status == "blocked":
            b.blocked.append(_blocked_cell(u, ws, by_slug, by_spike))
        else:  # building | in-review
            ph = phase_for(u) if phase_for else None
            suffix = unit_board_suffix(u, phase=ph)
            b.in_progress.append(f"{u.slug}{_pr_seg(u)} · {suffix}")

    for sp in ws.spikes:
        cell = _spike_tag(sp.slug)
        if sp.status == "complete":
            b.done.append(f"{cell}{_spike_progress_seg(sp)}")
        elif sp.status == "dropped":
            b.dropped.append(cell)
        elif sp.status == "blocked":
            b.blocked.append(_spike_blocked_cell(sp, ws, by_slug, by_spike))
        else:
            b.in_progress.append(f"{cell}{_spike_progress_seg(sp)}")

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

    planned_only = [p for p in ws.planned if p.slug not in ledger_slugs]
    non_dropped_spikes = [s for s in ws.spikes if s.status != "dropped"]
    b.merged_count = len(b.done)
    b.total_count = (
        len([u for u in ws.units if u.status != "dropped"])
        + len(non_dropped_spikes)
        + len(planned_only)
    )

    # Backlog: open in-flight F<n> + open workstream WF<n>. A follow-up a
    # live unit claims is that unit's row, not a backlog line.
    for u in ws.units:
        if u.status in ("merged", "dropped"):
            continue
        for fu in u.followups:
            if followup_open(f"{u.slug}:{fu.fid}", fu, ws):
                b.backlog.append(
                    f"- {fu.fid} {_gist(fu.desc)} (follow-up from {u.slug})")
    for fu in ws.wf_followups:
        if followup_open(fu.fid, fu, ws):
            origin = fu.origin or ws.ws_id
            b.backlog.append(
                f"- {fu.fid} {_gist(fu.desc)} (follow-up from {origin})")

    b.complete = workstream_done(ws, by_slug)
    b.focus_line = focus_line_for(ws)
    return b


def _blocked_cell(u: Unit, ws: Workstream,
                  by_slug: Dict[str, Unit],
                  by_spike: Optional[Dict[str, Spike]] = None) -> str:
    if by_spike is None:
        by_spike = _by_spike(ws)
    pairs = unmet_needs(u, ws, by_slug, by_spike)
    parts = [_blocked_need_label(t, n, by_spike) for t, n in pairs]
    cell = f"{u.slug} · needs {', '.join(parts)}"
    return cell + _pr_seg(u)


def _spike_blocked_cell(sp: Spike, ws: Workstream,
                        by_slug: Dict[str, Unit],
                        by_spike: Dict[str, Spike]) -> str:
    pairs = _spike_unmet_needs(sp, ws, by_slug, by_spike)
    parts = [_blocked_need_label(t, n, by_spike) for t, n in pairs]
    return f"{_spike_tag(sp.slug)} · needs {', '.join(parts)}"


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
    """SPEC "Workstream done": no active unit/spike and no open backlog."""
    active_units = {"building", "blocked", "in-review"}
    if any(u.status in active_units for u in ws.units):
        return False
    active_spikes = {"researching", "blocked"}
    if any(sp.status in active_spikes for sp in ws.spikes):
        return False
    ledger_slugs = set(by_slug)
    if any(p.slug not in ledger_slugs for p in ws.planned):
        return False
    if any(followup_open(fu.fid, fu, ws) for fu in ws.wf_followups):
        return False
    for u in ws.units:
        if any(followup_open(f"{u.slug}:{fu.fid}", fu, ws)
               for fu in u.followups):
            return False
    return True


# ---------------------------------------------------------------------------
# Decision engine — ws-next router (SPEC decision table, ranked)
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
                by_slug: Dict[str, Unit],
                by_spike: Optional[Dict[str, Spike]] = None
                ) -> List[Tuple[str, str]]:
    """(target, note) for each of the unit's needs that isn't satisfied."""
    return _unmet_need_pairs(unit_needs(u, ws), ws, by_slug, by_spike)


def _spike_unmet_needs(sp: Spike, ws: Workstream,
                       by_slug: Dict[str, Unit],
                       by_spike: Dict[str, Spike]) -> List[Tuple[str, str]]:
    return _unmet_need_pairs(spike_needs(sp), ws, by_slug, by_spike)


def _unmet_need_pairs(needs: List[Need], ws: Workstream,
                      by_slug: Dict[str, Unit],
                      by_spike: Optional[Dict[str, Spike]]) -> List[Tuple[str, str]]:
    out = []
    for n in needs:
        satisfied, note = need_state(n.target, ws, by_slug, by_spike)
        if not satisfied:
            out.append((n.target, note))
    return out


def _blocked_need_label(target: str, note: str,
                        by_spike: Dict[str, Spike]) -> str:
    lab = (_fu_key(target) if _is_followup_target(target)
           else _slug_of(target))
    if note:
        lab += f" ({note})"
    elif lab in by_spike:
        lab += " [spike]"
    return lab


def _spike_readiness(sp: Spike) -> Optional[str]:
    if sp.spike_complete:
        return None
    if sp.tasks_total:
        left = sp.tasks_total - sp.tasks_done
        return f"{left} of {sp.tasks_total} tasks left"
    if _spike_has_plan_line(sp) and not _spike_has_execute_mode(sp):
        return "plan-pause (store incomplete)"
    return "no tasks planned yet"


def _drifted(u: Unit) -> bool:
    """PR base moved off the recorded base (GitHub retargeted, or the base
    merged) with no restack reconciling it yet."""
    if not (u.pr and u.pr.base):
        return False
    rb = recorded_base(u)
    return rb is not None and u.pr.base != rb


def unit_readiness(u: Unit, *, phase: Optional[str] = None) -> Optional[str]:
    """Stack-base display suffix; None when implicit base need satisfied."""
    if phase == "prewalk":
        return "prewalk (exploring)"
    if phase == "prewalk-config":
        return "prewalk (config required)"
    if phase == "critic":
        return "critic (reviewing)"
    if u.code_complete:
        return None
    if u.tasks_total:
        left = u.tasks_total - u.tasks_done
        return f"{left} of {u.tasks_total} tasks left"
    if _has_plan_line(u) and not _has_execute_mode(u):
        return "plan-pause (store incomplete)"
    return "no tasks planned yet"


def _readiness_for_phase(u: Unit, phase: str) -> Optional[str]:
    if phase in ("prewalk", "prewalk-config", "critic"):
        return unit_readiness(u, phase=phase) or phase
    if phase == "plan-pause":
        return unit_readiness(u)
    return None


def unit_board_suffix(u: Unit, *, phase: Optional[str] = None) -> str:
    """In-progress column suffix for board display."""
    if phase:
        r = _readiness_for_phase(u, phase)
        if r:
            return r
    if u.tasks_total:
        return f"{u.tasks_done}/{u.tasks_total}"
    return unit_readiness(u) or f"{u.tasks_done}/{u.tasks_total}"


def _resume_move_why(u: Unit, *,
                     phase_for: Optional[Callable[[Unit], str]] = None
                     ) -> str:
    if phase_for:
        r = _readiness_for_phase(u, phase_for(u))
        if r:
            return r
    if u.code_complete:
        return (f"tasks done, PR #{u.pr.number}" if u.pr and u.pr.number
                else "tasks done, PR open")
    return unit_readiness(u) or "no tasks planned yet"


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


def _spike_dependents(sp: Spike, ws: Workstream,
                      by_slug: Dict[str, Unit],
                      by_spike: Dict[str, Spike]) -> int:
    n = 0
    for v in ws.units:
        if v.status != "blocked":
            continue
        if any(_slug_of(t) == sp.slug
               for t, _note in unmet_needs(v, ws, by_slug, by_spike)):
            n += 1
    for s in ws.spikes:
        if s.slug == sp.slug or s.status != "blocked":
            continue
        if any(_slug_of(t) == sp.slug
               for t, _note in _spike_unmet_needs(s, ws, by_slug, by_spike)):
            n += 1
    return n


@dataclass
class Move:
    unit: str                       # unit slug (ledger unit or planned)
    rule: str                       # restack|ship|resume
    command: str                    # resolved ws-* command
    branch: Optional[str] = None    # None until a worktree exists
    why: str = ""                   # short display phrase


# Rule priority for ranking: a rebase unblocks everything downstream,
# a finished unit is one PR away, work in flight beats work not begun.
_RULE_RANK = {"restack": 0, "ship": 1, "resume": 2}

_RULE_HEADLINE = {
    "restack": "base moved; rebase before proceeding",
    "ship": "tasks done, no PR — ship it",
    "resume": "advance the in-flight unit",
}


def _code_complete_waiting_on_open_pr(u: Unit) -> bool:
    return (u.code_complete and u.pr
            and u.pr.state == "OPEN" and not u.pr.is_draft)


def _code_complete_closed_pr(u: Unit) -> bool:
    return u.code_complete and u.pr and u.pr.state == "CLOSED"


def enumerate_moves(ws: Workstream,
                    by_slug: Dict[str, Unit],
                    overlay: Optional[Dict[str, ReconcileOverlay]] = None,
                    *,
                    phase_for: Optional[Callable[[Unit], str]] = None
                    ) -> List[Move]:
    """Every move runnable right now, ranked: at most one per unit/spike,
    ordered by rule priority, then dependents (critical path first),
    then source order. moves[0] is the router's default."""
    ranked: List[Tuple[Tuple[int, int, int], Move]] = []
    by_spike = _by_spike(ws)

    for i, u in enumerate(ws.units):
        if u.status in ("merged", "dropped"):
            continue
        if _overlay_suppresses(u.slug, overlay):
            continue
        deps = -_dependents(u, ws, by_slug)
        if _drifted(u):
            ranked.append(((_RULE_RANK["restack"], deps, i),
                           Move(u.slug, "restack", f"ws-restack {u.slug}",
                                u.branch or None,
                                f"base moved off {recorded_base(u)}")))
            continue
        if u.status not in ("building", "in-review"):
            continue                # blocked: the blocker moves first
        if _code_complete_waiting_on_open_pr(u):
            continue
        if _code_complete_closed_pr(u):
            ranked.append(((_RULE_RANK["resume"], deps, i),
                           Move(u.slug, "resume", f"ws-resume {u.slug}",
                                u.branch or None,
                                "ledger PR closed — reconcile or drop")))
            continue
        if u.code_complete and not u.pr:
            ranked.append(((_RULE_RANK["ship"], deps, i),
                           Move(u.slug, "ship", f"ws-resume {u.slug}",
                                u.branch or None, "tasks done, no PR")))
        else:
            why = _resume_move_why(u, phase_for=phase_for)
            ranked.append(((_RULE_RANK["resume"], deps, i),
                           Move(u.slug, "resume", f"ws-resume {u.slug}",
                                u.branch or None, why)))

    base = len(ws.units)
    for j, sp in enumerate(ws.spikes):
        if sp.status in ("complete", "dropped"):
            continue
        if sp.status == "blocked":
            continue
        deps = -_spike_dependents(sp, ws, by_slug, by_spike)
        why = _spike_readiness(sp) or "no tasks planned yet"
        ranked.append(((_RULE_RANK["resume"], deps, base + j),
                       Move(sp.slug, "resume", f"ws-resume {sp.slug}",
                            None, why)))

    ranked.sort(key=lambda pair: pair[0])
    return [m for _key, m in ranked]


@dataclass
class Proposable:
    """A follow-up a new unit could claim (SPEC §Follow-up units)."""
    fid: str                        # WF<n> or <slug>:F<n>
    desc: str
    origin: str                     # ws-id for WF, unit slug for F
    blocks: List[str] = field(default_factory=list)   # units it blocks


@dataclass
class StackBase:
    slug: str
    repo: str
    branch: str
    readiness: Optional[str] = None


_OVERLAY_GATE = frozenset({"tier-a", "tier-b"})


@dataclass
class ReconcileOverlay:
    """Per-slug ship-detection result; never persisted by ws-next."""
    slug: str
    outcome: str
    record: Optional[MergedVia] = None


def _overlay_outcome_gates(outcome: str) -> bool:
    return outcome in _OVERLAY_GATE


def _overlay_suppresses(slug: str,
                        overlay: Optional[Dict[str, ReconcileOverlay]]
                        ) -> bool:
    if not overlay:
        return False
    o = overlay.get(slug)
    return o is not None and _overlay_outcome_gates(o.outcome)


def _reconcile_candidates(
        overlay: Optional[Dict[str, ReconcileOverlay]]
        ) -> List[ReconcileOverlay]:
    if not overlay:
        return []
    return [o for o in overlay.values() if _overlay_outcome_gates(o.outcome)]


def stackable_bases(ws: Workstream,
                    proposal_repo: Optional[str] = None,
                    overlay: Optional[Dict[str, ReconcileOverlay]] = None
                    ) -> List[StackBase]:
    if not proposal_repo:
        return []
    want = proposal_repo.lower()
    out: List[StackBase] = []
    for u in ws.units:
        if u.dropped or not u.branch or not u.repo:
            continue
        if _overlay_suppresses(u.slug, overlay):
            continue
        if u.status not in ("building", "in-review"):
            continue
        if _drifted(u):
            continue
        if u.repo.lower() != want:
            continue
        out.append(StackBase(u.slug, u.repo, u.branch, unit_readiness(u)))
    return out


@dataclass
class Decision:
    rule: str  # restack|ship|resume|triage-*|suggest|reconcile-pending|...
    command: Optional[str] = None   # resolved ws-* command; None for triage/done
    unit: Optional[str] = None      # unit slug when the command is unit-scoped
    branch: Optional[str] = None    # ledger branch; None until a worktree exists
    moves: List[Move] = field(default_factory=list)    # ranked; moves[0] default
    blocked: List[str] = field(default_factory=list)   # "<unit> — needs ..."
    waiting: List[str] = field(default_factory=list)   # "<unit> — PR #N"
    open_items: List[str] = field(default_factory=list)
    headline: str = ""
    # Proposal material for the skill — full `suggest` or alongside
    # non-restack moves when `_proposal_attachable` holds.
    proposable: List[Proposable] = field(default_factory=list)
    covered: List[str] = field(default_factory=list)   # "<slug> — <title>"
    design: str = ""
    active_focus: Optional[FocusItem] = None
    focus_queue: List[FocusItem] = field(default_factory=list)
    stackable: Optional[List[StackBase]] = None
    reconcile_candidates: List[ReconcileOverlay] = field(default_factory=list)


def _followup_blockers(ws: Workstream,
                       by_slug: Dict[str, Unit]) -> Dict[str, List[str]]:
    """follow-up id → the units it blocks. Only a `blocked` unit can have
    an unmet need, so the others need no walk."""
    out: Dict[str, List[str]] = {}
    for u in ws.units:
        if u.status != "blocked":
            continue
        for target, _note in unmet_needs(u, ws, by_slug):
            if not _is_followup_target(target):
                continue
            slugs = out.setdefault(_fu_key(target), [])
            if u.slug not in slugs:     # two needs, one target
                slugs.append(u.slug)
    return out


def proposable_followups(ws: Workstream,
                         by_slug: Dict[str, Unit]) -> List[Proposable]:
    """Follow-ups a new unit could claim: the open ones (§followup_open)
    that no live unit is already working. An `F<n>` in a live unit is
    never proposable — that unit has its own resume move.

    Reads derived status, so `derive_status` must have run.
    """
    found = [(fu.fid, fu, fu.origin or ws.ws_id)
             for fu in ws.wf_followups if followup_open(fu.fid, fu, ws)]
    for u in ws.units:
        if u.status != "merged":
            continue
        found += [(f"{u.slug}:{fu.fid}", fu, u.slug) for fu in u.followups
                  if followup_open(f"{u.slug}:{fu.fid}", fu, ws)]
    if not found:
        return []               # nothing to annotate; skip the needs walk
    blockers = _followup_blockers(ws, by_slug)
    return [Proposable(fid, fu.desc, origin, blockers.get(fid, []))
            for fid, fu, origin in found]


def _pick_successors(slug: str, units: List[Unit],
                     by: Dict[str, Unit]) -> List[str]:
    """Successors to name in a superseded annotation."""
    all_s = [u.slug for u in units if u.restart_of == slug]
    if not all_s:
        return []
    live = [s for s in all_s
            if not by[s].dropped
            and not is_merged(by[s])]
    return live if live else [all_s[-1]]


def _covered_entry(u: Unit, units: List[Unit],
                   by: Dict[str, Unit],
                   overlay: Optional[Dict[str, ReconcileOverlay]] = None
                   ) -> str:
    base = f"{u.slug} — {u.title}" if u.title else u.slug
    if _overlay_suppresses(u.slug, overlay):
        base = f"{base} (reconcile pending)"
    if not u.dropped:
        return base
    succs = _pick_successors(u.slug, units, by)
    if not succs:
        return base
    return f"{base} (superseded by {', '.join(succs)})"


def _covered_scope(ws: Workstream, by_slug: Dict[str, Unit],
                   overlay: Optional[Dict[str, ReconcileOverlay]] = None
                   ) -> List[str]:
    """What the store already covers, so a proposal can skip it. Dropped
    units count — the drop was a decision (SPEC)."""
    out = [_covered_entry(u, ws.units, by_slug, overlay) for u in ws.units]
    for sp in ws.spikes:
        if sp.status not in ("complete", "dropped"):
            continue
        base = f"{sp.slug} — {sp.title} (spike)" if sp.title else f"{sp.slug} (spike)"
        out.append(base)
    out += [f"{p.slug} — {_gist(p.what)} (planned)" for p in ws.planned
            if p.slug not in by_slug]
    return out


def _proposal_material(
        ws: Workstream,
        by_slug: Dict[str, Unit],
        overlay: Optional[Dict[str, ReconcileOverlay]] = None
        ) -> Tuple[List[Proposable], List[str], str]:
    """Follow-ups, covered scope, and design path for Propose a unit."""
    return (proposable_followups(ws, by_slug),
            _covered_scope(ws, by_slug, overlay),
            ws.design)


def _has_proposal_source(ws: Workstream,
                         proposable: List[Proposable]) -> bool:
    return bool(proposable or ws.design or ws.active_focus)


def _proposal_attachable(moves: List[Move]) -> bool:
    """True when no move is restack — proposal may ride alongside."""
    return not any(m.rule == "restack" for m in moves)


def decide_next(ws: Workstream,
                proposal_repo: Optional[str] = None,
                overlay: Optional[Dict[str, ReconcileOverlay]] = None,
                *,
                phase_for: Optional[Callable[[Unit], str]] = None
                ) -> Decision:
    """Every move runnable now, ranked, with moves[0] as the default.
    Blocked units are never resumed — the router advances their blocker."""
    derive_status(ws)
    by_slug = {u.slug: u for u in ws.units}
    by_spike = _by_spike(ws)
    candidates = _reconcile_candidates(overlay)

    def _stackable_for(attach: bool, design: str) -> Optional[List[StackBase]]:
        if not attach or not (design or ws.active_focus):
            return None
        return stackable_bases(ws, proposal_repo, overlay)

    blocked_lines = []
    for u in ws.units:
        if u.status != "blocked":
            continue
        labels = [_blocked_need_label(t, n, by_spike)
                  for t, n in unmet_needs(u, ws, by_slug, by_spike)]
        blocked_lines.append(f"{u.slug} — needs {', '.join(labels)}")
    for sp in ws.spikes:
        if sp.status != "blocked":
            continue
        labels = [_blocked_need_label(t, n, by_spike)
                  for t, n in _spike_unmet_needs(sp, ws, by_slug, by_spike)]
        blocked_lines.append(f"{sp.slug} [spike] — needs {', '.join(labels)}")

    # Code-complete ready PRs emit no move; surface them so
    # a no-move workstream does not claim "done" while
    # review is still pending.
    waiting_lines = []
    for u in ws.units:
        if u.status != "in-review" or not u.code_complete:
            continue
        why = (f"PR #{u.pr.number}" if u.pr and u.pr.number else "PR open")
        waiting_lines.append(f"{u.slug} — {why}")

    def out(rule, command=None, unit=None, branch=None, moves=None,
            open_items=None, headline="", proposable=None, covered=None,
            design="", active_focus=None, focus_queue=None, stackable=None):
        return Decision(rule=rule, command=command, unit=unit,
                        branch=branch or None, moves=moves or [],
                        blocked=blocked_lines, waiting=waiting_lines,
                        open_items=open_items or [],
                        headline=headline, proposable=proposable or [],
                        covered=covered or [], design=design,
                        active_focus=active_focus,
                        focus_queue=focus_queue or [],
                        stackable=stackable,
                        reconcile_candidates=candidates)

    # Everything runnable now, ranked; the leader is the default.
    moves = enumerate_moves(ws, by_slug, overlay, phase_for=phase_for)
    if moves:
        top = moves[0]
        proposable, covered, design = _proposal_material(ws, by_slug, overlay)
        attach = (_proposal_attachable(moves)
                  and _has_proposal_source(ws, proposable))
        headline = (top.why if top.rule == "resume" and top.why
                    else _RULE_HEADLINE[top.rule])
        return out(top.rule, top.command, top.unit, top.branch, moves,
                   headline=headline,
                   proposable=proposable if attach else [],
                   covered=covered if attach else [],
                   design=design if attach else "",
                   active_focus=ws.active_focus,
                   focus_queue=ws.focus_queued,
                   stackable=_stackable_for(attach, design if attach else ""))

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
            return out("triage-dropped", cmd, u.slug, u.branch,
                       headline="blocker dropped/removed — re-point or clear")

    open_items = []
    ledger = set(by_slug)
    for p in ws.planned:
        if p.slug not in ledger:
            open_items.append(f"planned: {p.slug} — {_gist(p.what)}")
    for u in ws.units:
        for fu in u.followups:
            if followup_open(f"{u.slug}:{fu.fid}", fu, ws):
                open_items.append(f"{u.slug}:{fu.fid} — {_gist(fu.desc)}")
    for fu in ws.wf_followups:
        if followup_open(fu.fid, fu, ws):
            open_items.append(f"{fu.fid} — {_gist(fu.desc)}")

    # Terminal fork, first match wins: suggest > triage-backlog >
    # waiting > empty > done. `suggest` when no moves exist; terminal
    # moves may carry proposal material alongside (see early return).
    proposable, covered, design = _proposal_material(ws, by_slug, overlay)
    if candidates and _has_proposal_source(ws, proposable):
        n = len(candidates)
        headline = (f"reconcile before proposing — {n} unit(s) may have "
                    "shipped elsewhere")
        return out("reconcile-pending", None, None, open_items=open_items,
                   headline=headline,
                   proposable=proposable, covered=covered, design=design,
                   active_focus=ws.active_focus,
                   focus_queue=ws.focus_queued,
                   stackable=_stackable_for(True, design))
    if _has_proposal_source(ws, proposable):
        headline = ("focus: {} — propose the next unit".format(
            ws.active_focus.slug)
                    if ws.active_focus
                    else "no store work left — propose the next unit")
        return out("suggest", None, None, open_items=open_items,
                   headline=headline,
                   proposable=proposable, covered=covered, design=design,
                   active_focus=ws.active_focus,
                   focus_queue=ws.focus_queued,
                   stackable=_stackable_for(True, design))
    # Open work the proposal path can't take: a planned unit stuck behind
    # an unresolvable need, an F<n> in a live blocked unit, a hand-broken
    # need cycle.
    if blocked_lines or open_items:
        head = ("no active unit; open backlog remains — triage"
                if open_items and not blocked_lines
                else "no runnable step — advance a blocker or triage backlog")
        return out("triage-backlog", None, None, open_items=open_items,
                   headline=head)

    if waiting_lines:
        return out("waiting", None, None,
                   headline="waiting on review — nothing to advance")

    if not ws.units:
        return out("empty", None, None,
                   headline="no units yet — start the first with ws-start")

    return out("done", None, None, headline="workstream done — close it")
