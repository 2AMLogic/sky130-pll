"""Signed charge-pump current/charge analysis (the `cp` manifest block).

This is the pure analysis layer for the isolated PFD/charge-pump
characterization of issue #247 (implemented by issue #248): manifest parser,
deterministic ngspice control generation, dump parsing and the reducers.
It does **not** dispatch simulations, render records or run a campaign --
those are separate children (#249, #250). Nothing here is physical evidence;
it establishes reducer behavior on synthetic fixtures.

## Measurement contract (restated from #247's 2026-10-09 Revision)

The DUT is the unchanged `pfd_cp` block, ports `VDD GND REF DIV CP`. `CP` is
held at `VCTRL` by an ideal voltage clamp, so the whole PFD/CP is exercised
with no VCO and no loop filter. REF and DIV are equal-frequency square waves
(0 to VDD). **Positive phase offset means DIV rises later than REF.** Every
stimulus, sweep, window and numerical setting is owned by the manifest.

### Units and polarity

- Time `s`, current `A`, charge `C` (current integrated over seconds), slope
  `C/s` (numerically equal to amperes), voltage `V`.
- The clamp is oriented from `CP` (positive terminal) to ground. ngspice
  reports the branch current of a voltage source as positive when it flows
  into the positive terminal and through the source, so **positive clamp
  current means charge delivered by the pump into CP** (an UP pulse), and a DN
  pulse gives negative clamp current. The control generator dumps
  `i(<clamp_source>)` unmodified; the sign is never flipped in the reducer, so
  a source wired the other way round inverts every result (see the
  current-inversion test).
- `Qnet = integral(Iclamp dt)`, `Qplus = integral(max(Iclamp, 0) dt)`,
  `Qminus = -integral(min(Iclamp, 0) dt)`, so `Qnet = Qplus - Qminus`.
  Piecewise-linear zero crossings inside a segment are split exactly.

### Cycle windows

A REF rising edge is the 50% crossing: the generated PULSE starts
`rise/2` before the nominal edge time. REF edge `k` is at
`first_edge + k*T`. Each sweep coordinate settles for `settle_periods`
periods, then integrates `integrate_periods` complete periods between
consecutive REF rising edges, starting at `first_edge + settle*T`. Window
boundaries are interpolated linearly between the native timestamps; integration
is trapezoidal on the native (possibly irregular) timestamps. A window that
does not lie inside the dump is an error, never silently truncated.
Per-cycle charges, their mean and sample standard deviation are retained. A
`settled` flag compares the last and first cycle `Qnet` against a provisional
fraction (`settle_tolerance`) of the mean charge throughput; an unsettled
point is *recorded as such* -- the remedy is a new record with a longer
manifest window, not an edit.

### Asymmetry and its limitation

`(Qplus - Qminus) / (Qplus + Qminus)` (from the means) is reported for every
coordinate and is meaningful as the charge asymmetry at zero offset. An empty
denominator is *unavailable*, never "perfect matching". This is a
**net-output** quantity: simultaneously conducting opposing branch currents
cancel in the clamp current and cannot be separated by it.

### Directional plateaus, slope, compliance

- Plateau current comes from the `+plateau_offset` (UP) and `-plateau_offset`
  (DN) cases. Observed gate voltages (`up_gate`/`dn_gate`, each with a stated
  active level, thresholded at VDD/2) select the *exclusive* intervals (one
  gate active, the other not). Samples in the middle half of each exclusive
  pulse (interpolated bounds) are averaged; pulses truncated by the dump ends
  or starting outside the integration window are ignored. No exclusive pulse
  gives an unavailable plateau with a reason. UP is expected positive, DN
  negative; signed values and magnitudes are both kept, plus `sign_ok`.
- Minimum UP/DN active pulse widths are reported per coordinate.
- Phase slope `dQnet/doffset` (C/s) is the central difference over the
  `+/- slope_offset` pair at each VCTRL; no inference of a dead-zone limit is
  made -- the raw `Qnet`-versus-offset curve is the deliverable.
- The descriptive compliance window, per direction, is the contiguous run of
  *sampled* VCTRL fractions containing 0.5 where the plateau has the expected
  sign and its magnitude is within `compliance_tolerance` (provisional 10%,
  methodology only) of the midrail magnitude. Boundaries are sampled points;
  nothing is interpolated. Invalid midrail (not sampled, unavailable, wrong
  sign, zero) makes it unavailable. This is not a spec pass/fail.

### Operating point and resolution diagnostic

The `op` analysis (REF = DIV = 0, clamp at midrail) dumps each manifest-named
vector to its own file, separate from transient dumps. The optional
`diagnostic` block re-runs selected coordinates with finer dump/internal
steps; `compare_resolution` publishes the change in `Qnet` and minimum pulse
widths and refuses to call a material change or a sign change converged.
The `material_fraction` threshold is a diagnostic, not a design bound.
"""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass, field

from .measure import MeasureError, parse_spice_time, parse_wrdata_columns

COMPLETION_MARKER = "sim/harness: analysis complete"

_TINY = 1e-30  # A*s; below this a charge denominator counts as empty.
_MID_FRAC_TOL = 1e-9
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.$]*$")
_EXPR_RE = re.compile(r"^(?:[vi]\([A-Za-z0-9_.$]+\)|@[A-Za-z0-9_.$]+\[[A-Za-z0-9_]+\])$")

