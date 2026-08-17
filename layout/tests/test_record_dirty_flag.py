#!/usr/bin/env python3
"""Unit tests for render-record.py's repo-dirtiness classification.

The layout record stamps the repo commit it was produced at plus a `dirty`
flag. That flag has to mean "the flow that produced this evidence differed
from the named commit" -- if the run's own report directory counted, every
record would read dirty (the run just wrote those files) and the flag would
carry no information at all.

`layout/bin/` is not an importable package, so the module is loaded by path.

    python3 -m unittest discover -s layout/tests -v
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

RENDER_RECORD_PY = Path(__file__).resolve().parents[1] / "bin" / "render-record.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.git_status import porcelain_paths  # noqa: E402

_spec = importlib.util.spec_from_file_location("render_record", RENDER_RECORD_PY)
render_record = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_record)

REPORT_DIR = "layout/trivial-cell/reports/20260101-000000-abc1234/"


class DirtyFlagTests(unittest.TestCase):
    def test_clean_tree_is_not_dirty(self):
        self.assertFalse(render_record.is_dirty("", REPORT_DIR))

    def test_this_runs_own_report_dir_does_not_count_as_dirty(self):
        status = (
            f"?? {REPORT_DIR}drc.json\n"
            f"?? {REPORT_DIR}record.md\n"
            f"?? {REPORT_DIR}trivial_mos_array.gds\n"
        )
        self.assertFalse(render_record.is_dirty(status, REPORT_DIR))

    def test_modified_flow_script_counts_as_dirty(self):
        self.assertTrue(
            render_record.is_dirty(" M layout/bin/run-trivial-cell-flow.sh\n", REPORT_DIR)
        )

    def test_modified_reference_netlist_counts_as_dirty(self):
        # The LVS reference is the thing being compared against: an
        # uncommitted edit to it absolutely changes what the record means.
        self.assertTrue(
            render_record.is_dirty(" M layout/trivial-cell/reference.spice\n", REPORT_DIR)
        )

    def test_a_collapsed_parent_directory_counts_as_dirty(self):
        # git's DEFAULT porcelain output collapses a wholly untracked tree to
        # its parent ("?? layout/trivial-cell/reports/"), which no per-record
        # prefix can match. render-record.py therefore passes
        # --untracked-files=all; this test pins the conservative behavior if
        # that flag is ever dropped -- falsely dirty, never falsely clean.
        self.assertTrue(
            render_record.is_dirty("?? layout/trivial-cell/reports/\n", REPORT_DIR)
        )

    def test_an_earlier_report_dir_counts_as_dirty(self):
        status = "?? layout/trivial-cell/reports/20251231-235959-def5678/record.md\n"
        self.assertTrue(render_record.is_dirty(status, REPORT_DIR))

    def test_porcelain_paths_handles_renames_and_quoting(self):
        status = 'R  layout/a.py -> layout/b.py\n?? "layout/spaced name.py"\n'
        self.assertEqual(
            porcelain_paths(status),
            ["layout/b.py", "layout/spaced name.py"],
        )


if __name__ == "__main__":
    unittest.main()
