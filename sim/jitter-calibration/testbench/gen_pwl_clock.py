#!/usr/bin/env python3
"""Generate `tb_jitter_calibration.sch` -- a PWL clock of *known* period jitter.

`sim/jitter-floor/` (issue #178) measures what this harness's period-jitter
reducer reports for a signal whose true period jitter is **zero**. That is a
null control: it bounds the floor, but it never answers the question a reader
of a measured jitter figure actually has -- *if the signal really jitters by
`x`, what does this pipeline report?* (issue #185).

This script builds the source that answers it. The clock is a piecewise-linear
voltage source whose rising-edge schedule is drawn from a seeded RNG at an
**exactly** stated RMS period jitter, so the injected value is not an estimate
of the source's behaviour -- it is a property of the committed netlist, and
`sim/jitter-calibration/analysis/calibration.py` re-derives it from that
netlist rather than trusting this script or any prose.

## How the injected figure is made exact

`sim/harness/measure.period_jitter` reports `pstdev(T_k) / mean(T_k)` over the
population of consecutive periods. So this generator builds that exact
quantity by construction:

1. Draw `cycles` standard normal deviates `g_k` from `random.Random(seed)` via
   an explicit Box-Muller transform over `Random.random()` -- deliberately not
   `random.gauss()`, whose internal cached-deviate state is a stdlib
   implementation detail, where `Random.random()`'s Mersenne Twister stream is
   a documented, version-stable contract.
2. **Normalize** the draw: subtract its own sample mean and divide by its own
   population standard deviation. After this, `mean(g) = 0` and
   `pstdev(g) = 1` to floating-point exactness -- the realized sample no
   longer carries the scatter an unnormalized draw would.
3. Set `T_k = T_nom * (1 + rms_frac * g_k)`. Then `mean(T_k) = T_nom` and
   `pstdev(T_k) = T_nom * rms_frac`, so `pstdev(T_k)/mean(T_k) = rms_frac`
   exactly -- and, because the mean is exact, the whole schedule is exactly
   `cycles * T_nom` long regardless of `rms_frac` or seed.

The rising 50 % crossing of cycle `k` therefore lands at a *known* instant,
and the PWL point list is written so that instant is exactly the midpoint of a
symmetric 0 V -> `v_high` ramp: the crossing times are the schedule, not an
artefact of the waveform's shape.

## Why the schedule is committed rather than re-generated at run time

`sim/README.md` makes `sim/` an append-only evidence trail whose records must
be reproducible from what is committed. A source whose edges came from an RNG
invoked inside the simulator would make the injected value a claim about this
script; writing every edge into the netlist makes it a readable property of
the evidence. This script is the *provenance* of that netlist, not a
dependency of reading it -- `sim/tests/test_jitter_calibration.py` re-runs it
against each committed record and fails on any drift.

## Usage

    # write testbench/tb_jitter_calibration.sch for one variant, and point
    # tb.json's methodology note at it
    python3 sim/jitter-calibration/testbench/gen_pwl_clock.py --variant J10b

    # what a variant injects, without writing anything
    python3 sim/jitter-calibration/testbench/gen_pwl_clock.py --variant J10b --describe

    # just the SPICE card (what the unit test compares against)
    python3 sim/jitter-calibration/testbench/gen_pwl_clock.py --variant J10b --emit-card

Standard library only, same convention as `sim/run_corners.py` and every
`analysis/` script under `sim/`. No PDK, ngspice, xschem or `klt` required.
"""

from __future__ import annotations

import argparse
import math
import random
import re
import sys
from pathlib import Path
from statistics import fmean, pstdev

HERE = Path(__file__).resolve().parent
SCHEMATIC = HERE / "tb_jitter_calibration.sch"
MANIFEST = HERE / "tb.json"

#: Nominal period, in seconds. Deliberately the 3.9170 ns period of the
#: 255.3 MHz post-lock output frequency trial 5 of
#: `sim/pll-lock-mc/records/20260924-222341-a9375a5.md` measured -- the same
#: period `sim/jitter-floor`'s A3/B/C variants ran at, so this campaign's
#: reported figures and that campaign's floors are read at one period.
PERIOD_NOM_S = 3.9170e-9