_ALLOWED_KEYS = frozenset(
    {
        "clamp_source", "ref_source", "div_source", "up_gate", "dn_gate",
        "frequency_hz", "duty", "rise_s", "fall_s", "first_edge_s",
        "vctrl_fractions", "phase_offsets_s", "settle_periods",
        "integrate_periods", "dump_step_s", "max_step_s", "timeout_s",
        "plateau_offset_s", "slope_offset_s", "compliance_tolerance",
        "settle_tolerance", "op", "diagnostic",
    }
)
_REQUIRED_KEYS = (
    "clamp_source", "ref_source", "div_source", "up_gate", "dn_gate",
    "frequency_hz", "duty", "rise_s", "fall_s", "first_edge_s",
    "vctrl_fractions", "phase_offsets_s", "settle_periods",
    "integrate_periods", "dump_step_s", "max_step_s",
)


class CpError(MeasureError):
    """A malformed `cp` block, or an unusable charge-pump dump."""


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GateSpec:
    """A PFD gate node observed to decide which branch is conducting."""

    node: str
    active_high: bool


@dataclass(frozen=True)
class OpVector:
    label: str
    expr: str  # ngspice vector, e.g. `v(x1.nb)` or `@r.x1.rbias[i]`


@dataclass(frozen=True)
class DiagnosticSpec:
    """Finer-grid nominal-point resolution check."""

    dump_step_s: float
    max_step_s: float
    vctrl_fraction: float
    phase_offsets_s: tuple
    material_fraction: float = 0.05


