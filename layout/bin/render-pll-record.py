#!/usr/bin/env python3
"""Render layout/pll/reports/<record-id>/record.md from the `klt` JSON
envelopes and extracted netlists `run-pll-layout-flow.sh` just produced.

Same evidence-record contract as `render-record.py` (the trivial-cell flow's
renderer this is modelled on): the record is the deliverable, this script is
only its typesetter -- and it exits non-zero, *after* writing the record, if
any verdict it asserts does not hold, so a silent regression is a FAIL rather
than an unnoticed one.

What it asserts, and why those are the honest claims for issue #16:

* **Coverage** -- every device card in the schematic netlist drew a layout
  primitive (no device silently skipped).
* **Device set** -- for each device-level block, the `(class, W, L)` multiset
  `klt extract` reads back out of the drawn GDS equals the schematic's own,
  and each drawn passive's extracted value equals the value its schematic
  dimensions predict.
* **Standard-cell block** -- the divider's composed cell instantiates exactly
  the schematic's 29 standard-cell instances, each from the library cell the
  schematic names.
* **Supply flavor** -- every MOS device is a sky130 1.8 V core device
  (DR-001); no 3.3 V-class device is drawn.
* **DRC** -- reported, **not** asserted clean (DRC-clean closure is #17). The
  assertion is narrower and more useful: the only rule the deck fires is the
  one known `klt gen` limitation this flow documents, and it fires exactly
  once per minimum-gate-length device -- so a *new* violation class appearing
  is a FAIL.

It deliberately does **not** assert LVS: the shipped layout carries no
inter-device routing (see the record's own "What this layout is not"
section), so an LVS comparison against it could only ever report mismatch,
and asserting a mismatch would dress a known gap up as a passing check.
Since issue #18, a `klt lvs` comparison **is** attempted -- against the
routed routing-spot-check build, the one stream in the record with any
topology to compare at all -- and its result is reported verbatim (never
asserted "PASS"), so a still-substantial mismatch is recorded as evidence of
how much routing remains, not silently omitted.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_BIN_DIR = Path(__file__).resolve().parent
if str(_BIN_DIR) not in sys.path:
    sys.path.insert(0, str(_BIN_DIR))

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pll_layout import (  # noqa: E402
    LI1_MIN_SPACE_UM,
    MIM_AREA_CAP_F_UM2,
    MIM_PERIM_CAP_F_UM,
    SHEET_RHO_OHM_SQ,
    read_cards,
)
from render_common import git_provenance, klt_info, load_json  # noqa: E402

MOS_CARD_RE = re.compile(r"^M\S+\s+(?:\S+\s+){4}(\S+)\s+L=([\d.eE+-]+)U\s+W=([\d.eE+-]+)U")
RES_CARD_RE = re.compile(r"^R\S+\s+(?:\S+\s+){3}([\d.eE+-]+)\s+(\S+)")
CAP_CARD_RE = re.compile(r"^C\S+\s+(?:\S+\s+){2}([\d.eE+-]+)\s+(\S+)")

_load = load_json  # local alias, kept short for the calls below


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-15)


def extracted_sets(spice: str) -> dict[str, Counter]:
    """Multisets of what `klt extract` read back out of a drawn cell."""
    mos: Counter = Counter()
    res: Counter = Counter()
    cap: Counter = Counter()
    for line in spice.splitlines():
        match = MOS_CARD_RE.match(line)
        if match:
            klass, length, width = match.group(1), float(match.group(2)), float(match.group(3))
            mos[(klass, round(width, 6), round(length, 6))] += 1
            continue
        match = RES_CARD_RE.match(line)
        if match:
            res[(match.group(2), round(float(match.group(1)), 6))] += 1
            continue
        match = CAP_CARD_RE.match(line)
        if match:
            cap[(match.group(2), float(match.group(1)))] += 1
    return {"mos": mos, "res": res, "cap": cap}


def planned_sets(block: dict[str, Any]) -> dict[str, Counter]:
    """The same multisets, predicted from the schematic-derived plan."""
    mos: Counter = Counter()
    res: Counter = Counter()
    cap: Counter = Counter()
    for group in block["groups"]:
        params = group["params"]
        if group["kind"] == "mos_array":
            mos[(params["flavor"], round(params["w_um"], 6), round(params["l_um"], 6))] += group[
                "count"
            ]
        elif group["kind"] == "res_array":
            ohms = params["length_um"] / params["width_um"] * SHEET_RHO_OHM_SQ[params["flavor"]]
            res[(f"res_{params['flavor']}_po", round(ohms, 6))] += group["count"]
        elif group["kind"] == "mim_cap":
            # Two-term MiM model, matching the curated deck's own: plate area
            # plus a perimeter/fringe term. The area term alone undercounts a
            # small plate by up to ~15%, which is what `klt extract` reported
            # before the pin bumped in issue #46.
            width, length = params["w_um"], params["l_um"]
            farads = width * length * MIM_AREA_CAP_F_UM2 + 2 * (
                width + length
            ) * MIM_PERIM_CAP_F_UM
            cap[("sky130_fd_pr__model__cap_mim", farads)] += group["count"]
    return {"mos": mos, "res": res, "cap": cap}


#: How a `gen-compose` leg's own `reason` string is bucketed for the record's
#: routing spot-check table. Each entry is (substring, label); the first
#: matching substring wins, so order matters. The strings are the router's own
#: (`legs[].reason` in a compose response), not this script's paraphrase.
ROUTE_REASON_BUCKETS = (
    (
        "crosses already-routed net",
        "would cross an already-drawn route (the router's own route-vs-route "
        "collision check, klayout-tools#1057)",
    ),
    (
        "bare-poly gate",
        "terminates on a bare-poly gate with no contacted landing pad "
        "(`params.gate_contact`, klayout-tools#492 -- this flow does not opt in)",
    ),
    (
        "through unrelated block",
        "backbone would plough through an unrelated block's bbox (no routing "
        "channel between abutted groups)",
    ),
    (
        "through its own pin's block",
        "backbone would plough through its own pin's block (no routing channel "
        "inside a matched array)",
    ),
)


def _reason_bucket(reason: str | None) -> str:
    for needle, label in ROUTE_REASON_BUCKETS:
        if needle in (reason or ""):
            return label
    return "other"


def route_stats(spot_dir: Path) -> dict[str, Any]:
    """Aggregate what the routed spot-check's own compose responses report.

    Everything here is read back out of `klt gen-compose`'s responses -- net
    `status` (`"routed"`/`"partial"`/`"unrouted"`), per-leg `routed`, and the
    router's own `reason` string for a leg it declined to draw. Nothing is
    inferred from the drawn stream, which the flow deletes; the extraction
    cross-check below the narrative is what speaks for the geometry.
    """
    status: Counter = Counter()
    reasons: Counter = Counter()
    legs = drawn = 0
    for path in sorted(spot_dir.glob("compose.*.response.json")):
        for net in _load(path).get("nets", []) or []:
            status[net.get("status") or ("routed" if net.get("routed") else "unrouted")] += 1
            for leg in net.get("legs") or []:
                legs += 1
                if leg.get("routed"):
                    drawn += 1
                else:
                    reasons[_reason_bucket(leg.get("reason"))] += 1
    return {"status": status, "legs": legs, "drawn_legs": drawn, "reasons": reasons}


def _cap_sets_match(planned: Counter, extracted: Counter) -> bool:
    """Compare capacitor multisets on value with a float tolerance."""
    if sum(planned.values()) != sum(extracted.values()):
        return False
    remaining = list(extracted.elements())
    for klass, value in planned.elements():
        for index, (other_class, other_value) in enumerate(remaining):
            if other_class == klass and _close(value, other_value):
                remaining.pop(index)
                break
        else:
            return False
    return not remaining


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--record-id", required=True)
    ap.add_argument("--repo-root", required=True, type=Path)
    ap.add_argument("--klt", required=True)
    ap.add_argument("--pdk-variant", required=True)
    ap.add_argument("--netlist", required=True, type=Path)
    return ap.parse_args()


# --- compute: derive `checks` (and the device-set rows the record's own
# device-set table needs) from the loaded `klt` JSON evidence. Each
# `_check_*` helper below owns exactly one of the six assertions `main()`'s
# docstring-adjacent module doc lists (coverage, supply flavor, per-block
# device set, standard-cell instantiation, top hierarchy, DRC); `_build_checks`
# is a flat, branch-free sequence over them. -----------------------------


def _check_coverage(
    plan: dict[str, Any], cards: dict[str, list[dict[str, Any]]]
) -> tuple[str, bool, str]:
    coverage_ok = True
    coverage_rows: list[tuple[str, int, int]] = []
    for block in plan["blocks"]:
        drawn = sum(group["count"] for group in block["groups"])
        schematic = len(cards[block["name"]])
        coverage_rows.append((block["name"], schematic, drawn))
        coverage_ok = coverage_ok and drawn == schematic
    return (
        "Every device card in the schematic netlist drew a layout primitive",
        coverage_ok,
        ", ".join(f"{name}: {s} -> {d}" for name, s, d in coverage_rows),
    )


def _check_supply_flavor(cards: dict[str, list[dict[str, Any]]]) -> tuple[str, bool, str]:
    mos_models = {
        card["model"]
        for block_cards in cards.values()
        for card in block_cards
        if "fet" in card["model"]
    }
    flavor_ok = bool(mos_models) and all(model.endswith("_01v8") for model in mos_models)
    return (
        "Every MOS device is a sky130 1.8 V core device (DR-001) -- no "
        "3.3 V-class device is drawn",
        flavor_ok,
        ", ".join(sorted(mos_models)),
    )


def _check_device_sets(
    out_dir: Path, plan: dict[str, Any]
) -> tuple[list[tuple[str, bool, str]], list[dict[str, Any]]]:
    checks: list[tuple[str, bool, str]] = []
    device_rows: list[dict[str, Any]] = []
    for block in plan["blocks"]:
        name = block["name"]
        planned = planned_sets(block)
        if not any(planned.values()):
            continue
        spice_path = out_dir / f"{block['cell_name']}.extract.spice"
        extracted = extracted_sets(spice_path.read_text())
        mos_ok = planned["mos"] == extracted["mos"]
        res_ok = planned["res"] == extracted["res"]
        cap_ok = _cap_sets_match(planned["cap"], extracted["cap"])
        device_rows.append(
            {
                "block": name,
                "planned": planned,
                "extracted": extracted,
                "ok": mos_ok and res_ok and cap_ok,
            }
        )
        checks.append(
            (
                f"`{name}`: the `(class, W, L)` device multiset extracted from "
                "the drawn GDS equals the schematic's",
                mos_ok and res_ok and cap_ok,
                f"MOS {sum(planned['mos'].values())}, "
                f"R {sum(planned['res'].values())}, "
                f"C {sum(planned['cap'].values())}",
            )
        )
    return checks, device_rows


def _check_stdcell(out_dir: Path, plan: dict[str, Any]) -> list[tuple[str, bool, str]]:
    stdcell_blocks = [
        block
        for block in plan["blocks"]
        if any(group["kind"] == "stdcell" for group in block["groups"])
    ]
    checks: list[tuple[str, bool, str]] = []
    for block in stdcell_blocks:
        cells_block = _load(out_dir / f"cells.{block['name']}.json")
        top = next(entry for entry in cells_block["cells"] if entry["is_top"])
        expected = {
            f"{group['id']}__{group['params']['cell']}"
            for group in block["groups"]
            if group["kind"] == "stdcell"
        }
        actual = set(top["children"])
        stdcell_detail = (
            f"{block['cell_name']}: {top['instances']} instances, "
            f"{len(actual)} distinct library cells placed"
        )
        checks.append(
            (
                f"`{block['name']}`: the composed cell instantiates exactly the "
                f"schematic's {len(expected)} standard-cell instances, each from "
                "the library cell the schematic names",
                expected == actual and top["instances"] == len(expected),
                stdcell_detail,
            )
        )
    return checks


def _check_top_hierarchy(cells_top: dict[str, Any], plan: dict[str, Any]) -> tuple[str, bool, str]:
    top_cell = next(entry for entry in cells_top["cells"] if entry["is_top"])
    expected_children = {
        f"{block['cell_name']}__{block['cell_name']}" for block in plan["blocks"]
    }
    top_ok = set(top_cell["children"]) == expected_children
    return (
        f"`{plan['top_cell_name']}` instantiates all "
        f"{len(expected_children)} block cells",
        top_ok,
        ", ".join(sorted(top_cell["children"])),
    )


def _check_drc(plan: dict[str, Any], drc: dict[str, Any]) -> tuple[str, bool, str]:
    min_length_devices = sum(
        group["count"]
        for block in plan["blocks"]
        for group in block["groups"]
        if group["kind"] == "mos_array" and group["params"]["l_um"] < LI1_MIN_SPACE_UM
    )
    rule_counts = drc.get("rule_counts", {})
    drc_ok = set(rule_counts) == {"li1.space.1"} and rule_counts.get(
        "li1.space.1"
    ) == min_length_devices
    return (
        "DRC fires exactly one rule class -- the documented `klt gen` "
        "minimum-gate-length limitation -- once per minimum-length device "
        f"({min_length_devices} of them), and nothing else",
        drc_ok,
        f"status={drc.get('status')}, rule_counts={rule_counts}",
    )


def _build_checks(
    out_dir: Path,
    plan: dict[str, Any],
    cards: dict[str, list[dict[str, Any]]],
    cells_top: dict[str, Any],
    drc: dict[str, Any],
) -> tuple[list[tuple[str, bool, str]], list[dict[str, Any]]]:
    """The record's `checks` list and per-block device-set rows.

    Same six assertions, same order, as the pre-split `main()` built inline;
    only the "how" moved, one `_check_*` helper per assertion.
    """
    checks: list[tuple[str, bool, str]] = [
        _check_coverage(plan, cards),
        _check_supply_flavor(cards),
    ]
    device_checks, device_rows = _check_device_sets(out_dir, plan)
    checks.extend(device_checks)
    checks.extend(_check_stdcell(out_dir, plan))
    checks.append(_check_top_hierarchy(cells_top, plan))
    checks.append(_check_drc(plan, drc))
    return checks, device_rows


def _load_spot_check(out_dir: Path) -> dict[str, Any] | None:
    """The routing spot-check's evidence, or `None` if the flow skipped it."""
    spot_path = out_dir / "route-spot-check" / "build.json"
    if not spot_path.is_file():
        return None
    # A node the extractor labels with more than one declared net name is
    # a *drawn short*: two nets the schematic keeps apart ended up on one
    # electrical node. Counted straight out of the routed run's own
    # extracted netlist, so the claim is the extractor's, not this
    # script's.
    routed_spice = (out_dir / "route-spot-check" / "pll_top.spice").read_text()
    merged = sorted({m for m in re.findall(r"[A-Za-z_0-9]+(?:\|[A-Za-z_0-9]+)+", routed_spice)})
    lvs_path = out_dir / "route-spot-check" / "lvs.json"
    return {
        "build": _load(spot_path),
        "drc": _load(out_dir / "route-spot-check" / "drc.json"),
        "extract": _load(out_dir / "route-spot-check" / "extract.json"),
        "merged_nodes": merged,
        "routing": route_stats(out_dir / "route-spot-check"),
        "lvs": _load(lvs_path) if lvs_path.is_file() else None,
    }


