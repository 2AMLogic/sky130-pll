#!/usr/bin/env python3
"""Unit tests for sim/power/reduce.py (issue #233).

No PDK, ngspice or xschem required: every trace below is synthetic, built so
that the true mean supply current over a whole number of clock cycles is known
by construction.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POWER_DIR = REPO_ROOT / "sim" / "power"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"power_{name}", POWER_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"power_{name}"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


reduce_mod = _load("reduce")
sys.path.insert(0, str(POWER_DIR))
mint_mod = _load("mint")

VDD = 1.8
DT = 0.05e-9


def square_clock(period: float, t_end: float, *, dt: float = DT, vdd: float = VDD):
    """Rail-to-rail clock with finite (2 samples) edges; rises at k*period."""
    n = int(round(t_end / dt)) + 1
    times = [i * dt for i in range(n)]
    vals = []
    for t in times:
        ph = (t % period) / period
        vals.append(vdd if ph < 0.5 else 0.0)
    return times, vals


def wave_with_current(period: float, t_end: float, i_fn):
    """Waveform dict with clk + a current trace (negative = sourcing, like i(v1))."""
    times, clk = square_clock(period, t_end)
    return {
        "time": times,
        "v(clk)": clk,
        "i(v1)": [-i_fn(t) for t in times],
    }


class WindowMeanTests(unittest.TestCase):
    def test_constant(self):
        t = [0.0, 1.0, 2.0, 3.0]
        self.assertAlmostEqual(reduce_mod.window_mean(t, [5.0] * 4, 0.5, 2.5), 5.0)

    def test_ramp_exact_and_end_interpolation(self):
        t = [0.0, 1.0, 2.0]
        v = [0.0, 10.0, 20.0]
        # mean of 10*x over [0.25, 1.75] is 10
        self.assertAlmostEqual(reduce_mod.window_mean(t, v, 0.25, 1.75), 10.0)

    def test_nonuniform_grid_is_time_weighted(self):
        # value 0 for 1 s then 10 for 3 s -> mean 7.5, regardless of sample count
        t = [0.0, 1.0, 1.0000001, 2.0, 3.0, 4.0]
        v = [0.0, 0.0, 10.0, 10.0, 10.0, 10.0]
        self.assertAlmostEqual(reduce_mod.window_mean(t, v, 0.0, 4.0), 7.5, places=5)

    def test_rejects_empty_and_out_of_range(self):
        t = [0.0, 1.0]
        with self.assertRaises(reduce_mod.PowerError):
            reduce_mod.window_mean(t, [0.0, 0.0], 0.5, 0.5)
        with self.assertRaises(reduce_mod.PowerError):
            reduce_mod.window_mean(t, [0.0, 0.0], 0.5, 2.0)


class ReduceStageTests(unittest.TestCase):
    PERIOD = 10e-9

    def stage(self, **kw):
        base = {
            "id": "s", "kind": "active", "label": "s",
            "t0": 20e-9, "t1": 120e-9, "settle": 20e-9, "cycles": 4,
        }
        base.update(kw)
        return base

    def test_whole_cycle_mean_is_exact_where_fixed_window_is_not(self):
        # Current = I0 while the clock is high, 3*I0 while low: cycle mean 2*I0.
        i0 = 100e-6

        def i_fn(t):
            return i0 if (t % self.PERIOD) < self.PERIOD / 2 else 3 * i0

        wave = wave_with_current(self.PERIOD, 150e-9, i_fn)
        res = reduce_mod.reduce_stage(
            wave, self.stage(), align_node="v(clk)", supply_v=VDD
        )
        self.assertTrue(res.ok, res.reason)
        self.assertAlmostEqual(res.i_a, 2 * i0, delta=0.01 * i0)
        self.assertAlmostEqual(res.f_hz, 1 / self.PERIOD, delta=1e6)
        self.assertAlmostEqual(res.p_w, res.i_a * VDD)
        self.assertEqual(res.cycles, 4)
        # a deliberately misaligned half-cycle window is biased by ~I0/9: the
        # error the whole-cycle alignment exists to remove.
        times, i_vec = wave["time"], wave["i(v1)"]
        t_a = 40e-9
        misaligned = -reduce_mod.window_mean(times, i_vec, t_a, t_a + 4.5 * self.PERIOD)
        self.assertGreater(abs(misaligned - 2 * i0), 0.02 * i0)

    def test_window_starts_at_first_edge_after_settle(self):
        wave = wave_with_current(self.PERIOD, 150e-9, lambda t: 50e-6)
        res = reduce_mod.reduce_stage(
            wave, self.stage(settle=23e-9), align_node="v(clk)", supply_v=VDD
        )
        self.assertTrue(res.ok, res.reason)
        # edges rise at multiples of 10 ns (interpolated through the half-swing)
        self.assertAlmostEqual(res.window[0], 50e-9, delta=0.2e-9)  # t0 20 ns + settle 23 ns = 43 ns
        self.assertAlmostEqual(res.window[1] - res.window[0], 40e-9, delta=0.2e-9)

    def test_too_few_edges_is_a_failure_not_a_number(self):
        wave = wave_with_current(self.PERIOD, 150e-9, lambda t: 50e-6)
        res = reduce_mod.reduce_stage(
            wave, self.stage(cycles=40), align_node="v(clk)", supply_v=VDD
        )
        self.assertFalse(res.ok)
        self.assertIsNone(res.i_a)
        self.assertIn("rising edges", res.reason)

    def test_missing_vector_reported(self):
        wave = wave_with_current(self.PERIOD, 150e-9, lambda t: 50e-6)
        res = reduce_mod.reduce_stage(
            wave, self.stage(), align_node="v(nope)", supply_v=VDD
        )
        self.assertFalse(res.ok)
        self.assertIn("no vector", res.reason)

    def test_idle_stage_plain_mean_and_edge_count(self):
        times = [i * DT for i in range(int(150e-9 / DT) + 1)]
        wave = {
            "time": times,
            "v(clk)": [0.0] * len(times),
            "i(v1)": [-2e-6] * len(times),
        }
        stage = {"id": "idle", "kind": "idle", "t0": 0.0, "t1": 100e-9, "settle": 60e-9}
        res = reduce_mod.reduce_stage(wave, stage, align_node="v(clk)", supply_v=VDD)
        self.assertTrue(res.ok)
        self.assertAlmostEqual(res.i_a, 2e-6)
        self.assertEqual(res.edges_in_window, 0)
        self.assertAlmostEqual(res.p_w, 2e-6 * VDD)

    def test_idle_stage_flags_unexpected_activity(self):
        wave = wave_with_current(self.PERIOD, 150e-9, lambda t: 1e-6)
        stage = {"id": "idle", "kind": "idle", "t0": 0.0, "t1": 100e-9, "settle": 20e-9}
        res = reduce_mod.reduce_stage(wave, stage, align_node="v(clk)", supply_v=VDD)
        self.assertTrue(res.ok)
        self.assertGreater(res.edges_in_window, 0)

    def test_threshold_tracks_the_points_own_supply(self):
        # A 1.62 V rail: half-swing 0.81 V. A clock that only reaches 1.62 V must
        # still count; a threshold pinned at 0.9 V would also, but one pinned
        # at the 1.98 V corner's 0.99 V would not.
        times, clk = square_clock(self.PERIOD, 150e-9, vdd=1.62)
        wave = {"time": times, "v(clk)": clk, "i(v1)": [-1e-6] * len(times)}
        res = reduce_mod.reduce_stage(
            wave, self.stage(), align_node="v(clk)", supply_v=1.62
        )
        self.assertTrue(res.ok, res.reason)

    def test_reduce_point_covers_every_stage(self):
        wave = wave_with_current(self.PERIOD, 150e-9, lambda t: 50e-6)
        doc = {
            "align_node": "v(clk)",
            "stages": [
                {"id": "idle", "kind": "idle", "t0": 0.0, "t1": 15e-9, "settle": 5e-9},
                self.stage(),
            ],
        }
        out = reduce_mod.reduce_point(wave, doc, supply_v=VDD)
        self.assertEqual([r.stage_id for r in out], ["idle", "s"])


class InterpolationTests(unittest.TestCase):
    def test_interpolates_between_bracketing_stages(self):
        pts = [(50e6, 10e-6), (150e6, 30e-6), (300e6, 60e-6)]
        i, note = reduce_mod.interpolate_at_frequency(pts, 100e6)
        self.assertAlmostEqual(i, 20e-6)
        self.assertIn("interpolated", note)

    def test_exact_hit_returns_measured_value(self):
        pts = [(100e6, 20e-6), (200e6, 40e-6)]
        i, _ = reduce_mod.interpolate_at_frequency(pts, 200e6)
        self.assertAlmostEqual(i, 40e-6)

    def test_never_extrapolates(self):
        pts = [(150e6, 30e-6), (300e6, 60e-6)]
        i, note = reduce_mod.interpolate_at_frequency(pts, 100e6)
        self.assertIsNone(i)
        self.assertIn("outside", note)

    def test_needs_two_points_and_ignores_unmeasured(self):
        i, note = reduce_mod.interpolate_at_frequency([(100e6, 1e-6), (None, None)], 100e6)
        self.assertIsNone(i)
        self.assertIn("fewer than two", note)

    def test_static_dynamic_split(self):
        s, d = reduce_mod.split_static_dynamic(30e-6, 2e-6)
        self.assertAlmostEqual(s, 2e-6)
        self.assertAlmostEqual(d, 28e-6)
        self.assertEqual(reduce_mod.split_static_dynamic(None, 2e-6), (None, None))


class LoadWaveformTests(unittest.TestCase):
    def test_round_trip_lowercases_names(self):
        doc = {
            "plotname": "Transient Analysis",
            "variables": [
                {"index": 0, "name": "time", "type": "time"},
                {"index": 1, "name": "I(v1)", "type": "current"},
            ],
            "points": [[0.0, -1e-6], [1e-9, -2e-6]],
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "w.json"
            p.write_text(json.dumps(doc))
            w = reduce_mod.load_waveform(p)
        self.assertEqual(w["i(v1)"], [-1e-6, -2e-6])
        self.assertEqual(w["time"], [0.0, 1e-9])


def _stage(sid, i_a, kind="active", f_hz=None, ok=True):
    return reduce_mod.StageResult(sid, kind, sid, ok, i_a=i_a, p_w=None, f_hz=f_hz)


class RollupTests(unittest.TestCase):
    KEY = ("tt", 1.8, 27.0)

    def data(self, **over):
        vco = {
            "idle": _stage("idle", 2e-6, "idle"),
            "a": _stage("a", 20e-6, f_hz=50e6),
            "b": _stage("b", 60e-6, f_hz=150e6),
        }
        div = {"idle": _stage("idle", 1e-6, "idle"), "f100m": _stage("f100m", 10e-6)}
        pfd = {"idle": _stage("idle", 3e-6, "idle"), "25m_lock": _stage("25m_lock", 14e-6)}
        d = {
            "vco": {self.KEY: {"stages": vco, "errors": [], "xchk": {}}},
            "divider-n4": {self.KEY: {"stages": div, "errors": [], "xchk": {}}},
            "pfd-cp": {self.KEY: {"stages": pfd, "errors": [], "xchk": {}}},
        }
        d.update(over)
        return d

    def test_sum_of_blocks_and_static_dynamic_split(self):
        rows = mint_mod.rollup(self.data(), [self.KEY], 100e6, mint_mod.ROLLUPS[0])
        r = rows[self.KEY]
        self.assertTrue(r["ok"])
        # vco interpolated to 100 MHz = 40 uA; + 10 uA divider + 14 uA pfd
        self.assertAlmostEqual(r["i_total_a"], 64e-6)
        self.assertAlmostEqual(r["i_static_a"], 6e-6)  # 2 + 1 + 3
        self.assertAlmostEqual(r["i_dynamic_a"], 58e-6)
        self.assertAlmostEqual(r["p_total_w"], 64e-6 * 1.8)
        self.assertAlmostEqual(r["p_static_w"] + r["p_dynamic_w"], r["p_total_w"])

    def test_unbracketed_target_is_not_rolled_up(self):
        rows = mint_mod.rollup(self.data(), [self.KEY], 400e6, mint_mod.ROLLUPS[0])
        self.assertFalse(rows[self.KEY]["ok"])

    def test_failed_stage_blocks_rollup(self):
        d = self.data()
        d["pfd-cp"][self.KEY]["stages"]["25m_lock"] = _stage("25m_lock", None, ok=False)
        rows = mint_mod.rollup(d, [self.KEY], 100e6, mint_mod.ROLLUPS[0])
        self.assertFalse(rows[self.KEY]["ok"])

    def test_slow_vco_ladder_stage_is_data_not_a_failure(self):
        entry = {"errors": [], "stages": {
            "idle": _stage("idle", 1e-6, "idle"),
            "slow": _stage("slow", None, ok=False),
            "ok": _stage("ok", 5e-6, f_hz=1e8),
        }}
        self.assertFalse(mint_mod.corner_bad("vco", entry))
        self.assertTrue(mint_mod.corner_bad("pfd-cp", entry))
        entry["stages"]["idle"] = _stage("idle", None, "idle", ok=False)
        self.assertTrue(mint_mod.corner_bad("vco", entry))
        self.assertTrue(mint_mod.corner_bad("vco", {"errors": ["no waveform"], "stages": {}}))

    def test_corner_key_reads_the_klt_corner_shape(self):
        c = {"process": "ss", "supply_v": {"v1": 1.62}, "temperature_c": -40}
        self.assertEqual(mint_mod.corner_key(c), ("ss", 1.62, -40.0))

    def test_unit_formatting(self):
        self.assertEqual(mint_mod.fmt_i(5e-10), "0.50 nA")
        self.assertEqual(mint_mod.fmt_i(14e-6), "14.00 uA")
        self.assertEqual(mint_mod.fmt_p(2.5e-3), "2.5000 mW")


if __name__ == "__main__":
    unittest.main()
