#!/usr/bin/env python3
"""Aggregate sim/ and layout/ evidence records into one per-spec-row report.

Issue #22 (T1 item 8): a characterization report format/aggregator that rolls
up per-spec-row `sim/*/records/*.md` (PVT-corner) and
`layout/*/reports/*/record.md` (DRC/LVS) evidence records into a single
markdown (or JSON) table keyed by `spec/target-spec.md` row number.

This is a **rollup** tool, not an evidence generator: it never simulates,
extracts, or measures anything itself -- it only reads the append-only
records `sim/`/`layout/` already committed and reports what they say. See
`measurements/README.md` for the report format and the spec-row citation
convention a `sim/`/`layout/` record uses to appear against a specific row.

Issue #152 closed the gap that made this report structurally empty: the
citation convention was documented but adopted by nothing, so every row read
"No evidence" no matter how much real evidence landed. The citation is now
declared once per experiment (`sim/<slug>/testbench/tb.json`'s `spec_rows`,
`layout/<block>/spec-rows.json`), stamped into every newly-minted record by
the renderers, and -- for records minted before the convention, which are
append-only and must not be edited -- resolved from that same declaration
here.

Standard library only, mirroring `sim/run_corners.py` and
`layout/bin/render-record.py`'s "no extra runtime dependency" convention.

    python3 measurements/aggregate.py --out measurements/report.md
    python3 measurements/aggregate.py --format json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# An evidence record (either style) declares which spec/target-spec.md row(s)
# it substantiates by including a line such as:
#
#   - **Spec row(s)**: 8, 9
#
# anywhere in its body, or an explicit
#
#   - **Spec row(s)**: none -- <why this record measures no spec row>
#
# `sim/harness/report.py` and `layout/bin/render_common.py` emit that line
# into every record they mint, from the experiment's own `spec_rows`
# declaration -- so the convention is carried by construction rather than by
# an author remembering it (issue #152).
SPEC_ROWS_RE = re.compile(r"\*\*Spec row\(s\)\*\*:\s*([0-9,\s]+)")
# ... and this matches the *presence* of the line whatever follows the colon,
# so "declared none" is distinguishable from "never declared anything".
SPEC_ROWS_LINE_RE = re.compile(r"\*\*Spec row\(s\)\*\*:\s*(\S.*)")

# Where a record's row citation came from. Records minted before the
# convention existed carry no line of their own; for those the aggregator
# falls back to the experiment's own mutable declaration (see
# `_declared_spec_rows`) rather than editing the record, which `sim/README.md`
# and `layout/pll/README.md` forbid outright ("written once and never edited
# or deleted after creation, even to fix a typo").
SOURCE_RECORD = "record"
SOURCE_MANIFEST = "manifest"
SOURCE_UNDECLARED = "undeclared"
SOURCE_MALFORMED = "malformed"

# A record ID is always <YYYYMMDD>-<HHMMSS>-<short-git-sha> (sim/README.md,
# layout/README.md).
RECORD_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]+$")


def _parse_spec_row_refs(text: str) -> list[int]:
    m = SPEC_ROWS_RE.search(text)
    if not m:
        return []
    rows: list[int] = []
    for token in m.group(1).split(","):
        token = token.strip()
        if token.isdigit():
            rows.append(int(token))
    return rows


@dataclass
class SpecRowCitation:
    """Which spec rows a record claims, and on whose authority."""

    rows: list[int]
    source: str  # one of the SOURCE_* constants above
    note: str = ""


def _record_citation(text: str) -> SpecRowCitation | None:
    """The citation a record states in its own body, if it states one."""
    line = SPEC_ROWS_LINE_RE.search(text)
    if not line:
        return None
    rows = _parse_spec_row_refs(text)
    value = line.group(1).strip()
    if rows:
        return SpecRowCitation(rows=rows, source=SOURCE_RECORD, note=value)
    if value.lower().startswith("none"):
        return SpecRowCitation(rows=[], source=SOURCE_RECORD, note=value)
    # A line that is neither row numbers nor an explicit "none" is a typo, not
    # a claim -- surface it rather than silently reading it as "no rows".
    return SpecRowCitation(rows=[], source=SOURCE_MALFORMED, note=value)


def _read_declaration(path: Path, key_holder) -> SpecRowCitation | None:
    """Read a `spec_rows` / `spec_rows_note` declaration out of a JSON file."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("spec_rows"), list):
        return None
    rows = [n for n in data["spec_rows"] if isinstance(n, int) and not isinstance(n, bool)]
    note = str(data.get("spec_rows_note", "") or "").strip()
    return SpecRowCitation(
        rows=rows,
        source=SOURCE_MANIFEST,
        note=note or f"declared by `{key_holder}`",
    )


