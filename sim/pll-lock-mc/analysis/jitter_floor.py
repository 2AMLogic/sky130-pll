#!/usr/bin/env python3
"""Restate this campaign's measured period jitter against the measured floor.

`sim/pll-lock-mc/records/20260924-222341-a9375a5.md` reports three locked draws
at 1.584 %, 1.851 % and 3.073 % RMS period jitter against **ratified** spec
row 9's 1.0 % bound (`DR-006`) -- a recorded miss. That record also states, in
its own limitations, that it cannot separate those figures from the resolution
floor its 200 ps dump grid puts under them, because nothing in the repo had
quantified that floor (issue #178).

`sim/jitter-floor/` now has. This script restates the three figures against it.

It is an `analysis/` script in the sense `sim/README.md` defines: mutable,
stdlib-only, it reads committed records and restates what they already say, and
it **never** simulates, never reads a waveform dump, and never introduces a
measured number of its own. Its inputs are:

  * `sim/pll-lock-mc/records/<record-id>.md` -- the per-trial table: which
    draws locked, at what post-lock output frequency, with what period jitter
    (at the record's own printed precision -- three decimals of a percent, i.e.
    +/-0.0005 pp).
  * `sim/jitter-floor/records/*.md` -- one record per variant of the null
    control, each reporting the period jitter the identical reducer attributes
    to an ideal pulse source whose true period jitter is zero.
  * `sim/jitter-floor/corners/<record-id>/*.spice` -- the same records' own
    committed per-point netlists, read for the two numbers that define each
    variant and are otherwise only in prose: the `VCLK ... pulse(...)` card
    (the exactly-constant period and the transition time) and the injected
    `tran <step> <stop>` card (the dump grid). These are committed evidence of
    the same run as the record beside them, per `sim/README.md`'s retention
    table, so reading them is not reaching outside the evidence trail.

## The two derivations, and why each is defensible

1. **Quadrature removal.** The grid-quantization error is independent per edge
   and independent of the circuit's own jitter, so it adds to the true period
   spread in quadrature: `sigma_measured^2 = sigma_true^2 + sigma_floor^2`.
   The restatement therefore reports `sqrt(measured^2 - floor^2)` -- and
   reports *no value at all* when `measured <= floor`, which is the honest
   statement of "this measurement cannot separate the circuit from its own
   measurement", never a jitter of zero.

2. **The unresolved-edge quantization bound.** For an edge the grid cannot
   resolve at all, the interpolated crossing is quantized to the middle of
   whichever grid interval contains it, so its per-edge error is bounded by
   half a grid step and the per-period floor is of order `0.4-0.5 * step` RMS:
   exactly `step * sqrt(f*(1-f))` for a perfectly periodic clock of `(k+f)`
   steps -- maximum `step/2` at `f = 0.5` -- and `sqrt(2)*step/sqrt(12)` =
   `0.41*step` for edges arriving at independent, uniformly-spread grid phases,
   which is what a signal with real jitter comparable to the grid approaches
   and what the null control's deterministic phase walk does not reproduce.
   Both are arithmetic on the grid step the records themselves declare, not
   measurements, and both are printed with their formulas so a reader can
   check them. The restatement uses the *larger* of the two as its robustness
   test, so its conclusion does not depend on which regime applies.

## Why the calibration campaign is read but never used to pick one corrected number (issues #193, #205)

`sim/jitter-calibration` (issue #185) measures the regime above directly, with
a known nonzero injected jitter. This script reads its records -- to check,
per draw, whether a calibration variant exists at that draw's own measured
period, and, where one does, to bracket the residual over that family's whole
measured implied-floor range -- and, per the decision argued in the rendered
restatement's own "Why this restatement declines..." section, still declines
to *interpolate* a single calibrated floor and apply it as a correction. Two
grounds were originally argued for declining outright: applying a floor
measured at one period to a draw at a different one smuggles in an assumption
this repo had not tested (`calibration.md` finds the null control's own error
changes *sign* with `frac(period/step)`), and indexing a magnitude-dependent
floor by a draw's *measured* figure is mildly circular because that figure
already contains the floor being looked up.

**The second ground (circularity) rules out picking one corrected number for
any draw, period-matched or not -- but a *bracket* over a family's whole
measured range, rather than a single value selected by the draw's own
magnitude, does not make that circular move.** Issue #197 ran the calibration
family at a second nominal period, 3.9952 ns -- trial 2's own -- so for that
draw the first ground (cross-period extrapolation) has been retired and issue
#205 applies a bracket there: the residual against every fully-unresolved
variant the family ran at that period, reported as a range rather than a
point, with "not separable" where the family's own implied floor already
meets or exceeds the draw's measured figure. Trial 3's own period, 3.9904 ns,
still has no calibration family, so both grounds still apply to it and
nothing here changes for it. See the rendered section's "Why this restatement
declines..." for the full argument and the bracket itself.

Usage:

    # print the restatement to stdout
    python3 sim/pll-lock-mc/analysis/jitter_floor.py

    # (re)write sim/pll-lock-mc/analysis/jitter-floor/restatement.md
    python3 sim/pll-lock-mc/analysis/jitter_floor.py --write

    # re-derive and verify the committed document (exit 1 on any drift)
    python3 sim/pll-lock-mc/analysis/jitter_floor.py --check

Standard library only, same convention as `sim/run_corners.py`,
`sim/pll-lock-mc/analysis/yield_evidence.py` and `measurements/aggregate.py`.
No PDK, ngspice, xschem or `klt` required.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from statistics import fmean, pstdev

REPO_ROOT = Path(__file__).resolve().parents[3]
MC_RECORD = REPO_ROOT / "sim" / "pll-lock-mc" / "records" / "20260924-222341-a9375a5.md"
FLOOR_EXPERIMENT = REPO_ROOT / "sim" / "jitter-floor"
CALIBRATION_EXPERIMENT = REPO_ROOT / "sim" / "jitter-calibration"
OUTPUT = Path(__file__).resolve().parent / "jitter-floor" / "restatement.md"

#: Ratified spec row 9 (`DR-006`), as a fraction of the output period. Asserted
#: against the Monte Carlo manifest's own gated bound rather than trusted --
#: see `_assert_bound`.
ROW_9_MAX_FRAC = 0.01

#: Two periods this far apart (relative) are "the same operating point" for
#: pairing a null-control floor variant, or a `sim/jitter-calibration`
#: variant, to a Monte Carlo draw's own measured period. 0.1% is far tighter
#: than the spacing between any two variants either family runs.
PERIOD_MATCH_TOL = 1e-3

_SUFFIXES = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}
_LITERAL_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z]*)$")

_RECORD_ID_RE = re.compile(r"^- \*\*Record ID\*\*: (?P<record_id>\S+)\s*$", re.M)
_VARIANT_RE = re.compile(r"THIS RECORD'S VARIANT: (?P<variant>[A-Za-z0-9]+) --")
_JITTER_IN_DETAIL_RE = re.compile(
    r"period jitter (?P<pct>[\d.]+)% RMS over (?P<cycles>\d+) cycles"
)
_MC_JITTER_CELL_RE = re.compile(r"^(?P<pct>[\d.]+)% \((?P<cycles>\d+) cycles\)$")
_FREQ_MHZ_RE = re.compile(r"^(?P<mhz>[\d.]+) MHz$")
_PULSE_RE = re.compile(
    r"^VCLK\s+\S+\s+\S+\s+pulse\(\s*(?P<v1>\S+)\s+(?P<v2>\S+)\s+(?P<td>\S+)\s+"
    r"(?P<tr>\S+)\s+(?P<tf>\S+)\s+(?P<pw>\S+)\s+(?P<per>[^)\s]+)\s*\)",
    re.M | re.I,
)
_TRAN_RE = re.compile(r"^tran\s+(?P<step>\S+)\s+(?P<stop>\S+)\s*$", re.M)
_PWL_HEAD_RE = re.compile(r"^VCLK\s+\S+\s+\S+\s+pwl\([ \t]*\r?\n", re.M | re.I)

_MC_HEADER = [
    "Trial",
    "Seed",
    "Verdict",
    "Locked",
    "Time-to-lock",
    "f_out (post-lock)",
    "Duty",
    "Period jitter",
    "Detail",
]
_PVT_HEADER = ["Corner", "Temp (C)", "Supply (V)", "Verdict", "f_out", "Duty", "Detail"]


class AnalysisError(RuntimeError):
    pass


def _repo_rel(path: Path) -> str:
    """`path` relative to the repo root when it is inside it, else as-is.

    Every real input lives under the repo; the fall-back keeps the unit tests'
    synthetic temp-directory inputs readable instead of raising.
    """
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def spice_time(text: str) -> float:
    """Parse a SPICE time literal (`200p`, `3.9170n`, `50u`).

    Deliberately a local 10-liner rather than an import of
    `sim/harness/measure.parse_spice_time`: an `analysis/` script reads
    committed evidence and must keep running when the harness moves, so it
    takes no dependency on the harness package. `meg` is not accepted here --
    no time literal in this evidence trail uses it, and silently mapping `m`
    to milli (SPICE's convention, which this does) is the only footgun that
    matters for the cards read below.
    """
    m = _LITERAL_RE.match(text.strip())
    if not m:
        raise AnalysisError(f"not a SPICE time literal: {text!r}")
    value, suffix = float(m.group(1)), m.group(2).lower()
    if not suffix:
        return value
    scale = _SUFFIXES.get(suffix[0])
    if scale is None:
        raise AnalysisError(f"unknown SPICE time suffix in {text!r}")
    return value * scale


def _cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _table_rows(text: str, header: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    seen = False
    for line in text.splitlines():
        cells = _cells(line)
        if cells is None:
            continue
        if cells == header:
            seen = True
            continue
        if not seen:
            continue
        if set("".join(cells)) <= {"-", ":"}:
            continue
        if len(cells) != len(header):
            raise AnalysisError(f"result row has {len(cells)} cells: {line!r}")
        rows.append(cells)
    if not seen:
        raise AnalysisError("record has no result table with the expected header")
    return rows


def _record_id(text: str, path: Path) -> str:
    m = _RECORD_ID_RE.search(text)
    if m is None:
        raise AnalysisError(f"{path}: record has no `Record ID` field")
    return m.group("record_id")


def parse_mc_record(path: Path) -> dict:
    """The locked draws of a `--mc` record: frequency, jitter, population."""
    text = path.read_text()
    draws = []
    for cells in _table_rows(text, _MC_HEADER):
        locked = cells[3].replace("*", "").strip()
        if locked != "yes":
            continue
        freq = _FREQ_MHZ_RE.match(cells[5])
        jitter = _MC_JITTER_CELL_RE.match(cells[7])
        if freq is None or jitter is None:
            raise AnalysisError(
                f"{path}: locked trial {cells[0]} has an unreadable f_out/jitter "
                f"cell ({cells[5]!r} / {cells[7]!r})"
            )
        draws.append(
            {
                "trial": int(cells[0]),
                "seed": int(cells[1]),
                "verdict": cells[2],
                "freq_hz": float(freq.group("mhz")) * 1e6,
                "jitter_frac": float(jitter.group("pct")) / 100.0,
                "cycles": int(jitter.group("cycles")),
            }
        )
    if not draws:
        raise AnalysisError(f"{path}: no locked draw carries a period-jitter figure")
    return {"record_id": _record_id(text, path), "path": path, "draws": draws}


def parse_floor_record(record_path: Path, experiment: Path) -> dict:
    """One `sim/jitter-floor` variant: its reported floor and what produced it."""
    text = record_path.read_text()
    record_id = _record_id(text, record_path)

    variant = _VARIANT_RE.search(text)
    if variant is None:
        raise AnalysisError(
            f"{record_path}: no `THIS RECORD'S VARIANT: <id> --` line -- is this a "
            "sim/jitter-floor record?"
        )

    rows = _table_rows(text, _PVT_HEADER)
    if len(rows) != 1:
        raise AnalysisError(
            f"{record_path}: expected exactly one PVT point, found {len(rows)}"
        )
    detail = rows[0][6]
    jitter = _JITTER_IN_DETAIL_RE.search(detail)
    if jitter is None:
        raise AnalysisError(f"{record_path}: point reports no period jitter: {detail!r}")

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
            f"{netlists[0]}: this restatement assumes a symmetric edge "
            f"(TR == TF), got {pulse.group('tr')} / {pulse.group('tf')}"
        )

    return {
        "record_id": record_id,
        "path": record_path,
        "variant": variant.group("variant"),
        "floor_frac": float(jitter.group("pct")) / 100.0,
        "cycles": int(jitter.group("cycles")),
        "period_s": spice_time(pulse.group("per")),
        "edge_s": spice_time(pulse.group("tr")),
        "step_s": spice_time(tran.group("step")),
        "stop_s": spice_time(tran.group("stop")),
        "netlist": _repo_rel(netlists[0]),
    }


def parse_floor_records(experiment: Path) -> list[dict]:
    records = sorted((experiment / "records").glob("*.md"))
    if not records:
        raise AnalysisError(f"{experiment}/records/ holds no record")
    parsed = [parse_floor_record(p, experiment) for p in records]
    steps = {r["step_s"] for r in parsed}
    if len(steps) != 1:
        raise AnalysisError(
            "the floor records do not share one dump grid "
            f"({sorted(steps)}); this restatement compares floors at one grid"
        )
    return parsed


def pwl_points(netlist: str, path: Path) -> list[tuple[float, float]]:
    """The `(time_s, volts)` pairs of a committed `VCLK ... pwl(...)` card.

    Ported from `sim/jitter-calibration/analysis/calibration.py`'s function of
    the same name rather than imported: an `analysis/` script reads committed
    evidence and keeps running when a sibling campaign's script moves. Trimmed
    to what `calibration_schedule` below needs -- this script never renders
    the reported-vs-injected calibration curve `calibration.py` does.
    """
    m = _PWL_HEAD_RE.search(netlist)
    if m is None:
        raise AnalysisError(
            f"{path}: no `VCLK <n+> <n-> pwl(` card -- is this a "
            "sim/jitter-calibration per-point netlist?"
        )
    points: list[tuple[float, float]] = []
    closed = False
    for line in netlist[m.end() :].splitlines():
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
            points.append((spice_time(t_text), spice_time(v_text)))
    if not closed:
        raise AnalysisError(f"{path}: `pwl(` card is never closed")
    if len(points) < 4:
        raise AnalysisError(f"{path}: `pwl(` card holds only {len(points)} points")
    times = [t for t, _ in points]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise AnalysisError(f"{path}: `pwl(` times are not strictly increasing")
    return points


def calibration_schedule(points: list[tuple[float, float]], path: Path) -> dict:
    """The exact period, edge and injected RMS a committed PWL schedule carries.

    This script only needs enough of `sim/jitter-calibration`'s own record to
    match a variant to a Monte Carlo draw's period -- not the full
    reported-vs-injected calibration curve `calibration.py` renders -- so the
    injected figure is re-derived (`pstdev(T_k)/mean(T_k)` over the card's own
    rising-edge midpoints, the same estimator `sim/harness/measure.period_jitter`
    applies) but never used as a correction. See this module's docstring.
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
    }


