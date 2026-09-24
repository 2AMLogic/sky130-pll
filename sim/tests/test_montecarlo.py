#!/usr/bin/env python3
"""Unit tests for sim/harness's Monte Carlo trial generation and netlist
patching (issue #20). No PDK and no ngspice/xschem required -- mirrors
sim/tests/test_harness.py's coverage of the PVT corner matrix
(sim/harness/corners.py) for the Monte Carlo analogue
(sim/harness/montecarlo.py).

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import executor as executor_mod  # noqa: E402
from harness import measure as measure_mod  # noqa: E402
from harness import montecarlo as mc  # noqa: E402
from harness import runner  # noqa: E402


class McTrialTests(unittest.TestCase):
    def test_lib_corner_appends_mm_suffix_when_mismatch_enabled(self):
        t = mc.McTrial(
            trial=1, seed=1, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=True, process=True
        )
        self.assertEqual(t.lib_corner, "tt_mm")

    def test_lib_corner_is_plain_corner_when_mismatch_disabled(self):
        t = mc.McTrial(
            trial=1, seed=1, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=False, process=True
        )
        self.assertEqual(t.lib_corner, "tt")

    def test_corner_id_format(self):
        t = mc.McTrial(
            trial=3, seed=5, corner="ss", temp_c=-40.0, supply_v=1.62, mismatch=True, process=False
        )
        self.assertEqual(t.corner_id, "mc003_seed5_ss_mm_-40c_1.62v")

    def test_corner_id_zero_pads_trial_index(self):
        t = mc.McTrial(
            trial=1, seed=1, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=False, process=True
        )
        self.assertTrue(t.corner_id.startswith("mc001_"))


class BuildTrialsTests(unittest.TestCase):
    MANIFEST = {
        "monte_carlo": {
            "corner": "tt",
            "temp_c": 27,
            "supply_v": 1.8,
            "mismatch": True,
            "process": True,
            "trials": 5,
            "seed_base": 1,
        }
    }
    VALID_CORNERS = ("tt", "ss", "ff", "sf", "fs", "ll", "hh")

    def test_default_config_produces_the_manifest_trial_count(self):
        trials = mc.build_trials(self.MANIFEST, self.VALID_CORNERS)
        self.assertEqual(len(trials), 5)

    def test_trial_indices_and_seeds_are_sequential_from_seed_base(self):
        trials = mc.build_trials(self.MANIFEST, self.VALID_CORNERS)
        self.assertEqual([t.trial for t in trials], [1, 2, 3, 4, 5])
        self.assertEqual([t.seed for t in trials], [1, 2, 3, 4, 5])

    def test_seed_base_override_shifts_every_seed(self):
        trials = mc.build_trials(self.MANIFEST, self.VALID_CORNERS, seed_base_override=100)
        self.assertEqual([t.seed for t in trials], [100, 101, 102, 103, 104])

    def test_missing_monte_carlo_block_is_a_config_error(self):
        with self.assertRaises(mc.McConfigError):
            mc.build_trials({}, self.VALID_CORNERS)

    def test_unknown_corner_from_pdk_json_rejected(self):
        with self.assertRaises(mc.McConfigError):
            mc.build_trials(self.MANIFEST, self.VALID_CORNERS, corner_override="bogus")

    def test_corner_override_may_pick_any_pdk_valid_corner(self):
        trials = mc.build_trials(self.MANIFEST, self.VALID_CORNERS, corner_override="sf")
        self.assertTrue(all(t.corner == "sf" for t in trials))

    def test_trials_override_narrows_the_count(self):
        trials = mc.build_trials(self.MANIFEST, self.VALID_CORNERS, trials_override=2)
        self.assertEqual(len(trials), 2)

    def test_zero_trials_is_a_config_error(self):
        with self.assertRaises(mc.McConfigError):
            mc.build_trials(self.MANIFEST, self.VALID_CORNERS, trials_override=0)

    def test_both_switches_off_is_a_config_error(self):
        # With neither MC_MM_SWITCH nor MC_PR_SWITCH enabled, trials would
        # only differ by an RNG seed nothing in the netlist reads -- not a
        # Monte Carlo campaign, just N repeats of one PVT point.
        with self.assertRaises(mc.McConfigError):
            mc.build_trials(
                self.MANIFEST,
                self.VALID_CORNERS,
                mismatch_override=False,
                process_override=False,
            )

    def test_process_only_campaign_is_allowed(self):
        trials = mc.build_trials(
            self.MANIFEST, self.VALID_CORNERS, mismatch_override=False, process_override=True
        )
        self.assertFalse(trials[0].mismatch)
        self.assertEqual(trials[0].lib_corner, "tt")

    def test_temp_and_supply_overrides_apply_to_every_trial(self):
        trials = mc.build_trials(
            self.MANIFEST, self.VALID_CORNERS, temp_override=125.0, supply_override=1.98
        )
        self.assertTrue(all(t.temp_c == 125.0 and t.supply_v == 1.98 for t in trials))


class PatchNetlistMcTests(unittest.TestCase):
    MANIFEST = {
        "corner_pattern": r"(\.lib\s+\S*sky130\.lib\.spice\s+)(\w+)",
        "supply_pattern": r"(V1 GND net1 )([0-9.]+)",
    }
    NETLIST = (
        "**.subckt smoke_test\n"
        "V1 GND net1 1.8\n"
        "XR1 net1 net2 sky130_fd_pr__res_generic_po W=1 L=1 m=1\n"
        "**** begin user architecture code\n\n"
        ".lib /some/path/sky130.lib.spice tt\n"
        ".op\n\n"
        "**** end user architecture code\n"
        "**.ends\n"
        ".GLOBAL GND\n"
        ".end\n"
    )

    def test_mismatch_trial_selects_the_mm_lib_section(self):
        trial = mc.McTrial(
            trial=1, seed=7, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=True, process=True
        )
        patched = runner.patch_netlist_mc(self.NETLIST, self.MANIFEST, trial)
        self.assertIn(".lib /some/path/sky130.lib.spice tt_mm", patched)

    def test_process_only_trial_keeps_the_plain_lib_section(self):
        trial = mc.McTrial(
            trial=1, seed=7, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=False, process=True
        )
        patched = runner.patch_netlist_mc(self.NETLIST, self.MANIFEST, trial)
        self.assertIn(".lib /some/path/sky130.lib.spice tt\n", patched)
        self.assertNotIn("tt_mm", patched)

    def test_injects_switch_params_and_seed_and_temp(self):
        trial = mc.McTrial(
            trial=1, seed=42, corner="ss", temp_c=-40.0, supply_v=1.62, mismatch=True, process=False
        )
        patched = runner.patch_netlist_mc(self.NETLIST, self.MANIFEST, trial)
        self.assertIn(".param MC_MM_SWITCH=1", patched)
        self.assertIn(".param MC_PR_SWITCH=0", patched)
        self.assertIn(".options seed=42", patched)
        self.assertIn(".temp -40\n.end", patched)
        self.assertIn("V1 GND net1 1.62", patched)

    def test_does_not_corrupt_the_ends_terminator(self):
        trial = mc.McTrial(
            trial=1, seed=1, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=True, process=True
        )
        patched = runner.patch_netlist_mc(self.NETLIST, self.MANIFEST, trial)
        self.assertIn("**.ends\n", patched)
        self.assertEqual(patched.count(".temp"), 1)

    def test_missing_corner_pattern_raises(self):
        trial = mc.McTrial(
            trial=1, seed=1, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=True, process=True
        )
        with self.assertRaises(runner.NetlistError):
            runner.patch_netlist_mc("no corner line here\n.end\n", self.MANIFEST, trial)


class PatchNetlistMcWithMeasureSpecTests(unittest.TestCase):
    """`patch_netlist_mc`'s optional `spec`/`prefix` (issue #20's second
    acceptance-criteria bullet): a Monte Carlo trial of a manifest that also
    declares `measure` (e.g. `sim/pll-lock`'s `measure.lock`/`measure.jitter`)
    must inject the same manifest-owned `.control` block a PVT point's
    `measure` block does -- otherwise a lock-capable DUT whose schematic
    carries no `.tran` card of its own (this repo's own convention, see
    `sim/harness/measure.py`'s module docstring) would run no analysis at
    all under `--mc`.
    """

    MANIFEST = {
        "corner_pattern": r"(\.lib\s+\S*sky130\.lib\.spice\s+)(\w+)",
        "supply_pattern": r"(V1 GND net1 )([0-9.]+)",
        "measure": {
            "node": "CLK",
            "tran_step": "1n",
            "tran_stop": "100n",
            "jitter": {"max_frac": 0.05},
        },
    }
    NETLIST = (
        "**.subckt smoke_test\n"
        "V1 GND net1 1.8\n"
        ".lib /some/path/sky130.lib.spice tt\n"
        "**.ends\n"
        ".end\n"
    )

    def test_no_spec_leaves_todays_mc_only_cards(self):
        trial = mc.McTrial(
            trial=1, seed=1, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=True, process=True
        )
        patched = runner.patch_netlist_mc(self.NETLIST, self.MANIFEST, trial)
        self.assertNotIn(".control", patched)
        self.assertNotIn("tran ", patched)

    def test_a_spec_appends_the_manifest_owned_control_block(self):
        trial = mc.McTrial(
            trial=1, seed=1, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=True, process=True
        )
        spec = measure_mod.MeasureSpec.from_manifest(self.MANIFEST)
        patched = runner.patch_netlist_mc(
            self.NETLIST, self.MANIFEST, trial, spec=spec, prefix=f"{trial.corner_id}-"
        )
        self.assertIn(".control", patched)
        self.assertIn("tran 1n 100n", patched)
        self.assertIn(f"wrdata {trial.corner_id}-point000.raw v(CLK)", patched)
        self.assertIn(measure_mod.COMPLETION_MARKER, patched)
        # The MC sampling cards still come first, ahead of the injected
        # analysis -- both are inserted before the same `.end`, in one
        # `_END_CARD_RE.sub` call, so their relative order is exactly the
        # order they are concatenated in `patch_netlist_mc`.
        self.assertLess(
            patched.index(".param MC_MM_SWITCH"), patched.index(".control")
        )

    def test_control_block_comes_before_end(self):
        trial = mc.McTrial(
            trial=2, seed=9, corner="ss", temp_c=-40.0, supply_v=1.62, mismatch=False, process=True
        )
        spec = measure_mod.MeasureSpec.from_manifest(self.MANIFEST)
        patched = runner.patch_netlist_mc(
            self.NETLIST, self.MANIFEST, trial, spec=spec, prefix=f"{trial.corner_id}-"
        )
        self.assertLess(patched.index(".endc"), patched.rindex(".end"))


def _square_wave_dump(period_s: float, n_cycles: int, dt_s: float, vdd: float) -> str:
    """A `wrdata`-shaped ASCII dump of a perfectly periodic square wave --
    exactly the shape `measure.parse_wrdata` reads. Indexed in integer grid
    steps (not a repeatedly-accumulated float `t`, and not a float `%`) so
    every rising edge lands at exactly the same step offset each cycle with
    no floating-point drift -- a deterministic wiring check, not a re-test of
    `measure.py`'s own arithmetic (already exhaustively covered by
    `sim/tests/test_measure.py`'s `PeriodJitterTests`).
    """
    period_steps = round(period_s / dt_s)
    half_steps = period_steps // 2
    n_steps = n_cycles * period_steps
    lines = []
    for i in range(n_steps + 1):
        v = vdd if (i % period_steps) < half_steps else 0.0
        lines.append(f"{i * dt_s:.12g} {v:.12g}")
    return "\n".join(lines) + "\n"


class RunMcTrialMeasurementTests(unittest.TestCase):
    """`run_mc_trial` reduces a passing trial's waveform dump exactly as
    `run_point` reduces a PVT point's, once the manifest declares `measure`
    -- the wiring issue #20's second acceptance-criteria bullet needs to run
    a real jitter-bearing Monte Carlo campaign at all. No PDK/ngspice: the
    ngspice invocation is stubbed via `execute=`, the same executor seam
    `sim/tests/test_execution.py` uses.
    """

    MANIFEST = {
        "corner_pattern": r"(\.lib\s+\S*sky130\.lib\.spice\s+)(\w+)",
        "supply_pattern": r"(V1 VDD GND )([0-9.]+)",
        "measure": {
            "node": "CLK",
            "tran_step": "0.5n",
            "tran_stop": "50n",
            "min_edges": 4,
            "jitter": {"max_frac": 0.5, "min_cycles": 2},
        },
        "monte_carlo": {
            "corner": "tt",
            "temp_c": 27,
            "supply_v": 1.8,
            "mismatch": True,
            "process": True,
            "trials": 1,
        },
    }
    NETLIST = (
        "**.subckt tb_fake\n"
        "V1 VDD GND 1.8\n"
        ".lib /fake/sky130.lib.spice tt\n"
        "**.ends\n"
        ".end\n"
    )

    def _fake_execute(self, dump_text: str):
        def execute(unit: executor_mod.NgspiceUnit) -> executor_mod.NgspiceOutcome:
            names = measure_mod.waveform_names(
                measure_mod.MeasureSpec.from_manifest(self.MANIFEST), f"{unit.corner_id}-"
            )
            (unit.work_dir / names[0]).write_text(dump_text)
            return executor_mod.NgspiceOutcome(
                corner_id=unit.corner_id,
                returncode=0,
                log_text=f"{unit.completion_marker}\n",
                log_path=unit.work_dir / f"{unit.corner_id}.log",
                spice_path=unit.work_dir / f"{unit.corner_id}.spice",
            )

        return execute

    def test_a_passing_trial_is_reduced_to_a_measurement(self):
        trial = mc.McTrial(
            trial=1, seed=7, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=True, process=True
        )
        dump = _square_wave_dump(period_s=10e-9, n_cycles=5, dt_s=0.5e-9, vdd=1.8)
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.run_mc_trial(
                pdk=None,
                spiceinit=None,
                manifest=self.MANIFEST,
                netlist_text=self.NETLIST,
                trial=trial,
                work_dir=Path(tmp),
                execute=self._fake_execute(dump),
            )
        self.assertTrue(result.passed, result.reason)
        self.assertEqual(len(result.measurements), 1)
        m = result.measurements[0]
        self.assertTrue(m.oscillating)
        self.assertIsNotNone(m.period_jitter_frac)
        self.assertAlmostEqual(m.period_jitter_frac, 0.0, places=6)
        self.assertIn("period jitter", result.reason)

    def test_a_missing_dump_fails_the_trial_not_just_the_plumbing_check(self):
        """`_run_ngspice_and_judge` passes (the stub reports success), but no
        dump is written -- the reduction step must still fail the trial
        rather than reporting a bare harness-plumbing PASS with no evidence
        behind it (`_reduce_measurements`'s own contract, shared with
        `run_point`)."""

        def execute(unit: executor_mod.NgspiceUnit) -> executor_mod.NgspiceOutcome:
            return executor_mod.NgspiceOutcome(
                corner_id=unit.corner_id,
                returncode=0,
                log_text=f"{unit.completion_marker}\n",
                log_path=unit.work_dir / f"{unit.corner_id}.log",
                spice_path=unit.work_dir / f"{unit.corner_id}.spice",
            )

        trial = mc.McTrial(
            trial=1, seed=1, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=True, process=True
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.run_mc_trial(
                pdk=None,
                spiceinit=None,
                manifest=self.MANIFEST,
                netlist_text=self.NETLIST,
                trial=trial,
                work_dir=Path(tmp),
                execute=execute,
            )
        self.assertFalse(result.passed)
        self.assertIn("no waveform dump", result.reason)

    def test_a_manifest_with_no_measure_block_is_unaffected(self):
        """`sim/pdk-smoke`'s shape: no `measure` block at all -- the trial
        stays the plumbing-only check it always was, with no measurements."""
        manifest = {
            "corner_pattern": self.MANIFEST["corner_pattern"],
            "supply_pattern": self.MANIFEST["supply_pattern"],
            "monte_carlo": self.MANIFEST["monte_carlo"],
        }

        def execute(unit: executor_mod.NgspiceUnit) -> executor_mod.NgspiceOutcome:
            self.assertEqual(unit.completion_marker, runner.COMPLETION_MARKER)
            return executor_mod.NgspiceOutcome(
                corner_id=unit.corner_id,
                returncode=0,
                log_text=f"{unit.completion_marker}\n",
                log_path=unit.work_dir / f"{unit.corner_id}.log",
                spice_path=unit.work_dir / f"{unit.corner_id}.spice",
            )

        trial = mc.McTrial(
            trial=1, seed=1, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=True, process=True
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.run_mc_trial(
                pdk=None,
                spiceinit=None,
                manifest=manifest,
                netlist_text=self.NETLIST,
                trial=trial,
                work_dir=Path(tmp),
                execute=execute,
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.measurements, ())


if __name__ == "__main__":
    unittest.main()
