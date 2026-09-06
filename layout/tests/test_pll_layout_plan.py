#!/usr/bin/env python3
"""PDK-free checks on the schematic-driven PLL layout plan (issue #16).

These invoke neither `klt` nor the PDK: they exercise `pll_layout.py`'s pure
half against the *checked-in schematic netlist*, which is exactly the half
that decides what the layout draws. The claim they defend is the one the
layout record makes at the top of its verdict list -- the drawn device set is
the schematic's device set, derived rather than declared -- so a schematic
change that this builder would silently mis-draw (a new device flavor, a
device the grouper drops, a 3.3 V-class device sneaking in from the gf180
port) fails here, in `npm run check:ci`, without needing a PDK install.

    python3 -m unittest discover -s layout/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

LAYOUT_BIN = Path(__file__).resolve().parents[1] / "bin"
if str(LAYOUT_BIN) not in sys.path:
    sys.path.insert(0, str(LAYOUT_BIN))

import pll_layout  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
NETLIST = REPO_ROOT / "design" / "top" / "netlist" / "top.spice"


class NetlistParsingTests(unittest.TestCase):
    def test_netlist_exists(self):
        self.assertTrue(NETLIST.is_file(), f"missing {NETLIST}")

    def test_top_level_subckt_is_recovered_from_xschems_commented_header(self):
        # xschem writes the top-level subcircuit's own `.subckt`/`.ends` lines
        # commented out ("**.subckt top ...") while emitting its instance
        # cards uncommented. If the parser ever stops un-commenting those, the
        # builder silently loses the block list and draws nothing.
        cards = pll_layout.read_cards(NETLIST.read_text())
        self.assertIn("top", cards)
        self.assertEqual(len(cards["top"]), 4, "top instantiates four blocks")

    def test_continuation_lines_are_joined(self):
        text = "\n".join(
            [
                "**.subckt demo",
                "XM1 d g s b sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1",
                "+ ad=0.29 as=0.29",
                "**.ends",
            ]
        )
        cards = pll_layout.read_cards(text)["demo"]
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["params"]["AS"], "0.29")


class PlanCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = NETLIST.read_text()
        cls.cards = pll_layout.read_cards(cls.text)
        cls.plan = pll_layout.build_plan(cls.text)

    def test_every_schematic_device_is_drawn_exactly_once(self):
        for block in self.plan["blocks"]:
            drawn = sum(group["count"] for group in block["groups"])
            self.assertEqual(
                drawn,
                len(self.cards[block["name"]]),
                f"{block['name']}: plan draws {drawn} of "
                f"{len(self.cards[block['name']])} schematic devices",
            )

    def test_every_device_card_maps_to_exactly_one_group_member(self):
        for block in self.plan["blocks"]:
            members = [
                member["device"]
                for group in block["groups"]
                for member in group["members"]
            ]
            self.assertEqual(
                sorted(members),
                sorted(card["name"] for card in self.cards[block["name"]]),
                f"{block['name']}: group members do not match the netlist's "
                "own instance names",
            )

    def test_mos_arrays_draw_no_extra_devices(self):
        # rows*cols must be *exactly* the group's device count, and no dummy
        # columns: a matched array that rounds its size up would put devices
        # in the layout that the schematic never asked for, and the record's
        # extracted-vs-schematic multiset check would have to be loosened to
        # accommodate them.
        for block in self.plan["blocks"]:
            for group in block["groups"]:
                if group["kind"] != "mos_array":
                    continue
                params = group["params"]
                self.assertEqual(
                    params["rows"] * params["cols"], group["count"], group["id"]
                )
                self.assertEqual(params["dummy"], 0, group["id"])

    def test_mos_arrays_opt_into_gate_contact(self):
        # issue #18: every mos_array group must request a contacted gate
        # landing pad, or every net terminating on that group's gates is
        # unroutable by construction (klayout-tools#492's capability, only
        # useful once actually requested here).
        for block in self.plan["blocks"]:
            for group in block["groups"]:
                if group["kind"] != "mos_array":
                    continue
                self.assertTrue(
                    group["params"].get("gate_contact"), group["id"]
                )

    def test_mos_arrays_keep_common_centroid_device_matching(self):
        # issue #18 / PR #118 review: every even-count matched group must
        # keep `klt gen mos_array`'s common-centroid port-numbering topology
        # (the generator's own documented default) -- a real
        # centroid-symmetric visiting order that pairs instance 2k with its
        # point-reflection through the grid center, which is what cancels
        # process-gradient mismatch across the VCO ring stages and the
        # PFD/CP current mirrors. An odd count cannot be paired, so it
        # legitimately falls back to plain row-major `array`.
        #
        # Forcing this to a plain "array" does measurably improve this flow's
        # routing spot-check coverage, so the temptation is real and was
        # acted on once. It is not a trade this design may make: the shipped
        # stream is unrouted, so the spot-check is a diagnostic while the
        # device-to-position assignment is a property of the shipped
        # geometry. This test is the guard that makes dropping it a
        # deliberate, visible act rather than a silent side effect of an
        # unrelated floorplan change.
        for block in self.plan["blocks"]:
            for group in block["groups"]:
                if group["kind"] != "mos_array":
                    continue
                expected = "common_centroid" if group["count"] % 2 == 0 else "array"
                self.assertEqual(
                    group["params"]["topology"], expected, group["id"]
                )

    def test_mos_arrays_are_packed_in_a_near_square_grid(self):
        # issue #18: matched groups use `factor_rows_cols`'s near-square
        # grid, not a 1xN row. A single-row packing was measured across the
        # full topology x packing 2x2 (see the comment at the call site in
        # layout/bin/pll_layout.py) and is neutral-to-worse for routing
        # coverage in both topology regimes, while spreading a matched
        # group's devices over the widest possible span -- the very gradient
        # distance common-centroid ordering exists to cancel.
        for block in self.plan["blocks"]:
            for group in block["groups"]:
                if group["kind"] != "mos_array":
                    continue
                params = group["params"]
                self.assertEqual(
                    (params["rows"], params["cols"]),
                    pll_layout.factor_rows_cols(group["count"]),
                    group["id"],
                )

    def test_res_arrays_draw_no_dummy_elements(self):
        for block in self.plan["blocks"]:
            for group in block["groups"]:
                if group["kind"] == "res_array":
                    self.assertEqual(group["params"]["dummy"], 0, group["id"])
                    self.assertEqual(group["params"]["num"], group["count"], group["id"])

    def test_group_ids_are_unique(self):
        ids = [group["id"] for block in self.plan["blocks"] for group in block["groups"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_plan_is_deterministic(self):
        self.assertEqual(self.plan, pll_layout.build_plan(self.text))


class SupplyFlavorTests(unittest.TestCase):
    """DR-001: the ratified flavor is sky130's 1.8 V core devices."""

    def test_every_mos_device_in_the_schematic_is_a_1v8_core_device(self):
        cards = pll_layout.read_cards(NETLIST.read_text())
        models = {
            card["model"]
            for block_cards in cards.values()
            for card in block_cards
            if "fet" in card["model"]
        }
        self.assertTrue(models, "expected the schematic to contain MOS devices")
        for model in models:
            self.assertTrue(
                model.endswith("_01v8"),
                f"{model} is not a sky130 1.8 V core device (DR-001)",
            )

    def test_a_3v3_device_would_be_refused_rather_than_drawn_as_something_else(self):
        card = {
            "name": "XM1",
            "model": "sky130_fd_pr__nfet_g5v0d10v5",
            "nets": ["d", "g", "s", "b"],
            "params": {"W": "1", "L": "0.5"},
        }
        with self.assertRaises(pll_layout.PlanError):
            pll_layout.classify(card)


