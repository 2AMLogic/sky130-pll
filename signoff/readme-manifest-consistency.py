#!/usr/bin/env python3
"""
Verify that the prose about this block's T1 verdict agrees with the manifest
and the rendered report, rather than drifting from them.

Four checks, none of which needs `klt`:

1. **Item-3 record IDs.** Every layout record ID the README cites from the
   block the manifest's item 3 cites must be that item's record, except
   citations whose line carries the explicit
   ``<!-- signoff-historical-record -->`` marker. This is the
   README<->manifest half of the gap that run-signoff.sh's guard 2 does NOT
   cover (guard 2 checks manifest<->LATEST only).
2. **Met count and block kind.** Every ``**N of M T1 rows met**`` phrase in
   ``signoff/README.md``, the root ``README.md`` and ``docs/t1-gap.md`` must
   equal ``signoff/tier-report.json``'s ``t1_met_count`` and its number of T1
   rows, and every ``kind: "analog|digital|mixed-signal"`` phrase must equal
   the manifest's block ``kind``. (Each file is skipped if it does not exist.)
3. **Item-8 disclosure.** When the manifest cites a ``"kind": "generic"``
   envelope for item 8, that envelope's ``summary`` must name every spec row
   the cited characterization report itself records as FAIL (in a sentence
   that says FAIL) and every row it records no evidence for (in a sentence
   that says "no evidence"). A generic envelope asserts ``status: "pass"``
   over the whole report, so the summary is the only place the rows that
   report does *not* pass are disclosed -- and a regenerated report that
   adds a FAIL row must not leave a summary that silently omits it.
4. **No full pin literals in prose.** ``signoff/README.md`` must not
   restate any full 64-hex ``sha256:`` literal. The manifest and the cited
   evidence envelopes are the authoritative holders of pin values; every
   hand-restated copy in this README has gone stale on a re-pin (two of
   the three restatements were already wrong when this check was added).
   Truncated illustrative literals (``sha256:xxxxxxxx…``, the recorded
   tamper-experiment output) do not match, so no allowlist is needed.

Exit codes:
  0  All checks pass
  1  A check failed, or an input it needs is unreadable
"""

import json
import pathlib
import re
import sys


def main():
    repo_root = pathlib.Path(__file__).parent.parent
    manifest_path = repo_root / "signoff" / "block-manifest.json"
    readme_path = repo_root / "signoff" / "README.md"

    # Read the manifest to find what record ID is cited for item 3
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as exc:
        print(f"error: cannot read manifest {manifest_path}: {exc}", file=sys.stderr)
        return 1

    # Read the README
    try:
        readme_text = readme_path.read_text()
    except OSError as exc:
        print(f"error: cannot read {readme_path}: {exc}", file=sys.stderr)
        return 1

    try:
        errors = check_item3_records(manifest, readme_text)
    except ManifestShapeError as exc:
        print(
            "error: cannot extract a record ID from the manifest's item-3 "
            "evidence:",
            file=sys.stderr,
        )
        print(f"  {exc}", file=sys.stderr)
        print(
            "\nUpdate the manifest's item 3 evidence file to a "
            "layout/<block>/reports/<record-id>/... path.",
            file=sys.stderr,
        )
        return 1

    if errors:
        print("error: README record IDs do not match the manifest:", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nUpdate README.md to cite the record the manifest's item 3 "
            "evidence names, or update the manifest. If the mismatching "
            "citation is a deliberate historical reference, put "
            f"{HISTORICAL_RECORD_MARKER} back on its citing line.",
            file=sys.stderr,
        )
        return 1

    errors = check_counts_and_kind(repo_root, manifest, readme_text)
    if errors:
        print(
            "error: prose disagrees with signoff/tier-report.json or the manifest:",
            file=sys.stderr,
        )
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nThe rendered report is the verdict of record; update the prose to "
            "match it (re-render first with `bash signoff/run-signoff.sh` if the "
            "manifest changed).",
            file=sys.stderr,
        )
        return 1

    errors = check_item8_disclosure(repo_root, manifest)
    if errors:
        print(
            "error: the item-8 generic envelope does not disclose what its "
            "characterization report records:",
            file=sys.stderr,
        )
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nName every FAIL row in a sentence that says FAIL and every "
            "no-evidence row in a sentence that says \"no evidence\" -- the "
            "envelope's status: pass does not cover them (signoff/README.md).",
            file=sys.stderr,
        )
        return 1

    errors = check_no_pin_literals(readme_text)
    if errors:
        print(
            "error: signoff/README.md restates a full pin value as a literal:",
            file=sys.stderr,
        )
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nDo not restate pin values in prose: a restated copy cannot be "
            "checked against anything and has gone stale on every re-pin. "
            "Point at the authoritative field instead -- the manifest's "
            "per-item content_hash or the cited envelope's "
            "provenance.*.content_hash -- and state the invariant (guard 1 "
            "re-hashes the artifact from its live bytes on every run).",
            file=sys.stderr,
        )
        return 1

    return 0