# --- render: each `_render_*` helper appends one `## `-headed markdown
# section (or, for the header, the record's title + intro) to the shared
# `lines` list via `a = lines.append` -- the same convention `render-record.py`
# uses. `main()` calls them in the record's own section order. -------------


def _render_header(a: Any, args: argparse.Namespace, netlist_display: str) -> None:
    a(f"# PLL layout record: {args.record_id}")
    a("")
    a(
        "Device-level layout of the closed-loop PLL schematic "
        f"(`{netlist_display}`), drawn by `layout/bin/run-pll-layout-flow.sh` "
        "(issue #16). Read this file first; everything else in this directory "
        "is the raw `klt` evidence it summarises."
    )
    a("")


def _render_verdict(a: Any, checks: list[tuple[str, bool, str]], all_pass: bool) -> None:
    a("## Overall verdict: " + ("PASS" if all_pass else "FAIL"))
    a("")
    for desc, ok, detail in checks:
        a(f"- [{'x' if ok else ' '}] {desc} -- {detail}")
    a("")


def _render_layout_is(a: Any, plan: dict[str, Any], build: dict[str, Any], out_dir: Path) -> None:
    a("## What this layout is")
    a("")
    a(
        "A **device-level floorplan**: every device the schematic declares is "
        "physically drawn, at the schematic's own W/L, in a matched array "
        "grouped by `(flavor, W, L)`, and the four blocks are composed into "
        f"one `{plan['top_cell_name']}` cell. The device set is derived from "
        "the schematic netlist at build time -- nothing about it is typed in "
        "by hand -- which is what makes the device-set checks above "
        "reproducible rather than declarative."
    )
    a("")
    if (out_dir / "renders" / "overview.png").is_file():
        a("![composed PLL layout](renders/overview.png)")
        a("")
        a(
            "(All layers, `klt render`. Left to right in the strip along the "
            "top: the divider's standard-cell row; below it the PFD/charge "
            "pump's device groups and its 300 um bias resistor; right: the "
            "loop filter's three MiM capacitors; far right: the VCO's ring "
            "and buffer devices.)"
        )
        a("")
    a("| Block | Cell | Schematic devices | Groups | Placed size (um) |")
    a("| --- | --- | --- | --- | --- |")
    for entry in build["blocks"]:
        size = entry["size_um"]
        a(
            f"| `{entry['name']}` | `{entry['cell_name']}` | "
            f"{entry['device_count']} | {entry['group_count']} | "
            f"{size[0]} x {size[1]} |"
        )
    top_size = build["top"]["size_um"]
    a(
        f"| **top** | `{build['top']['cell_name']}` | "
        f"{sum(e['device_count'] for e in build['blocks'])} | "
        f"{len(build['blocks'])} | {top_size[0]} x {top_size[1]} |"
    )
    a("")


