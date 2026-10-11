"""Contract tests for the sim/pfd-cp and sim/pfd-cp-resolution manifests (#250).

These pin the #247 measurement contract and the testbench's structure. They
are not simulation evidence; the evidence is the committed records.
"""

import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sim.harness import corners, cpmeasure, runner  # noqa: E402

SIM = REPO_ROOT / "sim"
VALID = tuple(json.loads((SIM / "pdk.json").read_text())["process_corners"])


def manifest(slug):
    return json.loads((SIM / slug / "testbench" / "tb.json").read_text())


class PfdCpManifestTests(unittest.TestCase):
    def setUp(self):
        self.m = manifest("pfd-cp")
        self.spec = cpmeasure.CpSpec.from_manifest(self.m)

    def test_parses_with_issue_247_stimulus(self):
        s = self.spec
        self.assertEqual(s.frequency_hz, 10e6)
        self.assertEqual(s.duty, 0.5)
        self.assertAlmostEqual(s.rise_s, 100e-12)
        self.assertAlmostEqual(s.fall_s, 100e-12)
        self.assertAlmostEqual(s.first_edge_s, 100e-9)
        self.assertEqual((s.settle_periods, s.integrate_periods), (20, 10))
        self.assertAlmostEqual(s.dump_step_s, 5e-12)
        self.assertAlmostEqual(s.max_step_s, 5e-12)

    def test_declared_grids(self):
        s = self.spec
        self.assertEqual([round(f, 1) for f in s.vctrl_fractions], [i / 10 for i in range(1, 10)])
        self.assertEqual(
            [round(o * 1e9, 6) for o in s.phase_offsets_s],
            [-25, -10, -5, -1, -0.5, -0.1, -0.05, 0, 0.05, 0.1, 0.5, 1, 5, 10, 25],
        )

    def test_is_the_full_45_point_grid(self):
        m = self.m
        self.assertEqual(sorted(m["process_corners"]), ["ff", "fs", "sf", "ss", "tt"])
        self.assertEqual(m["temps_c"], [-40, 27, 125])
        pts = corners.build_matrix(m, VALID)
        self.assertEqual(len(pts), 45)
        self.assertEqual(sorted({round(p.supply_v, 2) for p in pts}), [1.62, 1.8, 1.98])

    def test_main_grid_has_no_diagnostic_and_row_citations_are_mechanism_only(self):
        self.assertIsNone(self.spec.diagnostic)
        self.assertEqual(self.m["spec_rows"], [10, 12])
        note = self.m["spec_rows_note"]
        self.assertIn("mechanism-only", note)
        self.assertIn("DRAFT", note)
        self.assertIn("no total-PLL-power claim", note)

    def test_op_vectors_name_the_rbias_branch(self):
        exprs = [v.expr for v in self.spec.op_vectors]
        self.assertIn("v(xx1.nb)", exprs)
        self.assertIn("@r.xx1.xrbias.rend1[i]", exprs)

    def test_control_block_uses_manifest_sources_and_declares_no_forcing(self):
        block = cpmeasure.build_cp_control_block(self.spec, 1.8, "p-")
        self.assertIn("alter VCLAMP", block)
        self.assertIn("alter VREF", block)
        self.assertIn("alter VDIV", block)
        self.assertEqual(block.count("\ntran "), 9 * 15)
        self.assertNotIn("force", block)


class PfdCpTestbenchTests(unittest.TestCase):
    SCH = (SIM / "pfd-cp" / "testbench" / "tb_pfd_cp.sch").read_text()

    def test_instantiates_the_unchanged_dut_symbol_on_its_real_ports(self):
        self.assertIn("{design/pfd-cp/pfd_cp.sym}", self.SCH)
        labels = set(re.findall(r"lab=(\w+)\}", self.SCH))
        self.assertTrue({"VDD", "GND", "REF", "DIV", "CP"} <= labels)

    def test_clamp_positive_terminal_is_cp(self):
        m = re.search(r"vsource\.sym\} (\d+) (\d+) 0 0 \{name=VCLAMP", self.SCH)
        self.assertIsNotNone(m)
        x, y = m.group(1), m.group(2)
        # the label above the source (its positive pin) is CP
        self.assertRegex(self.SCH, rf"lab_pin\.sym\}} {x} {int(y) - 30} 0 0 \{{name=\w+ sig_type=std_logic lab=CP\}}")

    def test_no_analysis_or_forcing_cards_in_schematic(self):
        body = self.SCH.split("}\nG {}", 1)[1]
        for card in (".tran", ".op", ".ic", ".nodeset", ".alter"):
            self.assertNotIn(card, body)

    def test_dut_files_are_not_touched_by_this_campaign(self):
        # the testbench reaches the block only via the symbol; no copy of the
        # block's schematic lives under sim/
        self.assertEqual(list((SIM / "pfd-cp").rglob("pfd_cp.sch")), [])

    def test_patches_cleanly(self):
        netlist = (
            "* tb\nV1 VDD GND 1.8\n.lib /p/sky130.lib.spice tt\n.GLOBAL GND\n.end\n"
        )
        m = manifest("pfd-cp")
        spec = cpmeasure.CpSpec.from_manifest(m)
        point = corners.PvtPoint(corner="fs", temp_c=125.0, supply_v=1.98)
        out = runner.patch_netlist(netlist, m, point, cp_spec=spec)
        self.assertIn(".lib /p/sky130.lib.spice fs", out)
        self.assertIn("V1 VDD GND 1.98", out)
        self.assertIn(".temp 125", out)
        self.assertIn(cpmeasure.COMPLETION_MARKER, out)


class PfdCpResolutionManifestTests(unittest.TestCase):
    def setUp(self):
        self.m = manifest("pfd-cp-resolution")
        self.spec = cpmeasure.CpSpec.from_manifest(self.m)

    def test_is_one_nominal_point_with_a_finer_diagnostic(self):
        pts = corners.build_matrix(self.m, VALID)
        self.assertEqual(len(pts), 1)
        self.assertEqual((pts[0].corner, pts[0].temp_c, round(pts[0].supply_v, 2)), ("tt", 27.0, 1.8))
        d = self.spec.diagnostic
        self.assertAlmostEqual(d.dump_step_s, 2.5e-12)
        self.assertAlmostEqual(d.max_step_s, 2.5e-12)
        self.assertEqual([round(o * 1e9, 6) for o in sorted(d.phase_offsets_s)], [-0.1, 0.0, 0.1])

    def test_shares_the_main_campaign_testbench_and_stimulus(self):
        main = manifest("pfd-cp")
        self.assertEqual((SIM / "pfd-cp-resolution" / "testbench" / self.m["schematic"]).resolve(),
                         (SIM / "pfd-cp" / "testbench" / "tb_pfd_cp.sch").resolve())
        self.assertEqual(self.m["cp"]["frequency_hz"], main["cp"]["frequency_hz"])
        self.assertEqual(self.m["cp"]["dump_step_s"], main["cp"]["dump_step_s"])

    def test_cites_no_spec_row_and_says_why(self):
        self.assertEqual(self.m["spec_rows"], [])
        self.assertTrue(self.m["spec_rows_note"])


if __name__ == "__main__":
    unittest.main()
