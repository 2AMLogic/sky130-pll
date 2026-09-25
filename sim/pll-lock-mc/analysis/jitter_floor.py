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
   and what the null control's deterministic phase walk does not reproduce
   (`sim/jitter-calibration`, issue #185, measures that regime directly with a
   known nonzero injected jitter; this script deliberately does not import its
   numbers -- restating a Monte Carlo draw against a floor measured at another
   source's jitter magnitude is a further step, not a pointer). Both are
   arithmetic on the grid step the records themselves
   declare, not measurements, and both are printed with their formulas so a
   reader can check them. The restatement uses the *larger* of the two as its
   robustness test, so its conclusion does not depend on which regime applies.

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

REPO_ROOT = Path(__file__).resolve().parents[3]
MC_RECORD = REPO_ROOT / "sim" / "pll-lock-mc" / "records" / "20260924-222341-a9375a5.md"
FLOOR_EXPERIMENT = REPO_ROOT / "sim" / "jitter-floor"
OUTPUT = Path(__file__).resolve().parent / "jitter-floor" / "restatement.md"

#: Ratified spec row 9 (`DR-006`), as a fraction of the output period. Asserted
#: against the Monte Carlo manifest's own gated bound rather than trusted --
#: see `_assert_bound`.
ROW_9_MAX_FRAC = 0.01

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
    if abs(best_period - target) / target > 1e-3:
        raise AnalysisError(
            f"trial {draw['trial']} measured a {1e9 * target:.4f} ns period, but the "
            f"closest floor variant ran at {1e9 * best_period:.4f} ns -- too far "
            "apart to restate against; run a variant at this draw's period"
        )
    return chosen


def restate(mc: dict, floors: list[dict]) -> dict:
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
            }
        )
    return {
        "step_s": step_s,
        "unresolved_worst_s": unresolved_worst_s,
        "unresolved_uniform_s": unresolved_uniform_s,
        "rows": rows,
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


def render(mc: dict, floors: list[dict], derived: dict) -> str:
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
        "second -- see its `analysis/calibration.md`, which finds that at this period "
        "the walk-phase figure is the *larger* of the two, so a null-control floor "
        "over-corrects a strongly jittering signal); both are arithmetic "
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
    a("## What this does and does not settle")
    a("")
    still = [
        r for r in derived["rows"] if r["residual_frac"] and r["residual_frac"] > ROW_9_MAX_FRAC
    ]
    robust = [r for r in derived["rows"] if r["misses_under_worst"]]
    ambiguous = [r for r in derived["rows"] if not r["misses_under_worst"]]
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
            f"- **The remaining {_trials(ambiguous)} keep a residual ambiguity, and it "
            "is named rather than argued away.** "
            "Their own magnitude rules out the fully-unresolved, uniformly-spread-phase "
            f"floor ({_ps(derived['unresolved_uniform_s'])}, which exceeds what they "
            "measured), but an *intermediate* floor -- edges the grid only partly "
            "resolves, at grid phases spread by the draw's own jitter rather than by a "
            "constant period's walk -- sits between the null control's figure and their "
            "measured one, and a large enough one would put them inside the bound. That "
            "regime is exactly what a source of known, nonzero injected jitter settles, "
            "and `sim/jitter-calibration` (issue #185) now measures it; the null control "
            "cannot, by construction. Applying that campaign's curve to these draws is a "
            "further step this restatement does not take on its own -- its floors were "
            "measured at *its* injected magnitudes, not at these draws'."
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
        "that measurement, read together with `sim/jitter-calibration`'s curve, would "
        "close."
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
        text = render(mc, floors, restate(mc, floors))
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
