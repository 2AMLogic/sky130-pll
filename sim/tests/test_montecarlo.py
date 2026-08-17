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
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

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


if __name__ == "__main__":
    unittest.main()
