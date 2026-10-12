#!/usr/bin/env python3
"""PDK-free tests for the LOCK timing measurement contract (issue #273).

    python3 -m unittest discover -s sim/tests -p 'test_locktiming.py' -v
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import locktiming as L  # noqa: E402


def manifest(product="p1"):
    probe = {"input": "in", "tap": "tap", "threshold_v": 0.9,
             "input_edge": "rising", "tap_edge": "rising"}
    return {
        "schema": L.MANIFEST_SCHEMA, "product_id": product, "candidate_id": "c1",
        "units": {"time": "s", "voltage": "V", "temperature": "C", "capacitance": "F"},
        "inventory": {"cells": [{"name": "x1", "drive": "1", "stage": "0"}],
                      "taps": ["tap"], "dividers": ["div0"]},
        "measurement": {
            "load_f": 1e-14, "slew_s": 1e-10, "acq": dict(probe),
            "rel": dict(probe, input_edge="falling", tap_edge="falling"),
            "tick": {"signal": "tick", "threshold_v": 0.9, "edge": "rising"},
            "raw": {"signal": "raw", "threshold_v": 0.9, "edge": "rising"},
            "startup": {"signal": "raw", "threshold_v": 0.9, "edge": "rising"}},
        "windows": {"enable_s": 1e-9, "settle_s": 1e-9, "window_start_s": 2e-9,
                    "window_stop_s": 2e-6, "step_s": 1e-11, "timeout_s": 600},
        "grid": [{"process": p, "temp_c": t, "vdd_v": v} for p, t, v in L.GRID],
    }


def edge_wave(t0, t1, rising=True, t_end=2.1e-6):
    lo, hi = (0.0, 1.8) if rising else (1.8, 0.0)
    return {"t": [0.0, t0, t1, t_end], "v": [lo, lo, hi, hi]}


def clock(period, t_end=2.1e-6):
    t, v, x = [0.0], [0.0], 0.0
    while x < t_end:
        for dt, lv in ((period * 0.01, 1.8), (period / 2, 1.8), (period * 0.01, 0.0),
                       (period / 2 - period * 0.02, 0.0)):
            x += dt
            t.append(x)
            v.append(lv)
    return {"t": t, "v": v}


def waves(acq=2e-9, rel=6e-9, tick=200e-9):
    inp = {"t": [0, 3e-9, 4e-9, 20e-9, 21e-9, 3e-6],
           "v": [0, 0, 1.8, 1.8, 0, 0]}
    # input crosses 0.9 at 3.5ns / 20.5ns
    tap = {"t": [0, 3.5e-9 + acq - 1e-12, 3.5e-9 + acq + 1e-12,
                 20.5e-9 + rel - 1e-12, 20.5e-9 + rel + 1e-12, 3e-6],
           "v": [0, 0, 1.8, 1.8, 0, 0]}
    return {"in": inp, "tap": tap, "tick": clock(tick), "raw": clock(1e-9)}


def point(c, **kw):
    return {"coord": {"process": c[0], "temp_c": c[1], "vdd_v": c[2]},
            "sim_ok": True, "waveforms": waves(**kw)}


def rows(m, **kw):
    return [L.reduce_point(m, point(c, **kw)) for c in L.GRID]


class Crossings(unittest.TestCase):
    def test_interpolated_nonuniform(self):
        t, v = [0, 1, 4], [0.0, 0.0, 1.8]
        self.assertAlmostEqual(L.crossings(t, v, 0.9, "rising")[0], 2.5)

    def test_exact_boundary_counted_once(self):
        t, v = [0, 1, 2, 3], [0.0, 0.9, 1.8, 1.8]
        self.assertEqual(L.crossings(t, v, 0.9, "rising"), [1])

    def test_falling_and_polarity(self):
        t, v = [0, 1, 2], [1.8, 0.9, 0.0]
        self.assertEqual(L.crossings(t, v, 0.9, "falling"), [1])
        self.assertEqual(L.crossings(t, v, 0.9, "rising"), [])

    def test_bad_edge(self):
        with self.assertRaises(L.LockTimingError):
            L.crossings([0, 1], [0, 1], 0.5, "up")

    def test_malformed_waveforms(self):
        for w in ({"t": [0, 1, 1], "v": [0, 1, 2]}, {"t": [0, 2, 1], "v": [0, 1, 2]},
                  {"t": [0, float("nan")], "v": [0, 1]}, {"t": [0, 1], "v": [0, float("inf")]},
                  {"t": [0, 1], "v": [0]}, {"t": [0], "v": [0]}, {"t": [True, 1], "v": [0, 1]}):
            with self.assertRaises(L.LockTimingError, msg=w):
                L.validate_waveform(w)


class Manifest(unittest.TestCase):
    def test_valid(self):
        L.validate_manifest(manifest())
        self.assertEqual(len(L.GRID), 45)

    def test_rejections(self):
        def bad(f):
            m = manifest()
            f(m)
            with self.assertRaises(L.LockTimingError):
                L.validate_manifest(m)
        bad(lambda m: m.update(schema="x"))
        bad(lambda m: m["grid"].pop())
        bad(lambda m: m["grid"].append(copy.deepcopy(m["grid"][0])))
        bad(lambda m: m["inventory"].update(taps=[]))
        bad(lambda m: m["measurement"]["acq"].update(input_edge="up"))
        bad(lambda m: m["measurement"].update(slew_s=0))
        bad(lambda m: m["windows"].update(window_start_s=1.5e-9))
        bad(lambda m: m["windows"].update(window_stop_s=1e-9))
        bad(lambda m: m["units"].update(time="ns"))


class Reduce(unittest.TestCase):
    def test_values(self):
        r = L.reduce_point(manifest(), point(L.GRID[0], acq=2e-9, rel=6e-9, tick=200e-9))
        self.assertEqual(r["status"], L.OK, r)
        self.assertAlmostEqual(r["w_acq_s"], 2e-9, delta=1e-12)
        self.assertAlmostEqual(r["w_rel_s"], 6e-9, delta=1e-12)
        self.assertAlmostEqual(r["tick_s"], 200e-9, delta=1e-12)
        self.assertAlmostEqual(r["raw_period_s"], 1e-9, delta=1e-12)
        self.assertGreater(r["startup_latency_s"], 0)

    def test_sim_failed(self):
        p = point(L.GRID[0])
        p["sim_ok"] = False
        self.assertEqual(L.reduce_point(manifest(), p)["status"], L.SIM_FAILED)

    def test_no_oscillation(self):
        p = point(L.GRID[0])
        p["waveforms"]["raw"] = {"t": [0, 3e-6], "v": [0, 0]}
        r = L.reduce_point(manifest(), p)
        self.assertEqual(r["status"], L.ABSENT_CROSSING)
        self.assertIsNone(r["tick_s"])

    def test_absent_tap(self):
        p = point(L.GRID[0])
        p["waveforms"]["tap"] = {"t": [0, 3e-6], "v": [0, 0]}
        self.assertEqual(L.reduce_point(manifest(), p)["status"], L.ABSENT_CROSSING)

    def test_insufficient_settling(self):
        p = point(L.GRID[0])
        p["waveforms"]["tick"] = {"t": [0, 1e-6], "v": [0, 1.8]}  # ends before stop
        self.assertEqual(L.reduce_point(manifest(), p)["status"], L.INSUFFICIENT_SETTLING)

    def test_startup_exclusion(self):
        m = manifest()
        p = point(L.GRID[0])
        # an early edge before enable_s must be excluded from startup latency
        # edges at 0.05ns (pre-enable, excluded), 5.05ns and 8.05ns (in window)
        p["waveforms"]["raw"] = {
            "t": [0, 0.1e-9, 0.2e-9, 5e-9, 5.1e-9, 6e-9, 8e-9, 8.1e-9, 3e-6],
            "v": [0, 1.8, 0, 0, 1.8, 1.8, 0, 1.8, 1.8]}
        r = L.reduce_point(m, p)
        self.assertEqual(r["status"], L.OK, r)
        self.assertGreater(r["startup_latency_s"], 3.9e-9)

    def test_malformed_recorded(self):
        p = point(L.GRID[0])
        p["waveforms"]["tick"] = {"t": [0, 0, 1], "v": [0, 1, 2]}
        r = L.reduce_point(manifest(), p)
        self.assertEqual(r["status"], L.MALFORMED)
        self.assertTrue(r["error"])

    def test_missing_waveform(self):
        p = point(L.GRID[0])
        del p["waveforms"]["tap"]
        self.assertEqual(L.reduce_point(manifest(), p)["status"], L.MALFORMED)


class Grade(unittest.TestCase):
    def grade(self, **kw):
        m = manifest()
        return L.grade_candidate(m, rows(m, **kw))

    def test_pass(self):
        g = self.grade()
        self.assertTrue(g["complete"])
        self.assertEqual(g["verdict"], L.PASS, g["verdicts"])

    def test_inclusive_boundaries_pass(self):
        # a point exactly on a bound must not be a miss (interp tolerance via 1ps pad)
        for kw in ({"acq": 1.5e-9 + 2e-12}, {"acq": 4.0e-9 - 2e-12, "rel": 10e-9 - 2e-12}):
            self.assertEqual(self.grade(**kw)["verdict"], L.PASS, kw)

    def test_just_outside_misses(self):
        self.assertEqual(self.grade(acq=1.49e-9)["verdicts"]["w_acq"], L.MISS)
        self.assertEqual(self.grade(acq=4.01e-9, rel=6e-9)["verdicts"]["w_acq"], L.MISS)
        self.assertEqual(self.grade(rel=4.4e-9)["verdicts"]["w_rel"], L.MISS)
        self.assertEqual(self.grade(rel=10.1e-9)["verdicts"]["w_rel"], L.MISS)
        self.assertEqual(self.grade(tick=124e-9)["verdicts"]["tick"], L.MISS)
        self.assertEqual(self.grade(tick=501e-9)["verdicts"]["tick"], L.MISS)
        self.assertEqual(self.grade(tick=501e-9)["verdict"], L.MISS)

    def test_band_edges_exact(self):
        for name, lo, hi in (("w_acq", *L.BANDS_S["w_acq"]), ("tick", *L.BANDS_S["tick"])):
            self.assertEqual(L._band([lo, hi], lo, hi, True), L.PASS, name)
            self.assertEqual(L._band([lo * 0.999], lo, hi, True), L.MISS)
            self.assertEqual(L._band([hi * 1.001], lo, hi, True), L.MISS)

    def test_inverted_hysteresis(self):
        g = self.grade(acq=4.0e-9 - 2e-12, rel=4.5e-9 + 2e-12)  # in-band, but only barely ordered
        self.assertEqual(g["verdicts"]["hysteresis_max_acq_lt_min_rel"], L.PASS)
        # equal envelopes violate the strict inequality
        v = L.grade_candidate(manifest(), rows(manifest(), acq=4e-9, rel=4.5e-9))
        self.assertNotEqual(v["verdict"], L.PASS)
        m = manifest()
        r = rows(m)
        for x in r:
            x["w_rel_s"] = x["w_acq_s"]
        self.assertEqual(L.grade_candidate(m, r)["verdicts"]["hysteresis_max_acq_lt_min_rel"],
                         L.MISS)

    def test_rel_ceiling(self):
        m = manifest()
        r = rows(m)
        for x in r:
            x["w_rel_s"] = 12e-9
        g = L.grade_candidate(m, r)
        self.assertEqual(g["verdicts"]["rel_ceiling_lt_12ns"], L.MISS)

    def test_missing_point_inconclusive_not_pass(self):
        m = manifest()
        g = L.grade_candidate(m, rows(m)[:-1])
        self.assertFalse(g["complete"])
        self.assertEqual(len(g["missing"]), 1)
        self.assertEqual(g["verdict"], L.INCONCLUSIVE)

    def test_miss_survives_incomplete(self):
        m = manifest()
        g = L.grade_candidate(m, rows(m, tick=600e-9)[:-1])
        self.assertEqual(g["verdict"], L.MISS)
        self.assertFalse(g["complete"])

    def test_duplicate_flagged(self):
        m = manifest()
        r = rows(m)
        r.append(copy.deepcopy(r[0]))
        g = L.grade_candidate(m, r)
        self.assertFalse(g["complete"])
        self.assertEqual(g["duplicates"], [L.GRID[0]])
        self.assertNotEqual(g["verdict"], L.PASS)

    def test_failed_point_listed(self):
        m = manifest()
        r = rows(m)
        r[3]["status"] = L.SIM_FAILED
        g = L.grade_candidate(m, r)
        self.assertEqual(g["failed"], {L.GRID[3]: L.SIM_FAILED})
        self.assertEqual(g["verdict"], L.INCONCLUSIVE)

    def test_unexpected_coordinate(self):
        m = manifest()
        r = rows(m)
        r.append(dict(r[0], coord={"process": "tt", "temp_c": 30.0, "vdd_v": 1.8}))
        g = L.grade_candidate(m, r)
        self.assertEqual(len(g["unexpected"]), 1)
        self.assertFalse(g["complete"])

    def test_raw_period_diagnostic_only(self):
        g = self.grade()
        self.assertNotIn("raw_period", g["verdicts"])
        self.assertIsNotNone(g["diagnostic_raw_period_s"])


class Handoff(unittest.TestCase):
    def result(self, product):
        m = manifest(product)
        return L.grade_candidate(m, rows(m))

    def test_subset_never_ready(self):
        h = L.handoff([self.result("a")], ["a", "b", "c"])
        self.assertEqual(h["scope"], "SUBSET")
        self.assertFalse(h["handoff_ready"])
        self.assertEqual(h["products_absent"], ["b", "c"])

    def test_full_ready(self):
        h = L.handoff([self.result(p) for p in "abc"], ["a", "b", "c"])
        self.assertEqual(h["scope"], "FULL")
        self.assertTrue(h["handoff_ready"])

    def test_full_with_miss_not_ready(self):
        m = manifest("c")
        bad = L.grade_candidate(m, rows(m, tick=900e-9))
        h = L.handoff([self.result("a"), self.result("b"), bad], ["a", "b", "c"])
        self.assertFalse(h["handoff_ready"])

    def test_bad_required_products(self):
        with self.assertRaises(L.LockTimingError):
            L.handoff([], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
