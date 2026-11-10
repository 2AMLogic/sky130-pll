#!/usr/bin/env python3
"""Unit tests for the `measure.quadrature` reducer and `sweep.per_point` tables (issue #422).

Synthetic waveforms with a known offset/duty -- no PDK, ngspice or xschem.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import measure  # noqa: E402
from test_measure import square_wave  # noqa: E402

F = 25e6
STEP = 50e-12


def _spec(**quad):
    manifest = {
        "measure": {
            "node": "clk",
            "tran_step": "50p",
            "tran_stop": "800n",
            "settle_from": "200n",
            "extra_nodes": ["clk90"],
            "require_oscillation": False,
            "quadrature": {"ref": "clk", "quad": "clk90", **quad},
            "sweep": {
                "source": "V2",
                "quantity": "VCTRL",
                "values": [0.7, 0.71],
                "per_point": {"tt_27c_1.80v": [0.7123, 0.7183]},
            },
        }
    }
    return measure.MeasureSpec.from_manifest(manifest)


def _waves(lag_deg, duty_q=0.5):
    t, ref = square_wave(freq_hz=F, duration_s=800e-9, step_s=STEP)
    # quad lags ref by lag_deg of the period
    _, q = square_wave(
        freq_hz=F, duty=duty_q, duration_s=800e-9, step_s=STEP, t0_s=lag_deg / 360.0 / F
    )
    return t, ref, q


class QuadratureTests(unittest.TestCase):
    def test_offset_and_duty_are_measured_from_edges(self):
        spec = _spec(window_deg=72, target_freq_hz=F)
        t, ref, q = _waves(95.0)
        m = measure.measure_trace(t, ref, spec, 1.8, extra={"clk90": q})
        self.assertAlmostEqual(m.quad.offset_mean_deg, 95.0, delta=0.5)
        self.assertAlmostEqual(m.quad.duty_ref, 0.5, delta=0.01)
        self.assertEqual(m.quad.grade, "PASS")
        self.assertTrue(m.quad.freq_in_band)

    def test_offset_outside_window_is_a_recorded_miss_not_a_harness_failure(self):
        spec = _spec(window_deg=10)
        t, ref, q = _waves(120.0)
        m = measure.measure_trace(t, ref, spec, 1.8, extra={"clk90": q})
        self.assertEqual(m.quad.grade, "FAIL")
        self.assertTrue(m.passed)  # grading is reported, never a harness gate
        self.assertIn("outside 90 +/- 10 deg", m.quad.reasons[0])

    def test_duty_bound_applies_to_the_quad_node_too(self):
        spec = _spec(window_deg=72)
        t, ref, q = _waves(90.0, duty_q=0.60)
        m = measure.measure_trace(t, ref, spec, 1.8, extra={"clk90": q})
        self.assertEqual(m.quad.grade, "FAIL")
        self.assertTrue(any("v(clk90) duty" in r for r in m.quad.reasons))

    def test_wrong_frequency_is_not_in_band(self):
        spec = _spec(target_freq_hz=50e6)
        t, ref, q = _waves(90.0)
        m = measure.measure_trace(t, ref, spec, 1.8, extra={"clk90": q})
        self.assertFalse(m.quad.freq_in_band)
        self.assertEqual(m.quad.grade, "FAIL")

    def test_dead_quad_node_fails_rather_than_dropping(self):
        spec = _spec()
        t, ref, _ = _waves(90.0)
        m = measure.measure_trace(t, ref, spec, 1.8, extra={"clk90": [0.0] * len(t)})
        self.assertEqual(m.quad.grade, "FAIL")
        self.assertIsNone(m.quad.offset_mean_deg)

    def test_quad_nodes_are_dumped(self):
        spec = _spec()
        self.assertEqual(spec.dump_nodes[:2], ("clk", "clk90"))


class PerPointSweepTests(unittest.TestCase):
    def test_per_point_values_replace_the_default_sweep_for_that_corner_only(self):
        spec = _spec()
        hit = spec.resolved("tt_27c_1.80v-")
        miss = spec.resolved("ss_27c_1.80v-")
        self.assertEqual([p.value for p in hit.sweep], [0.7123, 0.7183])
        self.assertEqual([p.value for p in miss.sweep], [0.7, 0.71])
        self.assertEqual(hit.sweep[0].label, "VCTRL=0.7123V")

    def test_control_block_alters_the_per_point_values(self):
        spec = _spec()
        block = measure.build_control_block(spec, "tt_27c_1.80v-")
        self.assertIn("alter V2 0.7123", block)
        self.assertNotIn("alter V2 0.7 ", block)

    def test_length_mismatch_is_refused(self):
        with self.assertRaises(measure.MeasureError):
            measure.MeasureSpec.from_manifest({"measure": {
                "node": "clk", "tran_step": "50p", "tran_stop": "1n",
                "sweep": {"source": "V2", "values": [1, 2], "per_point": {"x": [1]}},
            }})


if __name__ == "__main__":
    unittest.main()
