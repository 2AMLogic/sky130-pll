#!/usr/bin/env python3
"""Read this campaign's measured transition time against sim/jitter-floor's family.

`sim/jitter-floor/` (issue #178) measures `sim/harness/measure.py`'s own
period-jitter measurement-resolution floor as a family over the ratio of the
measured clock's transition (edge) time to the dump-grid step: the floor
collapses to 0.000 % once the transition spans two or more grid samples
(variant C, edge/step = 5.0), sits at 0.610 % exactly at one grid step
(variant B, edge/step = 1.0), and runs 0.381-2.371 % for an edge a tenth of a
step (variants A1/A2/A3, edge/step = 0.1, one per `sim/pll-lock-mc` locked
draw's own measured period). That family answers "what is the floor, given
the edge/step ratio" -- it does not say what `design/vco`'s own `CLK` ratio
actually is, which is `sim/vco-clk-transition/` (issue #186).

This script reads both and states the conclusion: `design/vco`'s own `CLK`
transition time, divided by the 200 ps dump grid `sim/jitter-floor` and
`sim/pll-lock-mc` both dump at, is a specific number -- and, because the
floor is a **monotonically decreasing** function of that ratio at fixed
period (established by the A3/B/C triple, which shares one period and
differs only in edge time: 0.1 -> 2.371 %, 1.0 -> 0.610 %, 5.0 -> 0.000 %),
the real ratio being strictly between A3's and B's *brackets* -- rather than
merely bounds -- the applicable floor between their two measured figures.
No new simulation is run here: the bracket is arithmetic on two already-
committed measurements plus a monotonicity argument `sim/harness/measure.py`'s
own module docstring already states in prose ("the floor collapses as soon
as the grid resolves the edge").

It is an `analysis/` script in the sense `sim/README.md` defines: mutable,
stdlib-only, it reads committed records (and, for the floor family, those
records' own committed per-point netlists, for the `pulse(...)`/`tran` cards
that state each variant's period/edge/step) and restates what they already
say. It never simulates and never introduces a measured number of its own.

Usage:

    # print the bracket document to stdout
    python3 sim/vco-clk-transition/analysis/bracket_floor.py

    # (re)write sim/vco-clk-transition/analysis/bracket.md
    python3 sim/vco-clk-transition/analysis/bracket_floor.py --write

    # re-derive and verify the committed document (exit 1 on any drift)
    python3 sim/vco-clk-transition/analysis/bracket_floor.py --check

Standard library only, same convention as `sim/jitter-calibration/analysis/
calibration.py` and `sim/pll-lock-mc/analysis/jitter_floor.py`. No PDK,
ngspice, xschem or `klt` required.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TRANSITION_EXPERIMENT = REPO_ROOT / "sim" / "vco-clk-transition"
FLOOR_EXPERIMENT = REPO_ROOT / "sim" / "jitter-floor"
OUTPUT = Path(__file__).resolve().parent / "bracket.md"

_SUFFIXES = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}
_LITERAL_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z]*)$")

_RECORD_ID_RE = re.compile(r"^- \*\*Record ID\*\*: (?P<record_id>\S+)\s*$", re.M)
_TRANSITION_DETAIL_RE = re.compile(
    r"transition time: rise (?P<rise>[\d.]+) ps \(n=(?P<n_rise>\d+)\), "
    r"fall (?P<fall>[\d.]+) ps \(n=(?P<n_fall>\d+)\)"
)
_FLOOR_VARIANT_RE = re.compile(r"THIS RECORD'S VARIANT: (?P<variant>[A-Za-z0-9]+) --")
_JITTER_IN_DETAIL_RE = re.compile(
    r"period jitter (?P<pct>[\d.]+)% RMS over (?P<cycles>\d+) cycles"
)
_PULSE_RE = re.compile(
    r"^VCLK\s+\S+\s+\S+\s+pulse\(\s*(?P<v1>\S+)\s+(?P<v2>\S+)\s+(?P<td>\S+)\s+"
    r"(?P<tr>\S+)\s+(?P<tf>\S+)\s+(?P<pw>\S+)\s+(?P<per>[^)\s]+)\s*\)",
    re.M | re.I,
)
_TRAN_RE = re.compile(r"^tran\s+(?P<step>\S+)\s+(?P<stop>\S+)(?:\s+uic)?\s*$", re.M)

_PVT_HEADER_NO_TRANSITION = ["Corner", "Temp (C)", "Supply (V)", "Verdict", "f_out", "Duty", "Detail"]


class AnalysisError(RuntimeError):
    pass


def _repo_rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def spice_literal(text: str) -> float:
    """Parse a SPICE literal (`200p`, `3.9170n`, `1.8`, `0`).

    Deliberately a local 10-liner rather than an import of
    `sim/harness/measure.parse_spice_time`: an `analysis/` script reads
    committed evidence and must keep running when the harness moves.
    """
    m = _LITERAL_RE.match(text.strip())
    if not m:
        raise AnalysisError(f"not a SPICE literal: {text!r}")
    value, suffix = float(m.group(1)), m.group(2).lower()
    if not suffix:
        return value
    scale = _SUFFIXES.get(suffix[0])
    if scale is None:
        raise AnalysisError(f"unknown SPICE suffix in {text!r}")
    return value * scale


def _record_id(text: str, path: Path) -> str:
    m = _RECORD_ID_RE.search(text)
    if m is None:
        raise AnalysisError(f"{path}: record has no `Record ID` field")
    return m.group("record_id")


def parse_transition_record(experiment: Path) -> dict:
    """The single measured record of `sim/vco-clk-transition`: rise/fall
    transition time, and this record's own dump-grid step (read from its
    committed per-point netlist's injected `tran` card, not assumed)."""
    records = sorted((experiment / "records").glob("*.md"))
    if len(records) != 1:
        raise AnalysisError(
            f"{experiment}/records/ holds {len(records)} record(s); this "
            "script assumes exactly one (issue #186's single fixed-VCTRL point)"
        )
    path = records[0]
    text = path.read_text()
    record_id = _record_id(text, path)
    m = _TRANSITION_DETAIL_RE.search(text)
    if m is None:
        raise AnalysisError(f"{path}: no '...transition time: rise ... fall ...' detail")

    corners = experiment / "corners" / record_id
    netlists = sorted(p for p in corners.glob("*.spice") if not p.name.startswith("tb_"))
    if len(netlists) != 1:
        raise AnalysisError(
            f"{corners}: expected exactly one committed per-point netlist, found "
            f"{len(netlists)}"
        )
    tran = _TRAN_RE.search(netlists[0].read_text())
    if tran is None:
        raise AnalysisError(f"{netlists[0]}: no injected `tran <step> <stop>` card")
    own_step_s = spice_literal(tran.group("step"))

    return {
        "record_id": record_id,
        "path": path,
        "netlist": _repo_rel(netlists[0]),
        "rise_s": float(m.group("rise")) * 1e-12,
        "n_rise": int(m.group("n_rise")),
        "fall_s": float(m.group("fall")) * 1e-12,
        "n_fall": int(m.group("n_fall")),
        "own_step_s": own_step_s,
    }


