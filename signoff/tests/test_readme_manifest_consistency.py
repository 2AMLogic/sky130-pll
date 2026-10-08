#!/usr/bin/env python3
"""
Unit tests for readme-manifest-consistency check.

Tests that the check correctly:
1. Passes when README cites the same record as manifest
2. Fails when README cites a stale/different record
3. Does not false-positive on historical references
4. Fails when a stated met count or block kind disagrees with the rendered
   report / manifest
5. Fails when item 8's generic envelope summary stops naming a row its
   characterization report records as FAIL or without evidence
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


class TestReadmeManifestConsistency(unittest.TestCase):
    """Test the readme-manifest-consistency.py check."""

    def setUp(self):
        """Create a temporary repo structure for testing."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_root = pathlib.Path(self.temp_dir.name)
        self.signoff_dir = self.repo_root / "signoff"
        self.signoff_dir.mkdir()

        # Create the check script symlink/copy
        script_src = pathlib.Path(__file__).parent.parent / "readme-manifest-consistency.py"
        self.script_path = self.signoff_dir / "readme-manifest-consistency.py"
        import shutil
        shutil.copy2(script_src, self.script_path)

    def tearDown(self):
        """Clean up temporary files."""
        self.temp_dir.cleanup()

    def _run_check(self):
        """Run the check script and return exit code."""
        result = subprocess.run(
            [sys.executable, str(self.script_path)],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr

    def test_check_passes_with_matching_record_id(self):
        """Test that check passes when README cites the manifest's record."""
        record_id = "20260924-041509-c53e7c4"

        # Create manifest with this record ID
        manifest = {
            "block": "sky130-pll",
            "kind": "mixed-signal",
            "evidence": {
                "3": {
                    "file": f"layout/pll/reports/{record_id}/drc.json",
                    "content_hash": "sha256:deadbeef",
                }
            },
        }
        (self.signoff_dir / "block-manifest.json").write_text(json.dumps(manifest))

        # Create README that cites this record ID
        readme = f"""
## Item 3 Section

Item 3 cites
`layout/pll/reports/{record_id}/drc.json` — some description.

The record's spot-check
`layout/pll/reports/{record_id}/route-spot-check/drc.json` also reports clean.
"""
        (self.signoff_dir / "README.md").write_text(readme)

        # Check should pass
        exit_code, stdout, stderr = self._run_check()
        self.assertEqual(exit_code, 0, f"Check should pass but got: {stderr}")

    def test_check_fails_with_stale_record_id(self):
        """Test that check fails when README cites stale/different record ID."""
        current_record = "20260924-041509-c53e7c4"
        stale_record = "20260923-084911-13ecfe9"

        # Create manifest with current record ID
        manifest = {
            "block": "sky130-pll",
            "kind": "mixed-signal",
            "evidence": {
                "3": {
                    "file": f"layout/pll/reports/{current_record}/drc.json",
                    "content_hash": "sha256:deadbeef",
                }
            },
        }
        (self.signoff_dir / "block-manifest.json").write_text(json.dumps(manifest))

        # Create README that cites stale record ID
        readme = f"""
## Item 3 Section

Item 3 cites
`layout/pll/reports/{stale_record}/drc.json` — some description.

The record's spot-check
`layout/pll/reports/{stale_record}/route-spot-check/drc.json` also reports clean.
"""
        (self.signoff_dir / "README.md").write_text(readme)

        # Check should fail
        exit_code, stdout, stderr = self._run_check()
        self.assertNotEqual(exit_code, 0, "Check should fail with stale record ID")
        self.assertIn(stale_record, stderr)
        self.assertIn(current_record, stderr)

    def test_check_ignores_historical_references(self):
        """Test that historical references don't cause false positives."""
        current_record = "20260924-041509-c53e7c4"
        historical_record = "20260906-195205-4a08c71"

        # Create manifest with current record ID
        manifest = {
            "block": "sky130-pll",
            "kind": "mixed-signal",
            "evidence": {
                "3": {
                    "file": f"layout/pll/reports/{current_record}/drc.json",
                    "content_hash": "sha256:deadbeef",
                }
            },
        }
        (self.signoff_dir / "block-manifest.json").write_text(json.dumps(manifest))

        # Create README that cites both current and historical record IDs
        readme = f"""
## Item 3 Section

Item 3 cites
`layout/pll/reports/{current_record}/drc.json` — current record.

Historical context:
An earlier, now-superseded record's own routed spot-check
(`layout/pll/reports/{historical_record}/route-spot-check/drc.json`,
cited by this block-manifest before issue #157's pin bump) shows the failure mode.
"""
        (self.signoff_dir / "README.md").write_text(readme)

        # Check should pass despite historical reference
        exit_code, stdout, stderr = self._run_check()
        self.assertEqual(exit_code, 0, f"Check should pass (ignoring historical refs) but got: {stderr}")

    def test_check_handles_missing_manifest(self):
        """Test that check fails gracefully with missing manifest."""
        # Create README without manifest
        readme = "`layout/pll/reports/20260924-041509-c53e7c4/drc.json`"
        (self.signoff_dir / "README.md").write_text(readme)

        exit_code, stdout, stderr = self._run_check()
        self.assertNotEqual(exit_code, 0)
        self.assertIn("manifest", stderr.lower())

    def test_check_handles_missing_readme(self):
        """Test that check fails gracefully with missing README."""
        # Create manifest without README
        manifest = {
            "block": "sky130-pll",
            "kind": "mixed-signal",
            "evidence": {
                "3": {
                    "file": "layout/pll/reports/20260924-041509-c53e7c4/drc.json",
                    "content_hash": "sha256:deadbeef",
                }
            },
        }
        (self.signoff_dir / "block-manifest.json").write_text(json.dumps(manifest))

        exit_code, stdout, stderr = self._run_check()
        self.assertNotEqual(exit_code, 0)
        self.assertIn("README", stderr)


RECORD_ID = "20260924-041509-c53e7c4"

# A miniature of measurements/aggregate.py's per-spec-row table: row 0 has no
# evidence, row 2 passes, row 8 fails on every record, row 9 has a FAIL and a
# PASS record (a continuation line with a blank row cell).
REPORT_MD = """# PLL characterization report

## Per-spec-row summary

| Row | Parameter | DRAFT target | Evidence | Verdict | Citation |
|---|---|---|---|---|---|
| 0 | Supply flavor | 1.8 V | No evidence | -- | -- |
| 2 | Output band | 10-200 MHz | sim/vco (a) | PASS | `a.md` |
| 8 | Lock time | < 100 us | sim/pll-lock (b) | FAIL | `b.md` |
| 9 | Period jitter | <= 1.0 % | sim/pll-lock (b) | FAIL | `b.md` |
|  |  |  | sim/pll-lock-mc (c) | PASS | `c.md` |

## Evidence found, not mapped to a spec row

| Kind | Block | Record | Claim | Verdict | Detail | Why unmapped | Citation |
|---|---|---|---|---|---|---|---|
| sim | x | 1 | harness | FAIL | 1/2 | none | `x.md` |
"""

COMPLETE_SUMMARY = (
    "Asserts only that the report is item 8's artifact. "
    "The report records FAIL against row 8 (lock time) and row 9 (jitter). "
    "It records no evidence for rows 0."
)


class TestCountsKindAndItem8Disclosure(unittest.TestCase):
    """Checks 2 and 3: met count, block kind, and item 8's envelope summary."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_root = pathlib.Path(self.temp_dir.name)
        (self.repo_root / "signoff" / "evidence").mkdir(parents=True)
        (self.repo_root / "measurements").mkdir()
        (self.repo_root / "docs").mkdir()
        import shutil
        script_src = pathlib.Path(__file__).parent.parent / "readme-manifest-consistency.py"
        self.script_path = self.repo_root / "signoff" / "readme-manifest-consistency.py"
        shutil.copy2(script_src, self.script_path)
        (self.repo_root / "measurements" / "report.md").write_text(REPORT_MD)
        self._write_report(met=3, rows=22)
        self._write_manifest(cite_item8=True)
        self._write_envelope(COMPLETE_SUMMARY)
        self._write_readme("**3 of 22 T1 rows met**", 'kind: "mixed-signal"')

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_report(self, met, rows):
        items = [{"tier": "T1", "id": n} for n in range(rows)]
        items.append({"tier": "T2", "id": 1})
        (self.repo_root / "signoff" / "tier-report.json").write_text(
            json.dumps({"t1_met_count": met, "items": items})
        )

    def _write_manifest(self, cite_item8, kind="mixed-signal"):
        evidence = {
            "3": {
                "file": f"layout/pll/reports/{RECORD_ID}/drc.json",
                "content_hash": "sha256:deadbeef",
            }
        }
        if cite_item8:
            evidence["8.analog"] = {
                "file": "signoff/evidence/characterization-report.json",
                "content_hash": "sha256:deadbeef",
            }
        (self.repo_root / "signoff" / "block-manifest.json").write_text(
            json.dumps({"block": "b", "kind": kind, "evidence": evidence})
        )

    def _write_envelope(self, summary):
        (self.repo_root / "signoff" / "evidence" / "characterization-report.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "generic",
                    "status": "pass",
                    "source": "measurements/report.md",
                    "summary": summary,
                    "provenance": {
                        "input": {
                            "content_hash": "sha256:deadbeef",
                            "path": {"path": "measurements/report.md", "scope": "repo"},
                        }
                    },
                }
            )
        )

    def _write_readme(self, count_phrase, kind_phrase):
        (self.repo_root / "signoff" / "README.md").write_text(
            f"Today the verdict is {count_phrase}.\n\n"
            f"`{kind_phrase}`, and an evidence kind such as `kind: \"yield\"` "
            "is not a block kind.\n\n"
            f"Item 3 cites `layout/pll/reports/{RECORD_ID}/drc.json`.\n"
        )

    def _run(self):
        result = subprocess.run(
            [sys.executable, str(self.script_path)],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stderr

    def test_consistent_inputs_pass(self):
        code, stderr = self._run()
        self.assertEqual(code, 0, stderr)

    def test_stale_met_count_in_signoff_readme_fails(self):
        self._write_readme("**2 of 22 T1 rows met**", 'kind: "mixed-signal"')
        code, stderr = self._run()
        self.assertEqual(code, 1)
        self.assertIn("'**2 of 22 T1 rows met**'", stderr)
        self.assertIn("renders 3 of 22", stderr)

    def test_stale_met_count_in_t1_gap_fails(self):
        (self.repo_root / "docs" / "t1-gap.md").write_text("Reads **1 of 22 T1 rows met**.")
        code, stderr = self._run()
        self.assertEqual(code, 1)
        self.assertIn("docs/t1-gap.md", stderr)

    def test_stale_met_count_in_root_readme_fails(self):
        (self.repo_root / "README.md").write_text("Reads **3 of 20 T1 rows met**.")
        code, stderr = self._run()
        self.assertEqual(code, 1)
        self.assertIn("README.md says '**3 of 20 T1 rows met**'", stderr)

    def test_stale_block_kind_fails(self):
        (self.repo_root / "docs" / "t1-gap.md").write_text('The block is `kind: "analog"`.')
        code, stderr = self._run()
        self.assertEqual(code, 1)
        self.assertIn('kind "mixed-signal"', stderr)

    def test_summary_missing_a_fail_row_fails(self):
        self._write_envelope(
            "The report records FAIL against row 8. It records no evidence for rows 0."
        )
        code, stderr = self._run()
        self.assertEqual(code, 1)
        self.assertIn("does not name [9] as FAIL", stderr)

    def test_fail_row_named_only_outside_a_fail_sentence_fails(self):
        self._write_envelope(
            "Row 9 is period jitter. The report records FAIL against row 8. "
            "It records no evidence for rows 0."
        )
        code, stderr = self._run()
        self.assertEqual(code, 1)
        self.assertIn("does not name [9] as FAIL", stderr)

    def test_summary_missing_a_no_evidence_row_fails(self):
        self._write_envelope("The report records FAIL against rows 8 and 9.")
        code, stderr = self._run()
        self.assertEqual(code, 1)
        self.assertIn("does not name [0] as no-evidence", stderr)

    def test_unmapped_table_fail_is_not_a_spec_row(self):
        # The second table's FAIL belongs to no spec row; the complete summary
        # above names nothing for it and still passes (test_consistent_inputs_pass).
        # A report that newly fails a spec row must be disclosed:
        (self.repo_root / "measurements" / "report.md").write_text(
            REPORT_MD.replace("| sim/vco (a) | PASS |", "| sim/vco (a) | FAIL |")
        )
        code, stderr = self._run()
        self.assertEqual(code, 1)
        self.assertIn("does not name [2] as FAIL", stderr)

    def test_no_item8_citation_skips_disclosure_check(self):
        self._write_manifest(cite_item8=False)
        self._write_envelope("says nothing")
        code, stderr = self._run()
        self.assertEqual(code, 0, stderr)

    def test_live_repo_envelope_names_every_fail_and_no_evidence_row(self):
        """The committed envelope against the committed report -- the same
        check `npm run check:ci` runs, pinned here so a regression in the
        parser cannot pass by finding no rows at all."""
        spec = importlib.util.spec_from_file_location(
            "consistency", pathlib.Path(__file__).parent.parent / "readme-manifest-consistency.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        repo = pathlib.Path(__file__).resolve().parents[2]
        states = module.report_row_states((repo / "measurements" / "report.md").read_text())
        self.assertIn(8, states)
        self.assertTrue(states[8][0], "row 8 (lock time) should read FAIL in the report")
        self.assertTrue(states[9][0], "row 9's deterministic records should read FAIL")
        manifest = json.loads((repo / "signoff" / "block-manifest.json").read_text())
        self.assertEqual(module.check_item8_disclosure(repo, manifest), [])


if __name__ == "__main__":
    unittest.main()
