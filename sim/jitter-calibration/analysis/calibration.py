#!/usr/bin/env python3
"""Restate this campaign's records as a reported-vs-injected calibration curve.

`sim/jitter-floor/` (issue #178) measures what `sim/harness/measure.py`'s
period-jitter reducer reports for a signal whose true period jitter is **zero**.
That is a *null* control: it bounds the measurement floor, but its edges arrive
at grid phases that walk deterministically by `frac(period/step)` and by nothing
else, so it cannot say what the pipeline does to a signal that genuinely jitters
(issue #185).

`sim/jitter-calibration/` does. Its source is a PWL clock whose rising-edge
schedule was drawn from a seeded RNG at an exactly specified nonzero RMS period
jitter and written edge by edge into the netlist. This script reads the injected
figure back out of that netlist, pairs it with the figure the reducer reported,
and renders the calibration curve.

It is an `analysis/` script in the sense `sim/README.md` defines: mutable,
stdlib-only, it reads committed records and restates what they already say, and
it **never** simulates, never reads a waveform dump, and never introduces a
measured number of its own. Its inputs are:

  * `sim/jitter-calibration/records/*.md` -- one record per variant, each
    reporting the period jitter the reducer attributed to that variant's clock
    (at the record's own printed precision -- three decimals of a percent).
  * `sim/jitter-calibration/corners/<record-id>/*.spice` -- the same records'
    own committed per-point netlists, read for what is otherwise only in prose:
    the `VCLK ... pwl(...)` edge schedule (which **is** the injected figure --
    see `injected_from_pwl` below), the variant label the generator stamped
    into it, and the injected `tran <step> <stop>` card (the dump grid).
  * `sim/jitter-floor/records/*.md` and their own per-point netlists -- the
    null control's floor at the matching period and transition time, so the two
    controls are read against each other rather than side by side.

All of these are committed evidence of the same runs as the records beside
them, per `sim/README.md`'s retention table, so reading them is not reaching
outside the evidence trail.

## What the document derives, and why each derivation is defensible

1. **The injected figure, re-derived rather than trusted.** The PWL card gives
   every rising 50 % crossing exactly (each is the midpoint of a symmetric
   `0 -> 1.8 V` ramp), so `pstdev(T_k)/mean(T_k)` over that schedule -- the
   *same* estimator `measure.period_jitter` applies to the reduced edges -- is
   the exact figure the source carried. Nothing here takes the generator's or
   the manifest's word for it.

2. **The implied floor, `sqrt(reported^2 - injected^2)`.** The grid's
   quantization error is independent of the source's own jitter and adds to it
   in quadrature, so this is the floor the pipeline carried *for a signal that
   actually jitters* -- the quantity issue #185 says the null control cannot
   reach. Reported *below* injected is printed as such (no value), never as a
   negative or a zero floor.

3. **The null control's floor, for comparison.** `sim/jitter-floor`'s record at
   the same nominal period and the same transition time. The difference between
   it and the implied floor of (2) is exactly what #185 predicted would exist
   and could not quantify.

4. **The two grid-arithmetic bounds**, printed with their formulas so a reader
   can check them: `step*sqrt(f*(1-f))` (the walk-phase case a perfectly
   periodic clock produces, `f = frac(period/step)`) and `sqrt(2)*step/sqrt(12)`
   (independent, uniformly-spread grid phases, the case a signal whose jitter
   is large compared with the grid approaches).

Usage:

    # print the calibration document to stdout
    python3 sim/jitter-calibration/analysis/calibration.py

    # (re)write sim/jitter-calibration/analysis/calibration.md
    python3 sim/jitter-calibration/analysis/calibration.py --write

    # re-derive and verify the committed document (exit 1 on any drift)
    python3 sim/jitter-calibration/analysis/calibration.py --check

Standard library only, same convention as `sim/run_corners.py` and the other
`analysis/` scripts under `sim/`. No PDK, ngspice, xschem or `klt` required,
and -- like `sim/pll-lock-mc/analysis/jitter_floor.py` -- deliberately no
import of `sim/harness/`: an `analysis/` script reads committed evidence and
must keep running when the harness moves.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from statistics import fmean, pstdev

REPO_ROOT = Path(__file__).resolve().parents[3]
CALIBRATION_EXPERIMENT = REPO_ROOT / "sim" / "jitter-calibration"
FLOOR_EXPERIMENT = REPO_ROOT / "sim" / "jitter-floor"
OUTPUT = Path(__file__).resolve().parent / "calibration.md"

#: Ratified spec row 9 (`DR-006`), as a fraction of the output period. Used
#: only for scale in the rendered table -- this campaign measures no spec row
#: and states no verdict on one.
ROW_9_MAX_FRAC = 0.01

#: The comparison threshold `measure.py` used, as a fraction of the rail. The
#: PWL ramps are symmetric, so a 0.5 threshold puts every crossing at the
#: ramp's exact midpoint; `injected_from_pwl` asserts this rather than
#: assuming it silently.
THRESHOLD_FRAC = 0.5

_SUFFIXES = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}
_LITERAL_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z]*)$")

_RECORD_ID_RE = re.compile(r"^- \*\*Record ID\*\*: (?P<record_id>\S+)\s*$", re.M)
_JITTER_IN_DETAIL_RE = re.compile(
    r"period jitter (?P<pct>[\d.]+)% RMS over (?P<cycles>\d+) cycles"
)
_TRAN_RE = re.compile(r"^tran\s+(?P<step>\S+)\s+(?P<stop>\S+)\s*$", re.M)
_PWL_VARIANT_RE = re.compile(r"^\*\* GENERATED -- variant (?P<variant>[A-Za-z0-9]+):", re.M)
_PWL_HEAD_RE = re.compile(r"^VCLK\s+\S+\s+\S+\s+pwl\([ \t]*\r?\n", re.M | re.I)
_PULSE_RE = re.compile(
    r"^VCLK\s+\S+\s+\S+\s+pulse\(\s*(?P<v1>\S+)\s+(?P<v2>\S+)\s+(?P<td>\S+)\s+"
    r"(?P<tr>\S+)\s+(?P<tf>\S+)\s+(?P<pw>\S+)\s+(?P<per>[^)\s]+)\s*\)",
    re.M | re.I,
)
_FLOOR_VARIANT_RE = re.compile(r"THIS RECORD'S VARIANT: (?P<variant>[A-Za-z0-9]+) --")

_PVT_HEADER = ["Corner", "Temp (C)", "Supply (V)", "Verdict", "f_out", "Duty", "Detail"]

#: Two periods (or transition times) closer together than this fraction are the
#: same operating point for the purpose of pairing a calibration variant with a
#: null-control variant. The two campaigns declare these numbers independently
#: (a `pwl` schedule vs. a `pulse` card), so an exact float match is the wrong
#: test; 0.1 % is far tighter than the spacing of any variant in either family.
_MATCH_TOL = 1e-3


class AnalysisError(RuntimeError):
    pass


def _repo_rel(path: Path) -> str:
    """`path` relative to the repo root when it is inside it, else as-is."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def spice_literal(text: str) -> float:
    """Parse a SPICE literal (`200p`, `3.9170n`, `1.8`, `0`).

    Deliberately a local 10-liner rather than an import of
    `sim/harness/measure.parse_spice_time`: an `analysis/` script reads
    committed evidence and must keep running when the harness moves, so it
    takes no dependency on the harness package.
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


def _cells(line: str) -> list | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _single_point_detail(text: str, path: Path) -> str:
    """The `Detail` cell of a record whose result table holds exactly one row."""
    rows, seen = [], False
    for line in text.splitlines():
        cells = _cells(line)
        if cells is None:
            continue
        if cells == _PVT_HEADER:
            seen = True
            continue
        if not seen:
            continue
        if set("".join(cells)) <= {"-", ":"}:
            continue
        if len(cells) != len(_PVT_HEADER):
            raise AnalysisError(f"{path}: result row has {len(cells)} cells: {line!r}")
        rows.append(cells)
    if not seen:
        raise AnalysisError(f"{path}: record has no result table with the expected header")
    if len(rows) != 1:
        raise AnalysisError(f"{path}: expected exactly one PVT point, found {len(rows)}")
    return rows[0][6]


def _record_id(text: str, path: Path) -> str:
    m = _RECORD_ID_RE.search(text)
    if m is None:
        raise AnalysisError(f"{path}: record has no `Record ID` field")
    return m.group("record_id")


def _reported(text: str, path: Path) -> tuple:
    detail = _single_point_detail(text, path)
    m = _JITTER_IN_DETAIL_RE.search(detail)
    if m is None:
        raise AnalysisError(f"{path}: point reports no period jitter: {detail!r}")
    return float(m.group("pct")) / 100.0, int(m.group("cycles"))


def _point_netlist(experiment: Path, record_id: str) -> Path:
    corners = experiment / "corners" / record_id
    netlists = sorted(p for p in corners.glob("*.spice") if not p.name.startswith("tb_"))
    if len(netlists) != 1:
        raise AnalysisError(
            f"{corners}: expected exactly one committed per-point netlist, found "
            f"{len(netlists)}"
        )
    return netlists[0]


def _tran(netlist: str, path: Path) -> tuple:
    m = _TRAN_RE.search(netlist)
    if m is None:
        raise AnalysisError(f"{path}: no injected `tran <step> <stop>` card")
    return spice_literal(m.group("step")), spice_literal(m.group("stop"))


def pwl_points(netlist: str, path: Path) -> list:
    """The `(time_s, volts)` pairs of the committed `VCLK ... pwl(...)` card."""
    m = _PWL_HEAD_RE.search(netlist)
    if m is None:
        raise AnalysisError(
            f"{path}: no `VCLK <n+> <n-> pwl(` card -- is this a "
            "sim/jitter-calibration per-point netlist?"
        )
    points: list = []
    lines = netlist[m.end():].splitlines()
    closed = False
    for line in lines:
        body = line.strip()
        if not body.startswith("+"):
            raise AnalysisError(f"{path}: `pwl(` card ends without a closing `+ )` line")
        body = body[1:].strip()
        if body == ")":
            closed = True
            break
        fields = body.split()
        if len(fields) % 2:
            raise AnalysisError(
                f"{path}: `pwl(` continuation line has an odd field count: {line!r}"
            )
        for t_text, v_text in zip(fields[0::2], fields[1::2]):
            points.append((spice_literal(t_text), spice_literal(v_text)))
    if not closed:
        raise AnalysisError(f"{path}: `pwl(` card is never closed")
    if len(points) < 4:
        raise AnalysisError(f"{path}: `pwl(` card holds only {len(points)} points")
    times = [t for t, _ in points]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise AnalysisError(f"{path}: `pwl(` times are not strictly increasing")
    return points


def injected_from_pwl(points: list, path: Path) -> dict:
    """The exact figure the committed edge schedule injects.

    Every rising segment of the card runs from `v_low` to `v_high` linearly, so
    the `threshold_frac * v_high` crossing sits at the segment's midpoint when
    `threshold_frac` is 0.5 -- which is what this campaign's manifest declares
    and what `_assert_threshold` pins. The returned `injected_frac` is
    `pstdev(T_k)/mean(T_k)` over those crossings: the **same** estimator
    `sim/harness/measure.period_jitter` applies to the reduced edges, so the
    reported and injected figures are the same quantity and are comparable
    without any conversion.
    """
    v_high = max(v for _, v in points)
    v_low = min(v for _, v in points)
    if v_high <= v_low:
        raise AnalysisError(f"{path}: `pwl(` card does not swing")
    rising, edge_widths = [], []
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if v0 == v_low and v1 == v_high:
            rising.append(0.5 * (t0 + t1))
            edge_widths.append(t1 - t0)
    if len(rising) < 3:
        raise AnalysisError(
            f"{path}: `pwl(` card holds only {len(rising)} rising transitions"
        )
    if max(edge_widths) - min(edge_widths) > 1e-15:
        raise AnalysisError(
            f"{path}: this restatement assumes one transition time for the whole "
            f"schedule, got {min(edge_widths):g}..{max(edge_widths):g} s"
        )
    periods = [b - a for a, b in zip(rising, rising[1:])]
    mean_period = fmean(periods)
    if mean_period <= 0:
        raise AnalysisError(f"{path}: the committed schedule has a non-positive period")
    return {
        "injected_frac": pstdev(periods) / mean_period,
        "period_s": mean_period,
        "edge_s": edge_widths[0],
        "cycles": len(periods),
        "v_high": v_high,
        "v_low": v_low,
    }


def parse_calibration_record(record_path: Path, experiment: Path) -> dict:
    """One `sim/jitter-calibration` variant: what it injected and what came back."""
    text = record_path.read_text()
    record_id = _record_id(text, record_path)
    reported_frac, reported_cycles = _reported(text, record_path)

    netlist_path = _point_netlist(experiment, record_id)
    netlist = netlist_path.read_text()
    variant = _PWL_VARIANT_RE.search(netlist)
    if variant is None:
        raise AnalysisError(
            f"{netlist_path}: no `** GENERATED -- variant <id>:` line -- is this a "
            "sim/jitter-calibration per-point netlist?"
        )
    step_s, stop_s = _tran(netlist, netlist_path)
    schedule = injected_from_pwl(pwl_points(netlist, netlist_path), netlist_path)

    if reported_cycles != schedule["cycles"]:
        raise AnalysisError(
            f"{record_path}: the reducer formed a {reported_cycles}-cycle population "
            f"but the committed schedule holds {schedule['cycles']} periods -- the "
            "reported and injected figures are not over the same population"
        )
    return {
        "record_id": record_id,
        "path": record_path,
        "netlist": _repo_rel(netlist_path),
        "variant": variant.group("variant"),
        "reported_frac": reported_frac,
        "cycles": reported_cycles,
        "step_s": step_s,
        "stop_s": stop_s,
        **schedule,
    }


def parse_floor_record(record_path: Path, experiment: Path) -> dict:
    """One `sim/jitter-floor` null-control variant, for comparison."""
    text = record_path.read_text()
    record_id = _record_id(text, record_path)
    variant = _FLOOR_VARIANT_RE.search(text)
    if variant is None:
        raise AnalysisError(
            f"{record_path}: no `THIS RECORD'S VARIANT: <id> --` line -- is this a "
            "sim/jitter-floor record?"
        )
    floor_frac, cycles = _reported(text, record_path)
    netlist_path = _point_netlist(experiment, record_id)
    netlist = netlist_path.read_text()
    pulse = _PULSE_RE.search(netlist)
    if pulse is None:
        raise AnalysisError(f"{netlist_path}: no `VCLK ... pulse(...)` card")
    if pulse.group("tr") != pulse.group("tf"):
        raise AnalysisError(
            f"{netlist_path}: this restatement assumes a symmetric edge (TR == TF), "
            f"got {pulse.group('tr')} / {pulse.group('tf')}"
        )
    step_s, _ = _tran(netlist, netlist_path)
    return {
        "record_id": record_id,
        "variant": variant.group("variant"),
        "floor_frac": floor_frac,
        "cycles": cycles,
        "period_s": spice_literal(pulse.group("per")),
        "edge_s": spice_literal(pulse.group("tr")),
        "step_s": step_s,
    }


def _parse_all(experiment: Path, parse) -> list:
    records = sorted((experiment / "records").glob("*.md"))
    if not records:
        raise AnalysisError(f"{experiment}/records/ holds no record")
    return [parse(p, experiment) for p in records]


def _assert_threshold(manifest_text: str) -> None:
    """The manifest must still measure at the ramp midpoint.

    `injected_from_pwl` reads each rising crossing off as the midpoint of a
    symmetric ramp, which is only the measured instant while the manifest's
    `threshold_frac` is 0.5 of a rail equal to the PWL card's own high value.
    """
    if f'"threshold_frac": {THRESHOLD_FRAC}' not in manifest_text:
        raise AnalysisError(
            "sim/jitter-calibration/testbench/tb.json no longer measures at "
            f"threshold_frac {THRESHOLD_FRAC}; the injected figure this script "
            "re-derives assumes the 50 % crossing is the ramp midpoint. Fix one "
            "of them; do not restate against a drifted threshold"
        )


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= _MATCH_TOL * max(abs(a), abs(b), 1e-30)


def match_floor(row: dict, floors: list) -> dict | None:
    """The null-control variant at this row's own period and transition time."""
    candidates = [
        f for f in floors
        if _close(f["period_s"], row["period_s"])
        and _close(f["edge_s"], row["edge_s"])
        and _close(f["step_s"], row["step_s"])
    ]
    if not candidates:
        return None
    if len(candidates) > 1:
        raise AnalysisError(
            f"variant {row['variant']}: {len(candidates)} null-control variants "
            "share its period, transition time and dump grid -- cannot pick one"
        )
    return candidates[0]