@dataclass(frozen=True)
class CpSpec:
    """The `cp` block of a `tb.json` manifest, parsed and validated."""

    clamp_source: str
    ref_source: str
    div_source: str
    up_gate: GateSpec
    dn_gate: GateSpec
    frequency_hz: float
    duty: float
    rise_s: float
    fall_s: float
    first_edge_s: float
    vctrl_fractions: tuple
    phase_offsets_s: tuple
    settle_periods: int
    integrate_periods: int
    dump_step_s: float
    max_step_s: float
    timeout_s: int = 900
    plateau_offset_s: float = 25e-9
    slope_offset_s: float = 0.1e-9
    compliance_tolerance: float = 0.1
    settle_tolerance: float = 0.05
    op_vectors: tuple = ()
    diagnostic: DiagnosticSpec | None = None

    @property
    def period_s(self) -> float:
        return 1.0 / self.frequency_hz

    @property
    def clamp_vector(self) -> str:
        return f"i({self.clamp_source.lower()})"

    def ref_edge(self, k: float) -> float:
        """Nominal REF rising-edge (50% crossing) time of edge `k`."""
        return self.first_edge_s + k * self.period_s

    @property
    def window_start_s(self) -> float:
        return self.ref_edge(self.settle_periods)

    @property
    def window_end_s(self) -> float:
        return self.ref_edge(self.settle_periods + self.integrate_periods)

    @property
    def stop_s(self) -> float:
        """Transient stop: window end plus one period of trailing data."""
        return self.window_end_s + self.period_s

    def cycle_windows(self) -> list:
        return [
            (self.ref_edge(self.settle_periods + k), self.ref_edge(self.settle_periods + k + 1))
            for k in range(self.integrate_periods)
        ]

    def midrail_index(self) -> int | None:
        for i, f in enumerate(self.vctrl_fractions):
            if abs(f - 0.5) < _MID_FRAC_TOL:
                return i
        return None

    def offset_index(self, offset_s: float) -> int | None:
        for j, o in enumerate(self.phase_offsets_s):
            if abs(o - offset_s) <= 1e-15:  # 1 fs: offsets are ps-ns scale
                return j
        return None

    @classmethod
    def from_manifest(cls, manifest: dict):
        """Parse the `cp` block; `None` when the manifest has none.

        A manifest declares one analysis mode: a `cp` block combined with a
        `measure` or `ac` block is rejected here.
        """
        block = manifest.get("cp")
        if not block:
            return None
        others = [k for k in ("measure", "ac") if manifest.get(k)]
        if others:
            raise CpError(
                "manifest declares `cp` together with " + ", ".join(f"`{k}`" for k in others)
                + "; a manifest declares exactly one analysis block"
            )
        if not isinstance(block, dict):
            raise CpError("manifest `cp` block must be an object")
        unknown = sorted(set(block) - _ALLOWED_KEYS)
        if unknown:
            raise CpError(f"manifest `cp` block has unknown key(s): {', '.join(unknown)}")
        for key in _REQUIRED_KEYS:
            if key not in block:
                raise CpError(f"manifest `cp` block is missing {key!r}")

        def name(key):
            v = block[key]
            if not isinstance(v, str) or not _NAME_RE.match(v):
                raise CpError(f"manifest `cp.{key}` is not a valid netlist name: {v!r}")
            return v

        def gate(key):
            g = block[key]
            if not isinstance(g, dict) or "node" not in g or "active" not in g:
                raise CpError(f"manifest `cp.{key}` needs `node` and `active` (high|low)")
            node = g["node"]
            if not isinstance(node, str) or not _NAME_RE.match(node):
                raise CpError(f"manifest `cp.{key}.node` is not a valid node name: {node!r}")
            if g["active"] not in ("high", "low"):
                raise CpError(f"manifest `cp.{key}.active` must be 'high' or 'low'")
            return GateSpec(node=node, active_high=g["active"] == "high")

        def num(key, value, *, positive=True):
            if isinstance(value, bool):
                raise CpError(f"manifest `cp.{key}` must be a number or SPICE literal")
            try:
                x = parse_spice_time(value)
            except (MeasureError, TypeError) as exc:
                raise CpError(f"manifest `cp.{key}`: {exc}") from exc
            if not math.isfinite(x):
                raise CpError(f"manifest `cp.{key}` is not finite")
            if positive and x <= 0:
                raise CpError(f"manifest `cp.{key}` must be > 0")
            return x

        def count(key, minimum):
            v = block[key]
            if isinstance(v, bool) or not isinstance(v, int) or v < minimum:
                raise CpError(f"manifest `cp.{key}` must be an integer >= {minimum}")
            return v

        def listing(key, value, *, positive):
            if not isinstance(value, (list, tuple)) or not value:
                raise CpError(f"manifest `cp.{key}` must be a non-empty list")
            return tuple(num(f"{key}[{i}]", v, positive=positive) for i, v in enumerate(value))

        freq = num("frequency_hz", block["frequency_hz"])
        period = 1.0 / freq
        duty = num("duty", block["duty"])
        if not 0.0 < duty < 1.0:
            raise CpError("manifest `cp.duty` must be in (0, 1)")
        rise, fall = num("rise_s", block["rise_s"]), num("fall_s", block["fall_s"])
        if (rise + fall) / 2.0 >= min(duty, 1.0 - duty) * period:
            raise CpError("manifest `cp` rise/fall times are too long for the period and duty")
        first_edge = num("first_edge_s", block["first_edge_s"])

        fracs = listing("vctrl_fractions", block["vctrl_fractions"], positive=False)
        if any(not 0.0 < f < 1.0 for f in fracs):
            raise CpError("manifest `cp.vctrl_fractions` entries must lie in (0, 1)")
        if any(b <= a for a, b in zip(fracs, fracs[1:])):
            raise CpError("manifest `cp.vctrl_fractions` must be strictly increasing")
        offsets = listing("phase_offsets_s", block["phase_offsets_s"], positive=False)
        if len(set(offsets)) != len(offsets):
            raise CpError("manifest `cp.phase_offsets_s` has duplicate entries")
        if any(abs(o) >= period / 2 for o in offsets):
            raise CpError("manifest `cp.phase_offsets_s` entries must be within half a period")
        if first_edge <= max(0.0, -min(offsets)) + rise:
            raise CpError(
                "manifest `cp.first_edge_s` leaves no room for the earliest DIV edge"
            )

        dump_step = num("dump_step_s", block["dump_step_s"])
        max_step = num("max_step_s", block["max_step_s"])
        tol_c = num("compliance_tolerance", block.get("compliance_tolerance", 0.1))
        tol_s = num("settle_tolerance", block.get("settle_tolerance", 0.05))
        if tol_c >= 1.0:
            raise CpError("manifest `cp.compliance_tolerance` must be < 1")

        op_vectors = []
        op = block.get("op")
        if op is not None:
            if not isinstance(op, dict) or set(op) - {"vectors"} or not op.get("vectors"):
                raise CpError("manifest `cp.op` must be {\"vectors\": [{label, expr}, ...]}")
            labels = set()
            for i, raw in enumerate(op["vectors"]):
                if (
                    not isinstance(raw, dict)
                    or not isinstance(raw.get("label"), str)
                    or not isinstance(raw.get("expr"), str)
                ):
                    raise CpError(f"manifest `cp.op.vectors[{i}]` needs string `label` and `expr`")
                if not _EXPR_RE.match(raw["expr"]):
                    raise CpError(
                        f"manifest `cp.op.vectors[{i}].expr` is not a plain ngspice vector: "
                        f"{raw['expr']!r}"
                    )
                if raw["label"] in labels or not raw["label"].strip():
                    raise CpError(f"manifest `cp.op.vectors[{i}].label` is empty or duplicated")
                labels.add(raw["label"])
                op_vectors.append(OpVector(label=raw["label"], expr=raw["expr"]))

        spec = cls(
            clamp_source=name("clamp_source"),
            ref_source=name("ref_source"),
            div_source=name("div_source"),
            up_gate=gate("up_gate"),
            dn_gate=gate("dn_gate"),
            frequency_hz=freq,
            duty=duty,
            rise_s=rise,
            fall_s=fall,
            first_edge_s=first_edge,
            vctrl_fractions=fracs,
            phase_offsets_s=offsets,
            settle_periods=count("settle_periods", 0),
            integrate_periods=count("integrate_periods", 1),
            dump_step_s=dump_step,
            max_step_s=max_step,
            timeout_s=int(block.get("timeout_s", 900)),
            plateau_offset_s=num("plateau_offset_s", block.get("plateau_offset_s", 25e-9)),
            slope_offset_s=num("slope_offset_s", block.get("slope_offset_s", 0.1e-9)),
            compliance_tolerance=tol_c,
            settle_tolerance=tol_s,
            op_vectors=tuple(op_vectors),
        )
        if spec.dump_step_s > spec.period_s / 20 or spec.max_step_s > spec.period_s / 20:
            raise CpError("manifest `cp` step sizes must be at most period/20")
        for off, what in (
            (spec.plateau_offset_s, "plateau_offset_s"),
            (-spec.plateau_offset_s, "-plateau_offset_s"),
            (spec.slope_offset_s, "slope_offset_s"),
            (-spec.slope_offset_s, "-slope_offset_s"),
        ):
            if spec.offset_index(off) is None:
                raise CpError(f"manifest `cp.phase_offsets_s` does not sample {what}")

        diag = block.get("diagnostic")
        if diag is not None:
            if not isinstance(diag, dict):
                raise CpError("manifest `cp.diagnostic` must be an object")
            bad = sorted(
                set(diag)
                - {"dump_step_s", "max_step_s", "vctrl_fraction", "phase_offsets_s", "material_fraction"}
            )
            if bad:
                raise CpError(f"manifest `cp.diagnostic` has unknown key(s): {', '.join(bad)}")
            for k in ("dump_step_s", "max_step_s", "vctrl_fraction", "phase_offsets_s"):
                if k not in diag:
                    raise CpError(f"manifest `cp.diagnostic` is missing {k!r}")
            d_dump = num("diagnostic.dump_step_s", diag["dump_step_s"])
            d_max = num("diagnostic.max_step_s", diag["max_step_s"])
            if d_dump >= spec.dump_step_s or d_max >= spec.max_step_s:
                raise CpError("manifest `cp.diagnostic` steps must be finer than the main grid")
            d_frac = num("diagnostic.vctrl_fraction", diag["vctrl_fraction"])
            d_offs = listing("diagnostic.phase_offsets_s", diag["phase_offsets_s"], positive=False)
            material = num("diagnostic.material_fraction", diag.get("material_fraction", 0.05))
            diagnostic = DiagnosticSpec(
                dump_step_s=d_dump, max_step_s=d_max, vctrl_fraction=d_frac,
                phase_offsets_s=d_offs, material_fraction=material,
            )
            spec = _replace(spec, diagnostic=diagnostic)
            if spec.diagnostic_vctrl_index() is None:
                raise CpError("manifest `cp.diagnostic.vctrl_fraction` is not in vctrl_fractions")
            if any(spec.offset_index(o) is None for o in d_offs):
                raise CpError("manifest `cp.diagnostic.phase_offsets_s` is not a subset of the sweep")
        return spec

    def diagnostic_vctrl_index(self) -> int | None:
        if self.diagnostic is None:
            return None
        for i, f in enumerate(self.vctrl_fractions):
            if abs(f - self.diagnostic.vctrl_fraction) < _MID_FRAC_TOL:
                return i
        return None

    def diagnostic_coordinates(self) -> list:
        """(vctrl_index, phase_index) pairs of the finer-grid diagnostic."""
        if self.diagnostic is None:
            return []
        i = self.diagnostic_vctrl_index()
        return [(i, self.offset_index(o)) for o in self.diagnostic.phase_offsets_s]


