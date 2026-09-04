#!/usr/bin/env python3
"""Unit tests for sim/harness/acmeasure.py -- the loop-dynamics reducer.

No PDK, no ngspice and no xschem required. Every test below drives the
extraction functions from a *synthetic* frequency response built here in the
test from closed-form complex arithmetic, so the crossover frequency and phase
margin the reducer reports are checked against values this file solves for
independently (by bisection on the same closed form) rather than against
anything the reducer itself produced.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import cmath
import math
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import acmeasure  # noqa: E402
from harness import runner  # noqa: E402
from harness.corners import PvtPoint  # noqa: E402
from harness.measure import MeasureError  # noqa: E402

# design/loop-filter/DESIGN.md's own component values -- the third-order
# passive network this campaign's DUT implements. Used here only to build a
# *synthetic* response with a known answer; the reducer never sees these.
R1, C1, C2, R3, C3 = 20.6e3, 53.26e-12, 2.48e-12, 10e3, 3.56e-12


def loop_gain(f: float, a: float) -> complex:
    """`T(s) = A * Z(s) / s` for the third-order filter, in closed form."""
    s = 2j * math.pi * f
    z1 = R1 + 1.0 / (s * C1)
    z2 = 1.0 / (s * C2)
    z3 = R3 + 1.0 / (s * C3)
    z_cp = 1.0 / (1.0 / z1 + 1.0 / z2 + 1.0 / z3)
    v_ctrl = z_cp * (1.0 / (s * C3)) / z3
    return a * v_ctrl / s


def solve_crossover(a: float, lo: float = 1.0, hi: float = 1e9) -> tuple:
    """Bisect `|T| = 1` and return (f_c, phase margin in degrees).

    Independent of everything in `acmeasure` -- this is the reference answer
    the reducer's log-interpolated result is compared against.
    """
    for _ in range(300):
        mid = math.sqrt(lo * hi)
        if abs(loop_gain(mid, a)) > 1.0:
            lo = mid
        else:
            hi = mid
    f_c = math.sqrt(lo * hi)
    return f_c, 180.0 + math.degrees(cmath.phase(loop_gain(f_c, a)))


def sample_response(a: float, f_start=100.0, f_stop=1e8, per_decade=40):
    """Sample `loop_gain` on a log grid, as ngspice's `ac dec` would."""
    n = int(round(per_decade * math.log10(f_stop / f_start)))
    freqs, reals, imags = [], [], []
    for k in range(n + 1):
        f = f_start * 10.0 ** (k / per_decade)
        t = loop_gain(f, a)
        freqs.append(f)
        reals.append(t.real)
        imags.append(t.imag)
    return freqs, reals, imags


def wrdata_text(freqs, reals, imags) -> str:
    """Render a sampled response the way ngspice's `wrdata` writes AC data."""
    return "".join(
        f" {f:.8e} {r:.8e} {i:.8e} \n" for f, r, i in zip(freqs, reals, imags)
    )


def spec(**overrides) -> acmeasure.AcSpec:
    block = {
        "node": "phi",
        "source": "I1",
        "f_start": "100",
        "f_stop": "100meg",
        "points_per_decade": 40,
        "f_ref_hz": 8e6,
        "phase_margin_floor_deg": 45,
        "f_c_ceiling_frac_of_f_ref": 0.1,
        "loop_gain": [
            {"label": "a", "icp_a": 5e-6, "kvco_hz_per_v": 460e6, "n_divide": 20},
        ],
    }
    block.update(overrides)
    return acmeasure.AcSpec.from_manifest({"ac": block})


