#!/usr/bin/env python3
"""
Tests for the item 1/9/10 inventories under signoff/inventory/ and the
manifest's partition_boundary (issue #329).

1. Every path an inventory lists exists on disk.
2. The manifest's partition_boundary names the same files as the README's
   "Block kind: mixed-signal, and the partition boundary" section.
3. Every partitioned row of the rendered report carries its partition_boundary.
"""

import json
import pathlib
import re
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_INVENTORY = _REPO_ROOT / "signoff" / "inventory"
_PATH_KEYS = ("files", "bench_dirs", "dirs")


def _inventories():
    return sorted(_INVENTORY.glob("*.json"))


class TestInventories(unittest.TestCase):
    def test_inventories_present(self):
        names = {p.stem for p in _inventories()}
        self.assertEqual(
            names,
            {"item1-analog", "item1-digital", "item9-analog", "item9-digital", "item10"},
        )

    def test_every_inventoried_path_exists(self):
        for inv in _inventories():
            data = json.loads(inv.read_text())
            listed = [p for k in _PATH_KEYS for p in data.get(k, [])]
            self.assertTrue(listed, f"{inv.name} lists no paths")
            for rel in listed:
                self.assertTrue((_REPO_ROOT / rel).exists(), f"{inv.name}: missing {rel}")

    def test_partition_boundary_matches_readme(self):
        manifest = json.loads((_REPO_ROOT / "signoff" / "block-manifest.json").read_text())
        boundary = manifest["partition_boundary"]
        self.assertEqual(set(boundary), {"analog", "digital"})
        readme = (_REPO_ROOT / "signoff" / "README.md").read_text()
        section = readme.split("## Block kind: `mixed-signal`, and the partition boundary", 1)[1]
        section = section.split("\n## ", 1)[0]
        for part, text in boundary.items():
            for path in re.findall(r"design/[\w./-]+", text):
                path = path.rstrip(".,)")
                self.assertIn(path, section, f"{part}: {path} not in README boundary section")

    def test_report_rows_carry_partition_boundary(self):
        report = json.loads((_REPO_ROOT / "signoff" / "tier-report.json").read_text())
        manifest = json.loads((_REPO_ROOT / "signoff" / "block-manifest.json").read_text())
        for row in report["items"]:
            if row["partition"] is None:
                continue  # shared rows are not partitioned
            self.assertEqual(
                row["partition_boundary"], manifest["partition_boundary"][row["partition"]]
            )


if __name__ == "__main__":
    unittest.main()