def parse_calibration_record(record_path: Path, experiment: Path) -> dict:
    """One `sim/jitter-calibration` variant: what it injected, at what period.

    Read for period coverage only -- see this module's docstring for why its
    calibrated floor is not applied as a correction here.
    """
    text = record_path.read_text()
    record_id = _record_id(text, record_path)

    variant = _VARIANT_RE.search(text)
    if variant is None:
        raise AnalysisError(
            f"{record_path}: no `THIS RECORD'S VARIANT: <id> --` line -- is this a "
            "sim/jitter-calibration record?"
        )

    rows = _table_rows(text, _PVT_HEADER)
    if len(rows) != 1:
        raise AnalysisError(
            f"{record_path}: expected exactly one PVT point, found {len(rows)}"
        )
    detail = rows[0][6]
    jitter = _JITTER_IN_DETAIL_RE.search(detail)
    if jitter is None:
        raise AnalysisError(f"{record_path}: point reports no period jitter: {detail!r}")

    corners = experiment / "corners" / record_id
    netlists = sorted(p for p in corners.glob("*.spice") if not p.name.startswith("tb_"))
    if len(netlists) != 1:
        raise AnalysisError(
            f"{corners}: expected exactly one committed per-point netlist, found "
            f"{len(netlists)}"
        )
    netlist = netlists[0].read_text()
    schedule = calibration_schedule(pwl_points(netlist, netlists[0]), netlists[0])
    tran = _TRAN_RE.search(netlist)
    if tran is None:
        raise AnalysisError(f"{netlists[0]}: no injected `tran <step> <stop>` card")

    reported_frac = float(jitter.group("pct")) / 100.0
    period_s = schedule["period_s"]
    reported_s = reported_frac * period_s
    injected_s = schedule["injected_frac"] * period_s
    implied_floor_s = (
        math.sqrt(reported_s**2 - injected_s**2) if reported_s > injected_s else None
    )

    return {
        "record_id": record_id,
        "path": record_path,
        "variant": variant.group("variant"),
        "reported_frac": reported_frac,
        "injected_frac": schedule["injected_frac"],
        "period_s": period_s,
        "edge_s": schedule["edge_s"],
        "cycles": schedule["cycles"],
        "step_s": spice_time(tran.group("step")),
        "implied_floor_s": implied_floor_s,
        "netlist": _repo_rel(netlists[0]),
    }