class ParseSpiceFreqTests(unittest.TestCase):
    def test_plain_and_suffixed_literals(self):
        self.assertEqual(acmeasure.parse_spice_freq("100"), 100.0)
        self.assertEqual(acmeasure.parse_spice_freq("1k"), 1e3)
        self.assertEqual(acmeasure.parse_spice_freq("2.5g"), 2.5e9)
        self.assertEqual(acmeasure.parse_spice_freq(1e6), 1e6)

    def test_meg_is_1e6_and_bare_m_is_milli(self):
        """SPICE's classic footgun, honored explicitly."""
        self.assertEqual(acmeasure.parse_spice_freq("100meg"), 1e8)
        self.assertEqual(acmeasure.parse_spice_freq("100m"), 0.1)

    def test_trailing_unit_letters_are_ignored(self):
        self.assertEqual(acmeasure.parse_spice_freq("5kHz"), 5e3)

    def test_rejects_garbage(self):
        with self.assertRaises(MeasureError):
            acmeasure.parse_spice_freq("wideband")
        with self.assertRaises(MeasureError):
            acmeasure.parse_spice_freq("10z")


class AcSpecTests(unittest.TestCase):
    def test_absent_block_yields_none(self):
        self.assertIsNone(acmeasure.AcSpec.from_manifest({}))
        self.assertIsNone(acmeasure.AcSpec.from_manifest({"ac": {}}))

    def test_missing_required_key_is_reported_by_name(self):
        with self.assertRaises(MeasureError) as ctx:
            acmeasure.AcSpec.from_manifest(
                {"ac": {"node": "phi", "f_start": "1", "f_stop": "2", "loop_gain": [1]}}
            )
        self.assertIn("source", str(ctx.exception))

    def test_empty_loop_gain_list_is_rejected(self):
        with self.assertRaises(MeasureError):
            spec(loop_gain=[])

    def test_loop_gain_point_missing_fields_is_reported(self):
        with self.assertRaises(MeasureError) as ctx:
            spec(loop_gain=[{"label": "x", "icp_a": 1e-5}])
        self.assertIn("kvco_hz_per_v", str(ctx.exception))
        self.assertIn("n_divide", str(ctx.exception))

    def test_non_positive_divide_ratio_is_rejected(self):
        with self.assertRaises(MeasureError):
            spec(
                loop_gain=[
                    {"label": "x", "icp_a": 1e-5, "kvco_hz_per_v": 1e9, "n_divide": 0}
                ]
            )

    def test_inverted_band_is_rejected(self):
        with self.assertRaises(MeasureError):
            spec(f_start="1meg", f_stop="1k")

    def test_loop_gain_scalar_is_icp_times_kvco_over_n(self):
        s = spec()
        self.assertAlmostEqual(s.loop_gain[0].scalar, 5e-6 * 460e6 / 20)

    def test_derived_bounds_and_defaults(self):
        s = spec()
        self.assertEqual(s.f_start_hz, 100.0)
        self.assertEqual(s.f_stop_hz, 1e8)
        self.assertAlmostEqual(s.f_c_ceiling_hz, 8e5)
        self.assertTrue(s.require_crossover)
        self.assertFalse(s.gate_on_bounds)

    def test_ceiling_is_none_without_both_inputs(self):
        self.assertIsNone(spec(f_ref_hz=None).f_c_ceiling_hz)
        self.assertIsNone(spec(f_c_ceiling_frac_of_f_ref=None).f_c_ceiling_hz)
        block = {
            "node": "phi",
            "source": "I1",
            "f_start": "100",
            "f_stop": "1meg",
            "loop_gain": [
                {"label": "a", "icp_a": 1e-5, "kvco_hz_per_v": 1e9, "n_divide": 20}
            ],
        }
        s = acmeasure.AcSpec.from_manifest({"ac": block})
        self.assertIsNone(s.f_c_ceiling_hz)


