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
    """Issue #304: klt 0.8.0 writes resistors as `X` cards, not `R` cards.

    The multiset is read from `devices[]`, so the deck's card form no longer
    matters; the history above is why this read left the deck (PR #416).
    """

    EXTRACT = {"devices": [
        {"class": "res_xhigh_po", "params": {"r_ohm": 5060.0}},
        {"class": "res_xhigh_po", "params": {"r_ohm": 10000.0}},
        {"class": "sky130_fd_pr__model__cap_mim", "params": {"c_f": 1e-12}},
    ]}

    def test_resistors_counted_from_json(self) -> None:
        got = render.extracted_sets(self.EXTRACT)["res"]
        self.assertEqual(got, {("res_xhigh_po", 5060.0): 1, ("res_xhigh_po", 10000.0): 1})

    def test_no_resistors_means_empty(self) -> None:
        self.assertFalse(render.extracted_sets({"devices": []})["res"])


class ExtractedMos(unittest.TestCase):
    """Issue #455: the MOS multiset moves from the deck's `M` cards to JSON.

    `M` cards still match at `klt` 0.8.0, but the deck card form drifted twice
    (capacitor 0.4.0 -> 0.6.0, resistor 0.6.0 -> 0.8.0) while `devices[]` did
    not. The trap pinned down here: a `res_xhigh_po` entry carries `l_um`/
    `w_um` as well as `r_ohm`, so an l_um-presence filter would count a
    block's bias resistors as MOS and fail its exact-Counter check -- MOS is
    therefore picked by class (`set(MOS_MODELS.values())`). Fixtures use the
    real `klt` 0.8.0 `devices[]` entry shape: nfet/pfet params carry
    ad/as/pd/ps/l/w, res_xhigh_po carries area/perimeter/r_ohm/l/w, cap_mim
    carries area/c_f/perimeter (no l_um/w_um at all).
    """

    EXTRACT = {"devices": [
        {"class": "nfet", "params": {
            "ad_um2": 0.45, "as_um2": 0.45, "l_um": 0.15, "pd_um": 2.47,
            "ps_um": 2.47, "w_um": 2.0}},
        {"class": "pfet", "params": {
            "ad_um2": 0.78, "as_um2": 0.78, "l_um": 0.5, "pd_um": 2.94,
            "ps_um": 2.94, "w_um": 4.0}},
    ]}

    def test_mos_counted_from_json_keyed_class_w_l(self) -> None:
        got = render.extracted_sets(self.EXTRACT)["mos"]
        self.assertEqual(got, {("nfet", 2.0, 0.15): 1, ("pfet", 4.0, 0.5): 1})

    def test_resistor_in_same_array_is_not_counted_as_mos(self) -> None:
        extract = {"devices": list(self.EXTRACT["devices"]) + [
            {"class": "res_xhigh_po", "params": {
                "area_um2": 2.53, "l_um": 2.53, "perimeter_um": 7.06,
                "r_ohm": 5060.0, "w_um": 1.0}},
        ]}
        got = render.extracted_sets(extract)
        self.assertEqual(got["mos"], {("nfet", 2.0, 0.15): 1, ("pfet", 4.0, 0.5): 1})
        self.assertEqual(got["res"], {("res_xhigh_po", 5060.0): 1})

    def test_no_devices_means_empty(self) -> None:
        self.assertFalse(render.extracted_sets({"devices": []})["mos"])

    def test_cap_only_array_yields_no_mos(self) -> None:
        extract = {"devices": [
            {"class": "sky130_fd_pr__model__cap_mim", "params": {
                "area_um2": 4.0, "c_f": 1e-12, "perimeter_um": 8.0}},
        ]}
        self.assertFalse(render.extracted_sets(extract)["mos"])

    def test_malformed_mos_entries_are_skipped(self) -> None:
        extract = {"devices": [
            {"class": "nfet"},
            {"class": "nfet", "params": {"w_um": 2.0}},
            {"class": "nfet", "params": {"l_um": 0.15}},
        ]}
        self.assertFalse(render.extracted_sets(extract)["mos"])


if __name__ == "__main__":
    unittest.main()