#: Cycles in the population. Issue #185's own sizing note: a few hundred
#: periods is plenty for an RMS estimate, and it keeps the committed edge
#: schedule small (a 50 us window at this period would be ~12,700 periods).
CYCLES = 300

#: Rail. `measure.threshold_frac` x the manifest's `supply_nominal` puts the
#: comparison threshold at exactly half of this.
V_HIGH = 1.8

#: Lead-in before the first rising edge, so the first ramp starts after t = 0.
T_START_S = 2.0e-9

#: Time written to the netlist in nanoseconds with this many decimals, i.e. a
#: 1 fs quantum -- four orders of magnitude below the smallest jitter figure
#: injected here (0.5 % of 3.9170 ns = 19.6 ps).
TIME_DECIMALS = 6

#: Points per continuation line in the emitted `pwl(...)` card.
POINTS_PER_LINE = 4


class GeneratorError(RuntimeError):
    pass


#: The variant family. Three injected RMS values x three edge rates, named
#: `J<rms-in-tenths-of-a-percent><edge-letter>`; the edge letters match
#: `sim/jitter-floor`'s own family so the two controls line up variant for
#: variant at the same 200 ps dump grid:
#:
#:   a = 20 ps   -- a tenth of a grid step, an edge the grid cannot resolve
#:                  (jitter-floor's A3)
#:   b = 200 ps  -- exactly one grid step, the marginal case (jitter-floor's B)
#:   c = 1 ns    -- five grid steps, an edge the grid resolves (jitter-floor's C)
#:
#: The seed depends only on the injected RMS, so the three edge variants of one
#: RMS carry the **identical** edge schedule and differ in nothing but the
#: transition time -- which is what isolates the grid's contribution.
VARIANTS = {
    "J05a": {"rms_frac": 0.005, "seed": 185005, "edge_s": 20e-12},
    "J05b": {"rms_frac": 0.005, "seed": 185005, "edge_s": 200e-12},
    "J05c": {"rms_frac": 0.005, "seed": 185005, "edge_s": 1e-9},
    "J10a": {"rms_frac": 0.010, "seed": 185010, "edge_s": 20e-12},
    "J10b": {"rms_frac": 0.010, "seed": 185010, "edge_s": 200e-12},
    "J10c": {"rms_frac": 0.010, "seed": 185010, "edge_s": 1e-9},
    "J20a": {"rms_frac": 0.020, "seed": 185020, "edge_s": 20e-12},
    "J20b": {"rms_frac": 0.020, "seed": 185020, "edge_s": 200e-12},
    "J20c": {"rms_frac": 0.020, "seed": 185020, "edge_s": 1e-9},
}


def standard_normals(seed: int, n: int) -> list:
    """`n` standard normal deviates, from `Random.random()` by Box-Muller.

    Explicit rather than `random.gauss()`: `Random.random()`'s Mersenne
    Twister stream is a documented, version-stable contract, while
    `random.gauss()`'s cached-second-deviate bookkeeping is an implementation
    detail this evidence trail should not depend on.
    """
    if n <= 0:
        raise GeneratorError(f"need at least one deviate, got {n}")
    rng = random.Random(seed)
    out: list = []
    while len(out) < n:
        u1 = rng.random()
        while u1 <= 0.0:  # log(0) guard; Random.random() may return 0.0
            u1 = rng.random()
        u2 = rng.random()
        radius = math.sqrt(-2.0 * math.log(u1))
        angle = 2.0 * math.pi * u2
        out.append(radius * math.cos(angle))
        if len(out) < n:
            out.append(radius * math.sin(angle))
    return out


