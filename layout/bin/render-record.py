#!/usr/bin/env python3
"""Render layout/trivial-cell/reports/<record-id>/record.md from the `klt`
JSON envelopes `run-trivial-cell-flow.sh` just produced in that directory.

Standard library only (matches sim/run_corners.py's convention of no extra
runtime dependency beyond what the harness itself needs).

Exits non-zero (after writing record.md, so the evidence trail still gets a
record of the failure) if any of the expected verdicts don't hold: DRC clean
on the trivial cell, DRC violations reported on the deliberately illegal
fixture, those violations being exactly the rules the fixture declares it
injects, LVS match on the good reference, and LVS mismatch on each of the
two negative-control references. That mirrors the trivial-cell flow's
actual job: it exists to prove the round trip works *and* that it can still
report failure, so a silent verdict flip is exactly the regression this
script is here to catch.

Provenance: adapted from 2AMLogic/sky130-bandgap
layout/bin/render-record.py (source commit
7d1ce05168777f6615e1e26adf5eedd6213df318) per this repo's CLAUDE.md
harness-bootstrap rule. Deviation: the DRC negative-control verdict is added
here (the source flow has no DRC negative control) -- see
run-trivial-cell-flow.sh's own header.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# scripts/git_status.py lives at the repo root (shared with
# sim/harness/report.py -- sim/ and layout/ are otherwise independent trees
# per CLAUDE.md's harness-bootstrap convention). This file is loaded both as
# a script (run directly) and by path via importlib (layout/tests), so the
# repo root has to be put on sys.path explicitly rather than relying on
# script-directory sys.path[0] insertion.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Re-exported (not just used below): layout/tests/test_record_dirty_flag.py
# loads this module by path and calls `render_record.is_dirty(...)` directly.
from scripts.git_status import is_dirty  # noqa: E402,F401

_BIN_DIR = Path(__file__).resolve().parent
if str(_BIN_DIR) not in sys.path:
    sys.path.insert(0, str(_BIN_DIR))

from render_common import git_provenance, klt_info, load_json  # noqa: E402

_load = load_json  # local alias, kept short for the calls below


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--record-id", required=True)
    ap.add_argument("--repo-root", required=True, type=Path)
    ap.add_argument("--klt", required=True)
    ap.add_argument("--pdk-variant", required=True)
    return ap.parse_args()


# --- compute: derive `checks` (and the two negative-control rule lists the
# record's detail paragraph needs) from the loaded `klt` JSON evidence. Each
# `_check_*` helper below owns exactly one of the six verdicts the module
# docstring lists; `_build_checks` is a flat, branch-free sequence over
# them. -----------------------------------------------------------------


def _check_drc_clean(drc: dict[str, Any]) -> tuple[str, bool]:
    return ("DRC on trivial_mos_array is clean", drc.get("status") == "clean")


def _check_drc_negative_control_violations(drc_nc: dict[str, Any]) -> tuple[str, bool]:
    return (
        "DRC negative control (deliberately illegal geometry) reports violations",
        drc_nc.get("status") == "violations",
    )


def _check_drc_negative_control_exact_rules(
    expected_nc_rules: list[str], fired_nc_rules: list[str]
) -> tuple[str, bool]:
    return (
        "DRC negative control trips exactly the rules its fixture "
        f"declares ({', '.join(expected_nc_rules) or 'none declared'})",
        bool(expected_nc_rules) and fired_nc_rules == expected_nc_rules,
    )


def _check_lvs_good(lvs_good: dict[str, Any]) -> tuple[str, bool]:
    return (
        "LVS matches the known-good reference",
        lvs_good.get("status") == "match",
    )


def _check_lvs_negative_control_device(lvs_bad_dev: dict[str, Any]) -> tuple[str, bool]:
    return (
        "LVS negative control (device-parameter corruption) reports mismatch",
        lvs_bad_dev.get("status") == "mismatch",
    )


def _check_lvs_negative_control_topology(lvs_bad_topo: dict[str, Any]) -> tuple[str, bool]:
    return (
        "LVS negative control (topology corruption) reports mismatch",
        lvs_bad_topo.get("status") == "mismatch",
    )


def _build_checks(
    drc: dict[str, Any],
    drc_nc: dict[str, Any],
    nc_params: dict[str, Any],
    lvs_good: dict[str, Any],
    lvs_bad_dev: dict[str, Any],
    lvs_bad_topo: dict[str, Any],
) -> tuple[list[tuple[str, bool]], list[str], list[str]]:
    """The record's `checks` list, plus the two negative-control rule lists.

    Same six assertions, same order, as the pre-split `main()` built inline;
    only the "how" moved, one `_check_*` helper per assertion. The rule
    lists are also returned since `_render_drc_negative_control_detail`
    needs them again for its own paragraph.
    """
    # The fixture declares which rules it is engineered to trip; the record
    # asserts the deck fired exactly those, so a fixture that silently stops
    # violating (or a deck that silently stops checking) is a FAIL rather
    # than an unnoticed no-op negative control.
    expected_nc_rules = sorted(nc_params.get("_expected_rules", {}))
    fired_nc_rules = sorted(drc_nc.get("rule_counts", {}))

    checks = [
        _check_drc_clean(drc),
        _check_drc_negative_control_violations(drc_nc),
        _check_drc_negative_control_exact_rules(expected_nc_rules, fired_nc_rules),
        _check_lvs_good(lvs_good),
        _check_lvs_negative_control_device(lvs_bad_dev),
        _check_lvs_negative_control_topology(lvs_bad_topo),
    ]
    return checks, expected_nc_rules, fired_nc_rules


# --- render: each `_render_*` helper appends one `## `-headed markdown
# section (or, for the header, the record's title + intro; or, for the two
# negative-control/LVS-good detail paragraphs, a sub-part of the "## Results"
# section) to the shared `lines` list via `a = lines.append`. `main()` calls
# them in the record's own section order. --------------------------------


def _render_header(a: Any, args: argparse.Namespace) -> None:
    a(f"# Layout DRC/LVS record: {args.record_id}")
    a("")
    a(
        "Trivial-cell proof of the `klt`-driven DRC/LVS flow (issue #2) -- "
        "**not** PLL-block layout, which is a later issue's scope (there is "
        "no PLL schematic yet)."
    )
    a("")


def _render_verdict(a: Any, checks: list[tuple[str, bool]], all_pass: bool) -> None:
    a("## Overall verdict: " + ("PASS" if all_pass else "FAIL"))
    a("")
    for desc, ok in checks:
        a(f"- [{'x' if ok else ' '}] {desc}")
    a("")


def _render_flow(a: Any, args: argparse.Namespace) -> None:
    a("## Flow")
    a("")
    a(
        "1. `klt gen mos_array --pdk "
        f"{args.pdk_variant} --cell-name trivial_mos_array` "
        "-- default params (2x2 array, 1 dummy column/side, nfet, no well)."
    )
    a("2. `klt drc trivial_mos_array.gds --deck sky130`")
    a(
        "2b. `klt draw` the deliberately illegal fixture "
        "(`drc-negative-control.params.json`), then run the same deck against "
        "it -- it must come back flagged."
    )
    a("3. `klt extract trivial_mos_array.gds --deck sky130 --top trivial_mos_array`")
    a(
        "4. `klt lvs` against `reference.spice` (known-good) and two "
        "negative-control references (`reference.broken-device.spice`, "
        "`reference.broken-topology.spice`)."
    )
    a("")


def _render_cell(a: Any, gen: dict[str, Any], extract: dict[str, Any]) -> None:
    a("## Cell")
    a("")
    a("- Generator: `mos_array` (`klt gen --list` for the full params schema)")
    a(f"- `device_count` (extracted): {extract.get('device_count')}")
    a(f"- `dummy_devices_dropped`: {extract.get('dummy_devices_dropped')}")
    a(f"- bbox (um): {gen.get('bbox_um')}")
    a(f"- `matched_group_id`: {gen.get('drc_hints', {}).get('matched_group_id')}")
    a("")


def _render_results(
    a: Any,
    drc: dict[str, Any],
    drc_nc: dict[str, Any],
    extract: dict[str, Any],
    lvs_good: dict[str, Any],
    lvs_bad_dev: dict[str, Any],
    lvs_bad_topo: dict[str, Any],
) -> None:
    a("## Results")
    a("")
    a("| Stage | Status | Detail |")
    a("| --- | --- | --- |")
    a(
        "| DRC | "
        f"{drc.get('status')} | violation_count={drc.get('violation_count')} |"
    )
    a(
        "| DRC negative control | "
        f"{drc_nc.get('status')} | violation_count="
        f"{drc_nc.get('violation_count')}, rule_counts="
        f"{drc_nc.get('rule_counts')} |"
    )
    a(
        "| Extract | "
        f"{extract.get('status')} | device_count={extract.get('device_count')}, "
        f"net_count={extract.get('net_count')}, pin_count={extract.get('pin_count')} |"
    )
    a(
        "| LVS (good reference) | "
        f"{lvs_good.get('status')} | mismatch_count={lvs_good.get('mismatch_count')}, "
        f"category_counts={lvs_good.get('category_counts')} |"
    )
    a(
        "| LVS negative control: device parameter | "
        f"{lvs_bad_dev.get('status')} | mismatch_count={lvs_bad_dev.get('mismatch_count')} |"
    )
    a(
        "| LVS negative control: topology (shorted net) | "
        f"{lvs_bad_topo.get('status')} | mismatch_count={lvs_bad_topo.get('mismatch_count')} |"
    )
    a("")


def _render_drc_negative_control_detail(
    a: Any,
    nc_params: dict[str, Any],
    expected_nc_rules: list[str],
    fired_nc_rules: list[str],
) -> None:
    a(
        "The DRC negative control is a `klt draw` fixture -- geometry written "
        "verbatim with no rule checking -- carrying one deliberately illegal "
        "width and one deliberately illegal spacing, so a regression that "
        "silently disabled either check primitive would still be caught by "
        "the other. Rules the fixture declares it should trip: "
        f"{', '.join(f'`{r}`' for r in expected_nc_rules) or '(none declared)'}; "
        "rules the deck actually reported: "
        f"{', '.join(f'`{r}`' for r in fired_nc_rules) or '(none)'}."
    )
    for rule in expected_nc_rules:
        a(f"- `{rule}` -- {nc_params['_expected_rules'][rule]}")
    a("")


def _render_lvs_good_detail(a: Any, lvs_good: dict[str, Any]) -> None:
    good_mismatches = lvs_good.get("mismatches", [])
    non_warning = [m for m in good_mismatches if m.get("severity") != "warning"]
    ambiguous_net = [
        m
        for m in good_mismatches
        if m.get("category") == "topology" and m.get("net") is not None
    ]
    unused_class = [
        m
        for m in good_mismatches
        if m.get("category") == "topology" and m.get("net") is None
    ]
    body_unverified = [
        m for m in good_mismatches if m.get("category") == "device.body_unverified"
    ]
    a(
        f"The good-reference LVS run's `mismatch_count` "
        f"({lvs_good.get('mismatch_count')}) is nonzero but `status` is "
        f"`\"match\"` -- all {len(good_mismatches)} entries are "
        f"`severity: \"warning\"` (0 at `severity: \"error\"`; see "
        "`lvs.json`), documented, expected quirks for this minimal, highly "
        "symmetric cell:"
    )
    a(
        f"- `device.body_unverified` (x{len(body_unverified)}): the curated "
        "sky130 extraction deck draws no distinct NMOS substrate/tap layer, "
        "so every body terminal compares against a deck-synthesized "
        "`vsubs` net rather than a real schematic net (documented in "
        "`klt extract`'s own \"Coverage\" docs)."
    )
    a(
        f"- `topology`, ambiguous net pairing (x{len(ambiguous_net)}): the "
        "array's unit devices are electrically interchangeable (no two "
        "devices connect to a common net that would anchor a unique "
        "pairing), so `NetlistComparer` resolves the correspondence "
        "structurally rather than uniquely -- expected for a fully "
        "symmetric matched array, not a defect."
    )
    a(
        f"- `topology`, unused device class on both sides (x{len(unused_class)}): "
        "device classes the sky130 deck can recognise (e.g. `pfet`, `pnp`, "
        "`resistor`) but that this cell draws none of -- not a real mismatch."
    )
    if non_warning:
        a(
            f"- **{len(non_warning)} `severity: \"error\"` entries were "
            "present -- this is NOT a clean match and the assertion above "
            "should have failed.**"
        )
    a("")


def _render_provenance(
    a: Any,
    args: argparse.Namespace,
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
    a(f"- `klt` version: `{klt_version}` (see `layout/requirements.txt`)")
    a(
        f"- KLayout engine version: "
        f"`{drc.get('provenance', {}).get('klayout_version')}`"
    )
    a(f"- PDK: `{pdk_info.get('variant')}`, `{pdk_info.get('version')}`")
    a(
        "- PDK pin cross-check: compare `version` above against "
        "`sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself "
        "enforce the pin (unlike `sim/harness/pdk.py`), so a mismatch here "
        "is a manual reproducibility note, not a hard failure."
    )
    a(f"- Repo state: `{sha}` on `{branch}`" + (" (dirty)" if dirty else ""))
    a("")


def _render_links(a: Any) -> None:
    a("## Links")
    a("")
    a("- [`gen.json`](gen.json), [`trivial_mos_array.gds`](trivial_mos_array.gds)")
    a("- [`drc.json`](drc.json)")
    a(
        "- [`drc-negative-control.params.json`](drc-negative-control.params.json), "
        "[`draw.negative-control.json`](draw.negative-control.json), "
        "[`drc_negative_control.gds`](drc_negative_control.gds), "
        "[`drc.negative-control.json`](drc.negative-control.json)"
    )
    a("- [`extract.json`](extract.json), [`trivial_mos_array.extract.spice`](trivial_mos_array.extract.spice)")
    a("- [`lvs.request.json`](lvs.request.json), [`lvs.json`](lvs.json), [`reference.spice`](reference.spice)")
    a(
        "- [`lvs.broken-device.request.json`](lvs.broken-device.request.json), "
        "[`lvs.broken-device.json`](lvs.broken-device.json), "
        "[`reference.broken-device.spice`](reference.broken-device.spice)"
    )
    a(
        "- [`lvs.broken-topology.request.json`](lvs.broken-topology.request.json), "
        "[`lvs.broken-topology.json`](lvs.broken-topology.json), "
        "[`reference.broken-topology.spice`](reference.broken-topology.spice)"
    )
    a("- [`report.md`](report.md) -- combined `klt report --format github-summary` rendering")
    a("")


def main() -> int:
    args = _parse_args()

    out_dir: Path = args.out_dir
    gen = _load(out_dir / "gen.json")
    drc = _load(out_dir / "drc.json")
    drc_nc = _load(out_dir / "drc.negative-control.json")
    nc_params = _load(out_dir / "drc-negative-control.params.json")
    extract = _load(out_dir / "extract.json")
    lvs_good = _load(out_dir / "lvs.json")
    lvs_bad_dev = _load(out_dir / "lvs.broken-device.json")
    lvs_bad_topo = _load(out_dir / "lvs.broken-topology.json")

    sha, branch, dirty = git_provenance(args.repo_root, out_dir)
    klt_version, pdk_info = klt_info(args.klt, args.pdk_variant)

    checks, expected_nc_rules, fired_nc_rules = _build_checks(
        drc, drc_nc, nc_params, lvs_good, lvs_bad_dev, lvs_bad_topo
    )
    all_pass = all(ok for _, ok in checks)

    lines: list[str] = []
    a = lines.append
    _render_header(a, args)
    _render_verdict(a, checks, all_pass)
    _render_flow(a, args)
    _render_cell(a, gen, extract)
    _render_results(a, drc, drc_nc, extract, lvs_good, lvs_bad_dev, lvs_bad_topo)
    _render_drc_negative_control_detail(a, nc_params, expected_nc_rules, fired_nc_rules)
    _render_lvs_good_detail(a, lvs_good)
    _render_provenance(a, args, klt_version, pdk_info, drc, sha, branch, dirty)
    _render_links(a)

    print("\n".join(lines))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
