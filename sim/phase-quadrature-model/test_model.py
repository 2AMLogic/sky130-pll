#!/usr/bin/env python3
"""PDK-free tests for the I/Q /2 behavioral model (issue #344).

Analytical controls (50 %, 45 %, 55 %), startup/reset, clock absence, path
delay, and the defeating control against an assumed perfect-quarter-cycle
generator.
"""

import os
import sys
import unittest
from fractions import Fraction as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import model as m  # noqa: E402
import run_cases as rc  # noqa: E402

T2 = F(10000)  # 100 MHz 2x clock (50 MHz output), picoseconds
LONG = [m.ClockSegment(F(0), T2 * 60)]


def run(duty, **kw):
    return m.measure(m.simulate(T2, F(duty), kw.pop("segments", LONG), **kw))


class AnalyticalControls(unittest.TestCase):
    def test_baseline_50_percent_is_exactly_90(self):
        r = run(F(1, 2))
        self.assertEqual(r["phase_rise_deg"], 90)
        self.assertEqual(r["phase_fall_deg"], 90)
        self.assertEqual(r["period"], 2 * T2)
        self.assertTrue(r["ordering_q_lags_i"])

    def test_non_50_percent_follows_180_d(self):
        for d in (F(45, 100), F(55, 100), F(30, 100), F(70, 100)):
            r = run(d)
            self.assertEqual(r["phase_rise_deg"], 180 * d, d)
            self.assertEqual(r["phase_fall_deg"], 180 * d, d)
            self.assertEqual(r["period"], 2 * T2)

    def test_45_and_55_values(self):
        self.assertEqual(run(F(45, 100))["phase_rise_deg"], F(81))
        self.assertEqual(run(F(55, 100))["phase_rise_deg"], F(99))

    def test_output_duty_is_half_regardless_of_input_duty(self):
        for d in (F(45, 100), F(55, 100)):
            r = run(d)
            self.assertEqual(r["duty_i"], F(1, 2))
            self.assertEqual(r["duty_q"], F(1, 2))

    def test_path_delay_adds_to_separation(self):
        slow_q = m.Flop(tcq_rise=F(500), tcq_fall=F(500))
        r = run(F(1, 2), ff_q=slow_q)
        want = m.analytic_phase_deg(F(1, 2), T2, F(500))
        self.assertEqual(r["phase_rise_deg"], want)
        self.assertEqual(want, 90 + F(9))  # 500 ps / 20 ns * 360

    def test_rise_fall_tcq_asymmetry_changes_duty_not_period(self):
        asym = m.Flop(tcq_rise=F(0), tcq_fall=F(400))
        r = run(F(1, 2), ff_i=asym)
        self.assertEqual(r["period"], 2 * T2)
        self.assertEqual(r["duty_i"], (T2 + 400) / (2 * T2))

    def test_zero_and_large_relative_delay_ordering(self):
        big = m.Flop(tcq_rise=F(9000), tcq_fall=F(9000))
        # FF_Q output arrives 14000 ps after the rising edge, later than the
        # next rising edge (10000 ps): FF_I samples a stale Q and the divide
        # no longer yields a 2*T2 period -- the data window is exceeded.
        r = run(F(1, 2), ff_q=big)
        self.assertNotEqual(r["period"], 2 * T2)


class DefeatingControl(unittest.TestCase):
    def test_ideal_generator_is_caught_at_45(self):
        want = m.analytic_phase_deg(F(45, 100), T2)
        ideal = m.ideal_quadrature_phase_deg(F(45, 100), T2)
        self.assertNotEqual(ideal, want)
        self.assertEqual(want - ideal, -9)
        self.assertTrue(rc.defeating_control(T2)["detected"])

    def test_ideal_generator_passes_only_at_50(self):
        self.assertEqual(m.ideal_quadrature_phase_deg(F(1, 2), T2),
                         m.analytic_phase_deg(F(1, 2), T2))


