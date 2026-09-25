#!/usr/bin/env python3
"""Unit tests for sim/harness. No PDK and no ngspice/xschem required.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import json
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


class PllManifestPatchNetlistTests(unittest.TestCase):
    """Exercises the sim/pll experiment's own corner_pattern/supply_pattern
    (issue #23) against a representative post-xschem-netlist snippet --
    loaded from the real committed manifest, not a hand-copied stand-in, so
    a future edit to the manifest's regex fields is checked against an
    actual patched-netlist expectation. Also pins the `V1 VDD GND` node
    order (VDD listed first, the SPICE positive terminal), which matters
    here in a way it didn't for sim/pdk-smoke's own throwaway resistor
    divider: getting this backwards silently biases every sky130_fd_pr__
    {n,p}fet_01v8 device in the closed loop at -VDD instead of +VDD."""

    MANIFEST = json.loads((SIM_DIR / "pll" / "testbench" / "tb.json").read_text())
    NETLIST = (
        "**.subckt tb_pll\n"
        "XXTOP VDD GND REF RESETB GND GND GND VDD VDD GND CLK top\n"
        "V1 VDD GND 1.8\n"
        "V2 REF GND pulse(0 1.8 0 1n 1n 48n 100n)\n"
        "V3 RESETB GND pwl(0 0 5n 0 6n 1.8)\n"
        "**** begin user architecture code\n\n"
        ".lib /some/path/sky130.lib.spice tt\n"
        ".tran 50p 200n\n\n"
        "**** end user architecture code\n"
        "**.ends\n"
        ".GLOBAL GND\n"
        ".end\n"
    )

    def test_patches_corner_and_supply_preserving_vdd_polarity(self):
        point = corners.PvtPoint(corner="ss", temp_c=-40.0, supply_v=1.62)
        patched = runner.patch_netlist(self.NETLIST, self.MANIFEST, point)
        self.assertIn(".lib /some/path/sky130.lib.spice ss", patched)
        self.assertIn("V1 VDD GND 1.62", patched)
        self.assertIn(".temp -40\n.end", patched)

    def test_manifest_process_corners_are_pdk_valid(self):
        pdk_json = json.loads((REPO_ROOT / "sim" / "pdk.json").read_text())
        valid = set(pdk_json["process_corners"])
        self.assertTrue(set(self.MANIFEST["process_corners"]).issubset(valid))


class DividerManifestPatchNetlistTests(unittest.TestCase):
    """Exercises the sim/divider experiment's own corner_pattern/supply_pattern
    (issue #129) against a representative post-xschem-netlist snippet -- same
    pattern as PllManifestPatchNetlistTests above, loaded from the real
    committed manifest rather than a hand-copied stand-in. sim/divider's DUT
    (design/divider/divider_intN.sch) is driven open-loop by an ideal pulse
    CLK source rather than a real VCO, but the corner/supply substitution
    machinery it exercises is identical, so this pins the same
    connectivity/polarity expectations for a manifest whose measure.lock
    block (not swept sim/vco-style characterization) is the interesting new
    surface -- covered by MeasureSpec parsing elsewhere in this file's
    BuildMatrixTests-adjacent coverage and by sim/tests/test_measure.py."""

    MANIFEST = json.loads((SIM_DIR / "divider" / "testbench" / "tb.json").read_text())
    NETLIST = (
        "**.subckt tb_divider\n"
        "XXXDIV VDD GND CLK RESETB GND GND GND VDD VDD GND FBCLK divider_intN\n"
        "V1 VDD GND 1.8\n"
        "V2 CLK GND pulse(0 1.8 0 12.5p 12.5p 442p 909p)\n"
        "V3 RESETB GND pwl(0 0 5n 0 6n 1.8)\n"
        "**** begin user architecture code\n\n"
        ".lib /some/path/sky130.lib.spice tt\n"
        "**** end user architecture code\n"
        "**.ends\n"
        ".GLOBAL GND\n"
        ".end\n"
    )

    def test_patches_corner_and_supply_preserving_vdd_polarity(self):
        point = corners.PvtPoint(corner="ss", temp_c=-40.0, supply_v=1.62)
        patched = runner.patch_netlist(self.NETLIST, self.MANIFEST, point)
        self.assertIn(".lib /some/path/sky130.lib.spice ss", patched)
        self.assertIn("V1 VDD GND 1.62", patched)
        self.assertIn(".temp -40\n.end", patched)

    def test_manifest_process_corners_are_pdk_valid(self):
        pdk_json = json.loads((REPO_ROOT / "sim" / "pdk.json").read_text())
        valid = set(pdk_json["process_corners"])
        self.assertTrue(set(self.MANIFEST["process_corners"]).issubset(valid))

    def test_manifest_declares_a_lock_block_gated_on_require_lock(self):
        # Unlike sim/pll-lock (require_lock: false -- a closed loop that
        # never locks is evidence, not a harness bug), a standalone divider
        # that fails to hold a clean N:1 division at this frequency, at this
        # corner, is a genuine FAIL (issue #129's own scope).
        measure = self.MANIFEST["measure"]
        self.assertIn("lock", measure)
        self.assertTrue(measure["require_lock"])
        self.assertEqual(measure["lock"]["target_hz"], 44004400)


class DividerFamilySiblingManifestTests(unittest.TestCase):
    """Same coverage as DividerManifestPatchNetlistTests above, extended to
    the four sibling standalone-divider campaigns issue #129 also added
    (`sim/divider-n4`, `sim/divider-n5`, `sim/divider-n63`,
    `sim/divider-n64`) -- each shares `sim/divider`'s DUT, open-loop method
    and `corner_pattern`/`supply_pattern`, differing only in `NSEL[5:0]`
    strap, CLK frequency and the resulting `measure.lock.target_hz`. Loaded
    from the real committed manifests (not hand-copied stand-ins) so a
    future edit to any of the five siblings' shared regex fields is checked
    against an actual patched-netlist expectation, not just the original
    `sim/divider` one."""

    # (slug, N, expected target_hz = f_CLK/N)
    SIBLINGS = (
        ("divider-n4", 4, 62500000),
        ("divider-n5", 5, 50000000),
        ("divider-n63", 63, 3968253.97),
        ("divider-n64", 64, 3906250),
    )

    NETLIST = (
        "**.subckt tb_divider\n"
        "XXXDIV VDD GND CLK RESETB GND GND GND VDD VDD GND FBCLK divider_intN\n"
        "V1 VDD GND 1.8\n"
        "V2 CLK GND pulse(0 1.8 0 12.5p 12.5p 1.998n 4n)\n"
        "V3 RESETB GND pwl(0 0 5n 0 6n 1.8)\n"
        "**** begin user architecture code\n\n"
        ".lib /some/path/sky130.lib.spice tt\n"
        "**** end user architecture code\n"
        "**.ends\n"
        ".GLOBAL GND\n"
        ".end\n"
    )

    def _manifest(self, slug: str) -> dict:
        return json.loads((SIM_DIR / slug / "testbench" / "tb.json").read_text())

    def test_every_sibling_manifest_exists_and_patches_cleanly(self):
        for slug, _n, _target_hz in self.SIBLINGS:
            with self.subTest(slug=slug):
                manifest = self._manifest(slug)
                point = corners.PvtPoint(corner="ss", temp_c=-40.0, supply_v=1.62)
                patched = runner.patch_netlist(self.NETLIST, manifest, point)
                self.assertIn(".lib /some/path/sky130.lib.spice ss", patched)
                self.assertIn("V1 VDD GND 1.62", patched)
                self.assertIn(".temp -40\n.end", patched)

    def test_every_sibling_manifest_process_corners_are_pdk_valid(self):
        pdk_json = json.loads((REPO_ROOT / "sim" / "pdk.json").read_text())
        valid = set(pdk_json["process_corners"])
        for slug, _n, _target_hz in self.SIBLINGS:
            with self.subTest(slug=slug):
                manifest = self._manifest(slug)
                self.assertTrue(set(manifest["process_corners"]).issubset(valid))

    def test_every_sibling_manifest_requires_lock_at_the_right_target(self):
        # Pins each sibling's NSEL strap to the modulus its own slug/claim
        # advertises: a copy-paste error here (e.g. n63's manifest quietly
        # keeping n64's target_hz) would otherwise silently mislabel which
        # modulus a passing record is evidence for.
        for slug, n, target_hz in self.SIBLINGS:
            with self.subTest(slug=slug):
                measure = self._manifest(slug)["measure"]
                self.assertIn("lock", measure)
                self.assertTrue(measure["require_lock"])
                self.assertAlmostEqual(measure["lock"]["target_hz"], target_hz, places=2)
                self.assertIn(f"N={n}", self._manifest(slug)["claim"])

    def test_every_sibling_manifest_cites_spec_row_4(self):
        # Pinned on the manifest's structured `spec_rows` field, not on a
        # sentence inside `claim`: the citation used to be hand-written into
        # the claim prose, which meant a record's rolled-up rows came from
        # prose the aggregator happened to match first rather than from the
        # declaration (issue #152). The prose copy is gone; this is the one
        # source `sim/harness/report.py` stamps into every record.
        for slug, _n, _target_hz in self.SIBLINGS:
            with self.subTest(slug=slug):
                manifest = self._manifest(slug)
                self.assertEqual(manifest["spec_rows"], [4])
                self.assertNotIn("**Spec row(s)**", manifest["claim"])


class PllLockJitterManifestTests(unittest.TestCase):
    """sim/pll-lock's row-9 (period jitter) declaration, issue #180.

    The PVT half of `DR-006`'s two-axis verification for ratified row 9 --
    the statistical half is `sim/pll-lock-mc`. These pin the three things the
    manifest *decides* (that it cites row 9 at all, the ratified bound it
    states, and that it gates on it), plus the one arithmetic coupling that
    makes gating safe on a campaign that deliberately does not require lock.
    """

    MANIFEST = json.loads((SIM_DIR / "pll-lock" / "testbench" / "tb.json").read_text())

    def _spec(self):
        from harness import measure as measure_mod

        return measure_mod.MeasureSpec.from_manifest(self.MANIFEST)

    def test_manifest_declares_row_9s_ratified_bound(self):
        spec = self._spec()
        self.assertIsNotNone(spec.jitter, "sim/pll-lock declares no measure.jitter block")
        # 1.0 % of the output period -- target-spec.md row 9, ratified by DR-006.
        self.assertEqual(spec.jitter.max_frac, 0.01)

    def test_manifest_cites_row_9_alongside_rows_8_and_14(self):
        self.assertEqual(self.MANIFEST["spec_rows"], [8, 9, 14])
        self.assertIn("row 9", self.MANIFEST["spec_rows_note"])

    def test_the_gating_choice_is_stated_explicitly_not_left_to_the_default(self):
        # `JitterSpec.gate_on_bound` defaults to true, so a manifest that
        # merely omits the key states nothing. This campaign's verdict column
        # already carries a deliberate non-gating convention for lock
        # (`require_lock: false`), so its row-9 gating decision has to be
        # visible in the manifest a reader of a record opens.
        block = self.MANIFEST["measure"]["jitter"]
        self.assertIn("gate_on_bound", block)
        self.assertTrue(block["gate_on_bound"])
        self.assertIn("gate_on_bound", self.MANIFEST["methodology_note"])

    def test_gating_cannot_fire_on_a_point_this_manifest_expects_not_to_lock(self):
        # The load-bearing composition: `require_lock: false` says a corner
        # that never locks is evidence, not a failure. A gated row-9 bound
        # must not fail that point through the back door.
        from harness import measure as measure_mod

        spec = self._spec()
        self.assertFalse(spec.require_lock)
        dead = measure_mod.Measurement(
            label="ss_-40c_1.62v",
            oscillating=True,
            freq_hz=180e6,
            duty_cycle=0.5,
            locked=False,
            lock_time_s=None,
            final_freq_hz=180e6,
            note="no lock within this window",
            passed=True,
            period_jitter_frac=None,
            jitter_cycles=0,
        )
        passed, _reason = measure_mod.aggregate([dead], spec)
        self.assertTrue(passed)

    def test_min_cycles_cannot_outrun_the_population_a_locked_point_guarantees(self):
        # `lock_time` only reports a lock when at least `min_hold_cycles`
        # cycles of in-band data follow the lock instant, and the jitter
        # population is exactly those cycles. So `jitter.min_cycles` <=
        # `lock.min_hold_cycles` is what stops a gated bound from FAILing a
        # locked point for a population shortfall it can never have -- an
        # artefact verdict, not a design fact.
        spec = self._spec()
        self.assertLessEqual(spec.jitter.min_cycles, spec.lock.min_hold_cycles)

    def test_the_dump_grid_the_number_is_read_at_is_stated_with_it(self):
        # measure.period_jitter's figure is only readable together with the
        # tran_step that produced it (#178). Refusing to restate the grid in
        # the manifest's own note would hand a record's reader a bare
        # percentage.
        note = self.MANIFEST["methodology_note"]
        self.assertIn(self.MANIFEST["measure"]["tran_step"], note)
        self.assertIn("#178", note)


class LoopRippleManifestTests(unittest.TestCase):
    """sim/loop-ripple (issue #166): same DUT and DR-005 cold start as
    sim/pll-lock, but the ideal supply V1 drives an upstream node VSUP
    through a series RPDN into the DUT's VDD -- so the supply_pattern must
    patch V1's value on VSUP (not VDD), and must leave the RPDN card alone.
    Loaded from the real committed manifest."""

    MANIFEST = json.loads((SIM_DIR / "loop-ripple" / "testbench" / "tb.json").read_text())
    PLL_LOCK = json.loads((SIM_DIR / "pll-lock" / "testbench" / "tb.json").read_text())
    NETLIST = (
        "**.subckt tb_loop_ripple\n"
        "XXXTOP VDD GND REF RESETB GND GND GND VDD VDD GND CLK top\n"
        "V1 VSUP GND 1.8\n"
        "RPDN VSUP VDD 1 m=1\n"
        "V2 REF GND pulse(0 1.8 0 1n 1n 48n 100n)\n"
        "V3 RESETB GND pwl(0 0 5n 0 6n 1.8)\n"
        "**** begin user architecture code\n\n"
        ".lib /some/path/sky130.lib.spice tt\n"
        "**** end user architecture code\n"
        "**.ends\n"
        ".GLOBAL GND\n"
        ".end\n"
    )

    def _patched(self):
        from harness import measure as measure_mod

        spec = measure_mod.MeasureSpec.from_manifest(self.MANIFEST)
        point = corners.PvtPoint(corner="ss", temp_c=-40.0, supply_v=1.62)
        return runner.patch_netlist(
            self.NETLIST, self.MANIFEST, point, spec=spec, prefix=f"{point.corner_id}-"
        )

    def test_patches_the_upstream_source_not_the_pdn_resistor(self):
        patched = self._patched()
        self.assertIn(".lib /some/path/sky130.lib.spice ss", patched)
        self.assertIn("V1 VSUP GND 1.62", patched)
        self.assertIn("RPDN VSUP VDD 1 m=1", patched)

    def test_injects_the_dr005_cold_start_and_a_multi_node_dump(self):
        patched = self._patched()
        for card in self.PLL_LOCK["measure"]["ic"]:
            self.assertIn(f".ic {card}", patched)
        self.assertIn("set wr_singlescale", patched)
        self.assertIn("wrdata ss_-40c_1.62v-point000.raw v(CLK) v(VDD) v(xxxtop.vctrl)", patched)
        self.assertIn("tran 200p 100u", patched)

    def test_cold_start_and_lock_criterion_match_sim_pll_lock(self):
        # Comparable lock column: same ic cards, window and criterion.
        mine, theirs = self.MANIFEST["measure"], self.PLL_LOCK["measure"]
        for key in ("ic", "lock", "tran_stop", "tran_step", "require_lock", "node"):
            self.assertEqual(mine[key], theirs[key], key)
        self.assertEqual(self.MANIFEST["process_corners"], self.PLL_LOCK["process_corners"])
        self.assertEqual(self.MANIFEST["spec_rows"], [13])


class RenderRippleTableTests(unittest.TestCase):
    """report.render() emits a per-point ripple table for a manifest with a
    `measure.ripple` block, marking whether each window was in lock."""

    def test_ripple_table_rows(self):
        from unittest import mock

        from harness import measure as measure_mod

        spec = measure_mod.MeasureSpec(
            node="CLK", tran_step="200p", tran_stop="100u", timeout_s=60,
            lock=measure_mod.LockSpec(
                target_hz=250e6, tolerance_frac=0.05, window_cycles=20, min_hold_cycles=20
            ),
            ripple=measure_mod.RippleSpec(nodes=("VDD", "xxxtop.vctrl"), window_s=5e-6),
        )

        def meas(in_lock, locked, vdd_pp, vctrl_pp):
            rip = (
                measure_mod.RippleResult("VDD", 95e-6, 100e-6, 1.79, 1.79 + vdd_pp, vdd_pp, in_lock),
                measure_mod.RippleResult("xxxtop.vctrl", 95e-6, 100e-6, 1.1, 1.1 + vctrl_pp, vctrl_pp, in_lock),
            )
            return measure_mod.Measurement(
                label=None, oscillating=True, freq_hz=250e6 if locked else None,
                duty_cycle=0.5 if locked else None, locked=locked,
                lock_time_s=30e-6 if locked else None, final_freq_hz=250e6,
                note="n", passed=True, ripple=rip,
            )

        p1 = corners.PvtPoint(corner="tt", temp_c=27.0, supply_v=1.8)
        p2 = corners.PvtPoint(corner="ss", temp_c=-40.0, supply_v=1.62)
        p3 = corners.PvtPoint(corner="ff", temp_c=125.0, supply_v=1.98)
        results = [
            runner.PointResult(point=p1, passed=True, reason="ok", measurements=(meas(True, True, 0.004, 0.001),)),
            runner.PointResult(point=p2, passed=True, reason="ok", measurements=(meas(False, False, 0.003, 0.02),)),
            runner.PointResult(point=p3, passed=False, reason="timed out"),
        ]
        with mock.patch.object(report, "git_info", return_value={"sha": "abc1234", "dirty": False}):
            with mock.patch.object(report, "sha256_file", return_value="deadbeef"):
                text = report.render(
                    record_id="20260101-000000-abc1234", slug="loop-ripple", claim="c",
                    spec_rows_line="13 -- x", pdk=RenderMethodologyTests._StubPdk(),
                    tool_versions={"ngspice": "n", "xschem": "x"}, repo_root=REPO_ROOT,
                    netlist_snapshot=Path("/fake/netlist.spice"), points=[p1, p2, p3],
                    results=results, subset_reason=None, supersedes=None,
                    methodology_note="m", analysis="a", spec=spec,
                )
        self.assertIn("- **Ripple** (peak-to-peak of v(VDD), v(xxxtop.vctrl) over the final 5 us", text)
        self.assertIn("| tt | 27 | 1.80 | yes | 4 mV | 1.79..1.794 V | 1 mV | 1.1..1.101 V |", text)
        self.assertIn("| ss | -40 | 1.62 | **no** | 3 mV |", text)
        self.assertIn("| ff | 125 | 1.98 | - | - | - | - | - |", text)
        self.assertIn("Ripple (reported, not gated on)", text)


class RenderMethodologyTests(unittest.TestCase):
    """Regression coverage for report.render()/render_mc()'s
    `methodology_note`/`analysis` parameters (issue #23). Before this, the
    "not a PLL performance measurement -- there is no PLL netlist yet" and
    "Analysis: DC operating point (`.op`)" lines were hardcoded verbatim
    inside report.py itself -- accurate for sim/pdk-smoke's own claim, but
    silently wrong the moment a second experiment (sim/pll, which *is* a PLL
    netlist and runs `.tran`, not `.op`) started using the same renderer.
    Pins that both lines are now sourced from the caller instead."""

    class _StubPdk:
        variant = "sky130A"
        resolved_commit = "0" * 40
        pinned_commit = "0" * 40
        commit_mismatch = False
        ngspice_lib = Path("/fake/sky130.lib.spice")

    def _render(self, **overrides):
        from unittest import mock

        point = corners.PvtPoint(corner="tt", temp_c=27.0, supply_v=1.8)
        result = runner.PointResult(
            point=point,
            passed=True,
            reason="ok",
        )
        kwargs = dict(
            record_id="20260101-000000-abc1234",
            slug="pll",
            claim="a claim",
            spec_rows_line="none -- a fixture",
            pdk=self._StubPdk(),
            tool_versions={"ngspice": "ngspice-47", "xschem": "XSCHEM V3.4.7"},
            repo_root=REPO_ROOT,
            netlist_snapshot=Path("/fake/netlist.spice"),
            points=[point],
            results=[result],
            subset_reason=None,
            supersedes=None,
            methodology_note="a PLL-specific methodology note.",
            analysis="transient (`.tran 50p 200n`)",
        )
        kwargs.update(overrides)
        with mock.patch.object(report, "git_info", return_value={"sha": "abc1234", "dirty": False}):
            with mock.patch.object(report, "sha256_file", return_value="deadbeef"):
                return report.render(**kwargs)

    def test_methodology_note_is_sourced_from_the_caller(self):
        text = self._render()
        self.assertIn("a PLL-specific methodology note.", text)

    def test_analysis_is_sourced_from_the_caller(self):
        text = self._render()
        self.assertIn("Analysis: transient (`.tran 50p 200n`).", text)

    def test_no_hardcoded_pdk_smoke_prose_leaks_into_an_unrelated_slug(self):
        text = self._render()
        self.assertNotIn("there is no PLL netlist yet", text)
        self.assertNotIn("DC operating point", text)

    def test_record_states_its_spec_rows(self):
        # The line measurements/aggregate.py matches on, stamped into every
        # record by construction (issue #152).
        text = self._render(spec_rows_line="6, 7 -- loop bandwidth and phase margin")
        self.assertIn("- **Spec row(s)**: 6, 7 -- loop bandwidth and phase margin", text)

    def test_record_can_state_an_explicit_none(self):
        text = self._render(spec_rows_line="none -- harness plumbing")
        self.assertIn("- **Spec row(s)**: none -- harness plumbing", text)


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


class TimeoutDecodingTests(unittest.TestCase):
    """Regression coverage for a real crash hit while running issue #52's
    lock-capable campaign: `subprocess.run(..., text=True, timeout=...)`
    raising `TimeoutExpired` does not guarantee its `.stdout`/`.stderr` are
    already-decoded `str` -- on a real timeout each can independently be
    `str`, `bytes`, or `None` (Popen.communicate() had not finished decoding
    when it raised). The pre-fix code did `(e.stdout or "") + (e.stderr or
    "")`, which raises `TypeError: can't concat str to bytes` whenever one
    stream came back as `bytes` -- crashing the *entire* multi-point run
    (not just the one point that timed out) the first time a real ngspice
    process actually blew its manifest's timeout budget. Hit in production
    running sim/pll's full PVT matrix (point 14/27, `ss_27c_1.80v`)."""

    def _timeout_reason(self, work_dir: Path, *, stdout, stderr) -> tuple:
        import subprocess
        from unittest import mock

        class _StubPdk:
            def as_env(self):
                return {}

        exc = subprocess.TimeoutExpired(cmd=["ngspice", "-b", "x.spice"], timeout=1, output=stdout, stderr=stderr)
        with mock.patch.object(runner.subprocess, "run", side_effect=exc):
            passed, reason, log_path, _spice_path = runner._run_ngspice_and_judge(
                _StubPdk(), work_dir / ".spiceinit", "* patched\n.end\n", "x", work_dir, timeout_s=1
            )
        return passed, reason, log_path

    def test_bytes_stdout_and_str_stderr_does_not_crash(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / ".spiceinit").write_text("")
            passed, reason, log_path = self._timeout_reason(
                work_dir, stdout=b"partial ngspice output\n", stderr=""
            )
            self.assertFalse(passed)
            self.assertIn("timeout", reason)
            self.assertIn("partial ngspice output", log_path.read_text())

    def test_none_stdout_and_none_stderr_does_not_crash(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / ".spiceinit").write_text("")
            passed, reason, log_path = self._timeout_reason(work_dir, stdout=None, stderr=None)
            self.assertFalse(passed)
            self.assertIn("timeout", reason)
            self.assertEqual(log_path.read_text(), "")

    def test_both_bytes_concatenates_both_streams(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / ".spiceinit").write_text("")
            _passed, _reason, log_path = self._timeout_reason(
                work_dir, stdout=b"stdout chunk", stderr=b"stderr chunk"
            )
            text = log_path.read_text()
            self.assertIn("stdout chunk", text)
            self.assertIn("stderr chunk", text)


class SpecRowsDeclarationTests(unittest.TestCase):
    """`spec_rows` is required at the manifest, so every minted record carries
    the `**Spec row(s)**:` citation `measurements/aggregate.py` matches on
    (issue #152) -- by construction, not by an author remembering it.
    """

    def test_missing_declaration_is_an_error_not_a_silent_default(self):
        with self.assertRaises(report.SpecRowsError) as ctx:
            report.spec_rows_from_manifest({"claim": "x"})
        self.assertIn("spec_rows", str(ctx.exception))

    def test_non_list_declaration_is_rejected(self):
        with self.assertRaises(report.SpecRowsError):
            report.spec_rows_from_manifest({"spec_rows": "6, 7"})

    def test_non_row_number_entry_is_rejected(self):
        with self.assertRaises(report.SpecRowsError):
            report.spec_rows_from_manifest({"spec_rows": ["six"]})
        with self.assertRaises(report.SpecRowsError):
            report.spec_rows_from_manifest({"spec_rows": [-1]})

    def test_empty_declaration_without_a_note_is_rejected(self):
        # "this measures no spec row" is a claim, so it has to be argued.
        with self.assertRaises(report.SpecRowsError):
            report.spec_rows_from_manifest({"spec_rows": []})

    def test_empty_declaration_with_a_note_is_accepted(self):
        rows, note = report.spec_rows_from_manifest(
            {"spec_rows": [], "spec_rows_note": "plumbing only"}
        )
        self.assertEqual(rows, [])
        self.assertEqual(note, "plumbing only")

    def test_rows_and_optional_note_round_trip(self):
        rows, note = report.spec_rows_from_manifest({"spec_rows": [6, 7]})
        self.assertEqual(rows, [6, 7])
        self.assertEqual(note, "")

    def test_section_override_only_applies_when_it_declares_its_own_rows(self):
        manifest = {"spec_rows": [6], "spec_rows_note": "base"}
        self.assertEqual(
            report.spec_rows_from_manifest(manifest, section={"claim": "mc"})[0], [6]
        )
        self.assertEqual(
            report.spec_rows_from_manifest(manifest, section={"spec_rows": [9, 10]})[0],
            [9, 10],
        )

    def test_formatted_line_leads_with_the_row_numbers(self):
        # The aggregator reads the digits immediately after the colon, so any
        # prose has to follow them, never precede them.
        self.assertEqual(report.format_spec_rows([6, 7], ""), "6, 7")
        self.assertTrue(report.format_spec_rows([6, 7], "why").startswith("6, 7 -- "))
        self.assertEqual(report.format_spec_rows([], "why"), "none -- why")

    def test_every_checked_in_manifest_declares_spec_rows(self):
        for tb_json in sorted((SIM_DIR).glob("*/testbench/tb.json")):
            with self.subTest(manifest=tb_json.name):
                manifest = json.loads(tb_json.read_text())
                report.spec_rows_from_manifest(manifest)  # raises if undeclared


if __name__ == "__main__":
    unittest.main()
