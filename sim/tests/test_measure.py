#!/usr/bin/env python3
"""Unit tests for sim/harness/measure.py -- the derived-measurement layer.

No PDK, no ngspice and no xschem required: every test below drives the
extraction functions from a *synthetic* transient trace it builds itself, so
the arithmetic is checked against a waveform whose true frequency, duty cycle
and lock instant are known by construction rather than read back out of a
simulator.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import measure  # noqa: E402


def square_wave(
    *,
    freq_hz: float,
    duty: float = 0.5,
    duration_s: float,
    step_s: float,
    v_low: float = 0.0,
    v_high: float = 1.8,
    edge_s: float = 0.0,
    t0_s: float = 0.0,
):
    """A sampled square wave with (optionally) finite-slope edges.

    Returns (times, values). `edge_s` linearly ramps each transition so the
    trace looks like a real CMOS clock rather than an ideal step -- the
    threshold-crossing interpolation has to land in the middle of that ramp.
    """
    period = 1.0 / freq_hz
    high_s = duty * period
    times, values = [], []
    n = int(round(duration_s / step_s)) + 1
    for i in range(n):
        t = i * step_s
        if t < t0_s:
            times.append(t)
            values.append(v_low)
            continue
        phase = math.fmod(t - t0_s, period)
        if edge_s <= 0.0:
            v = v_high if phase < high_s else v_low
        elif phase < edge_s:
            v = v_low + (v_high - v_low) * (phase / edge_s)
        elif phase < high_s:
            v = v_high
        elif phase < high_s + edge_s:
            v = v_high - (v_high - v_low) * ((phase - high_s) / edge_s)
        else:
            v = v_low
        times.append(t)
        values.append(v)
    return times, values


def wave_from_periods(
    periods,
    *,
    step_s: float,
    edge_s: float,
    duty: float = 0.5,
    v_low: float = 0.0,
    v_high: float = 1.8,
    t0_s: float = 0.0,
):
    """A sampled trapezoidal clock whose k-th cycle has period `periods[k]`.

    The companion to `square_wave` for jitter work: instead of one fixed
    frequency it takes an explicit period sequence, so a trace can carry a
    *known* injected period modulation and the extractor can be checked
    against an analytically-computed answer rather than against itself.

    Each transition is a linear ramp of width `edge_s`, so the reducer's
    linear interpolation of the 50 % crossing recovers the injected edge time
    exactly (up to float rounding) instead of being quantized to `step_s`.
    The k-th rising edge's 50 % crossing sits at
    `t0_s + sum(periods[:k]) + edge_s / 2`, a constant offset that cancels out
    of every period difference.
    """
    starts, t = [], t0_s
    for p in periods:
        starts.append(t)
        t += p
    total_s = t
    times, values = [], []
    n = int(total_s / step_s) + 1
    k = 0
    for i in range(n):
        ti = i * step_s
        if ti < t0_s:
            times.append(ti)
            values.append(v_low)
            continue
        while k + 1 < len(starts) and ti >= starts[k + 1]:
            k += 1
        phase = ti - starts[k]
        period = periods[k]
        high_s = duty * period
        if phase < edge_s:
            v = v_low + (v_high - v_low) * (phase / edge_s)
        elif phase < high_s:
            v = v_high
        elif phase < high_s + edge_s:
            v = v_high - (v_high - v_low) * ((phase - high_s) / edge_s)
        else:
            v = v_low
        times.append(ti)
        values.append(v)
    return times, values


def edges_from_periods(periods, t0_s: float = 0.0):
    """Rising-edge times for a cycle sequence with the given periods."""
    edges, t = [t0_s], t0_s
    for p in periods:
        t += p
        edges.append(t)
    return edges


class TimeSuffixTests(unittest.TestCase):
    def test_spice_suffixes(self):
        self.assertAlmostEqual(measure.parse_spice_time("50p"), 50e-12)
        self.assertAlmostEqual(measure.parse_spice_time("200n"), 200e-9)
        self.assertAlmostEqual(measure.parse_spice_time("40u"), 40e-6)
        self.assertAlmostEqual(measure.parse_spice_time("1.5m"), 1.5e-3)
        self.assertAlmostEqual(measure.parse_spice_time("2ns"), 2e-9)
        self.assertAlmostEqual(measure.parse_spice_time("3"), 3.0)

    def test_meg_is_not_milli(self):
        # SPICE's classic footgun: "m" is milli, "meg" is 1e6.
        self.assertAlmostEqual(measure.parse_spice_time("1meg"), 1e6)
        self.assertAlmostEqual(measure.parse_spice_time("1m"), 1e-3)

    def test_rejects_garbage(self):
        with self.assertRaises(measure.MeasureError):
            measure.parse_spice_time("later")


class WrdataParsingTests(unittest.TestCase):
    """ngspice `wrdata` emits whitespace-separated `x y` pairs, one row per
    sample, with no header. Blank lines and a trailing newline are normal."""

    SAMPLE = (
        " 0.00000000e+00  1.80000000e+00 \n"
        " 5.00000000e-11  1.79000000e+00 \n"
        "\n"
        " 1.00000000e-10  0.00000000e+00 \n"
    )

    def test_parses_two_columns(self):
        times, values = measure.parse_wrdata(self.SAMPLE)
        self.assertEqual(times, [0.0, 5e-11, 1e-10])
        self.assertEqual(values, [1.8, 1.79, 0.0])

    def test_empty_dump_raises(self):
        with self.assertRaises(measure.MeasureError):
            measure.parse_wrdata("\n\n")


class EdgeExtractionTests(unittest.TestCase):
    def test_rising_edge_count_matches_the_synthetic_wave(self):
        times, values = square_wave(freq_hz=250e6, duration_s=100e-9, step_s=50e-12)
        rising, falling = measure.edge_times(times, values, threshold=0.9)
        # 100 ns at 250 MHz = 25 cycles. The wave starts high at t=0, so the
        # first sample is already above threshold and is not counted as a
        # rising edge -- but the sample at exactly t=100 ns opens cycle 26,
        # which is: 25 falling edges (2, 6, ... 98 ns) and 25 rising edges
        # (4, 8, ... 100 ns).
        self.assertEqual(len(rising), 25)
        self.assertEqual(len(falling), 25)
        self.assertAlmostEqual(rising[0], 4e-9, delta=100e-12)
        self.assertAlmostEqual(falling[0], 2e-9, delta=100e-12)

    def test_crossing_time_is_interpolated_inside_the_ramp(self):
        # One 100 MHz cycle with 1 ns edges starting at t=10 ns: the 50 %
        # crossing of the rising edge is at 10 ns + 0.5 ns.
        times, values = square_wave(
            freq_hz=100e6, duration_s=40e-9, step_s=20e-12, edge_s=1e-9, t0_s=10e-9
        )
        rising, _ = measure.edge_times(times, values, threshold=0.9)
        self.assertAlmostEqual(rising[0], 10.5e-9, delta=30e-12)

    def test_hysteresis_rejects_a_ripple_that_recrosses_the_threshold(self):
        # A clean rising edge followed by ringing that dips back through the
        # 50 % threshold but never reaches the lower hysteresis rail.
        times = [0.0, 1e-9, 2e-9, 3e-9, 4e-9, 5e-9, 6e-9]
        values = [0.0, 1.8, 0.85, 1.8, 1.8, 1.8, 1.8]
        naive, _ = measure.edge_times(times, values, threshold=0.9, hysteresis=0.0)
        self.assertEqual(len(naive), 2)
        damped, _ = measure.edge_times(times, values, threshold=0.9, hysteresis=0.45)
        self.assertEqual(len(damped), 1)

    def test_a_flat_trace_has_no_edges(self):
        times = [i * 1e-11 for i in range(100)]
        values = [1.8] * 100
        rising, falling = measure.edge_times(times, values, threshold=0.9)
        self.assertEqual(rising, [])
        self.assertEqual(falling, [])


class TransitionTimeTests(unittest.TestCase):
    """`transition_times` -- issue #186's rise/fall extractor. `square_wave`'s
    `edge_s` ramps linearly from `v_low` to `v_high` over that whole width, so
    the true 10-90% duration of every edge is `0.8 * edge_s` by construction
    -- known ground truth, not a value read back out of the extractor itself.
    """

    def test_rise_and_fall_recover_the_known_ramp_width(self):
        edge_s = 200e-12
        times, values = square_wave(
            freq_hz=100e6, duration_s=200e-9, step_s=2e-12, edge_s=edge_s
        )
        rises, falls = measure.transition_times(times, values, 0.0, 1.8)
        self.assertGreater(len(rises), 5)
        self.assertGreater(len(falls), 5)
        for d in rises + falls:
            self.assertAlmostEqual(d, 0.8 * edge_s, delta=edge_s * 0.02)

    def test_a_coarse_grid_still_resolves_a_multi_step_edge(self):
        # The edge spans many dump-grid steps (step_s << edge_s), so each
        # level's crossing lands inside a different sample pair -- the
        # multi-sample-step case sim/jitter-floor's variant C exercises.
        edge_s = 1e-9
        times, values = square_wave(
            freq_hz=20e6, duration_s=200e-9, step_s=20e-12, edge_s=edge_s
        )
        rises, falls = measure.transition_times(times, values, 0.0, 1.8)
        self.assertGreater(len(rises), 2)
        for d in rises + falls:
            self.assertAlmostEqual(d, 0.8 * edge_s, delta=edge_s * 0.01)

    def test_frac_lo_must_be_less_than_frac_hi(self):
        with self.assertRaises(measure.MeasureError):
            measure.transition_times([0.0, 1e-9], [0.0, 1.8], 0.0, 1.8, frac_lo=0.9, frac_hi=0.1)

    def test_a_reversal_before_the_far_level_drops_the_edge(self):
        # Rises past the 10% level, then falls back below it and stays there
        # -- not a completed rising transition, so it must not be counted
        # (and, unlike the fixture below, there is no later excursion that
        # could complete a *different* valid rise instead).
        times = [0.0, 1e-9, 2e-9, 3e-9]
        values = [0.0, 0.3, 0.1, 0.1]
        rises, falls = measure.transition_times(times, values, 0.0, 1.8)
        self.assertEqual(rises, [])
        self.assertEqual(falls, [])

    def test_only_edges_at_or_after_t_from_are_counted(self):
        edge_s = 200e-12
        times, values = square_wave(
            freq_hz=100e6, duration_s=200e-9, step_s=2e-12, edge_s=edge_s
        )
        all_rises, _ = measure.transition_times(times, values, 0.0, 1.8)
        later_rises, _ = measure.transition_times(
            times, values, 0.0, 1.8, t_from=100e-9
        )
        self.assertLess(len(later_rises), len(all_rises))
        self.assertGreater(len(later_rises), 0)

    def test_a_flat_trace_has_no_transitions(self):
        times = [i * 1e-11 for i in range(100)]
        values = [1.8] * 100
        rises, falls = measure.transition_times(times, values, 0.0, 1.8)
        self.assertEqual(rises, [])
        self.assertEqual(falls, [])

    def test_a_custom_20_80_fraction_pair_scales_the_recovered_duration(self):
        edge_s = 200e-12
        times, values = square_wave(
            freq_hz=100e6, duration_s=200e-9, step_s=2e-12, edge_s=edge_s
        )
        rises, _ = measure.transition_times(
            times, values, 0.0, 1.8, frac_lo=0.2, frac_hi=0.8
        )
        for d in rises:
            self.assertAlmostEqual(d, 0.6 * edge_s, delta=edge_s * 0.02)


class FrequencyAndDutyTests(unittest.TestCase):
    def test_mean_frequency_of_a_known_wave(self):
        times, values = square_wave(freq_hz=250e6, duration_s=200e-9, step_s=20e-12)
        rising, _ = measure.edge_times(times, values, threshold=0.9)
        f = measure.mean_frequency(rising)
        self.assertAlmostEqual(f, 250e6, delta=250e6 * 1e-3)

    def test_mean_frequency_needs_two_edges(self):
        self.assertIsNone(measure.mean_frequency([1e-9]))
        self.assertIsNone(measure.mean_frequency([]))

    def test_duty_cycle_of_a_40_percent_wave(self):
        times, values = square_wave(
            freq_hz=100e6, duty=0.4, duration_s=200e-9, step_s=10e-12
        )
        rising, falling = measure.edge_times(times, values, threshold=0.9)
        d = measure.duty_cycle(rising, falling)
        self.assertAlmostEqual(d, 0.40, delta=0.005)

    def test_duty_cycle_is_none_without_a_complete_high_pulse(self):
        self.assertIsNone(measure.duty_cycle([1e-9], []))


class LockDetectionTests(unittest.TestCase):
    """The lock criterion is: the output is locked at time t when the mean
    frequency over *every* sliding window of `window_cycles` consecutive
    output cycles starting at or after t stays inside +/- `tolerance_frac` of
    the target, through the end of the simulated window. Time-to-lock is the
    earliest such t."""

    SPEC = measure.LockSpec(
        target_hz=250e6, tolerance_frac=0.02, window_cycles=10, min_hold_cycles=20
    )

    @staticmethod
    def _chirp_edges(*, start_hz, end_hz, settle_at_s, total_s):
        """Rising-edge times for an output that ramps linearly from
        `start_hz` to `end_hz` over [0, settle_at_s] and then holds."""
        t = 0.0
        edges = [t]
        while t < total_s:
            if t < settle_at_s:
                f = start_hz + (end_hz - start_hz) * (t / settle_at_s)
            else:
                f = end_hz
            t += 1.0 / f
            edges.append(t)
        return edges

    def test_locks_after_the_chirp_settles(self):
        edges = self._chirp_edges(
            start_hz=150e6, end_hz=250e6, settle_at_s=2e-6, total_s=6e-6
        )
        locked, t_lock = measure.lock_time(edges, self.SPEC)
        self.assertTrue(locked)
        self.assertIsNotNone(t_lock)
        # The last out-of-band sliding window ends just after the chirp does.
        self.assertGreater(t_lock, 1.5e-6)
        self.assertLess(t_lock, 2.5e-6)

    def test_a_run_that_never_reaches_the_target_does_not_lock(self):
        edges = self._chirp_edges(
            start_hz=150e6, end_hz=180e6, settle_at_s=2e-6, total_s=6e-6
        )
        locked, t_lock = measure.lock_time(edges, self.SPEC)
        self.assertFalse(locked)
        self.assertIsNone(t_lock)

    def test_settling_too_late_to_hold_does_not_count_as_locked(self):
        # Out of band for the whole run except the final 12 cycles -- fewer
        # than min_hold_cycles, so without that term the last sliding window
        # would trivially qualify and the point would be reported as locked.
        # This is exactly the "silently report the last simulated frequency as
        # if it had locked" failure the criterion has to rule out.
        edges = self._chirp_edges(
            start_hz=150e6, end_hz=150e6, settle_at_s=1e-6, total_s=6e-6
        )
        t = edges[-1]
        for _ in range(12):
            t += 1.0 / 250e6
            edges.append(t)
        locked, t_lock = measure.lock_time(edges, self.SPEC)
        self.assertFalse(locked)
        self.assertIsNone(t_lock)

    def test_the_same_run_with_enough_held_cycles_does_lock(self):
        # Companion to the test above: identical shape, but the in-band tail
        # is long enough to satisfy min_hold_cycles, so it must lock. Pins
        # that the guard rejects short tails, not in-band data generally.
        edges = self._chirp_edges(
            start_hz=150e6, end_hz=150e6, settle_at_s=1e-6, total_s=6e-6
        )
        t = edges[-1]
        for _ in range(200):
            t += 1.0 / 250e6
            edges.append(t)
        locked, t_lock = measure.lock_time(edges, self.SPEC)
        self.assertTrue(locked)
        self.assertIsNotNone(t_lock)

    def test_losing_lock_before_the_end_is_not_locked(self):
        stable = self._chirp_edges(
            start_hz=250e6, end_hz=250e6, settle_at_s=1e-6, total_s=3e-6
        )
        drift = self._chirp_edges(
            start_hz=250e6, end_hz=150e6, settle_at_s=2e-6, total_s=2e-6
        )
        edges = stable + [stable[-1] + d for d in drift[1:]]
        locked, _ = measure.lock_time(edges, self.SPEC)
        self.assertFalse(locked)

    def test_too_few_edges_is_not_locked(self):
        locked, t_lock = measure.lock_time([0.0, 4e-9, 8e-9], self.SPEC)
        self.assertFalse(locked)
        self.assertIsNone(t_lock)


class PeriodJitterTests(unittest.TestCase):
    """`spec/target-spec.md` row 9, RATIFIED by DR-006: the standard deviation
    of the measured period over a population of consecutive post-lock output
    cycles, divided by that population's mean period.

    Every case below injects a period modulation whose RMS-over-mean is known
    *analytically*, so the extractor is checked against ground truth rather
    than against its own output on a previous run.
    """

    T0 = 4e-9  # 250 MHz

    def test_a_perfectly_uniform_edge_train_has_zero_jitter(self):
        edges = edges_from_periods([self.T0] * 200)
        frac, n_cycles = measure.period_jitter(edges)
        self.assertEqual(n_cycles, 200)
        self.assertAlmostEqual(frac, 0.0, places=12)

    def test_alternating_period_modulation_recovers_its_own_amplitude(self):
        # T_k alternates T0*(1+a), T0*(1-a) over an even number of cycles, so
        # the population mean is exactly T0 and the population standard
        # deviation is exactly T0*a -- the jitter is therefore exactly `a`.
        a = 0.02
        periods = [self.T0 * (1 + a), self.T0 * (1 - a)] * 100
        frac, n_cycles = measure.period_jitter(edges_from_periods(periods))
        self.assertEqual(n_cycles, 200)
        self.assertAlmostEqual(frac, a, places=12)

    def test_sinusoidal_period_modulation_matches_a_over_root_two(self):
        # T_k = T0*(1 + a*sin(2*pi*k/M)) over an integer number of modulation
        # cycles: the mean of sin over whole cycles is 0 and the mean of sin^2
        # is exactly 1/2, so the population standard deviation is T0*a/sqrt(2)
        # and the mean period is exactly T0. The jitter is therefore a/sqrt(2)
        # -- a different, independent analytic answer from the square-wave
        # case above, which pins that the extractor is computing an RMS rather
        # than a peak-to-peak or a mean-absolute deviation.
        a, m_cycle, n_modulation_cycles = 0.03, 8, 25
        periods = [
            self.T0 * (1 + a * math.sin(2 * math.pi * k / m_cycle))
            for k in range(m_cycle * n_modulation_cycles)
        ]
        frac, n_cycles = measure.period_jitter(edges_from_periods(periods))
        self.assertEqual(n_cycles, 200)
        self.assertAlmostEqual(frac, a / math.sqrt(2.0), places=12)

    def test_the_population_starts_after_the_lock_instant(self):
        # 200 cycles at 150 MHz (nowhere near the 250 MHz target) followed by
        # 400 clean +/-0.5 % cycles. The whole-trace jitter is enormous; the
        # post-lock jitter is exactly the 0.5 % that was injected after lock.
        # The window start comes from `lock_time`, not from a second "has it
        # settled" rule invented here.
        a = 0.005
        periods = [1.0 / 150e6] * 200 + [
            self.T0 * (1 + a), self.T0 * (1 - a)
        ] * 200
        edges = edges_from_periods(periods)
        lock_spec = measure.LockSpec(
            target_hz=250e6, tolerance_frac=0.05, window_cycles=10, min_hold_cycles=20
        )
        locked, t_lock = measure.lock_time(edges, lock_spec)
        self.assertTrue(locked)
        self.assertAlmostEqual(t_lock, edges[200], places=15)

        whole, _ = measure.period_jitter(edges)
        self.assertGreater(whole, 0.10)

        frac, n_cycles = measure.period_jitter(edges, t_from=t_lock)
        self.assertEqual(n_cycles, 400)
        self.assertAlmostEqual(frac, a, places=12)

    def test_a_population_of_fewer_than_two_cycles_reports_no_number(self):
        # Two edges is one period, which has no deviation to speak of; one
        # edge is no period at all. Neither may be reported as "zero jitter".
        frac, n_cycles = measure.period_jitter([1e-9, 5e-9])
        self.assertIsNone(frac)
        self.assertEqual(n_cycles, 1)
        frac, n_cycles = measure.period_jitter([1e-9])
        self.assertIsNone(frac)
        self.assertEqual(n_cycles, 0)
        frac, n_cycles = measure.period_jitter([])
        self.assertIsNone(frac)
        self.assertEqual(n_cycles, 0)

    def test_t_from_past_the_end_of_the_trace_does_not_throw(self):
        edges = edges_from_periods([self.T0] * 50)
        frac, n_cycles = measure.period_jitter(edges, t_from=1.0)
        self.assertIsNone(frac)
        self.assertEqual(n_cycles, 0)


class DumpGridResolutionFloorTests(unittest.TestCase):
    """The resolution floor the dump grid puts under `period_jitter` (#178).

    `build_control_block` `linearize`s the measured node onto the manifest's
    `tran_step` grid before dumping it, and `edge_times` interpolates each
    crossing between the two grid samples that bracket it. Every case below
    hands the reducer a clock of **exactly constant period** -- true period
    jitter zero by construction -- sampled onto a stated grid, so whatever it
    reports is the floor and nothing else.

    **Scope, stated because it is easy to over-read.** These cases exercise
    only the Python half of the path: the interpolation in `edge_times` on an
    already-uniform grid. They do *not* exercise ngspice's own `linearize`
    resampling of its adaptive-timestep data onto that grid. The committed
    `sim/jitter-floor/` records are what close that gap -- they run this same
    waveform family through the real simulator, and
    `test_the_floor_matches_the_committed_jitter_floor_records` below asserts
    that these synthetic traces reproduce all five of them to within 0.01
    percentage points, which is the evidence that `linearize` contributes
    nothing measurable and that the floor is this interpolation.
    """

    #: `sim/pll-lock-mc`'s own dump grid, and the grid every committed
    #: `sim/jitter-floor` record ran at.
    STEP = 200e-12

    #: Ratified row 9 (`DR-006`), as a fraction of the output period.
    ROW_9 = 0.01

    #: One row per committed `sim/jitter-floor` record: the variant's pulse
    #: period and transition time (read from that record's own committed
    #: per-point netlist) and the period jitter the record reports for it.
    #:
    #:   A1 20260925-022153-30889a3   A2 20260925-022310-30889a3
    #:   A3 20260925-022043-30889a3   B  20260925-022424-30889a3
    #:   C  20260925-022516-30889a3
    COMMITTED_RECORDS = (
        ("A1", 3.9952e-9, 20e-12, 0.00381),
        ("A2", 3.9904e-9, 20e-12, 0.00720),
        ("A3", 3.9170e-9, 20e-12, 0.02371),
        ("B", 3.9170e-9, 200e-12, 0.00610),
        ("C", 3.9170e-9, 1000e-12, 0.00000),
    )

    def floor_for(self, *, period_s, edge_s, step_s=None, duration_s=5e-6):
        """The jitter the reducer reports for a jitter-free clock on a grid."""
        step_s = self.STEP if step_s is None else step_s
        times, values = square_wave(
            freq_hz=1.0 / period_s,
            duration_s=duration_s,
            step_s=step_s,
            edge_s=edge_s,
        )
        rising, _ = measure.edge_times(times, values, 0.9, 0.27)
        frac, n_cycles = measure.period_jitter(rising)
        self.assertIsNotNone(frac, "the synthetic trace produced no jitter figure")
        self.assertGreater(n_cycles, 100)
        return frac

    def test_a_period_commensurate_with_the_grid_has_no_floor(self):
        # 4.000 ns is exactly 20 grid steps, so every edge is quantized
        # identically and every measured period is identical -- the floor
        # vanishes for arithmetic reasons, not because the measurement is good.
        self.assertAlmostEqual(
            self.floor_for(period_s=4.0e-9, edge_s=20e-12), 0.0, places=12
        )

    def test_an_edge_the_grid_resolves_has_no_floor_even_off_grid(self):
        # 3.9170 ns is 19.585 steps -- deliberately NOT commensurate -- but a
        # 1 ns transition spans five grid samples, so the two samples
        # bracketing the 50 % crossing both sit on the straight ramp and the
        # linear interpolation recovers the crossing exactly.
        self.assertAlmostEqual(
            self.floor_for(period_s=3.9170e-9, edge_s=1e-9), 0.0, places=12
        )

    def test_an_edge_the_grid_cannot_resolve_manufactures_a_row_9_miss(self):
        # The case that matters for #178: a clock with NO jitter at all is
        # reported as missing ratified row 9's 1.0 % bound, by more than a
        # factor of two, purely because a 200 ps grid cannot place its edges.
        floor = self.floor_for(period_s=3.9170e-9, edge_s=20e-12)
        self.assertGreater(floor, 2 * self.ROW_9)
        self.assertLess(floor, 3 * self.ROW_9)

    def test_the_floor_matches_the_committed_jitter_floor_records(self):
        # The cross-check that lets the cheap synthetic cases above stand in
        # for a simulator run: the same five variants the committed
        # sim/jitter-floor records ran, at their own 50 us window, agree with
        # what ngspice + this reducer reported to within 0.01 pp.
        for variant, period_s, edge_s, recorded in self.COMMITTED_RECORDS:
            with self.subTest(variant=variant):
                floor = self.floor_for(
                    period_s=period_s, edge_s=edge_s, duration_s=50e-6
                )
                self.assertAlmostEqual(floor, recorded, delta=1e-4)

    def test_the_floor_falls_as_the_grid_resolves_the_edge(self):
        # Monotone in transition time at a fixed period and grid: the floor is
        # a resolution effect, not a constant offset of the reducer.
        floors = [
            self.floor_for(period_s=3.9170e-9, edge_s=edge_s)
            for edge_s in (20e-12, 100e-12, 200e-12, 400e-12)
        ]
        self.assertEqual(floors, sorted(floors, reverse=True))
        self.assertGreater(floors[0], 0.02)
        self.assertAlmostEqual(floors[-1], 0.0, places=12)

    def test_a_finer_grid_shrinks_the_floor_below_row_9s_budget(self):
        # What grid a defensible row-9 figure needs, measured rather than
        # asserted (see measure.py's "The dump grid puts a floor under this
        # figure"). The edge is held at a tenth of each grid step, so every
        # point stays in the unresolved-edge regime and the grid step is the
        # only thing that changes.
        period_s = 3.9170e-9
        budget_s = self.ROW_9 * period_s  # 39.2 ps, row 9's whole budget
        coarse = self.floor_for(period_s=period_s, edge_s=20e-12, step_s=200e-12)
        fine = self.floor_for(period_s=period_s, edge_s=2e-12, step_s=20e-12)
        self.assertGreater(coarse * period_s, 2 * budget_s)
        self.assertLess(fine * period_s, budget_s / 4)

    def test_no_measured_floor_exceeds_half_a_grid_step(self):
        # The arithmetic bound measure.py's docstring states: an unresolved
        # edge's crossing lands in the middle of the grid interval holding it,
        # so the per-edge error is bounded by half a step and a perfectly
        # periodic clock's per-period floor is `step * sqrt(f*(1-f))` <=
        # `step/2`. Asserted across the committed variants plus the
        # half-integer period that maximizes it.
        worst_case_s = self.STEP / 2
        periods = [p for _, p, _, _ in self.COMMITTED_RECORDS]
        periods.append(19.5 * self.STEP)  # f = 0.5, the maximizing phase
        for period_s in periods:
            with self.subTest(period_ns=round(1e9 * period_s, 4)):
                floor_s = self.floor_for(period_s=period_s, edge_s=20e-12) * period_s
                self.assertLessEqual(floor_s, worst_case_s)


class MeasureTraceTests(unittest.TestCase):
    OSC_SPEC = measure.MeasureSpec(
        node="clk",
        tran_step="20p",
        tran_stop="200n",
        threshold_frac=0.5,
        hysteresis_frac=0.15,
        settle_from_s=50e-9,
        min_edges=5,
        timeout_s=600,
    )
    LOCK_SPEC = measure.MeasureSpec(
        node="clk",
        tran_step="200p",
        tran_stop="6u",
        threshold_frac=0.5,
        hysteresis_frac=0.15,
        settle_from_s=0.0,
        min_edges=50,
        timeout_s=600,
        lock=measure.LockSpec(
            target_hz=250e6, tolerance_frac=0.02, window_cycles=10, min_hold_cycles=20
        ),
        require_lock=True,
    )

    def test_oscillation_mode_reports_frequency_and_duty(self):
        times, values = square_wave(
            freq_hz=500e6, duty=0.45, duration_s=200e-9, step_s=20e-12
        )
        m = measure.measure_trace(times, values, self.OSC_SPEC, supply_v=1.8)
        self.assertTrue(m.oscillating)
        self.assertAlmostEqual(m.freq_hz, 500e6, delta=500e6 * 2e-3)
        self.assertAlmostEqual(m.duty_cycle, 0.45, delta=0.01)
        self.assertIsNone(m.locked)
        self.assertTrue(m.passed)

    def test_oscillation_mode_reports_a_dead_ring_explicitly(self):
        times = [i * 20e-12 for i in range(10001)]
        values = [1.8] * 10001
        m = measure.measure_trace(times, values, self.OSC_SPEC, supply_v=1.8)
        self.assertFalse(m.oscillating)
        self.assertIsNone(m.freq_hz)
        self.assertFalse(m.passed)
        self.assertIn("no oscillation", m.note)

    def test_lock_mode_on_a_locked_trace(self):
        times, values = square_wave(freq_hz=250e6, duration_s=2e-6, step_s=200e-12)
        m = measure.measure_trace(times, values, self.LOCK_SPEC, supply_v=1.8)
        self.assertTrue(m.locked)
        self.assertIsNotNone(m.lock_time_s)
        self.assertAlmostEqual(m.freq_hz, 250e6, delta=250e6 * 5e-3)
        self.assertTrue(m.passed)

    def test_lock_mode_never_reports_a_post_lock_frequency_when_it_did_not_lock(self):
        # A ring stuck 40 % below target for the whole window. The final
        # window's mean frequency is still a real number -- the point of this
        # test is that it must NOT be presented as `freq_hz` (the post-lock
        # output frequency), only as `final_freq_hz`, and that the note says
        # so in words.
        times, values = square_wave(freq_hz=150e6, duration_s=2e-6, step_s=200e-12)
        m = measure.measure_trace(times, values, self.LOCK_SPEC, supply_v=1.8)
        self.assertFalse(m.locked)
        self.assertIsNone(m.freq_hz)
        self.assertIsNone(m.lock_time_s)
        self.assertIsNotNone(m.final_freq_hz)
        self.assertAlmostEqual(m.final_freq_hz, 150e6, delta=150e6 * 5e-3)
        self.assertIn("no lock", m.note)
        self.assertFalse(m.passed)

    def test_threshold_tracks_the_supply_of_the_pvt_point(self):
        # At the 1.62 V corner a 0.9 V fixed threshold would still work, but a
        # trace that only swings to 1.62 V must be measured at 0.81 V.
        times, values = square_wave(
            freq_hz=500e6, duration_s=200e-9, step_s=20e-12, v_high=1.62
        )
        m = measure.measure_trace(times, values, self.OSC_SPEC, supply_v=1.62)
        self.assertTrue(m.oscillating)
        self.assertAlmostEqual(m.freq_hz, 500e6, delta=500e6 * 2e-3)


class TransitionMeasureTraceTests(unittest.TestCase):
    """End-to-end through `measure_trace`: issue #186's transition figure,
    on both the free-running (no `lock` block) and post-lock branches."""

    EDGE_S = 300e-12
    OSC_SPEC = measure.MeasureSpec(
        node="clk",
        tran_step="20p",
        tran_stop="200n",
        threshold_frac=0.5,
        hysteresis_frac=0.15,
        settle_from_s=50e-9,
        min_edges=5,
        timeout_s=600,
        transition=measure.TransitionSpec(),
    )
    LOCK_SPEC = measure.MeasureSpec(
        node="clk",
        tran_step="200p",
        tran_stop="6u",
        threshold_frac=0.5,
        hysteresis_frac=0.15,
        settle_from_s=0.0,
        min_edges=50,
        timeout_s=600,
        lock=measure.LockSpec(
            target_hz=250e6, tolerance_frac=0.02, window_cycles=10, min_hold_cycles=20
        ),
        transition=measure.TransitionSpec(),
    )

    def test_free_running_mode_reports_rise_and_fall(self):
        times, values = square_wave(
            freq_hz=500e6, duration_s=200e-9, step_s=2e-12, edge_s=self.EDGE_S
        )
        m = measure.measure_trace(times, values, self.OSC_SPEC, supply_v=1.8)
        self.assertAlmostEqual(m.rise_time_s, 0.8 * self.EDGE_S, delta=self.EDGE_S * 0.05)
        self.assertAlmostEqual(m.fall_time_s, 0.8 * self.EDGE_S, delta=self.EDGE_S * 0.05)
        self.assertGreater(m.n_rise_edges, 0)
        self.assertGreater(m.n_fall_edges, 0)
        self.assertIn("transition time: rise", m.note)

    def test_locked_trace_reports_transition_from_the_post_lock_population(self):
        times, values = square_wave(
            freq_hz=250e6, duration_s=2e-6, step_s=100e-12, edge_s=self.EDGE_S
        )
        m = measure.measure_trace(times, values, self.LOCK_SPEC, supply_v=1.8)
        self.assertTrue(m.locked)
        self.assertAlmostEqual(m.rise_time_s, 0.8 * self.EDGE_S, delta=self.EDGE_S * 0.05)
        self.assertAlmostEqual(m.fall_time_s, 0.8 * self.EDGE_S, delta=self.EDGE_S * 0.05)
        self.assertIn("transition time: rise", m.note)

    def test_no_transition_block_leaves_the_measurement_unchanged(self):
        spec = measure.MeasureSpec(
            node="clk", tran_step="20p", tran_stop="200n", threshold_frac=0.5,
            hysteresis_frac=0.15, settle_from_s=50e-9, min_edges=5, timeout_s=600,
        )
        times, values = square_wave(
            freq_hz=500e6, duration_s=200e-9, step_s=2e-12, edge_s=self.EDGE_S
        )
        m = measure.measure_trace(times, values, spec, supply_v=1.8)
        self.assertIsNone(m.rise_time_s)
        self.assertIsNone(m.fall_time_s)
        self.assertEqual(m.n_rise_edges, 0)
        self.assertEqual(m.n_fall_edges, 0)
        self.assertNotIn("transition", m.note)

    def test_a_point_that_never_locked_reports_no_transition_time(self):
        # Consistent with jitter: a point with no post-lock population has
        # nothing for this figure to be measured over either.
        times, values = square_wave(
            freq_hz=150e6, duration_s=2e-6, step_s=200e-12, edge_s=self.EDGE_S
        )
        m = measure.measure_trace(times, values, self.LOCK_SPEC, supply_v=1.8)
        self.assertFalse(m.locked)
        self.assertIsNone(m.rise_time_s)
        self.assertIsNone(m.fall_time_s)


class JitterMeasureTraceTests(unittest.TestCase):
    """End-to-end through `measure_trace`: a sampled trapezoidal trace in,
    a row-9 number out. Unlike `PeriodJitterTests` these go through the real
    threshold-crossing extraction, so they also pin that the jitter figure is
    derived from the *same* interpolated edge list as frequency and duty and
    not from a second pass over the raw samples."""

    T0 = 4e-9  # 250 MHz
    LOCK = measure.LockSpec(
        target_hz=250e6, tolerance_frac=0.05, window_cycles=10, min_hold_cycles=20
    )

    @classmethod
    def _spec(cls, jitter, *, lock=True, settle_s=0.0):
        return measure.MeasureSpec(
            node="clk",
            tran_step="100p",
            tran_stop="2u",
            threshold_frac=0.5,
            hysteresis_frac=0.15,
            settle_from_s=settle_s,
            min_edges=50,
            timeout_s=600,
            lock=cls.LOCK if lock else None,
            jitter=jitter,
        )

    @classmethod
    def _jittered_trace(cls, amplitude, n_cycles=400):
        periods = [
            cls.T0 * (1 + amplitude if k % 2 == 0 else 1 - amplitude)
            for k in range(n_cycles)
        ]
        return wave_from_periods(periods, step_s=100e-12, edge_s=800e-12)

    # A trace whose jitter *differs by two orders of magnitude* either side of
    # the lock instant: 200 acquisition cycles far off target (150 MHz, then a
    # step to 250 MHz -- an enormous cycle-to-cycle spread when the whole trace
    # is taken as one population) followed by 400 clean +/-0.5 % cycles. Every
    # other fixture here (`_jittered_trace`) carries the *same* modulation
    # before and after lock, which makes the pre-lock and post-lock windows
    # indistinguishable and so cannot pin which one `measure_trace` actually
    # used. This one can.
    CHIRP_AMPLITUDE = 0.005
    CHIRP_CYCLES = 200
    CHIRP_PERIOD_S = 1.0 / 150e6

    @classmethod
    def _chirp_then_clean_trace(cls, clean_cycles=400):
        a = cls.CHIRP_AMPLITUDE
        periods = [cls.CHIRP_PERIOD_S] * cls.CHIRP_CYCLES + [
            cls.T0 * (1 + a if k % 2 == 0 else 1 - a) for k in range(clean_cycles)
        ]
        # The 200th rising edge is the first one at the target frequency, and
        # is where `lock_time`'s sliding window first comes in band.
        t_lock_expected = cls.CHIRP_PERIOD_S * cls.CHIRP_CYCLES
        times, values = wave_from_periods(periods, step_s=100e-12, edge_s=800e-12)
        return times, values, t_lock_expected

    def test_a_locked_trace_reports_the_injected_period_modulation(self):
        times, values = self._jittered_trace(0.005)
        spec = self._spec(measure.JitterSpec(max_frac=0.01, min_cycles=20))
        m = measure.measure_trace(times, values, spec, supply_v=1.8)
        self.assertTrue(m.locked)
        # +/-0.5 % alternating periods: RMS/mean is 0.005 by construction.
        self.assertAlmostEqual(m.period_jitter_frac, 0.005, delta=1e-4)
        self.assertGreater(m.jitter_cycles, 300)
        self.assertIn("period jitter 0.500% RMS", m.note)
        self.assertNotIn("misses", m.note)
        passed, reason = measure.aggregate([m], spec)
        self.assertTrue(passed)

    def test_a_trace_over_the_stated_bound_is_flagged_and_fails_the_fold(self):
        times, values = self._jittered_trace(0.02)
        spec = self._spec(measure.JitterSpec(max_frac=0.01, min_cycles=20))
        m = measure.measure_trace(times, values, spec, supply_v=1.8)
        self.assertTrue(m.locked)
        self.assertAlmostEqual(m.period_jitter_frac, 0.02, delta=1e-4)
        self.assertIn("misses", m.note)
        passed, reason = measure.aggregate([m], spec)
        self.assertFalse(passed)
        self.assertIn("period-jitter bound of 1%", reason)

    def test_a_manifest_without_a_jitter_block_measures_no_jitter(self):
        # The whole feature is opt-in: an existing campaign's manifest is
        # unaffected, and nothing appears in its note.
        times, values = self._jittered_trace(0.02)
        spec = self._spec(None)
        m = measure.measure_trace(times, values, spec, supply_v=1.8)
        self.assertTrue(m.locked)
        self.assertIsNone(m.period_jitter_frac)
        self.assertIsNone(m.jitter_cycles)
        self.assertNotIn("jitter", m.note)

    def test_a_point_that_never_locked_is_attributed_no_jitter(self):
        # Row 9 is stated "in lock". A loop stuck 40 % low has a perfectly
        # computable cycle-to-cycle spread, and reporting it as this row's
        # quantity would be exactly the "present the last simulated value as
        # the measurement" failure the lock criterion already rules out.
        times, values = square_wave(freq_hz=150e6, duration_s=2e-6, step_s=200e-12)
        spec = self._spec(measure.JitterSpec(max_frac=0.01, min_cycles=20))
        m = measure.measure_trace(times, values, spec, supply_v=1.8)
        self.assertFalse(m.locked)
        self.assertIsNone(m.period_jitter_frac)
        self.assertIn("No period jitter is attributed", m.note)

    def test_too_small_a_post_lock_population_reports_no_number(self):
        times, values = self._jittered_trace(0.005)
        spec = self._spec(measure.JitterSpec(max_frac=0.01, min_cycles=5000))
        m = measure.measure_trace(times, values, spec, supply_v=1.8)
        self.assertTrue(m.locked)
        self.assertIsNone(m.period_jitter_frac)
        self.assertGreater(m.jitter_cycles, 300)
        self.assertIn("**not measured**", m.note)
        # Gating on a bound the campaign could not measure is not a PASS.
        passed, reason = measure.aggregate([m], spec)
        self.assertFalse(passed)
        self.assertIn("produced no jitter number", reason)

    def test_a_free_running_manifest_measures_from_settle_instead(self):
        # No `lock` block: the population starts at `settle_from`, the same
        # instant frequency and duty are already taken over.
        times, values = self._jittered_trace(0.01)
        spec = self._spec(measure.JitterSpec(min_cycles=20), lock=False)
        m = measure.measure_trace(times, values, spec, supply_v=1.8)
        self.assertIsNone(m.locked)
        self.assertAlmostEqual(m.period_jitter_frac, 0.01, delta=1e-4)
        self.assertIn("period jitter 1.000% RMS", m.note)

    def test_a_non_monotonic_population_is_declined_for_its_own_reason(self):
        # `period_jitter` declines for two distinct reasons -- too small a
        # population, and a population whose mean period is non-positive --
        # and the note must name the one that actually applied. Only a
        # non-monotonic edge list reaches the second (`edge_times` never
        # emits one), but when it is reached the population here is ample, so
        # blaming the population size would name the wrong cause.
        spec = self._spec(measure.JitterSpec(max_frac=0.01, min_cycles=2))
        frac, n_cycles, clause = measure._measure_jitter(
            [0.0, 4e-9, -8e-9, -4e-9], spec, t_from=None
        )
        self.assertIsNone(frac)
        self.assertEqual(n_cycles, 3)
        self.assertIn("non-positive mean period", clause)
        self.assertNotIn("fewer than", clause)

    def test_measure_trace_starts_the_locked_population_at_the_lock_instant(self):
        # The acceptance criterion for row 9 is that the population starts
        # *after the loop is in lock*, reusing `lock_time`'s instant. The
        # `PeriodJitterTests` case of the same name pins `period_jitter`'s
        # `t_from` parameter directly; this one pins what `measure_trace`
        # itself passes, which is the thing the record's row-9 figure comes
        # from. It is written so that substituting any other plausible window
        # start -- `settle_from` (0 here), `None`, the start of the trace --
        # fails it: the acquisition transient's spread is >20x the post-lock
        # one, not a delta a tolerance could absorb.
        times, values, t_lock_expected = self._chirp_then_clean_trace()
        spec = self._spec(measure.JitterSpec(max_frac=0.01, min_cycles=20))
        m = measure.measure_trace(times, values, spec, supply_v=1.8)

        self.assertTrue(m.locked)
        self.assertAlmostEqual(m.lock_time_s, t_lock_expected, delta=self.T0)

        # What the whole trace would have reported, had the population started
        # at `settle_from`/the start of the trace instead of at `t_lock`.
        rising, _ = measure.edge_times(times, values, 0.9, 0.15 * 1.8)
        whole_trace, _ = measure.period_jitter(rising, t_from=spec.settle_from_s)
        self.assertGreater(whole_trace, 0.10)

        # What `measure_trace` actually reported: the post-lock amplitude.
        self.assertAlmostEqual(
            m.period_jitter_frac, self.CHIRP_AMPLITUDE, delta=1e-4
        )
        self.assertLess(m.period_jitter_frac, whole_trace / 20)
        self.assertEqual(m.jitter_cycles, len(rising) - 1 - self.CHIRP_CYCLES)
        self.assertIn("period jitter 0.500% RMS", m.note)
        self.assertNotIn("misses", m.note)
        passed, _ = measure.aggregate([m], spec)
        self.assertTrue(passed)

    def test_measure_trace_starts_the_free_running_population_at_settle(self):
        # The sibling of the test above for the no-`lock` branch: with a
        # non-zero `settle_from`, passing `None` (the whole trace) instead of
        # `settle` would drag the same acquisition transient into the
        # population. Both branches' window starts are therefore pinned, not
        # just the row-9 one.
        times, values, t_lock_expected = self._chirp_then_clean_trace()
        settle_s = t_lock_expected + 5e-9  # just inside the clean section
        spec = self._spec(
            measure.JitterSpec(max_frac=0.01, min_cycles=20),
            lock=False,
            settle_s=settle_s,
        )
        m = measure.measure_trace(times, values, spec, supply_v=1.8)

        self.assertIsNone(m.locked)
        rising, _ = measure.edge_times(times, values, 0.9, 0.15 * 1.8)
        whole_trace, _ = measure.period_jitter(rising)
        self.assertGreater(whole_trace, 0.10)

        self.assertAlmostEqual(
            m.period_jitter_frac, self.CHIRP_AMPLITUDE, delta=1e-4
        )
        self.assertLess(m.period_jitter_frac, whole_trace / 20)
        self.assertIn("period jitter 0.500% RMS", m.note)


class JitterAggregationTests(unittest.TestCase):
    """The row-9 pass/fail *fold* -- what a record's verdict column means when
    the manifest states a jitter bound."""

    @staticmethod
    def _m(label, *, frac, cycles=200, locked=True, oscillating=True):
        return measure.Measurement(
            label=label,
            oscillating=oscillating,
            freq_hz=250e6 if oscillating else None,
            duty_cycle=0.5 if oscillating else None,
            locked=locked,
            lock_time_s=1e-6 if locked else None,
            final_freq_hz=250e6 if oscillating else None,
            note="ok",
            passed=True,
            period_jitter_frac=frac,
            jitter_cycles=cycles,
        )

    @staticmethod
    def _spec(jitter):
        return measure.MeasureSpec(
            node="clk",
            tran_step="100p",
            tran_stop="2u",
            lock=measure.LockSpec(
                target_hz=250e6, tolerance_frac=0.05, window_cycles=10, min_hold_cycles=20
            ),
            jitter=jitter,
        )

    def test_every_point_inside_the_bound_passes(self):
        spec = self._spec(measure.JitterSpec(max_frac=0.01))
        passed, _ = measure.aggregate(
            [self._m(None, frac=0.004)], spec
        )
        self.assertTrue(passed)

    def test_a_point_outside_the_bound_fails_with_the_number_in_the_reason(self):
        spec = self._spec(measure.JitterSpec(max_frac=0.01))
        ms = [self._m("tt", frac=0.004), self._m("ss", frac=0.0173)]
        passed, reason = measure.aggregate(ms, spec)
        self.assertFalse(passed)
        self.assertIn("1/2 measurement(s) miss", reason)
        self.assertIn("ss: period jitter 1.730% RMS", reason)

    def test_a_report_only_manifest_records_the_miss_without_failing(self):
        # A characterization campaign may want row 9's number recorded
        # without the verdict column gating on it.
        spec = self._spec(measure.JitterSpec(max_frac=0.01, gate_on_bound=False))
        passed, _ = measure.aggregate([self._m(None, frac=0.05)], spec)
        self.assertTrue(passed)

    def test_a_manifest_that_states_no_bound_never_fails_on_jitter(self):
        spec = self._spec(measure.JitterSpec())
        passed, _ = measure.aggregate([self._m(None, frac=0.5)], spec)
        self.assertTrue(passed)

    def test_a_gated_bound_with_no_number_behind_it_fails(self):
        spec = self._spec(measure.JitterSpec(max_frac=0.01))
        passed, reason = measure.aggregate(
            [self._m("tt", frac=None, cycles=3)], spec
        )
        self.assertFalse(passed)
        self.assertIn("produced no jitter number", reason)
        self.assertIn("tt: 3 cycle(s)", reason)

    def test_a_point_that_never_locked_is_not_charged_for_missing_jitter(self):
        # Its own "no lock" record is the finding; failing it a second time
        # for the jitter number it could not have would double-count it. The
        # manifest's `require_lock` knob decides whether no-lock fails.
        spec = self._spec(measure.JitterSpec(max_frac=0.01))
        passed, _ = measure.aggregate(
            [self._m("ss", frac=None, cycles=0, locked=False)], spec
        )
        self.assertTrue(passed)

    def test_a_dead_point_is_not_charged_for_missing_jitter_either(self):
        spec = self._spec(measure.JitterSpec(max_frac=0.01))
        passed, _ = measure.aggregate(
            [self._m("ss", frac=None, cycles=0, locked=False, oscillating=False)], spec
        )
        self.assertTrue(passed)


def dc_with_ripple(
    *,
    dc_v: float,
    amp_v: float,
    freq_hz: float,
    duration_s: float,
    step_s: float,
    kick_until_s: float = 0.0,
    kick_v: float = 0.0,
):
    """A DC level plus a sinusoidal ripple of known amplitude, optionally
    preceded by a large start-up excursion (`kick_v` added before
    `kick_until_s`) -- the shape of a control node that slews to its lock
    value and then sits there, rippling at the reference rate."""
    times, values = [], []
    n = int(round(duration_s / step_s)) + 1
    for i in range(n):
        t = i * step_s
        v = dc_v + amp_v * math.sin(2 * math.pi * freq_hz * t)
        if t < kick_until_s:
            v += kick_v
        times.append(t)
        values.append(v)
    return times, values


class RipplePrimitiveTests(unittest.TestCase):
    """`ripple_pp` -- min/max/peak-to-peak of a DC-ish node over a settled
    window, checked against a synthetic waveform whose ripple is known by
    construction."""

    def test_known_sinusoidal_ripple(self):
        # 10 mV pp around 1.2 V, 10 MHz, sampled at 200 ps (50 samples/period,
        # so the sampled extremes land within ~0.2 % of the true peaks).
        times, values = dc_with_ripple(
            dc_v=1.2, amp_v=0.005, freq_hz=10e6, duration_s=2e-6, step_s=200e-12
        )
        lo, hi, pp = measure.ripple_pp(times, values, t_from=1e-6)
        self.assertAlmostEqual(lo, 1.195, delta=2e-5)
        self.assertAlmostEqual(hi, 1.205, delta=2e-5)
        self.assertAlmostEqual(pp, 0.010, delta=4e-5)
        self.assertAlmostEqual(pp, hi - lo)

    def test_startup_transient_before_the_window_is_excluded(self):
        # A 0.5 V start-up excursion before 1 us must not leak into a window
        # that starts at 1.5 us.
        times, values = dc_with_ripple(
            dc_v=1.2, amp_v=0.001, freq_hz=10e6, duration_s=3e-6, step_s=200e-12,
            kick_until_s=1e-6, kick_v=0.5,
        )
        _lo, _hi, pp = measure.ripple_pp(times, values, t_from=1.5e-6)
        self.assertAlmostEqual(pp, 0.002, delta=2e-5)
        # ...and the same trace measured from t=0 does see it.
        _lo, _hi, pp_all = measure.ripple_pp(times, values, t_from=0.0)
        self.assertGreater(pp_all, 0.5)

    def test_window_upper_bound_is_honoured(self):
        times = [0.0, 1.0, 2.0, 3.0, 4.0]
        values = [0.0, 1.0, 3.0, 2.0, 10.0]
        self.assertEqual(measure.ripple_pp(times, values, 1.0, 3.0), (1.0, 3.0, 2.0))
        self.assertEqual(measure.ripple_pp(times, values, 1.0), (1.0, 10.0, 9.0))

    def test_a_flat_trace_has_zero_ripple(self):
        times = [i * 1e-9 for i in range(100)]
        values = [1.8] * 100
        self.assertEqual(measure.ripple_pp(times, values, 0.0), (1.8, 1.8, 0.0))

    def test_an_empty_window_is_none_not_zero(self):
        # Zero would read as a (spuriously perfect) measurement.
        times = [0.0, 1e-9, 2e-9]
        values = [1.0, 1.1, 1.2]
        self.assertIsNone(measure.ripple_pp(times, values, t_from=5e-9))


class MultiColumnWrdataTests(unittest.TestCase):
    def test_single_scale_layout(self):
        text = " 0 1.8 0.0 1.80\n 1e-10 0.0 0.1 1.79\n"
        times, cols = measure.parse_wrdata_columns(text, 3)
        self.assertEqual(times, [0.0, 1e-10])
        self.assertEqual(cols, [[1.8, 0.0], [0.0, 0.1], [1.80, 1.79]])

    def test_paired_layout(self):
        text = " 0 1.8 0 0.0\n 1e-10 0.0 1e-10 0.1\n"
        times, cols = measure.parse_wrdata_columns(text, 2)
        self.assertEqual(times, [0.0, 1e-10])
        self.assertEqual(cols, [[1.8, 0.0], [0.0, 0.1]])

    def test_a_row_of_the_wrong_width_is_rejected(self):
        with self.assertRaises(measure.MeasureError):
            measure.parse_wrdata_columns(" 0 1 2\n", 3)

    def test_first_column_pair_still_reads_with_the_two_column_parser(self):
        # The clock node is dumped first, so the unchanged two-column parser
        # reads it correctly out of a single-scale multi-node dump too.
        text = " 0 1.8 0.5 1.79\n 1e-10 0.0 0.6 1.78\n"
        times, values = measure.parse_wrdata(text)
        self.assertEqual(values, [1.8, 0.0])

    def test_empty_dump_raises(self):
        with self.assertRaises(measure.MeasureError):
            measure.parse_wrdata_columns("\n", 2)


class RippleMeasureTraceTests(unittest.TestCase):
    SPEC = measure.MeasureSpec(
        node="clk",
        tran_step="200p",
        tran_stop="3u",
        min_edges=50,
        timeout_s=600,
        lock=measure.LockSpec(
            target_hz=250e6, tolerance_frac=0.05, window_cycles=10, min_hold_cycles=20
        ),
        require_lock=False,
        ripple=measure.RippleSpec(nodes=("vdd", "vctrl"), window_s=1e-6),
    )

    def _extra(self, times):
        _t, vdd = dc_with_ripple(
            dc_v=1.8, amp_v=0.002, freq_hz=10e6, duration_s=3e-6, step_s=200e-12
        )
        _t, vctrl = dc_with_ripple(
            dc_v=1.1, amp_v=0.0005, freq_hz=10e6, duration_s=3e-6, step_s=200e-12,
            kick_until_s=0.5e-6, kick_v=-1.0,
        )
        self.assertEqual(len(vdd), len(times))
        return {"vdd": vdd, "vctrl": vctrl}

    def test_locked_trace_reports_in_lock_ripple_per_node(self):
        times, values = square_wave(freq_hz=250e6, duration_s=3e-6, step_s=200e-12)
        m = measure.measure_trace(
            times, values, self.SPEC, supply_v=1.8, extra=self._extra(times)
        )
        self.assertTrue(m.locked)
        self.assertEqual([r.node for r in m.ripple], ["vdd", "vctrl"])
        vdd, vctrl = m.ripple
        self.assertTrue(vdd.in_lock)
        self.assertAlmostEqual(vdd.t_from_s, 2e-6)
        self.assertAlmostEqual(vdd.t_to_s, 3e-6)
        self.assertAlmostEqual(vdd.pp, 0.004, delta=2e-5)
        # The -1 V start-up kick on vctrl is long gone by the window.
        self.assertAlmostEqual(vctrl.pp, 0.001, delta=1e-5)
        self.assertIn("(in lock)", m.note)
        self.assertIn("v(vdd) ripple 4", m.note)
        self.assertTrue(m.passed)

    def test_unlocked_trace_still_reports_ripple_but_says_it_is_not_in_lock(self):
        # Stuck 40 % low: never locks. The ripple is still what the node did,
        # but must be flagged as not ripple-in-lock evidence, and (with
        # require_lock false) the point still passes -- no lock is evidence.
        times, values = square_wave(freq_hz=150e6, duration_s=3e-6, step_s=200e-12)
        m = measure.measure_trace(
            times, values, self.SPEC, supply_v=1.8, extra=self._extra(times)
        )
        self.assertFalse(m.locked)
        self.assertTrue(all(r.in_lock is False for r in m.ripple))
        self.assertIn("NOT in lock", m.note)
        self.assertTrue(m.passed)

    def test_a_missing_ripple_node_is_an_error_not_a_zero(self):
        times, values = square_wave(freq_hz=250e6, duration_s=3e-6, step_s=200e-12)
        with self.assertRaises(measure.MeasureError):
            measure.measure_trace(
                times, values, self.SPEC, supply_v=1.8, extra={"vdd": values}
            )

    def test_no_ripple_block_leaves_the_measurement_unchanged(self):
        spec = measure.MeasureSpec(
            node="clk", tran_step="200p", tran_stop="3u", min_edges=50, timeout_s=600,
            lock=self.SPEC.lock,
        )
        times, values = square_wave(freq_hz=250e6, duration_s=3e-6, step_s=200e-12)
        m = measure.measure_trace(times, values, spec, supply_v=1.8)
        self.assertEqual(m.ripple, ())
        self.assertNotIn("ripple", m.note)


class AggregationPolicyTests(unittest.TestCase):
    """`aggregate` is the pass/fail *policy* -- what a record's verdict column
    actually means. It lives beside the arithmetic so it can be pinned without
    a simulator."""

    @staticmethod
    def _m(label, *, oscillating=True, passed=True, freq=500e6):
        return measure.Measurement(
            label=label,
            oscillating=oscillating,
            freq_hz=freq if oscillating else None,
            duty_cycle=0.5 if oscillating else None,
            locked=None,
            lock_time_s=None,
            final_freq_hz=freq if oscillating else None,
            note="ok" if oscillating else "no oscillation: 0 rising edge(s)",
            passed=passed,
        )

    SWEEP_SPEC = measure.MeasureSpec(
        node="clk",
        tran_step="50p",
        tran_stop="200n",
        require_oscillation=False,
        min_oscillating_points=3,
    )

    def test_no_measurements_at_all_fails(self):
        passed, reason = measure.aggregate([], self.SWEEP_SPEC)
        self.assertFalse(passed)
        self.assertIn("no measurements", reason)

    def test_dead_low_end_of_a_characterization_sweep_still_passes(self):
        ms = [
            self._m("VCTRL=0.600V", oscillating=False),
            self._m("VCTRL=0.800V"),
            self._m("VCTRL=1.000V"),
            self._m("VCTRL=1.200V"),
        ]
        passed, reason = measure.aggregate(ms, self.SWEEP_SPEC)
        self.assertTrue(passed)
        self.assertIn("3/4 swept points oscillated", reason)

    def test_a_corner_where_almost_nothing_oscillates_fails(self):
        ms = [
            self._m("VCTRL=0.600V", oscillating=False),
            self._m("VCTRL=0.800V", oscillating=False),
            self._m("VCTRL=1.000V", oscillating=False),
            self._m("VCTRL=1.200V"),
        ]
        passed, reason = measure.aggregate(ms, self.SWEEP_SPEC)
        self.assertFalse(passed)
        self.assertIn("requires at least 3", reason)

    def test_a_failing_measurement_dominates(self):
        ms = [self._m("VCTRL=0.800V", passed=False), self._m("VCTRL=1.000V")]
        passed, reason = measure.aggregate(ms, self.SWEEP_SPEC)
        self.assertFalse(passed)
        self.assertIn("VCTRL=0.800V", reason)


class ManifestParsingTests(unittest.TestCase):
    def test_absent_measure_block_yields_none(self):
        self.assertIsNone(measure.MeasureSpec.from_manifest({}))

    def test_parses_a_lock_campaign_manifest(self):
        spec = measure.MeasureSpec.from_manifest(
            {
                "measure": {
                    "node": "clk",
                    "tran_step": "200p",
                    "tran_stop": "40u",
                    "settle_from": "1u",
                    "lock": {
                        "target_hz": 250e6,
                        "tolerance_frac": 0.01,
                        "window_cycles": 25,
                        "min_hold_cycles": 100,
                    },
                    "require_lock": True,
                }
            }
        )
        self.assertEqual(spec.node, "clk")
        self.assertAlmostEqual(spec.tran_stop_s, 40e-6)
        self.assertAlmostEqual(spec.settle_from_s, 1e-6)
        self.assertTrue(spec.require_lock)
        self.assertEqual(spec.lock.window_cycles, 25)
        self.assertEqual(spec.sweep, ())

    def test_parses_a_sweep_campaign_manifest(self):
        spec = measure.MeasureSpec.from_manifest(
            {
                "measure": {
                    "node": "clk",
                    "tran_step": "20p",
                    "tran_stop": "200n",
                    "sweep": {"source": "V2", "quantity": "VCTRL", "values": [0.8, 0.9]},
                }
            }
        )
        self.assertEqual(len(spec.sweep), 2)
        self.assertEqual(spec.sweep[0].source, "V2")
        self.assertEqual(spec.sweep[0].label, "VCTRL=0.800V")
        self.assertIsNone(spec.lock)

    def test_a_manifest_with_no_jitter_block_parses_to_no_jitter_spec(self):
        spec = measure.MeasureSpec.from_manifest(
            {"measure": {"node": "clk", "tran_step": "1p", "tran_stop": "1n"}}
        )
        self.assertIsNone(spec.jitter)

    def test_parses_a_row_9_jitter_block(self):
        spec = measure.MeasureSpec.from_manifest(
            {
                "measure": {
                    "node": "CLK",
                    "tran_step": "200p",
                    "tran_stop": "100u",
                    "lock": {
                        "target_hz": 250e6,
                        "tolerance_frac": 0.05,
                        "window_cycles": 20,
                        # A gated bound may not ask for a larger population
                        # than the lock criterion guarantees a locked point
                        # (#190), so a 200-cycle population needs the lock
                        # criterion to hold for 200 cycles too.
                        "min_hold_cycles": 200,
                    },
                    "jitter": {"max_frac": 0.01, "min_cycles": 200},
                }
            }
        )
        self.assertAlmostEqual(spec.jitter.max_frac, 0.01)
        self.assertEqual(spec.jitter.min_cycles, 200)
        # Row 9 is RATIFIED, so a stated bound gates by default -- unlike the
        # DRAFT rows 6/7 bounds in `acmeasure.AcSpec`, which do not.
        self.assertTrue(spec.jitter.gate_on_bound)

    def test_an_empty_jitter_block_reports_without_a_bound(self):
        spec = measure.MeasureSpec.from_manifest(
            {
                "measure": {
                    "node": "clk",
                    "tran_step": "1p",
                    "tran_stop": "1n",
                    "jitter": {},
                }
            }
        )
        self.assertIsNotNone(spec.jitter)
        self.assertIsNone(spec.jitter.max_frac)
        self.assertEqual(spec.jitter.min_cycles, 20)

    def test_a_bound_written_as_a_percentage_instead_of_a_fraction_is_rejected(self):
        # Row 9's bound is 1.0 %, i.e. `0.01`. A manifest that writes `1.0`
        # means 100 % of the output period -- a bound nothing could fail,
        # which would silently turn a gated campaign into a no-op.
        with self.assertRaises(measure.MeasureError):
            measure.MeasureSpec.from_manifest(
                {
                    "measure": {
                        "node": "clk",
                        "tran_step": "1p",
                        "tran_stop": "1n",
                        "jitter": {"max_frac": 1.0},
                    }
                }
            )

    def test_a_jitter_population_smaller_than_two_cycles_is_rejected(self):
        with self.assertRaises(measure.MeasureError):
            measure.MeasureSpec.from_manifest(
                {
                    "measure": {
                        "node": "clk",
                        "tran_step": "1p",
                        "tran_stop": "1n",
                        "jitter": {"min_cycles": 1},
                    }
                }
            )

    def test_a_gated_bound_whose_population_outruns_the_lock_criterion_is_rejected(self):
        # `lock_time` only reports a lock when at least `min_hold_cycles`
        # cycles of in-band data follow the lock instant, and the jitter
        # population is exactly those cycles. So a gated bound asking for MORE
        # cycles than the lock criterion guarantees FAILs every locked point
        # whose population lands in the gap -- for a shortfall it was
        # arithmetically incapable of avoiding. That is an artefact verdict
        # recorded as a design miss, so the manifest is refused instead.
        with self.assertRaises(measure.MeasureError) as caught:
            measure.MeasureSpec.from_manifest(
                {
                    "measure": {
                        "node": "clk",
                        "tran_step": "1p",
                        "tran_stop": "1n",
                        "lock": {
                            "target_hz": 250e6,
                            "tolerance_frac": 0.02,
                            "window_cycles": 20,
                            "min_hold_cycles": 20,
                        },
                        "jitter": {"max_frac": 0.01, "min_cycles": 50},
                    }
                }
            )
        # The message must name both knobs -- the trap is the relationship
        # between them, not either value on its own.
        message = str(caught.exception)
        self.assertIn("measure.jitter.min_cycles", message)
        self.assertIn("measure.lock.min_hold_cycles", message)
        self.assertIn("50", message)
        self.assertIn("20", message)

    def test_a_population_equal_to_what_the_lock_criterion_guarantees_is_accepted(self):
        # The boundary is the committed manifests' own setting
        # (`min_cycles == min_hold_cycles == 20`): every locked point holds
        # exactly enough cycles, so mode 2 is unreachable and every FAIL the
        # fold produces is a real miss. Must stay legal.
        spec = measure.MeasureSpec.from_manifest(
            {
                "measure": {
                    "node": "clk",
                    "tran_step": "1p",
                    "tran_stop": "1n",
                    "lock": {
                        "target_hz": 250e6,
                        "tolerance_frac": 0.02,
                        "window_cycles": 20,
                        "min_hold_cycles": 20,
                    },
                    "jitter": {"max_frac": 0.01, "min_cycles": 20},
                }
            }
        )
        self.assertEqual(spec.jitter.min_cycles, 20)
        self.assertEqual(spec.lock.min_hold_cycles, 20)

    def test_a_larger_population_stays_legal_where_no_artefact_fail_can_follow(self):
        # The check is scoped to exactly the shape that can mint an artefact
        # FAIL: a lock criterion, a stated bound, and gating on it. Everything
        # else may ask for a better-conditioned statistic than its own lock
        # criterion guarantees -- the shortfall is then reported as "not
        # measured" against that point, never folded into a FAIL.
        base = {
            "node": "clk",
            "tran_step": "1p",
            "tran_stop": "1n",
            "lock": {
                "target_hz": 250e6,
                "tolerance_frac": 0.02,
                "window_cycles": 20,
                "min_hold_cycles": 20,
            },
        }
        legal = (
            # Gating explicitly disabled: the number is reported, not gated.
            {"max_frac": 0.01, "min_cycles": 50, "gate_on_bound": False},
            # No bound stated at all: `_fold_jitter_bound` is a no-op.
            {"min_cycles": 50},
        )
        for block in legal:
            with self.subTest(jitter=block):
                spec = measure.MeasureSpec.from_manifest({"measure": dict(base, jitter=block)})
                self.assertEqual(spec.jitter.min_cycles, 50)

    def test_a_jitter_block_without_a_lock_block_is_unaffected_by_the_coupling(self):
        # `sim/jitter-floor`'s shape: a jitter block and no lock criterion at
        # all, so the population starts at `settle_from` and nothing bounds it
        # below. The new check must not start rejecting it.
        spec = measure.MeasureSpec.from_manifest(
            {
                "measure": {
                    "node": "clk",
                    "tran_step": "1p",
                    "tran_stop": "1n",
                    "jitter": {"max_frac": 0.01, "min_cycles": 500},
                }
            }
        )
        self.assertIsNone(spec.lock)
        self.assertEqual(spec.jitter.min_cycles, 500)

    def test_parses_a_ripple_block_and_orders_the_dump_nodes(self):
        spec = measure.MeasureSpec.from_manifest(
            {
                "measure": {
                    "node": "CLK",
                    "tran_step": "200p",
                    "tran_stop": "100u",
                    "extra_nodes": ["VDD"],
                    "ripple": {"nodes": ["VDD", "xxxtop.vctrl"], "window": "5u"},
                }
            }
        )
        self.assertEqual(spec.ripple.nodes, ("VDD", "xxxtop.vctrl"))
        self.assertAlmostEqual(spec.ripple.window_s, 5e-6)
        # Clock first, then extra_nodes, then any ripple node not yet listed.
        self.assertEqual(spec.dump_nodes, ("CLK", "VDD", "xxxtop.vctrl"))

    def test_malformed_ripple_blocks_are_rejected(self):
        base = {"node": "clk", "tran_step": "1p", "tran_stop": "1u"}
        bad = (
            {"nodes": ["vdd"]},  # no window
            {"window": "100n"},  # no nodes
            {"nodes": [], "window": "100n"},
            {"nodes": ["vdd"], "window": "2u"},  # longer than tran_stop
        )
        for block in bad:
            with self.subTest(block=block):
                with self.assertRaises(measure.MeasureError):
                    measure.MeasureSpec.from_manifest({"measure": dict(base, ripple=block)})
        with self.assertRaises(measure.MeasureError):
            measure.MeasureSpec.from_manifest(
                {
                    "measure": dict(
                        base,
                        ripple={"nodes": ["vdd"], "window": "100n"},
                        sweep={"source": "V2", "values": [0.8]},
                    )
                }
            )

    def test_a_lock_block_without_a_target_is_rejected(self):
        with self.assertRaises(measure.MeasureError):
            measure.MeasureSpec.from_manifest(
                {"measure": {"node": "clk", "tran_step": "1p", "tran_stop": "1n", "lock": {}}}
            )

    def test_a_manifest_with_no_transition_block_parses_to_no_transition_spec(self):
        spec = measure.MeasureSpec.from_manifest(
            {"measure": {"node": "clk", "tran_step": "1p", "tran_stop": "1n"}}
        )
        self.assertIsNone(spec.transition)

    def test_a_bare_true_transition_block_uses_the_10_90_default(self):
        spec = measure.MeasureSpec.from_manifest(
            {
                "measure": {
                    "node": "clk", "tran_step": "1p", "tran_stop": "1n",
                    "transition": True,
                }
            }
        )
        self.assertAlmostEqual(spec.transition.frac_lo, 0.1)
        self.assertAlmostEqual(spec.transition.frac_hi, 0.9)

    def test_a_transition_block_may_state_its_own_fractions(self):
        spec = measure.MeasureSpec.from_manifest(
            {
                "measure": {
                    "node": "clk", "tran_step": "1p", "tran_stop": "1n",
                    "transition": {"frac_lo": 0.2, "frac_hi": 0.8},
                }
            }
        )
        self.assertAlmostEqual(spec.transition.frac_lo, 0.2)
        self.assertAlmostEqual(spec.transition.frac_hi, 0.8)

    def test_malformed_transition_fractions_are_rejected(self):
        bad = (
            {"frac_lo": 0.9, "frac_hi": 0.1},  # inverted
            {"frac_lo": 0.5, "frac_hi": 0.5},  # equal
            {"frac_lo": -0.1, "frac_hi": 0.9},  # out of [0, 1]
            {"frac_lo": 0.1, "frac_hi": 1.1},
        )
        for block in bad:
            with self.subTest(block=block):
                with self.assertRaises(measure.MeasureError):
                    measure.MeasureSpec.from_manifest(
                        {
                            "measure": {
                                "node": "clk", "tran_step": "1p", "tran_stop": "1n",
                                "transition": block,
                            }
                        }
                    )

    def test_a_non_object_non_bool_transition_block_is_rejected(self):
        with self.assertRaises(measure.MeasureError):
            measure.MeasureSpec.from_manifest(
                {
                    "measure": {
                        "node": "clk", "tran_step": "1p", "tran_stop": "1n",
                        "transition": "10-90",
                    }
                }
            )


class ControlBlockTests(unittest.TestCase):
    """The harness injects the analysis itself rather than baking a `.tran`
    card into the schematic, so the transient window is a manifest knob (this
    is what lets sim/pll run a lock-capable window without editing the
    testbench schematic) and every swept point of a sweep campaign runs inside
    one ngspice invocation."""

    def test_unswept_block_runs_one_transient_and_dumps_one_waveform(self):
        spec = measure.MeasureSpec(
            node="clk", tran_step="200p", tran_stop="40u", timeout_s=60
        )
        text = measure.build_control_block(spec)
        self.assertIn("tran 200p 40u", text)
        self.assertIn("wrdata point000.raw v(clk)", text)
        self.assertIn(measure.COMPLETION_MARKER, text)
        self.assertEqual(text.count("tran "), 1)
        self.assertEqual(measure.waveform_names(spec), ["point000.raw"])

    def test_swept_block_alters_the_source_once_per_value(self):
        spec = measure.MeasureSpec(
            node="clk",
            tran_step="20p",
            tran_stop="200n",
            timeout_s=60,
            sweep=(
                measure.SweepPoint(source="V2", value=0.8, label="VCTRL=0.800V"),
                measure.SweepPoint(source="V2", value=1.6, label="VCTRL=1.600V"),
            ),
        )
        text = measure.build_control_block(spec)
        self.assertIn("alter V2 0.8", text)
        self.assertIn("alter V2 1.6", text)
        self.assertEqual(text.count("tran "), 2)
        self.assertEqual(
            measure.waveform_names(spec), ["point000.raw", "point001.raw"]
        )

    def test_initial_conditions_and_uic_are_emitted_when_requested(self):
        spec = measure.MeasureSpec(
            node="clk",
            tran_step="20p",
            tran_stop="200n",
            timeout_s=60,
            ic=("v(xxxvco.ring0)=0",),
            uic=True,
        )
        text = measure.build_control_block(spec)
        self.assertIn(".ic v(xxxvco.ring0)=0", text)
        self.assertIn("tran 20p 200n uic", text)

    def test_single_node_block_is_unchanged_by_the_multi_node_support(self):
        spec = measure.MeasureSpec(
            node="clk", tran_step="200p", tran_stop="40u", timeout_s=60
        )
        text = measure.build_control_block(spec)
        self.assertNotIn("wr_singlescale", text)
        self.assertIn("save v(clk)\n", text)
        self.assertIn("linearize v(clk)\n", text)

    def test_ripple_block_dumps_every_node_on_one_time_column(self):
        spec = measure.MeasureSpec(
            node="CLK",
            tran_step="200p",
            tran_stop="100u",
            timeout_s=60,
            ripple=measure.RippleSpec(nodes=("VDD", "xxxtop.vctrl"), window_s=5e-6),
        )
        text = measure.build_control_block(spec)
        vectors = "v(CLK) v(VDD) v(xxxtop.vctrl)"
        self.assertIn("set wr_singlescale", text)
        self.assertIn(f"save {vectors}\n", text)
        # linearize must name every dumped vector: with arguments it builds a
        # new plot holding only those, and wrdata reads from that plot.
        self.assertIn(f"linearize {vectors}\n", text)
        self.assertIn(f"wrdata point000.raw {vectors}\n", text)

    def test_waveform_dumps_use_the_raw_extension_so_they_stay_uncommitted(self):
        # sim/README.md's retention policy keeps waveform dumps out of the
        # committed evidence trail, and the repo's root .gitignore implements
        # that with a tree-wide `*.raw` rule. The dump filenames must land
        # inside that rule or every corner run would try to commit megabytes
        # of regenerable samples.
        spec = measure.MeasureSpec(
            node="clk", tran_step="20p", tran_stop="200n", timeout_s=60
        )
        for name in measure.waveform_names(spec):
            self.assertTrue(name.endswith(".raw"), name)


if __name__ == "__main__":
    unittest.main()
