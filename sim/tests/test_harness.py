#!/usr/bin/env python3
"""Unit tests for sim/harness. No PDK and no ngspice/xschem required.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from harness import cli  # noqa: E402
from harness import corners  # noqa: E402
from harness import pdk as pdk_mod  # noqa: E402
from harness import report  # noqa: E402
from harness import runner  # noqa: E402
from scripts.git_status import porcelain_paths  # noqa: E402


class SupplyPointsTests(unittest.TestCase):
    def test_zero_tolerance_is_nominal_only(self):
        self.assertEqual(corners.supply_points(1.8, 0), [1.8])

    def test_ten_percent_tolerance_gives_three_points(self):
        pts = corners.supply_points(1.8, 0.1)
        self.assertEqual(pts, [1.62, 1.8, 1.98])


class PvtPointTests(unittest.TestCase):
    def test_corner_id_format(self):
        p = corners.PvtPoint(corner="ss", temp_c=-40.0, supply_v=1.62)
        self.assertEqual(p.corner_id, "ss_-40c_1.62v")

    def test_corner_id_integer_temp_has_no_trailing_dot(self):
        p = corners.PvtPoint(corner="tt", temp_c=27.0, supply_v=1.8)
        self.assertEqual(p.corner_id, "tt_27c_1.80v")


class DirtyFlagTests(unittest.TestCase):
    """The record's `dirty` flag has to mean "the code that produced this
    evidence differed from the named commit". The run's own outputs are new
    files by construction, so counting them would make every record dirty and
    the flag worthless."""

    RECORD_OUTPUTS = (
        "sim/pdk-smoke/corners/20260101-000000-abc1234/",
        "sim/pdk-smoke/records/20260101-000000-abc1234.md",
        "sim/pdk-smoke/netlist-snapshots/20260101-000000-abc1234.spice",
    )

    def test_clean_tree_is_not_dirty(self):
        self.assertFalse(report.is_dirty("", self.RECORD_OUTPUTS))

    def test_this_runs_own_outputs_do_not_count_as_dirty(self):
        status = (
            "?? sim/pdk-smoke/corners/20260101-000000-abc1234/\n"
            "?? sim/pdk-smoke/records/20260101-000000-abc1234.md\n"
            "?? sim/pdk-smoke/netlist-snapshots/20260101-000000-abc1234.spice\n"
        )
        self.assertFalse(report.is_dirty(status, self.RECORD_OUTPUTS))

    def test_modified_harness_source_counts_as_dirty(self):
        status = " M sim/harness/runner.py\n"
        self.assertTrue(report.is_dirty(status, self.RECORD_OUTPUTS))

    def test_modified_testbench_counts_as_dirty(self):
        # Same experiment directory as the record, but not a record output:
        # editing the DUT absolutely changes what the evidence means.
        status = " M sim/pdk-smoke/testbench/tb_pdk_smoke.sch\n"
        self.assertTrue(report.is_dirty(status, self.RECORD_OUTPUTS))

    def test_a_collapsed_parent_directory_counts_as_dirty(self):
        # git's DEFAULT porcelain output collapses a wholly untracked tree to
        # its parent ("?? sim/pdk-smoke/corners/"), which no per-record prefix
        # can match. git_info therefore passes --untracked-files=all; this
        # test pins the conservative behavior if that flag is ever dropped --
        # falsely dirty, never falsely clean.
        self.assertTrue(report.is_dirty("?? sim/pdk-smoke/corners/\n", self.RECORD_OUTPUTS))

    def test_an_earlier_records_outputs_count_as_dirty(self):
        status = "?? sim/pdk-smoke/records/20251231-235959-def5678.md\n"
        self.assertTrue(report.is_dirty(status, self.RECORD_OUTPUTS))

    def test_porcelain_paths_handles_renames_and_quoting(self):
        status = 'R  sim/old.py -> sim/new.py\n?? "sim/spaced name.py"\n'
        self.assertEqual(porcelain_paths(status), ["sim/new.py", "sim/spaced name.py"])


class BuildMatrixTests(unittest.TestCase):
    MANIFEST = {
        "process_corners": ["tt", "ss", "ff"],
        "temps_c": [-40, 27, 125],
        "supply_nominal": 1.8,
        "supply_tolerance": 0.1,
    }
    VALID_CORNERS = ("tt", "ss", "ff", "sf", "fs", "ll", "hh")

    def test_default_grid_is_full_cross_product(self):
        points = corners.build_matrix(self.MANIFEST, self.VALID_CORNERS)
        self.assertEqual(len(points), 3 * 3 * 3)

    def test_unknown_corner_from_pdk_json_rejected(self):
        with self.assertRaises(corners.CornerError):
            corners.build_matrix(
                self.MANIFEST, self.VALID_CORNERS, corners_override=["bogus"]
            )

    def test_override_may_pick_any_pdk_valid_corner(self):
        # "sf" is not in this manifest's own default list but is a valid
        # sky130 corner -- the harness patches corners generically (see
        # runner.patch_netlist), so an override is not restricted to the
        # manifest's own default set.
        points = corners.build_matrix(self.MANIFEST, self.VALID_CORNERS, corners_override=["sf"])
        self.assertEqual({p.corner for p in points}, {"sf"})

    def test_override_narrows_the_grid(self):
        points = corners.build_matrix(
            self.MANIFEST,
            self.VALID_CORNERS,
            corners_override=["tt"],
            temps_override=[27.0],
            supply_tol_override=0.0,
        )
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].corner_id, "tt_27c_1.80v")


class PatchNetlistTests(unittest.TestCase):
    MANIFEST = {
        "corner_pattern": r"(\.lib\s+\S*sky130\.lib\.spice\s+)(\w+)",
        "supply_pattern": r"(V1 GND net1 )([0-9.]+)",
    }
    NETLIST = (
        "**.subckt smoke_test\n"
        "V1 GND net1 1.8\n"
        "XR1 net1 net2 sky130_fd_pr__res_generic_po W=1 L=1 m=1\n"
        "**** begin user architecture code\n\n"
        ".lib /some/path/sky130.lib.spice tt\n"
        ".op\n\n"
        "**** end user architecture code\n"
        "**.ends\n"
        ".GLOBAL GND\n"
        ".end\n"
    )

    def test_patches_corner_supply_and_inserts_temp(self):
        point = corners.PvtPoint(corner="ss", temp_c=-40.0, supply_v=1.62)
        patched = runner.patch_netlist(self.NETLIST, self.MANIFEST, point)
        self.assertIn(".lib /some/path/sky130.lib.spice ss", patched)
        self.assertIn("V1 GND net1 1.62", patched)
        self.assertIn(".temp -40\n.end", patched)

    def test_does_not_corrupt_the_ends_terminator(self):
        # Regression: a naive substring replace of ".end" also matches
        # "**.ends" (the subckt terminator), which appears earlier in the
        # file and would corrupt the netlist into an unbalanced pair.
        point = corners.PvtPoint(corner="tt", temp_c=27.0, supply_v=1.8)
        patched = runner.patch_netlist(self.NETLIST, self.MANIFEST, point)
        self.assertIn("**.ends\n", patched)
        self.assertEqual(patched.count(".temp"), 1)

    def test_missing_corner_pattern_raises(self):
        point = corners.PvtPoint(corner="tt", temp_c=27.0, supply_v=1.8)
        with self.assertRaises(runner.NetlistError):
            runner.patch_netlist("no corner line here\n.end\n", self.MANIFEST, point)


class PdkCommitParsingTests(unittest.TestCase):
    def test_extracts_commit_from_volare_style_symlink(self):
        import tempfile

        commit = "c6d73a35f524070e85faff4a6a9eef49553ebc2b"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_dir = root / "volare" / "sky130" / "versions" / commit / "sky130A"
            real_dir.mkdir(parents=True)
            link = root / "sky130A"
            link.symlink_to(real_dir)
            self.assertEqual(pdk_mod._commit_from_variant_dir(link), commit)

    def test_returns_none_for_a_non_volare_path(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "sky130A"
            plain.mkdir()
            self.assertIsNone(pdk_mod._commit_from_variant_dir(plain))


class SubsetReasonGateOrderingTests(unittest.TestCase):
    """The "an override needs --subset-reason" gate has to be checked *before*
    the corner matrix / MC trial list is built. Otherwise a run that supplies
    both an invalid override value and no `--subset-reason` reports the invalid
    value instead of the missing reason -- the operator fixes the corner name,
    re-runs, and only then learns a reason was required. Pinned here because
    the ordering is invisible to any test that supplies only one of the two
    errors at a time."""

    class _StubPdk:
        process_corners = ("tt",)
        commit_mismatch = False
        resolved_commit = "0" * 40
        pinned_commit = "0" * 40

    def _stderr_of(self, argv):
        import contextlib
        import io
        from unittest import mock

        args = cli.build_parser().parse_args(argv)
        buf = io.StringIO()
        with mock.patch.object(cli.pdk_mod, "resolve", return_value=self._StubPdk()):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(buf):
                rc = cli.cmd_run_mc(args) if args.mc else cli.cmd_run(args)
        return rc, buf.getvalue()

    def test_missing_subset_reason_outranks_an_invalid_corner(self):
        rc, err = self._stderr_of(["pdk-smoke", "--corners", "bogus_corner"])
        self.assertEqual(rc, 1)
        self.assertIn("needs --subset-reason", err)
        self.assertNotIn("bogus_corner", err)

    def test_missing_subset_reason_outranks_an_invalid_mc_corner(self):
        rc, err = self._stderr_of(["pdk-smoke", "--mc", "--mc-corner", "bogus_corner"])
        self.assertEqual(rc, 1)
        self.assertIn("needs --subset-reason", err)
        self.assertNotIn("bogus_corner", err)

    def test_invalid_corner_is_still_reported_once_a_reason_is_given(self):
        rc, err = self._stderr_of(
            ["pdk-smoke", "--corners", "bogus_corner", "--subset-reason", "pinning the gate order"]
        )
        self.assertEqual(rc, 1)
        self.assertIn("bogus_corner", err)


if __name__ == "__main__":
    unittest.main()