class FactorizationTests(unittest.TestCase):
    def test_rows_times_cols_is_always_the_exact_count(self):
        for count in range(1, 65):
            rows, cols = pll_layout.factor_rows_cols(count)
            self.assertEqual(rows * cols, count, count)
            self.assertLessEqual(rows, cols, count)

    def test_zero_devices_is_an_error(self):
        with self.assertRaises(pll_layout.PlanError):
            pll_layout.factor_rows_cols(0)


class ShelfPackTests(unittest.TestCase):
    def test_boxes_never_overlap_and_keep_the_requested_spacing(self):
        boxes = [(f"b{i}", 10.0 + i, 5.0 + (i % 3)) for i in range(9)]
        origins, (width, height) = pll_layout.shelf_pack(boxes, 40.0, 2.0)
        self.assertEqual(len(origins), len(boxes))
        placed = [
            (
                origins[box_id]["x"],
                origins[box_id]["y"],
                origins[box_id]["x"] + w,
                origins[box_id]["y"] + h,
            )
            for box_id, w, h in boxes
        ]
        for i, a in enumerate(placed):
            for b in placed[i + 1 :]:
                overlap_x = min(a[2], b[2]) - max(a[0], b[0])
                overlap_y = min(a[3], b[3]) - max(a[1], b[1])
                self.assertTrue(
                    overlap_x <= 0 or overlap_y <= 0, f"{a} overlaps {b}"
                )
        self.assertGreater(width, 0.0)
        self.assertGreater(height, 0.0)

    def test_packing_is_deterministic(self):
        boxes = [(f"b{i}", 3.0 * i + 1, 2.0) for i in range(6)]
        self.assertEqual(
            pll_layout.shelf_pack(boxes, 12.0, 1.0),
            pll_layout.shelf_pack(boxes, 12.0, 1.0),
        )


class ConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = pll_layout.build_plan(NETLIST.read_text())

    def test_declared_nets_reference_only_ports_their_group_actually_has(self):
        for block in self.plan["blocks"]:
            available = {
                (group["id"], port)
                for group in block["groups"]
                for member in group["members"]
                for port in member.get("ports", {})
            }
            for entry in pll_layout.block_connectivity(block):
                self.assertGreaterEqual(len(entry["pins"]), 2, entry["net"])
                for pin in entry["pins"]:
                    self.assertIn((pin["block"], pin["port"]), available, entry["net"])

    def test_every_multi_terminal_schematic_net_is_declared(self):
        # The composed stream carries no wires, so `plan.json`'s port/net map
        # *is* this layout's record of the schematic topology. A net that
        # silently stopped being declared would quietly shrink that record.
        cards = pll_layout.read_cards(NETLIST.read_text())
        for block in self.plan["blocks"]:
            if any(group["kind"] == "stdcell" for group in block["groups"]):
                continue  # library cells expose no port geometry -- see the module docstring
            counts: dict[str, int] = {}
            for card in cards[block["name"]]:
                nets = card["nets"]
                if pll_layout.classify(card) == "mos":
                    nets = nets[:3]  # d/g/s -- the bulk terminal is not a drawn port
                for net in nets:
                    counts[net] = counts.get(net, 0) + 1
            expected = {net for net, count in counts.items() if count >= 2}
            declared = {entry["net"] for entry in pll_layout.block_connectivity(block)}
            self.assertEqual(expected, declared, block["name"])


class LvsReferenceTextTests(unittest.TestCase):
    # issue #18: `klt lvs`'s SPICE reader needs a real `.subckt top ...` /
    # `.ends` pair to recognise the top level as a comparable circuit --
    # xschem emits that pair doubly-commented (`**.subckt` / `**.ends`).
    def test_uncomments_the_doubly_commented_subckt_and_ends_only(self):
        text = (
            "** this is a genuine comment, not a subckt marker\n"
            "**.subckt top vin vout\n"
            "xpfd pfd_cp a b\n"
            ".subckt pfd_cp a b\n"
            "m1 a b c d nfet_01v8\n"
            ".ends\n"
            "**.ends\n"
        )
        out = pll_layout.lvs_reference_text(text)
        lines = out.splitlines()
        self.assertIn(".subckt top vin vout", lines)
        # the already-plain subcircuit below `top` is left untouched
        self.assertIn(".subckt pfd_cp a b", lines)
        self.assertEqual(lines.count(".ends"), 2)  # pfd_cp's own, plus top's uncommented
        self.assertIn("** this is a genuine comment, not a subckt marker", lines)
        self.assertNotIn("**.subckt top vin vout", lines)
        self.assertNotIn("**.ends", lines)

    def test_real_netlist_top_level_becomes_a_real_subckt(self):
        out = pll_layout.lvs_reference_text(NETLIST.read_text())
        self.assertIn(".subckt top", out)
        self.assertNotIn("**.subckt top", out)


if __name__ == "__main__":
    unittest.main()
