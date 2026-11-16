#!/usr/bin/env python3
"""Tests for scripts/git_status.py, the shared repo-dirtiness classifier.

`is_dirty` answers "was anything modified/untracked other than this run's
own outputs?" for two independent consumers: sim/harness/report.py passes
its record-output prefixes as a `tuple[str, ...]`, while layout's
`render_common.git_provenance` passes its report directory as a single
`str`. `str.startswith` accepts either shape natively, so every behavioral
case below runs against both spellings with `subTest` and must read the same
verdict -- the shape a caller uses must not change the answer.

    python3 -m unittest discover -s scripts/tests -v
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "git_status", ROOT / "scripts" / "git_status.py"
)
git_status = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(git_status)

# The two real consumers' spellings of the same idea: layout's single
# report-directory str vs sim's tuple of record-output prefixes.
LAYOUT_PREFIX = "layout/trivial-cell/reports/20260101-000000-abc1234/"
SIM_PREFIXES = (
    "sim/pdk-smoke/corners/20260101-000000-abc1234/",
    "sim/pdk-smoke/records/20260101-000000-abc1234.md",
    "sim/pdk-smoke/netlist-snapshots/20260101-000000-abc1234.spice",
)


class IsDirtyTests(unittest.TestCase):
    """The record `dirty` flag has to mean "the code that produced this
    evidence differed from the named commit": the run's own outputs are new
    files by construction, so counting them would stamp every record dirty
    and make the flag worthless."""

    def assert_same_verdict(self, layout_status: str, sim_status: str, expected: bool):
        for shape, prefixes, status in (
            ("str: layout's report dir", LAYOUT_PREFIX, layout_status),
            ("tuple: sim's record outputs", SIM_PREFIXES, sim_status),
        ):
            with self.subTest(ignore_prefixes=shape):
                self.assertEqual(git_status.is_dirty(status, prefixes), expected)

    def test_a_clean_tree_is_not_dirty(self):
        self.assert_same_verdict("", "", False)

    def test_this_runs_own_outputs_do_not_count_as_dirty(self):
        layout_status = (
            f"?? {LAYOUT_PREFIX}drc.json\n"
            f"?? {LAYOUT_PREFIX}record.md\n"
            f"?? {LAYOUT_PREFIX}trivial_mos_array.gds\n"
        )
        sim_status = "".join(f"?? {p}\n" for p in SIM_PREFIXES)
        self.assert_same_verdict(layout_status, sim_status, False)

    def test_a_modified_source_file_counts_as_dirty(self):
        # The flow code itself: an uncommitted edit to whatever produces the
        # evidence invalidates the record.
        self.assert_same_verdict(
            " M layout/bin/run-trivial-cell-flow.sh\n",
            " M sim/harness/runner.py\n",
            True,
        )

    def test_a_modified_testbench_or_reference_counts_as_dirty(self):
        # Inside the experiment directory but not a record output: editing
        # the DUT (sim) or the LVS reference the record compares against
        # (layout) absolutely changes what the evidence means.
        self.assert_same_verdict(
            " M layout/trivial-cell/reference.spice\n",
            " M sim/pdk-smoke/testbench/tb_pdk_smoke.sch\n",
            True,
        )

    def test_a_collapsed_parent_directory_counts_as_dirty(self):
        # git's DEFAULT porcelain output collapses a wholly untracked tree
        # to its parent ("?? sim/pdk-smoke/corners/"), which no per-record
        # prefix can match. Both consumers therefore pass
        # --untracked-files=all; this pins the conservative behavior if that
        # flag is ever dropped -- falsely dirty, never falsely clean.
        self.assert_same_verdict(
            "?? layout/trivial-cell/reports/\n",
            "?? sim/pdk-smoke/corners/\n",
            True,
        )

    def test_an_earlier_records_outputs_count_as_dirty(self):
        # A sibling record from a previous run matches the same directory
        # pattern but not this run's timestamped prefix: stale evidence is
        # not this run's output.
        self.assert_same_verdict(
            "?? layout/trivial-cell/reports/20251231-235959-def5678/record.md\n",
            "?? sim/pdk-smoke/records/20251231-235959-def5678.md\n",
            True,
        )

    def test_with_no_ignore_prefixes_everything_counts(self):
        # The default `()` ignores nothing: any entry at all is dirty.
        self.assertFalse(git_status.is_dirty(""))
        self.assertTrue(
            git_status.is_dirty("?? layout/trivial-cell/reports/r/record.md\n")
        )


class PorcelainPathsTests(unittest.TestCase):
    def test_rename_takes_the_new_path_and_quoting_is_stripped(self):
        cases = (
            (
                'R  sim/old.py -> sim/new.py\n?? "sim/spaced name.py"\n',
                ["sim/new.py", "sim/spaced name.py"],
            ),
            (
                'R  layout/a.py -> layout/b.py\n?? "layout/spaced name.py"\n',
                ["layout/b.py", "layout/spaced name.py"],
            ),
        )
        for status, expected in cases:
            with self.subTest(status=status):
                self.assertEqual(git_status.porcelain_paths(status), expected)


if __name__ == "__main__":
    unittest.main()
