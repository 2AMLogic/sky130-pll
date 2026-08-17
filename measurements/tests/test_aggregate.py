#!/usr/bin/env python3
"""Unit tests for measurements/aggregate.py's evidence-record parsing and
rollup logic (issue #22). No PDK, ngspice, xschem, or klt required.

    python3 -m unittest discover -s measurements/tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

MEASUREMENTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MEASUREMENTS_DIR))

import aggregate  # noqa: E402


SPEC_FIXTURE = """\
# fixture spec

## Summary table

| # | Parameter | DRAFT target (starting point) | Source | sky130 open question |
|---|---|---|---|---|
| 0 | [Supply flavor](#supply-flavor) | 1.8 V core -- **RATIFIED** | sky130 core device menu | settled |
| 1 | [Lock time](#lock-time) | < 100 us | gf180-pll row 9 | re-verify |
| 2 | [Power](#power) | a budget, TBD | gf180-pll row 10 | re-budget |
"""


SIM_RECORD_FIXTURE = """\
# Record 20260814-022011-dcd6160

- **Record ID**: 20260814-022011-dcd6160
- **Claim**: harness self-test -- proves the plumbing works end to end.
- **Netlist provenance**: schematic, SHA-256 `deadbeef`
- **Environment provenance**:
  - PDK: volare `sky130A`
- **Corner matrix run**:
  - Total points: 27
- **Methodology / criteria / limitations**:
  - Per-point criterion: ok
- **Result**:

  | Corner | Temp (C) | Supply (V) | Verdict | Detail |
  |---|---|---|---|---|
  | tt | 27 | 1.80 | PASS | ok |

  - **Overall: PASS** (27/27 points passed)
- **Links**:
  - Testbench: `sim/pdk-smoke/testbench/`
- **Timestamp / author**: 2026-08-14T02:30:11Z, agent-builder
- **Supersedes**: (none -- first record for this claim)
"""


SIM_RECORD_WITH_SPEC_ROW_FIXTURE = SIM_RECORD_FIXTURE.replace(
    "- **Supersedes**: (none -- first record for this claim)",
    "- **Spec row(s)**: 1, 2\n- **Supersedes**: (none -- first record for this claim)",
)


SIM_RECORD_FAIL_FIXTURE = """\
# Record 20260815-000000-cafef00

- **Record ID**: 20260815-000000-cafef00
- **Claim**: a claim that failed one corner.
- **Result**:

  - **Overall: FAIL** (26/27 points passed)
- **Timestamp / author**: 2026-08-15T00:00:00Z, agent-builder
- **Supersedes**: (none -- first record for this claim)
"""


def _sim_supersedes(record_id_superseded: str) -> str:
    return SIM_RECORD_FIXTURE.replace(
        "20260814-022011-dcd6160", "20260901-000000-1234567", 1
    ).replace(
        "- **Supersedes**: (none -- first record for this claim)",
        f"- **Supersedes**: `{record_id_superseded}`",
    )


LAYOUT_RECORD_FIXTURE = """\
# Layout DRC/LVS record: 20260814-020940-aa2de71

Trivial-cell proof of the `klt`-driven DRC/LVS flow -- not PLL-block layout.

## Overall verdict: PASS

- [x] DRC on trivial_mos_array is clean
- [x] LVS matches the known-good reference

## Flow

1. `klt gen mos_array`

## Provenance

- Record ID: `20260814-020940-aa2de71`
"""


LAYOUT_RECORD_FAIL_FIXTURE = """\
# Layout DRC/LVS record: 20260901-000000-abcdef0

A layout record with one failing check.

## Overall verdict: FAIL

- [x] DRC on trivial_mos_array is clean
- [ ] LVS matches the known-good reference

## Provenance

- Record ID: `20260901-000000-abcdef0`
"""


class ParseSpecRowsTests(unittest.TestCase):
    def test_parses_number_parameter_anchor_and_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = Path(tmp) / "target-spec.md"
            spec_path.write_text(SPEC_FIXTURE)
            rows = aggregate.parse_spec_rows(spec_path)

        self.assertEqual([r.number for r in rows], [0, 1, 2])
        self.assertEqual(rows[1].parameter, "Lock time")
        self.assertEqual(rows[1].anchor, "lock-time")
        self.assertEqual(rows[1].draft_target, "< 100 us")

    def test_rows_sorted_by_number_even_if_file_is_not(self):
        shuffled = SPEC_FIXTURE.replace(
            "| 0 | [Supply flavor]", "| 9 | [Supply flavor]"
        )
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = Path(tmp) / "target-spec.md"
            spec_path.write_text(shuffled)
            rows = aggregate.parse_spec_rows(spec_path)
        self.assertEqual([r.number for r in rows], [1, 2, 9])


class ParseSimRecordTests(unittest.TestCase):
    def _write(self, tmp: str, text: str, slug: str = "pdk-smoke") -> Path:
        repo_root = Path(tmp)
        records_dir = repo_root / "sim" / slug / "records"
        records_dir.mkdir(parents=True)
        record_id = "20260814-022011-dcd6160" if "cafef00" not in text else "20260815-000000-cafef00"
        path = records_dir / f"{record_id}.md"
        path.write_text(text)
        return repo_root, path

    def test_extracts_record_id_claim_verdict_and_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, path = self._write(tmp, SIM_RECORD_FIXTURE)
            rec = aggregate.parse_sim_record(path, repo_root=repo_root)

        self.assertEqual(rec.record_id, "20260814-022011-dcd6160")
        self.assertEqual(rec.kind, "sim")
        self.assertEqual(rec.block, "pdk-smoke")
        self.assertIn("harness self-test", rec.claim)
        self.assertEqual(rec.verdict, "PASS")
        self.assertEqual(rec.detail, "27/27 points passed")
        self.assertEqual(rec.spec_rows, [])
        self.assertIsNone(rec.supersedes)
        self.assertEqual(
            rec.path.as_posix(), "sim/pdk-smoke/records/20260814-022011-dcd6160.md"
        )

    def test_fail_verdict_and_detail_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, path = self._write(tmp, SIM_RECORD_FAIL_FIXTURE)
            rec = aggregate.parse_sim_record(path, repo_root=repo_root)

        self.assertEqual(rec.verdict, "FAIL")
        self.assertEqual(rec.detail, "26/27 points passed")

    def test_spec_row_citation_is_parsed_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, path = self._write(tmp, SIM_RECORD_WITH_SPEC_ROW_FIXTURE)
            rec = aggregate.parse_sim_record(path, repo_root=repo_root)
        self.assertEqual(rec.spec_rows, [1, 2])

    def test_supersedes_reference_is_parsed(self):
        text = _sim_supersedes("20260814-022011-dcd6160")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            records_dir = repo_root / "sim" / "pdk-smoke" / "records"
            records_dir.mkdir(parents=True)
            path = records_dir / "20260901-000000-1234567.md"
            path.write_text(text)
            rec = aggregate.parse_sim_record(path, repo_root=repo_root)
        self.assertEqual(rec.supersedes, "20260814-022011-dcd6160")

    def test_first_record_supersedes_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, path = self._write(tmp, SIM_RECORD_FIXTURE)
            rec = aggregate.parse_sim_record(path, repo_root=repo_root)
        self.assertIsNone(rec.supersedes)


class ParseLayoutRecordTests(unittest.TestCase):
    def _write(self, tmp: str, text: str, record_id: str, block: str = "trivial-cell") -> tuple[Path, Path]:
        repo_root = Path(tmp)
        report_dir = repo_root / "layout" / block / "reports" / record_id
        report_dir.mkdir(parents=True)
        path = report_dir / "record.md"
        path.write_text(text)
        return repo_root, path

    def test_extracts_id_from_directory_claim_and_checklist_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, path = self._write(
                tmp, LAYOUT_RECORD_FIXTURE, "20260814-020940-aa2de71"
            )
            rec = aggregate.parse_layout_record(path, repo_root=repo_root)

        self.assertEqual(rec.record_id, "20260814-020940-aa2de71")
        self.assertEqual(rec.kind, "layout")
        self.assertEqual(rec.block, "trivial-cell")
        self.assertIn("Trivial-cell proof", rec.claim)
        self.assertEqual(rec.verdict, "PASS")
        self.assertEqual(rec.detail, "2/2 checks passed")
        self.assertEqual(rec.spec_rows, [])

    def test_fail_verdict_and_partial_checklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root, path = self._write(
                tmp, LAYOUT_RECORD_FAIL_FIXTURE, "20260901-000000-abcdef0"
            )
            rec = aggregate.parse_layout_record(path, repo_root=repo_root)

        self.assertEqual(rec.verdict, "FAIL")
        self.assertEqual(rec.detail, "1/2 checks passed")


class SupersessionTests(unittest.TestCase):
    def test_sim_record_named_in_a_newer_records_supersedes_field_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            records_dir = repo_root / "sim" / "pdk-smoke" / "records"
            records_dir.mkdir(parents=True)
            (records_dir / "20260814-022011-dcd6160.md").write_text(SIM_RECORD_FIXTURE)
            (records_dir / "20260901-000000-1234567.md").write_text(
                _sim_supersedes("20260814-022011-dcd6160")
            )
            records = aggregate.discover_evidence(repo_root)
            superseded = aggregate.compute_superseded_ids(repo_root, records)

        self.assertIn("20260814-022011-dcd6160", superseded)
        self.assertNotIn("20260901-000000-1234567", superseded)

    def test_layout_record_not_named_by_latest_pointer_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            reports_dir = repo_root / "layout" / "trivial-cell" / "reports"
            for record_id, text in (
                ("20260814-020940-aa2de71", LAYOUT_RECORD_FIXTURE),
                (
                    "20260901-000000-abcdef0",
                    LAYOUT_RECORD_FIXTURE.replace(
                        "20260814-020940-aa2de71", "20260901-000000-abcdef0"
                    ),
                ),
            ):
                d = reports_dir / record_id
                d.mkdir(parents=True)
                (d / "record.md").write_text(text)
            (reports_dir / "LATEST").write_text("20260901-000000-abcdef0\n")

            records = aggregate.discover_evidence(repo_root)
            superseded = aggregate.compute_superseded_ids(repo_root, records)

        self.assertIn("20260814-020940-aa2de71", superseded)
        self.assertNotIn("20260901-000000-abcdef0", superseded)

    def test_missing_latest_pointer_leaves_all_layout_records_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            report_dir = (
                repo_root / "layout" / "trivial-cell" / "reports" / "20260814-020940-aa2de71"
            )
            report_dir.mkdir(parents=True)
            (report_dir / "record.md").write_text(LAYOUT_RECORD_FIXTURE)

            records = aggregate.discover_evidence(repo_root)
            superseded = aggregate.compute_superseded_ids(repo_root, records)

        self.assertEqual(superseded, set())


class BuildReportTests(unittest.TestCase):
    def _spec_rows(self):
        return [
            aggregate.SpecRow(0, "Supply flavor", "supply-flavor", "1.8 V core"),
            aggregate.SpecRow(1, "Lock time", "lock-time", "< 100 us"),
        ]

    def _rec(self, spec_rows=(), record_id="20260101-000000-abcdef0") -> aggregate.EvidenceRecord:
        return aggregate.EvidenceRecord(
            record_id=record_id,
            kind="sim",
            block="some-block",
            claim="a claim",
            verdict="PASS",
            detail="ok",
            spec_rows=list(spec_rows),
            path=Path(f"sim/some-block/records/{record_id}.md"),
        )

    def test_row_with_no_matching_evidence_has_empty_list(self):
        data = aggregate.build_report(self._spec_rows(), [], repo_root=Path("."))
        self.assertEqual(data.rows[0], [])
        self.assertEqual(data.rows[1], [])
        self.assertEqual(data.unmapped, [])

    def test_record_citing_a_row_is_attached_to_that_row_not_unmapped(self):
        rec = self._rec(spec_rows=[1])
        data = aggregate.build_report(self._spec_rows(), [rec], repo_root=Path("."))
        self.assertEqual(data.rows[1], [rec])
        self.assertEqual(data.rows[0], [])
        self.assertEqual(data.unmapped, [])

    def test_record_citing_no_row_is_unmapped(self):
        rec = self._rec(spec_rows=[])
        data = aggregate.build_report(self._spec_rows(), [rec], repo_root=Path("."))
        self.assertEqual(data.unmapped, [rec])
        self.assertEqual(data.rows[0], [])
        self.assertEqual(data.rows[1], [])

    def test_record_citing_an_unknown_row_number_is_unmapped_not_dropped(self):
        # Defends "no silent omission": a citation to a row this spec
        # snapshot doesn't have must still surface somewhere.
        rec = self._rec(spec_rows=[99])
        data = aggregate.build_report(self._spec_rows(), [rec], repo_root=Path("."))
        self.assertEqual(data.unmapped, [rec])


class RenderMarkdownTests(unittest.TestCase):
    def test_row_with_no_evidence_renders_the_literal_marker(self):
        spec_rows = [aggregate.SpecRow(0, "Supply flavor", "supply-flavor", "1.8 V core")]
        data = aggregate.build_report(spec_rows, [], repo_root=Path("."))
        out = aggregate.render_markdown(data)
        self.assertIn("| 0 | Supply flavor | 1.8 V core | No evidence | -- | -- |", out)

    def test_mapped_evidence_renders_verdict_and_citation(self):
        spec_rows = [aggregate.SpecRow(1, "Lock time", "lock-time", "< 100 us")]
        rec = aggregate.EvidenceRecord(
            record_id="20260101-000000-abcdef0",
            kind="sim",
            block="lock-time-campaign",
            claim="a claim",
            verdict="PASS",
            detail="ok",
            spec_rows=[1],
            path=Path("sim/lock-time-campaign/records/20260101-000000-abcdef0.md"),
        )
        data = aggregate.build_report(spec_rows, [rec], repo_root=Path("."))
        out = aggregate.render_markdown(data)
        self.assertIn("sim/lock-time-campaign (20260101-000000-abcdef0)", out)
        self.assertIn("PASS", out)
        self.assertIn(
            "`sim/lock-time-campaign/records/20260101-000000-abcdef0.md`", out
        )

    def test_json_round_trips(self):
        import json

        spec_rows = [aggregate.SpecRow(0, "Supply flavor", "supply-flavor", "1.8 V core")]
        data = aggregate.build_report(spec_rows, [], repo_root=Path("."))
        payload = json.loads(aggregate.render_json(data))
        self.assertEqual(payload["rows"][0]["number"], 0)
        self.assertEqual(payload["rows"][0]["evidence"], [])
        self.assertEqual(payload["scan_summary"]["total_scanned"], 0)


class RealRepoSmokeTest(unittest.TestCase):
    """Runs the aggregator against this repo's actual checked-in
    harness-plumbing evidence (sim/pdk-smoke, layout/trivial-cell) -- the
    automated counterpart of issue #22's manual test-plan item. Neither
    record carries a PLL spec-row claim, so this proves the rollup
    mechanism, not a PLL result."""

    def test_aggregates_real_evidence_without_error(self):
        repo_root = MEASUREMENTS_DIR.parent
        spec_rows = aggregate.parse_spec_rows(repo_root / "spec" / "target-spec.md")
        records = aggregate.discover_evidence(repo_root)
        data = aggregate.build_report(spec_rows, records, repo_root=repo_root)

        self.assertGreaterEqual(len(spec_rows), 19)
        self.assertGreaterEqual(len(records), 2)  # pdk-smoke + trivial-cell, at least

        blocks = {(r.kind, r.block) for r in records}
        self.assertIn(("sim", "pdk-smoke"), blocks)
        self.assertIn(("layout", "trivial-cell"), blocks)

        markdown = aggregate.render_markdown(data)
        self.assertIn("# PLL characterization report", markdown)
        self.assertIn("No evidence", markdown)  # no record cites a spec row yet

        # render_json must not raise and must be valid JSON.
        import json

        json.loads(aggregate.render_json(data))


if __name__ == "__main__":
    unittest.main()