class ControlBlockTests(unittest.TestCase):
    def test_one_alter_ac_wrdata_triple_per_loop_gain_point(self):
        s = spec(
            loop_gain=[
                {"label": "lo", "icp_a": 5e-6, "kvco_hz_per_v": 460e6, "n_divide": 20},
                {"label": "hi", "icp_a": 1e-5, "kvco_hz_per_v": 460e6, "n_divide": 20},
            ]
        )
        text = acmeasure.build_ac_control_block(s, prefix="tt_27c-")
        self.assertEqual(text.count("alter @i1[acmag]"), 2)
        self.assertEqual(text.count("ac dec 40 100 100meg"), 2)
        self.assertEqual(text.count("destroy all"), 2)
        self.assertIn("wrdata tt_27c-ac000.raw v(phi)", text)
        self.assertIn("wrdata tt_27c-ac001.raw v(phi)", text)
        self.assertIn("alter @i1[acmag] = 115", text)
        self.assertIn("alter @i1[acmag] = 230", text)

    def test_completion_marker_is_the_last_statement_before_endc(self):
        lines = acmeasure.build_ac_control_block(spec()).strip().splitlines()
        self.assertEqual(lines[-1], ".endc")
        self.assertIn(acmeasure.COMPLETION_MARKER, lines[-2])

    def test_waveform_names_use_the_gitignored_raw_extension(self):
        s = spec(
            loop_gain=[
                {"label": "a", "icp_a": 1e-5, "kvco_hz_per_v": 1e9, "n_divide": 20},
                {"label": "b", "icp_a": 2e-5, "kvco_hz_per_v": 1e9, "n_divide": 20},
            ]
        )
        self.assertEqual(
            acmeasure.waveform_names(s, "ss_125c-"),
            ["ss_125c-ac000.raw", "ss_125c-ac001.raw"],
        )


class ParseAcWrdataTests(unittest.TestCase):
    def test_reads_freq_real_imag_triples(self):
        freqs, reals, imags = acmeasure.parse_ac_wrdata(
            " 1.0e+02  4.9e+06  2.9e+03 \n 2.0e+02  1.2e+06 -3.0e+03 \n"
        )
        self.assertEqual(freqs, [100.0, 200.0])
        self.assertEqual(reals, [4.9e6, 1.2e6])
        self.assertEqual(imags, [2.9e3, -3.0e3])

    def test_skips_unparseable_and_short_rows(self):
        freqs, _, _ = acmeasure.parse_ac_wrdata(
            "banner line\n1.0e+02\n 1.0e+02 1.0 2.0\nx y z\n"
        )
        self.assertEqual(freqs, [100.0])

    def test_empty_dump_raises(self):
        with self.assertRaises(MeasureError):
            acmeasure.parse_ac_wrdata("\n\nnothing numeric here\n")


class PhaseUnwrapTests(unittest.TestCase):
    def test_unwraps_across_the_plus_minus_180_branch_cut(self):
        # A phase walking -170 -> -190 deg: atan2 reports -170 then +170.
        angles = [-170.0, 170.0, 150.0]
        reals = [math.cos(math.radians(a)) for a in angles]
        imags = [math.sin(math.radians(a)) for a in angles]
        out = acmeasure.unwrapped_phase_deg(reals, imags)
        self.assertAlmostEqual(out[0], -170.0, places=6)
        self.assertAlmostEqual(out[1], -190.0, places=6)
        self.assertAlmostEqual(out[2], -210.0, places=6)

    def test_anchors_the_curve_into_minus_360_to_zero(self):
        """A response starting at +180 deg must be read as -180, not +180.

        This is the branch phase margin is defined against: `180 + arg T` at
        crossover. Anchoring on the wrong branch inflates a 50 deg margin into
        a 410 deg one, which is what the first real run of this reducer did
        before the anchor was fixed to `floor`.
        """
        angles = [180.0, 170.0, 120.0]
        reals = [math.cos(math.radians(a)) for a in angles]
        imags = [math.sin(math.radians(a)) for a in angles]
        out = acmeasure.unwrapped_phase_deg(reals, imags)
        self.assertAlmostEqual(out[0], -180.0, places=6)
        self.assertLessEqual(max(out), 0.0)

    def test_empty_input(self):
        self.assertEqual(acmeasure.unwrapped_phase_deg([], []), [])


