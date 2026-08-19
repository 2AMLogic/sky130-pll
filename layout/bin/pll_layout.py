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
#: allows -- one violation per such device, and the *only* violation class
#: this flow's output produces. Used by the record to assert exactly that.
LI1_MIN_SPACE_UM = 0.17

#: Bottom-plate (met3) overhang beyond the capm top plate, per side (um).
#: The schematic's W/L is the *capacitor* size, i.e. the capm plate, since
#: that is the layer the extraction deck measures the area of; met3 is drawn
#: larger so the plate is fully landed.
CAP_BOTTOM_MARGIN_UM = 0.2

#: Standard-cell library the divider's cells come from, and its row height /
#: site width (sky130 high-density library). Cells are placed in one
#: abutted row on the site grid -- see `plan_block` for why one row.
STDCELL_LIB = "sky130_fd_sc_hd"
STDCELL_SITE_UM = 0.46
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
        count = len(members)
        rows, cols = factor_rows_cols(count)
        group_id = f"{block_name}_{flavor}_w{_slug(w_um)}_l{_slug(l_um)}"
        groups.append(
            {
                "id": group_id,
                "kind": "mos_array",
                "generator": "mos_array",
                "params": {
                    "w_um": w_um,
                    "l_um": l_um,
                    "rows": rows,
                    "cols": cols,
                    "dummy": 0,
                    "flavor": flavor,
                    # A matched array is only meaningful common-centroid when
                    # its device count is even; an odd count cannot be paired,
                    # so it falls back to plain row-major order.
                    "topology": "common_centroid" if count % 2 == 0 else "array",
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
    def __init__(self, klt: str, pdk: str, out_dir: Path, route: bool) -> None:
        self.klt = klt
        self.pdk = pdk
        self.out_dir = out_dir
        self.route = route
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
        """Draw one `klt gen` group (mos_array / res_array)."""
        cell = group["id"]
        report = json.loads(
            self._run(
                [
                    "gen",
                    group["generator"],
                    "--pdk",
                    self.pdk,
                    "--params",
                    json.dumps(group["params"]),
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
            request["routing"] = {
                "layer_role": ROUTING_LAYER_ROLE,
                "width_um": ROUTING_WIDTH_UM,
            }
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


def build(plan: dict[str, Any], builder: Builder) -> dict[str, Any]:
    """Draw and compose the whole plan; return a build summary."""
    summary: dict[str, Any] = {"blocks": [], "top": None}
    block_reports: list[dict[str, Any]] = []

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
        connectivity = block_connectivity(block)
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
        "--print-blocks",
        action="store_true",
        help=(
            "print '<block> <cell_name> <stdcell|-->' per block on stdout "
            "(for the shell driver's per-block klt calls)"
        ),
    )
    args = ap.parse_args(argv)

    plan = build_plan(args.netlist.read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    if args.print_blocks:
        for block in plan["blocks"]:
            has_stdcells = any(g["kind"] == "stdcell" for g in block["groups"])
            print(
                f"{block['name']} {block['cell_name']} "
                f"{'stdcell' if has_stdcells else '--'}"
            )
    if args.plan_only:
        return 0

    builder = Builder(args.klt, args.pdk, args.out_dir, route=not args.no_route)
    summary = build(plan, builder)
    summary["totals"] = plan_totals(plan)
    (args.out_dir / "build.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["totals"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
