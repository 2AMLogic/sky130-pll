#!/usr/bin/env python3
"""The PLL record prose must state the plan's block count, not a typed-in one.

Issue #304: the renderer hard-coded "four blocks" after `clk_buf` made it five.
PDK- and `klt`-free.

    python3 -m unittest layout.tests.test_render_block_count -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.test_support import load_module  # noqa: E402

LAYOUT_BIN = Path(__file__).resolve().parents[1] / "bin"
render = load_module("render_pll_record_bc", LAYOUT_BIN / "render-pll-record.py", register=False)

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def _render(fn, *args) -> str:
    lines: list[str] = []
    fn(lines.append, *args)
    return "\n".join(lines)


def _blocks(n: int) -> list[dict]:
    return [
        {"name": f"b{i}", "cell_name": f"c{i}", "device_count": 1, "group_count": 1,
         "size_um": [1, 1], "declared_nets": 2, "groups": []}
        for i in range(n)
    ]


class BlockCountProse(unittest.TestCase):
    def test_prose_follows_block_count(self) -> None:
        for n in (4, 5, 6):
            plan = {"top_cell_name": "pll_top", "blocks": _blocks(n)}
            build = {"blocks": _blocks(n), "top": {"cell_name": "t", "size_um": [1, 1]}}
            is_text = _render(render._render_layout_is, plan, build, Path("/nonexistent"))
            not_text = _render(
                render._render_layout_is_not, plan, build, {"status": "clean"}
            )
            for text in (is_text, not_text):
                self.assertIn(f"the {WORDS[n]} blocks", text)
                for other in (4, 5, 6):
                    if other != n:
                        self.assertNotIn(f"the {WORDS[other]} blocks", text)

    def test_no_hardcoded_block_count_in_renderer_source(self) -> None:
        src = (LAYOUT_BIN / "render-pll-record.py").read_text()
        self.assertNotIn("the four blocks", src)


class ExtractedResistors(unittest.TestCase):
    """Issue #304: klt 0.8.0 writes resistors as `X` cards, not `R` cards."""

    DECK = (
        "X$4 \\$1 \\$2 vsubs res_xhigh_po r=5060 L=2.53U W=1U\n"
        "X$5 \\$3 \\$4 vsubs res_xhigh_po r=10000 L=5U W=1U\n"
    )
    EXTRACT = {"devices": [
        {"class": "res_xhigh_po", "params": {"r_ohm": 5060.0}},
        {"class": "res_xhigh_po", "params": {"r_ohm": 10000.0}},
        {"class": "sky130_fd_pr__model__cap_mim", "params": {"c_f": 1e-12}},
    ]}

    def test_resistors_counted_from_json_not_deck_cards(self) -> None:
        got = render.extracted_sets(self.DECK, self.EXTRACT)["res"]
        self.assertEqual(got, {("res_xhigh_po", 5060.0): 1, ("res_xhigh_po", 10000.0): 1})

    def test_no_resistors_means_empty(self) -> None:
        self.assertFalse(render.extracted_sets("", {"devices": []})["res"])


if __name__ == "__main__":
    unittest.main()
