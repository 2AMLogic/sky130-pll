"""Derive loop-dynamics measurements (crossover, phase margin) from an AC run.

`sim/harness/measure.py` deliberately stops short of loop bandwidth and phase
margin, and says so in its own module docstring: they are **open-loop**
quantities, and extracting them from a closed-loop transient means either
breaking the loop or fitting a step response whose accuracy is dominated by
the fit's assumptions. This module is the "different testbench topology" that
docstring points at -- a linearized open-loop AC analysis -- plus the reducer
that turns its frequency response into the two numbers
`spec/target-spec.md` rows 6 (loop bandwidth) and 7 (phase margin) are owed.

## The linearized open-loop model, stated once

A type-II charge-pump PLL's open-loop transfer function is

    T(s) = (Icp / 2*pi) * Z(s) * (2*pi*Kvco / s) / N
         = (Icp * Kvco / N) * Z(s) / s

where `Z(s)` is the loop filter's transimpedance from charge-pump current to
`VCTRL`, `Icp` the charge-pump current, `Kvco` the VCO gain in Hz/V, and `N`
the feedback divide ratio. Everything except `Z(s)` collapses into a single
scalar `A = Icp * Kvco / N`, which is why this testbench needs no VCO, no
charge pump and no divider in the netlist:

- `Z(s)` is simulated **for real** -- the DUT is `design/loop-filter`'s own
  sky130 R/C network, so every process corner and temperature moves the poles
  and the zero exactly as the silicon models say they do.
- `A` is applied as the **AC magnitude of the injected current source**, so a
  swept set of `(Icp, Kvco, N)` design points costs one `alter` + one `ac` per
  point inside a single ngspice invocation.
- The ideal `1/s` VCO phase integrator is one VCCS into a 1 F capacitor in the
  testbench itself (see `sim/loop-ac/testbench/tb_loop_ac.sch`).

`v(<node>)` is therefore the **dimensionless open-loop gain** `T(j*omega)`:
unity gain is 0 dB, and the sign convention is the usual one (the loop's own
inversion is *not* included, so `T` sits at -180 degrees at low frequency for
this two-integrator loop and phase margin is `180 + arg T` at crossover).

## What this module measures, and what it refuses to claim

- **Crossover (loop bandwidth) `f_c`** -- the frequency where `|T| = 1`,
  interpolated in log-frequency/log-magnitude between the bracketing samples.
- **Phase margin** -- `180 deg + arg T(j*2*pi*f_c)`, from a phase curve
  unwrapped across the sweep so a crossover past a -180 degree wrap is not
  read off the wrong branch.
- **Gain margin** -- the negated gain (in dB) at the first phase crossing of
  -180 degrees *above* `f_c`, reported when one exists.

A sweep with **no** unity-gain crossing reports `no crossover` explicitly and
attributes no bandwidth to the point -- the same discipline
`measure.measure_trace` applies to "no lock" (never report the last simulated
value as if it were the measured one).

Bounds (`phase_margin_floor_deg`, `f_c_ceiling_frac_of_f_ref`) are **reported,
not enforced**, unless a manifest opts in with `gate_on_bounds`. Rows 6 and 7
are DRAFT, not ratified; per `CLAUDE.md` a measurement that misses a DRAFT
target is recorded as a miss, and no harness verdict may be read as
ratifying -- or as relaxing -- a spec row.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .measure import MeasureError, format_hz

# Same completion marker discipline as `measure.py`: ngspice prints no
# "Total analysis time" banner for an analysis driven from a `.control`
# block, so the block echoes its own marker as its last statement.
COMPLETION_MARKER = "sim/harness: analysis complete"

_FREQ_RE = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z]*)\s*$")
_FREQ_SUFFIXES = {
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


def parse_spice_freq(text: str | float | int) -> float:
    """Parse a SPICE frequency literal (`100`, `1k`, `100meg`, `1.5g`).

    Same suffix table (and same `m`-is-milli / `meg`-is-1e6 footgun) as
    `measure.parse_spice_time`, kept separate because a frequency literal is
    a different manifest field with a different failure message.
    """
    if isinstance(text, (int, float)):
        return float(text)
    m = _FREQ_RE.match(text)
    if not m:
        raise MeasureError(f"not a SPICE frequency literal: {text!r}")
    value, suffix = float(m.group(1)), m.group(2).lower()
    if not suffix:
        return value
    if suffix.startswith("meg"):
        return value * _FREQ_SUFFIXES["meg"]
    scale = _FREQ_SUFFIXES.get(suffix[0])
    if scale is None:
        raise MeasureError(f"unknown SPICE frequency suffix in {text!r}")
    return value * scale


@dataclass(frozen=True)
class LoopGainPoint:
    """One `(Icp, Kvco, N)` design point of the swept loop-gain scalar.

    `basis` is the provenance sentence copied into the evidence record, so a
    later decision record can tell which of these numbers came from a block's
    own DESIGN.md, which from a committed `sim/` measurement, and which is a
    hand assumption.
    """

    label: str
    icp_a: float
    kvco_hz_per_v: float
    n_divide: float
    basis: str

    @property
    def scalar(self) -> float:
        """`A = Icp * Kvco / N` -- the AC magnitude injected for this point."""
        return self.icp_a * self.kvco_hz_per_v / self.n_divide

    @property
    def summary(self) -> str:
        return (
            f"Icp={self.icp_a * 1e6:g} uA, Kvco={self.kvco_hz_per_v / 1e6:g} MHz/V, "
            f"N={self.n_divide:g} (A={self.scalar:.4g})"
        )


@dataclass(frozen=True)
class AcSpec:
    """The `ac` block of a `tb.json` manifest, parsed."""

    node: str
    source: str
    dec_points: int
    f_start: str
    f_stop: str
    loop_gain: tuple
    timeout_s: int = 900
    f_ref_hz: float | None = None
    phase_margin_floor_deg: float | None = None
    f_c_ceiling_frac_of_f_ref: float | None = None
    gate_on_bounds: bool = False
    require_crossover: bool = True

    @property
    def f_start_hz(self) -> float:
        return parse_spice_freq(self.f_start)

    @property
    def f_stop_hz(self) -> float:
        return parse_spice_freq(self.f_stop)

    @property
    def f_c_ceiling_hz(self) -> float | None:
        if self.f_ref_hz is None or self.f_c_ceiling_frac_of_f_ref is None:
            return None
        return self.f_ref_hz * self.f_c_ceiling_frac_of_f_ref

    @classmethod
    def from_manifest(cls, manifest: dict):
        block = manifest.get("ac")
        if not block:
            return None
        for required in ("node", "source", "f_start", "f_stop", "loop_gain"):
            if required not in block:
                raise MeasureError(f"manifest `ac` block is missing {required!r}")
        if not block["loop_gain"]:
            raise MeasureError("manifest `ac.loop_gain` list is empty")

        points = []
        for i, raw in enumerate(block["loop_gain"]):
            missing = [k for k in ("label", "icp_a", "kvco_hz_per_v", "n_divide") if k not in raw]
            if missing:
                raise MeasureError(
                    f"manifest `ac.loop_gain[{i}]` is missing {', '.join(missing)}"
                )
            if float(raw["n_divide"]) <= 0:
                raise MeasureError(f"manifest `ac.loop_gain[{i}]` has a non-positive n_divide")
            points.append(
                LoopGainPoint(
                    label=str(raw["label"]),
                    icp_a=float(raw["icp_a"]),
                    kvco_hz_per_v=float(raw["kvco_hz_per_v"]),
                    n_divide=float(raw["n_divide"]),
                    basis=str(raw.get("basis", "(no basis stated in manifest)")),
                )
            )

        spec = cls(
            node=block["node"],
            source=block["source"],
            dec_points=int(block.get("points_per_decade", 40)),
            f_start=str(block["f_start"]),
            f_stop=str(block["f_stop"]),
            loop_gain=tuple(points),
            timeout_s=int(block.get("timeout_s", 900)),
            # An explicit `null` is as valid as an omitted key here: a
            # manifest may say "this campaign states no DRAFT bound" out loud.
            f_ref_hz=(
                float(block["f_ref_hz"]) if block.get("f_ref_hz") is not None else None
            ),
            phase_margin_floor_deg=(
                float(block["phase_margin_floor_deg"])
                if block.get("phase_margin_floor_deg") is not None
                else None
            ),
            f_c_ceiling_frac_of_f_ref=(
                float(block["f_c_ceiling_frac_of_f_ref"])
                if block.get("f_c_ceiling_frac_of_f_ref") is not None
                else None
            ),
            gate_on_bounds=bool(block.get("gate_on_bounds", False)),
            require_crossover=bool(block.get("require_crossover", True)),
        )
        if spec.f_stop_hz <= spec.f_start_hz:
            raise MeasureError(
                f"manifest `ac` block has f_stop ({spec.f_stop}) <= f_start ({spec.f_start})"
            )
        if spec.dec_points < 1:
            raise MeasureError("manifest `ac.points_per_decade` must be >= 1")
        return spec


def waveform_names(spec: AcSpec, prefix: str = "") -> list:
    """Per-run waveform dump filenames, one per swept loop-gain point.

    The `.raw` extension is load-bearing for the same reason it is in
    `measure.waveform_names`: `sim/README.md`'s retention policy keeps
    waveform data out of the committed evidence trail, and the repo's root
    `.gitignore` implements that with a tree-wide `*.raw` rule.
    """
    return [f"{prefix}ac{i:03d}.raw" for i in range(len(spec.loop_gain))]


def build_ac_control_block(spec: AcSpec, prefix: str = "") -> str:
    """Compose the `.control` section for one PVT point's AC sweep set.

    One `alter <source> acmag` + one `ac dec` + one `wrdata` per swept
    loop-gain point, all inside a single ngspice invocation, so the sky130
    model library is parsed once per PVT point rather than once per point of
    the sweep.
    """
    lines = [".control", "set filetype=ascii"]
    lines.append(f"save v({spec.node})")
    names = waveform_names(spec, prefix)
    for i, gain in enumerate(spec.loop_gain):
        lines.append(f"alter @{spec.source.lower()}[acmag] = {gain.scalar:.10g}")
        lines.append(f"ac dec {spec.dec_points} {spec.f_start} {spec.f_stop}")
        lines.append(f"wrdata {names[i]} v({spec.node})")
        # Free this swept point's plot before the next one -- a whole sweep
        # runs inside one invocation, so retained plots would accumulate.
        lines.append("destroy all")
    lines.append(f'echo "{COMPLETION_MARKER}"')
    lines.append(".endc")
    return "\n".join(lines) + "\n"


def parse_ac_wrdata(text: str) -> tuple:
    """Parse an ngspice AC-mode `wrdata` dump into (freqs, reals, imags).

    For a complex vector, `wrdata` writes three whitespace-separated columns
    per row: the x value (frequency), then the vector's real and imaginary
    parts. Rows with fewer than three parseable columns are skipped, so a
    stray banner line in the dump does not abort the reduction.
    """
    freqs, reals, imags = [], [], []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            f, re_, im = float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError:
            continue
        freqs.append(f)
        reals.append(re_)
        imags.append(im)
    if not freqs:
        raise MeasureError("AC waveform dump contained no samples")
    return freqs, reals, imags


def magnitudes(reals, imags) -> list:
    return [math.hypot(r, i) for r, i in zip(reals, imags)]


def unwrapped_phase_deg(reals, imags) -> list:
    """Phase in degrees, unwrapped across the sweep and anchored below zero.

    Two separate jobs, both load-bearing for a phase-margin number:

    1. **Unwrap** -- `atan2` returns a value in (-180, 180], so a phase that
       walks past -180 degrees reappears at +180. Reading a phase margin off
       that branch would report roughly +360 degrees of margin where there is
       none.
    2. **Anchor** -- the whole unwrapped curve is then shifted by a multiple
       of 360 degrees so its first sample lies in (-360, 0]. For this loop
       that puts the low-frequency asymptote at about -180 degrees, which is
       the branch `180 + arg T` is defined against.
    """
    if not reals:
        return []
    phases = [math.degrees(math.atan2(i, r)) for r, i in zip(reals, imags)]
    out = [phases[0]]
    for k in range(1, len(phases)):
        delta = phases[k] - phases[k - 1]
        # Fold the step into (-180, 180] before accumulating it.
        delta -= 360.0 * math.floor((delta + 180.0) / 360.0)
        out.append(out[-1] + delta)
    shift = 360.0 * math.floor(-out[0] / 360.0)
    return [p + shift for p in out]


def _interp_log(f0: float, f1: float, w: float) -> float:
    """Interpolate between two frequencies in log space at fraction `w`."""
    if f0 <= 0 or f1 <= 0:
        return f0 + w * (f1 - f0)
    return 10.0 ** (math.log10(f0) + w * (math.log10(f1) - math.log10(f0)))


def unity_gain_crossings(freqs, mags, phases) -> list:
    """Every downward |T| = 1 crossing, as (frequency, phase) pairs.

    Magnitude is interpolated in log-magnitude vs. log-frequency (a Bode plot
    is straight there, so this is the interpolation that matches the curve's
    own shape); the phase is interpolated linearly on the same fraction.
    Only *downward* crossings are returned -- an upward crossing is the loop
    gain re-entering the unity-gain region, not a candidate crossover.
    """
    out = []
    for k in range(1, len(freqs)):
        m0, m1 = mags[k - 1], mags[k]
        if m0 <= 0 or m1 <= 0:
            continue
        if not (m0 >= 1.0 > m1):
            continue
        l0, l1 = math.log10(m0), math.log10(m1)
        w = 0.0 if l1 == l0 else (0.0 - l0) / (l1 - l0)
        f_c = _interp_log(freqs[k - 1], freqs[k], w)
        phase = phases[k - 1] + w * (phases[k] - phases[k - 1])
        out.append((f_c, phase))
    return out


def phase_crossing_gain_db(freqs, mags, phases, above_hz: float) -> tuple:
    """Gain margin: (frequency, gain in dB) at the first -180 deg crossing.

    Searched only *above* `above_hz` (the crossover), because this loop's
    phase starts at -180 degrees by construction -- the low-frequency
    asymptote of a two-integrator loop -- and that asymptote is not a gain
    margin. Returns (None, None) when the phase never falls through -180
    degrees inside the swept band.
    """
    for k in range(1, len(freqs)):
        if freqs[k] <= above_hz:
            continue
        p0, p1 = phases[k - 1], phases[k]
        if not (p0 >= -180.0 > p1):
            continue
        w = 0.0 if p1 == p0 else (-180.0 - p0) / (p1 - p0)
        f = _interp_log(freqs[k - 1], freqs[k], w)
        m0, m1 = mags[k - 1], mags[k]
        if m0 <= 0 or m1 <= 0:
            return f, None
        log_m = math.log10(m0) + w * (math.log10(m1) - math.log10(m0))
        return f, -20.0 * log_m
    return None, None


@dataclass(frozen=True)
class AcMeasurement:
    """One swept loop-gain point's reduced frequency response."""

    label: str | None
    gain_point: LoopGainPoint | None
    crossed: bool
    crossing_count: int
    crossover_hz: float | None
    phase_at_crossover_deg: float | None
    phase_margin_deg: float | None
    gain_margin_db: float | None
    gain_margin_hz: float | None
    dc_gain_db: float | None
    meets_pm_floor: bool | None
    meets_fc_ceiling: bool | None
    note: str
    passed: bool

    def summary(self) -> str:
        return self.note


