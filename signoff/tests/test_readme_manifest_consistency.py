#!/usr/bin/env python3
"""
Unit tests for readme-manifest-consistency check.

Tests that the check correctly:
1. Passes when README cites the same record as manifest
2. Fails when README cites a stale/different record
3. Does not false-positive on historical references
"""

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


if __name__ == "__main__":
    unittest.main()