def _render_layout_is_not(a: Any, build: dict[str, Any], drc: dict[str, Any]) -> None:
    a("## What this layout is not")
    a("")
    a(
        "- **Not routed.** No inter-device interconnect is drawn. The full "
        "schematic topology *is* recorded, machine-derived, in `plan.json` "
        "(every group member carries its schematic device name and its "
        "port-to-net mapping), and "
        f"{sum(e['declared_nets'] for e in build['blocks'])} nets are declared "
        "across the four blocks -- but the composed GDS carries no wires "
        "between them. See the routing spot-check below for why."
    )
    a(
        "- **Not DRC-clean.** "
        f"{drc.get('violation_count')} violations, all of one rule class "
        "(see the DRC check above); DRC-clean closure is issue #17."
    )
    a(
        "- **Not LVS-clean.** The shipped stream carries no routing, so no "
        "`klt lvs` run is attempted against it (a foregone mismatch is not "
        "evidence). `klt lvs` *is* run against the routed routing-spot-check "
        "build below, and reports a large, honestly-recorded mismatch -- see "
        "the spot-check's own LVS section for the counts and why. LVS "
        "closure is issue #18."
    )
    a(
        "- **Not a verified circuit.** Nothing here is a claim against "
        "`spec/target-spec.md`; no simulation was run from this layout "
        "(PEX is issue #21)."
    )
    a("")