def _declared_spec_rows(repo_root: Path, kind: str, block: str) -> SpecRowCitation | None:
    """The experiment's own declaration, used only when a record has none.

    `sim/` and `layout/` records are append-only -- a record minted before
    this convention existed cannot be edited to add the citation line. Its
    experiment's declaration is the append-only-safe place to state the
    mapping instead: `sim/<slug>/testbench/` and `layout/<block>/` are both
    explicitly mutable (`sim/README.md`'s append-only rule names `testbench/`
    as an exception), and the declaration is what the renderers now stamp into
    every newly-minted record anyway, so the two can only agree.

    This is a shrinking legacy path, not a parallel convention: every record
    minted from here on carries its own line and never reaches this fallback.
    """
    if kind == "sim":
        rel = Path("sim") / block / "testbench" / "tb.json"
    else:
        rel = Path("layout") / block / "spec-rows.json"
    return _read_declaration(repo_root / rel, rel.as_posix())


def _resolve_citation(
    text: str, *, repo_root: Path, kind: str, block: str
) -> SpecRowCitation:
    """Record's own citation first; the experiment's declaration second."""
    own = _record_citation(text)
    if own is not None:
        return own
    declared = _declared_spec_rows(repo_root, kind, block)
    if declared is not None:
        return declared
    return SpecRowCitation(rows=[], source=SOURCE_UNDECLARED)


