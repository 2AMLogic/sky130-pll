"""Check the routed tally against the evidence used in the PLL record."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
LAYOUT_BIN = REPO_ROOT / "layout" / "bin"
for path in (REPO_ROOT, LAYOUT_BIN):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from route_lever_tally import merged_nodes, tally_row

from scripts.test_support import load_module

render = load_module("render_pll_record", LAYOUT_BIN / "render-pll-record.py", register=False)


class SupplyStatusTests(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.run_dir = Path(temp_dir.name)
        self.spot_dir = self.run_dir / "route-spot-check"
        self.spot_dir.mkdir()
        (self.spot_dir / "drc.json").write_text('{"violation_count": 0}')
        response = {
            "nets": [
                {"net": "AVDD", "status": "partial"},
                {"net": "VDD", "status": "unrouted"},
                {"net": "GND", "status": "routed"},
            ]
        }
        (self.spot_dir / "compose.vco.response.json").write_text(json.dumps(response))

    def test_uses_supply_names_from_the_routed_build(self):
        (self.run_dir / "build.json").write_text("{}")
        build = self.spot_dir / "build.json"
        build.write_text(json.dumps({"routing_levers": {"supply_nets": ["AVDD"]}}))
        row = tally_row(self.run_dir, "record", "supply plane", ["supply-plane"])
        self.assertEqual(row["supply_status"], {"vco": {"AVDD": "partial"}})
        self.assertEqual(
            row["evidence_sha256"]["route-spot-check/build.json"],
            hashlib.sha256(build.read_bytes()).hexdigest(),
        )

    def test_uses_default_rails_without_recorded_supply_names(self):
        for build in (None, {}, {"routing_levers": {"supply_nets": []}}):
            with self.subTest(build=build):
                if build is not None:
                    (self.spot_dir / "build.json").write_text(json.dumps(build))
                row = tally_row(self.run_dir, "record", "baseline", [])
                self.assertEqual(
                    row["supply_status"], {"vco": {"VDD": "unrouted", "GND": "routed"}}
                )


class MergedNodesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run_dir = Path(temp.name)
        self.spot_dir = self.run_dir / "route-spot-check"
        self.spot_dir.mkdir()
        for name in ("build.json", "drc.json", "extract.json"):
            (self.spot_dir / name).write_text("{}")

    def test_missing_netlist_is_optional_for_tally_but_required_for_record(self):
        row = tally_row(self.run_dir, "record", "", [])
        self.assertEqual(row["shorted_nodes"], 0)
        with self.assertRaises(FileNotFoundError):
            render._load_spot_check(self.run_dir)
        self.assertEqual(merged_nodes(self.spot_dir), [])

    def test_tally_and_spot_check_agree_on_unique_nodes(self):
        for netlist, expected in (
            ("R1 clk_out GND 1k\n", []),
            ("R1 z|n1 A_0|B|C 1k\nR2 A_0|B|C z|n1 2k\n", ["A_0|B|C", "z|n1"]),
        ):
            with self.subTest(netlist=netlist):
                (self.spot_dir / "pll_top.spice").write_text(netlist)
                self.assertEqual(merged_nodes(self.spot_dir), expected)
                spot = render._load_spot_check(self.run_dir)
                self.assertEqual(spot["merged_nodes"], expected)
                row = tally_row(self.run_dir, "record", "", [])
                self.assertEqual(row["shorted_nodes"], len(expected))
                _, ok, detail = render._check_levers_final_row(
                    self.run_dir, [row], "record"
                )
                self.assertTrue(ok, detail)
                row["shorted_nodes"] += 1
                _, ok, detail = render._check_levers_final_row(
                    self.run_dir, [row], "record"
                )
                self.assertFalse(ok)
                self.assertIn("shorted_nodes", detail)


class SupersedesTests(unittest.TestCase):
    oldest = "20260101-000000-abc1234"
    prior = "20260102-000000-abc1234"
    current = "20260103-000000-abc1234"

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        reports = root / "layout" / "pll" / "reports"
        reports.mkdir(parents=True)
        (reports / "LATEST").write_text(self.oldest + "\n")
        (reports.parent / "spec-rows.json").write_text('{"spec_rows": [18]}')
        self.args = argparse.Namespace(
            repo_root=root, out_dir=reports / self.current, record_id=self.current
        )

    def render_header(self):
        lines = []
        render._render_header(lines.append, self.args, "pll.spice")
        return [line for line in lines if "**Supersedes**" in line]

    def test_newest_tracked_prior_takes_precedence_over_latest(self):
        tracked = "\n".join(
            f"layout/pll/reports/{name}/record.md"
            for name in (self.prior, self.current, self.oldest)
        )
        with mock.patch.object(render, "run_git", return_value=tracked) as run_git:
            (line,) = self.render_header()
        run_git.assert_called_once_with(
            self.args.repo_root, "ls-files", "--", "layout/pll/reports"
        )
        self.assertIn(self.prior, line)

    def test_falls_back_to_latest_when_only_current_record_is_tracked(self):
        tracked = f"layout/pll/reports/{self.current}/record.md"
        with mock.patch.object(render, "run_git", return_value=tracked):
            (line,) = self.render_header()
        self.assertIn(self.oldest, line)

    def test_failed_git_lookup_propagates_even_with_latest(self):
        # A broken .git file makes Git fail regardless of any parent checkout.
        (self.args.repo_root / ".git").write_text("gitdir: missing\n")
        with self.assertRaises(subprocess.CalledProcessError):
            self.render_header()


if __name__ == "__main__":
    unittest.main()