def _replace(spec: CpSpec, **kw) -> CpSpec:
    import dataclasses

    return dataclasses.replace(spec, **kw)


# --------------------------------------------------------------------------
# Dump naming and ngspice control generation
# --------------------------------------------------------------------------


def op_dump_name(prefix: str = "") -> str:
    return f"{prefix}cp_op.raw"


def sweep_dump_name(vi: int, pj: int, prefix: str = "", *, diagnostic: bool = False) -> str:
    """Per-coordinate dump filename (`.raw`: kept out of committed evidence)."""
    return f"{prefix}{'cpdiag' if diagnostic else 'cp'}_v{vi:02d}_p{pj:02d}.raw"


def waveform_names(spec: CpSpec, prefix: str = "", *, include_diagnostic: bool = True) -> list:
    """Every dump the control block writes, in execution order."""
    names = []
    if spec.op_vectors:
        names.append(op_dump_name(prefix))
    for vi in range(len(spec.vctrl_fractions)):
        for pj in range(len(spec.phase_offsets_s)):
            names.append(sweep_dump_name(vi, pj, prefix))
    if include_diagnostic:
        names += [sweep_dump_name(vi, pj, prefix, diagnostic=True) for vi, pj in spec.diagnostic_coordinates()]
    return names


def _pulse_card(spec: CpSpec, vdd: float, delay_s: float) -> str:
    # PULSE width is chosen so the 50%-to-50% high time is duty*T.
    width = spec.duty * spec.period_s - (spec.rise_s + spec.fall_s) / 2.0
    td = delay_s - spec.rise_s / 2.0
    return (
        f"pulse = [ 0 {vdd:.10g} {td:.10g} {spec.rise_s:.10g} {spec.fall_s:.10g} "
        f"{width:.10g} {spec.period_s:.10g} ]"
    )


def _tran_lines(spec, vdd, vi, pj, dump, step, max_step, vectors) -> list:
    frac = spec.vctrl_fractions[vi]
    off = spec.phase_offsets_s[pj]
    return [
        f"alter {spec.clamp_source} {frac * vdd:.10g}",
        f"alter {spec.ref_source} {_pulse_card(spec, vdd, spec.first_edge_s)}",
        f"alter {spec.div_source} {_pulse_card(spec, vdd, spec.first_edge_s + off)}",
        f"tran {step:.10g} {spec.stop_s:.10g} 0 {max_step:.10g}",
        f"linearize {vectors}",
        f"wrdata {dump} {vectors}",
        "destroy all",
    ]