class UnityGainCrossingTests(unittest.TestCase):
    def test_finds_the_single_downward_crossing(self):
        freqs, reals, imags = sample_response(115.0)
        mags = acmeasure.magnitudes(reals, imags)
        phases = acmeasure.unwrapped_phase_deg(reals, imags)
        crossings = acmeasure.unity_gain_crossings(freqs, mags, phases)
        self.assertEqual(len(crossings), 1)
        f_ref, _ = solve_crossover(115.0)
        self.assertAlmostEqual(crossings[0][0] / f_ref, 1.0, places=3)

    def test_upward_crossings_are_not_candidates(self):
        freqs = [1.0, 2.0, 3.0, 4.0]
        mags = [0.5, 2.0, 0.5, 0.1]
        phases = [-180.0, -170.0, -160.0, -150.0]
        # Only the 2.0 -> 0.5 step is a downward crossing.
        crossings = acmeasure.unity_gain_crossings(freqs, mags, phases)
        self.assertEqual(len(crossings), 1)
        self.assertGreater(crossings[0][0], 2.0)
        self.assertLess(crossings[0][0], 3.0)


class MeasureAcResponseTests(unittest.TestCase):
    def _measure(self, a: float, **spec_overrides):
        freqs, reals, imags = sample_response(a)
        return acmeasure.measure_ac_response(
            freqs, reals, imags, spec(**spec_overrides)
        )

    def test_crossover_and_phase_margin_match_an_independent_solve(self):
        for a in (115.0, 230.0, 875.5):
            with self.subTest(a=a):
                m = self._measure(a)
                f_ref, pm_ref = solve_crossover(a)
                self.assertTrue(m.crossed)
                self.assertAlmostEqual(m.crossover_hz / f_ref, 1.0, places=2)
                self.assertAlmostEqual(m.phase_margin_deg, pm_ref, delta=0.5)

    def test_phase_margin_is_180_plus_phase_at_crossover(self):
        m = self._measure(115.0)
        self.assertAlmostEqual(m.phase_margin_deg, 180.0 + m.phase_at_crossover_deg)

    def test_gain_margin_is_reported_above_the_crossover(self):
        m = self._measure(115.0)
        self.assertIsNotNone(m.gain_margin_hz)
        self.assertGreater(m.gain_margin_hz, m.crossover_hz)
        # A stable loop has positive gain margin (|T| < 1 at -180 deg).
        self.assertGreater(m.gain_margin_db, 0.0)

    def test_draft_bounds_are_annotated_not_enforced(self):
        """A miss is recorded as a miss, and still PASSes the harness verdict.

        Rows 6 and 7 are DRAFT. Per CLAUDE.md the harness may not launder a
        miss into a pass, and equally may not present a bound it has not
        ratified as a gate -- so the measurement is annotated and the verdict
        stays on the plumbing/measurability criterion.
        """
        m = self._measure(875.5)
        self.assertFalse(m.meets_pm_floor)
        self.assertFalse(m.meets_fc_ceiling)
        self.assertIn("misses", m.note)
        self.assertTrue(m.passed)

    def test_gate_on_bounds_opt_in_fails_the_point(self):
        m = self._measure(875.5, gate_on_bounds=True)
        self.assertFalse(m.passed)

    def test_comfortable_point_meets_both_draft_bounds(self):
        m = self._measure(115.0)
        self.assertTrue(m.meets_pm_floor)
        self.assertTrue(m.meets_fc_ceiling)
        self.assertNotIn("misses", m.note)

    def test_no_crossover_is_explicit_and_attributes_no_bandwidth(self):
        """The AC counterpart of measure.py's "no lock" discipline.

        A sweep whose gain never falls through unity must not have the last
        simulated magnitude reported as if it were a crossover.
        """
        # Loop gain so small it is below unity across the whole band.
        freqs, reals, imags = sample_response(1e-9)
        m = acmeasure.measure_ac_response(freqs, reals, imags, spec())
        self.assertFalse(m.crossed)
        self.assertEqual(m.crossing_count, 0)
        self.assertIsNone(m.crossover_hz)
        self.assertIsNone(m.phase_margin_deg)
        self.assertIn("no crossover", m.note)
        self.assertFalse(m.passed)

    def test_no_crossover_passes_when_the_manifest_does_not_require_one(self):
        freqs, reals, imags = sample_response(1e-9)
        m = acmeasure.measure_ac_response(
            freqs, reals, imags, spec(require_crossover=False)
        )
        self.assertFalse(m.crossed)
        self.assertTrue(m.passed)

    def test_multiple_crossings_are_flagged_and_the_highest_is_used(self):
        freqs = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        mags = [10.0, 0.5, 4.0, 0.5, 0.2, 0.1]
        phases = [-180.0, -170.0, -160.0, -150.0, -140.0, -130.0]
        crossings = acmeasure.unity_gain_crossings(freqs, mags, phases)
        self.assertEqual(len(crossings), 2)
        reals = [m * math.cos(math.radians(p)) for m, p in zip(mags, phases)]
        imags = [m * math.sin(math.radians(p)) for m, p in zip(mags, phases)]
        m = acmeasure.measure_ac_response(freqs, reals, imags, spec())
        self.assertEqual(m.crossing_count, 2)
        self.assertIn("2 unity-gain crossings", m.note)
        self.assertAlmostEqual(m.crossover_hz, crossings[-1][0])

    def test_label_and_gain_point_are_carried_through(self):
        s = spec()
        freqs, reals, imags = sample_response(115.0)
        m = acmeasure.measure_ac_response(
            freqs, reals, imags, s, gain_point=s.loop_gain[0]
        )
        self.assertEqual(m.label, "a")
        self.assertIs(m.gain_point, s.loop_gain[0])


