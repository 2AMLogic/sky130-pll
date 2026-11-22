#!/usr/bin/env python3
"""Unit tests for sim/power/reduce.py (issue #233).

No PDK, ngspice or xschem required: every trace below is synthetic, built so
that the true mean supply current over a whole number of clock cycles is known
by construction.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.test_support import load_module  # noqa: E402

POWER_DIR = REPO_ROOT / "sim" / "power"

reduce_mod = load_module("power_reduce", POWER_DIR / "reduce.py")
sys.path.insert(0, str(POWER_DIR))
mint_mod = load_module("power_mint", POWER_DIR / "mint.py")
shard_mod = load_module("power_shard", POWER_DIR / "shard.py")
build_mod = load_module("power_build", POWER_DIR / "build.py")

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


class ShardTests(unittest.TestCase):
    def test_every_block_partitions_the_45_point_grid(self):
        for block in shard_mod.BLOCKS:
            full = json.loads((POWER_DIR / "testbench" / f"{block}.request.json").read_text())
            shards = shard_mod.shard_requests(block, full)
            pts = [shard_mod.grid_points(r) for r in shards]
            self.assertEqual(sum(len(p) for p in pts), 45, block)
            self.assertEqual(set().union(*pts), shard_mod.grid_points(full), block)
            self.assertEqual(len(shards), 15 if block == "divider-n64" else 5, block)
            self.assertLessEqual(max(len(p) for p in pts), 9, block)

    def test_serial_bound_fits_the_fleet_ceiling(self):
        for block in shard_mod.BLOCKS:
            full = json.loads((POWER_DIR / "testbench" / f"{block}.request.json").read_text())
            for r in shard_mod.shard_requests(block, full):
                n = len(shard_mod.grid_points(r))
                self.assertLessEqual(r["options"]["timeout_s"] * n + 120, 3600, block)
                self.assertGreaterEqual(r["options"]["timeout_s"], 370, block)

    def test_shard_leaves_the_rest_of_the_request_untouched(self):
        full = json.loads((POWER_DIR / "testbench" / "pfd-cp.request.json").read_text())
        for r in shard_mod.shard_requests("pfd-cp", full):
            self.assertEqual({k: v for k, v in r.items() if k not in ("corners", "options")},
                             {k: v for k, v in full.items() if k not in ("corners", "options")})
            self.assertEqual({k: v for k, v in r["options"].items() if k != "timeout_s"},
                             {k: v for k, v in full["options"].items() if k != "timeout_s"})


class MergeShardReportsTests(unittest.TestCase):
    def _corner(self, proc):
        return {"corner_id": f"{proc}/1.800V/27C", "process": proc,
                "supply_v": {"v1": 1.8}, "temperature_c": 27, "status": "pass"}

    def _write(self, d, name, procs, status="pass"):
        (d / name).write_text(json.dumps({
            "status": status, "corner_count": len(procs),
            "corners": [self._corner(p) for p in procs],
            "environment": {"remote": {"job_id": f"job-{name}"}},
            "provenance": {"klt_version": "0.7.1"},
        }))

    def test_merges_shards_in_order_and_keeps_every_job(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._write(d, "vco.shard00.report.json", ["tt"])
            self._write(d, "vco.shard01.report.json", ["ff"], status="fail")
            rep, files = mint_mod.load_block_reports(d, "vco")
            self.assertEqual([c["process"] for c in rep["corners"]], ["tt", "ff"])
            self.assertEqual(rep["corner_count"], 2)
            self.assertEqual(rep["status"], "fail")
            self.assertEqual(len(rep["environment"]["remote_jobs"]), 2)
            self.assertEqual(len(files), 2)

    def test_duplicate_point_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._write(d, "vco.shard00.report.json", ["tt"])
            self._write(d, "vco.shard01.report.json", ["tt"])
            with self.assertRaises(SystemExit):
                mint_mod.load_block_reports(d, "vco")

    def test_single_report_and_missing_report(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            with self.assertRaises(SystemExit):
                mint_mod.load_block_reports(d, "vco")
            self._write(d, "vco.report.json", ["tt"])
            rep, files = mint_mod.load_block_reports(d, "vco")
            self.assertEqual(files, [d / "vco.report.json"])
            self._write(d, "vco.shard00.report.json", ["ff"])
            with self.assertRaises(SystemExit):
                mint_mod.load_block_reports(d, "vco")


class ToBodyTests(unittest.TestCase):
    """build.to_body: xschem netlist text -> `klt sim` circuit body."""

    def test_strips_klt_netlist_inputs_line(self):
        # Newer `klt netlist` prepends this provenance header; the committed
        # bodies must not carry it (issue #565).
        text = (
            '** klt-netlist-inputs: {"pdk_variant": null, "xschem_version": "3.4.7"}\n'
            "** sch_path: /machine/local/tb_power_vco.sch\n"
            "** sym_path: /machine/local/vco_ring5.sym\n"
            "X1 VDD GND VCTRL CLK vco_ring5\n"
            ".end\n"
        )
        body = build_mod.to_body(text)
        self.assertNotIn("klt-netlist-inputs", body)
        self.assertNotIn("/machine/local", body)
        self.assertIn("** sch_path: (machine-local path elided)", body)
        self.assertIn("** sym_path: (machine-local path elided)", body)
        self.assertIn("X1 VDD GND VCTRL CLK vco_ring5", body)
        self.assertNotRegex(body, r"(?m)^\.end$")

    def test_input_without_klt_header_is_byte_stable(self):
        # klayout-tools==0.8.0 emits no `** klt-netlist-inputs:` line; its
        # committed bodies must survive the strip unchanged.
        text = "** sch_path: /machine/local/tb.sch\nR1 a b 1k\n.end\n"
        self.assertEqual(
            build_mod.to_body(text),
            "** sch_path: (machine-local path elided)\nR1 a b 1k\n",
        )

    def test_rejects_lib_and_control_cards(self):
        for bad in (".lib /pdk/sky130.lib.spice tt\n.end\n",
                    ".control\n.endc\n.end\n"):
            with self.assertRaises(SystemExit):
                build_mod.to_body(bad)

    def test_rewrites_machine_local_pdk_root(self):
        text = ".include /home/me/pdks/sky130A/libs.ref/sky130_fd_pr/pfet.spice\n.end\n"
        body = build_mod.to_body(text)
        self.assertIn(
            ".include $PDK_ROOT/sky130A/libs.ref/sky130_fd_pr/pfet.spice\n", body
        )


def _test_block() -> dict:
    """Minimal block dict exercising every key build_block consumes."""
    return {
        "sources": [("v", "V2", "VCTRL", "pwl(0 0)")],
        "name": "vco",
        "dut": "design/vco/vco_ring5.sym",
        "dut_name": "XXVCO",
        "pins": {"VDD": "VDD", "GND": "GND", "VCTRL": "VCTRL", "CLK": "CLK"},
        "code": "", "stdcells": False,
        "align_node": "v(clk)", "save": ["v(clk)", "i(v1)"],
        "tran_step": "50p", "tran_stop": "1u", "uic": True,
        "stages": [{"id": "idle", "kind": "idle", "label": "idle",
                    "t0": 0.0, "t1": 100e-9, "settle": 60e-9}],
        "title": "unit-test block", "timeout_s": 60, "note": "unit-test note",
    }


class BuildBlockTests(unittest.TestCase):
    """build.build_block delegates netlisting to runner.netlist_schematic."""

    def test_delegates_to_runner_netlist_schematic(self):
        seen = {}
        netlist_text = (
            '** klt-netlist-inputs: {"xschem_version": "9.9"}\n'
            "** sch_path: /machine/local/tb_power_vco.sch\n"
            "X1 VDD GND VCTRL CLK vco_ring5\n"
            ".end\n"
        )

        def fake(pdk, xschemrc, schematic, out_dir, repo_root):
            seen.update(pdk=pdk, xschemrc=xschemrc, schematic=schematic,
                        out_dir=out_dir, repo_root=repo_root,
                        sch_text=schematic.read_text())
            return netlist_text

        with mock.patch.object(build_mod.runner_mod, "netlist_schematic", fake):
            out = build_mod.build_block(_test_block(), pdk="pdk-sentinel")
        self.assertIs(seen["pdk"], "pdk-sentinel")
        self.assertEqual(seen["xschemrc"], build_mod.REPO_ROOT / "sim" / "xschemrc")
        self.assertEqual(seen["schematic"].name, "tb_power_vco.sch")
        self.assertEqual(seen["sch_text"], out["tb_power_vco.sch"])
        self.assertEqual(seen["out_dir"], seen["schematic"].parent)
        self.assertEqual(seen["repo_root"], build_mod.REPO_ROOT)
        body = out["vco.body.spice"]
        self.assertNotIn("klt-netlist-inputs", body)
        self.assertNotRegex(body, r"(?m)^\.end$")
        self.assertTrue(body.endswith("\n.save v(clk) i(v1)\n"))
        stages = json.loads(out["vco.stages.json"])
        self.assertEqual(stages["block"], "vco")
        req = json.loads(out["vco.request.json"])
        self.assertEqual(req["netlist"], "vco.body.spice")
        self.assertEqual(req["analysis"]["args"], "50p 1u uic")

    def test_netlist_error_becomes_system_exit(self):
        def boom(*args, **kwargs):
            raise build_mod.runner_mod.NetlistError("klt netlist failed (exit 1)")

        with mock.patch.object(build_mod.runner_mod, "netlist_schematic", boom):
            with self.assertRaises(SystemExit):
                build_mod.build_block(_test_block(), pdk=object())


class BuildSourceTests(unittest.TestCase):
    """Host rule: netlisting goes through `klt netlist`, never raw xschem."""

    def test_no_raw_xschem_invocation(self):
        src = (POWER_DIR / "build.py").read_text()
        self.assertIsNone(re.search(r'["\']xschem["\']', src))
        self.assertNotIn("netlist_with_xschem", src)


if __name__ == "__main__":
    unittest.main()
