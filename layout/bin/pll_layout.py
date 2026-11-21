#!/usr/bin/env python3
"""Schematic-driven PLL layout builder (issue #16).

Reads the *authored schematic's own netlist* (`design/top/netlist/top.spice`,
the closed-loop hierarchy landed by #28) and derives, deterministically, the
layout's device set from it -- then drives `klt` to draw that device set and
compose it into one `pll_top` GDS. Nothing about the device set is typed in
by hand here: every drawn device exists because a device card in the
schematic netlist asked for it, which is what makes "the layout matches the
schematic's device set" a checkable claim rather than an assertion.

Two halves, deliberately separated so the first is testable with no PDK and
no `klt` installed (`layout/tests/test_pll_device_set.py` exercises it):

1. **Plan** (pure, PDK-free): parse the netlist, classify every device card,
   group the MOS devices of each block into matched arrays keyed by
   `(flavor, W, L)`, and lay the groups out on a shelf-packed floorplan.
   `build_plan()` returns plain JSON-serialisable data.
2. **Build** (impure): run `klt gen` / `klt draw` per planned group, then
   `klt gen-compose` per block and once more for the top cell.

Scope caveat, stated here because it is the honest headline of this
deliverable: this is a **device-level floorplan**, not a routed full-custom
layout. Inter-device routing is limited to what `klt gen-compose`'s
point-to-point router can do (2-pin nets); every larger net is declared in
the composition request's `connectivity[]` and reported back in
`unrouted_nets[]`. DRC-clean and LVS-clean closure are issues #17/#18, not
this one. See `layout/pll/README.md` for the full "what is and is not
verified" statement.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# --- Device model recognition ----------------------------------------------
#
# The ratified supply flavor is sky130's 1.8 V core devices (DR-001, see
# spec/decision-records/DR-001-supply-flavor-scope.md). These tables are the
# only place a model name is turned into a drawable primitive, so a stray
# 3.3 V-class device carried over from the gf180-pll port cannot be drawn
# silently -- it raises `PlanError` instead (and
# layout/tests/test_pll_device_set.py asserts the netlist contains none).

MOS_MODELS = {
    "sky130_fd_pr__nfet_01v8": "nfet",
    "sky130_fd_pr__pfet_01v8": "pfet",
}

RESISTOR_MODELS = {
    # model -> `klt gen res_array` flavor param
    "sky130_fd_pr__res_xhigh_po": "xhigh",
    "sky130_fd_pr__res_high_po": "high",
    "sky130_fd_pr__res_generic_po": "generic",
}

# MiM capacitors have no `klt gen` generator (see layout/pll/README.md's
# friction section), so they are drawn as plate geometry with `klt draw` on
# the two layers the curated sky130 extraction deck recognises the device by.
CAP_MODELS = {
    "sky130_fd_pr__cap_mim_m3_1": ("met3", "capm"),
}

STDCELL_PREFIX = "sky130_fd_sc_hd__"

#: (layer, datatype) pairs used by the drawn MiM capacitor plates. Sourced
#: from the curated sky130 extraction deck's own capacitor definition
#: (`klayout_tools.decks.sky130.EXTRACTION_DECK.capacitors[0]`:
#: top_plate=(89, 44) capm.drawing over bottom_plate=(70, 20) met3.drawing).
CAP_LAYERS = {"met3": (70, 20), "capm": (89, 44)}

#: Curated-deck electrical constants, used only to predict what `klt extract`
#: should report back for a drawn passive (the record's cross-check), never to
#: size anything. Sourced from `klayout_tools.decks.sky130.EXTRACTION_DECK`:
#: `resistors[...].sheet_rho_ohm_sq` for `res_xhigh_po`, and
#: `capacitors[0].area_cap_f_um2` / `.perim_cap_f_um` for the MiM stack.
SHEET_RHO_OHM_SQ = {"xhigh": 2000.0, "high": 319.8, "generic": 48.2}
MIM_AREA_CAP_F_UM2 = 2.0e-15
#: Perimeter/fringe term of the same MiM stack, in F per um of top-plate
#: perimeter. `klt extract` reports a MiM capacitor as
#: `W*L*area_cap_f_um2 + 2*(W+L)*perim_cap_f_um`; the area term alone
#: undercounts a small unit capacitor by up to ~15%, which is why the deck
#: carries both (klayout-tools#512/#517, reaching this repo with issue #46's
#: pin bump -- the `0.2.0` release predates it and reported the area term
#: only). The record predicts the same two-term value so its
#: schematic-vs-extracted capacitor comparison stays exact.
MIM_PERIM_CAP_F_UM = 1.9e-16

#: Minimum li1 (local-interconnect) spacing the curated sky130 DRC deck
#: enforces (`li1.space.1`), in um. `klt gen`'s MOS unit devices abut their
#: source/drain li1 pads directly against the poly gate, so a device whose
#: gate length is below this spacing draws two pads closer than the rule
#: allows -- one violation per such device. Through issue #46's `klt` pin
#: that was the only violation class this flow's output produced; issue #17
#: bumped the pin past the upstream fix (klayout-tools#1201) and the deck now
#: comes back genuinely clean, so the record's DRC check asserts zero
#: violations from *any* rule rather than this one class. This threshold is
#: what identifies the devices that fired the rule back then, so the record
#: can state that history with a count derived from the plan (issue #443).
LI1_MIN_SPACE_UM = 0.17

#: Bottom-plate (met3) overhang beyond the capm top plate, per side (um).
#: The schematic's W/L is the *capacitor* size, i.e. the capm plate, since
#: that is the layer the extraction deck measures the area of; met3 is drawn
#: larger so the plate is fully landed.
CAP_BOTTOM_MARGIN_UM = 0.2

#: Standard-cell library the divider's cells come from, and its row height
#: (sky130 high-density library). Cells are placed in one abutted row on the
#: site grid -- see `plan_block` for why one row.
STDCELL_LIB = "sky130_fd_sc_hd"
STDCELL_ROW_UM = 2.72
#: Each library cell's drawn bbox overhangs its logical (site-grid) width by
#: this much per side -- nwell/pwell overhang shared with the abutting cell.
STDCELL_BBOX_OVERHANG_UM = 0.19

#: Spacing left between placed groups inside a block, and between blocks at
#: the top level (um). Well above every curated-deck same-layer spacing rule,
#: so block-to-block spacing is never the binding DRC constraint.
GROUP_SPACING_UM = 4.0
BLOCK_SPACING_UM = 20.0

#: Shelf-packer target width for a block's own group floorplan (um). Groups
#: are placed left to right and wrap to a new shelf past this, which keeps a
#: block's aspect ratio sane without pretending to be a real floorplanner.
BLOCK_TARGET_WIDTH_UM = 220.0

#: Router settings handed to `klt gen-compose` (`routing.layer_role`
#: `"metal2"` is met1 with a via1 drop back to each pad's own li1 layer).
ROUTING_LAYER_ROLE = "metal2"
ROUTING_WIDTH_UM = 0.3

#: Routing levers the *routed spot-check build* requests (issue #548). Every
#: one of these is a shipped `klt gen-compose` / `klt gen` capability this
#: generator never asked for until issue #548 measured what they buy; the
#: unrouted *shipped* build is untouched by all of them (see `Builder` for
#: where each one enters the request).
#:
#: The second plane for cross-block/self-net fallback legs: one metal role
#: above the met1 primary, so a same-block leg that would short across
#: another of its own block's pads on met1 retries on met2 instead
#: (`routing.cross_block_layer_role`, klayout-tools#1168). Per-net planes for
#: the supplies (`connectivity[].layer_role`, klayout-tools#1655) so the
#: rails stop competing with signals for the one met1 plane; the fanout
#: signals get their own plane one higher still. `interior_channel_um` on
#: `mos_array` (klayout-tools#1531, closed) reserves navigable row/column
#: gap bands the router is allowed to pass through
#: (`navigable_regions`, subtracted from a block's obstacle bbox per
#: klayout-tools#1835) -- sized for one routing width plus the same-layer
#: spacing either side of it.
CROSS_BLOCK_LAYER_ROLE = "metal3"
INTERIOR_CHANNEL_UM = 1.0
SUPPLY_LAYER_ROLE = "metal3"
FANOUT_LAYER_ROLE = "metal4"
#: How many of the highest-pin-count non-supply nets get a per-net plane.
#: #18 warns against exhaustive hand assignment of every declared net; this
#: stays a handful by construction (the set is derived from the plan at
#: build time, never typed in).
FANOUT_NET_LIMIT = 4

#: The selectable lever names (`--route-levers`), in the order issue #548
#: applied and measured them. ``all`` (the default) and ``none`` are
#: convenience spellings the CLI expands.
ROUTE_LEVER_NAMES = (
    "cross-block-plane",
    "interior-channel",
    "supply-plane",
    "fanout-plane",
)


def parse_route_levers(spec: str) -> frozenset[str]:
    """Expand a `--route-levers` argument into a set of lever names.

    ``all`` (an empty argument means the same) selects every lever in
    `ROUTE_LEVER_NAMES`; ``none`` selects nothing. Anything else is a
    comma-separated subset, so the measurement ladder in issue #548 could
    run one lever at a time cumulatively; an unknown name is a `PlanError`
    rather than a silently dropped no-op (the same convention `klt` itself
    applies to unrecognized request keys).
    """
    text = spec.strip()
    if text in ("all", ""):
        return frozenset(ROUTE_LEVER_NAMES)
    if text == "none":
        return frozenset()
    levers = {name.strip() for name in text.split(",") if name.strip()}
    unknown = levers - set(ROUTE_LEVER_NAMES)
    if unknown:
        raise PlanError(
            f"unknown route lever(s) {sorted(unknown)} -- allowed: "
            f"{list(ROUTE_LEVER_NAMES)}, all, none"
        )
    return frozenset(levers)


class PlanError(Exception):
    """The schematic netlist contains something this builder cannot draw."""


# --- 1. Netlist parsing (pure, PDK-free) ------------------------------------


def read_cards(netlist_text: str) -> dict[str, list[dict[str, Any]]]:
    """Parse a flat SPICE netlist into `{subckt: [instance card, ...]}`.

    Handles xschem's `+` continuation lines and its `*`-comment convention.
    An instance card is `{name, model, nets, params}` -- the trailing tokens
    of the form `k=v` are params, the last remaining positional token is the
    model/subckt name, and everything between the instance name and the model
    is the ordered net list.
    """
    joined: list[str] = []
    for raw in netlist_text.splitlines():
        line = raw.rstrip()
        if line.startswith("+") and joined:
            joined[-1] = joined[-1] + " " + line[1:].strip()
        else:
            joined.append(line)

    blocks: dict[str, list[dict[str, Any]]] = {}
    current: str | None = None
    for line in joined:
        stripped = line.strip()
        # xschem comments out the *top-level* subcircuit's own header/footer
        # ("**.subckt top ..." / "**.ends") while emitting its instance cards
        # uncommented, so the top level is a subcircuit in every way that
        # matters here. Uncomment those two forms before the comment filter.
        if stripped.startswith("**.subckt") or stripped.startswith("**.ends"):
            stripped = stripped[2:]
        if not stripped or stripped.startswith("*"):
            continue
        lowered = stripped.lower()
        if lowered.startswith(".subckt"):
            current = stripped.split()[1]
            blocks.setdefault(current, [])
            continue
        if lowered.startswith(".ends"):
            current = None
            continue
        if stripped.startswith("."):
            continue
        if current is None:
            continue

        tokens = stripped.split()
        params: dict[str, str] = {}
        positional: list[str] = []
        for token in tokens[1:]:
            if "=" in token:
                key, value = token.split("=", 1)
                params[key.upper()] = value
            else:
                positional.append(token)
        if len(positional) < 2:
            raise PlanError(f"unparsable instance card: {stripped!r}")
        blocks[current].append(
            {
                "name": tokens[0],
                "model": positional[-1],
                "nets": positional[:-1],
                "params": params,
            }
        )
    return blocks


def _um(card: dict[str, Any], key: str) -> float:
    raw = card["params"].get(key)
    if raw is None:
        raise PlanError(f"{card['name']} ({card['model']}) has no {key} param")
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover - malformed netlist
        raise PlanError(f"{card['name']}: {key}={raw!r} is not a number") from exc


def classify(card: dict[str, Any]) -> str:
    """Return the primitive kind this instance card draws as."""
    model = card["model"]
    if model in MOS_MODELS:
        return "mos"
    if model in RESISTOR_MODELS:
        return "resistor"
    if model in CAP_MODELS:
        return "capacitor"
    if model.startswith(STDCELL_PREFIX):
        return "stdcell"
    raise PlanError(
        f"{card['name']}: no layout primitive is defined for model {model!r} "
        "(if this is a new device flavor, extend MOS_MODELS/RESISTOR_MODELS/"
        "CAP_MODELS in layout/bin/pll_layout.py rather than drawing it as "
        "something it is not)"
    )


def _slug(value: float) -> str:
    text = f"{value:g}".replace(".", "p").replace("-", "m")
    return text


def factor_rows_cols(count: int) -> tuple[int, int]:
    """Pick a `(rows, cols)` pair whose product is exactly `count`.

    Exactly -- never rounded up -- so an array never draws a device the
    schematic did not ask for. `rows` is the largest divisor of `count` at or
    below its square root, which keeps the array as close to square as its
    own factorization allows (18 -> 3x6, 6 -> 2x3, 5 -> 1x5, 1 -> 1x1).
    """
    if count < 1:
        raise PlanError(f"cannot lay out a group of {count} devices")
    rows = 1
    for candidate in range(1, int(math.isqrt(count)) + 1):
        if count % candidate == 0:
            rows = candidate
    return rows, count // rows


def _mos_array_group(
    group_id: str,
    flavor: str,
    w_um: float,
    l_um: float,
    rows: int,
    cols: int,
    members: list[dict[str, Any]],
    *,
    row_channel: bool = False,
) -> dict[str, Any]:
    """One `mos_array` group dict for `rows` x `cols` of `members` (in order).

    Shared by both the single-block and row-split paths in `plan_block` below
    so the two only differ in what `rows`/`cols`/`members` slice they pass --
    everything about how a group's own params/members are shaped is written
    once. `row_channel` is a plan-only marker (never forwarded into `params`,
    which is passed to `klt gen` verbatim) recording *why* this group is
    `rows=1`: `True` means it is one row of a larger matched group that was
    split so `GROUP_SPACING_UM` of real inter-block space falls where an
    opaque multi-row `mos_array` call would otherwise leave a zero-width
    internal row gap (issue #18) -- distinct from a group that is `rows=1`
    simply because `factor_rows_cols` found it has too few devices to need a
    second row. `layout/tests/test_pll_layout_plan.py` reads this back
    instead of parsing `id` strings.
    """
    count = len(members)
    return {
        "id": group_id,
        "kind": "mos_array",
        "generator": "mos_array",
        "row_channel": row_channel,
        "params": {
            "w_um": w_um,
            "l_um": l_um,
            "rows": rows,
            "cols": cols,
            "dummy": 0,
            "flavor": flavor,
            # A matched array is only meaningful common-centroid when its
            # device count is even; an odd count cannot be paired, so it
            # falls back to plain row-major order. See the row-splitting
            # comment at this function's call site for why callers only ever
            # pass an odd count here when the *whole* schematic-declared
            # group is odd (never as a side effect of splitting an even one).
            #
            # `common_centroid` is `klt gen mos_array`'s own documented
            # default and a real centroid-symmetric visiting order (its
            # `_centroid_order`): instance 2k is immediately followed by its
            # point-reflection through the grid center, so a matched pair
            # lands centroid-symmetrically and a linear process gradient
            # cancels across it. That is the standard analog matching
            # technique, and this loop covers every matched group in the
            # design -- the VCO ring stages, the PFD/CP current mirrors, the
            # divider transistors.
            #
            # Forcing this to a plain "array" measurably improves this
            # flow's routing spot-check coverage (see `layout/pll/README.md`
            # for the 2x2 measurement). It is deliberately NOT taken. The
            # routing spot-check is a diagnostic build -- the stream this
            # flow actually ships is unrouted -- whereas the
            # device-to-position assignment this field controls is a
            # property of the shipped geometry. Trading real device matching
            # in the shipped layout for a better number in a diagnostic is
            # exactly the kind of laundering this repo's CLAUDE.md forbids;
            # the routing gap is recorded as a miss instead.
            "topology": "common_centroid" if count % 2 == 0 else "array",
            "gate_contact": True,
        },
        "count": count,
        "members": [
            {
                "device": card["name"],
                "unit": index,
                # xschem writes a MOS card as `X<name> d g s b <model>`.
                "ports": {
                    f"U{index}_D": card["nets"][0],
                    f"U{index}_G": card["nets"][1],
                    f"U{index}_S": card["nets"][2],
                },
            }
            for index, card in enumerate(members)
        ],
    }


def plan_block(block_name: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Group one `.subckt`'s device cards into drawable layout groups."""
    mos: dict[tuple[str, float, float], list[dict[str, Any]]] = {}
    res: dict[tuple[str, float, float], list[dict[str, Any]]] = {}
    caps: list[dict[str, Any]] = []
    stdcells: list[dict[str, Any]] = []

    for card in cards:
        kind = classify(card)
        if kind == "mos":
            key = (MOS_MODELS[card["model"]], _um(card, "W"), _um(card, "L"))
            mos.setdefault(key, []).append(card)
        elif kind == "resistor":
            key = (RESISTOR_MODELS[card["model"]], _um(card, "W"), _um(card, "L"))
            res.setdefault(key, []).append(card)
        elif kind == "capacitor":
            caps.append(card)
        else:
            stdcells.append(card)

    groups: list[dict[str, Any]] = []

    for (flavor, w_um, l_um), members in sorted(mos.items()):
        # Issue #18: `factor_rows_cols`'s near-square grid is the base shape
        # (kept for the reasons below). Historically a single opaque
        # `mos_array` call reserved *no* channel between its own rows --
        # `gen-compose` saw one solid bbox regardless of `rows`/`cols`, and
        # reading `_mos_array_layout`'s parameter surface directly confirmed
        # no channel knob existed, which is what was filed upstream as
        # klayout-tools#1531. That gap has since been closed upstream: the
        # pinned `klt` reserves navigable interior gap bands via
        # `mos_array`'s `interior_channel_um` (reported back as
        # `navigable_regions`, which `gen-compose` subtracts from the
        # block's obstacle bbox, klayout-tools#1835), and the routed
        # spot-check build now requests exactly that -- see
        # `Builder.gen_group`. The split below is therefore no longer the
        # only interior-space lever, but it is kept: it is already shipped
        # and measured, the parity guard costs no device its matched
        # partner, and it buys `GROUP_SPACING_UM` of *placement* space
        # between independently placed blocks -- a different resource than
        # the channel the generator now reserves inside one call, and one
        # the routed build gets on top of (not instead of) the channel.
        #
        # The lever this flow's own floorplan requests *do* control is how
        # many devices go into one `klt gen` call in the first place --
        # nothing requires an entire matched group to be one call. Splitting
        # the near-square grid into `rows` separate one-row `mos_array`
        # calls of `cols` devices each turns what used to be a zero-width
        # internal row gap into `GROUP_SPACING_UM` of real, router-visible
        # space between independently placed blocks -- the same kind of gap
        # `shelf_pack` already reserves between every other pair of groups.
        #
        # This is only done when `cols` is itself even, so every row keeps
        # its own valid common-centroid pairing (`_centroid_order`'s
        # point-reflection still has a mirror within that row) -- splitting
        # never costs a device its matched partner. On this design that is
        # exactly the two 18-device groups (`factor_rows_cols(18) ==
        # (3, 6)`, an even `cols`); every other matched group either already
        # fits on one row (`rows == 1` -- nothing to split) or has an odd
        # `cols` (the four 6-device groups, `factor_rows_cols(6) ==
        # (2, 3)`), where splitting would silently drop common-centroid
        # matching to plain `array` order on a smaller group than the
        # schematic's own count -- a real analog-matching regression this
        # flow does not make to chase a routing number, the same principle
        # `_mos_array_group`'s own `topology` guard already applies. See
        # `layout/pll/README.md` for the measured effect on this design's
        # routing spot-check.
        #
        # A single-row packing of the *whole* group (`rows=1, cols=count`,
        # one block, not several) was tried earlier and measured
        # neutral-to-worse (62/917 -> 55/945 with centroid ordering kept) --
        # see the git history of this comment and `layout/pll/README.md` for
        # that 2x2. This is a different change: several small one-row blocks
        # with real spacing between them, not one large one-row block.
        count = len(members)
        rows, cols = factor_rows_cols(count)
        group_id = f"{block_name}_{flavor}_w{_slug(w_um)}_l{_slug(l_um)}"
        if rows > 1 and cols % 2 == 0:
            for row in range(rows):
                chunk = members[row * cols : (row + 1) * cols]
                groups.append(
                    _mos_array_group(
                        f"{group_id}_row{row}",
                        flavor,
                        w_um,
                        l_um,
                        1,
                        cols,
                        chunk,
                        row_channel=True,
                    )
                )
        else:
            groups.append(
                _mos_array_group(group_id, flavor, w_um, l_um, rows, cols, members)
            )

    for (flavor, w_um, l_um), members in sorted(res.items()):
        count = len(members)
        group_id = f"{block_name}_res{flavor}_w{_slug(w_um)}_l{_slug(l_um)}"
        groups.append(
            {
                "id": group_id,
                "kind": "res_array",
                "generator": "res_array",
                "params": {
                    "length_um": l_um,
                    "width_um": w_um,
                    "num": count,
                    "dummy": 0,
                    "rows": 1,
                    "flavor": flavor,
                },
                "count": count,
                "members": [
                    {
                        "device": card["name"],
                        "unit": index,
                        # `X<name> plus minus bulk <model>`.
                        "ports": {
                            f"R{index}_A": card["nets"][0],
                            f"R{index}_B": card["nets"][1],
                        },
                    }
                    for index, card in enumerate(members)
                ],
            }
        )

    for card in sorted(caps, key=lambda c: c["name"]):
        w_um, l_um = _um(card, "W"), _um(card, "L")
        groups.append(
            {
                "id": f"{block_name}_{card['name']}",
                "kind": "mim_cap",
                "generator": "draw",
                "params": {"w_um": w_um, "l_um": l_um},
                "count": 1,
                "members": [
                    {
                        "device": card["name"],
                        "unit": 0,
                        # `X<name> top bottom <model>`.
                        "ports": {"TOP": card["nets"][0], "BOT": card["nets"][1]},
                    }
                ],
            }
        )

    for index, card in enumerate(stdcells):
        cell = card["model"]
        groups.append(
            {
                "id": f"{block_name}_{card['name']}",
                "kind": "stdcell",
                "generator": "library",
                "params": {"cell": cell},
                "count": 1,
                "members": [
                    {"device": card["name"], "unit": 0, "nets": card["nets"]}
                ],
            }
        )

    return {
        "name": block_name,
        "cell_name": f"pll_{block_name}",
        "device_count": len(cards),
        "groups": groups,
    }


def build_plan(netlist_text: str, top_subckt: str = "top") -> dict[str, Any]:
    """Derive the whole layout plan from a schematic netlist."""
    cards = read_cards(netlist_text)
    if top_subckt not in cards:
        raise PlanError(f"netlist has no .subckt {top_subckt}")

    # Block order = the order the top-level schematic instantiates them, so
    # the floorplan's left-to-right order follows the signal path the
    # schematic itself declares rather than an alphabetical accident.
    block_order = [card["model"] for card in cards[top_subckt]]
    missing = [name for name in block_order if name not in cards]
    if missing:
        raise PlanError(f"top instantiates undefined subckt(s): {missing}")

    return {
        "top_subckt": top_subckt,
        "top_cell_name": "pll_top",
        "blocks": [plan_block(name, cards[name]) for name in block_order],
    }


def lvs_reference_text(netlist_text: str) -> str:
    """`netlist_text`, with the top level's `.subckt`/`.ends` uncommented.

    xschem writes the *top-level* subcircuit's own header/footer doubly
    commented (`**.subckt top ...` / `**.ends`, see `read_cards`'s docstring
    for why) while its instance cards are emitted uncommented -- fine for
    this module's own parser, which already strips the `**` prefix, but not
    for `klt lvs`'s reference-netlist reader, which needs a real `.subckt
    <top>` / `.ends` pair to recognise "top" as a comparable circuit at all
    (issue #18). Nothing else about the netlist is touched -- every
    subcircuit below `top` is already written in plain, uncommented SPICE.
    """
    lines = []
    for line in netlist_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("**.subckt") or stripped.startswith("**.ends"):
            line = line.replace("**.", ".", 1)
        lines.append(line)
    return "\n".join(lines) + "\n"


def supply_nets(netlist_text: str, top_subckt: str = "top") -> list[str]:
    """The top level's own `*.iopin` markers, in declaration order.

    xschem writes the top-level schematic's supply pins as `*.iopin <name>`
    comment markers directly under its (doubly commented) `.subckt` header --
    `VDD`/`GND` on this design. That is an *authored* declaration, so the
    supply-plane lever keys on it rather than on a typed-in net list: a
    renamed or added supply follows the schematic, not this file. Only the
    top's own markers are read -- the scan stops at the first uncommented
    child `.subckt`, so a block that also happens to name a net `VDD` does
    not extend the set (the child scopes' own `*.iopin` markers, if any,
    belong to their cells, not to the composition's rails).
    """
    supplies: list[str] = []
    for line in netlist_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(".subckt"):
            name = stripped.split()[1:2]
            if name and name[0] != top_subckt:
                # The first uncommented child `.subckt` -- everything past
                # the top's own header block belongs to a block's scope.
                break
        if stripped.startswith("*.iopin"):
            tokens = stripped.split()
            if len(tokens) >= 2:
                if tokens[1] not in supplies:
                    supplies.append(tokens[1])
    return supplies


def with_supply_plane(
    connectivity: list[dict[str, Any]],
    supplies: list[str],
    layer_role: str,
) -> list[dict[str, Any]]:
    """Supplies first and on their own plane; every other net unchanged.

    `gen-compose` routes `connectivity[]` in declaration order, so moving
    the supply entries to the front means the rails claim their plane
    before any signal net competes for it. Each supply entry additionally
    carries `connectivity[].layer_role` (klayout-tools#1655), taking it off
    the primary `routing.layer_role` plane entirely. Non-supply entries
    keep their original (sorted) order and fields, byte for byte.
    """
    supply_entries = [
        {**entry, "layer_role": layer_role}
        for entry in connectivity
        if entry["net"] in supplies
    ]
    supply_entries.sort(key=lambda entry: supplies.index(entry["net"]))
    others = [entry for entry in connectivity if entry["net"] not in supplies]
    return supply_entries + others


def top_fanout_nets(
    connectivity_by_block: dict[str, list[dict[str, Any]]],
    supplies: list[str],
    limit: int,
) -> list[str]:
    """The highest-pin-count non-supply nets, design-wide, deterministically.

    Pin counts are summed across blocks (a net declared in two blocks with
    four pins each has eight), supplies are excluded (they have their own
    lever), and ties break alphabetically so the set is a pure function of
    the plan. Capped at `limit` -- issue #18's warning against exhaustive
    hand assignment of every declared net is why the cap exists; the cut is
    derived, never curated per net.
    """
    pins: dict[str, int] = {}
    for connectivity in connectivity_by_block.values():
        for entry in connectivity:
            if entry["net"] in supplies:
                continue
            pins[entry["net"]] = pins.get(entry["net"], 0) + len(entry["pins"])
    ranked = sorted(pins.items(), key=lambda item: (-item[1], item[0]))
    return [net for net, _ in ranked[:limit]]


def with_fanout_plane(
    connectivity: list[dict[str, Any]],
    fanout_nets: list[str],
    layer_role: str,
) -> list[dict[str, Any]]:
    """Give the selected high-fanout nets a per-net plane, order untouched.

    Same mechanism as `with_supply_plane` (`connectivity[].layer_role`,
    klayout-tools#1655) minus the reordering: these are signal nets, and the
    supply lever owns the "who routes first" question.
    """
    if not fanout_nets:
        return connectivity
    return [
        {**entry, "layer_role": layer_role}
        if entry["net"] in fanout_nets
        else entry
        for entry in connectivity
    ]


# --- 2. Floorplanning (pure, PDK-free) --------------------------------------


def shelf_pack(
    sizes: list[tuple[str, float, float]], target_width_um: float, spacing_um: float
) -> tuple[dict[str, dict[str, float]], tuple[float, float]]:
    """Place `(id, width, height)` boxes left to right, wrapping past a width.

    Returns `({id: {"x", "y"}}, (width, height))`. Deterministic: identical
    input always yields identical origins, so a re-run of the flow produces a
    byte-comparable floorplan.
    """
    origins: dict[str, dict[str, float]] = {}
    x = y = shelf_height = 0.0
    max_x = 0.0
    for box_id, width, height in sizes:
        if x > 0.0 and x + width > target_width_um:
            y += shelf_height + spacing_um
            x = 0.0
            shelf_height = 0.0
        origins[box_id] = {"x": round(x, 3), "y": round(y, 3)}
        x += width + spacing_um
        max_x = max(max_x, x - spacing_um)
        shelf_height = max(shelf_height, height)
    return origins, (max_x, y + shelf_height)


# --- 3. Build (impure: runs `klt`) ------------------------------------------


class Builder:
    def __init__(
        self,
        klt: str,
        pdk: str,
        out_dir: Path,
        route: bool,
        route_levers: frozenset[str] = frozenset(),
    ) -> None:
        self.klt = klt
        self.pdk = pdk
        self.out_dir = out_dir
        self.route = route
        #: Which issue-#548 routing levers the *routed* build requests. The
        #: shipped (`--no-route`) build is unaffected by these no matter
        #: what they name: the interior-channel lever is gated on
        #: `self.route` inside `gen_group`, and every other lever only
        #: touches request fields the unrouted build never emits
        #: (`connectivity[]`/`routing`).
        self.route_levers = route_levers
        self.cells_cache: dict[str, dict[str, Any]] = {}

    def _run(self, args: list[str], *, ok_returncodes: tuple[int, ...] = (0,)) -> str:
        proc = subprocess.run(
            [self.klt, *args], capture_output=True, text=True, cwd=self.out_dir
        )
        if proc.returncode not in ok_returncodes:
            raise PlanError(
                f"klt {' '.join(args)} failed ({proc.returncode}):\n"
                f"{proc.stdout}\n{proc.stderr}"
            )
        return proc.stdout

    def _write_json(self, name: str, payload: Any) -> Path:
        path = self.out_dir / name
        path.write_text(json.dumps(payload, indent=2) + "\n")
        return path

    # -- primitives ---------------------------------------------------------

    def gen_group(self, group: dict[str, Any]) -> dict[str, Any]:
        """Draw one `klt gen` group (mos_array / res_array).

        With the interior-channel lever on, a multi-unit `mos_array` group
        additionally reserves `interior_channel_um` (klayout-tools#1531,
        closed) of navigable gap between its own rows/columns, which the
        generator reports back as `navigable_regions` and `gen-compose`
        subtracts from the block's obstacle bbox (klayout-tools#1835) --
        the router may then cross the array through its own interior bands
        instead of treating the whole footprint as opaque. Gated on
        `self.route` so the *shipped* build's `klt gen` calls (and therefore
        its GDS bytes, bboxes and DRC-clean evidence) stay exactly what
        they were before issue #548; a `rows == cols == 1` group has no
        interior gap bands at all, so the param is not added there.
        """
        cell = group["id"]
        params = group["params"]
        if (
            self.route
            and "interior-channel" in self.route_levers
            and group["kind"] == "mos_array"
            and (params["rows"] > 1 or params["cols"] > 1)
        ):
            params = {**params, "interior_channel_um": INTERIOR_CHANNEL_UM}
        report = json.loads(
            self._run(
                [
                    "gen",
                    group["generator"],
                    "--pdk",
                    self.pdk,
                    "--params",
                    json.dumps(params),
                    "--cell-name",
                    cell,
                    "-o",
                    f"{cell}.gds",
                    "--format",
                    "json",
                ]
            )
        )
        self._write_json(f"gen.{cell}.json", report)
        return report

    def draw_mim_cap(self, group: dict[str, Any]) -> dict[str, Any]:
        """Draw one MiM capacitor as plate geometry (`klt draw`).

        `klt gen` has no MiM-capacitor generator (friction filed upstream --
        see layout/pll/README.md), so the plates are written verbatim: the
        capm top plate at exactly the schematic's W x L (capm is the layer
        the curated extraction deck measures the device's area on), landed on
        a met3 bottom plate oversized by `CAP_BOTTOM_MARGIN_UM` per side.
        """
        cell = group["id"]
        w_um = group["params"]["w_um"]
        l_um = group["params"]["l_um"]
        margin = CAP_BOTTOM_MARGIN_UM
        request = {
            "shapes": [
                {
                    "layer": list(CAP_LAYERS["met3"]),
                    "rect_um": [0.0, 0.0, w_um + 2 * margin, l_um + 2 * margin],
                },
                {
                    "layer": list(CAP_LAYERS["capm"]),
                    "rect_um": [margin, margin, margin + w_um, margin + l_um],
                },
            ]
        }
        params_path = self._write_json(f"draw.{cell}.params.json", request)
        report = json.loads(
            self._run(
                [
                    "draw",
                    "--params",
                    params_path.name,
                    "--cell-name",
                    cell,
                    "-o",
                    f"{cell}.gds",
                    "--format",
                    "json",
                ]
            )
        )
        # `klt draw` reports no ports (it has no device model); synthesize the
        # two plate terminals at their own drawn centres so the composition
        # request can still name them.
        report["generator"] = "draw"
        report["ports"] = [
            {
                "name": "TOP",
                "layer": {"layer": CAP_LAYERS["capm"][0], "datatype": CAP_LAYERS["capm"][1]},
                "x_um": margin + w_um / 2.0,
                "y_um": margin + l_um / 2.0,
                "width_um": w_um,
                "direction_deg": 90,
            },
            {
                "name": "BOT",
                "layer": {"layer": CAP_LAYERS["met3"][0], "datatype": CAP_LAYERS["met3"][1]},
                "x_um": margin / 2.0,
                "y_um": margin + l_um / 2.0,
                "width_um": margin,
                "direction_deg": 180,
            },
        ]
        self._write_json(f"draw.{cell}.json", report)
        return report

    def library_cell(self, group: dict[str, Any]) -> dict[str, Any]:
        """Resolve one standard cell from the PDK's library GDS.

        `klt place-and-route` is the verb that would place a gate-level
        netlist, but it shells out to an `openroad` binary that is not part
        of the `klt` install (absent on this host). For a floorplan-level
        placement the cell's own GDS view plus its bounding box is all that
        is needed, and `klt cells` reports exactly that -- so the cell is
        consumed straight from the library stream.
        """
        cell = group["params"]["cell"]
        lib_gds = self.stdcell_library_gds()
        cells = self.cells_cache.get("lib")
        if cells is None:
            report = json.loads(
                self._run(["cells", str(lib_gds), "--format", "json"])
            )
            cells = {entry["name"]: entry for entry in report["cells"]}
            self.cells_cache["lib"] = cells
        if cell not in cells:
            raise PlanError(f"{cell} not found in {lib_gds}")
        bbox = cells[cell]["bbox_um"]
        return {
            "generator": "library",
            "cell_name": cell,
            "gds_path": os.path.relpath(lib_gds, self.out_dir),
            "bbox_um": {
                "x0": bbox["left"],
                "y0": bbox["bottom"],
                "x1": bbox["right"],
                "y1": bbox["top"],
            },
            "ports": [],
        }

    def stdcell_library_gds(self) -> Path:
        info = json.loads(
            self._run(["pdk", "find", "--pdk", self.pdk, "--format", "json"])
        )
        libs_ref = Path(info["assets"]["libs_ref"])
        path = libs_ref / STDCELL_LIB / "gds" / f"{STDCELL_LIB}.gds"
        if not path.is_file():
            raise PlanError(f"standard-cell library GDS not found: {path}")
        return path

    # -- composition --------------------------------------------------------

    def compose(
        self,
        request_name: str,
        blocks: list[dict[str, Any]],
        origins: dict[str, dict[str, float]],
        cell_name: str,
        connectivity: list[dict[str, Any]],
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "schema": "klt.gen_compose.request/1",
            "pdk": {"variant": self.pdk},
            "blocks": blocks,
            "placement": {
                "strategy": "explicit",
                "order": [block["id"] for block in blocks],
                "origins_um": origins,
            },
            "options": {"cell_name": cell_name, "output": f"{cell_name}.gds"},
        }
        # `connectivity[]` cannot be declared without also asking the router to
        # draw it -- `gen-compose` rejects a request whose `connectivity[]` is
        # non-empty and whose `routing` block is absent. So the unrouted build
        # omits `connectivity[]` from the *request*; the declared topology it
        # would have carried is written to `plan.json` either way (see
        # `block_connectivity`), which is where this flow's own record reads it
        # from. Friction filed upstream -- layout/pll/README.md.
        if connectivity and self.route:
            request["connectivity"] = connectivity
            routing: dict[str, Any] = {
                "layer_role": ROUTING_LAYER_ROLE,
                "width_um": ROUTING_WIDTH_UM,
            }
            if "cross-block-plane" in self.route_levers:
                # A second, higher plane a same-block leg falls back to when
                # it would short across another of its own block's pads on
                # the primary plane (klayout-tools#1168) -- one via2 hop
                # above the met1 primary on sky130.
                routing["cross_block_layer_role"] = CROSS_BLOCK_LAYER_ROLE
            request["routing"] = routing
        path = self._write_json(request_name, request)
        # Exit 3 is `gen-compose`'s documented *partial success*: every block
        # placed, some declared net left unrouted. That is the expected
        # outcome here (see this module's docstring), not a failure.
        report = json.loads(
            self._run(
                ["gen-compose", path.name, "--format", "json"],
                ok_returncodes=(0, 3),
            )
        )
        self._write_json(request_name.replace("request", "response"), report)
        return report


def group_size(report: dict[str, Any]) -> tuple[float, float]:
    bbox = report["bbox_um"]
    return bbox["x1"] - bbox["x0"], bbox["y1"] - bbox["y0"]


def block_connectivity(block: dict[str, Any]) -> list[dict[str, Any]]:
    """Every net inside one block, as a `connectivity[]` entry.

    Declared in full -- including the many-pin supply and internal nets the
    phase-2 point-to-point router cannot draw -- so the composition report's
    `nets[]`/`unrouted_nets[]` split is an honest, machine-generated record of
    exactly how much of the schematic's topology is physically wired.
    """
    nets: dict[str, list[dict[str, str]]] = {}
    for group in block["groups"]:
        if group["kind"] == "stdcell":
            # A library cell's pin *geometry* is not exposed by any `klt`
            # read verb, so its nets cannot be named as {block, port} pairs.
            continue
        for member in group["members"]:
            for port, net in member.get("ports", {}).items():
                nets.setdefault(net, []).append({"block": group["id"], "port": port})
    return [
        {"net": net, "pins": pins}
        for net, pins in sorted(nets.items())
        if len(pins) >= 2
    ]


def build(
    plan: dict[str, Any],
    builder: Builder,
    supplies: list[str] | None = None,
) -> dict[str, Any]:
    """Draw and compose the whole plan; return a build summary.

    `supplies` is the schematic's own `*.iopin` declaration (see
    `supply_nets`), passed in by `main` rather than stored on the plan so
    `plan.json` -- committed evidence -- keeps exactly the shape it had
    before issue #548's levers.
    """
    summary: dict[str, Any] = {"blocks": [], "top": None}
    block_reports: list[dict[str, Any]] = []

    # Issue #548's per-net levers, derived once for the whole design (the
    # fanout ranking sums pins across blocks, so it cannot be per-block).
    supplies = supplies or []
    connectivity_by_block = {
        block["name"]: block_connectivity(block) for block in plan["blocks"]
    }
    fanout_nets: list[str] = []
    if builder.route and "fanout-plane" in builder.route_levers:
        fanout_nets = top_fanout_nets(
            connectivity_by_block, supplies, FANOUT_NET_LIMIT
        )
    if builder.route and builder.route_levers:
        summary["routing_levers"] = {
            "levers": sorted(builder.route_levers),
            "cross_block_layer_role": (
                CROSS_BLOCK_LAYER_ROLE
                if "cross-block-plane" in builder.route_levers
                else None
            ),
            "interior_channel_um": (
                INTERIOR_CHANNEL_UM
                if "interior-channel" in builder.route_levers
                else None
            ),
            "supply_layer_role": (
                SUPPLY_LAYER_ROLE if "supply-plane" in builder.route_levers else None
            ),
            "supply_nets": supplies if "supply-plane" in builder.route_levers else [],
            "fanout_layer_role": (
                FANOUT_LAYER_ROLE if "fanout-plane" in builder.route_levers else None
            ),
            "fanout_nets": fanout_nets,
        }

    for block in plan["blocks"]:
        reports: dict[str, dict[str, Any]] = {}
        for group in block["groups"]:
            if group["kind"] in ("mos_array", "res_array"):
                reports[group["id"]] = builder.gen_group(group)
            elif group["kind"] == "mim_cap":
                reports[group["id"]] = builder.draw_mim_cap(group)
            elif group["kind"] == "stdcell":
                reports[group["id"]] = builder.library_cell(group)
            else:  # pragma: no cover - guarded by plan_block
                raise PlanError(f"unknown group kind {group['kind']!r}")

        stdcell_only = all(g["kind"] == "stdcell" for g in block["groups"])
        if stdcell_only:
            # One abutted standard-cell row on the site grid. One row, not a
            # stacked array, because `gen-compose`'s explicit placement has no
            # orientation control -- and unmirrored stacked rows would abut a
            # VPWR rail against a VGND rail (a supply short), which is not a
            # trade a layout may silently make.
            origins: dict[str, dict[str, float]] = {}
            x = 0.0
            for group in block["groups"]:
                report = reports[group["id"]]
                width = (
                    report["bbox_um"]["x1"]
                    - report["bbox_um"]["x0"]
                    - 2 * STDCELL_BBOX_OVERHANG_UM
                )
                origins[group["id"]] = {"x": round(x, 3), "y": 0.0}
                x += width
            size = (x, STDCELL_ROW_UM)
        else:
            sizes = [
                (group["id"], *group_size(reports[group["id"]]))
                for group in block["groups"]
            ]
            origins, size = shelf_pack(
                sizes, BLOCK_TARGET_WIDTH_UM, GROUP_SPACING_UM
            )

        blocks_field = [
            {"id": group["id"], "generator_report": reports[group["id"]]}
            for group in block["groups"]
        ]
        connectivity = connectivity_by_block[block["name"]]
        if builder.route and "supply-plane" in builder.route_levers:
            connectivity = with_supply_plane(
                connectivity, supplies, SUPPLY_LAYER_ROLE
            )
        if fanout_nets:
            connectivity = with_fanout_plane(
                connectivity, fanout_nets, FANOUT_LAYER_ROLE
            )
        report = builder.compose(
            f"compose.{block['name']}.request.json",
            blocks_field,
            origins,
            block["cell_name"],
            connectivity,
        )
        summary["blocks"].append(
            {
                "name": block["name"],
                "cell_name": block["cell_name"],
                "group_count": len(block["groups"]),
                "device_count": block["device_count"],
                "declared_nets": len(connectivity),
                "routed_nets": sum(1 for n in report.get("nets", []) if n.get("routed")),
                # Without a `routing` block the request carries no
                # `connectivity[]` at all, so every declared net is unrouted by
                # construction rather than by the router's own report.
                "unrouted_nets": (
                    len(report.get("unrouted_nets", []))
                    if builder.route
                    else len(connectivity)
                ),
                "routing_notes": report.get("drc_hints", {}).get("notes", []),
                "bbox_um": report["bbox_um"],
                "size_um": [round(size[0], 3), round(size[1], 3)],
            }
        )
        block_reports.append(report)

    # Top level: place the four composed block cells. A `gen-compose`
    # response is not itself a valid composition *input* (it carries no
    # `generator` field and no `ports[]`), so the inline block report is
    # rebuilt from it -- see layout/pll/README.md's friction section.
    sizes = [
        (
            report["cell_name"],
            report["bbox_um"]["x1"] - report["bbox_um"]["x0"],
            report["bbox_um"]["y1"] - report["bbox_um"]["y0"],
        )
        for report in block_reports
    ]
    origins, size = shelf_pack(sizes, sum(s[1] for s in sizes) + 1.0, BLOCK_SPACING_UM)
    top_blocks = [
        {
            "id": report["cell_name"],
            "generator_report": {
                "generator": "gen-compose",
                "cell_name": report["cell_name"],
                "gds_path": report["gds_path"],
                "bbox_um": report["bbox_um"],
                "ports": [],
            },
        }
        for report in block_reports
    ]
    top = builder.compose(
        "compose.top.request.json",
        top_blocks,
        origins,
        plan["top_cell_name"],
        connectivity=[],
    )
    summary["top"] = {
        "cell_name": top["cell_name"],
        "gds_path": top["gds_path"],
        "bbox_um": top["bbox_um"],
        "size_um": [round(size[0], 3), round(size[1], 3)],
    }
    return summary


def plan_totals(plan: dict[str, Any]) -> dict[str, int]:
    """Device totals per primitive kind, for the record's cross-check table."""
    totals: dict[str, int] = {}
    for block in plan["blocks"]:
        for group in block["groups"]:
            totals[group["kind"]] = totals.get(group["kind"], 0) + group["count"]
    return totals


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--netlist", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--klt", default="klt")
    ap.add_argument("--pdk", default="sky130A")
    ap.add_argument(
        "--plan-only",
        action="store_true",
        help="write plan.json and stop (no PDK or klt needed)",
    )
    ap.add_argument(
        "--no-route",
        action="store_true",
        help="record the declared connectivity but do not run gen-compose's router",
    )
    ap.add_argument(
        "--route-levers",
        default="all",
        metavar="LEVERS",
        help=(
            "which routing levers the routed build requests from klt, as a "
            "comma-separated subset of cross-block-plane, interior-channel, "
            "supply-plane, fanout-plane (issue #548), or 'all' (default) or "
            "'none'. The unrouted (--no-route) build is unaffected by this "
            "flag whichever way it is spelled"
        ),
    )
    ap.add_argument(
        "--print-blocks",
        action="store_true",
        help=(
            "print '<block> <cell_name> <stdcell|-->' per block on stdout "
            "(for the shell driver's per-block klt calls)"
        ),
    )
    ap.add_argument(
        "--emit-lvs-reference",
        action="store_true",
        help=(
            "also write reference.spice (the schematic netlist with its top "
            "level's .subckt/.ends uncommented -- see lvs_reference_text) "
            "for use as a `klt lvs` reference netlist"
        ),
    )
    args = ap.parse_args(argv)

    netlist_text = args.netlist.read_text()
    plan = build_plan(netlist_text)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    if args.emit_lvs_reference:
        (args.out_dir / "reference.spice").write_text(lvs_reference_text(netlist_text))
    if args.print_blocks:
        for block in plan["blocks"]:
            has_stdcells = any(g["kind"] == "stdcell" for g in block["groups"])
            print(
                f"{block['name']} {block['cell_name']} "
                f"{'stdcell' if has_stdcells else '--'}"
            )
    if args.plan_only:
        return 0

    builder = Builder(
        args.klt,
        args.pdk,
        args.out_dir,
        route=not args.no_route,
        route_levers=parse_route_levers(args.route_levers),
    )
    summary = build(
        plan, builder, supplies=supply_nets(netlist_text, plan["top_subckt"])
    )
    summary["totals"] = plan_totals(plan)
    (args.out_dir / "build.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["totals"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
