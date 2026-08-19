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

It deliberately does **not** assert LVS: the composed layout carries no
inter-device routing (see the record's own "What this layout is not"
section), so an LVS comparison against the schematic could only ever report
mismatch, and asserting a mismatch would dress a known gap up as a passing
check.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
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
    SHEET_RHO_OHM_SQ,
    read_cards,
)
from scripts.git_status import is_dirty, run_git  # noqa: E402

MOS_CARD_RE = re.compile(r"^M\S+\s+(?:\S+\s+){4}(\S+)\s+L=([\d.eE+-]+)U\s+W=([\d.eE+-]+)U")
RES_CARD_RE = re.compile(r"^R\S+\s+(?:\S+\s+){3}([\d.eE+-]+)\s+(\S+)")
CAP_CARD_RE = re.compile(r"^C\S+\s+(?:\S+\s+){2}([\d.eE+-]+)\s+(\S+)")


def _load(path: Path) -> Any:
    with path.open() as handle:
        return json.load(handle)


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
            farads = params["w_um"] * params["l_um"] * MIM_AREA_CAP_F_UM2
            cap[("sky130_fd_pr__model__cap_mim", farads)] += group["count"]
    return {"mos": mos, "res": res, "cap": cap}


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--record-id", required=True)
    ap.add_argument("--repo-root", required=True, type=Path)
    ap.add_argument("--klt", required=True)
    ap.add_argument("--pdk-variant", required=True)
    ap.add_argument("--netlist", required=True, type=Path)
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    plan = _load(out_dir / "plan.json")
    build = _load(out_dir / "build.json")
    drc = _load(out_dir / "drc.json")
    extract_top = _load(out_dir / "extract.json")
    cells_top = _load(out_dir / "cells.top.json")
    cards = read_cards(args.netlist.read_text())

    checks: list[tuple[str, bool, str]] = []

    # --- coverage ----------------------------------------------------------
    coverage_ok = True
    coverage_rows: list[tuple[str, int, int]] = []
    for block in plan["blocks"]:
        drawn = sum(group["count"] for group in block["groups"])
        schematic = len(cards[block["name"]])
        coverage_rows.append((block["name"], schematic, drawn))
        coverage_ok = coverage_ok and drawn == schematic
    checks.append(
        (
            "Every device card in the schematic netlist drew a layout primitive",
            coverage_ok,
            ", ".join(f"{name}: {s} -> {d}" for name, s, d in coverage_rows),
        )
    )

    # --- supply flavor -----------------------------------------------------
    mos_models = {
        card["model"]
        for block_cards in cards.values()
        for card in block_cards
        if "fet" in card["model"]
    }
    flavor_ok = bool(mos_models) and all(model.endswith("_01v8") for model in mos_models)
    checks.append(
        (
            "Every MOS device is a sky130 1.8 V core device (DR-001) -- no "
            "3.3 V-class device is drawn",
            flavor_ok,
            ", ".join(sorted(mos_models)),
        )
    )

    # --- per-block device set ---------------------------------------------
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

    # --- standard-cell block ----------------------------------------------
    stdcell_blocks = [
        block
        for block in plan["blocks"]
        if any(group["kind"] == "stdcell" for group in block["groups"])
    ]
    stdcell_detail = "(no standard-cell block in this design)"
    stdcell_ok = True
    for block in stdcell_blocks:
        cells_block = _load(out_dir / f"cells.{block['name']}.json")
        top = next(entry for entry in cells_block["cells"] if entry["is_top"])
        expected = {
            f"{group['id']}__{group['params']['cell']}"
            for group in block["groups"]
            if group["kind"] == "stdcell"
        }
        actual = set(top["children"])
        stdcell_ok = stdcell_ok and expected == actual and top["instances"] == len(expected)
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

    # --- top hierarchy -----------------------------------------------------
    top_cell = next(entry for entry in cells_top["cells"] if entry["is_top"])
    expected_children = {
        f"{block['cell_name']}__{block['cell_name']}" for block in plan["blocks"]
    }
    top_ok = set(top_cell["children"]) == expected_children
    checks.append(
        (
            f"`{plan['top_cell_name']}` instantiates all "
            f"{len(expected_children)} block cells",
            top_ok,
            ", ".join(sorted(top_cell["children"])),
        )
    )

    # --- DRC ---------------------------------------------------------------
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
    checks.append(
        (
            "DRC fires exactly one rule class -- the documented `klt gen` "
            "minimum-gate-length limitation -- once per minimum-length device "
            f"({min_length_devices} of them), and nothing else",
            drc_ok,
            f"status={drc.get('status')}, rule_counts={rule_counts}",
        )
    )

    all_pass = all(ok for _, ok, _ in checks)

    klt_version = subprocess.run(
        [args.klt, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    pdk_info = json.loads(
        subprocess.run(
            [args.klt, "pdk", "find", "--pdk", args.pdk_variant, "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )

    sha = run_git(args.repo_root, "rev-parse", "HEAD")
    branch = run_git(args.repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    report_rel = out_dir.resolve().relative_to(args.repo_root.resolve()).as_posix() + "/"
    dirty = is_dirty(
        run_git(args.repo_root, "status", "--porcelain", "--untracked-files=all"),
        report_rel,
    )

    spot = None
    spot_path = out_dir / "route-spot-check" / "build.json"
    if spot_path.is_file():
        # A node the extractor labels with more than one declared net name is
        # a *drawn short*: two nets the schematic keeps apart ended up on one
        # electrical node. Counted straight out of the routed run's own
        # extracted netlist, so the claim is the extractor's, not this
        # script's.
        routed_spice = (out_dir / "route-spot-check" / "pll_top.spice").read_text()
        merged = sorted({m for m in re.findall(r"[A-Za-z_0-9]+(?:\|[A-Za-z_0-9]+)+", routed_spice)})
        spot = {
            "build": _load(spot_path),
            "drc": _load(out_dir / "route-spot-check" / "drc.json"),
            "extract": _load(out_dir / "route-spot-check" / "extract.json"),
            "merged_nodes": merged,
        }

    lines: list[str] = []
    a = lines.append
    a(f"# PLL layout record: {args.record_id}")
    a("")
    try:
        netlist_display = args.netlist.resolve().relative_to(
            args.repo_root.resolve()
        ).as_posix()
    except ValueError:  # pragma: no cover - netlist outside the repo
        netlist_display = args.netlist.as_posix()
    a(
        "Device-level layout of the closed-loop PLL schematic "
        f"(`{netlist_display}`), drawn by `layout/bin/run-pll-layout-flow.sh` "
        "(issue #16). Read this file first; everything else in this directory "
        "is the raw `klt` evidence it summarises."
    )
    a("")
    a("## Overall verdict: " + ("PASS" if all_pass else "FAIL"))
    a("")
    for desc, ok, detail in checks:
        a(f"- [{'x' if ok else ' '}] {desc} -- {detail}")
    a("")
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
        "- **Not LVS-clean, and not LVS-compared.** With no routing there is "
        "no topology in the stream to compare, so no LVS run is attempted "
        "here at all rather than reporting a foregone mismatch. LVS closure "
        "is issue #18."
    )
    a(
        "- **Not a verified circuit.** Nothing here is a claim against "
        "`spec/target-spec.md`; no simulation was run from this layout "
        "(PEX is issue #21)."
    )
    a("")
    if spot:
        spot_blocks = spot["build"]["blocks"]
        routed = sum(entry["routed_nets"] for entry in spot_blocks)
        declared = sum(entry["declared_nets"] for entry in spot_blocks)
        a("## Routing spot-check (why the shipped layout is unrouted)")
        a("")
        merged = spot["merged_nodes"]
        merged_nets = sum(node.count("|") + 1 for node in merged)
        a(
            "The same build was re-run with `klt gen-compose`'s "
            f"point-to-point router enabled (`route-spot-check/`). It routed "
            f"{routed} of {declared} declared nets; the rest are >2-pin bundle "
            "nets (out of scope for the router's current phase) or "
            "point-to-point pairs whose backbone would cross an unrelated "
            "block."
        )
        a("")
        a(
            f"**Every one of those {routed} routes is a drawn short.** The "
            "routed run's own extracted netlist collapses them onto "
            f"{len(merged)} electrical node(s) carrying {merged_nets} distinct "
            "net names between them:"
        )
        a("")
        for node in merged:
            a(f"- `{node}`")
        a("")
        a(
            f"Its DRC also reports {spot['drc'].get('violation_count')} "
            f"violations ({spot['drc'].get('rule_counts')}) against "
            f"{drc.get('violation_count')} for the unrouted build, and its "
            f"extraction finds {spot['extract'].get('net_count')} nets against "
            f"{extract_top.get('net_count')} -- "
            f"{extract_top.get('net_count') - spot['extract'].get('net_count')} "
            f"fewer for {routed} routes drawn, where {routed} correct "
            "point-to-point routes could account for at most "
            f"{routed}. Shipping known "
            "shorts to buy a handful of wires is a bad trade, so the shipped "
            "stream is the unrouted one and the behaviour is filed upstream "
            "(see `layout/pll/README.md`)."
        )
        a("")
        a("Per-block routing outcome from the spot-check:")
        a("")
        a("| Block | Declared nets | Routed | Unrouted |")
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
    a("## Flow")
    a("")
    a("1. `pll_layout.py` parses the schematic netlist and derives the plan (`plan.json`).")
    a("2. `klt gen mos_array` / `klt gen res_array` per matched device group.")
    a("3. `klt draw` per MiM capacitor (plate geometry -- no generator exists; see README).")
    a("4. Each divider standard cell is taken from the PDK's own library GDS.")
    a("5. `klt gen-compose` (explicit placement) per block, then once more for the top cell.")
    a("6. `klt drc` / `klt extract` / `klt cells` over the result -- the evidence in this directory.")
    a("")
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