def normalized_normals(seed: int, n: int) -> list:
    """`standard_normals`, shifted and scaled to exactly zero mean, unit pstdev."""
    raw = standard_normals(seed, n)
    mu = fmean(raw)
    sigma = pstdev(raw)
    if sigma <= 0.0:
        raise GeneratorError("degenerate draw: the deviates have zero spread")
    return [(g - mu) / sigma for g in raw]


def periods(rms_frac: float, seed: int, cycles: int = CYCLES,
            period_nom_s: float = PERIOD_NOM_S) -> list:
    """The injected period sequence `T_k`, with `pstdev/mean == rms_frac`."""
    if not 0.0 < rms_frac < 1.0:
        raise GeneratorError(
            f"rms_frac must be a fraction strictly inside (0, 1), got {rms_frac}"
        )
    return [period_nom_s * (1.0 + rms_frac * g)
            for g in normalized_normals(seed, cycles)]


def rising_edges(period_list: list, t_start_s: float = T_START_S) -> list:
    """Rising 50 % crossing instants: `len(period_list) + 1` of them."""
    edges = [t_start_s]
    for period in period_list:
        edges.append(edges[-1] + period)
    return edges


def _ns(seconds: float) -> str:
    return f"{seconds * 1e9:.{TIME_DECIMALS}f}n"


def _v(value: float) -> str:
    return f"{value:g}"


def pwl_points(rising: list, period_list: list, edge_s: float) -> list:
    """`(time_s, volts)` pairs of the trapezoidal clock, in emission order.

    Each rising crossing sits exactly at the midpoint of a symmetric
    `0 -> V_HIGH` ramp of width `edge_s`, and each cycle's falling crossing at
    exactly half that cycle's own period later -- so the 50 % crossings are
    the schedule itself, and duty cycle stays 50 % for every cycle regardless
    of how that cycle's period was drawn.
    """
    half = edge_s / 2.0
    if rising[0] - half <= 0.0:
        raise GeneratorError(
            "the first ramp would start at or before t = 0; raise T_START_S"
        )
    pts: list = [(0.0, 0.0)]
    for k, t_rise in enumerate(rising):
        # The final rising edge closes no cycle of its own, so it borrows the
        # nominal half-period for its fall. It is outside the measured
        # population either way (a period needs two edges to bound it).
        period = period_list[k] if k < len(period_list) else fmean(period_list)
        t_fall = t_rise + period / 2.0
        pts.append((t_rise - half, 0.0))
        pts.append((t_rise + half, V_HIGH))
        pts.append((t_fall - half, V_HIGH))
        pts.append((t_fall + half, 0.0))
    times = [t for t, _ in pts]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise GeneratorError(
            "PWL times are not strictly increasing -- the transition time is "
            "too long for the shortest drawn period"
        )
    return pts


def pwl_card(points: list) -> str:
    """The `VCLK CLK GND pwl(...)` SPICE card, with `+` continuations."""
    chunks = []
    for start in range(0, len(points), POINTS_PER_LINE):
        chunk = points[start:start + POINTS_PER_LINE]
        chunks.append(" ".join(f"{_ns(t)} {_v(v)}" for t, v in chunk))
    body = "\n+ ".join(chunks)
    return f"VCLK CLK GND pwl(\n+ {body}\n+ )"


def variant_schedule(variant: str) -> dict:
    """Everything a variant pins, plus the exact figure it injects."""
    try:
        spec = VARIANTS[variant]
    except KeyError:
        raise GeneratorError(
            f"unknown variant {variant!r}; known: {', '.join(sorted(VARIANTS))}"
        ) from None
    period_list = periods(spec["rms_frac"], spec["seed"])
    rising = rising_edges(period_list)
    points = pwl_points(rising, period_list, spec["edge_s"])
    return {
        "variant": variant,
        "rms_frac": spec["rms_frac"],
        "seed": spec["seed"],
        "edge_s": spec["edge_s"],
        "cycles": len(period_list),
        "period_nom_s": PERIOD_NOM_S,
        "periods": period_list,
        "rising": rising,
        "points": points,
        "card": pwl_card(points),
        # The exact injected figure, computed with `measure.period_jitter`'s
        # own estimator over the same population the reducer will form.
        "injected_frac": pstdev(period_list) / fmean(period_list),
        "span_s": rising[-1] - rising[0],
        "last_point_s": points[-1][0],
    }