def _render_routing_spotcheck(
    a: Any,
    spot: dict[str, Any],
    build: dict[str, Any],
    drc: dict[str, Any],
    extract_top: dict[str, Any],
) -> None:
    """The "why the shipped layout is unrouted" section.

    Only called when `spot` is not `None` (the caller's `if spot:` guard) --
    the largest single markdown section, so it gets its own helper per the
    issue's proposed approach.
    """
    spot_blocks = spot["build"]["blocks"]
    routed = sum(entry["routed_nets"] for entry in spot_blocks)
    declared = sum(entry["declared_nets"] for entry in spot_blocks)
    a("## Routing spot-check (why the shipped layout is unrouted)")
    a("")
    merged = spot["merged_nodes"]
    merged_nets = sum(node.count("|") + 1 for node in merged)
    routing = spot["routing"]
    status = routing["status"]
    partial = status.get("partial", 0)
    a(
        "The same build was re-run with `klt gen-compose`'s router enabled "
        f"(`route-spot-check/`). Of {declared} declared nets it drew "
        f"{routed} in full and {partial} in part, leaving "
        f"{status.get('unrouted', 0)} with no geometry at all -- "
        f"{routing['drawn_legs']} of {routing['legs']} two-pin legs drawn. "
        "The router declined the rest, with its own reason per leg:"
    )
    a("")
    a("| Why a leg was not drawn | Legs |")
    a("| --- | --- |")
    for label, count in routing["reasons"].most_common():
        a(f"| {label} | {count} |")
    a("")
    if merged:
        node_word = "node" if len(merged) == 1 else "nodes"
        a(
            f"**The drawn geometry still shorts {len(merged)} {node_word}.** "
            "The routed run's own extracted netlist collapses "
            f"{merged_nets} distinct declared net names onto "
            f"{len(merged)} electrical {node_word}:"
        )
        a("")
        for node in merged:
            a(f"- `{node}`")
        a("")
        a(
            "That is why the shipped stream is still the unrouted one: a "
            "layout that shorts nets the schematic keeps apart is worse "
            "than one with no wires, and nothing downstream (#17's DRC "
            "closure, #18's LVS closure) can be argued from it. The "
            "residual short survives the router's own route-vs-route check "
            "(which this `klt` pin does have, and which fires on the legs "
            "counted in the table above); it is a coverage gap in that "
            "check, reproduced on `klt`'s own default generator output and "
            "filed upstream as "
            "[klayout-tools#1197](https://github.com/2AMLogic/klayout-tools/issues/1197)."
        )
    else:
        a(
            "**No drawn short:** the routed run's extracted netlist carries "
            "no multi-label node, so nothing the router drew merged two "
            "declared nets. The shipped stream is still the unrouted one "
            "because most nets remain undrawn (see the table above), not "
            "because the drawn ones are wrong."
        )
    a("")
    a(
        f"Its DRC reports {spot['drc'].get('violation_count')} "
        f"violations ({spot['drc'].get('rule_counts')}) against "
        f"{drc.get('violation_count')} for the unrouted build, and its "
        f"extraction finds {spot['extract'].get('net_count')} nets against "
        f"{extract_top.get('net_count')} for the unrouted build. Most of "
        "that difference is the routing doing its job -- each drawn leg "
        "merges two device pads that the unrouted stream counts as two "
        "separate nets -- which is why the multi-label node count above, "
        "not the net-count delta, is what identifies a short."
    )
    a("")
    a("Per-block routing outcome from the spot-check:")
    a("")
    a("| Block | Declared nets | Fully routed | Not fully routed |")
    a("| --- | --- | --- | --- |")
    for entry in spot_blocks:
        a(
            f"| `{entry['name']}` | {entry['declared_nets']} | "
            f"{entry['routed_nets']} | {entry['unrouted_nets']} |"
        )
    a("")
    a(
        "(The spot-check's own GDS streams are deleted by the flow after "
        "its DRC/extract run -- the JSON envelopes are the evidence, and "
        "`run-pll-layout-flow.sh` regenerates the streams on demand.)"
    )
    a("")
    lvs = spot["lvs"]
    a("### LVS (spot-check)")
    a("")
    if lvs is None:
        a(
            "`klt lvs` was not run for this record (no "
            "`route-spot-check/lvs.json`)."
        )
    elif "error" in lvs:
        a(
            "`klt lvs` itself errored rather than returning a comparison "
            f"-- `{lvs['error'].get('message')}`."
        )
    else:
        counts = lvs.get("counts", {})
        nets = counts.get("nets", {})
        devices = counts.get("devices", {})
        a(
            f"`klt lvs` compared the spot-check's routed "
            f"`{build['top']['cell_name']}` against the authored schematic "
            "(`reference.spice`, the same netlist `pll_layout.py` derives "
            "the plan from, with its top "
            "level's `.subckt`/`.ends` uncommented so `klt lvs`'s SPICE "
            "reader recognises it -- both sides flattened first, since "
            "this flow's composed block names (`pll_pfd_cp`, ...) differ "
            "from the schematic's own subcircuit names (`pfd_cp`, ...) "
            "and `klt lvs` does not resolve that across un-flattened "
            "circuit boundaries)."
        )
        a("")
        a(
            f"**Status: `{lvs.get('status')}`, "
            f"{lvs.get('mismatch_count')} mismatches** -- "
            f"nets {nets.get('matched', 0)}/{nets.get('reference', 0)} "
            f"reference nets matched ({nets.get('layout', 0)} in the "
            "layout), devices "
            f"{devices.get('matched', 0)}/{devices.get('reference', 0)} "
            f"reference devices matched ({devices.get('layout', 0)} in "
            "the layout)."
        )
        a("")
        cat_counts = lvs.get("category_counts", {})
        if cat_counts:
            a("| Mismatch category | Count |")
            a("| --- | --- |")
            for category, count in sorted(
                cat_counts.items(), key=lambda item: -item[1]
            ):
                a(f"| `{category}` | {count} |")
            a("")
        a(
            "This is the expected shape of the result, not a surprise: "
            f"only {routing['drawn_legs']} of {routing['legs']} two-pin "
            "legs are drawn (see the table above), so almost every "
            "reference net and device is structurally unreachable from "
            "the layout side. `klt lvs` is run and its result recorded "
            "in full precisely so that claim rests on the tool's own "
            "comparison rather than on this record's own leg-reason "
            "tally -- per this repo's CLAUDE.md, a miss is recorded as a "
            "miss, never rounded up to \"clean.\" Full `klt lvs` closure "
            "(issue #18) needs the router's structural gaps above "
            "(chiefly the point-to-point router's inability to route a "
            "pin buried inside a matched device array) closed first, and "
            "klayout-tools#1197's residual same-block short fixed "
            "upstream before routing further is safe to attempt at all "
            "-- see `layout/pll/README.md`."
        )
        a("")


