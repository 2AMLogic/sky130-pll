#!/usr/bin/env python3
"""Mint an append-only power-campaign evidence record from `klt sim` reports (issue #233).

Inputs: one `klt sim --format json` report per block (`vco`, `divider-n4`,
`divider-n64`, `pfd-cp`), each produced from
`sim/power/testbench/<block>.request.json` and each pointing (via
`corners[].artifacts.waveform`) at the per-corner waveform JSON it
downloaded. This module never simulates; it reduces those artifacts with
`sim/power/reduce.py`, rolls the blocks up, and writes:

    sim/power/records/<record-id>.md              the evidence record
    sim/power/reports/<record-id>/<block>.report.json   the klt reports, verbatim
    sim/power/reports/<record-id>/reduced.json    every reduced stage, machine-readable
    sim/power/netlist-snapshots/<record-id>/      the inputs that were simulated

Waveform dumps themselves are NOT committed (sim/README.md's retention policy).
A record is never edited; a re-run mints a new one (`--supersedes <id>`).

    python3 sim/power/mint.py --reports-dir DIR [--supersedes ID]
        [--subset-reason TEXT] [--record-id ID] [--dry-run]

DIR holds `<block>.report.json` for every block.

Provenance: the record layout (Record ID / Claim / Spec row(s) / Netlist
provenance / Environment provenance / Corner matrix run / Methodology /
Result) follows sim/README.md and sim/harness/report.py in this repo, so
measurements/aggregate.py reads it unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import reduce as R  # noqa: E402

BLOCKS = ["vco", "divider-n4", "divider-n64", "pfd-cp"]
F_REF_OUT_HZ = 100e6  # the gf180-pll reference point for row 12
F_LOCK_OUT_HZ = 250e6  # sim/pll-lock's closed-loop operating point
TYPICAL = ("tt", 1.80, 27.0)
ROLLUPS = [
    # (key, label, divider block, divider stage, pfd stage, pfd f_ref)
    ("N4", "N=4, 25 MHz reference", "divider-n4", "f100m", "25m_lock", "25 MHz"),
    ("N64", "N=64, 1 MHz reference", "divider-n64", "f100m", "1m_lock", "1 MHz"),
]

SPEC_ROW_NOTE = (
    "spec/target-spec.md row 12 (Power: 'a budget at a stated frequency'). Row 12 is "
    "DRAFT and this record ratifies nothing and proposes no number: it supplies the "
    "measured sky130 per-block supply current and power, at stated frequencies, that a "
    "future decision record would have to argue a budget from. Rows 1, 19 and 20 "
    "define the PVT grid it was measured on."
)


# --------------------------------------------------------------------------- #
# collection
# --------------------------------------------------------------------------- #


def corner_key(c: dict) -> tuple:
    vdd = next(iter(c["supply_v"].values()))
    return (c["process"], round(float(vdd), 3), float(c["temperature_c"]))


def reduce_block(block: str, report: dict, stages_doc: dict) -> dict:
    """{corner_key: {"stages": {id: StageResult}, "status", "errors": [...]}}"""
    out = {}
    for c in report.get("corners", []):
        key = corner_key(c)
        entry = {"status": c.get("status"), "stages": {}, "errors": [], "xchk": {}}
        for m in c.get("measurements", []):
            if m["name"].startswith("i_xchk_") and m.get("value") is not None:
                entry["xchk"][m["name"][len("i_xchk_"):]] = -float(m["value"])
        wf = (c.get("artifacts") or {}).get("waveform")
        if not wf or not Path(wf).is_file():
            entry["errors"].append("no waveform artifact for this corner")
        else:
            try:
                wave = R.load_waveform(wf)
                for r in R.reduce_point(wave, stages_doc, supply_v=key[1]):
                    entry["stages"][r.stage_id] = r
            except (R.PowerError, KeyError, ValueError) as exc:
                entry["errors"].append(f"waveform reduction failed: {exc}")
        out[key] = entry
    return out


def corner_bad(block: str, entry: dict) -> bool:
    """A block-corner is bad if its waveform is missing/unreadable, its idle stage
    failed, or (non-VCO blocks) any stage failed. A VCO ladder stage too slow to
    show the requested whole cycles is DATA (the ring is slow there), not a failure;
    whether the roll-up still has a bracketing pair is judged separately."""
    if entry["errors"] or not entry["stages"]:
        return True
    for sid, r in entry["stages"].items():
        if r.ok:
            continue
        if block == "vco" and r.kind == "active":
            continue
        return True
    return False


def stage_i(data: dict, key: tuple, sid: str):
    e = data.get(key)
    if not e:
        return None
    r = e["stages"].get(sid)
    return r.i_a if r is not None and r.ok else None


def vco_points(data: dict, key: tuple) -> list:
    e = data.get(key)
    if not e:
        return []
    return [(r.f_hz, r.i_a) for r in e["stages"].values()
            if r.kind == "active" and r.ok]


def rollup(all_data: dict, keys: list, f_out: float, spec: tuple) -> dict:
    """Per-corner sum-of-blocks at output frequency `f_out`."""
    _k, _label, div_block, div_stage, pfd_stage, _f = spec
    rows = {}
    for key in keys:
        vdd = key[1]
        vco_a, vco_note = R.interpolate_at_frequency(vco_points(all_data["vco"], key), f_out)
        vco_s = stage_i(all_data["vco"], key, "idle")
        div_a = stage_i(all_data[div_block], key, div_stage)
        div_s = stage_i(all_data[div_block], key, "idle")
        pfd_a = stage_i(all_data["pfd-cp"], key, pfd_stage)
        pfd_s = stage_i(all_data["pfd-cp"], key, "idle")
        parts_a = [vco_a, div_a, pfd_a]
        parts_s = [vco_s, div_s, pfd_s]
        if None in parts_a or None in parts_s:
            rows[key] = {"ok": False, "reason": "; ".join(
                n for n, v in (("vco", vco_a if vco_a is not None else vco_note),
                               ("divider", div_a), ("pfd", pfd_a)) if v is None or isinstance(v, str)
            ) or "missing stage"}
            continue
        i_tot, i_stat = sum(parts_a), sum(parts_s)
        rows[key] = {
            "ok": True, "vdd": vdd,
            "i_total_a": i_tot, "i_static_a": i_stat, "i_dynamic_a": i_tot - i_stat,
            "p_total_w": i_tot * vdd, "p_static_w": i_stat * vdd,
            "p_dynamic_w": (i_tot - i_stat) * vdd,
            "blocks_a": {"vco": vco_a, "divider": div_a, "pfd": pfd_a},
        }
    return rows


# --------------------------------------------------------------------------- #
# formatting
# --------------------------------------------------------------------------- #


def fmt_i(a) -> str:
    if a is None:
        return "-"
    if abs(a) < 1e-7:
        return f"{a * 1e9:.2f} nA"
    return f"{a * 1e6:.2f} uA" if abs(a) < 1e-3 else f"{a * 1e3:.3f} mA"


def fmt_p(w) -> str:
    if w is None:
        return "-"
    if abs(w) < 1e-7:
        return f"{w * 1e9:.2f} nW"
    return f"{w * 1e6:.2f} uW" if abs(w) < 1e-3 else f"{w * 1e3:.4f} mW"


def fmt_f(f) -> str:
    if f is None:
        return "-"
    return f"{f / 1e6:.2f} MHz" if f < 1e9 else f"{f / 1e9:.3f} GHz"


def key_label(k: tuple) -> str:
    return f"{k[0]}/{k[2]:g}C/{k[1]:.2f}V"


def summary_rows(rows: dict) -> list:
    ok = {k: v for k, v in rows.items() if v["ok"]}
    out = []
    if TYPICAL in ok:
        out.append(("typical (tt, 27 C, 1.80 V)", TYPICAL, ok[TYPICAL]))
    if ok:
        kmax = max(ok, key=lambda k: ok[k]["p_total_w"])
        kmin = min(ok, key=lambda k: ok[k]["p_total_w"])
        out.append(("maximum total power over the grid", kmax, ok[kmax]))
        out.append(("minimum total power over the grid", kmin, ok[kmin]))
        hot = {k: v for k, v in ok.items() if k[2] == 125.0}
        if hot:
            kh = max(hot, key=lambda k: hot[k]["p_static_w"])
            out.append(("maximum static power (125 C)", kh, hot[kh]))
    return out


def rollup_tables(title: str, rows: dict, full: bool = True) -> list:
    lines = [f"  **{title}**", "",
             "  | Case | Corner | I_total | P_static | P_dynamic (active - idle) | P_total |",
             "  |---|---|---|---|---|---|"]
    for label, k, v in summary_rows(rows):
        lines.append(
            f"  | {label} | {key_label(k)} | {fmt_i(v['i_total_a'])} | {fmt_p(v['p_static_w'])} "
            f"| {fmt_p(v['p_dynamic_w'])} | {fmt_p(v['p_total_w'])} |"
        )
    missing = [k for k, v in rows.items() if not v["ok"]]
    if missing:
        lines.append("")
        lines.append(f"  {len(missing)} corner(s) could not be rolled up (see per-corner table).")
    if full:
        lines += ["", "  Per-corner (all grid points):", "",
                  "  | Corner | VDD (V) | I_vco | I_divider | I_pfd | P_static | P_dynamic | P_total |",
                  "  |---|---|---|---|---|---|---|---|"]
        for k in sorted(rows, key=lambda k: (k[0], k[2], k[1])):
            v = rows[k]
            if v["ok"]:
                b = v["blocks_a"]
                lines.append(
                    f"  | {key_label(k)} | {k[1]:.2f} | {fmt_i(b['vco'])} | {fmt_i(b['divider'])} "
                    f"| {fmt_i(b['pfd'])} | {fmt_p(v['p_static_w'])} | {fmt_p(v['p_dynamic_w'])} "
                    f"| {fmt_p(v['p_total_w'])} |"
                )
            else:
                lines.append(f"  | {key_label(k)} | {k[1]:.2f} | not rolled up: {v['reason']} | | | | | |")
    return lines


def block_table(block: str, data: dict, stages_doc: dict) -> list:
    lines = [f"  **{block}** -- per-stage supply current at the typical corner "
             "(tt, 27 C, 1.80 V) and the grid extremes", "",
             "  | Stage | f (align node) | I typ | I min over grid | I max over grid | max at |",
             "  |---|---|---|---|---|---|"]
    for s in stages_doc["stages"]:
        sid = s["id"]
        vals = {k: stage_i(data, k, sid) for k in data}
        good = {k: v for k, v in vals.items() if v is not None}
        typ = vals.get(TYPICAL)
        ftyp = None
        e = data.get(TYPICAL)
        if e and sid in e["stages"] and e["stages"][sid].ok:
            ftyp = e["stages"][sid].f_hz
        if good:
            kmax = max(good, key=good.get)
            kmin = min(good, key=good.get)
            lines.append(
                f"  | {s['label']} | {fmt_f(ftyp)} | {fmt_i(typ)} | {fmt_i(good[kmin])} "
                f"| {fmt_i(good[kmax])} | {key_label(kmax)} |"
            )
        else:
            lines.append(f"  | {s['label']} | - | - | - | - | no corner reduced |")
    return lines


def vco_freq_table(data: dict, stages_doc: dict) -> list:
    lines = ["  VCO output frequency per VCTRL stage (typical corner):", "",
             "  | VCTRL | f_out | I_supply | P (1.80 V) |", "  |---|---|---|---|"]
    e = data.get(TYPICAL)
    for s in stages_doc["stages"]:
        if s["kind"] != "active" or not e:
            continue
        r = e["stages"].get(s["id"])
        if r is not None and r.ok:
            lines.append(f"  | {s['vctrl']:.2f} V | {fmt_f(r.f_hz)} | {fmt_i(r.i_a)} | {fmt_p(r.p_w)} |")
    return lines


def at_250(all_data: dict, keys: list) -> list:
    lines = ["  Per-block at the sim/pll-lock operating frequency (250 MHz output / divider input); "
             "NOT summed (no N=25 divider and no 10 MHz PFD point was simulated):", "",
             "  | Block | Case | I typ | P typ | P max over grid | max at |", "  |---|---|---|---|---|---|"]
    entries = []
    for key in keys:
        pass
    # VCO interpolated at 250 MHz
    def vco_val(k):
        i, _ = R.interpolate_at_frequency(vco_points(all_data["vco"], k), F_LOCK_OUT_HZ)
        return i
    series = [
        ("vco_ring5", "interpolated to 250 MHz", vco_val),
        ("divider N=4", "250 MHz input", lambda k: stage_i(all_data["divider-n4"], k, "f250m")),
        ("divider N=64", "250 MHz input", lambda k: stage_i(all_data["divider-n64"], k, "f250m")),
    ]
    for name, case, fn in series:
        vals = {k: fn(k) for k in keys}
        good = {k: v * k[1] for k, v in vals.items() if v is not None}
        if not good:
            lines.append(f"  | {name} | {case} | - | - | - | no corner reduced |")
            continue
        kmax = max(good, key=good.get)
        typ_i = vals.get(TYPICAL)
        lines.append(
            f"  | {name} | {case} | {fmt_i(typ_i)} | {fmt_p(good.get(TYPICAL))} "
            f"| {fmt_p(good[kmax])} | {key_label(kmax)} |"
        )
    return lines


# --------------------------------------------------------------------------- #
# record
# --------------------------------------------------------------------------- #


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(record_id: str, reports: dict, all_data: dict, stages_docs: dict,
           supersedes: str | None, subset_reason: str | None) -> str:
    keys_by_block = {b: sorted(all_data[b]) for b in BLOCKS}
    grid = sorted(set().union(*[set(v) for v in keys_by_block.values()]))
    procs = sorted({k[0] for k in grid})
    temps = sorted({k[2] for k in grid})
    vdds = sorted({k[1] for k in grid})
    full = len(grid) == 45 and all(len(keys_by_block[b]) == 45 for b in BLOCKS)

    rollups = {spec[0]: rollup(all_data, grid, F_REF_OUT_HZ, spec) for spec in ROLLUPS}
    n_total = sum(len(keys_by_block[b]) for b in BLOCKS)
    bad_set = {(b, k) for b in BLOCKS for k in keys_by_block[b] if corner_bad(b, all_data[b][k])}
    n_bad = len(bad_set)
    unrolled = sum(1 for r in rollups.values() for v in r.values() if not v["ok"])
    overall_ok = n_bad == 0 and unrolled == 0 and n_total > 0
    verdict = "PASS" if overall_ok else "FAIL"

    envs = {b: (reports[b].get("environment") or {}) for b in BLOCKS}
    remote = {b: envs[b].get("remote") or {} for b in BLOCKS}
    prov = {b: (reports[b].get("provenance") or {}) for b in BLOCKS}
    klt_versions = sorted({str(prov[b].get("klt_version")) for b in BLOCKS})

    L = []
    L.append(f"# Record {record_id}")
    L.append("")
    L.append(f"- **Record ID**: {record_id}")
    L.append(
        "- **Claim**: Measured sky130 supply current and power of the open-loop blocks "
        "(`vco_ring5`, `divider_intN` at N=4 and N=64, `pfd_cp` at the reference-range "
        "extremes) over the ratified PVT grid, with the static (idle) and dynamic "
        "(active minus idle) parts reported separately, rolled up as a SUM OF BLOCKS at a "
        "stated 100 MHz output frequency (issue #233). This is measured design input, "
        "not a spec claim and not a closed-loop measurement: it ratifies nothing and "
        "proposes no budget number."
    )
    L.append(f"- **Spec row(s)**: 12 -- {SPEC_ROW_NOTE}")
    if supersedes:
        L.append(f"- **Supersedes**: {supersedes}")
    L.append("- **Netlist provenance**: schematics `sim/power/testbench/tb_power_*.sch`, netlisted by "
             "`sim/power/build.py`; frozen under "
             f"`sim/power/netlist-snapshots/{record_id}/`:")
    for b in BLOCKS:
        body = REPO_ROOT / "sim" / "power" / "netlist-snapshots" / record_id / f"{b}.body.spice"
        digest = sha256(HERE / "testbench" / f"{b}.body.spice")
        L.append(f"  - `{b}.body.spice` SHA-256 `{digest}`")
        del body
    L.append("- **Environment provenance**:")
    L.append(f"  - klt: {', '.join(klt_versions)} (`klt sim`, ngspice engine, PDK `sky130A`)")
    pdk = next((prov[b].get("pdk") for b in BLOCKS if prov[b].get("pdk")), None)
    if pdk:
        L.append(f"  - PDK: {json.dumps(pdk, sort_keys=True)}")
    L.append(f"  - Repo commit: `{git('rev-parse', 'HEAD')}`" + (" (dirty)" if git("status", "--porcelain") else ""))
    for b in BLOCKS:
        r = remote[b]
        if r:
            L.append(
                f"  - `{b}` ran on the batch fleet: job `{r.get('job_id')}`, "
                f"`{r.get('instance_type')}`, lifecycle `{r.get('lifecycle')}`, "
                f"{r.get('elapsed_seconds')} s elapsed"
            )
        else:
            L.append(f"  - `{b}`: no `environment.remote` in the report (ran locally)")
    L.append("- **Corner matrix run**:")
    L.append(f"  - Process corners: {', '.join(procs)}")
    L.append(f"  - Temperatures (deg C): {', '.join(f'{t:g}' for t in temps)}")
    L.append(f"  - Supplies (V): {', '.join(f'{v:.2f}' for v in vdds)}")
    L.append(f"  - Total points: {len(grid)} per block ({', '.join(f'{b}: {len(keys_by_block[b])}' for b in BLOCKS)})")
    if full:
        L.append("  - The full ratified 5 x 3 x 3 = 45-point grid (rows 19/20/1) was run for every block; no subset.")
    else:
        L.append(f"  - **Subset of the manifest's default grid**: {subset_reason or '(reason not stated)'}")
    L.append("- **Methodology / criteria / limitations**:")
    for text in METHOD_LINES:
        L.append(f"  - {text}")
    L.append("- **Result**:")
    L.append("")
    L.append("  | Block | Corners reduced | Corners with a missing/failed stage |")
    L.append("  |---|---|---|")
    for b in BLOCKS:
        bad = sum(1 for k in keys_by_block[b] if (b, k) in bad_set)
        L.append(f"  | {b} | {len(keys_by_block[b])} | {bad} |")
    L.append("")
    L.append(
        f"  - **Overall: {verdict}** ({n_total - n_bad}/{n_total} block-corners fully reduced"
        f"; {unrolled} of {sum(len(r) for r in rollups.values())} roll-up corners unavailable; "
        "this is a characterization record -- the verdict means every stage was measured, "
        "not that a power budget is met, because row 12 states no numeric budget)"
    )
    L.append("")
    L.append("- **Roll-up at 100 MHz output (SUM OF OPEN-LOOP BLOCKS, not a loop measurement)**:")
    L.append("")
    L.append(
        "  Included: `vco_ring5` (interpolated in output frequency to 100 MHz between "
        "the bracketing VCTRL stages; no extrapolation), `divider_intN` driven at 100 MHz, "
        "`pfd_cp` at the stated reference frequency in the lock-like condition "
        "(DIV lagging REF by 100 ps). Excluded: loop filter (passive, no supply current), "
        "lock detector and any output buffering (none exist in the design), and every "
        "testbench source."
    )
    L.append("")
    for spec in ROLLUPS:
        L += rollup_tables(f"{spec[1]} -- divider driven at 100 MHz", rollups[spec[0]])
        L.append("")
    L.append("- **Per-block results**:")
    L.append("")
    for b in BLOCKS:
        L += block_table(b, all_data[b], stages_docs[b])
        L.append("")
        if b == "vco":
            L += vco_freq_table(all_data[b], stages_docs[b])
            L.append("")
    L += at_250(all_data, grid)
    L.append("")
    L.append("- **Cross-check against the in-simulator fixed-window `.meas` cards**:")
    L.append("")
    worst = []
    for b in BLOCKS:
        for k in keys_by_block[b]:
            e = all_data[b][k]
            for sid, r in e["stages"].items():
                x = e["xchk"].get(sid)
                if r.ok and x is not None and r.i_a:
                    worst.append((abs(x - r.i_a) / abs(r.i_a), b, k, sid))
    if worst:
        worst.sort(reverse=True)
        frac, b, k, sid = worst[0]
        fr = sorted(w[0] for w in worst)
        median = fr[len(fr) // 2]
        L.append(
            f"  Over {len(worst)} stage-corners the whole-cycle reduction and the coarse "
            f"second-half-of-stage `.meas AVG` differ by a median of {median * 100:.2f} % and "
            f"at worst {frac * 100:.1f} % ({b}, stage `{sid}`, {key_label(k)}). The "
            "`.meas` figure is not cycle-aligned and is NOT what this record reports; "
            "the spread is the bias whole-cycle alignment removes."
        )
    else:
        L.append("  No overlapping stage-corners to compare.")
    L.append("")
    L.append("- **Machine-readable data**: "
             f"`sim/power/reports/{record_id}/reduced.json` (every stage of every corner).")
    L.append("")
    return "\n".join(L)


METHOD_LINES = [
    "Stimulus: ONE transient per PVT point per block, staged in time (`sim/power/build.py` "
    "emits the schematic, request and stage table from one definition). Each testbench "
    "has a single supply source `V1` on the DUT's VDD net; `i(V1)` is the block's own "
    "supply current (stimulus sources, the `.ic` card and the absent output loads draw "
    "nothing from it). Supply values 1.62/1.80/1.98 V are applied to `V1` by the "
    "`klt sim` supply axis; stimulus amplitudes track the point's own VDD.",
    "Reduction: `sim/power/reduce.py` averages `i(V1)` over an integer number of cycles of "
    "the stage's alignment node (VCO output; divider output = one whole divider period; PFD "
    "reference), starting at the first rising edge (0.5*VDD, 15 % hysteresis) after the "
    "stage's settling time. The idle stage is a plain mean over its settled window. "
    "Unit tests: `sim/tests/test_power.py`. Power = mean current x the point's own VDD.",
    "Stimulus summary: VCO -- VCTRL held at 0 V (idle: the starved ring is quiescent), then "
    "0.70-1.60 V in thirteen 250 ns stages, 3 whole cycles averaged after 100 ns of settling "
    "(a ladder stage too slow to show 3 cycles is reported as unresolved, not extrapolated). Divider -- "
    "RESETB released, input clock gated off (idle), then a rail-to-rail 100 MHz and a "
    "250 MHz input clock; one whole divider output period averaged after one warm-up "
    "period. PFD/CP -- REF and DIV low (idle), then 25 MHz and 1 MHz (the row 3 reference "
    "range extremes), each with DIV lagging REF by 100 ps (lock-like) and by a "
    "quarter period (acquisition-like, the high-activity bound); CP held at 0.9 V "
    "by an ideal source.",
    "Static vs dynamic: 'static' is the idle-stage current (leakage plus any bias that flows "
    "with the block quiescent); 'dynamic' is DERIVED as active minus idle at the same "
    "corner, so it includes any switching-dependent bias or short-circuit current. They are "
    "not separately simulated components. Hot-corner (125 C) leakage is the static column.",
    "100 MHz roll-up: the VCO value is interpolated linearly in output frequency between "
    "the two measured VCTRL stages that bracket 100 MHz at that corner; where 100 MHz is not "
    "bracketed the corner is reported as not rolled up. The divider is driven at 100 MHz "
    "(its input is the VCO output). For N=4 the reference is 25 MHz; for N=64 the nearest "
    "simulated reference extreme is 1 MHz (the true 100/64 = 1.5625 MHz reference was not "
    "simulated; the PFD figure at 1 MHz slightly understates it). N=4 and N=64 are the "
    "range extremes (row 4); intermediate N were not run.",
    "NOT a loop measurement: the totals are sums of three separately simulated open-loop "
    "blocks. They contain no interaction between blocks (no real VCO loading on the divider, "
    "no real divider output edge into the PFD, CP held by an ideal source instead of the "
    "loop filter) and say nothing about the assembled loop, which still does not lock "
    "(issue #98). The VCO's own CLK buffer is inside `vco_ring5` and is counted; any "
    "external output buffer or pad driver is not in the design and is not counted.",
    "Simulator accuracy: ngspice default tolerances, `tran` step capped at the manifest's "
    "step (VCO 50 ps, divider 20/40 ps, PFD 100 ps); no `reltol` tightening. Average current "
    "is far less sensitive to integrator tolerance than edge timing (see "
    "`sim/tolerance-audit/README.md`), but no tolerance audit was run on this campaign. "
    "VCO frequency (hence its 100 MHz interpolation point) inherits that campaign's "
    "documented frequency uncertainty at the fast end.",
    "Not measured: supply-ripple or transient-supply behaviour, any mismatch Monte Carlo "
    "(local-mismatch spread of the currents), interconnect parasitics (schematic-level "
    "devices only, no layout), the loop filter, and PFD behaviour with a non-zero charge-pump "
    "load current. Row 12's numeric budget is not proposed here.",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reports-dir", required=True, type=Path)
    ap.add_argument("--record-id")
    ap.add_argument("--supersedes")
    ap.add_argument("--subset-reason")
    ap.add_argument("--dry-run", action="store_true", help="print the record, write nothing")
    args = ap.parse_args(argv)

    reports, stages_docs, all_data = {}, {}, {}
    for b in BLOCKS:
        rp = args.reports_dir / f"{b}.report.json"
        if not rp.is_file():
            raise SystemExit(f"missing {rp}")
        reports[b] = json.loads(rp.read_text())
        stages_docs[b] = json.loads((HERE / "testbench" / f"{b}.stages.json").read_text())
        all_data[b] = reduce_block(b, reports[b], stages_docs[b])

    record_id = args.record_id or (
        datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + git("rev-parse", "--short", "HEAD")
    )
    rec_path = HERE / "records" / f"{record_id}.md"
    if rec_path.exists():
        raise SystemExit(f"{rec_path} exists; records are append-only (mint a new id)")
    text = render(record_id, reports, all_data, stages_docs, args.supersedes, args.subset_reason)
    if args.dry_run:
        print(text)
        return 0

    (HERE / "records").mkdir(exist_ok=True)
    rec_path.write_text(text)
    rep_dir = HERE / "reports" / record_id
    rep_dir.mkdir(parents=True)
    snap_dir = HERE / "netlist-snapshots" / record_id
    snap_dir.mkdir(parents=True)
    for b in BLOCKS:
        shutil.copy(args.reports_dir / f"{b}.report.json", rep_dir / f"{b}.report.json")
        for suffix in ("body.spice", "request.json", "stages.json"):
            shutil.copy(HERE / "testbench" / f"{b}.{suffix}", snap_dir / f"{b}.{suffix}")
    reduced = {
        b: {
            key_label(k): {
                "process": k[0], "vdd": k[1], "temp_c": k[2],
                "errors": e["errors"],
                "stages": {
                    sid: {"ok": r.ok, "reason": r.reason, "i_a": r.i_a, "p_w": r.p_w,
                          "f_hz": r.f_hz, "window_s": list(r.window) if r.window else None,
                          "cycles": r.cycles, "edges": r.edges_in_window}
                    for sid, r in e["stages"].items()
                },
            }
            for k, e in sorted(all_data[b].items())
        }
        for b in BLOCKS
    }
    (rep_dir / "reduced.json").write_text(json.dumps(reduced, indent=1) + "\n")
    print(f"wrote {rec_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