HEADER = """v {{xschem version=3.4.7 file_version=1.2
* tb_jitter_calibration.sch -- period-jitter CALIBRATION control (issue #185)
*
* GENERATED FILE -- do not hand-edit. Regenerate with
*   python3 sim/jitter-calibration/testbench/gen_pwl_clock.py --variant {variant}
* That script's module docstring is the authoritative description of how the
* edge schedule below is built and why its injected figure is exact.
*
* DELIBERATELY NOT A PLL, and deliberately NOT a null control. The whole DUT
* is one piecewise-linear voltage source and one load resistor. Unlike
* sim/jitter-floor/testbench/tb_jitter_floor.sch -- whose pulse source has a
* period that is exactly constant, i.e. TRUE period jitter of zero -- this
* source's rising edges are scheduled from a seeded RNG at a KNOWN, nonzero
* RMS period jitter. Pushing it through the identical
* `linearize` -> `wrdata` -> `edge_times` -> `period_jitter` path answers the
* question a null control cannot: what does this pipeline REPORT when the
* signal it is handed genuinely jitters by a stated amount (issue #185)?
*
* Committed state: variant {variant} -- {cycles} cycles of nominal period
* {period_ns:.4f} ns at an injected {injected_pct:.3f}% RMS period jitter
* (seed {seed}), transition time TR = TF = {edge}. The `pwl(...)` card below
* IS the schedule: every 50% crossing is the exact midpoint of a symmetric
* ramp, so the injected figure is a property of this text rather than a claim
* about the generator. sim/jitter-calibration/analysis/calibration.py
* re-derives it from each record's own committed per-point netlist.
*
* Why there is no sky130 device here at all: a control has to isolate the
* thing under test, which is the harness's own reduction path and not a
* circuit, so anything that could itself jitter is removed. The sky130 .lib
* include below is kept anyway, unused, so the harness's per-point corner
* substitution (`corner_pattern`) has something real to patch and this
* campaign's records carry the same PDK/model/simulator environment
* provenance every other record under sim/ carries -- the same choice
* tb_jitter_floor.sch makes, for the same reasons.
*
* No `.tran` card here on purpose -- sim/harness/measure.py injects the
* transient window, the `linearize` onto the manifest's `tran_step` grid, the
* `wrdata` dump and the completion marker from sim/jitter-calibration/
* testbench/tb.json's own `measure` block.
*
* Provenance: schematic-capture convention (label-based wiring, one lab_pin
* per net, zero drawn wire segments) matches sim/jitter-floor/testbench/
* tb_jitter_floor.sch; written fresh for issue #185, no external source
* netlist.
}}
G {{}}
V {{}}
S {{}}
E {{}}
C {{devices/lab_pin.sym}} 0 -30 0 0 {{name=p1 sig_type=std_logic lab=CLK}}
C {{devices/gnd.sym}} 0 30 0 0 {{name=l1 lab=GND}}
C {{devices/res.sym}} 300 0 0 0 {{name=R1 value=1k}}
C {{devices/lab_pin.sym}} 300 -30 0 0 {{name=p2 sig_type=std_logic lab=CLK}}
C {{devices/gnd.sym}} 300 30 0 0 {{name=l2 lab=GND}}
C {{devices/code.sym}} 600 -100 0 0 {{name=CLKSRC
only_toplevel=true
format="tcleval( @value )"
value="
** GENERATED -- variant {variant}: {cycles} cycles, nominal period
** {period_ns:.4f} ns, injected period jitter {injected_pct:.6f}% RMS
** (seeded RNG, seed {seed}), TR = TF = {edge}.
{card}
"
spice_ignore=false}}
C {{devices/code.sym}} 600 200 0 0 {{name=MODELS
only_toplevel=true
format="tcleval( @value )"
value="
** sky130 PDK model include (tt corner) -- patched per-point by sim/harness.
** No device in this testbench uses it: it is here so the harness's own
** corner substitution and this record's environment provenance are the same
** as every other campaign's. See this file's header comment.
.lib $::SKYWATER_MODELS/sky130.lib.spice tt
** No .tran/.print card here on purpose -- sim/harness/measure.py injects the
** analysis from this manifest's own measure block.
"
spice_ignore=false}}
C {{devices/title.sym}} -200 300 0 0 {{name=l3 author="2AM Logic (issue #185, period-jitter calibration control)"}}
"""


