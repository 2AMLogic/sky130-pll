#!/usr/bin/env python3
"""PDK-free tests for the divider Fmax campaign (issue #244).

No PDK, ngspice or xschem: waveforms are synthesized from a model divider, and
the campaign driver is exercised end to end against a fake execution backend
that "simulates" by evaluating that model.

    python3 -m unittest discover -s sim/tests -p 'test_fmax.py' -v
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import executor as executor_mod  # noqa: E402
from harness import fmax as F  # noqa: E402
from harness import fmax_cli as C  # noqa: E402
from harness import fmax_report  # noqa: E402
from harness import measure as measure_mod  # noqa: E402

MANIFEST_PATH = SIM_DIR / "divider-fmax" / "testbench" / "fmax.json"
MANIFEST = json.loads(MANIFEST_PATH.read_text())
SPEC = F.FmaxSpec.from_manifest(MANIFEST)

NETLIST = """* fake
V1 VDD GND 1.8
V2 CLK GND pulse(0 1.8 0 12.5p 12.5p 442p 909p)
V3 RESETB GND pwl(0 0 5n 0 6n 1.8)
.lib /fake/sky130.lib.spice tt
.end
"""


def output_edges(plan: F.ProbePlan, *, skip_cycles=(), extra_edges=(), dead_after=None,
                 period_scale=1.0):
    """Rising-edge times of a model FBCLK for `plan`: one edge per N CLK cycles
    from reset release. `skip_cycles` drops output cycles (lost division),
    `dead_after` silences the output after that time, `period_scale` models a
    divider that divides by the wrong ratio."""
    edges, k = [], 1
    period = plan.expected_out_period_s * period_scale
    while True:
        t = plan.reset_high_at_s + 0.3e-9 + k * period
        if t > plan.tran_stop_s:
            break
        if k not in skip_cycles and (dead_after is None or t < dead_after):
            edges.append(t)
        k += 1
    return sorted(edges + list(extra_edges))


def trace(plan: F.ProbePlan, edges, width=0.1e-9, tr=20e-12):
    """A sparse piecewise-linear FBCLK trace (rail to rail) through `edges`."""
    v = plan.supply_v
    times, vals = [0.0], [0.0]
    for e in edges:
        times += [e - tr / 2, e + tr / 2, e + width - tr / 2, e + width + tr / 2]
        vals += [0.0, v, v, 0.0]
    times.append(plan.tran_stop_s)
    vals.append(0.0)
    return times, vals


def judge(plan, edges):
    t, v = trace(plan, edges)
    return F.classify_waveform(t, v, plan, threshold_frac=0.5, hysteresis_frac=0.15)


class StimulusTargetCoupling(unittest.TestCase):
    def test_period_width_and_target_follow_one_frequency(self):
        for n in (4, 5, 25, 63, 64):
            for f in (800e6, 1175e6, 2600e6):
                p = F.stimulus_for(SPEC, n, f, 1.62)
                self.assertAlmostEqual(p.clk_period_s * f, 1.0, places=9)
                self.assertAlmostEqual(p.expected_out_period_s, n / f, places=18)
                # 50% points are high for duty*period: pw + one edge time.
                self.assertAlmostEqual(
                    (p.clk_width_s + p.rise_s) / p.clk_period_s, SPEC.stimulus.duty, places=9
                )
                self.assertGreater(p.steady_from_s, p.reset_high_at_s)
                self.assertGreater(p.tran_stop_s, p.steady_from_s + 9 * p.expected_out_period_s)

    def test_patched_netlist_carries_the_same_numbers(self):
        p = F.stimulus_for(SPEC, 25, 1250e6, 1.98)
        text = F.patch_stimulus(NETLIST, p)
        m = re.search(r"^V2 CLK GND pulse\(0 ([\d.]+) 0 ([\d.]+)p ([\d.]+)p ([\d.]+)p ([\d.]+)p\)", text, re.M)
        self.assertIsNotNone(m)
        self.assertAlmostEqual(float(m.group(1)), 1.98)  # tracks the supply
        self.assertAlmostEqual(float(m.group(5)) * 1e-12, 1 / 1250e6, places=15)
        self.assertAlmostEqual(float(m.group(4)) * 1e-12, p.clk_width_s, places=15)
        self.assertIn("pwl(0 0 5000p 0 6000p 1.98)", text)
        self.assertEqual(text.count("pulse("), 1)

    def test_netlist_shape_is_enforced(self):
        p = F.stimulus_for(SPEC, 25, 1000e6, 1.8)
        with self.assertRaises(F.FmaxError):
            F.patch_stimulus(NETLIST.replace("V2 CLK", "V2 CLKX"), p)
        with self.assertRaises(F.FmaxError):
            F.patch_stimulus(NETLIST + "V9 CLK GND pulse(0 1 0 1p 1p 1p 2p)\n", p)

    def test_impossible_period_rejected(self):
        with self.assertRaises(F.FmaxError):
            F.stimulus_for(SPEC, 4, 50e9, 1.8)

    def test_real_manifest_and_schematics_are_consistent(self):
        # Every modulus schematic exists, and the manifest is a valid spec.
        for m in SPEC.moduli:
            self.assertTrue((MANIFEST_PATH.parent / m.schematic).resolve().is_file(), m.schematic)
        g = F.grid(SPEC.search)
        self.assertEqual((g[0], g[-1]), (SPEC.search.f_min_hz, SPEC.search.f_max_hz))
        self.assertEqual(sorted({m.n for m in SPEC.moduli}), [4, 5, 25, 63, 64])

    def test_manifest_validation(self):
        bad = json.loads(json.dumps(MANIFEST))
        bad["search"]["resolution_hz"] = 70e6  # bounds not on the grid
        with self.assertRaises(F.FmaxError):
            F.FmaxSpec.from_manifest(bad)
        bad = json.loads(json.dumps(MANIFEST))
        del bad["criterion"]["tolerance_frac"]
        with self.assertRaises(F.FmaxError):
            F.FmaxSpec.from_manifest(bad)


class GridAndPlan(unittest.TestCase):
    def test_coarse_includes_top_and_refine_is_strictly_inside(self):
        self.assertEqual(F.coarse_indices(73, 8), [0, 8, 16, 24, 32, 40, 48, 56, 64, 72])
        self.assertEqual(F.coarse_indices(10, 4), [0, 4, 8, 9])
        obs = {0: F.PASS, 8: F.PASS, 16: F.FAIL, 24: F.FAIL}
        self.assertEqual(F.refine_indices(obs), list(range(9, 16)))

    def test_no_refinement_next_to_inconclusive_or_without_transition(self):
        self.assertEqual(F.refine_indices({0: F.PASS, 8: F.INCONCLUSIVE, 16: F.FAIL}), [])
        self.assertEqual(F.refine_indices({0: F.PASS, 8: F.PASS}), [])
        self.assertEqual(F.refine_indices({0: F.FAIL, 8: F.FAIL}), [])


class PerPeriodCriterion(unittest.TestCase):
    def setUp(self):
        self.plan = F.stimulus_for(SPEC, 25, 1100e6, 1.8)

    def test_clean_division_passes(self):
        v = judge(self.plan, output_edges(self.plan))
        self.assertEqual(v.status, F.PASS, v.reason)
        self.assertGreaterEqual(v.periods, SPEC.criterion.min_periods)

    def test_one_skipped_cycle_fails_even_though_the_average_is_close(self):
        # Drop one output edge inside the steady window: one period is 2x.
        edges = output_edges(self.plan)
        steady = [i + 1 for i, t in enumerate(edges) if t > self.plan.steady_from_s]
        v = judge(self.plan, output_edges(self.plan, skip_cycles={steady[3]}))
        self.assertEqual(v.status, F.FAIL)
        self.assertIn("period", v.reason)
        self.assertGreater(v.worst_dev_frac, 0.5)

    def test_wrong_ratio_fails(self):
        v = judge(self.plan, output_edges(self.plan, period_scale=1.2))
        self.assertEqual(v.status, F.FAIL)

    def test_short_glitch_period_fails(self):
        edges = output_edges(self.plan)
        mid = edges[len(edges) // 2]
        v = judge(self.plan, output_edges(self.plan, extra_edges=[mid + 0.4 * self.plan.expected_out_period_s]))
        self.assertEqual(v.status, F.FAIL)

    def test_missing_edges_is_a_measured_failure(self):
        v = judge(self.plan, [])
        self.assertEqual(v.status, F.FAIL)
        self.assertIn("missing output edges", v.reason)
        v = judge(self.plan, output_edges(self.plan)[:2])
        self.assertEqual(v.status, F.FAIL)

    def test_output_dying_mid_window_fails_as_silence(self):
        v = judge(self.plan, output_edges(self.plan, dead_after=self.plan.steady_from_s
                                          + 6.5 * self.plan.expected_out_period_s))
        self.assertEqual(v.status, F.FAIL)

    def test_truncated_trace_is_inconclusive_not_a_failure(self):
        t, vals = trace(self.plan, output_edges(self.plan))
        cut = [i for i, x in enumerate(t) if x < self.plan.tran_stop_s * 0.5]
        v = F.classify_waveform(t[: len(cut)], vals[: len(cut)], self.plan,
                                threshold_frac=0.5, hysteresis_frac=0.15)
        self.assertEqual(v.status, F.INCONCLUSIVE)
        self.assertEqual(F.classify_waveform([], [], self.plan, threshold_frac=0.5,
                                             hysteresis_frac=0.15).status, F.INCONCLUSIVE)


class BoundarySelection(unittest.TestCase):
    G = [800e6 + 25e6 * i for i in range(73)]

    def b(self, obs):
        return F.fmax_bracket(obs, self.G)

    def test_bracketed_reports_both_ends(self):
        obs = {i: F.PASS for i in (0, 8)} | {16: F.FAIL, 24: F.FAIL}
        obs |= {9: F.PASS, 10: F.PASS, 11: F.PASS, 12: F.FAIL, 13: F.FAIL, 14: F.FAIL, 15: F.FAIL}
        r = self.b(obs)
        self.assertEqual(r.status, F.BRACKETED)
        self.assertEqual((r.pass_hz, r.fail_hz), (self.G[11], self.G[12]))

    def test_censored_high_has_no_failing_end(self):
        r = self.b({0: F.PASS, 8: F.PASS, 72: F.PASS})
        self.assertEqual(r.status, F.CENSORED_HIGH)
        self.assertIsNone(r.fail_hz)

    def test_censored_low(self):
        r = self.b({0: F.FAIL, 8: F.FAIL, 72: F.FAIL})
        self.assertEqual(r.status, F.CENSORED_LOW)
        self.assertIsNone(r.pass_hz)

    def test_non_monotonic_is_flagged_with_the_lowest_bracket(self):
        r = self.b({0: F.PASS, 1: F.FAIL, 2: F.PASS, 3: F.FAIL})
        self.assertEqual(r.status, F.NON_MONOTONIC)
        self.assertEqual((r.pass_hz, r.fail_hz), (self.G[0], self.G[1]))
        self.assertEqual(r.non_monotonic_passes_hz, (self.G[2],))

    def test_inconclusive_probe_inside_the_bracket_prevents_a_bracket(self):
        r = self.b({0: F.PASS, 1: F.INCONCLUSIVE, 2: F.FAIL})
        self.assertEqual(r.status, F.CELL_INCONCLUSIVE)
        r = self.b({0: F.PASS, 8: F.INCONCLUSIVE, 16: F.FAIL})
        self.assertEqual(r.status, F.CELL_INCONCLUSIVE)

    def test_unrefined_gap_is_not_a_bracket(self):
        r = self.b({0: F.PASS, 8: F.FAIL})
        self.assertEqual(r.status, F.CELL_INCONCLUSIVE)
        self.assertIn("not adjacent", r.detail)

    def test_inconclusive_top_is_not_censored(self):
        self.assertEqual(self.b({0: F.PASS, 72: F.INCONCLUSIVE}).status, F.CELL_INCONCLUSIVE)
        self.assertEqual(self.b({}).status, F.CELL_INCONCLUSIVE)

    def test_fail_below_pass_only(self):
        r = self.b({0: F.INCONCLUSIVE, 1: F.FAIL, 5: F.PASS})
        self.assertEqual(r.status, F.CELL_INCONCLUSIVE)


# --------------------------------------------------------------------------- #
# the campaign driver against a fake backend
# --------------------------------------------------------------------------- #


class FakeBackend:
    """Stands in for an executor: 'simulates' by evaluating a model divider.

    `fmax_for(n, corner)` -> highest frequency the model divides correctly at;
    above it the model loses division (drops every other output edge).
    `errors` maps a frequency (Hz, +/-1 kHz) to "timeout"/"error"/"nodump".
    """

    name = "local"
    requested = "local"

    def __init__(self, fmax_for, errors=None):
        self.fmax_for, self.errors, self.executed = fmax_for, errors or {}, []

    def stage(self, units):
        return self

    def provenance(self):
        return None

    def execute(self, unit):
        self.executed.append(unit.corner_id)
        text = unit.netlist_text
        per = float(re.search(r"^V2 CLK GND pulse\(.* ([\d.]+)p\)", text, re.M).group(1)) * 1e-12
        freq = 1 / per
        n = int(re.match(r"n(\d+)_", unit.corner_id).group(1))
        corner = re.search(r"sky130\.lib\.spice (\w+)", text).group(1)
        plan = F.stimulus_for(SPEC, n, freq, 1.8)
        unit.work_dir.mkdir(parents=True, exist_ok=True)
        log = unit.log_path
        err = next((v for f, v in self.errors.items() if abs(f - freq) < 1e3), None)
        if err == "timeout":
            log.write_text("partial")
            return executor_mod.NgspiceOutcome(unit.corner_id, -1, "partial", log, unit.spice_path, timed_out=True)
        if err == "error":
            log.write_text("Error: timestep too small\n")
            return executor_mod.NgspiceOutcome(unit.corner_id, 1, "Error: timestep too small\n", log, unit.spice_path)
        good = freq <= self.fmax_for(n, corner)
        edges = output_edges(plan, skip_cycles=set() if good else set(range(1, 400, 2)))
        t, v = trace(plan, edges)
        if err != "nodump":
            name = f"{unit.corner_id}-point000.raw"
            (unit.work_dir / name).write_text("".join(f"{a:.6e} {b:.6e}\n" for a, b in zip(t, v)))
        out = f"ok\n{measure_mod.COMPLETION_MARKER}\n"
        log.write_text(out)
        return executor_mod.NgspiceOutcome(unit.corner_id, 0, out, log, unit.spice_path)


def make_cells(ns=(25,), corners=("tt",)):
    from harness.corners import PvtPoint

    mods = {m.n: m for m in SPEC.moduli}
    return [C.Cell(mods[n], PvtPoint(c, 27.0, 1.8)) for n in ns for c in corners]


def run(cells, backend):
    grid = F.grid(SPEC.search)
    with tempfile.TemporaryDirectory() as tmp:
        C.run_campaign(cells, grid, manifest=MANIFEST, spec=SPEC,
                       netlists={c.modulus.n: NETLIST for c in cells},
                       work_dir=Path(tmp), backend=backend, jobs=1, log=lambda *_: None)
    return grid, [F.fmax_bracket(c.observed, grid) for c in cells]


class CampaignWithFakeBackend(unittest.TestCase):
    def test_finds_the_modeled_boundary_as_an_adjacent_bracket(self):
        cells = make_cells(ns=(4, 25, 64), corners=("tt", "ss"))
        cap = {"tt": 1337e6, "ss": 1110e6}
        grid, res = run(cells, FakeBackend(lambda n, c: cap[c]))
        for cell, b in zip(cells, res):
            self.assertEqual(b.status, F.BRACKETED, b.detail)
            self.assertLessEqual(b.pass_hz, cap[cell.point.corner])
            self.assertGreater(b.fail_hz, cap[cell.point.corner])
            self.assertAlmostEqual(b.fail_hz - b.pass_hz, SPEC.search.resolution_hz)

    def test_probe_count_is_bounded_and_provenance_retained(self):
        cells = make_cells()
        backend = FakeBackend(lambda n, c: 1337e6)
        run(cells, backend)
        self.assertLessEqual(len(backend.executed), 10 + 7)
        for p in cells[0].probes:
            for key in ("freq_hz", "status", "reason", "netlist_sha256", "log_sha256",
                        "log_file", "expected_out_period_s", "clk_period_s", "stage"):
                self.assertIn(key, p)
            self.assertAlmostEqual(p["expected_out_period_s"], 25 * p["clk_period_s"], places=15)

    def test_boundary_above_the_range_is_censored_high(self):
        _, res = run(make_cells(), FakeBackend(lambda n, c: 9e9))
        self.assertEqual(res[0].status, F.CENSORED_HIGH)
        self.assertIsNone(res[0].fail_hz)

    def test_boundary_below_the_range_is_censored_low(self):
        _, res = run(make_cells(), FakeBackend(lambda n, c: 100e6))
        self.assertEqual(res[0].status, F.CENSORED_LOW)

    def test_simulator_errors_are_inconclusive_not_failures(self):
        grid = F.grid(SPEC.search)
        # Timeout at the coarse probe just above the boundary: no failure seen.
        for kind in ("timeout", "error", "nodump"):
            cells = make_cells()
            _, res = run(cells, FakeBackend(lambda n, c: 1337e6, errors={grid[24]: kind}))
            statuses = {p["freq_hz"]: p["status"] for p in cells[0].probes}
            self.assertEqual(statuses[grid[24]], F.INCONCLUSIVE, kind)
            self.assertEqual(res[0].status, F.CELL_INCONCLUSIVE, kind)
            self.assertFalse(res[0].resolved)

    def test_error_below_boundary_does_not_hide_a_resolvable_bracket_only_if_adjacent(self):
        grid = F.grid(SPEC.search)
        cells = make_cells()
        _, res = run(cells, FakeBackend(lambda n, c: 1337e6, errors={grid[8]: "error"}))
        # coarse probe 8 is far below the boundary; the 16->24 transition is
        # still bracketed even though 8 is inconclusive.
        self.assertEqual(res[0].status, F.BRACKETED, res[0].detail)

    def test_degraded_divider_is_detected_as_lost_division(self):
        healthy_cells, degraded_cells = make_cells(), make_cells()
        _, healthy = run(healthy_cells, FakeBackend(lambda n, c: 1500e6))
        _, degraded = run(degraded_cells, FakeBackend(lambda n, c: 1000e6))
        self.assertLess(degraded[0].pass_hz, healthy[0].pass_hz)
        failing = [p for p in degraded_cells[0].probes if p["status"] == F.FAIL]
        self.assertTrue(failing)
        self.assertTrue(all("period" in p["reason"] or "missing" in p["reason"] for p in failing))
        # The same probe frequency that passes on the healthy part fails here.
        f = healthy[0].pass_hz
        d = {p["freq_hz"]: p["status"] for p in degraded_cells[0].probes}
        h = {p["freq_hz"]: p["status"] for p in healthy_cells[0].probes}
        common = [x for x in d if x in h and h[x] == F.PASS and d[x] == F.FAIL]
        self.assertTrue(common or f > degraded[0].fail_hz)

    def test_degraded_input_detects_lost_division_at_a_known_good_frequency(self):
        # A probe the model divider handles cleanly, driven past its cap: the
        # per-period criterion must see the skipped cycles.
        cells = make_cells()
        run_cells = FakeBackend(lambda n, c: 1000e6)
        with tempfile.TemporaryDirectory() as tmp:
            unit, plan, mspec = C.build_probe_unit(MANIFEST, SPEC, cells[0], 1100e6, NETLIST, Path(tmp))
            outcome = run_cells.execute(unit)
            v = C.judge_probe(unit, outcome, plan, mspec, SPEC)
        self.assertEqual(v.status, F.FAIL)


class LocalGuards(unittest.TestCase):
    def test_remote_fallback_to_local_refused_for_a_grid(self):
        inner = SimpleNamespace(name="local", fallback_reason="no fleet", stage=lambda u: None)
        g = C._GuardedRemote(inner, max_local=1)
        with self.assertRaises(C._LocalFallbackRefused):
            g.stage([1, 2])
        self.assertIs(g.stage([1]), g)  # a single probe may run locally

    def test_dry_run_plans_without_a_pdk(self):
        rc = C.main(["divider-fmax", "--dry-run", "--moduli", "25", "--corners", "tt"])
        self.assertEqual(rc, 0)


class RecordRendering(unittest.TestCase):
    def test_record_table_round_trips_through_the_aggregator(self):
        sys.path.insert(0, str(SIM_DIR.parent / "measurements"))
        import aggregate  # noqa: E402

        grid = F.grid(SPEC.search)
        cells = []
        for n, obs in ((25, {0: F.PASS, 1: F.FAIL}), (64, {0: F.PASS, 72: F.PASS}), (4, {})):
            cells.append({"n": n, "corner": "tt", "temp_c": 27.0, "supply_v": 1.8,
                          "boundary": F.fmax_bracket(obs, grid)})
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "s.spice"
            snap.write_text("* x\n")
            pdk = SimpleNamespace(variant="sky130A", resolved_commit="abc", commit_mismatch=False,
                                  pinned_commit="abc", ngspice_lib="/x/sky130.lib.spice")
            text = fmax_report.render(
                record_id="20260101-000000-abcdef0", slug="divider-fmax", manifest=MANIFEST,
                spec=SPEC, pdk=pdk, tool_versions={}, repo_root=SIM_DIR.parent,
                netlist_snapshot=snap, cells=cells, probe_count=3, subset_reason="test",
                supersedes=None, execution_note=None)
        parsed = aggregate.parse_fmax_cells(text)
        self.assertEqual([(c.modulus, c.status) for c in parsed],
                         [(25, "BRACKETED"), (64, "CENSORED_HIGH"), (4, "INCONCLUSIVE")])
        self.assertEqual((parsed[0].pass_mhz, parsed[0].fail_mhz), (800.0, 825.0))
        self.assertIsNone(parsed[1].fail_mhz)
        self.assertIn("**Overall: FAIL**", text)  # an inconclusive cell fails the record
        self.assertIn("Spec row(s)**: 4 --", text)
        self.assertIn("stays DRAFT", text)


if __name__ == "__main__":
    unittest.main()