def _render_device_set(a: Any, device_rows: list[dict[str, Any]], out_dir: Path, plan: dict[str, Any]) -> None:
    a("## Device set: schematic vs. extracted")
    a("")
    a(
        "`klt extract` reads the drawn stream back into a netlist with no "
        "knowledge of the plan that produced it, so this table compares two "
        "independently-derived multisets."
    )
    a("")
    a("| Block | Kind | Schematic (from netlist) | Extracted (from GDS) | Match |")
    a("| --- | --- | --- | --- | --- |")
    for row in device_rows:
        for kind, label in (("mos", "MOS (class, W um, L um)"), ("res", "resistors (class, ohm)"), ("cap", "capacitors (class, F)")):
            planned = row["planned"][kind]
            extracted = row["extracted"][kind]
            if not planned and not extracted:
                continue
            ok = (
                _cap_sets_match(planned, extracted)
                if kind == "cap"
                else planned == extracted
            )
            a(
                f"| `{row['block']}` | {label} | "
                f"{sum(planned.values())}: {_fmt_counter(planned)} | "
                f"{sum(extracted.values())}: {_fmt_counter(extracted)} | "
                f"{'yes' if ok else '**NO**'} |"
            )
    a("")
    a(
        "The standard-cell block extracts as "
        f"{_stdcell_device_count(out_dir, plan)} transistors rather than its "
        "29 schematic instances -- those are the library cells' own internal "
        "devices, which is what a standard-cell block's layout *is*; the "
        "instance-level check above is the one that compares like with like."
    )
    a("")