def render_schematic(schedule: dict) -> str:
    edge_s = schedule["edge_s"]
    edge = f"{edge_s * 1e12:g} ps" if edge_s < 1e-9 else f"{edge_s * 1e9:g} ns"
    return HEADER.format(
        variant=schedule["variant"],
        cycles=schedule["cycles"],
        period_ns=schedule["period_nom_s"] * 1e9,
        injected_pct=100.0 * schedule["injected_frac"],
        seed=schedule["seed"],
        edge=edge,
        card=schedule["card"],
    )


_MANIFEST_VARIANT_RE = re.compile(r"THIS RECORD'S VARIANT: [A-Za-z0-9]+")


def retarget_manifest(text: str, variant: str) -> str:
    """Point `tb.json`'s methodology note at `variant`.

    A targeted string substitution rather than a JSON round-trip, so the
    manifest's committed formatting is untouched by a variant change.
    """
    updated, n = _MANIFEST_VARIANT_RE.subn(
        f"THIS RECORD'S VARIANT: {variant}", text
    )
    if n != 1:
        raise GeneratorError(
            f"expected exactly one `THIS RECORD'S VARIANT: <id>` marker in the "
            f"manifest, found {n}"
        )
    return updated


def describe(schedule: dict) -> str:
    edge_s = schedule["edge_s"]
    return "\n".join(
        [
            f"variant           {schedule['variant']}",
            f"seed              {schedule['seed']}",
            f"cycles            {schedule['cycles']}",
            f"nominal period    {schedule['period_nom_s'] * 1e9:.4f} ns",
            f"injected jitter   {100.0 * schedule['injected_frac']:.6f}% RMS "
            f"(requested {100.0 * schedule['rms_frac']:.3f}%)",
            f"transition time   {edge_s * 1e12:.1f} ps",
            f"min / max period  {min(schedule['periods']) * 1e9:.6f} ns / "
            f"{max(schedule['periods']) * 1e9:.6f} ns",
            f"edge schedule     {schedule['rising'][0] * 1e9:.6f} ns .. "
            f"{schedule['rising'][-1] * 1e9:.6f} ns "
            f"({schedule['span_s'] * 1e6:.6f} us)",
            f"last PWL point    {schedule['last_point_s'] * 1e9:.6f} ns",
            f"PWL points        {len(schedule['points'])}",
        ]
    )


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--variant",
        required=True,
        help=f"which variant to generate ({', '.join(sorted(VARIANTS))})",
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--describe", action="store_true",
        help="print what this variant injects and write nothing",
    )
    mode.add_argument(
        "--emit-card", action="store_true",
        help="print the `VCLK ... pwl(...)` SPICE card and write nothing",
    )
    args = ap.parse_args(argv)

    try:
        schedule = variant_schedule(args.variant)
        if args.describe:
            print(describe(schedule))
            return 0
        if args.emit_card:
            print(schedule["card"])
            return 0
        SCHEMATIC.write_text(render_schematic(schedule))
        MANIFEST.write_text(retarget_manifest(MANIFEST.read_text(), args.variant))
    except (GeneratorError, OSError) as exc:
        print(f"gen_pwl_clock.py: {exc}", file=sys.stderr)
        return 2

    print(f"wrote {SCHEMATIC.name} and retargeted {MANIFEST.name} at variant "
          f"{args.variant}")
    print(describe(schedule))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
