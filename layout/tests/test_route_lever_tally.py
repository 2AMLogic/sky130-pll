"""Check the supply outcomes in a routed spot-check's measurement row."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

LAYOUT_BIN = Path(__file__).resolve().parents[1] / "bin"
if str(LAYOUT_BIN) not in sys.path:
    sys.path.insert(0, str(LAYOUT_BIN))

from route_lever_tally import tally_row


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


if __name__ == "__main__":
    unittest.main()