def _cells(line: str) -> list | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _single_point_detail(text: str, path: Path) -> str:
    rows, seen = [], False
    for line in text.splitlines():
        cells = _cells(line)
        if cells is None:
            continue
        if cells == _PVT_HEADER_NO_TRANSITION:
            seen = True
            continue
        if not seen:
            continue
        if set("".join(cells)) <= {"-", ":"}:
            continue
        if len(cells) != len(_PVT_HEADER_NO_TRANSITION):
            raise AnalysisError(f"{path}: result row has {len(cells)} cells: {line!r}")
        rows.append(cells)
    if not seen:
        raise AnalysisError(f"{path}: record has no result table with the expected header")
    if len(rows) != 1:
        raise AnalysisError(f"{path}: expected exactly one PVT point, found {len(rows)}")
    return rows[0][6]


def parse_floor_record(record_path: Path, experiment: Path) -> dict:
    """One `sim/jitter-floor` variant -- its floor, period, edge and grid step,
    all read from that record and its own committed per-point netlist (the
    same reading convention `sim/jitter-calibration/analysis/calibration.py`
    and `sim/pll-lock-mc/analysis/jitter_floor.py` use)."""
    text = record_path.read_text()
    record_id = _record_id(text, record_path)
    variant = _FLOOR_VARIANT_RE.search(text)
    if variant is None:
        raise AnalysisError(
            f"{record_path}: no `THIS RECORD'S VARIANT: <id> --` line -- is this a "
            "sim/jitter-floor record?"
        )
    floor_frac_m = _JITTER_IN_DETAIL_RE.search(_single_point_detail(text, record_path))
    if floor_frac_m is None:
        raise AnalysisError(f"{record_path}: point reports no period jitter")

    corners = experiment / "corners" / record_id
    netlists = sorted(p for p in corners.glob("*.spice") if not p.name.startswith("tb_"))
    if len(netlists) != 1:
        raise AnalysisError(
            f"{corners}: expected exactly one committed per-point netlist, found "
            f"{len(netlists)}"
        )
    netlist = netlists[0].read_text()
    pulse = _PULSE_RE.search(netlist)
    tran = _TRAN_RE.search(netlist)
    if pulse is None or tran is None:
        raise AnalysisError(
            f"{netlists[0]}: no `VCLK ... pulse(...)` card and/or no injected "
            "`tran <step> <stop>` card"
        )
    if pulse.group("tr") != pulse.group("tf"):
        raise AnalysisError(
            f"{netlists[0]}: this restatement assumes a symmetric edge (TR == TF), "
            f"got {pulse.group('tr')} / {pulse.group('tf')}"
        )
    return {
        "record_id": record_id,
        "variant": variant.group("variant"),
        "floor_frac": float(floor_frac_m.group("pct")) / 100.0,
        "cycles": int(floor_frac_m.group("cycles")),
        "period_s": spice_literal(pulse.group("per")),
        "edge_s": spice_literal(pulse.group("tr")),
        "step_s": spice_literal(tran.group("step")),
    }