def restate(rows: list, floors: list) -> dict:
    steps = {r["step_s"] for r in rows}
    if len(steps) != 1:
        raise AnalysisError(
            f"the calibration records do not share one dump grid ({sorted(steps)}); "
            "this restatement compares reported-vs-injected at one grid"
        )
    periods = {round(r["period_s"], 15) for r in rows}
    if len(periods) != 1:
        raise AnalysisError(
            f"the calibration records do not share one nominal period ({sorted(periods)}); "
            "the grid-phase arithmetic below is period-specific"
        )
    step_s = rows[0]["step_s"]
    period_s = rows[0]["period_s"]
    ratio = period_s / step_s
    f_phase = ratio - math.floor(ratio)

    derived = []
    for row in sorted(rows, key=lambda r: (r["edge_s"], r["injected_frac"])):
        reported_s = row["reported_frac"] * row["period_s"]
        injected_s = row["injected_frac"] * row["period_s"]
        implied_s = (
            math.sqrt(reported_s**2 - injected_s**2) if reported_s > injected_s else None
        )
        floor = match_floor(row, floors)
        null_s = None if floor is None else floor["floor_frac"] * floor["period_s"]
        if null_s is not None and reported_s > null_s:
            null_removed_s: float | None = math.sqrt(reported_s**2 - null_s**2)
        else:
            null_removed_s = None
        derived.append(
            {
                **row,
                "reported_s": reported_s,
                "injected_s": injected_s,
                "implied_floor_s": implied_s,
                "implied_floor_frac": None if implied_s is None else implied_s / row["period_s"],
                "floor": floor,
                "null_floor_s": null_s,
                "null_removed_s": null_removed_s,
                "null_removed_frac": (
                    None if null_removed_s is None else null_removed_s / row["period_s"]
                ),
                "inflation": row["reported_frac"] / row["injected_frac"],
            }
        )
    return {
        "step_s": step_s,
        "period_s": period_s,
        "f_phase": f_phase,
        "walk_phase_s": step_s * math.sqrt(f_phase * (1.0 - f_phase)),
        "uniform_phase_s": math.sqrt(2.0) * step_s / math.sqrt(12.0),
        "rows": derived,
    }