class AggregateTests(unittest.TestCase):
    def _measurement(self, **kwargs):
        base = dict(
            label=None,
            gain_point=None,
            crossed=True,
            crossing_count=1,
            crossover_hz=3.5e5,
            phase_at_crossover_deg=-130.0,
            phase_margin_deg=50.0,
            gain_margin_db=12.0,
            gain_margin_hz=3e6,
            dc_gain_db=130.0,
            meets_pm_floor=True,
            meets_fc_ceiling=True,
            note="f_c 350 kHz, phase margin 50.0 deg",
            passed=True,
        )
        base.update(kwargs)
        return acmeasure.AcMeasurement(**base)

    def test_no_measurements_fails(self):
        passed, reason = acmeasure.aggregate([], spec())
        self.assertFalse(passed)
        self.assertIn("no AC measurements", reason)

    def test_a_single_failing_measurement_fails_the_point(self):
        passed, reason = acmeasure.aggregate(
            [self._measurement(label="hi", passed=False, note="**no crossover**: ...")],
            spec(),
        )
        self.assertFalse(passed)
        self.assertIn("hi", reason)
        self.assertIn("no crossover", reason)

    def test_multi_point_summary_names_every_swept_point(self):
        passed, reason = acmeasure.aggregate(
            [
                self._measurement(label="lo", crossover_hz=3.5e5, phase_margin_deg=50.0),
                self._measurement(label="hi", crossover_hz=1.5e6, phase_margin_deg=25.0),
            ],
            spec(),
        )
        self.assertTrue(passed)
        self.assertIn("lo", reason)
        self.assertIn("hi", reason)
        self.assertIn("50.0 deg", reason)
        self.assertIn("25.0 deg", reason)