def parse_calibration_records(experiment: Path) -> list[dict]:
    records = sorted((experiment / "records").glob("*.md"))
    if not records:
        raise AnalysisError(f"{experiment}/records/ holds no record")
    return [parse_calibration_record(p, experiment) for p in records]


def calibration_variants_at(period_s: float, cal_records: list[dict]) -> list[dict]:
    """The calibration variants sharing one draw's own measured period.

    Same `PERIOD_MATCH_TOL` `match_floor` uses to pair a null-control variant
    to a draw -- but unlike `match_floor`, an empty result here is not a
    refusal: `sim/jitter-calibration` (issue #185) runs at one nominal period
    today, and a draw at a different one simply has no calibration coverage
    yet. Naming that gap in the rendered restatement, not raising past it, is
    the point of this script's Decline resolution (issue #193).
    """
    return sorted(
        (
            c
            for c in cal_records
            if abs(c["period_s"] - period_s) / period_s <= PERIOD_MATCH_TOL
        ),
        key=lambda c: c["variant"],
    )


def calibration_bracket(
    period_s: float, measured_s: float, cal_records: list[dict]
) -> dict | None:
    """A draw's residual against every fully-unresolved calibration variant at
    its own period -- a bracket over the family's measured range, never a
    single value picked by the draw's own magnitude (issue #205).

    "Fully unresolved" mirrors `sim/jitter-calibration/analysis/calibration.py`'s
    own cut (`edge_s <= 0.5 * step_s`): the regime where the bracketing sample
    pair straddles the whole transition and `implied_floor_s` is a meaningful
    per-variant floor rather than an artifact of a partially-resolved edge.
    Returns `None` when the period has no such variant -- no bracket to draw,
    which the rendered restatement states as the coverage gap it is, never as
    a silently-empty range.
    """
    unresolved = [
        c
        for c in calibration_variants_at(period_s, cal_records)
        if c["implied_floor_s"] is not None and c["edge_s"] <= 0.5 * c["step_s"]
    ]
    if not unresolved:
        return None
    points = []
    for c in sorted(unresolved, key=lambda c: c["implied_floor_s"]):
        floor_s = c["implied_floor_s"]
        residual_s = math.sqrt(measured_s**2 - floor_s**2) if measured_s > floor_s else None
        points.append(
            {
                "variant": c["variant"],
                "injected_frac": c["injected_frac"],
                "implied_floor_s": floor_s,
                "residual_s": residual_s,
                "residual_frac": None if residual_s is None else residual_s / period_s,
            }
        )
    return {"points": points}


