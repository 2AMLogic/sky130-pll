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

    def test_a_lock_block_without_a_target_is_rejected(self):
        with self.assertRaises(measure.MeasureError):
            measure.MeasureSpec.from_manifest(
                {"measure": {"node": "clk", "tran_step": "1p", "tran_stop": "1n", "lock": {}}}
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
