#!/usr/bin/env python3
"""PDK-free sanity checks on layout/trivial-cell/drc-negative-control.json.

The DRC negative control is only meaningful if its geometry is actually
illegal. A well-meaning edit that rounds a dimension up to a legal value
would turn the control into a silent no-op: the fixture would DRC clean, and
"the flow catches an injected DRC violation" would quietly stop being true.

These tests need no PDK, no `klt`, and no KLayout -- they re-derive each
declared violation from the fixture's own rectangles against the sky130
minimums hardcoded below, so `npm run check:ci` catches the regression on
every push rather than only on a machine that can run the full flow.

The complementary end-to-end check lives in layout/bin/render-record.py,
which fails the run unless the deck reports exactly the rules the fixture's
`_expected_rules` block declares.

    python3 -m unittest discover -s layout/tests -v
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

TRIVIAL_CELL_DIR = Path(__file__).resolve().parents[1] / "trivial-cell"
FIXTURE = TRIVIAL_CELL_DIR / "drc-negative-control.json"

# sky130 minimums the curated `klt drc` sky130 deck enforces for the two
# rules this fixture targets. Values are documented deck constants, not spec
# values of this design -- nothing here depends on issue #1's supply flavor.
POLY_MIN_WIDTH_UM = 0.15  # poly.width.1
LI1_MIN_SPACE_UM = 0.17  # li1.space.1

POLY_LAYER = [66, 20]
LI1_LAYER = [67, 20]


def load_fixture() -> dict:
    with FIXTURE.open() as f:
        return json.load(f)


def rects_on(fixture: dict, layer: list) -> list:
    return [s["rect_um"] for s in fixture["shapes"] if s["layer"] == layer]


class DrcNegativeControlFixtureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture()

    def test_fixture_exists_and_declares_expected_rules(self):
        declared = self.fixture.get("_expected_rules")
        self.assertIsInstance(declared, dict)
        self.assertEqual(
            sorted(declared), ["li1.space.1", "poly.width.1"],
            "render-record.py asserts the deck fires exactly these rules; "
            "changing the set here must be matched by a re-run of the flow",
        )

    def test_poly_rect_is_narrower_than_the_minimum_poly_width(self):
        polys = rects_on(self.fixture, POLY_LAYER)
        self.assertEqual(len(polys), 1, "expected exactly one poly rectangle")
        x0, y0, x1, y1 = polys[0]
        narrow_dim = min(abs(x1 - x0), abs(y1 - y0))
        self.assertLess(
            narrow_dim,
            POLY_MIN_WIDTH_UM,
            f"poly rect narrow dimension {narrow_dim} um is legal (>= "
            f"{POLY_MIN_WIDTH_UM} um): the poly.width.1 negative control "
            "would no longer violate anything",
        )

    def test_li1_rects_are_closer_than_the_minimum_li1_spacing(self):
        li1 = rects_on(self.fixture, LI1_LAYER)
        self.assertEqual(len(li1), 2, "expected exactly two li1 rectangles")
        (_, _, _, lower_top), (_, upper_bottom, _, _) = sorted(
            li1, key=lambda r: r[1]
        )
        gap = upper_bottom - lower_top
        self.assertGreater(gap, 0, "the two li1 rects must not overlap or abut")
        self.assertLess(
            gap,
            LI1_MIN_SPACE_UM,
            f"li1 gap {gap} um is legal (>= {LI1_MIN_SPACE_UM} um): the "
            "li1.space.1 negative control would no longer violate anything",
        )

    def test_no_shape_is_on_an_undeclared_layer(self):
        for shape in self.fixture["shapes"]:
            self.assertIn(
                shape["layer"],
                (POLY_LAYER, LI1_LAYER),
                "a shape on an unexpected layer may trip a different rule "
                "than the fixture declares",
            )


if __name__ == "__main__":
    unittest.main()
