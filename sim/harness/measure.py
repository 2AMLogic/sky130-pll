"""Derive design measurements from a transient run, instead of only plumbing.

Everything else in `sim/harness` judges a PVT point by whether ngspice
*finished* it (`runner._run_ngspice_and_judge`'s "exits 0, printed its
analysis-completion marker, emitted no `Error:` line"). That is a harness
plumbing check, not a design measurement -- it cannot say what frequency the
DUT ran at, whether a loop locked, or how asymmetric the output clock was.
This module is the missing measurement layer.

Two halves, deliberately separated so the arithmetic is testable without a
simulator (`sim/tests/test_measure.py` drives every function below from
synthetic traces):

1. **Stimulus** -- `build_control_block` composes the ngspice `.control`
   section the runner injects into each patched netlist: initial conditions,
   one `tran` per swept point, `linearize` onto a uniform grid, and a
   `wrdata` dump of the measured node. Putting the analysis here rather than
   in the testbench schematic is what makes the transient window a manifest
   knob -- `sim/pll` can run a lock-capable window without editing
   `tb_pll.sch`, and a sweep campaign (`sim/vco`) can run every swept point
   inside one ngspice invocation, paying the sky130 model-library parse once.
2. **Reduction** -- `parse_wrdata` -> `edge_times` -> `mean_frequency` /
   `duty_cycle` / `lock_time` / `period_jitter` -> `measure_trace`, which folds
   those into one `Measurement` per (point, swept value). A manifest with a
   `measure.ripple` block also dumps the named DC-ish nodes
   (`parse_wrdata_columns`) and reduces each to a peak-to-peak figure over the
   final settled window of the transient (`ripple_pp`), reported alongside --
   never gating -- the clock measurement. A manifest with a `measure.transition`
   block additionally reduces the same `v(node)` samples `edge_times` already
   has in hand to a rise/fall transition time (`transition_times`, issue
   #186) -- the 10-90% (default; a manifest may state another pair of
   fractions) edge speed, again reported alongside and never gating the
   clock measurement.

## What "locked" means here

Stated once, in code, so every record that cites it means the same thing:

> The output is **locked at time t** when the mean output frequency over
> *every* sliding window of `window_cycles` consecutive output cycles
> beginning at or after `t` lies within +/- `tolerance_frac` of the target
> frequency, and does so through the end of the simulated window, with at
> least `min_hold_cycles` output cycles of in-band data after `t`.
> **Time-to-lock** is the earliest such `t`. If no such `t` exists, the point
> reports **no lock** -- explicitly, never as "the frequency at the end of
> the run".

The `min_hold_cycles` term is what stops the criterion being trivially
satisfied by the final window of a run that is still slewing: without it, a
loop that first touches the target band one cycle before the transient ends
would be reported as locked. The "through the end of the simulated window"
term is what stops a loop that locks and then falls back out from being
reported as locked at its first excursion into the band.

## What "period jitter" means here

`spec/target-spec.md` row 9 is **RATIFIED** (`DR-006`, #151) and states the
quantity in percentage form, so this module measures exactly that form and
nothing else:

> **Period jitter** is the standard deviation of the measured period `T_k`
> over a population of consecutive output cycles taken after lock, divided by
> that population's mean period. It is reported as a **fraction** internally
> (`Measurement.period_jitter_frac`) and rendered as a percentage; any
> absolute picosecond figure is a derived restatement of it, never the
> measured quantity.

Three choices that a reader of a record is owed, stated here once:

- **The population is post-lock, and "lock" means this module's one lock
  criterion.** The population starts at `lock_time`'s `t_lock` when the
  manifest declares a `lock` block, and at `settle_from` when it does not.
  There is deliberately no second "has it settled yet" test -- a jitter
  number whose window was chosen by a different rule than the record's own
  lock column would not be comparable with it.
- **The periods come from the same interpolated rising edges everything else
  here is derived from** (`edge_times`), not from a second pass over the raw
  trace. `T_k = rising[k+1] - rising[k]`.
- **The standard deviation is the population one (`N` divisor,
  `statistics.pstdev`), not the sample estimator (`N-1`).** DR-006 words the
  spec'd quantity as a deviation "over a population of consecutive output
  cycles", i.e. over the cycles actually measured, and this reducer reports
  that literally rather than estimating the deviation of a hypothetical
  parent process. The two differ by `sqrt(N/(N-1))` -- 0.1 % at the 500-cycle
  populations a lock campaign produces, but the choice is stated rather than
  left for a reader to infer from a number.

A population smaller than the manifest's `jitter.min_cycles` yields **no
jitter number at all**, reported as such -- the same discipline the lock
criterion applies to a run that never locks (never present a value computed
from too little data as if it were the measurement).

### A gated bound may not ask for more cycles than the lock criterion guarantees

`jitter.min_cycles` and `lock.min_hold_cycles` sit in sibling blocks of the
same `measure` object, and they are **coupled**: `lock_time` only reports a
lock once at least `min_hold_cycles` cycles of in-band data follow the lock
instant, and `period_jitter`'s population is exactly those cycles. So on a
manifest that declares both blocks, the population of any *locked* point is
bounded below by `min_hold_cycles`, and the relation between the two knobs
decides what a FAIL from `_fold_jitter_bound` can mean:

- `jitter.min_cycles <= lock.min_hold_cycles` -- a locked point always holds
  enough cycles to form the statistic, so every FAIL the fold produces is a
  point that **missed** the bound: a design result, and the reason gating
  exists.
- `jitter.min_cycles > lock.min_hold_cycles` -- every locked point whose
  population lands in the gap FAILs for a population shortfall it was
  *arithmetically incapable* of avoiding. Against a ratified row that is an
  artefact verdict recorded as a design miss, which is the one thing this
  repo's evidence convention is most careful not to do.

**`MeasureSpec.from_manifest` therefore refuses the second shape** rather than
letting the fold mint the artefact, in the same place it refuses an
out-of-range `max_frac` or a `min_cycles` below 2 (#190). Rejecting at parse
time rather than merely wording the record's message more carefully is the
choice this module makes deliberately: a manifest is authored once and its
records are append-only evidence, so the cheap moment to catch the trap is
before a campaign spends hours producing a verdict a reader would then have
to be told not to believe.

The refusal is scoped to exactly the shape that can mint an artefact FAIL -- a
`lock` block, a stated `max_frac`, and `gate_on_bound` -- so the legitimate
reasons to want a larger population stay legal, and each of them already has a
way to say so in the manifest's existing vocabulary:

- a **jitter-only** manifest with no `lock` block (`sim/jitter-floor`) has no
  lock criterion to outrun, and its population starts at `settle_from`;
- a **characterization** manifest that wants a better-conditioned statistic
  than its own lock criterion guarantees sets `gate_on_bound` false (or states
  no bound at all) -- the shortfall is then reported against the point that
  hit it, never folded into a FAIL.

### The dump grid puts a floor under this figure

`build_control_block` below `linearize`s the measured node onto the manifest's
own `tran_step` grid before dumping it, and `edge_times` interpolates each
crossing linearly between the two grid samples that bracket it. So the grid
step sets a resolution floor under every jitter figure this module reports,
and row 9's bound is tight against it: 1.0 % of a 4 ns period is **40 ps**,
where `sim/pll-lock-mc`'s manifest dumps at 200 ps.

**That floor is measured, not argued** -- `sim/jitter-floor/` pushes an ideal
pulse source of exactly constant period (true period jitter zero by
construction) through this identical path, and its records report what this
module attributes to it. At a 200 ps grid the floor is not one number; it is a
function of two ratios, and the two behave very differently:

- **Transition time / grid step.** At an edge spanning five grid steps the
  floor is **0.000 %** (`sim/jitter-floor` variant C): both samples bracketing
  the 50 % crossing sit on the straight ramp, so the linear interpolation is
  exact. At one grid step it is 0.610 % (variant B), and at 1/10 of a step
  0.381-2.371 % (variants A1-A3). The floor is a *resolution* effect, so it
  collapses as soon as the grid resolves the edge.
- **Period / grid step.** For a constant period the grid phase of successive
  edges walks by the fractional part of that ratio, so at a fixed (fast) edge
  the floor runs from ~0 for a period that is an exact multiple of the step up
  to 2.371 % at variant A3's 0.585 fractional part.

**What grid a defensible row-9 figure needs**, so a future campaign does not
re-derive this:

1. **Resolve the edge.** `tran_step <= (transition time of the measured
   node)/2` makes the floor vanish rather than merely shrink. This is the
   cheap condition, but it needs the measured node's transition time to be
   known -- and for this repo's `CLK` that is not yet committed anywhere
   (issue #186).
2. **Or bound it unconditionally.** A crossing interpolated from a sample pair
   that straddles the whole edge lands in the middle of whichever grid
   interval holds it, so the per-edge error is bounded by half a step and the
   per-period floor is of order `0.4-0.5 * tran_step` RMS: exactly
   `tran_step * sqrt(f * (1 - f))` for a perfectly periodic clock of
   `(k + f)` steps (its maximum, `tran_step / 2`, at `f = 0.5`), and
   `sqrt(2) * tran_step / sqrt(12)` = `0.41 * tran_step` for edges landing at
   independent, uniformly-spread grid phases. Against row 9's 40 ps budget:
   200 ps buys a worst case of 100 ps (2.5x the whole budget), 20 ps buys
   10 ps (a quarter of it -- 6.4 ps at `sim/pll-lock-mc`'s own measured
   period), 10 ps buys 5 ps. `sim/tests/test_measure.py`'s
   `DumpGridResolutionFloorTests` pins those two figures.
3. **Cost it honestly.** `tran_step` also caps ngspice's internal timestep, so
   a 10x finer grid is roughly a 10x wall-clock cost on a campaign whose
   points already run ~1 h 20 m each. Refining the grid is a real spend, which
   is why `sim/jitter-floor` exists: the floor itself is measurable for the
   price of one 60-second run of a source and a resistor, with no PLL
   transient at all.

Two limits of that control, stated here because they bound what the floor
numbers above can be used for: it is a **null** control (a signal with real
jitter presents its edges at grid phases spread by that jitter, not at a
constant period's deterministic walk), and it says nothing about which of its
own variants the real DUT sits at (issue #186).
`sim/pll-lock-mc/analysis/jitter-floor/restatement.md` restates that
campaign's measured figures against this family.

The first of those two limits has its own control: `sim/jitter-calibration`
(issue #185) is the same shape of testbench with a **known, exactly specified
nonzero** injected period jitter instead of zero, so what it reports is a
calibration curve rather than a floor. Its measured answer at a 200 ps grid, at
each of the two nominal periods it has run (3.9170 ns and 3.9952 ns): an edge
the grid resolves returns the injected figure exactly, and for one it cannot,
the floor a *jittering* signal carries moves away from the null control's
walk-phase figure and toward the `sqrt(2) * tran_step / sqrt(12)`
uniformly-spread-phase figure above as the source's own jitter grows relative to
the grid step. It is therefore **not** safe to assume a null-control floor is a
conservative correction for a signal that jitters -- and the *direction* of the
error is not fixed either: measured at those two periods (issue #197), the null
control over-states the floor at `frac(period/step)` = 0.585 and under-states it
at 0.976, so which way a null-control correction errs is a property of the
period being corrected. See `sim/jitter-calibration/analysis/calibration.md`.

## Loop bandwidth / phase margin are deliberately NOT measured here

Issue #52 allows scoping that decision in the implementation. Loop bandwidth
and phase margin are open-loop quantities: extracting them from a *closed*-
loop transient requires either breaking the loop (an AC analysis on a
linearized model, i.e. a different testbench topology, not a different
measurement of this one) or a step-response fit whose accuracy is dominated
by the fit's own assumptions. `2AMLogic/gf180-pll`'s harness draws the same
line -- its transient reduction covers frequency/lock/jitter-shaped
quantities, and the loop-dynamics rows are argued from a separate analysis.
Both are therefore left to a dedicated open-loop/AC testbench, not bolted
onto this transient reducer where they would produce a number nobody could
defend.

**That testbench now exists**: `sim/harness/acmeasure.py` is its reducer and
`sim/loop-ac/` is the campaign. The split above is unchanged -- this module
still measures nothing open-loop -- but the deferral is no longer open.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from statistics import fmean, pstdev

# Echoed by `build_control_block` as the last statement of the injected
# `.control` section. ngspice does not print its usual "Total analysis time"
# banner for an analysis driven from a `.control` block, so a measurement run
# needs its own completion marker -- one ngspice only reaches by executing
# every `tran` in the block.
COMPLETION_MARKER = "sim/harness: analysis complete"

_SUFFIXES = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "meg": 1e6,
    "g": 1e9,
    "t": 1e12,
}
_TIME_RE = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z]*)\s*$")


class MeasureError(ValueError):
    """A malformed `measure` manifest block, or an unusable waveform dump."""


def parse_spice_literal(text: str | float | int, *, kind: str = "time") -> float:
    """Parse a SPICE numeric literal (`50p`, `200n`, `40u`, `2ns`, `1meg`).

    Shared by `parse_spice_time` (time literals) and
    `sim.harness.acmeasure.parse_spice_freq` (frequency literals) -- the
    regex, suffix table, and `meg`-is-1e6 footgun are identical for both; the
    only thing that varies is the domain word (`kind`) substituted into the
    error message, e.g. "not a SPICE {kind} literal".

    SPICE's classic footgun is honored: `m` is milli and `meg` is 1e6. A
    trailing unit letter after the suffix (`ns`, `us`) is ignored, as ngspice
    itself ignores it.
    """
    if isinstance(text, (int, float)):
        return float(text)
    m = _TIME_RE.match(text)
    if not m:
        raise MeasureError(f"not a SPICE {kind} literal: {text!r}")
    value, suffix = float(m.group(1)), m.group(2).lower()
    if not suffix:
        return value
    if suffix.startswith("meg"):
        return value * _SUFFIXES["meg"]
    scale = _SUFFIXES.get(suffix[0])
    if scale is None:
        raise MeasureError(f"unknown SPICE {kind} suffix in {text!r}")
    return value * scale


def parse_spice_time(text: str | float | int) -> float:
    """Parse a SPICE time literal (`50p`, `200n`, `40u`, `2ns`, `1meg`).

    SPICE's classic footgun is honored: `m` is milli and `meg` is 1e6. A
    trailing unit letter after the suffix (`ns`, `us`) is ignored, as ngspice
    itself ignores it.
    """
    return parse_spice_literal(text, kind="time")


@dataclass(frozen=True)
class SweepPoint:
    """One value of a swept independent source within a single PVT point."""

    source: str
    value: float
    label: str


@dataclass(frozen=True)
class LockSpec:
    target_hz: float
    tolerance_frac: float
    window_cycles: int
    min_hold_cycles: int

    @property
    def summary(self) -> str:
        return (
            f"mean output frequency over every sliding window of "
            f"{self.window_cycles} output cycles stays within "
            f"+/-{self.tolerance_frac * 100:g}% of {self.target_hz / 1e6:g} MHz "
            f"through the end of the transient, with at least "
            f"{self.min_hold_cycles} cycles of in-band data after the lock instant"
        )


@dataclass(frozen=True)
class JitterSpec:
    """The `measure.jitter` block of a `tb.json` manifest, parsed.

    `max_frac` is the bound as a **fraction of the output period** (`0.01` is
    `spec/target-spec.md` row 9's ratified 1.0 %), or `None` for a campaign
    that wants the number recorded without a bound stated against it.
    """

    max_frac: float | None = None
    min_cycles: int = 20
    # Unlike `acmeasure.AcSpec.gate_on_bounds` (default `false`, because rows 6
    # and 7 are DRAFT and a harness verdict must not read as ratifying one),
    # this defaults to `true`: row 9 IS ratified, so a manifest that states the
    # bound at all is stating a ratified one, and a point that misses it cannot
    # honestly be folded into a PASS. A characterization campaign that wants
    # the number reported without gating on it says so explicitly.
    gate_on_bound: bool = True

    @property
    def summary(self) -> str:
        population = (
            f"a population of at least {self.min_cycles} consecutive post-lock "
            f"output cycles"
        )
        if self.max_frac is None:
            return (
                f"period jitter -- the standard deviation of the measured period "
                f"over {population}, divided by that population's mean period -- "
                f"is reported for each point; this manifest states no bound"
            )
        return (
            f"the standard deviation of the measured period over {population}, "
            f"divided by that population's mean period, is at most "
            f"{self.max_frac * 100:g}% "
            + (
                "(gated: a point that misses it FAILs)"
                if self.gate_on_bound
                else "(reported, but not gated on, for this manifest)"
            )
        )


@dataclass(frozen=True)
class RippleSpec:
    """The optional `measure.ripple` block: which DC-ish nodes to reduce to a
    peak-to-peak ripple figure, and over how long a settled window.

    The window is the **final** `window_s` of the transient,
    `[tran_stop - window_s, tran_stop]`. Anchoring it to the end of the run
    rather than to the measured lock instant is deliberate: the lock
    criterion is a +/- few-percent frequency band, and a loop that has just
    entered it is still slewing `VCTRL` towards its final value -- a window
    starting at the lock instant would fold that residual settling drift into
    the "ripple" figure. See `ripple_pp`.
    """

    nodes: tuple
    window_s: float

    @property
    def summary(self) -> str:
        names = ", ".join(f"v({n})" for n in self.nodes)
        return f"peak-to-peak of {names} over the final {_fmt_s(self.window_s)} of the transient"


@dataclass(frozen=True)
class TransitionSpec:
    """The optional `measure.transition` block: reduce the measured node's
    own edges to a rise/fall transition time (issue #186), reported --
    never gated -- alongside frequency/duty/jitter.

    `frac_lo`/`frac_hi` are fractions of the node's `[0, supply_v]` swing
    (the same convention `threshold_frac` uses for the 50% crossing), the
    levels a rising edge's duration is measured between (in the reverse
    order for a falling edge). The conventional figure is 10-90%
    (`frac_lo=0.1`, `frac_hi=0.9`, this module's default); `sim/jitter-floor`
    also cites 20-80% as an equally defensible alternative convention, so a
    manifest that wants it states so explicitly rather than this module
    picking for it.
    """

    frac_lo: float = 0.1
    frac_hi: float = 0.9

    @property
    def summary(self) -> str:
        return (
            f"{self.frac_lo * 100:g}-{self.frac_hi * 100:g}% transition time "
            f"(rise/fall separately), each edge's duration between linearly "
            f"interpolated crossings of {self.frac_lo:g}*VDD and "
            f"{self.frac_hi:g}*VDD"
        )


@dataclass(frozen=True)
class MeasureSpec:
    """The `measure` block of a `tb.json` manifest, parsed."""

    node: str
    tran_step: str
    tran_stop: str
    timeout_s: int = 3600
    threshold_frac: float = 0.5
    hysteresis_frac: float = 0.15
    settle_from_s: float = 0.0
    min_edges: int = 4
    ic: tuple = ()
    uic: bool = False
    sweep: tuple = ()
    lock: LockSpec | None = None
    jitter: JitterSpec | None = None
    require_lock: bool = False
    require_oscillation: bool = True
    # For a swept campaign: how many of the swept values must oscillate for
    # the PVT point to pass. A characterization sweep deliberately runs past
    # the edges of the tuning range -- "the ring is dead at the bottom of the
    # swept range" is data, not a harness failure -- so such a manifest sets
    # `require_oscillation` false and gates on this count instead, which still
    # catches the real failure (a corner where nothing oscillates at all).
    min_oscillating_points: int = 0
    extra_nodes: tuple = field(default=())
    ripple: RippleSpec | None = None
    transition: TransitionSpec | None = None

    @property
    def tran_stop_s(self) -> float:
        return parse_spice_time(self.tran_stop)

    @property
    def dump_nodes(self) -> tuple:
        """Every node this spec dumps, in `wrdata` column order.

        The measured `node` is always first (so `parse_wrdata`'s two-column
        read of a dump is unchanged), then `extra_nodes`, then any ripple node
        not already listed. Duplicates are dropped, first occurrence wins.
        """
        ordered = []
        ripple_nodes = self.ripple.nodes if self.ripple else ()
        for n in (self.node,) + tuple(self.extra_nodes) + tuple(ripple_nodes):
            if n not in ordered:
                ordered.append(n)
        return tuple(ordered)

    @classmethod
    def from_manifest(cls, manifest: dict):
        block = manifest.get("measure")
        if not block:
            return None
        for required in ("node", "tran_step", "tran_stop"):
            if required not in block:
                raise MeasureError(f"manifest `measure` block is missing {required!r}")

        lock = None
        if "lock" in block:
            lk = block["lock"]
            missing = [k for k in ("target_hz", "tolerance_frac", "window_cycles") if k not in lk]
            if missing:
                raise MeasureError(
                    f"manifest `measure.lock` block is missing {', '.join(missing)}"
                )
            lock = LockSpec(
                target_hz=float(lk["target_hz"]),
                tolerance_frac=float(lk["tolerance_frac"]),
                window_cycles=int(lk["window_cycles"]),
                min_hold_cycles=int(lk.get("min_hold_cycles", lk["window_cycles"])),
            )

        jitter = None
        if "jitter" in block:
            jt = block["jitter"]
            if jt is None:
                jt = {}
            if not isinstance(jt, dict):
                raise MeasureError("manifest `measure.jitter` block must be an object")
            raw_max = jt.get("max_frac")
            max_frac = None if raw_max is None else float(raw_max)
            if max_frac is not None and not 0.0 < max_frac < 1.0:
                raise MeasureError(
                    f"manifest `measure.jitter.max_frac` must be a fraction of the "
                    f"output period in (0, 1) -- got {raw_max!r}; row 9's ratified "
                    f"1.0 % bound is 0.01, not 1.0"
                )
            min_cycles = int(jt.get("min_cycles", 20))
            if min_cycles < 2:
                raise MeasureError(
                    "manifest `measure.jitter.min_cycles` must be at least 2 "
                    "(a standard deviation needs two periods)"
                )
            gate_on_bound = bool(jt.get("gate_on_bound", True))
            # The two knobs are coupled -- see "A gated bound may not ask for
            # more cycles than the lock criterion guarantees" in the module
            # docstring. `lock_time` only reports a lock once at least
            # `min_hold_cycles` cycles of in-band data follow the lock
            # instant, and the jitter population is exactly those cycles, so a
            # gated bound asking for more would FAIL a locked point for a
            # shortfall it was arithmetically incapable of avoiding.
            if (
                lock is not None
                and gate_on_bound
                and max_frac is not None
                and min_cycles > lock.min_hold_cycles
            ):
                raise MeasureError(
                    f"manifest `measure.jitter.min_cycles` ({min_cycles}) exceeds "
                    f"`measure.lock.min_hold_cycles` ({lock.min_hold_cycles}), and "
                    f"this manifest gates on its jitter bound. A locked point's "
                    f"jitter population is exactly the in-band cycles the lock "
                    f"criterion held for, so every locked point whose population "
                    f"lands in the {lock.min_hold_cycles}-{min_cycles} cycle gap "
                    f"would FAIL for a shortfall it could not avoid -- an artefact "
                    f"verdict recorded as a design miss. Lower min_cycles to at "
                    f"most {lock.min_hold_cycles}, raise min_hold_cycles to at "
                    f"least {min_cycles}, or set `gate_on_bound` false to report "
                    f"the number without gating on it"
                )
            jitter = JitterSpec(
                max_frac=max_frac,
                min_cycles=min_cycles,
                gate_on_bound=gate_on_bound,
            )

        sweep = ()
        if "sweep" in block:
            sw = block["sweep"]
            for required in ("source", "values"):
                if required not in sw:
                    raise MeasureError(f"manifest `measure.sweep` block is missing {required!r}")
            quantity = sw.get("quantity", sw["source"])
            sweep = tuple(
                SweepPoint(
                    source=sw["source"],
                    value=float(v),
                    label=f"{quantity}={float(v):.3f}V",
                )
                for v in sw["values"]
            )

        ripple = None
        if "ripple" in block:
            rp = block["ripple"]
            missing = [k for k in ("nodes", "window") if k not in rp]
            if missing:
                raise MeasureError(
                    f"manifest `measure.ripple` block is missing {', '.join(missing)}"
                )
            nodes = tuple(rp["nodes"])
            if not nodes:
                raise MeasureError("manifest `measure.ripple.nodes` is empty")
            window_s = parse_spice_time(rp["window"])
            stop_s = parse_spice_time(str(block["tran_stop"]))
            if not 0.0 < window_s <= stop_s:
                raise MeasureError(
                    f"manifest `measure.ripple.window` ({rp['window']!r}) must be "
                    f"positive and no longer than tran_stop ({block['tran_stop']!r})"
                )
            if sweep:
                # A swept campaign re-runs the transient per swept value; a
                # per-sweep ripple figure is not something any campaign needs
                # yet, so refuse it rather than silently reducing only one.
                raise MeasureError("`measure.ripple` is not supported on a swept manifest")
            ripple = RippleSpec(nodes=nodes, window_s=window_s)

        transition = None
        if "transition" in block:
            trb = block["transition"]
            if trb is None or trb is True:
                trb = {}
            if not isinstance(trb, dict):
                raise MeasureError(
                    "manifest `measure.transition` block must be an object "
                    "(or `true` for the default 10-90%)"
                )
            frac_lo = float(trb.get("frac_lo", 0.1))
            frac_hi = float(trb.get("frac_hi", 0.9))
            if not 0.0 <= frac_lo < frac_hi <= 1.0:
                raise MeasureError(
                    "manifest `measure.transition` fractions must satisfy "
                    f"0 <= frac_lo < frac_hi <= 1 -- got frac_lo={frac_lo!r}, "
                    f"frac_hi={frac_hi!r}"
                )
            transition = TransitionSpec(frac_lo=frac_lo, frac_hi=frac_hi)

        return cls(
            node=block["node"],
            tran_step=str(block["tran_step"]),
            tran_stop=str(block["tran_stop"]),
            timeout_s=int(block.get("timeout_s", 3600)),
            threshold_frac=float(block.get("threshold_frac", 0.5)),
            hysteresis_frac=float(block.get("hysteresis_frac", 0.15)),
            settle_from_s=parse_spice_time(block.get("settle_from", 0)),
            min_edges=int(block.get("min_edges", 4)),
            ic=tuple(block.get("ic", ())),
            uic=bool(block.get("uic", False)),
            sweep=sweep,
            lock=lock,
            jitter=jitter,
            require_lock=bool(block.get("require_lock", False)),
            require_oscillation=bool(block.get("require_oscillation", True)),
            min_oscillating_points=int(block.get("min_oscillating_points", 0)),
            extra_nodes=tuple(block.get("extra_nodes", ())),
            ripple=ripple,
            transition=transition,
        )


def waveform_names(spec: MeasureSpec, prefix: str = "") -> list:
    """Per-run waveform dump filenames, in swept order.

    `prefix` namespaces the dumps per PVT point, since every point of a run
    shares one `corners/<record-id>/` working directory.

    The `.raw` extension is load-bearing, not cosmetic: `sim/README.md`'s
    retention policy keeps waveform dumps *out* of the committed evidence
    trail (they are regenerable from the frozen netlist plus the logged
    environment), and the repo's root `.gitignore` implements that with a
    tree-wide `*.raw` rule. A dump written under any other extension would be
    swept into the record's committed `corners/<record-id>/` directory.
    """
    n = max(1, len(spec.sweep))
    return [f"{prefix}point{i:03d}.raw" for i in range(n)]


def build_control_block(spec: MeasureSpec, prefix: str = "") -> str:
    """Compose the `.ic` cards plus the `.control` section for one PVT point."""
    lines = [f".ic {card}" for card in spec.ic]
    lines.append(".control")
    lines.append("set filetype=ascii")
    tran = f"tran {spec.tran_step} {spec.tran_stop}" + (" uic" if spec.uic else "")
    nodes = spec.dump_nodes
    vectors = " ".join(f"v({n})" for n in nodes)
    multi = len(nodes) > 1
    if multi:
        # One shared time column instead of ngspice's default (scale, value)
        # pair per vector, so a multi-node dump reads as `t v1 v2 ...`.
        # `parse_wrdata_columns` accepts either layout regardless, and a
        # single-node dump is identical under both, so the single-node
        # control block is left byte-for-byte as it always was.
        lines.append("set wr_singlescale")
    # `save` is load-bearing on a long window, not an optimisation: ngspice
    # otherwise retains every node voltage and branch current of the whole
    # hierarchy for every timepoint, and a lock-capable transient across a
    # few-hundred-node DUT exhausts memory ("Setting the output memory is not
    # possible") long before it reaches the stop time. Only the nodes this
    # reducer actually measures are kept.
    lines.append(f"save {vectors}")
    names = waveform_names(spec, prefix)
    points = spec.sweep or (None,)
    for i, point in enumerate(points):
        if point is not None:
            lines.append(f"alter {point.source} {point.value:g}")
        lines.append(tran)
        # `linearize` with arguments builds a *new* plot holding only the
        # vectors it names, and makes that plot current -- so every dumped
        # vector has to be named here, or `wrdata` below would not find it.
        lines.append(f"linearize {vectors}" if multi else f"linearize v({spec.node})")
        lines.append(f"wrdata {names[i]} {vectors}")
        # Free the swept point's plot before the next one: a sweep campaign
        # runs every point inside one ngspice invocation, so without this the
        # retained plots accumulate across the whole sweep.
        lines.append("destroy all")
    lines.append(f'echo "{COMPLETION_MARKER}"')
    lines.append(".endc")
    return "\n".join(lines) + "\n"


def parse_wrdata(text: str) -> tuple:
    """Parse an ngspice `wrdata` ASCII dump into (times, values).

    `wrdata` writes one whitespace-separated row per sample, with no header:
    the x column (time) followed by the vector's value. Extra columns from
    additional vectors are ignored here -- this reducer measures one node.
    """
    times, values = [], []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            t, v = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        times.append(t)
        values.append(v)
    if not times:
        raise MeasureError("waveform dump contained no samples")
    return times, values


def parse_wrdata_columns(text: str, n_vectors: int) -> tuple:
    """Parse a multi-vector ngspice `wrdata` dump into (times, [values, ...]).

    Accepts both layouts ngspice can write for `n_vectors` vectors: the
    `wr_singlescale` one (`t v1 v2 ... vn`, which `build_control_block` asks
    for) and the default paired one (`t v1 t v2 ... t vn`). Any row whose
    column count matches neither is rejected rather than guessed at -- a
    silently mis-assigned column would attribute one node's waveform to
    another.
    """
    if n_vectors < 1:
        raise MeasureError("parse_wrdata_columns needs at least one vector")
    times = []
    columns = [[] for _ in range(n_vectors)]
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            continue
        if len(nums) == n_vectors + 1:
            row = nums[1:]
        elif len(nums) == 2 * n_vectors:
            row = nums[1::2]
        else:
            raise MeasureError(
                f"waveform dump row has {len(nums)} columns; expected "
                f"{n_vectors + 1} (single scale) or {2 * n_vectors} (paired) "
                f"for {n_vectors} vector(s)"
            )
        times.append(nums[0])
        for col, v in zip(columns, row):
            col.append(v)
    if not times:
        raise MeasureError("waveform dump contained no samples")
    return times, columns


def ripple_pp(times, values, t_from: float, t_to: float | None = None) -> tuple | None:
    """(min, max, peak-to-peak) of `values` over samples with
    `t_from <= t <= t_to` (`t_to=None` means through the end of the trace).

    Returns None when no sample falls inside the window -- never a zero
    ripple, which would read as a (spuriously perfect) measurement.

    This is a plain extremum statistic over the *samples it is given*: on a
    dump `linearize`d onto a uniform grid, any excursion narrower than the
    grid step is attenuated by the resampling, so the result is the ripple
    as seen at that grid's bandwidth, not an unbounded-bandwidth peak.
    """
    window = [
        v for t, v in zip(times, values) if t >= t_from and (t_to is None or t <= t_to)
    ]
    if not window:
        return None
    lo, hi = min(window), max(window)
    return lo, hi, hi - lo


def edge_times(times, values, threshold: float, hysteresis: float = 0.0) -> tuple:
    """Interpolated threshold-crossing times, split into rising and falling.

    A crossing is only *accepted* once the signal has travelled past the far
    hysteresis rail (`threshold +/- hysteresis`), which rejects ringing that
    re-crosses the threshold without completing a real transition; the time
    reported is still the interpolated crossing of `threshold` itself, not of
    the rail, so the measurement is not biased by the hysteresis band.
    """
    hi = threshold + hysteresis
    lo = threshold - hysteresis
    rising, falling = [], []
    state = "high" if values[0] >= threshold else "low"
    for i in range(1, len(values)):
        v = values[i]
        if state == "low" and v >= hi:
            rising.append(_interpolate_back(times, values, i, threshold, rising_edge=True))
            state = "high"
        elif state == "high" and v <= lo:
            falling.append(_interpolate_back(times, values, i, threshold, rising_edge=False))
            state = "low"
    return rising, falling


def _interpolate_back(times, values, i: int, threshold: float, *, rising_edge: bool) -> float:
    """Linearly interpolate the crossing of `threshold` at or before sample `i`.

    Walks back to the last sample on the far side of `threshold` so the
    interpolation happens across the pair that actually brackets it, even
    when the accepted-crossing sample `i` is further along the transition
    (which is the normal case once hysteresis is in play).
    """
    j = i
    while j > 0:
        prev = values[j - 1]
        if (rising_edge and prev < threshold) or (not rising_edge and prev > threshold):
            break
        j -= 1
    v0, v1 = values[j - 1], values[j]
    t0, t1 = times[j - 1], times[j]
    if v1 == v0:
        return t1
    return t0 + (threshold - v0) * (t1 - t0) / (v1 - v0)


def mean_frequency(rising, t_from: float | None = None) -> float | None:
    """Mean frequency over the rising edges at or after `t_from`."""
    edges = [t for t in rising if t_from is None or t >= t_from]
    if len(edges) < 2:
        return None
    return (len(edges) - 1) / (edges[-1] - edges[0])


def duty_cycle(rising, falling, t_from: float | None = None) -> float | None:
    """Mean high-time / period over complete cycles at or after `t_from`."""
    ratios = []
    for k in range(len(rising) - 1):
        r, nxt = rising[k], rising[k + 1]
        if t_from is not None and r < t_from:
            continue
        fall = next((f for f in falling if r < f < nxt), None)
        if fall is None:
            continue
        period = nxt - r
        if period <= 0:
            continue
        ratios.append((fall - r) / period)
    if not ratios:
        return None
    return fmean(ratios)


def transition_times(
    times,
    values,
    v_lo: float,
    v_hi: float,
    frac_lo: float = 0.1,
    frac_hi: float = 0.9,
    t_from: float | None = None,
) -> tuple:
    """Rise/fall transition durations of the measured node (issue #186).

    A rising edge's duration is the time between its linearly interpolated
    crossing of `v_lo + frac_lo*(v_hi - v_lo)` and its crossing of
    `v_lo + frac_hi*(v_hi - v_lo)` (the reverse order, high level first, for
    a falling edge) -- the same linear-interpolation-between-the-bracketing-
    sample-pair method `edge_times`/`_interpolate_back` use for a single
    threshold, applied at two levels instead of one.

    Returns `(rise_times, fall_times)`, each a list of durations in seconds,
    one entry per edge that completes a **monotonic** crossing of both
    levels in the expected direction: an excursion that reverses before
    reaching the far level (e.g. ringing that re-crosses the near level) is
    silently dropped rather than contributing a bogus duration, mirroring
    `edge_times`' treatment of a crossing that never resolves. An edge whose
    near-level crossing lands before `t_from` is excluded, the same
    settle/lock-window convention `duty_cycle`/`mean_frequency` use.

    `v_lo`/`v_hi` are the node's assumed rail-to-rail swing (typically `0`
    and the PVT point's own supply voltage, mirroring `threshold_frac`'s
    convention), not a per-edge measured extremum -- a node that does not
    swing rail-to-rail under-reports both levels' separation and so
    over-reports the transition time, which is a property of the DUT stated
    once by the caller, not inferred edge-by-edge.
    """
    if frac_hi <= frac_lo:
        raise MeasureError(
            f"transition_times needs frac_lo < frac_hi -- got frac_lo={frac_lo!r}, "
            f"frac_hi={frac_hi!r}"
        )
    lo = v_lo + frac_lo * (v_hi - v_lo)
    hi = v_lo + frac_hi * (v_hi - v_lo)
    rises, falls = [], []
    pending_rise: float | None = None  # interpolated `lo` crossing time, going up
    pending_fall: float | None = None  # interpolated `hi` crossing time, going down
    for i in range(1, len(values)):
        t0, t1 = times[i - 1], times[i]
        v0, v1 = values[i - 1], values[i]
        if v0 != v1:
            if v0 < lo <= v1:
                pending_rise = t0 + (lo - v0) * (t1 - t0) / (v1 - v0)
            if pending_rise is not None and v0 < hi <= v1:
                t_hi = t0 + (hi - v0) * (t1 - t0) / (v1 - v0)
                if t_from is None or pending_rise >= t_from:
                    rises.append(t_hi - pending_rise)
                pending_rise = None

            if v0 > hi >= v1:
                pending_fall = t0 + (hi - v0) * (t1 - t0) / (v1 - v0)
            if pending_fall is not None and v0 > lo >= v1:
                t_lo = t0 + (lo - v0) * (t1 - t0) / (v1 - v0)
                if t_from is None or pending_fall >= t_from:
                    falls.append(t_lo - pending_fall)
                pending_fall = None

        # A reversal before the far level completes cancels the pending
        # crossing rather than letting the next excursion complete it with a
        # stale start time.
        if pending_rise is not None and v1 < lo:
            pending_rise = None
        if pending_fall is not None and v1 > hi:
            pending_fall = None
    return rises, falls


def lock_time(rising, spec: LockSpec) -> tuple:
    """Apply this module's lock criterion. Returns (locked, time_to_lock)."""
    w = spec.window_cycles
    if len(rising) < w + 1 + spec.min_hold_cycles:
        return False, None
    n_windows = len(rising) - w
    target, tol = spec.target_hz, spec.tolerance_frac
    last_out_of_band = -1
    for i in range(n_windows):
        span = rising[i + w] - rising[i]
        if span <= 0:
            last_out_of_band = i
            continue
        f = w / span
        if abs(f - target) > tol * target:
            last_out_of_band = i
    first = last_out_of_band + 1
    if first >= n_windows:
        return False, None
    # Cycles of in-band data remaining after the candidate lock instant.
    if (len(rising) - 1) - first < spec.min_hold_cycles:
        return False, None
    return True, rising[first]


def period_jitter(rising, t_from: float | None = None) -> tuple:
    """Row 9's quantity. Returns `(jitter_frac, n_cycles)`.

    `jitter_frac` is `pstdev(T_k) / mean(T_k)` over the consecutive cycles
    `T_k = rising[k+1] - rising[k]` whose *opening* edge is at or after
    `t_from` -- i.e. the population is the cycles the loop ran through after
    the caller's chosen start instant, never a cycle straddling it. It is a
    fraction; the percentage `spec/target-spec.md` row 9 states is
    `100 * jitter_frac`.

    Callers pass `t_from=t_lock` (see `lock_time`) so the population is the
    post-lock one row 9 is stated over. This function does not re-derive
    edges and does not apply a lock criterion of its own -- see this module's
    docstring, "What period jitter means here".

    `jitter_frac` is `None` (with `n_cycles` still reported) when there are
    fewer than two periods in the population, or when the population's mean
    period is non-positive: too little data is reported as too little data,
    never as a jitter of zero.

    **This figure carries the dump grid's resolution floor**, and at a tight
    bound that floor can be a large fraction of it -- 2.371 % of the output
    period for a 200 ps grid at one of `sim/pll-lock-mc`'s own measured
    periods, against a 1.0 % bound. The floor is measured (`sim/jitter-floor/`)
    rather than argued, it can only *inflate* this number (the per-edge error
    is independent and adds in quadrature), and the grid a defensible row-9
    figure needs is stated in this module's docstring under "The dump grid puts
    a floor under this figure". Read a number from here together with the
    `tran_step` that produced it.
    """
    edges = [t for t in rising if t_from is None or t >= t_from]
    periods = [b - a for a, b in zip(edges, edges[1:])]
    n_cycles = len(periods)
    if n_cycles < 2:
        return None, n_cycles
    mean_period = fmean(periods)
    if mean_period <= 0:
        return None, n_cycles
    return pstdev(periods) / mean_period, n_cycles


@dataclass(frozen=True)
class RippleResult:
    """`ripple_pp` over one node's settled window, plus the context a reader
    needs to know whether it is *ripple-in-lock* evidence at all."""

    node: str
    t_from_s: float
    t_to_s: float
    v_min: float | None
    v_max: float | None
    pp: float | None
    # True: the loop met the lock criterion at or before `t_from_s`, so the
    # whole window is in lock. False: it did not (never locked, or locked
    # inside the window). None: the manifest has no lock criterion.
    in_lock: bool | None

    def describe(self) -> str:
        if self.pp is None:
            return f"v({self.node}) ripple -: no samples in window"
        return (
            f"v({self.node}) ripple {_fmt_v(self.pp)} pp "
            f"[{self.v_min:.5g} .. {self.v_max:.5g} V]"
        )


def _fmt_v(value: float | None) -> str:
    if value is None:
        return "-"
    mag = abs(value)
    if mag >= 1.0:
        return f"{value:.4g} V"
    if mag >= 1e-3:
        return f"{value * 1e3:.4g} mV"
    return f"{value * 1e6:.4g} uV"


def format_v(value: float | None) -> str:
    """Public voltage formatter, for report.py's ripple table."""
    return _fmt_v(value)


@dataclass(frozen=True)
class Measurement:
    """One measured operating point of one PVT point."""

    label: str | None
    oscillating: bool
    freq_hz: float | None
    duty_cycle: float | None
    locked: bool | None
    lock_time_s: float | None
    final_freq_hz: float | None
    note: str
    passed: bool
    # Row 9 (period jitter), as a fraction of the output period -- `None` when
    # the manifest declares no `jitter` block, when the point never reached a
    # post-lock window, or when that window held fewer cycles than the
    # manifest requires. `jitter_cycles` is the population size the number was
    # computed over (or would have been, when it is too small), so a record
    # can say how much data is behind the figure it prints.
    period_jitter_frac: float | None = None
    jitter_cycles: int | None = None
    # One `RippleResult` per `measure.ripple` node; empty when the manifest
    # asks for no ripple reduction.
    ripple: tuple = ()
    # Issue #186's transition-time figure -- `None`/`0` when the manifest
    # declares no `transition` block, or when no edge of that direction
    # completed a monotonic crossing of both levels. The mean is over
    # `n_rise_edges`/`n_fall_edges` individual edge durations, reported
    # separately because a single-ended current-starved ring's rise and fall
    # need not be symmetric (design/vco/DESIGN.md's own 2:1 PMOS:NMOS sizing
    # note).
    rise_time_s: float | None = None
    fall_time_s: float | None = None
    n_rise_edges: int = 0
    n_fall_edges: int = 0

    def summary(self) -> str:
        """One-line human-readable form, used in the record's result table."""
        return self.note


def _fmt_hz(value: float | None) -> str:
    if value is None:
        return "-"
    if value >= 1e9:
        return f"{value / 1e9:.4g} GHz"
    if value >= 1e6:
        return f"{value / 1e6:.4g} MHz"
    if value >= 1e3:
        return f"{value / 1e3:.4g} kHz"
    return f"{value:.4g} Hz"


def _fmt_s(value: float | None) -> str:
    if value is None:
        return "-"
    if value < 1e-9:
        return f"{value * 1e12:.4g} ps"
    if value < 1e-6:
        return f"{value * 1e9:.4g} ns"
    if value < 1e-3:
        return f"{value * 1e6:.4g} us"
    return f"{value * 1e3:.4g} ms"


def _measure_jitter(rising, spec: MeasureSpec, t_from: float | None) -> tuple:
    """Row 9's quantity for one trace: `(frac, n_cycles, note_clause)`.

    `t_from` is the population's start instant -- `t_lock` for a manifest with
    a `lock` block, `settle_from` for one without. All three results are
    `None` when the manifest declares no `jitter` block, so a campaign that
    does not ask for jitter is byte-for-byte unaffected.
    """
    if spec.jitter is None:
        return None, None, None
    js = spec.jitter
    frac, n_cycles = period_jitter(rising, t_from=t_from)
    start = "the start of the trace" if t_from is None else _fmt_s(t_from)
    if frac is None and n_cycles >= 2:
        # `period_jitter` declined for its *other* reason: the population's
        # mean period is non-positive (only a non-monotonic edge list can do
        # that). There is plenty of data here, so calling this a population
        # shortfall would name the wrong cause.
        return None, n_cycles, (
            f"period jitter **not measured**: the {n_cycles}-cycle population "
            f"from {start} has a non-positive mean period -- a non-monotonic "
            f"edge list, not a population this manifest can form a fraction of"
        )
    if frac is None or n_cycles < js.min_cycles:
        return None, n_cycles, (
            f"period jitter **not measured**: the population from {start} holds "
            f"{n_cycles} cycle(s), fewer than the {js.min_cycles} this manifest "
            f"requires"
        )
    clause = f"period jitter {frac * 100:.3f}% RMS over {n_cycles} cycles"
    if js.max_frac is not None and frac > js.max_frac:
        clause += (
            f" -- **misses** this manifest's stated bound of "
            f"{js.max_frac * 100:g}% of the output period"
        )
    return frac, n_cycles, clause


def _measure_transition(
    times, values, spec: MeasureSpec, supply_v: float, t_from: float | None
) -> tuple:
    """Issue #186's transition-time figure for one trace:
    `(rise_mean, fall_mean, n_rise, n_fall, note_clause)`.

    `t_from` is the same population start instant `_measure_jitter` uses --
    `t_lock` for a manifest with a `lock` block, `settle_from` for one
    without -- so a transition figure is never drawn from the pre-lock
    acquisition transient either. All five results are `None`/`0`/`None`
    when the manifest declares no `transition` block, so a campaign that
    does not ask for it is byte-for-byte unaffected.
    """
    if spec.transition is None:
        return None, None, 0, 0, None
    ts = spec.transition
    rises, falls = transition_times(
        times, values, 0.0, supply_v,
        frac_lo=ts.frac_lo, frac_hi=ts.frac_hi, t_from=t_from,
    )
    rise_mean = fmean(rises) if rises else None
    fall_mean = fmean(falls) if falls else None
    tag = f"{ts.frac_lo * 100:g}-{ts.frac_hi * 100:g}%"
    if rise_mean is None and fall_mean is None:
        start = "the start of the trace" if t_from is None else _fmt_s(t_from)
        return None, None, 0, 0, (
            f"{tag} transition time **not measured**: no rising or falling "
            f"edge from {start} completed a monotonic crossing of both levels"
        )
    parts = []
    if rise_mean is not None:
        parts.append(f"rise {_fmt_s(rise_mean)} (n={len(rises)})")
    if fall_mean is not None:
        parts.append(f"fall {_fmt_s(fall_mean)} (n={len(falls)})")
    clause = f"{tag} transition time: " + ", ".join(parts)
    return rise_mean, fall_mean, len(rises), len(falls), clause


def measure_trace(
    times,
    values,
    spec: MeasureSpec,
    supply_v: float,
    label: str | None = None,
    extra: dict | None = None,
) -> Measurement:
    """Reduce one transient trace to a `Measurement`.

    `supply_v` is this PVT point's own supply, so the comparison threshold
    tracks the swept supply instead of being pinned to the nominal rail --
    at the 1.62 V corner a rail-to-rail clock is measured at 0.81 V, not at
    0.90 V.

    `extra` maps each additional dumped node name to its values (sampled on
    the same `times`); it is only consulted when the manifest carries a
    `measure.ripple` block. Ripple never changes a point's pass/fail: it is
    reported alongside the clock measurement, labelled with whether its
    window was in lock, and gating on it is a decision for whichever
    decision record eventually cites it.
    """
    m = _measure_clock(times, values, spec, supply_v, label)
    if spec.ripple is None:
        return m

    extra = extra or {}
    t_to = spec.tran_stop_s
    t_from = t_to - spec.ripple.window_s
    if spec.lock is None:
        in_lock = None
    else:
        in_lock = bool(m.locked and m.lock_time_s is not None and m.lock_time_s <= t_from)
    results = []
    for node in spec.ripple.nodes:
        series = values if node == spec.node else extra.get(node)
        if series is None:
            raise MeasureError(f"ripple node v({node}) was not in the waveform dump")
        stat = ripple_pp(times, series, t_from, t_to)
        lo, hi, pp = stat if stat is not None else (None, None, None)
        results.append(
            RippleResult(
                node=node, t_from_s=t_from, t_to_s=t_to,
                v_min=lo, v_max=hi, pp=pp, in_lock=in_lock,
            )
        )
    if in_lock is None:
        context = ""
    elif in_lock:
        context = " (in lock)"
    else:
        context = " (**NOT in lock** -- not ripple-in-lock evidence)"
    ripple_note = (
        f"ripple over [{_fmt_s(t_from)}, {_fmt_s(t_to)}]{context}: "
        + "; ".join(r.describe() for r in results)
    )
    return replace(m, ripple=tuple(results), note=f"{m.note}. {ripple_note}")


def _measure_clock(
    times,
    values,
    spec: MeasureSpec,
    supply_v: float,
    label: str | None = None,
) -> Measurement:
    """The clock half of `measure_trace`: oscillation, frequency, duty and
    lock, from the measured node's threshold crossings."""
    threshold = spec.threshold_frac * supply_v
    hysteresis = spec.hysteresis_frac * supply_v
    rising, falling = edge_times(times, values, threshold, hysteresis)
    settle = spec.settle_from_s
    usable = [t for t in rising if t >= settle]

    if len(usable) < spec.min_edges:
        note = (
            f"no oscillation: {len(usable)} rising edge(s) at v({spec.node}) crossed "
            f"{threshold:.3g} V after {_fmt_s(settle)} (fewer than the "
            f"{spec.min_edges} this manifest requires)"
        )
        return Measurement(
            label=label,
            oscillating=False,
            freq_hz=None,
            duty_cycle=None,
            locked=False if spec.lock else None,
            lock_time_s=None,
            final_freq_hz=None,
            note=note,
            passed=not (spec.require_oscillation or spec.require_lock),
        )

    if spec.lock is None:
        f = mean_frequency(usable)
        d = duty_cycle(rising, falling, t_from=settle)
        note = f"f_out {_fmt_hz(f)}, duty {d * 100:.1f}%" if d is not None else (
            f"f_out {_fmt_hz(f)}, duty -"
        )
        # No `lock` block means no lock instant to start the population at, so
        # `settle_from` is the window start -- the same instant the frequency
        # and duty above are taken over. A manifest measuring row 9 itself
        # declares `lock` (the row is stated "in lock"); this branch is for a
        # free-running campaign that wants the cycle-to-cycle spread of an
        # oscillator recorded alongside its frequency.
        jitter_frac, jitter_cycles, jitter_clause = _measure_jitter(
            rising, spec, t_from=settle
        )
        if jitter_clause:
            note += f", {jitter_clause}"
        rise_t, fall_t, n_rise, n_fall, transition_clause = _measure_transition(
            times, values, spec, supply_v, t_from=settle
        )
        if transition_clause:
            note += f", {transition_clause}"
        return Measurement(
            label=label,
            oscillating=True,
            freq_hz=f,
            duty_cycle=d,
            locked=None,
            lock_time_s=None,
            final_freq_hz=f,
            note=note,
            passed=True,
            period_jitter_frac=jitter_frac,
            jitter_cycles=jitter_cycles,
            rise_time_s=rise_t,
            fall_time_s=fall_t,
            n_rise_edges=n_rise,
            n_fall_edges=n_fall,
        )

    locked, t_lock = lock_time(usable, spec.lock)
    tail = usable[-(spec.lock.window_cycles + 1):]
    final_f = mean_frequency(tail)
    if not locked:
        note = (
            f"**no lock** within {_fmt_s(spec.tran_stop_s)}: the sliding-window "
            f"criterion was never satisfied. Final-window mean is "
            f"{_fmt_hz(final_f)} -- that is the frequency the loop happened to be "
            f"running at when the transient ended, NOT a locked output frequency"
        )
        if spec.jitter is not None:
            # Row 9 is stated "in lock". A point that never locked has no
            # post-lock population, so it gets no jitter number at all --
            # the final-window cycles are not silently substituted for one.
            note += (
                ". No period jitter is attributed to it either: row 9's "
                "population is a post-lock one, and this point has none"
            )
        return Measurement(
            label=label,
            oscillating=True,
            freq_hz=None,
            duty_cycle=None,
            locked=False,
            lock_time_s=None,
            final_freq_hz=final_f,
            note=note,
            passed=not spec.require_lock,
        )

    f = mean_frequency(usable, t_from=t_lock)
    d = duty_cycle(rising, falling, t_from=t_lock)
    duty_txt = f"{d * 100:.1f}%" if d is not None else "-"
    note = (
        f"locked at {_fmt_s(t_lock)}; post-lock f_out {_fmt_hz(f)}, duty {duty_txt}"
    )
    # Row 9's population: the consecutive output cycles after `t_lock`, the
    # same instant the post-lock frequency and duty above are taken from.
    # `lock_time` ran on `usable` while this filters `rising`, and the two
    # agree: `t_lock` is an element of `usable`, `usable` is `rising` with
    # everything before `settle` dropped, and so `t_lock >= settle` -- the
    # extra pre-settle edges in `rising` are all below `t_from` and drop out.
    jitter_frac, jitter_cycles, jitter_clause = _measure_jitter(
        rising, spec, t_from=t_lock
    )
    if jitter_clause:
        note += f", {jitter_clause}"
    rise_t, fall_t, n_rise, n_fall, transition_clause = _measure_transition(
        times, values, spec, supply_v, t_from=t_lock
    )
    if transition_clause:
        note += f", {transition_clause}"
    return Measurement(
        label=label,
        oscillating=True,
        freq_hz=f,
        duty_cycle=d,
        locked=True,
        lock_time_s=t_lock,
        final_freq_hz=final_f,
        note=note,
        passed=True,
        period_jitter_frac=jitter_frac,
        jitter_cycles=jitter_cycles,
        rise_time_s=rise_t,
        fall_time_s=fall_t,
        n_rise_edges=n_rise,
        n_fall_edges=n_fall,
    )


def _jitter_population_owed(m: Measurement) -> bool:
    """Should this measurement have produced a period-jitter number?

    Yes for a point that oscillated and (where a lock criterion applies) locked
    -- those are exactly the points row 9 is stated over. A dead point, or one
    that never locked, is already recorded as such by its own note and is not
    additionally failed for having no jitter figure.
    """
    return m.oscillating and m.locked is not False


def _fold_jitter_bound(measurements, spec: MeasureSpec):
    """The row-9 half of `aggregate`. Returns `(passed, reason)`, or `None`
    when this manifest states no gated jitter bound and the fold is a no-op.

    Two distinct failures, reported distinctly, because they mean different
    things to a reader of the record: a point that *missed* a stated bound is
    a design result, while a point that produced *no* jitter number at all is
    a campaign that cannot speak to the row -- and neither may be folded into
    a PASS against a bound the manifest asked to be gated on.
    """
    js = spec.jitter
    if js is None or js.max_frac is None or not js.gate_on_bound:
        return None

    misses, unmeasured = [], []
    for m in measurements:
        if not _jitter_population_owed(m):
            continue
        if m.period_jitter_frac is None:
            unmeasured.append(m)
        elif m.period_jitter_frac > js.max_frac:
            misses.append(m)

    def _tag(m: Measurement) -> str:
        return f"{m.label}: " if m.label else ""

    if misses:
        detail = "; ".join(
            f"{_tag(m)}period jitter {m.period_jitter_frac * 100:.3f}% RMS over "
            f"{m.jitter_cycles} cycles"
            for m in misses[:3]
        )
        return False, (
            f"{len(misses)}/{len(measurements)} measurement(s) miss this "
            f"manifest's period-jitter bound of {js.max_frac * 100:g}% of the "
            f"output period ({detail})"
        )
    if unmeasured:
        detail = "; ".join(
            f"{_tag(m)}{m.jitter_cycles} cycle(s) in the population" for m in unmeasured[:3]
        )
        return False, (
            f"this manifest gates on a period-jitter bound of "
            f"{js.max_frac * 100:g}% of the output period, but "
            f"{len(unmeasured)}/{len(measurements)} measurement(s) produced no "
            f"jitter number -- either fewer than the {js.min_cycles} cycles it "
            f"requires, or a population with no usable mean period; each "
            f"point's own note says which ({detail})"
        )
    return None


def aggregate(measurements, spec: MeasureSpec) -> tuple:
    """Fold one PVT point's measurements into (passed, reason).

    Kept here rather than in `runner` so the pass/fail *policy* -- which is
    what a record's verdict column means -- is unit-testable without a
    simulator, alongside the arithmetic it judges.

    Three folds, in order: any individually-failed measurement dominates; then
    a manifest-stated period-jitter bound (`_fold_jitter_bound`, row 9); then
    the swept-campaign "how many points must oscillate" count.
    """
    if not measurements:
        return False, "no measurements were produced"

    failed = [m for m in measurements if not m.passed]
    if failed:
        detail = "; ".join(
            (f"{m.label}: {m.note}" if m.label else m.note) for m in failed[:3]
        )
        return False, detail

    jitter_verdict = _fold_jitter_bound(measurements, spec)
    if jitter_verdict is not None:
        return jitter_verdict

    oscillating = sum(1 for m in measurements if m.oscillating)
    if oscillating < spec.min_oscillating_points:
        return False, (
            f"only {oscillating}/{len(measurements)} swept points oscillated "
            f"(this manifest requires at least {spec.min_oscillating_points})"
        )

    if len(measurements) == 1 and measurements[0].label is None:
        return True, measurements[0].note
    return True, (
        f"{oscillating}/{len(measurements)} swept points oscillated; "
        + ", ".join(f"{m.label} {_fmt_hz(m.freq_hz)}" for m in measurements)
    )


def format_hz(value: float | None) -> str:
    """Public alias of the internal frequency formatter, for report.py."""
    return _fmt_hz(value)


def format_s(value: float | None) -> str:
    """Public alias of the internal time formatter, for report.py."""
    return _fmt_s(value)