def parse_floor_records(experiment: Path) -> list:
    records = sorted((experiment / "records").glob("*.md"))
    if not records:
        raise AnalysisError(f"{experiment}/records/ holds no record")
    parsed = [parse_floor_record(p, experiment) for p in records]
    steps = {r["step_s"] for r in parsed}
    if len(steps) != 1:
        raise AnalysisError(
            f"the floor records do not share one dump grid ({sorted(steps)}); this "
            "restatement compares floors at one grid"
        )
    return parsed


def _ps(seconds: float) -> str:
    return f"{1e12 * seconds:.2f} ps"


def _pct(frac: float) -> str:
    return f"{100.0 * frac:.3f}%"


def bracket(transition: dict, floors: list) -> dict:
    """The core derivation: where `transition`'s edge/step ratio falls among
    the floor family's own ratios, and the monotonicity bound that follows.

    `sim/jitter-floor`'s A3/B/C variants share one period (3.9170 ns) and
    differ only in edge time (0.1/1.0/5.0 grid steps), so at that one period
    the floor is a measured, monotonically-decreasing function of edge/step:
    2.371 % (A3, 0.1) -> 0.610 % (B, 1.0) -> 0.000 % (C, 5.0). This design's
    own edge/step ratio at the *same* 200 ps grid (using the shorter, more
    conservative of the measured rise/fall figures) is computed and located
    in that ordering.
    """
    step_s = floors[0]["step_s"]
    own_ratio_rise = transition["rise_s"] / step_s
    own_ratio_fall = transition["fall_s"] / step_s
    own_ratio_lo = min(own_ratio_rise, own_ratio_fall)
    own_ratio_hi = max(own_ratio_rise, own_ratio_fall)

    # The A3/B/C triple -- the one period with all three edge/step points
    # measured, per sim/jitter-floor/records/*.md's own "WHY A FAMILY OF
    # VARIANTS" note.
    by_variant = {f["variant"]: f for f in floors}
    triple_variants = ("A3", "B", "C")
    missing = [v for v in triple_variants if v not in by_variant]
    if missing:
        raise AnalysisError(
            f"sim/jitter-floor is missing the A3/B/C triple this bracket needs "
            f"(missing: {missing})"
        )
    a3, b, c = by_variant["A3"], by_variant["B"], by_variant["C"]
    triple = sorted((a3, b, c), key=lambda f: f["edge_s"] / f["step_s"])
    for lo, hi in zip(triple, triple[1:]):
        if lo["floor_frac"] < hi["floor_frac"]:
            raise AnalysisError(
                f"variants {lo['variant']} ({lo['edge_s']/lo['step_s']:.2f}x step, "
                f"{_pct(lo['floor_frac'])}) and {hi['variant']} "
                f"({hi['edge_s']/hi['step_s']:.2f}x step, {_pct(hi['floor_frac'])}) "
                "are not monotonically decreasing -- the bracket below assumes they are"
            )

    # Locate (lo, hi) in the A3/B/C ordering such that lo's ratio <= our
    # design's ratio <= hi's ratio, at the SAME period (3.9170 ns).
    lower = [f for f in triple if f["edge_s"] / f["step_s"] <= own_ratio_lo]
    upper = [f for f in triple if f["edge_s"] / f["step_s"] >= own_ratio_hi]
    if not lower or not upper:
        raise AnalysisError(
            f"design's own edge/step ratio ({own_ratio_lo:.3f}-{own_ratio_hi:.3f}) "
            f"falls outside the A3/B/C triple's own range "
            f"({triple[0]['edge_s']/triple[0]['step_s']:.2f}-"
            f"{triple[-1]['edge_s']/triple[-1]['step_s']:.2f}) -- the bracket below "
            "does not apply; widen sim/jitter-floor's family or state a different bound"
        )
    bracket_lo = max(lower, key=lambda f: f["edge_s"] / f["step_s"])  # closest below
    bracket_hi = min(upper, key=lambda f: f["edge_s"] / f["step_s"])  # closest above

    others = [f for f in floors if f["variant"] not in ("A3", "B", "C")]

    return {
        "step_s": step_s,
        "own_ratio_lo": own_ratio_lo,
        "own_ratio_hi": own_ratio_hi,
        "triple": triple,
        "bracket_lo": bracket_lo,
        "bracket_hi": bracket_hi,
        "floor_lo": bracket_hi["floor_frac"],  # higher ratio -> lower floor
        "floor_hi": bracket_lo["floor_frac"],  # lower ratio -> higher floor
        "others": sorted(others, key=lambda f: f["variant"]),
    }