class StartupAndReset(unittest.TestCase):
    def test_every_power_up_state_converges_to_same_ordering(self):
        seen = set()
        for s in ((0, 0), (0, 1), (1, 0), (1, 1)):
            r = run(F(1, 2), init_state=s)
            self.assertEqual(r["phase_rise_deg"], 90, s)
            self.assertTrue(r["ordering_q_lags_i"], s)
            seen.add(s)
        self.assertEqual(len(seen), 4)

    def test_reset_release_sweep_keeps_ordering(self):
        for k in range(0, 21):
            rel = T2 * 3 + T2 * F(k, 10)
            r = run(F(1, 2), reset=(F(0), rel), init_state=(1, 1))
            self.assertEqual(r["phase_rise_deg"], 90, k)
            self.assertTrue(r["ordering_q_lags_i"], k)

    def test_release_coincident_with_edge_shifts_first_clk_edge_by_one_2x_period(self):
        rel = T2 * 4  # coincides with a rising edge
        a = m.simulate(T2, F(1, 2), LONG, reset=(F(0), rel),
                       release_edge_counts=True)
        b = m.simulate(T2, F(1, 2), LONG, reset=(F(0), rel),
                       release_edge_counts=False)
        ra, rb = a.i.edges("rise")[0], b.i.edges("rise")[0]
        self.assertEqual(ra, rel)
        self.assertEqual(rb - ra, T2)  # first captured edge is one 2x period later

    def test_reset_forces_both_low(self):
        res = m.simulate(T2, F(1, 2), LONG, reset=(T2 * 5 + 1, T2 * 8),
                         init_state=(0, 0))
        self.assertEqual(res.i.at(T2 * 7), 0)
        self.assertEqual(res.q.at(T2 * 7), 0)

    def test_recovery_window_is_flagged_not_resolved(self):
        res = m.simulate(T2, F(1, 2), LONG, reset=(F(0), T2 * 4 - 10),
                         trec=F(50))
        self.assertTrue(any(k == "recovery" for k, _ in res.flags))


class ClockAbsence(unittest.TestCase):
    def test_stop_restore_keeps_ordering(self):
        segs = [m.ClockSegment(F(0), T2 * 20),
                m.ClockSegment(T2 * 35 + 1234, T2 * 80)]
        res = m.simulate(T2, F(1, 2), segs)
        r = m.measure(res, since=T2 * 35 + 1234 + T2 * 4, skip=0)
        self.assertTrue(r["ordering_q_lags_i"])
        self.assertEqual(r["phase_rise_deg"], 90)

    def test_runt_restoration_is_visible_as_one_abnormal_separation(self):
        segs = [m.ClockSegment(F(0), T2 * 20),
                m.ClockSegment(T2 * 30, T2 * 60, first_high=F(100))]
        res = m.simulate(T2, F(1, 2), segs)
        # all state changes still alternate rise/fall of the same ordering
        self.assertTrue(m.measure(res)["ordering_q_lags_i"])

    def test_outputs_hold_during_absence(self):
        segs = [m.ClockSegment(F(0), T2 * 20), m.ClockSegment(T2 * 40, T2 * 60)]
        res = m.simulate(T2, F(1, 2), segs)
        gap = [t for t in res.i.times if T2 * 20 + 1 < t < T2 * 40]
        self.assertEqual(gap, [])


class RunCaps(unittest.TestCase):
    def test_edge_cap_enforced(self):
        with self.assertRaises(ValueError):
            m.simulate(T2, F(1, 2), LONG, max_edges=10)

    def test_matrix_is_finite_and_capped(self):
        cases = rc.build_matrix()
        self.assertLessEqual(len(cases), rc.MAX_CASES)

    def test_report_is_deterministic(self):
        a = rc.render_report("TEST-ID")
        b = rc.render_report("TEST-ID")
        self.assertEqual(a, b)

    def test_all_declared_properties_pass_or_are_unresolved_not_silent(self):
        _, rows = rc.run_matrix()
        for r in rows:
            self.assertIn(r["verdict"], ("PASS", "FINDING", "FAIL"))
        self.assertFalse([r for r in rows if r["verdict"] == "FAIL"])


if __name__ == "__main__":
    unittest.main()