def _truncate(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\N{HORIZONTAL ELLIPSIS}"


@dataclass
class SpecRow:
    number: int
    parameter: str
    anchor: str
    draft_target: str


@dataclass
class EvidenceRecord:
    record_id: str
    kind: str  # "sim" or "layout"
    block: str  # experiment slug (sim) or cell name (layout)
    claim: str
    verdict: str  # "PASS" / "FAIL" / "UNKNOWN"
    detail: str
    spec_rows: list[int]
    path: Path  # repo-root-relative
    supersedes: str | None = None
    spec_rows_source: str = SOURCE_RECORD
    spec_rows_note: str = ""

    def citation(self) -> str:
        return f"`{self.path.as_posix()}`"

    def declared_in(self) -> str:
        """The experiment declaration a manifest-sourced citation came from."""
        return (
            f"sim/{self.block}/testbench/tb.json"
            if self.kind == "sim"
            else f"layout/{self.block}/spec-rows.json"
        )

    def rows_provenance(self) -> str:
        """Human-readable "on whose authority" for the rows above."""
        if self.spec_rows_source == SOURCE_MANIFEST:
            return (
                f"declared by `{self.declared_in()}`; the record itself "
                "predates the citation convention and is append-only"
            )
        if self.spec_rows_source == SOURCE_UNDECLARED:
            return "no spec-row declaration found"
        if self.spec_rows_source == SOURCE_MALFORMED:
            return "malformed `**Spec row(s)**` citation"
        return "cited by the record itself"


def parse_spec_rows(spec_path: Path) -> list[SpecRow]:
    """Parse the `## Summary table` of spec/target-spec.md.

    Each row is `| N | [Parameter](#anchor) | draft target | source |
    open question |`; only the first three columns are used here.
    """
    row_re = re.compile(
        r"^\|\s*(\d+)\s*\|\s*\[([^\]]+)\]\(#([^)]+)\)\s*\|\s*([^|]+?)\s*\|"
    )
    rows: list[SpecRow] = []
    for line in spec_path.read_text().splitlines():
        m = row_re.match(line)
        if not m:
            continue
        rows.append(
            SpecRow(
                number=int(m.group(1)),
                parameter=m.group(2).strip(),
                anchor=m.group(3).strip(),
                draft_target=m.group(4).strip(),
            )
        )
    rows.sort(key=lambda r: r.number)
    return rows


_SIM_FIELD_RE = {
    "record_id": re.compile(r"^-\s*\*\*Record ID\*\*:\s*(.+)$", re.MULTILINE),
    "claim": re.compile(r"^-\s*\*\*Claim\*\*:\s*(.+)$", re.MULTILINE),
    "supersedes": re.compile(r"^-\s*\*\*Supersedes\*\*:\s*(.+)$", re.MULTILINE),
}
_SIM_OVERALL_RE = re.compile(
    r"\*\*Overall:\s*(PASS|FAIL)\*\*(?:\s*\(([^)]*)\))?"
)


def parse_sim_record(path: Path, *, repo_root: Path) -> EvidenceRecord:
    """Parse a `sim/<slug>/records/<record-id>.md` evidence record.

    Schema: `sim/README.md` / `sim/harness/report.py`.
    """
    text = path.read_text()

    def field_value(name: str, default: str = "") -> str:
        m = _SIM_FIELD_RE[name].search(text)
        return m.group(1).strip() if m else default

    record_id = field_value("record_id", default=path.stem)
    claim = field_value("claim")

    overall = _SIM_OVERALL_RE.search(text)
    verdict = overall.group(1) if overall else "UNKNOWN"
    detail = (overall.group(2) or "").strip() if overall else ""

    supersedes_raw = field_value("supersedes")
    supersedes = None
    candidate = supersedes_raw.strip("`() ")
    if RECORD_ID_RE.match(candidate):
        supersedes = candidate

    slug = path.relative_to(repo_root).parts[1]  # sim/<slug>/records/<id>.md
    citation = _resolve_citation(text, repo_root=repo_root, kind="sim", block=slug)

    return EvidenceRecord(
        record_id=record_id,
        kind="sim",
        block=slug,
        claim=claim,
        verdict=verdict,
        detail=detail,
        spec_rows=citation.rows,
        path=path.relative_to(repo_root),
        supersedes=supersedes,
        spec_rows_source=citation.source,
        spec_rows_note=citation.note,
    )


_LAYOUT_VERDICT_RE = re.compile(r"^##\s*Overall verdict:\s*(PASS|FAIL)\s*$", re.MULTILINE)
_LAYOUT_CHECKLIST_ITEM_RE = re.compile(r"^-\s*\[( |x)\]", re.MULTILINE)


def parse_layout_record(path: Path, *, repo_root: Path) -> EvidenceRecord:
    """Parse a `layout/<block>/reports/<record-id>/record.md` evidence record.

    Schema: `layout/README.md` / `layout/bin/render-record.py`. The record ID
    is authoritatively the containing directory name (the render script has
    no separate "Record ID" bullet the way sim records do, though it does
    stamp one under "## Provenance" as a cross-check).
    """
    text = path.read_text()
    record_id = path.parent.name

    lines = text.splitlines()
    claim_lines: list[str] = []
    for line in lines[1:]:  # skip the "# ... record: <id>" H1
        if line.startswith("## "):
            break
        if line.strip():
            claim_lines.append(line.strip())
    claim = " ".join(claim_lines)

    verdict_match = _LAYOUT_VERDICT_RE.search(text)
    verdict = verdict_match.group(1) if verdict_match else "UNKNOWN"

    detail = ""
    if verdict_match:
        section_start = verdict_match.end()
        next_heading = text.find("\n## ", section_start)
        section = text[section_start : next_heading if next_heading != -1 else None]
        items = _LAYOUT_CHECKLIST_ITEM_RE.findall(section)
        if items:
            checked = sum(1 for c in items if c == "x")
            detail = f"{checked}/{len(items)} checks passed"

    block = path.relative_to(repo_root).parts[1]  # layout/<block>/reports/<id>/record.md
    citation = _resolve_citation(text, repo_root=repo_root, kind="layout", block=block)

    return EvidenceRecord(
        record_id=record_id,
        kind="layout",
        block=block,
        claim=claim,
        verdict=verdict,
        detail=detail,
        spec_rows=citation.rows,
        path=path.relative_to(repo_root),
        supersedes=None,
        spec_rows_source=citation.source,
        spec_rows_note=citation.note,
    )


def discover_evidence(repo_root: Path) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for p in sorted(repo_root.glob("sim/*/records/*.md")):
        records.append(parse_sim_record(p, repo_root=repo_root))
    for p in sorted(repo_root.glob("layout/*/reports/*/record.md")):
        records.append(parse_layout_record(p, repo_root=repo_root))
    return records


def _layout_latest_ids(repo_root: Path, records: list[EvidenceRecord]) -> dict[str, str]:
    """block -> the record id its `reports/LATEST` pointer names, if any."""
    latest: dict[str, str] = {}
    for block in {r.block for r in records if r.kind == "layout"}:
        latest_file = repo_root / "layout" / block / "reports" / "LATEST"
        if latest_file.is_file():
            latest[block] = latest_file.read_text().strip()
    return latest


def compute_superseded_ids(repo_root: Path, records: list[EvidenceRecord]) -> set[str]:
    """Record IDs that a newer record (sim) or a `LATEST` pointer (layout)
    marks as no longer current.

    Mirrors each tree's own status/supersession convention rather than
    inventing a new one: sim/README.md's "Status / supersession language"
    (`Supersedes` field on the newer record) and layout/README.md's
    `reports/LATEST` pointer.
    """
    superseded: set[str] = set()
    for r in records:
        if r.supersedes:
            superseded.add(r.supersedes)
    latest_by_block = _layout_latest_ids(repo_root, records)
    for r in records:
        if r.kind != "layout":
            continue
        latest = latest_by_block.get(r.block)
        if latest and r.record_id != latest:
            superseded.add(r.record_id)
    return superseded


@dataclass
class ReportData:
    generated_at: str
    spec_rows: list[SpecRow]
    rows: dict[int, list[EvidenceRecord]]
    unmapped: list[EvidenceRecord]
    total_scanned: int
    superseded_count: int


def build_report(spec_rows: list[SpecRow], records: list[EvidenceRecord], *, repo_root: Path) -> ReportData:
    superseded_ids = compute_superseded_ids(repo_root, records)
    current = [r for r in records if r.record_id not in superseded_ids]

    rows: dict[int, list[EvidenceRecord]] = {row.number: [] for row in spec_rows}
    unmapped: list[EvidenceRecord] = []
    for rec in current:
        matched_any = False
        for n in rec.spec_rows:
            if n in rows:
                rows[n].append(rec)
                matched_any = True
        if not matched_any:
            unmapped.append(rec)

    return ReportData(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        spec_rows=spec_rows,
        rows=rows,
        unmapped=unmapped,
        total_scanned=len(records),
        superseded_count=len(superseded_ids),
    )


def _all_current(data: ReportData) -> list[EvidenceRecord]:
    """Every current record exactly once, mapped or not (a record may appear
    against several rows; the citation-provenance counts must not double it).
    """
    seen: dict[str, EvidenceRecord] = {}
    for recs in list(data.rows.values()) + [data.unmapped]:
        for rec in recs:
            seen.setdefault(f"{rec.kind}:{rec.path.as_posix()}", rec)
    return list(seen.values())


def render_markdown(data: ReportData) -> str:
    lines: list[str] = []
    a = lines.append
    a("# PLL characterization report")
    a("")
    a(
        f"Generated: {data.generated_at} by `measurements/aggregate.py` -- "
        "this file is a **derived rollup**, not append-only evidence itself; "
        "re-run the aggregator to refresh it (see `measurements/README.md`)."
    )
    a("")
    a(
        "Rolls up every `sim/*/records/*.md` and `layout/*/reports/*/"
        "record.md` evidence record into one table, keyed by "
        "`spec/target-spec.md` row number. **No row below is a ratified PLL "
        "result, and a populated row is not a passing row.** Only rows 0, 1, "
        "19 and 20 of `spec/target-spec.md` are ratified (`DR-001`/`DR-002`/"
        "`DR-003`); every numeric row an evidence record appears against is "
        "still DRAFT. A record listed against a row is *evidence bearing on "
        "that row* -- the measured input a future decision record would argue "
        "the row from -- never a verdict on it, and never a substitute for "
        "the ratification act itself. Read each record before quoting it: its "
        "own `Verdict` column here is the record's overall pass/fail, which "
        "for several campaigns means \"the harness ran and recorded what "
        "happened\", including recorded non-lock."
    )
    a("")
    a("## Per-spec-row summary")
    a("")
    a("| Row | Parameter | DRAFT target (unratified except rows 0/1/19/20 -- see spec/target-spec.md) | Evidence | Verdict | Citation |")
    a("|---|---|---|---|---|---|")
    for row in data.spec_rows:
        matches = data.rows.get(row.number, [])
        target = _truncate(row.draft_target, 100)
        if not matches:
            a(f"| {row.number} | {row.parameter} | {target} | No evidence | -- | -- |")
            continue
        for i, rec in enumerate(matches):
            num_cell = str(row.number) if i == 0 else ""
            param_cell = row.parameter if i == 0 else ""
            target_cell = target if i == 0 else ""
            evidence = f"{rec.kind}/{rec.block} ({rec.record_id})"
            citation = rec.citation()
            if rec.spec_rows_source == SOURCE_MANIFEST:
                citation += f" -- rows via `{rec.declared_in()}`"
            a(f"| {num_cell} | {param_cell} | {target_cell} | {evidence} | {rec.verdict} | {citation} |")
    a("")
    a("## Evidence found, not mapped to a spec row")
    a("")
    a(
        "Harness-plumbing evidence, negative controls, and anything whose "
        "citation does not resolve to a row of `spec/target-spec.md` -- "
        "listed here rather than silently dropped. The **Why unmapped** "
        "column says which: a record that *declares* it measures no spec row "
        "is doing the right thing, while `no spec-row declaration found` or "
        "`malformed ...` is a gap to close (see `measurements/README.md`)."
    )
    a("")
    if not data.unmapped:
        a("(none)")
    else:
        a("| Kind | Block | Record | Claim | Verdict | Detail | Why unmapped | Citation |")
        a("|---|---|---|---|---|---|---|---|")
        for rec in data.unmapped:
            if rec.spec_rows:
                why = (
                    "cites row(s) "
                    + ", ".join(str(n) for n in rec.spec_rows)
                    + " -- no such row in spec/target-spec.md"
                )
            elif rec.spec_rows_source in (SOURCE_RECORD, SOURCE_MANIFEST):
                why = f"declares it measures no spec row ({rec.rows_provenance()})"
            else:
                why = rec.rows_provenance()
            a(
                f"| {rec.kind} | {rec.block} | {rec.record_id} | "
                f"{_truncate(rec.claim)} | {rec.verdict} | {rec.detail} | "
                f"{why} | {rec.citation()} |"
            )
    a("")
    a("## Scan summary")
    a("")
    a(f"- Evidence records scanned: {data.total_scanned}")
    current_count = data.total_scanned - data.superseded_count
    a(f"- Current (non-superseded): {current_count}")
    a(
        "- Superseded (excluded from the tables above; still retained, "
        f"append-only, under `sim/`/`layout/`): {data.superseded_count}"
    )
    by_record = sum(
        1 for r in _all_current(data) if r.spec_rows_source == SOURCE_RECORD
    )
    by_manifest = sum(
        1 for r in _all_current(data) if r.spec_rows_source == SOURCE_MANIFEST
    )
    undeclared = sum(
        1
        for r in _all_current(data)
        if r.spec_rows_source in (SOURCE_UNDECLARED, SOURCE_MALFORMED)
    )
    a(f"- Spec-row citation stated by the record itself: {by_record}")
    a(
        "- Spec-row citation resolved from the experiment's own declaration "
        "(`sim/<slug>/testbench/tb.json` / `layout/<block>/spec-rows.json`) "
        "because the record predates the convention and is append-only: "
        f"{by_manifest}"
    )
    a(f"- **Current records with no spec-row declaration at all: {undeclared}**")
    a("")
    return "\n".join(lines)


def render_json(data: ReportData) -> str:
    def rec_dict(rec: EvidenceRecord) -> dict:
        return {
            "record_id": rec.record_id,
            "kind": rec.kind,
            "block": rec.block,
            "claim": rec.claim,
            "verdict": rec.verdict,
            "detail": rec.detail,
            "spec_rows": rec.spec_rows,
            "spec_rows_source": rec.spec_rows_source,
            "spec_rows_note": rec.spec_rows_note,
            "path": rec.path.as_posix(),
            "supersedes": rec.supersedes,
        }

    payload = {
        "generated_at": data.generated_at,
        "rows": [
            {
                "number": row.number,
                "parameter": row.parameter,
                "draft_target": row.draft_target,
                "evidence": [rec_dict(r) for r in data.rows.get(row.number, [])],
            }
            for row in data.spec_rows
        ],
        "unmapped_evidence": [rec_dict(r) for r in data.unmapped],
        "scan_summary": {
            "total_scanned": data.total_scanned,
            "superseded": data.superseded_count,
            "current": data.total_scanned - data.superseded_count,
            "cited_by_record": sum(
                1 for r in _all_current(data) if r.spec_rows_source == SOURCE_RECORD
            ),
            "cited_by_manifest": sum(
                1 for r in _all_current(data) if r.spec_rows_source == SOURCE_MANIFEST
            ),
            "undeclared": sum(
                1
                for r in _all_current(data)
                if r.spec_rows_source in (SOURCE_UNDECLARED, SOURCE_MALFORMED)
            ),
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="repository root to scan (default: this script's repo)",
    )
    ap.add_argument(
        "--spec",
        type=Path,
        default=None,
        help="path to target-spec.md (default: <repo-root>/spec/target-spec.md)",
    )
    ap.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the report here instead of stdout",
    )
    args = ap.parse_args(argv)

    repo_root = args.repo_root.resolve()
    spec_path = args.spec or (repo_root / "spec" / "target-spec.md")

    spec_rows = parse_spec_rows(spec_path)
    records = discover_evidence(repo_root)
    data = build_report(spec_rows, records, repo_root=repo_root)

    output = render_markdown(data) if args.format == "markdown" else render_json(data)

    if args.out:
        args.out.write_text(output)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