# An HTML comment: invisible in rendered Markdown, so marking a citation
# does not change what a reader sees, and greppable, so the historical
# exemption is a deliberate declaration rather than a side effect of the
# surrounding prose.
HISTORICAL_RECORD_MARKER = "<!-- signoff-historical-record -->"


class ManifestShapeError(Exception):
    """The manifest's item-3 evidence path is not shaped as
    ``layout/<block>/reports/<record-id>/...``, so check 1 cannot extract the
    record ID to compare README citations against. This is a manifest-shape
    fault, not a README disagreement: the caller reports it under its own
    header with a manifest-directed remediation."""


def check_item3_records(manifest, readme_text):
    """Check 1: every layout record ID the README cites must be the record
    the manifest actually cites for item 3, except citations whose line
    carries ``HISTORICAL_RECORD_MARKER`` (a deliberate historical citation).

    Only records of the block item 3 cites are compared, so a sibling
    block's citations can never be matched against item 3's record.

    Raises ``ManifestShapeError`` when the item-3 evidence path carries no
    record ID, before any README comparison happens.
    """
    item3_evidence = manifest.get("evidence", {}).get("3", {})
    if isinstance(item3_evidence, dict):
        item3_file = item3_evidence.get("file", "")
    else:
        # Might be a string (old format)
        item3_file = item3_evidence if isinstance(item3_evidence, str) else ""

    # Record ID and block directory from the item-3 path:
    # layout/<block>/reports/<record-id>/...
    match = re.match(r"^layout/([^/]+)/reports/([^/]+)/", item3_file)
    if not match:
        raise ManifestShapeError(
            f"cannot extract record ID from manifest item 3 evidence: {item3_file}"
        )
    block = match.group(1)
    manifest_record_id = match.group(2)

    # Record IDs are timestamps: YYYYMMDD-HHMMSS-<hex>
    record_pattern = re.compile(
        rf"`layout/{re.escape(block)}/reports/(\d{{8}}-\d{{6}}-[a-f0-9]+)/"
    )

    errors = []
    for line in readme_text.splitlines():
        if HISTORICAL_RECORD_MARKER in line:
            continue
        for record_id in record_pattern.findall(line):
            if record_id != manifest_record_id:
                errors.append(
                    f"README mentions record {record_id}, but manifest item 3 "
                    f"cites {manifest_record_id}"
                )
    return errors


MET_COUNT_RE = re.compile(r"\*\*(\d+) of (\d+) T1 rows met\*\*")
# Block kinds only -- `kind: "yield"`/`kind: "generic"` are evidence kinds a
# document may legitimately quote, and say nothing about the block.
KIND_RE = re.compile(r'`kind: "(analog|digital|mixed-signal)"`')


def check_counts_and_kind(repo_root, manifest, readme_text):
    """Check 2: met-count and block-kind phrases against the report/manifest."""
    errors = []
    docs = {"signoff/README.md": readme_text}
    for name in ("README.md", "docs/t1-gap.md"):
        path = repo_root / name
        if path.is_file():
            docs[name] = path.read_text()

    report_path = repo_root / "signoff" / "tier-report.json"
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text())
        except ValueError as exc:
            return [f"signoff/tier-report.json is unreadable ({exc})"]
        met = report.get("t1_met_count")
        rows = sum(1 for item in report.get("items", []) if item.get("tier") == "T1")
        for name, text in docs.items():
            for match in MET_COUNT_RE.finditer(text):
                said = (int(match.group(1)), int(match.group(2)))
                if said != (met, rows):
                    errors.append(
                        f"{name} says '{match.group(0)}', but "
                        f"signoff/tier-report.json renders {met} of {rows}"
                    )

    kind = manifest.get("kind")
    for name, text in docs.items():
        for match in KIND_RE.finditer(text):
            if match.group(1) != kind:
                errors.append(
                    f"{name} says {match.group(0)}, but the manifest declares "
                    f'kind "{kind}"'
                )
    return errors


SPEC_ROW_RE = re.compile(r"^\|\s*(\d+)?\s*\|")
ROW_LIST_RE = re.compile(r"\brows? (\d+(?:(?:,? and |, )\d+)*)")


def report_row_states(report_text):
    """Map each spec row of a characterization report's per-spec-row table to
    ``(has_fail, has_no_evidence)``.

    The table (``measurements/aggregate.py``'s rendering) starts each spec
    row with its row number and lists further evidence records for the same
    row on continuation lines whose row cell is blank. Columns: Row,
    Parameter, target, Evidence, Verdict, Citation.
    """
    states = {}
    in_table = False
    current = None
    for line in report_text.splitlines():
        if line.startswith("## "):
            in_table = line.strip() == "## Per-spec-row summary"
            continue
        if not in_table or not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5 or cells[0] == "Row":
            continue
        if cells[0]:
            if not cells[0].isdigit():
                continue
            current = int(cells[0])
            states.setdefault(current, [False, False])
        if current is None:
            continue
        if cells[4] == "FAIL":
            states[current][0] = True
        if cells[3] == "No evidence":
            states[current][1] = True
    return {row: tuple(state) for row, state in states.items()}


