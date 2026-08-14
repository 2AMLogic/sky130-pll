#!/usr/bin/env python3
"""PDK-free sanity checks on layout/trivial-cell/reference*.spice.

These do not invoke `klt`/ngspice at all -- they check the three hand-written
LVS reference netlists are internally consistent with what
layout/README.md and each file's own header claim: 8 M-cards, a balanced
.SUBCKT/.ENDS pair, and exactly the documented single-line corruption
between the good reference and each negative control.

    python3 -m unittest discover -s layout/tests -v
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

TRIVIAL_CELL_DIR = Path(__file__).resolve().parents[1] / "trivial-cell"

GOOD = TRIVIAL_CELL_DIR / "reference.spice"
BROKEN_DEVICE = TRIVIAL_CELL_DIR / "reference.broken-device.spice"
BROKEN_TOPOLOGY = TRIVIAL_CELL_DIR / "reference.broken-topology.spice"

M_CARD_RE = re.compile(r"^M\d+ .*$", re.MULTILINE)


def device_lines(path: Path) -> list[str]:
    return M_CARD_RE.findall(path.read_text())


class ReferenceNetlistTests(unittest.TestCase):
    def test_all_three_references_exist(self):
        for path in (GOOD, BROKEN_DEVICE, BROKEN_TOPOLOGY):
            self.assertTrue(path.is_file(), f"missing {path}")

    def test_good_reference_has_eight_devices(self):
        self.assertEqual(len(device_lines(GOOD)), 8)

    def test_all_references_are_balanced_subckt_ends(self):
        for path in (GOOD, BROKEN_DEVICE, BROKEN_TOPOLOGY):
            text = path.read_text()
            self.assertEqual(text.count(".SUBCKT"), 1, path)
            self.assertEqual(text.count(".ENDS"), 1, path)
            self.assertEqual(len(device_lines(path)), 8, path)

    def test_broken_device_differs_from_good_by_one_parameter_only(self):
        good = device_lines(GOOD)
        bad = device_lines(BROKEN_DEVICE)
        diffs = [i for i, (g, b) in enumerate(zip(good, bad)) if g != b]
        self.assertEqual(len(diffs), 1, "expected exactly one corrupted device line")
        g, b = good[diffs[0]], bad[diffs[0]]
        # Same node list, different W value -- a device-parameter corruption,
        # not a topology one.
        self.assertEqual(g.split()[:4], b.split()[:4], "nodes must be unchanged")
        self.assertNotEqual(g, b)

    def test_broken_topology_differs_from_good_by_one_node_only(self):
        good = device_lines(GOOD)
        bad = device_lines(BROKEN_TOPOLOGY)
        diffs = [i for i, (g, b) in enumerate(zip(good, bad)) if g != b]
        self.assertEqual(len(diffs), 1, "expected exactly one corrupted device line")
        g, b = good[diffs[0]], bad[diffs[0]]
        # Same device parameters (L/W), different drain node -- a topology
        # (net-merge) corruption, not a device-parameter one.
        self.assertEqual(g.split()[4:], b.split()[4:], "L/W params must be unchanged")
        self.assertNotEqual(g.split()[1], b.split()[1], "drain node must differ")


if __name__ == "__main__":
    unittest.main()
