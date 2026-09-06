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
   `duty_cycle` / `lock_time` -> `measure_trace`, which folds those into one
   `Measurement` per (point, swept value).

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
from dataclasses import dataclass, field
from statistics import fmean

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


def parse_spice_time(text: str | float | int) -> float:
    """Parse a SPICE time literal (`50p`, `200n`, `40u`, `2ns`, `1meg`).

    SPICE's classic footgun is honored: `m` is milli and `meg` is 1e6. A
    trailing unit letter after the suffix (`ns`, `us`) is ignored, as ngspice
    itself ignores it.
    """
    if isinstance(text, (int, float)):
        return float(text)
    m = _TIME_RE.match(text)
    if not m:
        raise MeasureError(f"not a SPICE time literal: {text!r}")
    value, suffix = float(m.group(1)), m.group(2).lower()
    if not suffix:
        return value
    if suffix.startswith("meg"):
        return value * _SUFFIXES["meg"]
    scale = _SUFFIXES.get(suffix[0])
    if scale is None:
        raise MeasureError(f"unknown SPICE time suffix in {text!r}")
    return value * scale


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

    @property
    def tran_stop_s(self) -> float:
        return parse_spice_time(self.tran_stop)

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
            require_lock=bool(block.get("require_lock", False)),
            require_oscillation=bool(block.get("require_oscillation", True)),
            min_oscillating_points=int(block.get("min_oscillating_points", 0)),
            extra_nodes=tuple(block.get("extra_nodes", ())),
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
    nodes = (spec.node,) + tuple(spec.extra_nodes)
    vectors = " ".join(f"v({n})" for n in nodes)
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
        lines.append(f"linearize v({spec.node})")
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


def measure_trace(
    times,
    values,
    spec: MeasureSpec,
    supply_v: float,
    label: str | None = None,
) -> Measurement:
    """Reduce one transient trace to a `Measurement`.

    `supply_v` is this PVT point's own supply, so the comparison threshold
    tracks the swept supply instead of being pinned to the nominal rail --
    at the 1.62 V corner a rail-to-rail clock is measured at 0.81 V, not at
    0.90 V.
    """
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
    )


def aggregate(measurements, spec: MeasureSpec) -> tuple:
    """Fold one PVT point's measurements into (passed, reason).

    Kept here rather than in `runner` so the pass/fail *policy* -- which is
    what a record's verdict column means -- is unit-testable without a
    simulator, alongside the arithmetic it judges.
    """
    if not measurements:
        return False, "no measurements were produced"

    failed = [m for m in measurements if not m.passed]
    if failed:
        detail = "; ".join(
            (f"{m.label}: {m.note}" if m.label else m.note) for m in failed[:3]
        )
        return False, detail

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