def _render_flow(a: Any) -> None:
    a("## Flow")
    a("")
    a("1. `pll_layout.py` parses the schematic netlist and derives the plan (`plan.json`).")
    a("2. `klt gen mos_array` / `klt gen res_array` per matched device group.")
    a("3. `klt draw` per MiM capacitor (plate geometry -- no generator exists; see README).")
    a("4. Each divider standard cell is taken from the PDK's own library GDS.")
    a("5. `klt gen-compose` (explicit placement) per block, then once more for the top cell.")
    a("6. `klt drc` / `klt extract` / `klt cells` over the result -- the evidence in this directory.")
    a("")


def _render_provenance(
    a: Any,
    args: argparse.Namespace,
    netlist_display: str,
    klt_version: str,
    pdk_info: dict[str, Any],
    drc: dict[str, Any],
    sha: str,
    branch: str,
    dirty: bool,
) -> None:
    a("## Provenance")
    a("")
    a(f"- Record ID: `{args.record_id}`")
    a(f"- Schematic netlist: `{netlist_display}`")
    a(f"- `klt` version: `{klt_version}` (see `layout/requirements.txt`)")
    a(f"- KLayout engine version: `{drc.get('provenance', {}).get('klayout_version')}`")
    a(f"- PDK: `{pdk_info.get('variant')}`, `{pdk_info.get('version')}`")
    a(
        "- PDK pin cross-check: compare `version` above against "
        "`sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself "
        "enforce the pin, so a mismatch is a manual reproducibility note."
    )
    a(f"- Repo state: `{sha}` on `{branch}`" + (" (dirty)" if dirty else ""))
    a("")


