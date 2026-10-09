#!/usr/bin/env python3
"""PDK-free tests for the `klt sim --backend batch` route of the Fmax campaign.

A fake `klt` runner reads the generated request and body netlist, "simulates"
a model divider and writes the report and waveform artifacts `klt sim` would
return, so the grouping, stimulus coupling, window cut, failure policy and
campaign reducer are exercised without a PDK, ngspice, AWS or a fleet.

    python3 -m unittest discover -s sim/tests -p 'test_fmax_klt.py' -v
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
sys.path.insert(0, str(SIM_DIR / "tests"))

from harness import fmax as F  # noqa: E402
from harness import fmax_cli as C  # noqa: E402
from harness import fmax_klt as K  # noqa: E402
from test_fmax import MANIFEST, SPEC, make_cells, output_edges, trace  # noqa: E402

NETLIST = """* fake testbench
**.subckt tb
XXXDIV VDD GND CLK RESETB VDD VDD GND GND GND GND FBCLK divider_intN
V1 VDD GND 1.8
V2 CLK GND pulse(0 1.8 0 12.5p 12.5p 442p 909p)
V3 RESETB GND pwl(0 0 5n 0 6n 1.8)
.lib /fake/sky130.lib.spice tt
.include /fake/cells.spice
.subckt divider_intN VDD GND CLK RESETB A B C D E F FBCLK
.ends
.GLOBAL GND
.end
"""


class FakeKlt:
    """A `subprocess.run` stand-in modelling `klt sim --backend batch`."""

    def __init__(self, fmax_for=lambda n, corner: 1337e6, mode=None):
        self.fmax_for, self.mode, self.calls = fmax_for, mode, []

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.calls.append(cmd)
        req_path = Path(cmd[2])
        outdir = Path(cmd[cmd.index("-o") + 1])
        req = json.loads(req_path.read_text())
        body = (req_path.parent / req["netlist"]).read_text()
        if self.mode == "version_refusal":
            msg = "the fleet runner runs klt 0.5.0 but the submitting client is 0.7.0"
            corners = [{"corner_id": "x", "process": p, "temperature_c": t, "status": "error",
                        "diagnostics": [{"code": "batch_job_failed", "message": msg}],
                        "artifacts": {}} for p in req["corners"]["process"]
                       for t in req["corners"]["temperature_c"]]
            return SimpleNamespace(returncode=4, stdout=json.dumps({"corners": corners}), stderr="")
        if self.mode == "no_json":
            return SimpleNamespace(returncode=1, stdout="", stderr="boom: no credentials")
        n = int(re.search(r"n(\d+)_", req_path.parent.name).group(1))
        duts = {}
        for m in re.finditer(r"^VCLK_(\d+) CLK_\d+ GND pulse\(.* ([\d.]+)p\)$", body, re.M):
            duts[int(m.group(1))] = 1 / (float(m.group(2)) * 1e-12)
        supply = float(re.search(r"^V1 VDD GND ([\d.]+)", body, re.M).group(1))
        excluded = {(e["process"], e["temperature_c"]) for e in req.get("exclude", [])}
        stop = float(re.search(r"([\d.]+)n$", req["analysis"]["args"]).group(1)) * 1e-9
        corners = []
        for p in req["corners"]["process"]:
            for t in req["corners"]["temperature_c"]:
                if (p, t) in excluded:
                    continue
                cdir = outdir / f"{p}_novdd_{t:g}C"
                cdir.mkdir(parents=True, exist_ok=True)
                (cdir / "ngspice.log").write_text(f"log {p} {t}\n")
                c = {"corner_id": f"{p}/novdd/{t:g}C", "process": p, "temperature_c": t,
                     "supply_v": {}, "status": "pass", "diagnostics": [], "measurements": [],
                     "artifacts": {"log": str(cdir / "ngspice.log"),
                                   "waveform": str(cdir / "waveform.raw.json")}}
                if self.mode == "corner_error" and p == "ss":
                    c["status"] = "error"
                    c["diagnostics"] = [{"code": "timeout", "message": "corner timed out"}]
                    c["artifacts"] = {}
                    corners.append(c)
                    continue
                cols = []
                for k in sorted(duts):
                    plan = F.stimulus_for(SPEC, n, duts[k], supply)
                    good = duts[k] <= self.fmax_for(n, p)
                    edges = output_edges(plan, skip_cycles=set() if good else set(range(1, 400, 2)))
                    # model trace on the group's common (longer) window
                    tt, vv = trace(plan, edges)
                    cols.append((tt, vv))
                grid_t = sorted({x for tt, _ in cols for x in tt} | {stop})

                def at(tt, vv, x):
                    if x >= tt[-1]:
                        return vv[-1]
                    import bisect
                    i = bisect.bisect_right(tt, x) - 1
                    if i < 0:
                        return vv[0]
                    t0, t1 = tt[i], tt[i + 1]
                    return vv[i] if t1 == t0 else vv[i] + (vv[i + 1] - vv[i]) * (x - t0) / (t1 - t0)

                pts = [[x] + [at(tt, vv, x) for tt, vv in cols] for x in grid_t]
                wave = {"variables": [{"index": 0, "name": "time", "type": "time"}] + [
                    {"index": i + 1, "name": f"v(fbclk_{k})", "type": "voltage"}
                    for i, k in enumerate(sorted(duts))], "points": pts}
                (cdir / "waveform.raw.json").write_text(json.dumps(wave))
                corners.append(c)
        report = {"status": "pass", "corners": corners, "environment": {
            "engine_version": "46", "remote": {
                "job_id": f"klt-sim-{len(self.calls):04d}", "instance_type": "m7i.4xlarge",
                "lifecycle": "spot", "runner_klt_version": "0.5.0",
                "client_klt_version": "0.7.0"}}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr="")


def backend_for(tmp, runner):
    return K.KltBatchBackend(spec=SPEC, manifest=MANIFEST, work_dir=Path(tmp), klt="klt",
                             runner=runner, log=lambda *_: None)


def run_campaign(cells, runner, tmp):
    grid = F.grid(SPEC.search)
    backend = backend_for(tmp, runner)
    backend.preflight = lambda: None
    C.run_campaign(cells, grid, manifest=MANIFEST, spec=SPEC,
                   netlists={c.modulus.n: NETLIST for c in cells}, work_dir=Path(tmp),
                   backend=backend, jobs=1, log=lambda *_: None)
    return grid, backend


class BodyConstruction(unittest.TestCase):
    def group(self, freqs, n=25, supply=1.8):
        g = K.Group(n=n, supply_v=supply)
        for k, f in enumerate(freqs):
            g.freqs[f] = k
        return g

    def test_one_dut_copy_per_frequency_with_coupled_stimulus(self):
        g = self.group([1000e6, 2000e6])
        body, plans = K.build_body(NETLIST, MANIFEST, SPEC, g)
        self.assertEqual(len(re.findall(r"^XXXDIV_\d", body, re.M)), 2)
        for k, f in enumerate([1000e6, 2000e6]):
            plan = F.stimulus_for(SPEC, 25, f, 1.8)
            self.assertIn(f"VCLK_{k} CLK_{k} GND {plan.clk_card}", body)
            self.assertIn(f"VRST_{k} RESETB_{k} GND {plan.reset_card}", body)
            self.assertIn(f"CLK_{k} RESETB_{k}", body)
            self.assertAlmostEqual(plans[f].expected_out_period_s, 25 / f, places=15)
        self.assertIn(".save v(fbclk_0) v(fbclk_1)", body)

    def test_klt_owned_cards_and_old_sources_are_removed(self):
        body, _ = K.build_body(NETLIST, MANIFEST, SPEC, self.group([1000e6]))
        self.assertNotIn(".lib", body)
        self.assertNotIn("\n.end\n", body)
        self.assertNotIn("V2 CLK", body)
        self.assertNotIn("V3 RESETB", body)
        self.assertIn(".include /fake/cells.spice", body)

    def test_supply_sets_rail_and_clock_high_level(self):
        body, _ = K.build_body(NETLIST, MANIFEST, SPEC, self.group([1000e6], supply=1.62))
        self.assertIn("V1 VDD GND 1.62", body)
        self.assertIn("pulse(0 1.62 ", body)
        self.assertIn("pwl(0 0 5000p 0 6000p 1.62)", body)

    def test_testbench_shape_is_enforced(self):
        with self.assertRaises(F.FmaxError):
            K.build_body(NETLIST.replace("XXXDIV", "RXXDIV"), MANIFEST, SPEC, self.group([1e9]))

    def test_request_excludes_unrequested_pairs(self):
        g = self.group([1000e6])
        g.processes, g.temps = ["tt", "ss"], [27.0, 125.0]
        g.needed = {("tt", 27.0), ("ss", 125.0)}
        req = K.build_request(SPEC, g, 1e-7, timeout_s=100, max_workers=2)
        self.assertEqual(req["backend"], "batch")
        self.assertEqual(len(req["exclude"]), 2)
        self.assertEqual(req["options"]["waveforms"], True)

    def test_clip_trace_interpolates_at_the_window_end(self):
        t, v = K.clip_trace([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 2.0, 3.0], 2.5)
        self.assertEqual(t[-1], 2.5)
        self.assertAlmostEqual(v[-1], 2.5)


class Chunking(unittest.TestCase):
    def test_frequencies_are_chunked_in_ascending_order(self):
        cells = make_cells(ns=(25,), corners=("tt",))
        grid = F.grid(SPEC.search)
        reqs = [(cells[0], i, grid[i]) for i in F.coarse_indices(len(grid), SPEC.search.coarse_stride)]
        with tempfile.TemporaryDirectory() as tmp:
            groups, index = backend_for(tmp, FakeKlt())._groups(reqs)
        self.assertEqual([len(g.freqs) for g in groups], [4, 4, 2])
        self.assertEqual(sorted(index), sorted((25, 1.8, grid[i]) for _, i, _ in reqs))
        lows = [min(g.freqs) for g in groups]
        self.assertEqual(lows, sorted(lows))


class CampaignViaFakeKlt(unittest.TestCase):
    def test_finds_the_modeled_boundary_as_an_adjacent_bracket(self):
        cells = make_cells(ns=(4, 25), corners=("tt", "ss"))
        cap = {"tt": 1337e6, "ss": 1110e6}
        with tempfile.TemporaryDirectory() as tmp:
            grid, backend = run_campaign(cells, FakeKlt(lambda n, c: cap[c]), tmp)
            res = [F.fmax_bracket(c.observed, grid) for c in cells]
            for cell, b in zip(cells, res):
                self.assertEqual(b.status, F.BRACKETED, b.detail)
                self.assertLessEqual(b.pass_hz, cap[cell.point.corner])
                self.assertGreater(b.fail_hz, cap[cell.point.corner])
            p = cells[0].probes[0]
            for key in ("batch_job_id", "batch_group", "netlist_sha256", "log_sha256", "log_file"):
                self.assertTrue(p[key], key)
            self.assertTrue((Path(tmp) / p["log_file"]).is_file())
            self.assertTrue(backend.jobs)

    def test_degraded_divider_is_detected_as_lost_division(self):
        cells = make_cells(ns=(25,), corners=("tt",))
        with tempfile.TemporaryDirectory() as tmp:
            grid, _ = run_campaign(cells, FakeKlt(lambda n, c: 0.0), tmp)
        self.assertEqual(F.fmax_bracket(cells[0].observed, grid).status, F.CENSORED_LOW)

    def test_one_failing_corner_is_inconclusive_not_a_measured_failure(self):
        cells = make_cells(ns=(25,), corners=("tt", "ss"))
        with tempfile.TemporaryDirectory() as tmp:
            grid, _ = run_campaign(cells, FakeKlt(mode="corner_error"), tmp)
        ss = next(c for c in cells if c.point.corner == "ss")
        self.assertTrue(all(s == F.INCONCLUSIVE for s in ss.observed.values()))
        self.assertTrue(all("simulator" in p["reason"] for p in ss.probes))
        tt = next(c for c in cells if c.point.corner == "tt")
        self.assertIn(F.PASS, tt.observed.values())

    def test_job_level_refusal_aborts_with_the_diagnostic_and_never_runs_locally(self):
        cells = make_cells(ns=(25,), corners=("tt",))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(K.KltBatchError) as cm:
                run_campaign(cells, FakeKlt(mode="version_refusal"), tmp)
        self.assertIn("fleet runner runs klt 0.5.0", str(cm.exception))

    def test_missing_report_aborts(self):
        cells = make_cells(ns=(25,), corners=("tt",))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(K.KltBatchError) as cm:
                run_campaign(cells, FakeKlt(mode="no_json"), tmp)
        self.assertIn("no credentials", str(cm.exception))

    def test_collected_reports_are_reused_on_rerun(self):
        cells = make_cells(ns=(25,), corners=("tt",))
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            fake = FakeKlt()
            b1 = K.KltBatchBackend(spec=SPEC, manifest=MANIFEST, work_dir=Path(tmp), cache_dir=cache,
                                   klt="klt", runner=fake, log=lambda *_: None)
            b1.preflight = lambda: None
            C.run_campaign(cells, F.grid(SPEC.search), manifest=MANIFEST, spec=SPEC,
                           netlists={25: NETLIST}, work_dir=Path(tmp), backend=b1, jobs=1,
                           log=lambda *_: None)
            first = len(fake.calls)
            cells2 = make_cells(ns=(25,), corners=("tt",))
            fake2 = FakeKlt()
            b2 = K.KltBatchBackend(spec=SPEC, manifest=MANIFEST, work_dir=Path(tmp), cache_dir=cache,
                                   klt="klt", runner=fake2, log=lambda *_: None)
            b2.preflight = lambda: None
            C.run_campaign(cells2, F.grid(SPEC.search), manifest=MANIFEST, spec=SPEC,
                           netlists={25: NETLIST}, work_dir=Path(tmp), backend=b2, jobs=1,
                           log=lambda *_: None)
        self.assertGreater(first, 0)
        self.assertEqual(fake2.calls, [])
        self.assertEqual(cells[0].observed, cells2[0].observed)


if __name__ == "__main__":
    unittest.main()