def _pct(frac: float | None) -> str:
    return "-" if frac is None else f"{100.0 * frac:.3f}%"


def _ps(seconds: float | None) -> str:
    return "-" if seconds is None else f"{1e12 * seconds:.1f} ps"


def _edge(seconds: float) -> str:
    return f"{1e12 * seconds:g} ps" if seconds < 1e-9 else f"{1e9 * seconds:g} ns"


def render(rows: list, floors: list, derived: dict) -> str:
    step_s = derived["step_s"]
    period_s = derived["period_s"]
    out: list = []
    a = out.append

    a("# What this pipeline reports when the signal really jitters")
    a("")
    a(
        "**Generated** by `sim/jitter-calibration/analysis/calibration.py` -- do not "
        "edit by hand. Re-derive with `--write`, verify with `--check`. Every figure "
        "below is read from a committed record (or from that record's own committed "
        "per-point netlist); nothing here simulates or measures."
    )
    a("")
    a("## Inputs")
    a("")
    a(
        f"- Calibration: `sim/jitter-calibration/records/` -- {len(rows)} variant "
        "record(s). Each one's source is a PWL clock whose rising-edge schedule was "
        "drawn from a seeded RNG at an exactly specified RMS period jitter and written "
        "edge by edge into the netlist, so the **injected** column below is re-derived "
        "from the committed netlist rather than taken on trust: it is "
        "`pstdev(T_k)/mean(T_k)` over the card's own 50 % crossings, the same estimator "
        "`sim/harness/measure.period_jitter` applies to the reduced edges."
    )
    a(
        f"- Null control, for comparison: `sim/jitter-floor/records/` -- {len(floors)} "
        "variant record(s) of an ideal pulse source of exactly constant period (true "
        "period jitter zero by construction)."
    )
    a(
        f"- Both at a {1e12 * step_s:.0f} ps dump grid and a "
        f"{1e9 * period_s:.4f} ns nominal period, so every figure below is one "
        "operating point's."
    )
    a("")
    a("## The calibration curve")
    a("")
    a(
        "`Injected` is what the source carried; `Reported` is what the reducer said; "
        "`Implied floor` is `sqrt(reported^2 - injected^2)`, the measurement error this "
        "pipeline actually added to a signal that jitters. `Null-control floor` is what "
        "`sim/jitter-floor` measured at the *same* period and transition time, for a "
        "signal that does not."
    )
    a("")
    a(
        "| Variant | Record | Edge (TR=TF) | Edge / grid step | Injected | Reported | "
        "Reported / injected | Implied floor | Null-control floor (variant) |"
    )
    a("|---|---|---|---|---|---|---|---|---|")
    for r in derived["rows"]:
        floor = r["floor"]
        null_cell = (
            "-- (no null-control variant at this edge)"
            if floor is None
            else f"{_pct(floor['floor_frac'])} ({_ps(r['null_floor_s'])}, {floor['variant']})"
        )
        a(
            f"| {r['variant']} | `{r['record_id']}` | {_edge(r['edge_s'])} | "
            f"{r['edge_s'] / step_s:.2f} | {_pct(r['injected_frac'])} "
            f"({_ps(r['injected_s'])}) | {_pct(r['reported_frac'])} "
            f"({_ps(r['reported_s'])}) | {r['inflation']:.2f}x | "
            f"{_pct(r['implied_floor_frac'])} ({_ps(r['implied_floor_s'])}) | "
            f"{null_cell} |"
        )
    a("")
    a("## Reading it")
    a("")
    resolved = [r for r in derived["rows"] if r["edge_s"] >= 2.0 * step_s]
    if resolved:
        worst = max(abs(r["reported_frac"] - r["injected_frac"]) for r in resolved)
        a(
            f"- **An edge the grid resolves costs nothing.** For the "
            f"{len(resolved)} variant(s) whose transition spans two or more grid "
            "samples, the reported figure matches the injected one to within "
            f"{100.0 * worst:.3f} pp -- the two samples that bracket the 50 % crossing "
            "both sit on the (straight) ramp, so `measure.edge_times._interpolate_back` "
            "recovers the crossing exactly and the reducer is unbiased. This is also "
            "the check that the injected figure is what this campaign says it is: the "
            "generator, the netlist, the reducer and this script agree on a number "
            "none of them could fake independently."
        )
    unresolved = [r for r in derived["rows"] if r["edge_s"] < 2.0 * step_s]
    if unresolved:
        a(
            f"- **An edge it cannot resolve costs a floor that does not vanish as the "
            "injected figure shrinks.** For the "
            f"{len(unresolved)} variant(s) below two grid samples, the reported figure "
            "is inflated by "
            f"{min(r['inflation'] for r in unresolved):.2f}x to "
            f"{max(r['inflation'] for r in unresolved):.2f}x. Read the `Implied floor` "
            "column rather than the inflation factor: the floor is roughly constant in "
            "absolute time while the injected figure is not, which is exactly why a "
            "small true jitter is inflated most."
        )
    a("")
    a("## The null control's floor is not this floor -- which is the point of #185")
    a("")
    a(
        "A jitter-free source's edges walk through grid phase deterministically, by "
        f"`frac(period/step)` = {derived['f_phase']:.3f} of a step per period and by "
        "nothing else. A source that genuinely jitters spreads them further, and the "
        "two distributions have different spreads -- so the null control's floor is a "
        "different quantity from the floor a real signal carries, not a conservative "
        "version of it. Neither of the two bounds below is measured; both are "
        f"arithmetic on this {1e12 * step_s:.0f} ps grid, printed with their formulas:"
    )
    a("")
    a(
        f"- `step * sqrt(f*(1-f))` at `f = {derived['f_phase']:.3f}` = "
        f"**{_ps(derived['walk_phase_s'])}** -- the walk-phase case, i.e. what an "
        "unresolved edge on a *perfectly periodic* clock carries at this period. This "
        "is the regime `sim/jitter-floor` measures."
    )
    a(
        f"- `sqrt(2)*step/sqrt(12)` = `0.41*step` = "
        f"**{_ps(derived['uniform_phase_s'])}** -- independent, uniformly-spread grid "
        "phases, the case a signal whose jitter is large compared with the grid "
        "approaches."
    )
    a("")
    a(
        "Against those two, the floors this campaign actually implied. Only the "
        "**fully unresolved** variants are listed -- an edge shorter than half a grid "
        "step, where the bracketing sample pair straddles the whole transition and the "
        "arithmetic above is the applicable model. The one-grid-step variants sit in an "
        "intermediate regime (the pair sometimes lands on the ramp), so neither bound "
        "describes them and they are deliberately not scored against either."
    )
    a("")
    a(
        "| Variant | Injected | Injected / grid step | Implied floor | vs. walk-phase | "
        "vs. uniform-phase |"
    )
    a("|---|---|---|---|---|---|")
    unresolved_scored = [
        r for r in derived["rows"]
        if r["edge_s"] <= 0.5 * step_s and r["implied_floor_s"] is not None
    ]
    for r in unresolved_scored:
        a(
            f"| {r['variant']} | {_pct(r['injected_frac'])} ({_ps(r['injected_s'])}) | "
            f"{r['injected_s'] / step_s:.2f} | {_ps(r['implied_floor_s'])} | "
            f"{r['implied_floor_s'] / derived['walk_phase_s']:.2f}x | "
            f"{r['implied_floor_s'] / derived['uniform_phase_s']:.2f}x |"
        )
    a("")
    if len(unresolved_scored) >= 2:
        lo = min(unresolved_scored, key=lambda r: r["injected_s"])
        hi = max(unresolved_scored, key=lambda r: r["injected_s"])
        toward_uniform = abs(hi["implied_floor_s"] - derived["uniform_phase_s"]) < abs(
            lo["implied_floor_s"] - derived["uniform_phase_s"]
        )
        a(
            "The trend across that table is the finding, and it is read off the table "
            "rather than asserted: going from the smallest injected figure "
            f"({lo['variant']}, {_pct(lo['injected_frac'])}, implied floor "
            f"{_ps(lo['implied_floor_s'])} = "
            f"{lo['implied_floor_s'] / derived['uniform_phase_s']:.2f}x the "
            "uniformly-spread-phase bound) to the largest "
            f"({hi['variant']}, {_pct(hi['injected_frac'])}, "
            f"{_ps(hi['implied_floor_s'])} = "
            f"{hi['implied_floor_s'] / derived['uniform_phase_s']:.2f}x), the floor a "
            "jittering signal carries moves "
            + ("**toward**" if toward_uniform else "**away from**")
            + " the uniformly-spread-phase figure and "
            + ("away from" if toward_uniform else "toward")
            + " the walk-phase figure the null control measures. That is the crossover "
            "issue #185 predicted must exist: a source whose jitter is small compared "
            "with the grid step still presents the constant-period walk, and one whose "
            "jitter is comparable to it does not."
        )
        a("")
        a(
            "So a floor read off `sim/jitter-floor` and applied to a signal that really "
            "jitters is an approximation, and **its sign is not guaranteed**. At this "
            f"period the walk-phase floor ({_ps(derived['walk_phase_s'])}) is the "
            f"*larger* of the two bounds, so the null control over-states the floor for "
            "a strongly jittering signal and over-corrects it; at a period whose "
            "`frac(period/step)` is nearer 0 or 1 the walk-phase floor is the smaller "
            "one and the error runs the other way. Neither direction is conservative by "
            "construction, which is why the correction wanted a measurement rather than "
            "an argument."
        )
    a("")
    a("## Using this to read a measured figure")
    a("")
    a(
        "For a measured figure `m` at this grid and period, with an unresolved edge, "
        "the true figure is `sqrt(m^2 - floor^2)` with `floor` taken from the "
        "`Implied floor` column at a comparable injected magnitude (the floor is mildly "
        "magnitude-dependent, per the table above) -- and **no value at all** when "
        "`m <= floor`, which is the honest statement of \"this measurement cannot "
        "separate the signal from its own measurement\". For a resolved edge no "
        "correction is needed. For scale: ratified spec row 9's bound is "
        f"{100.0 * ROW_9_MAX_FRAC:.1f} % of the output period, "
        f"{_ps(ROW_9_MAX_FRAC * period_s)} at this period, against a grid step of "
        f"{_ps(step_s)}."
    )
    a("")
    a("## What this does and does not settle")
    a("")
    a(
        "- **It calibrates the reducer, not the PLL.** This campaign's DUT is a voltage "
        "source and a resistor. It measures no `spec/target-spec.md` row, states no "
        "verdict on one, and ratifies nothing -- see its manifest's `spec_rows_note`."
    )
    a(
        "- **Its injected jitter is white.** Independent Gaussian period to period: no "
        "correlation, no wander, no deterministic or spur component. A correlated "
        "source presents a different grid-phase distribution again, and this campaign "
        "says nothing about it."
    )
    a(
        f"- **One period and one grid.** {1e9 * period_s:.4f} ns at "
        f"{1e12 * step_s:.0f} ps. The grid-phase arithmetic is period-specific "
        "(`f = frac(period/step)`), so these numbers transfer to another period only "
        "through that arithmetic, never by assumption."
    )
    a(
        f"- **Sampling error is not zero.** Each figure is over a "
        f"{derived['rows'][0]['cycles']}-cycle population, so the *reported* column "
        f"carries roughly `1/sqrt(2N)` = "
        f"{100.0 / math.sqrt(2.0 * derived['rows'][0]['cycles']):.1f} % relative error. "
        "The *injected* column carries none: it is exact by construction (the "
        "generator normalizes its draw to the stated RMS) and re-derived here from the "
        "committed schedule."
    )
    a(
        "- **It does not establish which variant the real DUT is in.** Nothing "
        "committed here states `design/vco`'s `CLK` transition time at the row-9 "
        "operating point (issue #186), so the applicable row of the table above cannot "
        "be read off without that measurement -- the same gap `sim/jitter-floor`'s "
        "records name."
    )
    a("")
    return "\n".join(out) + "\n"


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--experiment",
        default=str(CALIBRATION_EXPERIMENT),
        help="the sim/jitter-calibration experiment directory holding the records",
    )
    ap.add_argument(
        "--floor-experiment",
        default=str(FLOOR_EXPERIMENT),
        help="the sim/jitter-floor experiment directory holding the null control",
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
        _assert_threshold((experiment / "testbench" / "tb.json").read_text())
        rows = _parse_all(experiment, parse_calibration_record)
        floors = _parse_all(Path(args.floor_experiment), parse_floor_record)
        text = render(rows, floors, restate(rows, floors))
    except (AnalysisError, OSError) as exc:
        print(f"calibration.py: {exc}", file=sys.stderr)
        return 2

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(text)
        print(f"wrote {_repo_rel(OUTPUT)}")
        return 0
    if args.check:
        if not OUTPUT.is_file():
            print(f"calibration.py: {OUTPUT} is missing -- run --write", file=sys.stderr)
            return 1
        if OUTPUT.read_text() != text:
            print(
                f"calibration.py: {_repo_rel(OUTPUT)} does not match what the committed "
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