def _assert_bound(manifest_text: str) -> None:
    """The Monte Carlo manifest must still gate at ratified row 9's bound."""
    if f'"max_frac": {ROW_9_MAX_FRAC}' not in manifest_text:
        raise AnalysisError(
            "sim/pll-lock-mc/testbench/tb.json no longer gates period jitter at "
            f"{ROW_9_MAX_FRAC} of the output period (ratified row 9, DR-006). The "
            "manifest and the ratified row disagree -- fix one of them; do not "
            "restate against a drifted bound"
        )


def match_floor(draw: dict, floors: list[dict]) -> dict:
    """The worst-case floor variant for one draw's own measured period.

    Worst case over the two ratios `sim/jitter-floor`'s manifest names: the
    variant whose pulse period is closest to this draw's measured post-lock
    period (grid phase walks by the fractional part of period/step, so the
    floor is period-specific), and among those the one with the *fastest* edge
    (the floor falls monotonically as the grid resolves the edge, so the
    fastest edge is the largest floor the family measured at that period).
    """
    target = 1.0 / draw["freq_hz"]
    best_period = min(floors, key=lambda f: abs(f["period_s"] - target))["period_s"]
    at_period = [f for f in floors if f["period_s"] == best_period]
    chosen = min(at_period, key=lambda f: f["edge_s"])
    # A 0.1 % period mismatch would mean this draw has no variant of its own.
    if abs(best_period - target) / target > PERIOD_MATCH_TOL:
        raise AnalysisError(
            f"trial {draw['trial']} measured a {1e9 * target:.4f} ns period, but the "
            f"closest floor variant ran at {1e9 * best_period:.4f} ns -- too far "
            "apart to restate against; run a variant at this draw's period"
        )
    return chosen