def build_cp_control_block(
    spec: CpSpec, vdd: float, prefix: str = "", *, include_diagnostic: bool = True
) -> str:
    """Compose the `.control` section for one PVT point (given its VDD).

    Order: the operating point (REF = DIV = 0 via flat pulses, clamp at
    midrail) with its own dump, then one transient per VCTRL x phase
    coordinate, then the optional finer-grid diagnostic transients. All run
    in one ngspice invocation so the model library is parsed once per point.
    """
    if not (isinstance(vdd, (int, float)) and math.isfinite(vdd) and vdd > 0):
        raise CpError(f"vdd must be a positive finite number, got {vdd!r}")
    tran_vectors = " ".join(
        [spec.clamp_vector, f"v({spec.up_gate.node})", f"v({spec.dn_gate.node})"]
    )
    lines = [".control", "set filetype=ascii", "set wr_singlescale"]
    saves = [spec.clamp_vector, f"v({spec.up_gate.node})", f"v({spec.dn_gate.node})"]
    saves += [v.expr for v in spec.op_vectors if v.expr not in saves]
    lines.append("save " + " ".join(saves))
    if spec.op_vectors:
        mid = spec.midrail_index()
        if mid is None:
            raise CpError("operating point needs 0.5 in cp.vctrl_fractions")
        flat = (
            f"pulse = [ 0 0 0 {spec.rise_s:.10g} {spec.fall_s:.10g} "
            f"{spec.period_s / 2:.10g} {spec.period_s:.10g} ]"
        )
        lines += [
            f"alter {spec.clamp_source} {0.5 * vdd:.10g}",
            f"alter {spec.ref_source} {flat}",
            f"alter {spec.div_source} {flat}",
            "op",
            "wrdata " + op_dump_name(prefix) + " " + " ".join(v.expr for v in spec.op_vectors),
            "destroy all",
        ]
    for vi in range(len(spec.vctrl_fractions)):
        for pj in range(len(spec.phase_offsets_s)):
            lines += _tran_lines(
                spec, vdd, vi, pj, sweep_dump_name(vi, pj, prefix),
                spec.dump_step_s, spec.max_step_s, tran_vectors,
            )
    if include_diagnostic and spec.diagnostic is not None:
        for vi, pj in spec.diagnostic_coordinates():
            lines += _tran_lines(
                spec, vdd, vi, pj, sweep_dump_name(vi, pj, prefix, diagnostic=True),
                spec.diagnostic.dump_step_s, spec.diagnostic.max_step_s, tran_vectors,
            )
    lines.append(f'echo "{COMPLETION_MARKER}"')
    lines.append(".endc")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Dump parsing
# --------------------------------------------------------------------------


def _check_series(times, columns) -> None:
    if len(times) < 2:
        raise CpError(f"dump is too short ({len(times)} sample(s)); need at least 2")
    for series in (times, *columns):
        if not all(math.isfinite(x) for x in series):
            raise CpError("dump contains a nonfinite value")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise CpError("dump timestamps are not strictly increasing")


def parse_cp_tran(text: str) -> tuple:
    """Parse a transient dump `t i(clamp) v(up) v(dn)` -> (t, i, v_up, v_dn)."""
    try:
        times, cols = parse_wrdata_columns(text, 3)
    except MeasureError as exc:
        raise CpError(str(exc)) from exc
    _check_series(times, cols)
    return times, cols[0], cols[1], cols[2]


def parse_cp_op(text: str, n_vectors: int) -> list:
    """Parse the OP dump (one row; the scale column is ignored) -> values."""
    try:
        _, cols = parse_wrdata_columns(text, n_vectors)
    except MeasureError as exc:
        raise CpError(str(exc)) from exc
    if len(cols[0]) != 1:
        raise CpError(f"operating-point dump has {len(cols[0])} rows; expected exactly 1")
    values = [c[0] for c in cols]
    if not all(math.isfinite(v) for v in values):
        raise CpError("operating-point dump contains a nonfinite value")
    return values


# --------------------------------------------------------------------------
# Pure numerics
# --------------------------------------------------------------------------


def _interp(times, values, t: float) -> float:
    if t < times[0] or t > times[-1]:
        raise CpError(f"time {t:g} s lies outside the dump [{times[0]:g}, {times[-1]:g}] s")
    i = bisect.bisect_right(times, t)
    if i >= len(times):
        return values[-1]
    if i == 0:
        return values[0]
    t0, t1 = times[i - 1], times[i]
    return values[i - 1] + (values[i] - values[i - 1]) * (t - t0) / (t1 - t0)


def _segment_integral(t0, v0, t1, v1, part: str) -> float:
    if part == "neg":
        v0, v1 = -v0, -v1
    if part == "net":
        return 0.5 * (v0 + v1) * (t1 - t0)
    # positive part of a linear segment (exact, splitting at the zero crossing)
    if v0 >= 0 and v1 >= 0:
        return 0.5 * (v0 + v1) * (t1 - t0)
    if v0 <= 0 and v1 <= 0:
        return 0.0
    tz = t0 + (0.0 - v0) / (v1 - v0) * (t1 - t0)
    if v0 > 0:
        return 0.5 * v0 * (tz - t0)
    return 0.5 * v1 * (t1 - tz)


def integrate(times, values, t0: float, t1: float, part: str = "net") -> float:
    """Trapezoidal integral over `[t0, t1]` on native timestamps.

    `part` is `net` (integral of v), `pos` (integral of max(v, 0)) or `neg`
    (integral of max(-v, 0), a nonnegative number). Boundaries are linearly
    interpolated; a window outside the dump raises rather than truncating.
    """
    if part not in ("net", "pos", "neg"):
        raise CpError(f"unknown integration part {part!r}")
    if not t1 > t0:
        raise CpError(f"empty or reversed window [{t0:g}, {t1:g}]")
    if len(times) != len(values):
        raise CpError("time and value series differ in length")
    if len(times) < 2:
        raise CpError("series too short to integrate")
    if t0 < times[0] or t1 > times[-1]:
        raise CpError(
            f"window [{t0:g}, {t1:g}] s exceeds the dump [{times[0]:g}, {times[-1]:g}] s"
        )
    pts = [(t0, _interp(times, values, t0))]
    lo, hi = bisect.bisect_right(times, t0), bisect.bisect_left(times, t1)
    pts += [(times[k], values[k]) for k in range(lo, hi)]
    pts.append((t1, _interp(times, values, t1)))
    total = 0.0
    for (ta, va), (tb, vb) in zip(pts, pts[1:]):
        if tb > ta:
            total += _segment_integral(ta, va, tb, vb, part)
    return total