def rows_named(sentences):
    named = set()
    for sentence in sentences:
        for match in ROW_LIST_RE.finditer(sentence):
            named.update(int(n) for n in re.findall(r"\d+", match.group(1)))
    return named


def generic_input_path(envelope):
    """The repo-relative artifact a generic envelope names in
    ``provenance.input.path`` (a string, or ``{"path": ..., "scope": "repo"}``
    -- the opt-in field klayout-tools#2403 added), or None."""
    provenance = envelope.get("provenance")
    input_block = provenance.get("input") if isinstance(provenance, dict) else None
    named = input_block.get("path") if isinstance(input_block, dict) else None
    if isinstance(named, dict) and named.get("scope") == "repo":
        named = named.get("path")
    if not isinstance(named, str) or not named:
        return None
    parts = pathlib.PurePosixPath(named)
    if parts.is_absolute() or ".." in parts.parts:
        return None
    return named


def check_item8_disclosure(repo_root, manifest):
    """Check 3: an item-8 generic envelope's summary discloses the report's
    FAIL and no-evidence rows."""
    errors = []
    for key, entry in (manifest.get("evidence") or {}).items():
        if key.split(".", 1)[0] != "8":
            continue
        path = entry.get("file") if isinstance(entry, dict) else entry
        if not isinstance(path, str):
            continue
        try:
            envelope = json.loads((repo_root / path).read_text())
        except (OSError, ValueError) as exc:
            errors.append(f"item {key}: {path} is unreadable ({exc})")
            continue
        if envelope.get("kind") != "generic":
            continue
        source = generic_input_path(envelope)
        summary = envelope.get("summary")
        if source is None:
            errors.append(
                f"item {key}: {path} names no repo-relative provenance.input.path report"
            )
            continue
        if not isinstance(summary, str) or not summary:
            errors.append(f"item {key}: {path} has no 'summary' to disclose rows in")
            continue
        try:
            report_text = (repo_root / source).read_text()
        except OSError as exc:
            errors.append(f"item {key}: cited report {source} is unreadable ({exc})")
            continue
        states = report_row_states(report_text)
        if not states:
            errors.append(
                f"item {key}: {source} has no parseable per-spec-row summary table"
            )
            continue
        sentences = re.split(r"(?<=\.)\s+", summary)
        fail_named = rows_named(s for s in sentences if "FAIL" in s)
        none_named = rows_named(s for s in sentences if "no evidence" in s.lower())
        fail_rows = sorted(row for row, (fail, _) in states.items() if fail)
        none_rows = sorted(row for row, (_, none) in states.items() if none)
        missing_fail = [row for row in fail_rows if row not in fail_named]
        missing_none = [row for row in none_rows if row not in none_named]
        if missing_fail:
            errors.append(
                f"item {key}: {source} records FAIL against rows {fail_rows}; "
                f"{path}'s summary does not name {missing_fail} as FAIL"
            )
        if missing_none:
            errors.append(
                f"item {key}: {source} records no evidence for rows {none_rows}; "
                f"{path}'s summary does not name {missing_none} as no-evidence"
            )
    return errors


# A full-length pin literal: `sha256:` followed by exactly 64 lowercase hex
# digits with no further hex digit after it. This is the shape of every
# machine-held pin in this repo (the manifest's per-item `content_hash`, an
# envelope's `provenance.*.content_hash`), so its presence in README prose
# is a hand-maintained restatement of a value the machine files hold more
# reliably. The regex is case-sensitive (every recorded pin is lowercase,
# as `sha256sum` emits) and the lookahead makes it exactly 64: 63- and
# 65-hex runs do not match. Truncated illustrative literals -- the
# recorded tamper-experiment output, `sha256:xxxxxxxx…` -- never reach 64
# digits and pass untouched, so no allowlist is needed.
PIN_LITERAL_RE = re.compile(r"sha256:[0-9a-f]{64}(?![0-9a-f])")


def check_no_pin_literals(readme_text):
    """Check 4: README prose must not restate a full pin value as a literal.

    The manifest and the evidence envelopes are the authoritative holders
    of pin values; a restated copy cannot be checked against anything and
    has gone stale on every re-pin cycle so far. Prose should point at the
    authoritative field instead and state the invariant (guard 1 re-hashes
    the artifact from its live bytes on every run).

    Not caught by design: a literal split across a line wrap (not the shape
    any recorded pin takes, and not greppable either), uppercase-hex
    literals, and hex runs of any length other than exactly 64. See
    ``PIN_LITERAL_RE``.
    """
    errors = []
    for lineno, line in enumerate(readme_text.splitlines(), start=1):
        for match in PIN_LITERAL_RE.finditer(line):
            errors.append(
                f"line {lineno} restates a full pin literal ({match.group(0)})"
            )
    return errors


if __name__ == "__main__":
    sys.exit(main())