def restate(mc: dict, floors: list[dict], cal_records: list[dict]) -> dict:
    step_s = floors[0]["step_s"]
    # Two unresolved-edge quantization figures, both arithmetic on the grid
    # step (see this module's docstring): the worst case over grid phases for a
    # perfectly periodic clock, `step * sqrt(f*(1-f))` maximized at f = 0.5,
    # and the uniformly-spread-phase case a really-jittering signal approaches.
    unresolved_worst_s = 0.5 * step_s
    unresolved_uniform_s = math.sqrt(2.0) * step_s / math.sqrt(12.0)

    rows = []
    for draw in mc["draws"]:
        floor = match_floor(draw, floors)
        period_s = 1.0 / draw["freq_hz"]
        measured_s = draw["jitter_frac"] * period_s
        floor_s = floor["floor_frac"] * floor["period_s"]
        if measured_s > floor_s:
            residual_s: float | None = math.sqrt(measured_s**2 - floor_s**2)
        else:
            residual_s = None
        # Read for period coverage only -- this script declines to apply the
        # calibrated floor as a correction (see this module's docstring); an
        # empty list here just means "no calibration variant at this draw's
        # own period", which is the gap the rendered restatement names.
        cal_at_period = calibration_variants_at(period_s, cal_records)
        # A bracket over the period-matched family's own measured range
        # (issue #205) -- distinct from the single-value correction this
        # module's docstring explains this script still declines to make.
        bracket = calibration_bracket(period_s, measured_s, cal_records)
        rows.append(
            {
                "draw": draw,
                "floor": floor,
                "period_s": period_s,
                "budget_s": ROW_9_MAX_FRAC * period_s,
                "measured_s": measured_s,
                "floor_s": floor_s,
                "residual_s": residual_s,
                "residual_frac": None if residual_s is None else residual_s / period_s,
                "below_unresolved_worst": measured_s < unresolved_worst_s,
                # Does this draw still miss row 9 even if the most pessimistic
                # floor arithmetic allows at this grid applied to it?
                "misses_under_worst": (
                    measured_s > unresolved_worst_s
                    and math.sqrt(measured_s**2 - unresolved_worst_s**2) / period_s
                    > ROW_9_MAX_FRAC
                ),
                "calibration_variants": cal_at_period,
                "has_calibration_at_period": bool(cal_at_period),
                "calibration_bracket": bracket,
            }
        )
    # Rounded to 1 fs: `fmean` over each record's own ~300-edge PWL schedule
    # accumulates float error of that order between otherwise-identical
    # periods (calibration.py's `restate` rounds the same way for the same
    # reason), which would otherwise read as spurious distinct periods.
    calibration_periods_s = sorted({round(c["period_s"], 15) for c in cal_records})
    return {
        "step_s": step_s,
        "unresolved_worst_s": unresolved_worst_s,
        "unresolved_uniform_s": unresolved_uniform_s,
        "rows": rows,
        "calibration_periods_s": calibration_periods_s,
    }


def _trials(rows: list[dict]) -> str:
    """`trial 5` / `trials 2 and 3` / `trials 2, 3 and 5`."""
    names = [str(r["draw"]["trial"]) for r in rows]
    if len(names) == 1:
        return f"trial {names[0]}"
    return f"trials {', '.join(names[:-1])} and {names[-1]}"


def _pct(frac: float | None) -> str:
    return "-" if frac is None else f"{100.0 * frac:.3f}%"


def _ps(seconds: float | None) -> str:
    return "-" if seconds is None else f"{1e12 * seconds:.1f} ps"


