#!/usr/bin/env python3
"""PDK-free tests for the prepared N=20 / 500 MHz Stage A Fmax configuration
(issue #352).

No PDK, ngspice, xschem or `klt`: the schematic is parsed as text, waveforms are
synthesized from a model divider, and the campaign runs against test_fmax's fake
backend. Nothing here executes a simulation.

    python3 -m unittest discover -s sim/tests -p 'test_fmax_stage_a.py' -v
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
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
from harness import fmax_report  # noqa: E402
from test_fmax import MANIFEST as BASE_MANIFEST  # noqa: E402
from test_fmax import NETLIST, FakeBackend, judge, output_edges, trace  # noqa: E402

STAGE_A_PATH = SIM_DIR / "divider-fmax" / "testbench" / "fmax-stage-a-500mhz.json"
MANIFEST = json.loads(STAGE_A_PATH.read_text())
SPEC = F.FmaxSpec.from_manifest(MANIFEST)
BASE_SPEC = F.FmaxSpec.from_manifest(BASE_MANIFEST)
F500 = 500e6


def nsel_modulus(sch_text: str) -> int:
    """N a testbench schematic straps: NSEL[5:0] carries N-1 in plain binary
    (design/divider/DESIGN.md). The lab_pins p5..p10 sit on the symbol's
    NSEL0..NSEL5 pins in y order; each ties to VDD (1) or GND (0)."""
    bits = {}
    for m in re.finditer(r"name=p(\d+) sig_type=std_logic lab=(VDD|GND)\}", sch_text):
        idx = int(m.group(1)) - 5
        if 0 <= idx <= 5:
            bits[idx] = 1 if m.group(2) == "VDD" else 0
    assert sorted(bits) == list(range(6)), bits
    return sum(b << i for i, b in bits.items()) + 1


def sch(slug: str, name: str) -> str:
    return (SIM_DIR / slug / "testbench" / name).read_text()


def run_stage_a(spec, backend, corners=("tt",)):
    from harness.corners import PvtPoint

    cells = [C.Cell(spec.moduli[0], PvtPoint(c, 27.0, 1.8)) for c in corners]
    grid = F.grid(spec.search)
    with tempfile.TemporaryDirectory() as tmp:
        C.run_campaign(cells, grid, manifest=MANIFEST, spec=spec,
                       netlists={20: NETLIST}, work_dir=Path(tmp), backend=backend,
                       jobs=1, log=lambda *_: None)
    return grid, cells


class StaticNselEncoding(unittest.TestCase):
    def test_parser_reproduces_every_existing_bench(self):
        # Validates the independent decode against benches whose modulus is
        # known from their records, so a parser bug cannot bless a wrong strap.
        for slug, n in (("divider-n4", 4), ("divider-n5", 5), ("divider-n63", 63),
                        ("divider-n64", 64)):
            with self.subTest(slug=slug):
                self.assertEqual(nsel_modulus(sch(slug, f"tb_divider_n{n}.sch")), n)

    def test_n20_bench_straps_n_minus_1_equals_19(self):
        text = sch("divider-n20", "tb_divider_n20.sch")
        self.assertEqual(nsel_modulus(text), 20)
        pins = dict(re.findall(r"name=p(\d+) sig_type=std_logic lab=(VDD|GND)\}", text))
        self.assertEqual("".join("1" if pins[str(p)] == "VDD" else "0" for p in range(10, 4, -1)),
                         "010011")  # NSEL5..NSEL0

    def test_negative_control_neighbouring_straps_are_not_n20(self):
        text = sch("divider-n20", "tb_divider_n20.sch")
        # 010100 (= 20 as NSEL, i.e. N=21) is the tempting wrong answer.
        wrong = text.replace("name=p5 sig_type=std_logic lab=VDD", "name=p5 sig_type=std_logic lab=GND") \
                    .replace("name=p6 sig_type=std_logic lab=VDD", "name=p6 sig_type=std_logic lab=GND") \
                    .replace("name=p7 sig_type=std_logic lab=GND", "name=p7 sig_type=std_logic lab=VDD")
        self.assertNotEqual(nsel_modulus(wrong), 20)
        self.assertEqual(nsel_modulus(wrong), 21)

    def test_bench_manifest_and_stage_a_manifest_agree_on_the_modulus(self):
        tb = json.loads((SIM_DIR / "divider-n20" / "testbench" / "tb.json").read_text())
        self.assertIn("N=20", tb["claim"])
        self.assertEqual(tb["measure"]["lock"]["target_hz"], 250e6 / 20)
        self.assertEqual([m.n for m in SPEC.moduli], [20])
        sch_path = (STAGE_A_PATH.parent / SPEC.moduli[0].schematic).resolve()
        self.assertEqual(sch_path, SIM_DIR / "divider-n20" / "testbench" / "tb_divider_n20.sch")
        self.assertEqual(nsel_modulus(sch_path.read_text()), SPEC.moduli[0].n)

    def test_bench_window_fits_the_lock_criterion(self):
        m = json.loads((SIM_DIR / "divider-n20" / "testbench" / "tb.json").read_text())["measure"]
        stop_s = float(m["tran_stop"].rstrip("n")) * 1e-9
        out_period = 20 / 250e6
        lock = m["lock"]
        need = lock["window_cycles"] + 1 + lock["min_hold_cycles"]
        self.assertGreaterEqual((stop_s - 6e-9) / out_period, need)


class FrequencyPeriodCoupling(unittest.TestCase):
    def test_500mhz_probe_derives_clk_and_target_from_one_frequency(self):
        plan = F.stimulus_for(SPEC, 20, F500, 1.8)
        self.assertAlmostEqual(plan.clk_period_s, 2e-9, places=18)
        self.assertAlmostEqual(plan.expected_out_period_s, 40e-9, places=17)
        self.assertAlmostEqual(1 / plan.expected_out_period_s, 25e6, delta=1)
        patched = F.patch_stimulus(NETLIST, plan)
        self.assertIn("2000p)", re.search(r"^V\d+ CLK .*$", patched, re.M).group(0))

    def test_observation_window_scales_with_n_and_frequency(self):
        plan = F.stimulus_for(SPEC, 20, F500, 1.8)
        c = SPEC.criterion
        self.assertAlmostEqual(
            plan.tran_stop_s,
            SPEC.stimulus.reset_high_at_s + (c.skip_output_periods + c.min_periods + c.margin_periods) * 40e-9,
            places=15)


class MandatoryProbeScheduling(unittest.TestCase):
    def test_500mhz_is_declared_but_not_a_coarse_probe(self):
        grid = F.grid(SPEC.search)
        coarse = {grid[i] for i in F.coarse_indices(len(grid), SPEC.search.coarse_stride)}
        self.assertEqual(SPEC.mandatory_probes_hz, (F500,))
        self.assertNotIn(F500, coarse)  # a coarse-only plan would never probe it
        self.assertIn(F500, {grid[i] for i in F.stage1_indices(grid, SPEC)})

    def test_existing_manifest_plan_is_unchanged(self):
        self.assertNotIn("mandatory_probes_hz", BASE_MANIFEST)
        self.assertEqual(BASE_SPEC.mandatory_probes_hz, ())
        grid = F.grid(BASE_SPEC.search)
        self.assertEqual(F.stage1_indices(grid, BASE_SPEC),
                         F.coarse_indices(len(grid), BASE_SPEC.search.coarse_stride))
        self.assertEqual(C.planned_stage1(range(225), BASE_SPEC), 225 * 10)
        self.assertEqual([m.n for m in BASE_SPEC.moduli], [4, 5, 25, 63, 64])

    def test_planned_probe_counts(self):
        # 89 grid points, stride 8 -> 12 coarse probes, plus the mandatory one.
        self.assertEqual(len(F.grid(SPEC.search)), 89)
        self.assertEqual(C.planned_stage1([None], SPEC), 13)
        self.assertEqual(C.planned_stage1(range(45), SPEC), 45 * 13)

    def test_off_grid_or_duplicate_probe_is_rejected(self):
        for bad in ([512.5e6], [F500, F500], [100e6]):
            with self.subTest(bad=bad), self.assertRaises(F.FmaxError):
                F.FmaxSpec.from_manifest({**MANIFEST, "mandatory_probes_hz": bad})

    def test_dry_run_lists_the_mandatory_probe(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = C.main([str(STAGE_A_PATH), "--dry-run", "--corners", "tt", "--temps", "27",
                         "--supply-tol", "0"])
        self.assertEqual(rc, 0)
        self.assertIn("stage-1 probes 13", buf.getvalue())
        self.assertIn("mandatory probes (every cell): 500 MHz", buf.getvalue())


class MandatoryProbeRetention(unittest.TestCase):
    def mandatory(self, cap_hz, errors=None, spec=SPEC):
        grid, cells = run_stage_a(spec, FakeBackend(lambda n, c: cap_hz, errors=errors))
        cell = cells[0]
        return grid, cell, F.fmax_bracket(cell.observed, grid), F.mandatory_results(cell.observed, grid, spec)

    def test_probe_is_run_and_retained_when_the_search_is_censored_high(self):
        _, cell, b, mand = self.mandatory(9e9)
        self.assertEqual(b.status, F.CENSORED_HIGH)
        self.assertEqual(mand, {F500: F.PASS})
        self.assertIn(F500, [p["freq_hz"] for p in cell.probes])

    def test_probe_is_run_and_retained_when_the_search_is_censored_low(self):
        _, cell, b, mand = self.mandatory(100e6)
        self.assertEqual(b.status, F.CENSORED_LOW)
        self.assertEqual(mand, {F500: F.FAIL})
        self.assertIn(F500, [p["freq_hz"] for p in cell.probes])

    def test_electrical_fail_and_invalid_run_are_distinct(self):
        _, _, _, fail = self.mandatory(450e6)
        self.assertEqual(fail, {F500: F.FAIL})
        for kind in ("timeout", "error", "nodump"):
            with self.subTest(kind=kind):
                _, _, _, inv = self.mandatory(9e9, errors={F500: kind})
                self.assertEqual(inv, {F500: F.INCONCLUSIVE})
        self.assertNotEqual(fail[F500], F.INCONCLUSIVE)

    def test_negative_control_without_the_declaration_the_probe_is_never_made(self):
        undeclared = dataclasses.replace(SPEC, mandatory_probes_hz=())
        grid, cell, _, _ = self.mandatory(9e9, spec=undeclared)
        self.assertNotIn(F500, [p["freq_hz"] for p in cell.probes])
        # The spec that declares it asks the question of that same observation.
        self.assertEqual(F.mandatory_results(cell.observed, grid, SPEC), {F500: None})

    def test_unrun_and_non_passing_probes_fail_the_record(self):
        grid = F.grid(SPEC.search)
        b = F.fmax_bracket({0: F.PASS, len(grid) - 1: F.PASS}, grid)
        row = {"n": 20, "corner": "tt", "temp_c": 27.0, "supply_v": 1.8, "boundary": b}
        self.assertEqual(fmax_report.overall([{**row, "mandatory": {F500: F.PASS}}])[0], "PASS")
        for st in (F.FAIL, F.INCONCLUSIVE, None):
            with self.subTest(st=st):
                self.assertEqual(fmax_report.overall([{**row, "mandatory": {F500: st}}])[0], "FAIL")
        # Manifests without mandatory probes keep their verdict rule.
        self.assertEqual(fmax_report.overall([row])[0], "PASS")

    def test_record_lists_each_mandatory_probe(self):
        grid = F.grid(SPEC.search)
        row = {"n": 20, "corner": "tt", "temp_c": 27.0, "supply_v": 1.8,
               "boundary": F.fmax_bracket({0: F.PASS, 88: F.PASS}, grid),
               "mandatory": {F500: F.INCONCLUSIVE}}
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "s.spice"
            snap.write_text("* x\n")
            pdk = SimpleNamespace(variant="sky130A", resolved_commit="abc", commit_mismatch=False,
                                  pinned_commit="abc", ngspice_lib="/x/sky130.lib.spice")
            text = fmax_report.render(
                record_id="20260101-000000-abcdef0", slug="divider-fmax", manifest=MANIFEST,
                spec=SPEC, pdk=pdk, tool_versions={}, repo_root=SIM_DIR.parent,
                netlist_snapshot=snap, cells=[row], probe_count=2, subset_reason="test",
                supersedes=None, execution_note=None)
        self.assertIn(fmax_report.MANDATORY_TABLE_HEADING, text)
        self.assertIn("| 20 | tt | 27 | 1.80 | 500 | INCONCLUSIVE |", text)
        self.assertIn("**Overall: FAIL**", text)


class ClassificationAt500MHz(unittest.TestCase):
    """The synthetic controls, applied at the N=20 / 500 MHz operating point."""

    plan = F.stimulus_for(SPEC, 20, F500, 1.8)

    def test_correct_division_passes(self):
        self.assertEqual(judge(self.plan, output_edges(self.plan)).status, F.PASS)

    def test_missing_edge_is_a_measured_fail(self):
        v = judge(self.plan, output_edges(self.plan, skip_cycles={4}))
        self.assertEqual(v.status, F.FAIL)

    def test_incorrect_division_ratio_is_a_fail(self):
        # N=21 behaviour from an N=20 request: 5% period error > 2% tolerance.
        v = judge(self.plan, output_edges(self.plan, period_scale=21 / 20))
        self.assertEqual(v.status, F.FAIL)

    def test_dead_output_is_a_fail_but_a_truncated_run_is_invalid(self):
        edges = output_edges(self.plan, dead_after=self.plan.steady_from_s)
        self.assertEqual(judge(self.plan, edges).status, F.FAIL)
        t, v = trace(self.plan, output_edges(self.plan))
        cut = [i for i, x in enumerate(t) if x < self.plan.tran_stop_s * 0.5]
        verdict = F.classify_waveform([t[i] for i in cut], [v[i] for i in cut], self.plan,
                                      threshold_frac=0.5, hysteresis_frac=0.15)
        self.assertEqual(verdict.status, F.INCONCLUSIVE)


if __name__ == "__main__":
    unittest.main()