def _render_links(a: Any, build: dict[str, Any]) -> None:
    a("## Links")
    a("")
    a("- [`plan.json`](plan.json) -- the schematic-derived layout plan (device set + full port/net map)")
    a("- [`build.json`](build.json) -- placement/composition summary")
    a(f"- [`{build['top']['gds_path']}`]({build['top']['gds_path']}) -- **the layout**")
    a("- [`drc.json`](drc.json), [`extract.json`](extract.json), [`pll_top.spice`](pll_top.spice)")
    a("- [`cells.top.json`](cells.top.json) -- composed cell hierarchy")
    a("- [`renders/overview.png`](renders/overview.png), [`render.json`](render.json)")
    a("- [`report.md`](report.md) -- combined `klt report --format github-summary` rendering")
    a("")


def main() -> int:
    args = _parse_args()

    out_dir: Path = args.out_dir
    plan = _load(out_dir / "plan.json")
    build = _load(out_dir / "build.json")
    drc = _load(out_dir / "drc.json")
    extract_top = _load(out_dir / "extract.json")
    cells_top = _load(out_dir / "cells.top.json")
    cards = read_cards(args.netlist.read_text())

    checks, device_rows = _build_checks(out_dir, plan, cards, cells_top, drc)
    all_pass = all(ok for _, ok, _ in checks)

    klt_version, pdk_info = klt_info(args.klt, args.pdk_variant)
    sha, branch, dirty = git_provenance(args.repo_root, out_dir)
    spot = _load_spot_check(out_dir)

    try:
        netlist_display = args.netlist.resolve().relative_to(
            args.repo_root.resolve()
        ).as_posix()
    except ValueError:  # pragma: no cover - netlist outside the repo
        netlist_display = args.netlist.as_posix()

    lines: list[str] = []
    a = lines.append
    _render_header(a, args, netlist_display)
    _render_verdict(a, checks, all_pass)
    _render_layout_is(a, plan, build, out_dir)
    _render_layout_is_not(a, build, drc)
    if spot:
        _render_routing_spotcheck(a, spot, build, drc, extract_top)
    _render_device_set(a, device_rows, out_dir, plan)
    _render_flow(a)
    _render_provenance(a, args, netlist_display, klt_version, pdk_info, drc, sha, branch, dirty)
    _render_links(a, build)

    print("\n".join(lines))
    return 0 if all_pass else 1


def _fmt_counter(counter: Counter) -> str:
    if not counter:
        return "--"
    parts = []
    for key, count in sorted(counter.items(), key=lambda item: str(item[0])):
        rendered = "/".join(f"{part:g}" if isinstance(part, float) else str(part) for part in key)
        parts.append(f"{count}x {rendered}")
    return "; ".join(parts)


def _stdcell_device_count(out_dir: Path, plan: dict[str, Any]) -> int:
    total = 0
    for block in plan["blocks"]:
        if not any(group["kind"] == "stdcell" for group in block["groups"]):
            continue
        path = out_dir / f"extract.{block['cell_name']}.json"
        if path.is_file():
            total += _load(path).get("device_count", 0)
    return total


if __name__ == "__main__":
    sys.exit(main())
