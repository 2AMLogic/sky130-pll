#!/usr/bin/env python3
"""Unit tests for the degraded-DUT variant behind T1 item 6's negative control.

No PDK, ngspice or xschem required -- every check here is over committed text.

What these tests are for: `sim/pll-lock-mc-negative-control` is only a negative
control if it is **the same experiment** as `sim/pll-lock-mc` except for one
stated degradation, and its DUT is only that degradation if the variant
schematics are still the committed design files' own bodies. Both of those are
properties a careful edit can silently break months later, so they are asserted
here rather than described in a README:

1. Both generators' `--check` modes pass, i.e. every committed variant schematic
   still re-derives byte for byte from `design/loop-filter/loop_filter.sch`,
   `design/top/top.sch` and `sim/pll-lock-mc/testbench/tb_pll_lock_mc.sch`.
2. The control campaign's manifest agrees with the nominal campaign's on every
   field `yield_evidence.py` requires to agree -- read from that script's own
   list, so the two cannot drift apart.
3. The control campaign declares what it degrades, in the manifest that would
   netlist it, and the arm its testbench actually points at is the arm that
   declaration names.
4. The sizing unit carries a committed schematic for every arm its generator
   declares, so a declared-but-absent arm fails here.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIZING = REPO_ROOT / "sim" / "lf-c2-jitter-sensitivity"
CONTROL = REPO_ROOT / "sim" / "pll-lock-mc-negative-control"
NOMINAL_MANIFEST = REPO_ROOT / "sim" / "pll-lock-mc" / "testbench" / "tb.json"


def _load(name: str, path: Path):
    """Load a module from its path -- the slugs carry hyphens, so none of these
    directories is an importable package. Same pattern as
    `sim/tests/test_jitter_floor.py`."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


gen_c2_variant = _load(
    "gen_c2_variant", SIZING / "testbench" / "gen_c2_variant.py"
)
gen_tb = _load("gen_control_tb", CONTROL / "testbench" / "gen_tb.py")
yield_evidence = _load(
    "yield_evidence_for_control",
    REPO_ROOT / "sim" / "pll-lock-mc" / "analysis" / "yield_evidence.py",
)


class VariantsStillDeriveFromTheDesign(unittest.TestCase):
    def test_sizing_arms_match_the_committed_design_files(self):
        self.assertEqual(
            gen_c2_variant.main(["--check"]),
            0,
            "a committed sim/lf-c2-jitter-sensitivity arm no longer re-derives from "
            "design/loop-filter/loop_filter.sch + design/top/top.sch -- re-run the "
            "generator with --write and re-run the affected arm, rather than "
            "hand-editing the variant",
        )

    def test_control_testbench_matches_the_nominal_campaigns(self):
        self.assertEqual(
            gen_tb.main(["--check"]),
            0,
            "sim/pll-lock-mc-negative-control's testbench schematic is no longer "
            "sim/pll-lock-mc/testbench/tb_pll_lock_mc.sch's body with only the DUT "
            "substitution -- the control would no longer be the same experiment",
        )

    def test_every_declared_sizing_arm_has_a_committed_schematic(self):
        for factor in gen_c2_variant.FACTORS:
            with self.subTest(factor=factor):
                for name in gen_c2_variant._variant_files(factor):
                    self.assertTrue(
                        (SIZING / "testbench" / name).exists(),
                        f"arm {factor} declares {name}, which is not committed",
                    )

    def test_the_degraded_arm_changes_only_c2(self):
        # The one substitution, spelled out: C2's drawn geometry differs and no
        # other line of the loop filter does.
        nominal = (REPO_ROOT / "design/loop-filter/loop_filter.sch").read_text()
        variant = (SIZING / "testbench" / "loop_filter_c2div4.sch").read_text()
        body_of = lambda text: text.partition("}\nG {}\n")[2].splitlines()
        differing = [
            (a, b) for a, b in zip(body_of(nominal), body_of(variant)) if a != b
        ]
        self.assertEqual(len(body_of(nominal)), len(body_of(variant)))
        self.assertEqual(
            differing,
            [("W=72", "W=36"), ("L=72", "L=36")],
            "the degraded arm differs from design/loop-filter/loop_filter.sch in "
            "something other than C2's drawn geometry",
        )


class ControlIsTheSameExperiment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nominal_raw = json.loads(NOMINAL_MANIFEST.read_text())
        cls.control_raw = json.loads((CONTROL / "testbench" / "tb.json").read_text())
        cls.nominal = yield_evidence.parse_manifest(cls.nominal_raw)
        cls.control = yield_evidence.parse_control_manifest(cls.control_raw)

    def test_every_must_match_field_agrees_with_the_nominal_campaign(self):
        for field in yield_evidence._CONTROL_MUST_MATCH:
            with self.subTest(field=field):
                self.assertEqual(
                    self.control[field],
                    self.nominal[field],
                    f"the control campaign's {field} differs from the nominal "
                    "campaign's, so yield_evidence.py would refuse to grade it",
                )

    def test_control_declares_what_it_degrades_and_for_which_campaign(self):
        self.assertEqual(self.control["of"], "sim/pll-lock-mc")
        self.assertIn("C2", self.control["degradation"])

    def test_testbench_points_at_the_arm_the_degradation_names(self):
        # gen_tb.ARM is `top_c2div<F>`; the declared degradation has to name the
        # same factor, or the manifest describes a circuit the run would not use.
        factor = gen_tb.ARM.rsplit("c2div", 1)[1]
        side = gen_c2_variant.side_for(int(factor))
        self.assertIn(
            f"{side} um",
            self.control["degradation"],
            f"the control's DUT is arm {gen_tb.ARM} (C2 side {side} um), which the "
            "declared degradation string does not name",
        )
        self.assertIn(
            gen_tb.ARM,
            (CONTROL / "testbench" / gen_tb.OUT_NAME).read_text(),
            "the committed control testbench does not instantiate the declared arm",
        )

    def test_control_draws_enough_trials_for_the_detection_rule(self):
        # sim/pll-lock-mc/analysis/negative-control/reachability.md: against a
        # 5-of-5 nominal (Clopper-Pearson lower bound 0.478176), an all-failing
        # control separates at six draws (upper bound 0.459258) and not at five
        # (0.521824). Committed probes p4 and p7 are those two runs.
        self.assertGreaterEqual(
            self.control_raw["monte_carlo"]["trials"],
            6,
            "fewer than six control draws cannot be reported `detected` against "
            "the nominal campaign's current 5-of-5 population",
        )

    def test_control_gates_on_the_ratified_bound_exactly_as_the_campaign_does(self):
        self.assertEqual(
            self.control_raw["measure"]["jitter"],
            self.nominal_raw["measure"]["jitter"],
            "the control's jitter block differs from the campaign's -- including "
            "gate_on_bound, which is left true on purpose so a control draw that "
            "misses the bound is recorded as a per-trial FAIL by the harness "
            "itself rather than by a reading of the table",
        )

    def test_control_declares_no_spec_row(self):
        self.assertEqual(
            self.control_raw["spec_rows"],
            [],
            "a deliberately degraded variant must not claim a spec row",
        )


if __name__ == "__main__":
    unittest.main()