class RunnerAcIntegrationTests(unittest.TestCase):
    """`runner.patch_netlist`'s AC path and the null-supply_pattern case."""

    NETLIST = (
        "XXLF CP GND VCTRL loop_filter\n"
        "I1 GND CP dc 0 ac 1\n"
        ".lib /pdk/sky130.lib.spice tt\n"
        ".end\n"
    )
    MANIFEST = {
        "corner_pattern": r"(\.lib\s+\S*sky130\.lib\.spice\s+)(\w+)",
        "supply_pattern": None,
    }

    def test_null_supply_pattern_patches_corner_and_temp_only(self):
        point = PvtPoint(corner="hh", temp_c=125.0, supply_v=1.8)
        patched = runner.patch_netlist(self.NETLIST, self.MANIFEST, point)
        self.assertIn(".lib /pdk/sky130.lib.spice hh", patched)
        self.assertIn(".temp 125", patched)

    def test_missing_supply_pattern_key_behaves_like_null(self):
        point = PvtPoint(corner="ss", temp_c=27.0, supply_v=1.8)
        patched = runner.patch_netlist(self.NETLIST, {
            "corner_pattern": self.MANIFEST["corner_pattern"]
        }, point)
        self.assertIn(".lib /pdk/sky130.lib.spice ss", patched)

    def test_corner_pattern_is_still_mandatory(self):
        point = PvtPoint(corner="tt", temp_c=27.0, supply_v=1.8)
        with self.assertRaises(runner.NetlistError):
            runner.patch_netlist("no corner line here\n.end\n", self.MANIFEST, point)

    def test_ac_spec_injects_its_control_block_before_the_end_card(self):
        point = PvtPoint(corner="tt", temp_c=-40.0, supply_v=1.8)
        patched = runner.patch_netlist(
            self.NETLIST,
            self.MANIFEST,
            point,
            prefix="tt_-40c-",
            ac_spec=spec(),
        )
        self.assertIn("alter @i1[acmag]", patched)
        self.assertIn("ac dec 40 100 100meg", patched)
        self.assertIn("wrdata tt_-40c-ac000.raw v(phi)", patched)
        self.assertLess(patched.index(".endc"), patched.index(".end\n"))

    def test_no_ac_spec_means_no_control_block(self):
        point = PvtPoint(corner="tt", temp_c=27.0, supply_v=1.8)
        patched = runner.patch_netlist(self.NETLIST, self.MANIFEST, point)
        self.assertNotIn(".control", patched)


class LoopAcManifestTests(unittest.TestCase):
    """The shipped sim/loop-ac manifest must parse and stay self-consistent."""

    @classmethod
    def setUpClass(cls):
        import json

        path = SIM_DIR / "loop-ac" / "testbench" / "tb.json"
        cls.manifest = json.loads(path.read_text())
        cls.spec = acmeasure.AcSpec.from_manifest(cls.manifest)

    def test_manifest_parses_into_an_ac_spec(self):
        self.assertIsNotNone(self.spec)
        self.assertEqual(self.spec.node, "phi")
        self.assertEqual(self.spec.source, "I1")

    def test_every_loop_gain_point_states_its_basis(self):
        for g in self.spec.loop_gain:
            with self.subTest(label=g.label):
                self.assertNotIn("no basis stated", g.basis)
                self.assertGreater(len(g.basis), 40)

    def test_declares_no_supply_axis_because_the_dut_is_passive(self):
        self.assertIsNone(self.manifest["supply_pattern"])
        self.assertEqual(self.manifest["supply_tolerance"], 0)

    def test_runs_the_passive_skew_corners_the_ratified_set_omits(self):
        """The five DR-003 corners are all "nominal resistance, nominal
        capacitance" -- on a DUT with no transistors they are identical by
        construction, so the manifest must also run ll/hh or the corner axis
        would report an untested robustness."""
        corners = self.manifest["process_corners"]
        for ratified in ("tt", "ff", "ss", "sf", "fs"):
            self.assertIn(ratified, corners)
        self.assertIn("ll", corners)
        self.assertIn("hh", corners)

    def test_does_not_gate_on_draft_spec_bounds(self):
        self.assertFalse(self.spec.gate_on_bounds)
        self.assertIsNotNone(self.spec.phase_margin_floor_deg)
        self.assertIsNotNone(self.spec.f_c_ceiling_hz)


if __name__ == "__main__":
    unittest.main()