def render(mc: dict, floors: list[dict], cal_records: list[dict], derived: dict) -> str:
    step_s = derived["step_s"]
    out: list[str] = []
    a = out.append

    a("# `sim/pll-lock-mc`'s measured period jitter, restated against the measured floor")
    a("")
    a(
        "**Generated** by `sim/pll-lock-mc/analysis/jitter_floor.py` -- do not edit by "
        "hand. Re-derive with `--write`, verify with `--check`. Every figure below is "
        "read from a committed record (or from that record's own committed per-point "
        "netlist); nothing here simulates or measures."
    )
    a("")
    a("## Inputs")
    a("")
    a(
        f"- Measured: `{_repo_rel(mc['path'])}` "
        f"(record `{mc['record_id']}`) -- {len(mc['draws'])} locked draw(s) carrying a "
        "period-jitter figure."
    )
    a(
        f"- Floor: `sim/jitter-floor/records/` -- {len(floors)} variant record(s) of the "
        "null control (an ideal pulse source of exactly constant period, true period "
        "jitter zero by construction), all at the same "
        f"{1e12 * step_s:.0f} ps dump grid as the measured record."
    )
    a(
        f"- Calibration, read for period coverage and, where the period matches, a "
        "residual bracket (see \"Why this restatement declines...\" below -- no single "
        f"calibrated floor is ever picked as a correction): `sim/jitter-calibration/"
        f"records/` -- {len(cal_records)} variant record(s) of a source with known, "
        f"nonzero injected jitter (issue #185), spanning "
        f"{len(derived['calibration_periods_s'])} distinct nominal period(s)."
    )
    a("")
    a("## The floor family, as measured")
    a("")
    a(
        "| Variant | Record | Pulse period | Edge (TR=TF) | Edge / grid step | "
        "frac(period / step) | Floor reported | Population |"
    )
    a("|---|---|---|---|---|---|---|---|")
    for f in sorted(floors, key=lambda r: r["variant"]):
        ratio = f["period_s"] / f["step_s"]
        a(
            f"| {f['variant']} | `{f['record_id']}` | {1e9 * f['period_s']:.4f} ns | "
            f"{_ps(f['edge_s'])} | {f['edge_s'] / f['step_s']:.2f} | "
            f"{ratio - math.floor(ratio):.3f} | {_pct(f['floor_frac'])} | "
            f"{f['cycles']} cycles |"
        )
    a("")
    a(
        "Read this as the two dependences `sim/jitter-floor/testbench/tb.json` states: "
        "the floor collapses once the clock's transition spans two or more grid samples "
        "(the interpolation then happens across a bracketing pair that both sit on the "
        "ramp), and, for an edge the grid cannot resolve, it is set by how far the grid "
        "phase of successive edges walks -- the fractional part of period/step."
    )
    a("")
    a("## The restatement")
    a("")
    a(
        "Quadrature removal, `sqrt(measured^2 - floor^2)`, at each draw's own measured "
        "post-lock period, against the worst-case (fastest-edge) floor variant measured "
        "at that period. Row 9's bound is 1.0 % of the output period; the `Budget` "
        "column is that bound in absolute time, for scale against the "
        f"{1e12 * step_s:.0f} ps grid."
    )
    a("")
    a(
        "| Trial | Verdict in record | f_out | Budget (1.0 %) | Measured | Floor "
        "(variant) | Floor-removed | Floor-removed % | Still misses row 9 at this floor? |"
    )
    a("|---|---|---|---|---|---|---|---|---|")
    for r in derived["rows"]:
        draw = r["draw"]
        floor = r["floor"]
        if r["residual_s"] is None:
            verdict = "**not separable** -- measured figure is at or below the floor"
        elif r["residual_frac"] > ROW_9_MAX_FRAC:
            verdict = "**yes**"
        else:
            verdict = "**no** -- inside the bound once the floor is removed"
        a(
            f"| {draw['trial']} | {draw['verdict']} | "
            f"{draw['freq_hz'] / 1e6:.1f} MHz | {_ps(r['budget_s'])} | "
            f"{_pct(draw['jitter_frac'])} ({_ps(r['measured_s'])}) | "
            f"{_pct(floor['floor_frac'])} ({_ps(r['floor_s'])}, {floor['variant']}) | "
            f"{_ps(r['residual_s'])} | {_pct(r['residual_frac'])} | {verdict} |"
        )
    a("")
    a("## The regime the null control does not reproduce")
    a("")
    a(
        "The null control's period is exactly constant, so its edges walk through grid "
        "phase deterministically. A signal with real jitter comparable to the grid step "
        "does not: its edges land at grid phases spread by that jitter, which is a wider "
        "distribution and therefore a different floor. Neither figure below is measured "
        "here (`sim/jitter-calibration`, issue #185, is the control that measures the "
        "second -- see its `analysis/calibration.md`, which finds that *which way* the "
        "null control's floor differs from the floor a jittering signal carries is "
        "itself a property of the period being corrected); both are arithmetic "
        f"on this {1e12 * step_s:.0f} ps grid, printed with their formulas:"
    )
    a("")
    a(
        f"- `step * sqrt(f*(1-f))`, maximized at `f = 0.5`, i.e. `step/2` = "
        f"**{_ps(derived['unresolved_worst_s'])}** -- the worst case over grid phases "
        "for a perfectly periodic clock, which is the largest floor any unresolved edge "
        "with adjacent-interval quantization can carry."
    )
    a(
        f"- `sqrt(2)*step/sqrt(12)` = `0.41*step` = "
        f"**{_ps(derived['unresolved_uniform_s'])}** -- edges at independent, "
        "uniformly-spread grid phases, the case a really-jittering signal approaches."
    )
    a("")
    a(
        f"Applying the larger of the two ({_ps(derived['unresolved_worst_s'])}) to each "
        "draw, as a test of whether the conclusion above survives the most pessimistic "
        "floor arithmetic allows:"
    )
    a("")
    for r in derived["rows"]:
        draw = r["draw"]
        worst = derived["unresolved_worst_s"]
        if r["below_unresolved_worst"]:
            a(
                f"- Trial {draw['trial']}: measured {_ps(r['measured_s'])} RMS, which is "
                f"**below** {_ps(worst)}. A quadrature-additive error cannot exceed the "
                "total it contributes to, so this draw's own magnitude rules that "
                "pessimistic floor out for it -- whatever floor applies to this draw is "
                "smaller than its measured figure, which is what the restatement above "
                "already assumes."
            )
        else:
            residual = math.sqrt(max(r["measured_s"] ** 2 - worst**2, 0.0))
            a(
                f"- Trial {draw['trial']}: measured {_ps(r['measured_s'])} RMS. Even if "
                f"the whole {_ps(worst)} applied, {_ps(residual)} "
                f"({_pct(residual / r['period_s'])} of its period) would remain -- "
                + (
                    "still outside row 9's bound."
                    if residual / r["period_s"] > ROW_9_MAX_FRAC
                    else "inside row 9's bound."
                )
            )
    a("")
    still = [
        r for r in derived["rows"] if r["residual_frac"] and r["residual_frac"] > ROW_9_MAX_FRAC
    ]
    robust = [r for r in derived["rows"] if r["misses_under_worst"]]
    ambiguous = [r for r in derived["rows"] if not r["misses_under_worst"]]
    a("## Why this restatement declines to apply the calibration-informed floor")
    a("")
    cal_periods = derived["calibration_periods_s"]
    a(
        "`sim/jitter-calibration` (issue #185) measures the regime above directly, with "
        "a known, nonzero injected jitter, instead of arguing it from grid arithmetic. "
        "Its `analysis/calibration.md` finds that the two floors are different "
        "quantities -- not one a conservative bound on the other -- and that the "
        "null-control floor's error **changes sign** with `frac(period/step)`: where the "
        "walk-phase figure `step*sqrt(f*(1-f))` is the larger of the two grid bounds "
        "above, the null control *over*-states the floor a strongly jittering signal "
        "carries and a correction using it over-corrects; where it is the smaller one, "
        "the error runs the other way."
    )
    a("")
    a(
        f"That campaign's {len(cal_records)} committed variant record(s) span "
        f"{len(cal_periods)} distinct nominal period(s) -- "
        + ", ".join(f"{1e9 * p:.4f} ns" for p in cal_periods)
        + " -- "
        + (
            "so the sign's period dependence is measured there rather than argued from "
            "the formula (issue #197)."
            if len(cal_periods) > 1
            else "so the sign's period dependence is argued there from the formula "
            "rather than measured."
        )
        + " Checked against each locked draw's own measured period:"
    )
    a("")
    a("| Trial | f_out | Period | frac(period / step) | Calibration variant at this period? |")
    a("|---|---|---|---|---|")
    for r in derived["rows"]:
        draw = r["draw"]
        ratio = r["period_s"] / step_s
        frac = ratio - math.floor(ratio)
        if r["has_calibration_at_period"]:
            variants = ", ".join(c["variant"] for c in r["calibration_variants"])
            coverage = f"**yes** -- {variants}"
        else:
            coverage = "**no**"
        a(
            f"| {draw['trial']} | {draw['freq_hz'] / 1e6:.1f} MHz | "
            f"{1e9 * r['period_s']:.4f} ns | {frac:.3f} | {coverage} |"
        )
    a("")
    robust_covered = [r for r in robust if r["has_calibration_at_period"]]
    ambiguous_covered = [r for r in ambiguous if r["has_calibration_at_period"]]
    ambiguous_uncovered = [r for r in ambiguous if not r["has_calibration_at_period"]]
    if robust_covered:
        a(
            f"{_trials(robust_covered).capitalize()} already has a calibration family at "
            "its own period, but is resolved without it -- it is one of the "
            f"{len(robust)} draw(s) that miss row 9 even under the null control's own "
            "most pessimistic floor arithmetic (the bullet above), so nothing about its "
            "verdict depends on the calibration curve."
        )
        a("")
    if ambiguous:
        a(
            f"Of the draws with a residual ambiguity left to resolve "
            f"({_trials(ambiguous)}), "
            + (
                f"{_trials(ambiguous_covered)} now has a calibration family at its own "
                "period ("
                + "; ".join(
                    f"{1e9 * r['period_s']:.4f} ns -- "
                    + ", ".join(c["variant"] for c in r["calibration_variants"])
                    for r in ambiguous_covered
                )
                + ")"
                if ambiguous_covered
                else "none has a calibration family at its own period"
            )
            + (
                f", and {_trials(ambiguous_uncovered)} still has none ("
                + ", ".join(
                    f"{1e9 * r['period_s']:.4f} ns" for r in ambiguous_uncovered
                )
                + ", a period the calibration family has never visited)."
                if ambiguous_uncovered
                else ", and none is left without one."
            )
        )
        a("")
    a(
        "**Decision (issue #205): still decline to pick a single calibrated floor for "
        "any draw, but apply a bracket over a period-matched family's whole measured "
        "range where the cross-period ground has been retired.** Picking one calibrated "
        "floor by interpolating the family at a draw's own measured magnitude stays "
        "circular whether or not the period matches: a draw's measured figure already "
        "contains the floor being looked up, so using it to select which family row "
        "applies assumes what the correction is trying to bound. That ground rules out "
        "a single corrected number for every draw here and is not weakened by any "
        "calibration run -- no trial below gets one. A **bracket** does not make that "
        "move: it reads the residual at *every* fully-unresolved variant the family ran "
        "at a draw's own period, rather than selecting one row by the draw's own "
        "magnitude."
        + (
            f" Applying one is now possible for {_trials(ambiguous_covered)} -- its "
            "period-matched family landed in issue #197."
            if ambiguous_covered
            else ""
        )
        + (
            f" It still is not for {_trials(ambiguous_uncovered)}: with no calibration "
            "variant at "
            + ", ".join(f"{1e9 * r['period_s']:.4f} ns" for r in ambiguous_uncovered)
            + ", a bracket there would still be the unmeasured cross-period "
            "extrapolation `calibration.md` warns against, on a quantity that does not "
            "transfer across periods by assumption."
            if ambiguous_uncovered
            else ""
        )
    )
    a("")
    if ambiguous_covered:
        a(
            f"**{_trials(ambiguous_covered).capitalize()}'s bracket, at its own "
            "period.** The period-matched family's fully-unresolved variants (fastest "
            "edge -- the same regime the null-control floor above is drawn from), read "
            "against this draw's own measured figure rather than at a single selected "
            "magnitude:"
        )
        a("")
        a(
            "| Trial | Family variant | Injected | Implied floor (fastest edge) | "
            "Residual vs. this floor |"
        )
        a("|---|---|---|---|---|")
        for r in ambiguous_covered:
            for p in r["calibration_bracket"]["points"]:
                residual_cell = (
                    f"{_ps(p['residual_s'])} ({_pct(p['residual_frac'])})"
                    if p["residual_s"] is not None
                    else "**not separable** -- measured figure is at or below this implied floor"
                )
                a(
                    f"| {r['draw']['trial']} | {p['variant']} | "
                    f"{_pct(p['injected_frac'])} | {_ps(p['implied_floor_s'])} | "
                    f"{residual_cell} |"
                )
        a("")
        for r in ambiguous_covered:
            draw = r["draw"]
            points = r["calibration_bracket"]["points"]
            separable = [p for p in points if p["residual_s"] is not None]
            not_separable = [p for p in points if p["residual_s"] is None]
            if not separable:
                a(
                    f"Trial {draw['trial']}'s measured figure is at or below every "
                    "fully-unresolved variant's implied floor this family ran at its "
                    "period -- the bracket is **not separable** at every point measured."
                )
                a("")
                continue
            widest = max(separable, key=lambda p: p["residual_s"])
            a(
                f"Trial {draw['trial']}'s bracket over this family runs from "
                f"{_ps(widest['residual_s'])} ({_pct(widest['residual_frac'])}), at "
                f"{widest['variant']}'s {_pct(widest['injected_frac'])}-injected implied "
                "floor -- the only fully-unresolved variant this draw's own measured "
                "figure clears"
                + (
                    ", through **not separable** at "
                    + " and ".join(p["variant"] for p in not_separable)
                    + " -- where the family's own implied floor at this period already "
                    "meets or exceeds this draw's measured figure"
                    if not_separable
                    else ""
                )
                + f". Against the {_ps(r['residual_s'])} ({_pct(r['residual_frac'])}) "
                "already reported above under the (smaller) null-control floor, the "
                "bracket does not move the verdict: its numeric end, "
                f"{_pct(widest['residual_frac'])}, is "
                + (
                    "still above"
                    if widest["residual_frac"] > ROW_9_MAX_FRAC
                    else "inside"
                )
                + " row 9's 1.0 % bound, and its non-numeric end says only that the "
                "measurement cannot rule out that a larger share of this draw's own "
                "measured spread is floor -- not that the draw is inside the bound."
            )
            a("")
    if ambiguous_uncovered:
        a(
            "**The run that would close the remaining gap**: a `sim/jitter-calibration` "
            "variant family (the same 3 injected magnitudes x 3 edges that campaign runs) "
            "at "
            + " and ".join(
                f"{1e9 * r['period_s']:.4f} ns" for r in ambiguous_uncovered
            )
            + f" -- {_trials(ambiguous_uncovered)}'s own measured "
            f"period{'' if len(ambiguous_uncovered) == 1 else 's'}, which the "
            "calibration family has not visited. Until then this restatement has nothing "
            "period-matched to read there, in either direction, and no bracket applies."
        )
    a("")
    a("## What this does and does not settle")
    a("")
    a(
        f"- **{len(still)} of {len(derived['rows'])} locked draws still miss ratified "
        "row 9's 1.0 % bound once the measured floor is removed in quadrature** -- the "
        "floor this null control measures at each draw's own period, with the fastest "
        "edge (largest floor) the family ran. At the *other* end of the family, an edge "
        "the grid resolves, the measured floor is 0.000 % and the draws' figures stand "
        "unchanged. So under both regimes the control itself covers, the recorded miss "
        "is the circuit's, not the grid's."
    )
    a(
        f"- **{len(robust)} of {len(derived['rows'])} miss it even under the most "
        "pessimistic floor arithmetic allows at this grid** "
        f"({_ps(derived['unresolved_worst_s'])} per period)"
        + (
            f": {_trials(robust)}. That miss is not readable as a measurement artefact "
            "under any floor model considered here."
            if robust
            else "."
        )
    )
    if ambiguous:
        a(
            f"- **The remaining {_trials(ambiguous)} keep a residual ambiguity, and this "
            "restatement declines to resolve it rather than argue it away.** "
            "Their own magnitude rules out the fully-unresolved, uniformly-spread-phase "
            f"floor ({_ps(derived['unresolved_uniform_s'])}, which exceeds what they "
            "measured), but an *intermediate* floor -- edges the grid only partly "
            "resolves, at grid phases spread by the draw's own jitter rather than by a "
            "constant period's walk -- sits between the null control's figure and their "
            "measured one, and a large enough one would put them inside the bound. "
            "`sim/jitter-calibration` (issue #185) measures exactly that regime, at "
            f"{len(derived['calibration_periods_s'])} nominal period(s) so far; "
            + (
                f"{_trials([r for r in ambiguous if r['has_calibration_at_period']])} "
                "now has a family at its own period and "
                if any(r["has_calibration_at_period"] for r in ambiguous)
                else ""
            )
            + (
                f"{_trials([r for r in ambiguous if not r['has_calibration_at_period']])} "
                "does not"
                if any(not r["has_calibration_at_period"] for r in ambiguous)
                else "every ambiguous draw now has one"
            )
            + " -- see \"Why this restatement declines...\" above for the argued "
            "decision (issue #205): a bracket now applies to the period-matched draw(s) "
            "there without resolving their ambiguity to a pass -- its numeric end still "
            "misses row 9 and its other end is \"not separable\", never a clean bound -- "
            "and the period-mismatched draw(s) still have nothing period-matched to "
            "read, which remains their own open gap, named rather than folded into the "
            "period-matched draw's treatment."
        )
    a(
        "- **It does not ratify, relax or restate row 9**, and it does not turn the "
        "recorded miss into a pass or a failure verdict of its own. "
        "`sim/pll-lock-mc/records/20260924-222341-a9375a5.md` stands exactly as "
        "written, per `sim/README.md`'s append-only rule; this document is a derived "
        "reading of it, not a correction to it."
    )
    a(
        "- **It does not establish which floor variant the real DUT sits at.** Nothing "
        "committed here states `design/vco`'s `CLK` transition time at the row-9 "
        "operating point (issue #186), so the applicable floor is bounded by this "
        "family rather than read off it. The first bullet is stated over both ends of "
        "the family so it does not depend on that answer; the ambiguity bullet is what "
        "that measurement, read together with a period-matched "
        "`sim/jitter-calibration` variant (issue #197), would close."
    )
    a("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "record",
        nargs="?",
        default=str(MC_RECORD),
        help="the sim/pll-lock-mc record to restate (default: the campaign's only record)",
    )
    ap.add_argument(
        "--floor-experiment",
        default=str(FLOOR_EXPERIMENT),
        help="the sim/jitter-floor experiment directory holding the floor records",
    )
    ap.add_argument(
        "--calibration-experiment",
        default=str(CALIBRATION_EXPERIMENT),
        help=(
            "the sim/jitter-calibration experiment directory holding the calibration "
            "records (read for period coverage and, where matched, a residual bracket "
            "-- see this module's docstring)"
        ),
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help=f"write {OUTPUT.name}")
    mode.add_argument(
        "--check", action="store_true", help="verify the committed document, exit 1 on drift"
    )
    args = ap.parse_args(argv)

    try:
        mc = parse_mc_record(Path(args.record))
        _assert_bound(
            (REPO_ROOT / "sim" / "pll-lock-mc" / "testbench" / "tb.json").read_text()
        )
        floors = parse_floor_records(Path(args.floor_experiment))
        cal_records = parse_calibration_records(Path(args.calibration_experiment))
        text = render(mc, floors, cal_records, restate(mc, floors, cal_records))
    except (AnalysisError, OSError) as exc:
        print(f"jitter_floor.py: {exc}", file=sys.stderr)
        return 2

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(text)
        print(f"wrote {OUTPUT.relative_to(REPO_ROOT).as_posix()}")
        return 0
    if args.check:
        if not OUTPUT.is_file():
            print(f"jitter_floor.py: {OUTPUT} is missing -- run --write", file=sys.stderr)
            return 1
        committed = OUTPUT.read_text()
        if committed != text:
            print(
                f"jitter_floor.py: {OUTPUT.relative_to(REPO_ROOT).as_posix()} does not "
                "match what the committed records re-derive -- re-run --write and read "
                "the diff",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {OUTPUT.relative_to(REPO_ROOT).as_posix()} matches the records")
        return 0
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