def _mean_std(xs) -> tuple:
    n = len(xs)
    mean = math.fsum(xs) / n
    if n < 2:
        return mean, 0.0
    return mean, math.sqrt(math.fsum((x - mean) ** 2 for x in xs) / (n - 1))


def _crossings(times, values, thr) -> list:
    out = []
    for k in range(len(times) - 1):
        a, b = values[k] >= thr, values[k + 1] >= thr
        if a != b:
            v0, v1 = values[k], values[k + 1]
            out.append(times[k] + (thr - v0) / (v1 - v0) * (times[k + 1] - times[k]))
    return out


def _is_active(gate: GateSpec, v: float, thr: float) -> bool:
    return (v >= thr) if gate.active_high else (v < thr)


def active_intervals(times, up, dn, spec: CpSpec, vdd: float) -> list:
    """Constant-state intervals: list of (a, b, up_active, dn_active).

    State changes only at interpolated threshold (VDD/2) crossings of either
    gate, so each sub-interval is classified once at its midpoint.
    """
    thr = 0.5 * vdd
    cuts = sorted(set([times[0], times[-1]] + _crossings(times, up, thr) + _crossings(times, dn, thr)))
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if b <= a:
            continue
        mid = 0.5 * (a + b)
        out.append(
            (a, b, _is_active(spec.up_gate, _interp(times, up, mid), thr),
             _is_active(spec.dn_gate, _interp(times, dn, mid), thr))
        )
    return out


def _runs(intervals, predicate) -> list:
    """Merge adjacent intervals satisfying `predicate` -> [(a, b)]."""
    runs = []
    for a, b, u, d in intervals:
        if not predicate(u, d):
            continue
        if runs and abs(runs[-1][1] - a) <= 0.0:
            runs[-1] = (runs[-1][0], b)
        else:
            runs.append((a, b))
    return runs


def _pulses_in_window(times, runs, w0, w1) -> list:
    """Complete pulses (not touching the dump ends) starting inside the window."""
    return [
        (a, b) for a, b in runs
        if w0 <= a < w1 and a > times[0] and b < times[-1]
    ]


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CpCoordinate:
    """Sweep coordinates carried by every per-point result."""

    vctrl_index: int
    vctrl_fraction: float
    vctrl_v: float
    phase_index: int
    offset_s: float


@dataclass(frozen=True)
class CycleCharge:
    index: int
    t_start_s: float
    t_end_s: float
    qnet_c: float
    qplus_c: float
    qminus_c: float


@dataclass(frozen=True)
class PlateauResult:
    direction: str  # "UP" or "DN"
    available: bool
    reason: str
    current_a: float | None = None  # signed
    magnitude_a: float | None = None
    spread_a: float | None = None
    n_pulses: int = 0
    sign_ok: bool | None = None


@dataclass(frozen=True)
class CpPhaseResult:
    coord: CpCoordinate
    available: bool
    reason: str
    cycles: tuple = ()
    qnet_mean_c: float | None = None
    qnet_std_c: float | None = None
    qplus_mean_c: float | None = None
    qminus_mean_c: float | None = None
    asymmetry: float | None = None
    asymmetry_reason: str = ""
    drift_c: float | None = None
    settled: bool | None = None
    min_up_width_s: float | None = None
    min_dn_width_s: float | None = None
    plateau: PlateauResult | None = None  # UP at +plateau offset, DN at -


@dataclass(frozen=True)
class SlopeResult:
    vctrl_index: int
    vctrl_fraction: float
    vctrl_v: float
    available: bool
    reason: str
    slope_c_per_s: float | None = None


@dataclass(frozen=True)
class ComplianceWindow:
    available: bool
    reason: str
    lo_index: int | None = None
    hi_index: int | None = None
    lo_fraction: float | None = None
    hi_fraction: float | None = None
    lo_v: float | None = None
    hi_v: float | None = None
    n_points: int = 0
    mid_magnitude_a: float | None = None


@dataclass(frozen=True)
class ComplianceResult:
    up: ComplianceWindow
    dn: ComplianceWindow
    both: ComplianceWindow


@dataclass(frozen=True)
class OpResult:
    available: bool
    reason: str
    values: tuple = ()  # ((label, expr, value), ...)


@dataclass(frozen=True)
class ResolutionDelta:
    coord: CpCoordinate
    available: bool
    reason: str
    dqnet_c: float | None = None
    sign_changed: bool | None = None
    dmin_up_width_s: float | None = None
    dmin_dn_width_s: float | None = None
    material: bool | None = None
    converged: bool | None = None  # None means no claim can be made


@dataclass(frozen=True)
class CpSweepResult:
    vdd: float
    op: OpResult
    points: tuple
    diagnostic_points: tuple
    slopes: tuple
    compliance: ComplianceResult
    resolution: tuple = field(default=())

    def point(self, vi: int, pj: int) -> CpPhaseResult:
        for p in self.points:
            if p.coord.vctrl_index == vi and p.coord.phase_index == pj:
                return p
        raise KeyError((vi, pj))


# --------------------------------------------------------------------------
# Reducers
# --------------------------------------------------------------------------


def _coord(spec: CpSpec, vdd: float, vi: int, pj: int) -> CpCoordinate:
    f = spec.vctrl_fractions[vi]
    return CpCoordinate(vi, f, f * vdd, pj, spec.phase_offsets_s[pj])


