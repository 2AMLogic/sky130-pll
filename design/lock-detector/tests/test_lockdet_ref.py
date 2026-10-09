"""Deterministic edge-stream tests for the DR-007 behavioral reference.

Every expected LOCK transition below is a literal time derived by hand in the
comment next to it, not recomputed from the model's own formulas. These are
behavioral-reference results only: ideal edges, no cell delay, no PVT.

Run (stdlib only):
    python3 -m unittest discover -s design/lock-detector/tests -p 'test_*.py'

Common scenario unless a test says otherwise
--------------------------------------------
- RESETB low at t=0, released at 50 ns.
- REF 10 MHz (T = 100 ns), 50 % duty: rising edge r_k = 100 ns + k*100 ns,
  falling edge f_k = r_k + 50 ns, k = 0, 1, ...
- f_0 = 150 ns is the first fall after reset: it opens the history and is not
  evaluated. Evaluation j happens at f_j = 150 ns + j*100 ns and pairs r_j
  with the FBCLK edges in (f_(j-1), f_j].
- Qualification Q = 32, release R = 4, w_acq = 2.5 ns, w_rel = 6.0 ns,
  watchdog 250 ns period at phase 0, timeout 16 ticks.
- Hence a clean acquisition asserts LOCK at f_32 = 150 + 3200 ns = 3.35 us.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lockdet_ref as ld  # noqa: E402
from lockdet_ref import (  # noqa: E402
    Contract, Stimulus, Transition, Watchdog, fb_from_offsets, ref_clock, simulate,
)

NS = 1_000
US = 1_000_000
T10 = 100 * NS
RESET = ((0, 0), (50 * NS, 1))
NO_FREQ = Contract(frequency_qualification=False)
NO_TIMEOUT = Contract(timeouts_enabled=False)


def up(t, cause="qualified"):
    return Transition(t, 1, cause)


def down(t, cause):
    return Transition(t, 0, cause)


def run(offsets, cycles=300, contract=Contract(), wd=Watchdog(), resetb=RESET,
        ref=None, fb=None, t_end=None):
    rr, rf = ref if ref is not None else ref_clock(100 * NS, T10, cycles)
    if fb is None:
        fb = fb_from_offsets(rr, offsets)
    end = t_end if t_end is not None else rf[-1]
    return simulate(Stimulus(rr, rf, tuple(fb), t_end_ps=end, resetb=resetb), contract, wd)


class ContractValues(unittest.TestCase):
    """Pin the provisional numbers to DR-007 and check the band invariants."""

    def test_nominal_values_match_dr007(self):
        c, w = Contract(), Watchdog()
        self.assertEqual((c.w_acq_ps, c.w_rel_ps), (2_500, 6_000))
        self.assertEqual((c.qualify_cycles, c.release_cycles), (32, 4))
        self.assertEqual((c.timeout_ticks, w.period_ps), (16, 250_000))
        self.assertTrue(c.frequency_qualification and c.timeouts_enabled)

    def test_band_invariants(self):
        # Hysteresis survives PVT: widest acquisition < narrowest release.
        self.assertLess(ld.W_ACQ_BAND_PS[1], ld.W_REL_BAND_PS[0])
        # Release window stays inside the REF-falling-edge pairing interval at
        # the shortest REF period and either duty extreme: 0.3 * 40 ns = 12 ns.
        self.assertLess(ld.W_REL_BAND_PS[1],
                        ld.REF_PERIOD_MIN_PS * ld.REF_DUTY_MIN_PCT // 100)
        # Nominal values sit inside their bands.
        c = Contract()
        self.assertTrue(ld.W_ACQ_BAND_PS[0] <= c.w_acq_ps <= ld.W_ACQ_BAND_PS[1])
        self.assertTrue(ld.W_REL_BAND_PS[0] <= c.w_rel_ps <= ld.W_REL_BAND_PS[1])
        # Earliest possible timeout (fastest watchdog, timeout fires after more
        # than 15 ticks) exceeds the slowest REF period: 15 * 125 ns = 1.875 us.
        fastest = (c.timeout_ticks - 1) * ld.WD_PERIOD_BAND_PS[0]
        self.assertEqual(fastest, 1_875_000)
        self.assertGreater(fastest, ld.REF_PERIOD_MAX_PS)
        # Latest timeout (slowest watchdog): 16 * 500 ns = 8 us.
        self.assertEqual(c.timeout_ticks * ld.WD_PERIOD_BAND_PS[1], 8 * US)

    def test_invalid_contract_rejected(self):
        with self.assertRaises(ValueError):
            Contract(w_acq_ps=6_000, w_rel_ps=6_000)
        with self.assertRaises(ValueError):
            Watchdog(period_ps=100, phase_ps=100)
        with self.assertRaises(ValueError):
            simulate(Stimulus((0, 10), (5, 7), (), 20))  # REF not alternating


class Acquisition(unittest.TestCase):
    def test_clean_acquisition(self):
        self.assertEqual(run(lambda k: 0).transitions, [up(3_350_000)])

    def test_acquisition_after_frequency_settling_and_sustained_lock(self):
        # r_0..r_9 at +20 ns (BAD: |e| > 6 ns); good from k=10 with a
        # deterministic +/-2.5 ns pattern. Evaluations j=10..41 are the 32
        # GOOD ones -> LOCK at f_41 = 150 + 4100 ns. Then 2000 more cycles of
        # the same pattern: no further transition (sustained lock).
        pattern = (2_500, -2_500, 1_000, -1_000, 0)
        res = run(lambda k: 20 * NS if k < 10 else pattern[k % 5], cycles=2100)
        self.assertEqual(res.transitions, [up(4_250_000)])
        self.assertEqual(res.final_lock, 1)

    def test_reset_release_latency(self):
        # Reset release at 50 ns; first REF rise 100 ns; LOCK = first fall
        # after release (no evaluation) + 32 REF periods = 150 ns + 3.2 us.
        res = run(lambda k: 0)
        self.assertEqual(res.lock_at(3_349_999), 0)
        self.assertEqual(res.lock_at(3_350_000), 1)
        self.assertEqual(res.evaluations[0].t_ps, 250 * NS)


class Thresholds(unittest.TestCase):
    def test_acquisition_threshold_inclusive(self):
        for e in (2_500, -2_500):
            with self.subTest(e=e):
                self.assertEqual(run(lambda k: e).transitions, [up(3_350_000)])

    def test_acquisition_threshold_just_outside(self):
        # 2.501 ns is in the hysteresis band: never qualifies.
        for e in (2_501, -2_501):
            with self.subTest(e=e):
                self.assertEqual(run(lambda k: e).transitions, [])

    def test_release_threshold_inclusive_holds(self):
        # Locked at 3.35 us with e=0, then |e| = 6.000 ns from k=50 onward.
        for e in (6_000, -6_000, 4_000):
            with self.subTest(e=e):
                res = run(lambda k: 0 if k < 50 else e)
                self.assertEqual(res.transitions, [up(3_350_000)])

    def test_release_threshold_just_outside_releases(self):
        # |e| = 6.001 ns from k=50: BAD at j=50,51,52,53 -> release at
        # f_53 = 150 + 5300 ns = 5.45 us.
        for e in (6_001, -6_001):
            with self.subTest(e=e):
                res = run(lambda k: 0 if k < 50 else e)
                self.assertEqual(res.transitions,
                                 [up(3_350_000), down(5_450_000, "release")])

    def test_hysteresis_marginal_does_not_relock(self):
        # Release at 5.45 us (6.001 ns for k=50..59), then 4 ns (marginal) for
        # k=60..149: no re-lock. e=0 from k=150: GOOD j=150..181 -> LOCK at
        # f_181 = 150 + 18100 ns.
        def off(k):
            if k < 50:
                return 0
            if k < 60:
                return 6_001
            if k < 150:
                return 4_000
            return 0
        res = run(off)
        self.assertEqual(res.transitions, [up(3_350_000), down(5_450_000, "release"),
                                           up(18_250_000)])


class Reset(unittest.TestCase):
    def test_reset_during_qualification(self):
        # 18 GOOD evaluations (j=1..18) before RESETB falls at 2.0 us. Release
        # at 2.2 us coincides with r_21 (RESETB processed first, so the edge
        # counts). f_21 = 2.25 us opens history; GOOD j=22..53 -> LOCK at
        # f_53 = 5.45 us. The un-reset LOCK time 3.35 us must not appear.
        resetb = ((0, 0), (50 * NS, 1), (2 * US, 0), (2_200 * NS, 1))
        res = run(lambda k: 0, resetb=resetb)
        self.assertEqual(res.transitions, [up(5_450_000)])

    def test_reset_during_lock(self):
        # LOCK falls exactly at the RESETB fall (async, 5.0 us). Release at
        # 5.02 us; f_49 = 5.05 us opens history; LOCK at f_81 = 8.25 us.
        resetb = ((0, 0), (50 * NS, 1), (5 * US, 0), (5_020 * NS, 1))
        res = run(lambda k: 0, resetb=resetb)
        self.assertEqual(res.transitions,
                         [up(3_350_000), down(5_000_000, "reset"), up(8_250_000)])

    def test_held_in_reset_never_locks(self):
        res = run(lambda k: 0, resetb=((0, 0),))
        self.assertEqual(res.transitions, [])
        self.assertEqual(res.evaluations, [])


class DroppedAndExtraEdges(unittest.TestCase):
    def test_single_dropped_fb_edge_in_lock_is_filtered(self):
        res = run(lambda k: None if k == 50 else 0)
        self.assertEqual(res.transitions, [up(3_350_000)])

    def test_three_dropped_fb_edges_in_lock_are_filtered(self):
        res = run(lambda k: None if 50 <= k <= 52 else 0)
        self.assertEqual(res.transitions, [up(3_350_000)])

    def test_four_dropped_fb_edges_release_then_relock(self):
        # BAD j=50..53 -> release at f_53 = 5.45 us. GOOD j=54..85 -> f_85.
        res = run(lambda k: None if 50 <= k <= 53 else 0)
        self.assertEqual(res.transitions, [up(3_350_000), down(5_450_000, "release"),
                                           up(8_650_000)])

    def test_dropped_fb_edge_during_qualification_restarts_count(self):
        # GOOD j=1..19, BAD j=20, GOOD j=21..52 -> LOCK at f_52 = 5.35 us.
        res = run(lambda k: None if k == 20 else 0)
        self.assertEqual(res.transitions, [up(5_350_000)])

    def test_dropped_ref_cycle_in_lock_is_filtered(self):
        # REF misses one whole cycle (no r_50 / f_50); FBCLK keeps running.
        # The evaluation at f_51 sees two FBCLK edges (BAD once), then GOOD.
        rr, rf = ref_clock(100 * NS, T10, 300)
        fb = fb_from_offsets(rr, lambda k: 0)
        ref = (rr[:50] + rr[51:], rf[:50] + rf[51:])
        res = run(None, ref=ref, fb=fb)
        self.assertEqual(res.transitions, [up(3_350_000)])
        bad = [ev for ev in res.evaluations if ev.cls == ld.BAD]
        self.assertEqual([(ev.t_ps, ev.n_fb) for ev in bad], [(rf[51], 2)])

    def test_extra_fb_edge_in_lock_is_filtered(self):
        rr, rf = ref_clock(100 * NS, T10, 300)
        fb = sorted(fb_from_offsets(rr, lambda k: 0) + (rr[60] + 30 * NS,))
        res = run(None, ref=(rr, rf), fb=fb)
        self.assertEqual(res.transitions, [up(3_350_000)])


class StoppedClocks(unittest.TestCase):
    # Last REF/FBCLK rising edge before a stop is r_79 = 8.0 us, which lies on
    # a watchdog tick (8.0 us / 250 ns = 32). The 16th tick strictly after it
    # is 8.0 + 16 * 0.25 = 12.0 us.

    def test_ref_stops_fb_runs(self):
        rr, rf = ref_clock(100 * NS, T10, 300)
        fb = fb_from_offsets(rr, lambda k: 0)
        res = run(None, ref=(rr[:80], rf[:80]), fb=fb, t_end=30 * US)
        self.assertEqual(res.transitions,
                         [up(3_350_000), down(12_000_000, "ref_timeout")])

    def test_fb_stops_ref_runs(self):
        # REF keeps evaluating: BAD j=80..83 -> release at f_83 = 8.45 us,
        # before the 12.0 us FBCLK timeout (which then changes nothing).
        res = run(lambda k: 0 if k < 80 else None)
        self.assertEqual(res.transitions, [up(3_350_000), down(8_450_000, "release")])

    def test_both_stop_together(self):
        # Both counters reach 16 at the 12.0 us tick; REF is processed first.
        rr, rf = ref_clock(100 * NS, T10, 80)
        fb = fb_from_offsets(rr, lambda k: 0)
        res = run(None, ref=(rr, rf), fb=fb, t_end=30 * US)
        self.assertEqual(res.transitions,
                         [up(3_350_000), down(12_000_000, "ref_timeout")])

    def test_fb_stop_at_1mhz_timer_quantization_extremes(self):
        # REF 1 MHz: r_k = 1 us + k us, f_k = r_k + 0.5 us. LOCK at f_32 =
        # 33.5 us. FBCLK stops after r_39 = 40 us. REF-side release would come
        # at f_43 = 44.5 us; the FBCLK timeout is 16 ticks after 40 us:
        #   fast 125 ns -> 42.0 us (timeout first)
        #   nominal 250 ns -> 44.0 us (timeout first)
        #   slow 500 ns -> 48.0 us (release at 44.5 us comes first)
        rr, rf = ref_clock(1 * US, 1 * US, 80)
        fb = fb_from_offsets(rr, lambda k: 0 if k < 40 else None)
        cases = ((125_000, down(42_000_000, "fb_timeout")),
                 (250_000, down(44_000_000, "fb_timeout")),
                 (500_000, down(44_500_000, "release")))
        for period, expected in cases:
            with self.subTest(wd_period=period):
                res = run(None, ref=(rr, rf), fb=fb, wd=Watchdog(period))
                self.assertEqual(res.transitions, [up(33_500_000), expected])

    def test_fastest_watchdog_never_false_times_out_at_slowest_ref(self):
        # 1 MHz REF, 125 ns ticks: an REF gap is 8 ticks, well under 16.
        rr, rf = ref_clock(1 * US, 1 * US, 200)
        res = run(lambda k: 0, ref=(rr, rf), wd=Watchdog(125_000))
        self.assertEqual(res.transitions, [up(33_500_000)])

    def test_watchdog_phase_quantization(self):
        # Ticks at 1 ps + j * 250 ns. First tick strictly after 8.0 us is
        # 8.000001 us; the 16th is 8.000001 + 15 * 0.25 = 11.750001 us, i.e.
        # the timeout elapsed time sits at the short end of (15, 16] ticks.
        rr, rf = ref_clock(100 * NS, T10, 300)
        fb = fb_from_offsets(rr, lambda k: 0)
        res = run(None, ref=(rr[:80], rf[:80]), fb=fb, t_end=30 * US,
                  wd=Watchdog(250_000, 1))
        self.assertEqual(res.transitions,
                         [up(3_350_000), down(11_750_001, "ref_timeout")])

    def test_timeout_boundary_edge_vs_tick(self):
        # REF pauses after r_79 = 8.0 us and resumes at 10 MHz from t_r.
        # FBCLK runs continuously on the 100 ns grid (an edge at 12.0 us).
        rr, rf = ref_clock(100 * NS, T10, 300)
        fb = fb_from_offsets(rr, lambda k: 0)
        # t_r = 11.999999 us: the 16th tick (12.0 us) never arrives before the
        # edge. One BAD evaluation (40 FBCLK edges in the long interval) is
        # filtered by R; LOCK holds throughout.
        r2, f2 = ref_clock(11_999_999, T10, 150)
        res = run(None, ref=(rr[:80] + r2, rf[:80] + f2), fb=fb)
        self.assertEqual(res.transitions, [up(3_350_000)])
        # t_r = 12.0 us: the tick is processed before the coincident edge, so
        # the timeout fires at 12.0 us. History restarts: f = 12.05 us opens
        # it; LOCK again at 12.05 + 32 * 0.1 = 15.25 us.
        r2, f2 = ref_clock(12 * US, T10, 150)
        res = run(None, ref=(rr[:80] + r2, rf[:80] + f2), fb=fb)
        self.assertEqual(res.transitions, [up(3_350_000), down(12_000_000, "ref_timeout"),
                                           up(15_250_000)])


class Restart(unittest.TestCase):
    def test_ref_restart(self):
        # REF stops after r_79, restarts at 20.0 us on the FBCLK grid. Timeout
        # at 12.0 us; 20.05 us opens history; LOCK at 20.05 + 3.2 = 23.25 us.
        rr, rf = ref_clock(100 * NS, T10, 300)
        fb = fb_from_offsets(rr, lambda k: 0)
        r2, f2 = ref_clock(20 * US, T10, 100)
        res = run(None, ref=(rr[:80] + r2, rf[:80] + f2), fb=fb)
        self.assertEqual(res.transitions, [up(3_350_000), down(12_000_000, "ref_timeout"),
                                           up(23_250_000)])

    def test_both_restart(self):
        rr, rf = ref_clock(100 * NS, T10, 80)
        r2, f2 = ref_clock(20 * US, T10, 100)
        ref = (rr + r2, rf + f2)
        fb = fb_from_offsets(ref[0], lambda k: 0)
        res = run(None, ref=ref, fb=fb)
        self.assertEqual(res.transitions, [up(3_350_000), down(12_000_000, "ref_timeout"),
                                           up(23_250_000)])

    def test_fb_restart(self):
        # FBCLK absent for k=80..199: release at 8.45 us (REF-side). FBCLK
        # back at r_200: GOOD j=200..231 -> LOCK at f_231 = 23.25 us.
        res = run(lambda k: None if 80 <= k < 200 else 0)
        self.assertEqual(res.transitions, [up(3_350_000), down(8_450_000, "release"),
                                           up(23_250_000)])


class CycleSlip(unittest.TestCase):
    def test_full_cycle_slip_releases_and_reacquires(self):
        # Aligned through r_49; FBCLK then runs at 102 ns for 50 periods
        # (phase walks +2 ns per REF cycle) and slips exactly one REF cycle,
        # landing on r_100; then 100 ns again.
        #   e_50..e_52 = 2, 4, 6 ns (not BAD); e_53..e_56 > 6 ns -> release
        #   at f_56 = 5.75 us.
        #   Re-entry: e_96 = -8 (BAD), e_97 = -6, e_98 = -4 (MARGINAL),
        #   e_99 = -2 (GOOD), e_100 = 0 ... GOOD j=99..130 -> f_130 = 13.15 us.
        rr, rf = ref_clock(100 * NS, T10, 300)
        fb = list(rr[:50])
        fb += [rr[49] + 102 * NS * i for i in range(1, 51)]
        while fb[-1] + T10 <= rf[-1]:
            fb.append(fb[-1] + T10)
        res = run(None, ref=(rr, rf), fb=fb)
        self.assertEqual(res.transitions, [up(3_350_000), down(5_750_000, "release"),
                                           up(13_150_000)])

    def test_persistent_frequency_error_never_locks(self):
        # FBCLK at 102 ns from the start (2 % slow): phase sweeps through the
        # acquisition window in at most 3 consecutive GOOD cycles.
        rr, rf = ref_clock(100 * NS, T10, 600)
        fb = [rr[0] + 102 * NS * i for i in range(590)]
        res = run(None, ref=(rr, rf), fb=fb)
        self.assertEqual(res.transitions, [])
        self.assertLessEqual(max(ev.q for ev in res.evaluations), 3)


class Harmonics(unittest.TestCase):
    """Coincident edges alone must never qualify lock."""

    @staticmethod
    def fb_2x(cycles=300):
        # FBCLK at 20 MHz, zero phase: an FBCLK edge coincides with every REF
        # rising edge, and a second one sits at each REF falling edge.
        return [100 * NS + i * 50 * NS for i in range(2 * cycles)]

    def test_2_to_1_rejected(self):
        res = run(None, fb=self.fb_2x())
        self.assertEqual(res.transitions, [])
        self.assertTrue(all(ev.n_fb == 2 and ev.cls == ld.BAD for ev in res.evaluations))

    def test_1_to_2_rejected(self):
        res = run(lambda k: 0 if k % 2 == 0 else None)
        self.assertEqual(res.transitions, [])

    def test_harmonics_rejected_at_25mhz_and_duty_extremes(self):
        for duty in (30, 70):
            rr, rf = ref_clock(100 * NS, 40 * NS, 300, duty)
            with self.subTest(duty=duty, ratio="2:1"):
                fb = [100 * NS + i * 20 * NS for i in range(600)]
                self.assertEqual(run(None, ref=(rr, rf), fb=fb).transitions, [])
            with self.subTest(duty=duty, ratio="1:2"):
                fb = fb_from_offsets(rr, lambda k: 0 if k % 2 == 0 else None)
                self.assertEqual(run(None, ref=(rr, rf), fb=fb).transitions, [])


class NegativeControls(unittest.TestCase):
    """Each control removes one mechanism and shows the case it exists for."""

    def test_without_frequency_qualification_2_to_1_is_accepted(self):
        # Pure coincidence: nearest FBCLK edge to r_k has e = 0 -> GOOD every
        # cycle -> LOCK at 3.35 us, exactly as if locked at 1:1.
        res = run(None, fb=Harmonics.fb_2x(), contract=NO_FREQ)
        self.assertEqual(res.transitions, [up(3_350_000)])

    def test_without_frequency_qualification_1_to_2_is_accepted(self):
        # Odd evaluations carry no FBCLK edge (no information); even ones are
        # GOOD; the 32nd GOOD is j=64 -> f_64 = 6.55 us.
        res = run(lambda k: 0 if k % 2 == 0 else None, contract=NO_FREQ)
        self.assertEqual(res.transitions, [up(6_550_000)])

    def test_without_timeouts_stopped_ref_is_missed(self):
        rr, rf = ref_clock(100 * NS, T10, 300)
        fb = fb_from_offsets(rr, lambda k: 0)
        res = run(None, ref=(rr[:80], rf[:80]), fb=fb, t_end=100 * US,
                  contract=NO_TIMEOUT)
        self.assertEqual(res.transitions, [up(3_350_000)])
        self.assertEqual(res.final_lock, 1)

    def test_without_timeouts_both_stopped_is_missed(self):
        rr, rf = ref_clock(100 * NS, T10, 80)
        fb = fb_from_offsets(rr, lambda k: 0)
        res = run(None, ref=(rr, rf), fb=fb, t_end=100 * US, contract=NO_TIMEOUT)
        self.assertEqual(res.final_lock, 1)

    def test_without_timeouts_fb_stop_still_caught_by_ref_cycles(self):
        # FBCLK loss with REF running does not need the watchdog.
        res = run(lambda k: 0 if k < 80 else None, contract=NO_TIMEOUT)
        self.assertEqual(res.transitions, [up(3_350_000), down(8_450_000, "release")])


class RefRangeExtremes(unittest.TestCase):
    def test_1mhz_acquisition(self):
        # f_32 = 1 us + 32 us + 0.5 us.
        rr, rf = ref_clock(1 * US, 1 * US, 60)
        res = run(lambda k: 0, ref=(rr, rf))
        self.assertEqual(res.transitions, [up(33_500_000)])

    def test_25mhz_duty_extremes(self):
        # T = 40 ns, r_k = 100 + 40k ns, f_k = r_k + 12 ns (30 %) / 28 ns (70 %).
        # LOCK at f_32 = 100 + 1280 + {12, 28} ns. Phase 6.001 ns from k=50 on
        # the side nearer the pairing-interval edge -> release at f_53 =
        # 100 + 2120 + {12, 28} ns.
        cases = ((30, 6_001, 1_392_000, 2_232_000), (70, -6_001, 1_408_000, 2_248_000))
        for duty, e, t_up, t_down in cases:
            with self.subTest(duty=duty):
                rr, rf = ref_clock(100 * NS, 40 * NS, 200, duty)
                for acq in (2_500, -2_500):
                    res = run(lambda k: acq, ref=(rr, rf))
                    self.assertEqual(res.transitions, [up(t_up)])
                res = run(lambda k: 0 if k < 50 else e, ref=(rr, rf))
                self.assertEqual(res.transitions, [up(t_up), down(t_down, "release")])

    def test_25mhz_30pct_lag_just_inside_pairing_interval(self):
        # e = +11.999 ns still pairs with r_k (interval ends at r_k + 12 ns):
        # n = 1 and BAD by phase, never locks; no edge mis-pairing.
        rr, rf = ref_clock(100 * NS, 40 * NS, 200, 30)
        res = run(lambda k: 11_999, ref=(rr, rf))
        self.assertEqual(res.transitions, [])
        self.assertTrue(all(ev.n_fb == 1 and ev.e_ps == 11_999 for ev in res.evaluations))


if __name__ == "__main__":
    unittest.main()