def _fmt_deg(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f} deg"


def measure_ac_response(
    freqs,
    reals,
    imags,
    spec: AcSpec,
    gain_point: LoopGainPoint | None = None,
) -> AcMeasurement:
    """Reduce one AC sweep to an `AcMeasurement`."""
    label = gain_point.label if gain_point is not None else None
    mags = magnitudes(reals, imags)
    phases = unwrapped_phase_deg(reals, imags)
    dc_gain_db = 20.0 * math.log10(mags[0]) if mags and mags[0] > 0 else None

    crossings = unity_gain_crossings(freqs, mags, phases)
    if not crossings:
        highest_db = 20.0 * math.log10(max(mags)) if max(mags) > 0 else None
        gain_txt = "-" if highest_db is None else f"{highest_db:.1f} dB"
        note = (
            f"**no crossover**: |T| never falls through unity between "
            f"{format_hz(spec.f_start_hz)} and {format_hz(spec.f_stop_hz)} "
            f"(peak |T| in band {gain_txt}). No loop bandwidth or phase margin "
            f"is attributed to this point"
        )
        return AcMeasurement(
            label=label,
            gain_point=gain_point,
            crossed=False,
            crossing_count=0,
            crossover_hz=None,
            phase_at_crossover_deg=None,
            phase_margin_deg=None,
            gain_margin_db=None,
            gain_margin_hz=None,
            dc_gain_db=dc_gain_db,
            meets_pm_floor=None,
            meets_fc_ceiling=None,
            note=note,
            passed=not spec.require_crossover,
        )

    # The highest-frequency downward crossing is the loop's actual crossover:
    # a conditionally-stable response can dip through unity and come back, and
    # the margin that matters is the one at the last exit.
    f_c, phase_c = crossings[-1]
    pm = 180.0 + phase_c
    gm_hz, gm_db = phase_crossing_gain_db(freqs, mags, phases, above_hz=f_c)

    meets_pm = None if spec.phase_margin_floor_deg is None else pm >= spec.phase_margin_floor_deg
    ceiling = spec.f_c_ceiling_hz
    meets_fc = None if ceiling is None else f_c < ceiling

    parts = [f"f_c {format_hz(f_c)}, phase margin {pm:.1f} deg"]
    if gm_db is not None:
        parts.append(f"gain margin {gm_db:.1f} dB at {format_hz(gm_hz)}")
    if len(crossings) > 1:
        parts.append(
            f"**{len(crossings)} unity-gain crossings** -- reported values are "
            "taken at the highest-frequency one"
        )
    misses = []
    if meets_pm is False:
        misses.append(
            f"below the DRAFT row-7 floor of {spec.phase_margin_floor_deg:g} deg"
        )
    if meets_fc is False:
        misses.append(f"above the DRAFT row-6 ceiling of {format_hz(ceiling)}")
    if misses:
        parts.append("**misses** " + " and ".join(misses))

    passed = True
    if spec.gate_on_bounds and (meets_pm is False or meets_fc is False):
        passed = False

    return AcMeasurement(
        label=label,
        gain_point=gain_point,
        crossed=True,
        crossing_count=len(crossings),
        crossover_hz=f_c,
        phase_at_crossover_deg=phase_c,
        phase_margin_deg=pm,
        gain_margin_db=gm_db,
        gain_margin_hz=gm_hz,
        dc_gain_db=dc_gain_db,
        meets_pm_floor=meets_pm,
        meets_fc_ceiling=meets_fc,
        note="; ".join(parts),
        passed=passed,
    )


def aggregate(measurements, spec: AcSpec) -> tuple:
    """Fold one PVT point's AC measurements into (passed, reason).

    Same split of concerns as `measure.aggregate`: the pass/fail *policy* a
    record's verdict column means lives next to the arithmetic it judges, and
    is unit-testable without a simulator.
    """
    if not measurements:
        return False, "no AC measurements were produced"

    failed = [m for m in measurements if not m.passed]
    if failed:
        detail = "; ".join(
            (f"{m.label}: {m.note}" if m.label else m.note) for m in failed[:3]
        )
        return False, detail

    if len(measurements) == 1 and measurements[0].label is None:
        return True, measurements[0].note

    return True, ", ".join(
        f"{m.label}: f_c {format_hz(m.crossover_hz)} / PM {_fmt_deg(m.phase_margin_deg)}"
        for m in measurements
    )


def format_deg(value: float | None) -> str:
    """Public alias of the internal degree formatter, for report.py."""
    return _fmt_deg(value)