def directional_plateau(times, current, up, dn, spec: CpSpec, vdd: float, direction: str) -> PlateauResult:
    """Plateau current of the `UP` or `DN` branch from exclusive pulses.

    Uses the middle half of each complete exclusive pulse that starts inside
    the integration window. UP is expected positive, DN negative.
    """
    if direction not in ("UP", "DN"):
        raise CpError(f"direction must be 'UP' or 'DN', got {direction!r}")
    intervals = active_intervals(times, up, dn, spec, vdd)
    if direction == "UP":
        runs = _runs(intervals, lambda u, d: u and not d)
    else:
        runs = _runs(intervals, lambda u, d: d and not u)
    pulses = _pulses_in_window(times, runs, spec.window_start_s, spec.window_end_s)
    if not pulses:
        return PlateauResult(direction, False, f"no exclusive {direction} plateau in the integration window")
    means = []
    for a, b in pulses:
        w = b - a
        lo, hi = a + w / 4.0, a + 3.0 * w / 4.0
        means.append(integrate(times, current, lo, hi) / (hi - lo))
    mean, std = _mean_std(means)
    expected_positive = direction == "UP"
    return PlateauResult(
        direction, True, "", current_a=mean, magnitude_a=abs(mean), spread_a=std,
        n_pulses=len(pulses), sign_ok=(mean > 0) if expected_positive else (mean < 0),
    )


def _min_width(times, up, dn, spec, vdd, which: str) -> float | None:
    intervals = active_intervals(times, up, dn, spec, vdd)
    pick = (lambda u, d: u) if which == "UP" else (lambda u, d: d)
    pulses = _pulses_in_window(times, _runs(intervals, pick), spec.window_start_s, spec.window_end_s)
    return min((b - a for a, b in pulses), default=None)


def reduce_cp_point(spec: CpSpec, vdd: float, vi: int, pj: int, text: str) -> CpPhaseResult:
    """Reduce one coordinate's dump. Unusable input -> unavailable, with reason."""
    coord = _coord(spec, vdd, vi, pj)
    try:
        times, cur, up, dn = parse_cp_tran(text)
        cycles = []
        for k, (a, b) in enumerate(spec.cycle_windows()):
            cycles.append(
                CycleCharge(
                    k, a, b,
                    integrate(times, cur, a, b, "net"),
                    integrate(times, cur, a, b, "pos"),
                    integrate(times, cur, a, b, "neg"),
                )
            )
        qnet, qstd = _mean_std([c.qnet_c for c in cycles])
        qplus, _ = _mean_std([c.qplus_c for c in cycles])
        qminus, _ = _mean_std([c.qminus_c for c in cycles])
        denom = qplus + qminus
        if denom > _TINY:
            asym, asym_reason = (qplus - qminus) / denom, ""
        else:
            asym, asym_reason = None, "Qplus + Qminus is empty; asymmetry undefined"
        drift = cycles[-1].qnet_c - cycles[0].qnet_c
        settled = abs(drift) <= spec.settle_tolerance * denom if denom > _TINY else abs(drift) <= _TINY
        plateau = None
        if pj == spec.offset_index(spec.plateau_offset_s):
            plateau = directional_plateau(times, cur, up, dn, spec, vdd, "UP")
        elif pj == spec.offset_index(-spec.plateau_offset_s):
            plateau = directional_plateau(times, cur, up, dn, spec, vdd, "DN")
        return CpPhaseResult(
            coord, True, "", tuple(cycles), qnet, qstd, qplus, qminus, asym, asym_reason,
            drift, settled,
            _min_width(times, up, dn, spec, vdd, "UP"),
            _min_width(times, up, dn, spec, vdd, "DN"),
            plateau,
        )
    except MeasureError as exc:
        return CpPhaseResult(coord, False, str(exc))


def _slope(spec: CpSpec, vdd: float, vi: int, grid: dict) -> SlopeResult:
    f = spec.vctrl_fractions[vi]
    base = dict(vctrl_index=vi, vctrl_fraction=f, vctrl_v=f * vdd)
    jp, jm = spec.offset_index(spec.slope_offset_s), spec.offset_index(-spec.slope_offset_s)
    p, m = grid.get((vi, jp)), grid.get((vi, jm))
    if p is None or m is None or not p.available or not m.available:
        bad = [r for r in (p, m) if r is None or not r.available]
        why = bad[0].reason if bad and bad[0] is not None else "slope-pair point missing"
        return SlopeResult(**base, available=False, reason=f"slope pair unavailable: {why}")
    span = p.coord.offset_s - m.coord.offset_s
    return SlopeResult(**base, available=True, reason="", slope_c_per_s=(p.qnet_mean_c - m.qnet_mean_c) / span)


def _window_for(spec, vdd, direction, plateaus: dict) -> ComplianceWindow:
    n = len(spec.vctrl_fractions)
    mid = spec.midrail_index()
    if mid is None:
        return ComplianceWindow(False, "midrail (0.5 VDD) is not a sampled VCTRL")

    def valid(i):
        p = plateaus.get(i)
        return p is not None and p.available and p.sign_ok and p.magnitude_a and p.magnitude_a > 0

    if not valid(mid):
        p = plateaus.get(mid)
        why = p.reason if p is not None and not p.available else "midrail plateau missing, zero or wrong sign"
        return ComplianceWindow(False, f"{direction} midrail reference invalid: {why}")
    ref = plateaus[mid].magnitude_a
    ok = lambda i: valid(i) and abs(plateaus[i].magnitude_a - ref) <= spec.compliance_tolerance * ref
    lo = hi = mid
    while lo - 1 >= 0 and ok(lo - 1):
        lo -= 1
    while hi + 1 < n and ok(hi + 1):
        hi += 1
    return _window(spec, vdd, lo, hi, ref)


