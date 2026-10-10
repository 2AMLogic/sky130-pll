#!/usr/bin/env python3
"""Unit tests for sim/harness/cpmeasure.py -- signed charge-pump analysis.

No PDK, no ngspice and no xschem required. Every dump below is synthesized
here from piecewise-linear current/gate waveforms with closed-form areas, then
sampled at irregular timestamps (piecewise-linear signals are reproduced
exactly by linear interpolation, so the trapezoid integral is exact). Expected
charges are computed from the construction (Icp * pulse length), not from
anything the reducer produced.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import copy
import math
import random
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import cpmeasure  # noqa: E402
from harness.cpmeasure import CpError, CpSpec  # noqa: E402
from harness.measure import MeasureError  # noqa: E402

VDD = 1.8
RAMP = 100e-12
PW = 0.5e-9  # reset-overlap pulse width of the synthetic PFD

MANIFEST = {
    "cp": {
        "clamp_source": "VCLAMP",
        "ref_source": "VREF",
        "div_source": "VDIV",
        "up_gate": {"node": "x1.up", "active": "high"},
        "dn_gate": {"node": "x1.dnb", "active": "low"},
        "frequency_hz": 10e6,
        "duty": 0.5,
        "rise_s": "100p",
        "fall_s": "100p",
        "first_edge_s": "100n",
        "vctrl_fractions": [0.1, 0.3, 0.5, 0.7, 0.9],
        "phase_offsets_s": ["-25n", "-0.1n", 0, "0.1n", "25n"],
        "settle_periods": 2,
        "integrate_periods": 4,
        "dump_step_s": "5p",
        "max_step_s": "5p",
        "op": {
            "vectors": [
                {"label": "NB", "expr": "v(x1.nb)"},
                {"label": "PB", "expr": "v(x1.pb)"},
                {"label": "IREF", "expr": "@r.x1.rbias[i]"},
            ]
        },
        "diagnostic": {
            "dump_step_s": "2.5p",
            "max_step_s": "2.5p",
            "vctrl_fraction": 0.5,
            "phase_offsets_s": ["-0.1n", 0, "0.1n"],
        },
    }
}


def make_spec(**overrides) -> CpSpec:
    m = copy.deepcopy(MANIFEST)
    m["cp"].update(overrides)
    return CpSpec.from_manifest(m)


def pwl(bps, t):
    """Evaluate a piecewise-linear breakpoint list [(t, v), ...] at `t`."""
    if t <= bps[0][0]:
        return bps[0][1]
    if t >= bps[-1][0]:
        return bps[-1][1]
    lo, hi = 0, len(bps) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if bps[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    (t0, v0), (t1, v1) = bps[lo], bps[hi]
    return v0 + (v1 - v0) * (t - t0) / (t1 - t0)


def pulse_bps(spans, level, base=0.0):
    """Trapezoid train with ramps centered on each span edge (area = level*len)."""
    bps = [(0.0, base)]
    for a, b in spans:
        bps += [(a - RAMP / 2, base), (a + RAMP / 2, level), (b - RAMP / 2, level), (b + RAMP / 2, base)]
    bps.append((1.0, base))
    return bps


def synth_dump(spec, offset, iup=100e-6, idn=100e-6, sign=1.0, seed=1, stop=None, stagger=False):
    """Text of a `t i(clamp) v(up) v(dnb)` dump for a PFD with overlap PW.

    With `stagger` the DN pulse follows the UP pulse in time instead of
    overlapping it, so opposing currents cannot cancel in the clamp current.
    Either way Qnet = Icp * offset for equal branch currents.
    """
    ups, dns = [], []
    k = 0
    while True:
        e = spec.ref_edge(k)
        if e > (stop or spec.stop_s):
            break
        end = e + max(offset, 0.0) + PW
        ups.append((e, end))
        if stagger:
            d0 = end + 1e-9
            dns.append((d0, d0 + PW + max(-offset, 0.0)))
        else:
            dns.append((e + offset, end))
        k += 1
    # Current = sign*(+iup on UP, -idn on DN); sum two trapezoid trains.
    up_c, dn_c = pulse_bps(ups, sign * iup), pulse_bps(dns, -sign * idn)
    up_g = pulse_bps(ups, VDD)  # active high
    dn_g = pulse_bps(dns, 0.0, base=VDD)  # active low gate
    knots = sorted({t for b in (up_c, dn_c, up_g, dn_g) for t, _ in b if t <= (stop or spec.stop_s)})
    rng = random.Random(seed)
    t_end = stop or spec.stop_s
    extra = sorted(rng.uniform(0, t_end) for _ in range(400))
    times = sorted(set(knots + extra + [0.0, t_end]))
    rows = []
    for t in times:
        i = pwl(up_c, t) + pwl(dn_c, t)
        rows.append(f"{t:.17e} {i:.17e} {pwl(up_g, t):.17e} {pwl(dn_g, t):.17e}")
    return "\n".join(rows) + "\n"


class ParserTests(unittest.TestCase):
    def test_valid_block_parses_with_units_and_literals(self):
        spec = make_spec()
        self.assertAlmostEqual(spec.period_s, 100e-9)
        self.assertAlmostEqual(spec.phase_offsets_s[0], -25e-9, delta=1e-18)
        self.assertEqual(spec.phase_offsets_s[2], 0.0)
        self.assertEqual(spec.vctrl_fractions[2], 0.5)
        self.assertEqual(spec.midrail_index(), 2)
        self.assertTrue(spec.up_gate.active_high)
        self.assertFalse(spec.dn_gate.active_high)
        self.assertEqual(spec.clamp_vector, "i(vclamp)")
        self.assertAlmostEqual(spec.window_start_s, 100e-9 + 2 * 100e-9)
        self.assertEqual(len(spec.cycle_windows()), 4)
        self.assertEqual(len(spec.op_vectors), 3)
        self.assertEqual(spec.diagnostic_coordinates(), [(2, 1), (2, 2), (2, 3)])

    def test_no_block_returns_none(self):
        self.assertIsNone(CpSpec.from_manifest({"measure": {}}))

    def test_incompatible_analysis_declarations_rejected(self):
        for other in ("measure", "ac"):
            m = copy.deepcopy(MANIFEST)
            m[other] = {"anything": 1}
            with self.assertRaisesRegex(CpError, "exactly one analysis"):
                CpSpec.from_manifest(m)

    def test_malformed_parameters_rejected(self):
        bad = [
            ({"frequency_hz": 0}, "frequency_hz"),
            ({"frequency_hz": float("nan")}, "not finite"),
            ({"duty": 1.0}, "duty"),
            ({"vctrl_fractions": [0.5, 0.3]}, "strictly increasing"),
            ({"vctrl_fractions": [0.5, 1.2]}, "lie in"),
            ({"vctrl_fractions": []}, "non-empty"),
            ({"phase_offsets_s": ["-25n", "25n", "25n", "0.1n", "-0.1n"]}, "duplicate"),
            ({"phase_offsets_s": ["-25n", "-0.1n", 0, "0.1n"]}, "does not sample"),
            ({"phase_offsets_s": ["-60n", "-25n", "-0.1n", "0.1n", "25n"]}, "half a period"),
            ({"settle_periods": True}, "settle_periods"),
            ({"integrate_periods": 0}, "integrate_periods"),
            ({"dump_step_s": "20n"}, "period/20"),
            ({"clamp_source": "bad name"}, "valid netlist name"),
            ({"up_gate": {"node": "x", "active": "up"}}, "active"),
            ({"bogus": 1}, "unknown key"),
            ({"first_edge_s": "10n"}, "no room"),
            ({"compliance_tolerance": 1.5}, "< 1"),
            ({"rise_s": "200n"}, "too long"),
            ({"op": {"vectors": [{"label": "A", "expr": "v(a); shell"}]}}, "plain ngspice"),
            ({"op": {"vectors": [{"label": "A", "expr": "v(a)"}, {"label": "A", "expr": "v(b)"}]}}, "duplicated"),
        ]
        for override, pattern in bad:
            with self.subTest(override=override):
                with self.assertRaisesRegex(MeasureError, pattern):
                    make_spec(**override)

    def test_missing_required_key_rejected(self):
        m = copy.deepcopy(MANIFEST)
        del m["cp"]["max_step_s"]
        with self.assertRaisesRegex(CpError, "max_step_s"):
            CpSpec.from_manifest(m)

    def test_diagnostic_must_be_finer_and_a_subset(self):
        d = dict(MANIFEST["cp"]["diagnostic"])
        with self.assertRaisesRegex(CpError, "finer"):
            make_spec(diagnostic={**d, "dump_step_s": "5p"})
        with self.assertRaisesRegex(CpError, "vctrl_fractions"):
            make_spec(diagnostic={**d, "vctrl_fraction": 0.55})
        with self.assertRaisesRegex(CpError, "subset"):
            make_spec(diagnostic={**d, "phase_offsets_s": ["3n"]})
        with self.assertRaisesRegex(CpError, "unknown"):
            make_spec(diagnostic={**d, "junk": 1})


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec()

    def test_stimulus_values_for_a_transient(self):
        text = cpmeasure.build_cp_control_block(self.spec, 1.62, prefix="p1_")
        lines = text.splitlines()
        self.assertEqual(lines[0], ".control")
        self.assertEqual(lines[-1], ".endc")
        self.assertIn("alter VCLAMP 0.162", lines)  # 0.1 * 1.62 V
        self.assertIn("alter VCLAMP 1.458", lines)  # 0.9 * 1.62 V
        # REF: high level is VDD, edge (50% crossing) at 100 ns => td 99.95 ns
        ref = [l for l in lines if l.startswith("alter VREF pulse")][-1]
        self.assertIn("pulse = [ 0 1.62 9.995e-08 1e-10 1e-10 4.99e-08 1e-07 ]", ref)
        # DIV for the +25 ns case is delayed by exactly 25 ns
        self.assertIn(
            "alter VDIV pulse = [ 0 1.62 1.2495e-07 1e-10 1e-10 4.99e-08 1e-07 ]", lines
        )
        # DIV for -25 ns leads
        self.assertIn(
            "alter VDIV pulse = [ 0 1.62 7.495e-08 1e-10 1e-10 4.99e-08 1e-07 ]", lines
        )
        # dump spacing and max internal step are the manifest's, stop = window end + 1 T
        stop = self.spec.window_end_s + self.spec.period_s
        self.assertIn(f"tran 5e-12 {stop:.10g} 0 5e-12", lines)
        self.assertIn(f"linearize i(vclamp) v(x1.up) v(x1.dnb)", lines)
        self.assertIn("set wr_singlescale", lines)
        self.assertIn(f'echo "{cpmeasure.COMPLETION_MARKER}"', lines)

    def test_op_outputs_are_separate_and_use_flat_stimulus(self):
        text = cpmeasure.build_cp_control_block(self.spec, 1.8, prefix="p1_")
        lines = text.splitlines()
        i_op = lines.index("op")
        self.assertIn("alter VCLAMP 0.9", lines[:i_op])
        self.assertIn("alter VREF pulse = [ 0 0 0 1e-10 1e-10 5e-08 1e-07 ]", lines[:i_op])
        self.assertIn("alter VDIV pulse = [ 0 0 0 1e-10 1e-10 5e-08 1e-07 ]", lines[:i_op])
        self.assertIn("wrdata p1_cp_op.raw v(x1.nb) v(x1.pb) @r.x1.rbias[i]", lines)
        save = [l for l in lines if l.startswith("save ")][0]
        self.assertIn("@r.x1.rbias[i]", save)
        self.assertIn("i(vclamp)", save)
        # the OP dump name is never a transient dump name
        names = cpmeasure.waveform_names(self.spec, "p1_")
        self.assertEqual(names.count("p1_cp_op.raw"), 1)

    def test_per_sweep_filenames_unique_and_cartesian(self):
        names = cpmeasure.waveform_names(self.spec, "p1_")
        self.assertEqual(len(names), len(set(names)))
        sweep = [n for n in names if n.startswith("p1_cp_v")]
        self.assertEqual(len(sweep), 5 * 5)
        self.assertIn("p1_cp_v02_p04.raw", sweep)
        self.assertTrue(all(n.endswith(".raw") for n in names))
        text = cpmeasure.build_cp_control_block(self.spec, 1.8, prefix="p1_")
        for n in names:
            self.assertEqual(text.count(f"wrdata {n} "), 1, n)

    def test_diagnostic_grid_uses_finer_steps_and_own_files(self):
        text = cpmeasure.build_cp_control_block(self.spec, 1.8, prefix="p1_")
        stop = self.spec.window_end_s + self.spec.period_s
        self.assertEqual(text.count(f"tran 2.5e-12 {stop:.10g} 0 2.5e-12"), 3)
        for name in ("p1_cpdiag_v02_p01.raw", "p1_cpdiag_v02_p02.raw", "p1_cpdiag_v02_p03.raw"):
            self.assertIn(f"wrdata {name} ", text)
        plain = cpmeasure.build_cp_control_block(self.spec, 1.8, "p1_", include_diagnostic=False)
        self.assertNotIn("cpdiag", plain)
        self.assertNotIn("2.5e-12", plain)

    def test_deterministic_and_rejects_bad_vdd(self):
        a = cpmeasure.build_cp_control_block(self.spec, 1.8)
        self.assertEqual(a, cpmeasure.build_cp_control_block(self.spec, 1.8))
        for bad in (0, -1.0, float("nan"), float("inf")):
            with self.assertRaises(CpError):
                cpmeasure.build_cp_control_block(self.spec, bad)

    def test_no_op_block_means_no_op_lines(self):
        m = copy.deepcopy(MANIFEST)
        del m["cp"]["op"]
        spec = CpSpec.from_manifest(m)
        text = cpmeasure.build_cp_control_block(spec, 1.8)
        self.assertNotIn("\nop\n", text)
        self.assertNotIn("cp_op.raw", text)


class IntegrationTests(unittest.TestCase):
    def test_rectangle_on_irregular_timestamps(self):
        # 3 A for 2 s sampled irregularly, with extra collinear points.
        t = [0.0, 0.3, 0.35, 1.1, 1.9, 2.0, 2.7]
        v = [3.0] * len(t)
        self.assertAlmostEqual(cpmeasure.integrate(t, v, 0.0, 2.0), 6.0, places=12)

    def test_triangle_analytic(self):
        t = [0.0, 1.0, 1.4, 3.0]
        v = [0.0, 2.0, 1.2, 0.0]  # exact: 1.0*2/2 + 0.4*(2+1.2)/2 + 1.6*1.2/2
        want = 1.0 + 0.64 + 0.96
        self.assertAlmostEqual(cpmeasure.integrate(t, v, 0.0, 3.0), want, places=12)

    def test_boundary_interpolation(self):
        t = [0.0, 1.0, 2.0]
        v = [0.0, 1.0, 1.0]  # ramp 0->1 then flat
        # window [0.5, 1.5]: ramp part 0.5..1 area = 0.5*(0.5+1)/2, flat 0.5
        self.assertAlmostEqual(cpmeasure.integrate(t, v, 0.5, 1.5), 0.375 + 0.5, places=12)
        # window inside a single segment
        self.assertAlmostEqual(cpmeasure.integrate(t, v, 0.2, 0.4), (0.2 + 0.4) / 2 * 0.2, places=12)

    def test_zero_crossing_split(self):
        t, v = [0.0, 2.0], [-1.0, 1.0]
        self.assertAlmostEqual(cpmeasure.integrate(t, v, 0, 2, "net"), 0.0, places=12)
        self.assertAlmostEqual(cpmeasure.integrate(t, v, 0, 2, "pos"), 0.5, places=12)
        self.assertAlmostEqual(cpmeasure.integrate(t, v, 0, 2, "neg"), 0.5, places=12)

    def test_window_outside_dump_or_bad_series_fails(self):
        t, v = [0.0, 1.0, 2.0], [1.0, 1.0, 1.0]
        with self.assertRaisesRegex(CpError, "exceeds"):
            cpmeasure.integrate(t, v, -0.1, 1.0)
        with self.assertRaisesRegex(CpError, "exceeds"):
            cpmeasure.integrate(t, v, 1.0, 2.1)
        with self.assertRaisesRegex(CpError, "reversed"):
            cpmeasure.integrate(t, v, 1.0, 1.0)
        with self.assertRaisesRegex(CpError, "unknown"):
            cpmeasure.integrate(t, v, 0, 1, "bogus")


class ParseDumpTests(unittest.TestCase):
    def test_roundtrip(self):
        spec = make_spec()
        t, i, up, dn = cpmeasure.parse_cp_tran(synth_dump(spec, 0.0))
        self.assertEqual(len(t), len(i))
        self.assertTrue(all(b > a for a, b in zip(t, t[1:])))

    def test_bad_dumps_are_explicit_failures(self):
        with self.assertRaisesRegex(CpError, "no samples"):
            cpmeasure.parse_cp_tran("")
        with self.assertRaisesRegex(CpError, "too short"):
            cpmeasure.parse_cp_tran("0 1 2 3\n")
        with self.assertRaisesRegex(CpError, "nonfinite"):
            cpmeasure.parse_cp_tran("0 1 2 3\n1 nan 2 3\n")
        with self.assertRaisesRegex(CpError, "nonfinite"):
            cpmeasure.parse_cp_tran("0 1 2 3\n1 inf 2 3\n")
        with self.assertRaisesRegex(CpError, "strictly increasing"):
            cpmeasure.parse_cp_tran("0 1 2 3\n0 1 2 3\n")
        with self.assertRaisesRegex(CpError, "columns"):
            cpmeasure.parse_cp_tran("0 1 2\n1 1 2\n")

    def test_op_parse(self):
        self.assertEqual(cpmeasure.parse_cp_op("0 0.7 1.1 2e-5\n", 3), [0.7, 1.1, 2e-5])
        with self.assertRaisesRegex(CpError, "exactly 1"):
            cpmeasure.parse_cp_op("0 1\n1 2\n", 1)
        with self.assertRaisesRegex(CpError, "nonfinite"):
            cpmeasure.parse_cp_op("0 nan\n", 1)


class PointReductionTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec()
        self.j0 = self.spec.offset_index(0.0)

    def reduce(self, offset, vi=2, **kw):
        pj = self.spec.offset_index(offset)
        return cpmeasure.reduce_cp_point(self.spec, VDD, vi, pj, synth_dump(self.spec, offset, **kw))

    def test_zero_offset_balance(self):
        r = self.reduce(0.0, stagger=True)
        self.assertTrue(r.available, r.reason)
        icp = 100e-6
        self.assertAlmostEqual(r.qnet_mean_c, 0.0, delta=1e-20)
        self.assertAlmostEqual(r.qplus_mean_c, icp * PW, delta=1e-18)
        self.assertAlmostEqual(r.qminus_mean_c, icp * PW, delta=1e-18)
        self.assertAlmostEqual(r.asymmetry, 0.0, delta=1e-9)
        self.assertEqual(len(r.cycles), 4)
        self.assertTrue(r.settled)
        # coordinates retained
        self.assertEqual((r.coord.vctrl_index, r.coord.phase_index), (2, self.j0))
        self.assertAlmostEqual(r.coord.vctrl_v, 0.9)

    def test_mismatch_gives_signed_asymmetry(self):
        r = self.reduce(0.0, iup=110e-6, idn=90e-6, stagger=True)
        want = (110 - 90) / (110 + 90)
        self.assertAlmostEqual(r.asymmetry, want, places=9)
        self.assertAlmostEqual(r.qnet_mean_c, 20e-6 * PW, delta=1e-18)

    def test_overlapping_equal_branches_cancel_and_are_unavailable(self):
        # Documented limitation: simultaneous opposing branch currents cancel
        # in the clamp current, so the reducer sees no charge at all and must
        # report the asymmetry as unavailable, not as perfect matching.
        r = self.reduce(0.0)
        self.assertAlmostEqual(r.qplus_mean_c, 0.0, delta=1e-20)
        self.assertAlmostEqual(r.qminus_mean_c, 0.0, delta=1e-20)
        self.assertIsNone(r.asymmetry)
        self.assertIn("undefined", r.asymmetry_reason)
        # Unequal overlapping branches leave only the residual.
        m = self.reduce(0.0, iup=110e-6, idn=90e-6)
        self.assertAlmostEqual(m.qplus_mean_c, 20e-6 * PW, delta=1e-18)
        self.assertAlmostEqual(m.asymmetry, 1.0, places=9)

    def test_current_inversion_flips_net_charge(self):
        a = self.reduce(0.1e-9, iup=110e-6, idn=90e-6, stagger=True)
        b = self.reduce(0.1e-9, iup=110e-6, idn=90e-6, sign=-1.0, stagger=True)
        self.assertAlmostEqual(a.qnet_mean_c, -b.qnet_mean_c, delta=1e-20)
        self.assertGreater(a.qnet_mean_c, 0.0)
        self.assertAlmostEqual(a.qplus_mean_c, b.qminus_mean_c, delta=1e-20)
        self.assertAlmostEqual(a.asymmetry, -b.asymmetry, places=9)
        # an inverted clamp makes the expected-sign check fail, visibly
        inv = self.reduce(25e-9, sign=-1.0)
        self.assertFalse(inv.plateau.sign_ok)

    def test_known_phase_response_slope(self):
        icp = 100e-6
        for off in (-0.1e-9, 0.1e-9):
            r = self.reduce(off)
            self.assertAlmostEqual(r.qnet_mean_c, icp * off, delta=1e-18)
        spec = self.spec
        dumps = {
            cpmeasure.sweep_dump_name(vi, pj): synth_dump(spec, spec.phase_offsets_s[pj])
            for vi in range(5)
            for pj in range(5)
        }
        res = cpmeasure.reduce_cp_sweep(spec, VDD, dumps)
        for s in res.slopes:
            self.assertTrue(s.available, s.reason)
            self.assertAlmostEqual(s.slope_c_per_s, icp, delta=icp * 1e-6)
        # raw curve is retained: Qnet is linear in offset
        for pj, off in enumerate(spec.phase_offsets_s):
            self.assertAlmostEqual(res.point(2, pj).qnet_mean_c, icp * off, delta=1e-17)

    def test_plateaus_signed_and_directional(self):
        up = self.reduce(25e-9, iup=120e-6, idn=100e-6)
        dn = self.reduce(-25e-9, iup=120e-6, idn=100e-6)
        self.assertEqual(up.plateau.direction, "UP")
        self.assertAlmostEqual(up.plateau.current_a, 120e-6, delta=1e-12)
        self.assertAlmostEqual(up.plateau.magnitude_a, 120e-6, delta=1e-12)
        self.assertTrue(up.plateau.sign_ok)
        self.assertEqual(dn.plateau.direction, "DN")
        self.assertAlmostEqual(dn.plateau.current_a, -100e-6, delta=1e-12)
        self.assertAlmostEqual(dn.plateau.magnitude_a, 100e-6, delta=1e-12)
        self.assertTrue(dn.plateau.sign_ok)
        self.assertEqual(up.plateau.n_pulses, 4)

    def test_plateau_ignores_nonplateau_edges(self):
        # The middle half of the 25.5 ns UP-exclusive pulse excludes the
        # overlap/reset portion where the DN current opposes the UP current.
        r = self.reduce(25e-9, iup=100e-6, idn=50e-6)
        self.assertAlmostEqual(r.plateau.current_a, 100e-6, delta=1e-12)

    def test_min_pulse_widths(self):
        r = self.reduce(0.0)
        self.assertAlmostEqual(r.min_up_width_s, PW, delta=1e-12)
        self.assertAlmostEqual(r.min_dn_width_s, PW, delta=1e-12)
        w = self.reduce(0.1e-9)
        self.assertAlmostEqual(w.min_up_width_s, PW + 0.1e-9, delta=1e-12)
        self.assertAlmostEqual(w.min_dn_width_s, PW, delta=1e-12)

    def test_absent_plateau_is_unavailable_not_zero(self):
        # An offset-0 style dump at the +25 ns slot: gates never exclusive.
        text = synth_dump(self.spec, 0.0)
        pj = self.spec.offset_index(25e-9)
        r = cpmeasure.reduce_cp_point(self.spec, VDD, 2, pj, text)
        self.assertTrue(r.available)
        self.assertFalse(r.plateau.available)
        self.assertIn("no exclusive UP plateau", r.plateau.reason)
        self.assertIsNone(r.plateau.current_a)

    def test_zero_denominator_is_unavailable_asymmetry(self):
        zero = "\n".join(
            f"{t:.12e} 0 0 {VDD}" for t in [i * 1e-9 for i in range(0, 800)]
        )
        pj = self.j0
        r = cpmeasure.reduce_cp_point(self.spec, VDD, 2, pj, zero + "\n")
        self.assertTrue(r.available)
        self.assertEqual(r.qnet_mean_c, 0.0)
        self.assertIsNone(r.asymmetry)
        self.assertIn("undefined", r.asymmetry_reason)

    def test_short_missing_nonfinite_dumps_are_unavailable_with_coordinates(self):
        pj = self.j0
        short = synth_dump(self.spec, 0.0, stop=self.spec.window_end_s - 50e-9)
        for text, pattern in (
            (short, "exceeds"),
            ("", "no samples"),
            ("0 1 0 0\n1e-9 nan 0 0\n", "nonfinite"),
            ("0 1 0 0\n", "too short"),
        ):
            with self.subTest(pattern=pattern):
                r = cpmeasure.reduce_cp_point(self.spec, VDD, 1, pj, text)
                self.assertFalse(r.available)
                self.assertRegex(r.reason, pattern)
                self.assertEqual((r.coord.vctrl_index, r.coord.phase_index), (1, pj))
                self.assertIsNone(r.qnet_mean_c)

    def test_unsettled_startup_is_recorded(self):
        # Pump current ramps up cycle by cycle: last cycle charge differs a lot.
        spec = self.spec
        base = synth_dump(spec, 0.1e-9)
        rows = []
        for line in base.splitlines():
            t, i, u, d = (float(x) for x in line.split())
            scale = 0.2 if t < spec.ref_edge(spec.settle_periods + 2) else 1.0
            rows.append(f"{t:.17e} {i * scale:.17e} {u:.17e} {d:.17e}")
        r = cpmeasure.reduce_cp_point(spec, VDD, 2, spec.offset_index(0.1e-9), "\n".join(rows) + "\n")
        self.assertTrue(r.available)
        self.assertFalse(r.settled)
        self.assertGreater(r.qnet_std_c, 0.0)


class SweepTests(unittest.TestCase):
    def dumps(self, spec, up_by_frac, dn_by_frac, drop=()):
        out = {}
        for vi, f in enumerate(spec.vctrl_fractions):
            for pj, off in enumerate(spec.phase_offsets_s):
                name = cpmeasure.sweep_dump_name(vi, pj)
                if name in drop:
                    continue
                out[name] = synth_dump(spec, off, iup=up_by_frac[f], idn=dn_by_frac[f])
        return out

    def test_compliance_windows_are_sampled_contiguous_and_directional(self):
        spec = make_spec(diagnostic=None)
        up = {0.1: 50e-6, 0.3: 95e-6, 0.5: 100e-6, 0.7: 109e-6, 0.9: 80e-6}
        dn = {0.1: 60e-6, 0.3: 92e-6, 0.5: 100e-6, 0.7: 85e-6, 0.9: 100e-6}
        res = cpmeasure.reduce_cp_sweep(spec, VDD, self.dumps(spec, up, dn))
        c = res.compliance
        self.assertTrue(c.up.available, c.up.reason)
        self.assertEqual((c.up.lo_fraction, c.up.hi_fraction), (0.3, 0.7))
        self.assertAlmostEqual(c.up.lo_v, 0.3 * VDD)
        self.assertEqual(c.up.n_points, 3)
        self.assertAlmostEqual(c.up.mid_magnitude_a, 100e-6, delta=1e-12)
        # DN: 0.7 is outside 10%; 0.9 is back inside but not contiguous
        self.assertEqual((c.dn.lo_fraction, c.dn.hi_fraction), (0.3, 0.5))
        self.assertEqual((c.both.lo_fraction, c.both.hi_fraction), (0.3, 0.5))
        # signed values and magnitudes both kept
        pl = res.point(2, spec.offset_index(-25e-9)).plateau
        self.assertAlmostEqual(pl.current_a, -100e-6, delta=1e-12)

    def test_missing_dump_keeps_coordinates_and_reason(self):
        spec = make_spec(diagnostic=None)
        flat = {f: 100e-6 for f in spec.vctrl_fractions}
        drop = {cpmeasure.sweep_dump_name(1, 3)}
        res = cpmeasure.reduce_cp_sweep(spec, VDD, self.dumps(spec, flat, flat, drop=drop))
        bad = res.point(1, 3)
        self.assertFalse(bad.available)
        self.assertIn("dump missing", bad.reason)
        self.assertEqual(bad.coord.vctrl_fraction, 0.3)
        self.assertAlmostEqual(bad.coord.offset_s, 0.1e-9, delta=1e-18)
        self.assertFalse(res.slopes[1].available)
        self.assertIn("slope pair unavailable", res.slopes[1].reason)
        self.assertTrue(res.slopes[2].available)

    def test_invalid_midrail_makes_windows_unavailable(self):
        spec = make_spec(diagnostic=None)
        flat = {f: 100e-6 for f in spec.vctrl_fractions}
        drop = {cpmeasure.sweep_dump_name(2, spec.offset_index(25e-9))}
        res = cpmeasure.reduce_cp_sweep(spec, VDD, self.dumps(spec, flat, flat, drop=drop))
        self.assertFalse(res.compliance.up.available)
        self.assertIn("midrail", res.compliance.up.reason)
        self.assertTrue(res.compliance.dn.available)
        self.assertFalse(res.compliance.both.available)

    def test_midrail_not_sampled_is_unavailable(self):
        spec = make_spec(diagnostic=None, vctrl_fractions=[0.2, 0.4, 0.6, 0.8])
        flat = {f: 100e-6 for f in spec.vctrl_fractions}
        res = cpmeasure.reduce_cp_sweep(spec, VDD, self.dumps(spec, flat, flat))
        self.assertFalse(res.compliance.up.available)
        self.assertIn("not a sampled", res.compliance.up.reason)

    def test_inverted_polarity_never_yields_a_window(self):
        spec = make_spec(diagnostic=None)
        out = {}
        for vi in range(5):
            for pj, off in enumerate(spec.phase_offsets_s):
                out[cpmeasure.sweep_dump_name(vi, pj)] = synth_dump(spec, off, sign=-1.0)
        res = cpmeasure.reduce_cp_sweep(spec, VDD, out)
        self.assertFalse(res.compliance.up.available)
        self.assertFalse(res.compliance.dn.available)

    def test_prefix_and_op_and_resolution(self):
        spec = make_spec()
        flat = {f: 100e-6 for f in spec.vctrl_fractions}
        raw = self.dumps(spec, flat, flat)
        dumps = {f"p9_{k}": v for k, v in raw.items()}
        for vi, pj in spec.diagnostic_coordinates():
            off = spec.phase_offsets_s[pj]
            dumps[cpmeasure.sweep_dump_name(vi, pj, "p9_", diagnostic=True)] = synth_dump(spec, off, seed=7)
        dumps["p9_cp_op.raw"] = "0 0.62 1.1 2.5e-5\n"
        res = cpmeasure.reduce_cp_sweep(spec, VDD, dumps, prefix="p9_")
        self.assertTrue(res.op.available, res.op.reason)
        self.assertEqual(res.op.values[0], ("NB", "v(x1.nb)", 0.62))
        self.assertEqual(res.op.values[2][2], 2.5e-5)
        self.assertEqual(len(res.resolution), 3)
        for d in res.resolution:
            self.assertTrue(d.available, d.reason)
            self.assertFalse(d.material)
            self.assertTrue(d.converged)
            self.assertAlmostEqual(d.dqnet_c, 0.0, delta=1e-19)

    def test_material_change_or_sign_flip_is_not_converged(self):
        spec = make_spec()
        flat = {f: 100e-6 for f in spec.vctrl_fractions}
        dumps = self.dumps(spec, flat, flat)
        for vi, pj in spec.diagnostic_coordinates():
            off = spec.phase_offsets_s[pj]
            dumps[cpmeasure.sweep_dump_name(vi, pj, diagnostic=True)] = synth_dump(
                spec, off, sign=-1.0 if off > 0 else 1.0, iup=150e-6 if off == 0 else 100e-6
            )
        res = cpmeasure.reduce_cp_sweep(spec, VDD, dumps)
        by_off = {round(d.coord.offset_s * 1e12): d for d in res.resolution}
        self.assertTrue(by_off[100].sign_changed)
        self.assertFalse(by_off[100].converged)
        self.assertTrue(by_off[0].material)
        self.assertFalse(by_off[0].converged)
        self.assertFalse(by_off[-100].material)

    def test_missing_op_and_diagnostic_dumps_are_unavailable(self):
        spec = make_spec()
        flat = {f: 100e-6 for f in spec.vctrl_fractions}
        res = cpmeasure.reduce_cp_sweep(spec, VDD, self.dumps(spec, flat, flat))
        self.assertFalse(res.op.available)
        self.assertIn("dump missing", res.op.reason)
        self.assertTrue(all(not d.available for d in res.resolution))
        self.assertTrue(all(d.converged is None for d in res.resolution))
        bad = cpmeasure.reduce_op(spec, "0 nan 1 2\n")
        self.assertFalse(bad.available)


if __name__ == "__main__":
    unittest.main()
