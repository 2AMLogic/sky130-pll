"""Reduce `klt sim` waveform artifacts to supply-current / power figures (issue #233).

Pure functions, stdlib only, no simulator needed: `sim/tests/test_power.py`
drives every function below from synthetic traces whose true mean current is
known by construction.

## What is measured

Each block's testbench runs ONE transient per PVT point, staged in time (see
`sim/power/build.py`): an *idle* stage (the block held without switching) and
several *active* stages (the block running at a stated operating point). For
each stage this module reduces the dumped supply-source branch current `i(v1)`
to a mean current:

* **active stage** -- the mean of `i(v1)` over an *integer number of cycles of
  the stage's alignment node* (`align_node`: the VCO output, the divider
  output, or the PFD reference), starting at the first rising edge of that
  node after the stage's settling time. A mean over a fractional number of
  cycles of a periodic current is biased by up to (ripple/N_cycles); aligning
  to whole cycles removes that bias, which is why this reducer exists instead
  of a fixed-window `.meas AVG` (the request still carries fixed-window
  `.meas` cards as a coarse cross-check only).
* **idle stage** -- the plain mean over `[t0 + settle, t1]` (no cycles to
  align to). The reducer also counts alignment-node edges in the window, so a
  stage that was meant to be quiescent but was not is visible.

`i(v1)` is the current INTO the source's + terminal, so supply current drawn
by the block is `-mean(i(v1))`; power is that times the point's own supply.

## What is NOT measured here

No dynamic/static split is *measured*: the idle stage gives the static
(leakage + bias) current of the block held quiescent, and "dynamic" in the
roll-up is the DIFFERENCE active - idle, reported as such. It is a derived
figure, not a separately simulated one (short-circuit and bias current that
only flow while switching are inside it).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SIM = Path(__file__).resolve().parents[1]
if str(_SIM) not in sys.path:  # `harness` is a sibling package, not installed
    sys.path.insert(0, str(_SIM))

from harness.measure import edge_times  # noqa: E402  (proven crossing extractor)

# Hysteresis for edge detection, as a fraction of the supply (same default the
# harness uses for clock nodes).
HYSTERESIS_FRAC = 0.15


class PowerError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# waveform access
# --------------------------------------------------------------------------- #


def load_waveform(path: str | Path) -> dict:
    """Load a `klt sim` waveform JSON into {variable name (lowercase): [values]}."""
    doc = json.loads(Path(path).read_text())
    names = [v["name"].lower() for v in doc["variables"]]
    cols = list(zip(*doc["points"]))
    if len(cols) != len(names):
        raise PowerError(f"{path}: {len(names)} variables but {len(cols)} columns")
    return {n: list(c) for n, c in zip(names, cols)}


def _col(wave: dict, name: str) -> list:
    key = name.lower()
    if key not in wave:
        raise PowerError(f"waveform has no vector {name!r} (has: {', '.join(sorted(wave))})")
    return wave[key]


# --------------------------------------------------------------------------- #
# reduction
# --------------------------------------------------------------------------- #


def _interp(times, values, i: int, t: float) -> float:
    """Value at `t` inside the sample interval [times[i], times[i+1]]."""
    t0, t1 = times[i], times[i + 1]
    if t1 == t0:
        return values[i]
    return values[i] + (values[i + 1] - values[i]) * (t - t0) / (t1 - t0)


def window_mean(times, values, t_a: float, t_b: float) -> float:
    """Time-weighted mean of a piecewise-linear trace over [t_a, t_b].

    Trapezoid integration with the window ends interpolated onto the samples,
    so the result does not depend on where the (adaptive) timestep happened to
    put its points.
    """
    if not t_b > t_a:
        raise PowerError(f"empty averaging window [{t_a}, {t_b}]")
    if t_a < times[0] or t_b > times[-1]:
        raise PowerError(
            f"window [{t_a:.4g}, {t_b:.4g}] s outside the trace [{times[0]:.4g}, {times[-1]:.4g}] s"
        )
    area = 0.0
    n = len(times)
    for i in range(n - 1):
        lo, hi = times[i], times[i + 1]
        if hi <= t_a or lo >= t_b:
            continue
        a, b = max(lo, t_a), min(hi, t_b)
        va = _interp(times, values, i, a)
        vb = _interp(times, values, i, b)
        area += 0.5 * (va + vb) * (b - a)
    return area / (t_b - t_a)


@dataclass(frozen=True)
class StageResult:
    stage_id: str
    kind: str
    label: str
    ok: bool
    reason: str = ""
    i_a: float | None = None  # supply current drawn from the rail (A, positive)
    p_w: float | None = None  # i_a * supply
    f_hz: float | None = None  # alignment-node frequency over the window
    window: tuple | None = None  # (t_start_s, t_end_s)
    cycles: int | None = None
    edges_in_window: int | None = None
    extra: dict = field(default_factory=dict)


def reduce_stage(wave: dict, stage: dict, *, align_node: str, supply_v: float,
                 hysteresis_frac: float = HYSTERESIS_FRAC) -> StageResult:
    """Reduce one stage of one PVT point's waveform.

    `stage` is an entry of a `<block>.stages.json` table: `id`, `kind`
    (`idle`/`active`), `label`, `t0`, `t1`, `settle` and (active) `cycles`.
    """
    sid, kind, label = stage["id"], stage["kind"], stage.get("label", stage["id"])
    times = _col(wave, "time")
    i_vec = _col(wave, "i(v1)")
    t_from = stage["t0"] + stage["settle"]
    t_to = stage["t1"]

    def fail(reason: str, **kw) -> StageResult:
        return StageResult(sid, kind, label, False, reason=reason, **kw)

    try:
        node = _col(wave, align_node)
    except PowerError as exc:
        return fail(str(exc))
    rising, _falling = edge_times(
        times, node, 0.5 * supply_v, hysteresis_frac * supply_v
    )

    if kind == "idle":
        window = (t_from, t_to)
        n_edges = sum(1 for e in rising if window[0] <= e <= window[1])
        try:
            mean_i = window_mean(times, i_vec, *window)
        except PowerError as exc:
            return fail(str(exc))
        i_a = -mean_i
        return StageResult(sid, kind, label, True, i_a=i_a, p_w=i_a * supply_v,
                           window=window, edges_in_window=n_edges, cycles=0)

    if kind != "active":
        return fail(f"unknown stage kind {kind!r}")
    cycles = int(stage["cycles"])
    in_stage = [e for e in rising if t_from <= e <= t_to]
    if len(in_stage) < cycles + 1:
        return fail(
            f"only {len(in_stage)} rising edges of {align_node} in "
            f"[{t_from * 1e9:.1f}, {t_to * 1e9:.1f}] ns; {cycles + 1} needed for "
            f"{cycles} whole cycle(s) -- stage too slow or alignment node dead",
            edges_in_window=len(in_stage),
        )
    t_a, t_b = in_stage[0], in_stage[cycles]
    try:
        mean_i = window_mean(times, i_vec, t_a, t_b)
    except PowerError as exc:
        return fail(str(exc))
    i_a = -mean_i
    return StageResult(
        sid, kind, label, True, i_a=i_a, p_w=i_a * supply_v,
        f_hz=cycles / (t_b - t_a), window=(t_a, t_b), cycles=cycles,
        edges_in_window=len(in_stage),
    )


def reduce_point(wave: dict, stages_doc: dict, *, supply_v: float) -> list:
    """Reduce every stage of one PVT point."""
    return [
        reduce_stage(wave, s, align_node=stages_doc["align_node"], supply_v=supply_v)
        for s in stages_doc["stages"]
    ]


# --------------------------------------------------------------------------- #
# roll-up arithmetic
# --------------------------------------------------------------------------- #


def interpolate_at_frequency(points: list, f_target: float) -> tuple:
    """Linear interpolation of supply current against output frequency.

    `points` is a list of (f_hz, i_a) from the active stages of ONE PVT point.
    Returns (i_a, note). Refuses to extrapolate: if `f_target` is not bracketed
    by two measured frequencies, returns (None, reason) -- a roll-up figure
    must never be an extrapolation presented as a measurement.
    """
    pts = sorted((f, i) for f, i in points if f is not None and i is not None)
    if len(pts) < 2:
        return None, f"fewer than two measured stages ({len(pts)})"
    if f_target < pts[0][0] or f_target > pts[-1][0]:
        return None, (
            f"target {f_target / 1e6:.1f} MHz outside the measured "
            f"{pts[0][0] / 1e6:.1f}-{pts[-1][0] / 1e6:.1f} MHz span"
        )
    for (f0, i0), (f1, i1) in zip(pts, pts[1:]):
        if f0 <= f_target <= f1:
            if f1 == f0:
                return i0, "exact"
            w = (f_target - f0) / (f1 - f0)
            return i0 + w * (i1 - i0), (
                f"interpolated between {f0 / 1e6:.1f} and {f1 / 1e6:.1f} MHz"
            )
    return None, "no bracketing pair"  # pragma: no cover


def split_static_dynamic(i_active: float | None, i_idle: float | None) -> tuple:
    """(static, dynamic) current: static = idle stage, dynamic = active - idle.

    `dynamic` can come out marginally negative when the idle stage is not a
    strict lower bound (bias that is larger at idle); it is reported as is.
    """
    if i_active is None or i_idle is None:
        return None, None
    return i_idle, i_active - i_idle