def _window(spec, vdd, lo, hi, ref) -> ComplianceWindow:
    f = spec.vctrl_fractions
    return ComplianceWindow(
        True, "", lo, hi, f[lo], f[hi], f[lo] * vdd, f[hi] * vdd, hi - lo + 1, ref
    )


def compare_resolution(spec: CpSpec, vdd: float, base: dict, fine: dict) -> tuple:
    """Per-coordinate change between the main grid and the finer-grid rerun."""
    frac = spec.diagnostic.material_fraction if spec.diagnostic else 0.05
    out = []
    for vi, pj in spec.diagnostic_coordinates():
        coord = _coord(spec, vdd, vi, pj)
        b, f = base.get((vi, pj)), fine.get((vi, pj))
        if b is None or f is None or not b.available or not f.available:
            why = next((r.reason for r in (b, f) if r is not None and not r.available), "point missing")
            out.append(ResolutionDelta(coord, False, f"comparison unavailable: {why}"))
            continue
        dq = f.qnet_mean_c - b.qnet_mean_c
        flipped = b.qnet_mean_c * f.qnet_mean_c < 0
        scale = b.qplus_mean_c + b.qminus_mean_c
        material = abs(dq) > frac * scale if scale > _TINY else abs(dq) > _TINY
        dws = []
        for wb, wf in ((b.min_up_width_s, f.min_up_width_s), (b.min_dn_width_s, f.min_dn_width_s)):
            dws.append(None if wb is None or wf is None else wf - wb)
            if wb is not None and wf is not None and abs(wf - wb) > frac * wb:
                material = True
            elif (wb is None) != (wf is None):
                material = True
        out.append(
            ResolutionDelta(
                coord, True, "", dq, flipped, dws[0], dws[1], material,
                converged=not (material or flipped),
            )
        )
    return tuple(out)


def reduce_op(spec: CpSpec, text: str | None) -> OpResult:
    if not spec.op_vectors:
        return OpResult(False, "no operating-point vectors declared in the manifest")
    if text is None:
        return OpResult(False, f"dump missing: {op_dump_name()}")
    try:
        values = parse_cp_op(text, len(spec.op_vectors))
    except MeasureError as exc:
        return OpResult(False, str(exc))
    return OpResult(True, "", tuple((v.label, v.expr, x) for v, x in zip(spec.op_vectors, values)))


def reduce_cp_sweep(spec: CpSpec, vdd: float, dumps: dict, prefix: str = "") -> CpSweepResult:
    """Reduce every dump of one PVT point.

    `dumps` maps dump filename (as `waveform_names` produces, including the
    prefix) to its text. A missing or `None` entry, or an unparseable one,
    yields an unavailable result that keeps its coordinates and the reason.
    """
    grid, diag = {}, {}
    for vi in range(len(spec.vctrl_fractions)):
        for pj in range(len(spec.phase_offsets_s)):
            name = sweep_dump_name(vi, pj, prefix)
            text = dumps.get(name)
            grid[(vi, pj)] = (
                reduce_cp_point(spec, vdd, vi, pj, text)
                if text is not None
                else CpPhaseResult(_coord(spec, vdd, vi, pj), False, f"dump missing: {name}")
            )
    for vi, pj in spec.diagnostic_coordinates():
        name = sweep_dump_name(vi, pj, prefix, diagnostic=True)
        text = dumps.get(name)
        diag[(vi, pj)] = (
            reduce_cp_point(spec, vdd, vi, pj, text)
            if text is not None
            else CpPhaseResult(_coord(spec, vdd, vi, pj), False, f"dump missing: {name}")
        )

    slopes = tuple(_slope(spec, vdd, vi, grid) for vi in range(len(spec.vctrl_fractions)))

    jp, jm = spec.offset_index(spec.plateau_offset_s), spec.offset_index(-spec.plateau_offset_s)
    up_pl = {vi: grid[(vi, jp)].plateau or PlateauResult("UP", False, grid[(vi, jp)].reason or "no plateau")
             for vi in range(len(spec.vctrl_fractions))}
    dn_pl = {vi: grid[(vi, jm)].plateau or PlateauResult("DN", False, grid[(vi, jm)].reason or "no plateau")
             for vi in range(len(spec.vctrl_fractions))}
    up_w = _window_for(spec, vdd, "UP", up_pl)
    dn_w = _window_for(spec, vdd, "DN", dn_pl)
    if up_w.available and dn_w.available:
        lo, hi = max(up_w.lo_index, dn_w.lo_index), min(up_w.hi_index, dn_w.hi_index)
        both = _window(spec, vdd, lo, hi, None)
    else:
        why = up_w.reason if not up_w.available else dn_w.reason
        both = ComplianceWindow(False, f"directional window unavailable: {why}")

    op_text = dumps.get(op_dump_name(prefix)) if spec.op_vectors else None
    op = reduce_op(spec, op_text) if spec.op_vectors else OpResult(False, "no operating-point vectors declared in the manifest")
    if spec.op_vectors and op_text is None:
        op = OpResult(False, f"dump missing: {op_dump_name(prefix)}")

    return CpSweepResult(
        vdd=vdd, op=op, points=tuple(grid.values()), diagnostic_points=tuple(diag.values()),
        slopes=slopes, compliance=ComplianceResult(up_w, dn_w, both),
        resolution=compare_resolution(spec, vdd, grid, diag) if spec.diagnostic else (),
    )