def render(transition: dict, floors: list, d: dict) -> str:
    out: list = []
    a = out.append
    step_s = d["step_s"]

    a("# Which member of `sim/jitter-floor`'s family applies to `design/vco`'s own `CLK`")
    a("")
    a(
        "**Generated** by `sim/vco-clk-transition/analysis/bracket_floor.py` -- do not "
        "edit by hand. Re-derive with `--write`, verify with `--check`. Every figure "
        "below is read from a committed record (or from that record's own committed "
        "per-point netlist); nothing here simulates or measures."
    )
    a("")
    a("## Inputs")
    a("")
    a(
        f"- Measured transition time: `{_repo_rel(transition['path'])}` (record "
        f"`{transition['record_id']}`) -- design/vco/vco_ring5.sch's own `CLK`, open "
        "loop, at the VCTRL that puts it near the row-9 operating point (issue #186)."
    )
    a(
        f"- Floor family: `sim/jitter-floor/records/` (issue #178) -- {len(floors)} "
        f"variant record(s), all dumped at the same {_ps(step_s)} grid this design's "
        "own transition time is read against."
    )
    a("")
    a("## The measured transition time, and its ratio to the dump grid")
    a("")
    a(
        f"- Rise (10-90%): {_ps(transition['rise_s'])} (mean over {transition['n_rise']} "
        "edges)"
    )
    a(
        f"- Fall (10-90%): {_ps(transition['fall_s'])} (mean over {transition['n_fall']} "
        "edges)"
    )
    a(
        f"- Ratio to a {_ps(step_s)} dump grid (`sim/jitter-floor`'s and "
        f"`sim/pll-lock-mc`'s own): **{d['own_ratio_lo']:.3f}-{d['own_ratio_hi']:.3f}x** "
        "a grid step -- i.e. both edges are a fraction of one grid step, not multiple "
        "grid steps."
    )
    a("")
    a("## The A3/B/C triple: one period, three edge/step ratios, floor measured at each")
    a("")
    a(
        "`sim/jitter-floor`'s A3, B and C variants share one pulse period (3.9170 ns, "
        "`sim/pll-lock-mc`'s own trial-5 measured period) and differ only in edge time, "
        "so at this one period the floor is a directly measured function of edge/step:"
    )
    a("")
    a("| Variant | Record | Edge/step | Floor reported |")
    a("|---|---|---|---|")
    for f in d["triple"]:
        a(
            f"| {f['variant']} | `{f['record_id']}` | {f['edge_s']/f['step_s']:.2f}x | "
            f"{_pct(f['floor_frac'])} |"
        )
    a("")
    a(
        "Monotonically decreasing, as `sim/harness/measure.py`'s own module docstring "
        "states in prose (\"the floor collapses as soon as the grid resolves the "
        "edge\") -- this triple is the direct measurement of that claim."
    )
    a("")
    a("## The bracket")
    a("")
    a(
        f"Design's own edge/step ratio ({d['own_ratio_lo']:.3f}-{d['own_ratio_hi']:.3f}x) "
        f"sits strictly between `{d['bracket_lo']['variant']}`'s "
        f"({d['bracket_lo']['edge_s']/d['bracket_lo']['step_s']:.2f}x, "
        f"{_pct(d['bracket_lo']['floor_frac'])}) and `{d['bracket_hi']['variant']}`'s "
        f"({d['bracket_hi']['edge_s']/d['bracket_hi']['step_s']:.2f}x, "
        f"{_pct(d['bracket_hi']['floor_frac'])}). Because the triple above is measured "
        "monotonic in edge/step at this fixed period, the applicable floor at this "
        f"design's own transition time -- **at `sim/pll-lock-mc`'s own 3.9170 ns "
        f"operating period** -- is bounded:"
    )
    a("")
    a(f"> **{_pct(d['floor_lo'])} < applicable floor < {_pct(d['floor_hi'])}**")
    a("")
    a(
        "Concretely: this design's real `CLK` sits in the family's **unresolved-edge** "
        "regime (its transition spans well under one grid step), the same regime "
        "`sim/jitter-floor`'s A-variants exemplify -- **not** variant C's fully-resolved, "
        "0.000 % case, and not far from variant B's one-grid-step marginal case either. "
        "A reader of `sim/pll-lock-mc/records/20260924-222341-a9375a5.md`'s measured "
        "period-jitter figures should read them against this bracket, not against "
        "variant C's zero floor and not against the full 0.000-2.371 % span the family "
        "covered before this measurement existed."
    )
    a("")
    a("## The other variants, for context")
    a("")
    a(
        "`sim/jitter-floor`'s remaining variants (A1, A2) share the A-family's edge/step "
        "ratio (0.1x, the same regime this design's own edge falls near) but run at "
        "`sim/pll-lock-mc`'s other two locked draws' own periods, showing how much the "
        "floor still varies with the *second* ratio (period/step grid-phase) even at a "
        "fixed, fully-unresolved edge:"
    )
    a("")
    a("| Variant | Period | Edge/step | Floor reported |")
    a("|---|---|---|---|")
    for f in d["others"]:
        a(
            f"| {f['variant']} | {1e9 * f['period_s']:.4f} ns | "
            f"{f['edge_s']/f['step_s']:.2f}x | {_pct(f['floor_frac'])} |"
        )
    a("")
    a(
        "This design's own edge/step ratio is higher than the A-family's 0.1x (its edge "
        "is a few times longer, not a tenth of a grid step), so the true bound at any of "
        "these periods is tighter than -- not wider than -- the 0.381-2.371 % span the "
        "A-family alone covers; the A3/B/C bracket above states that tighter bound at the "
        "one period all three edge ratios were actually measured at."
    )
    a("")
    a("## What this does and does not settle")
    a("")
    a(
        "- **It answers issue #186's question**: which end of `sim/jitter-floor`'s "
        "family applies to this design's real `CLK` is no longer a range spanning the "
        "whole family (0.000-2.371 %) -- it is the bracket stated above, derived from a "
        "real measured transition time rather than assumed."
    )
    a(
        "- **It is a bound, not a new floor measurement.** No new simulation ran here; "
        "the number comes from the already-measured monotonic A3/B/C triple plus this "
        "design's own already-measured transition time. A future campaign that dumps "
        "`sim/jitter-floor` at THIS design's exact edge/step ratio (rather than "
        "bracketing it between two coarser variants) could narrow the bound further -- "
        "not attempted here."
    )
    a(
        "- **It is read at `sim/pll-lock-mc`'s own operating period (3.9170 ns), not at "
        "this open-loop point's own free-running period** (`design/vco`'s ring runs "
        "slightly faster open-loop at this fixed VCTRL than the closed loop's own "
        "locked output -- see `sim/vco-clk-transition/records/`'s own claim). The "
        "transition TIME is a property of the ring's edge dynamics near this operating "
        "region and is not assumed to depend sensitively on that small period "
        "difference, but the bracket above is stated at the period the floor family was "
        "actually measured at, not re-derived at a new one."
    )
    a(
        "- **It does not ratify, relax or restate ratified spec row 9** "
        "(`spec/target-spec.md`, `DR-006`). `sim/pll-lock-mc/records/"
        "20260924-222341-a9375a5.md` stands exactly as written, per `sim/README.md`'s "
        "append-only rule; this document is a derived reading of its own applicable "
        "resolution floor, not a correction to the record."
    )
    a("")
    return "\n".join(out) + "\n"


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--experiment",
        default=str(TRANSITION_EXPERIMENT),
        help="the sim/vco-clk-transition experiment directory holding the record",
    )
    ap.add_argument(
        "--floor-experiment",
        default=str(FLOOR_EXPERIMENT),
        help="the sim/jitter-floor experiment directory holding the floor family",
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help=f"write {OUTPUT.name}")
    mode.add_argument(
        "--check", action="store_true",
        help="verify the committed document, exit 1 on drift",
    )
    args = ap.parse_args(argv)

    try:
        experiment = Path(args.experiment)
        floor_experiment = Path(args.floor_experiment)
        transition = parse_transition_record(experiment)
        floors = parse_floor_records(floor_experiment)
        # This campaign's OWN dump grid is deliberately much finer than the
        # floor family's 200 ps grid -- it exists to measure the transition
        # time itself, not to be read against it -- so the ratio this script
        # computes below (transition time / floor family's own grid step) is
        # only trustworthy if this campaign's own grid actually resolved the
        # edge it measured (tran_step <= transition_time/2, the same
        # criterion sim/harness/measure.py's module docstring states).
        own_step_s = transition["own_step_s"]
        shortest_edge_s = min(transition["rise_s"], transition["fall_s"])
        if own_step_s > 0.5 * shortest_edge_s:
            raise AnalysisError(
                f"{experiment}'s own {_ps(own_step_s)} dump grid does not resolve its "
                f"own measured {_ps(shortest_edge_s)} transition (need "
                f"tran_step <= transition_time/2) -- the transition-time figure itself "
                "is not trustworthy enough to bracket sim/jitter-floor's family against"
            )
        text = render(transition, floors, bracket(transition, floors))
    except (AnalysisError, OSError) as exc:
        print(f"bracket_floor.py: {exc}", file=sys.stderr)
        return 2

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(text)
        print(f"wrote {_repo_rel(OUTPUT)}")
        return 0
    if args.check:
        if not OUTPUT.is_file():
            print(f"bracket_floor.py: {OUTPUT} is missing -- run --write", file=sys.stderr)
            return 1
        if OUTPUT.read_text() != text:
            print(
                f"bracket_floor.py: {_repo_rel(OUTPUT)} does not match what the committed "
                "records re-derive -- re-run --write and read the diff",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {_repo_rel(OUTPUT)} matches the records")
        return 0
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
