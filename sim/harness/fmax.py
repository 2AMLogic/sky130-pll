"""Divider Fmax characterization: search planning, stimulus/target coupling,
per-period correct-division criterion and boundary selection (issue #244).

This module is PDK-free and simulator-free: everything here is arithmetic over
declared parameters and over waveforms handed in by the caller. The I/O half
(netlisting, executing, writing the record) lives in `fmax_cli.py`.

Why a separate campaign. The fixed-frequency divider campaigns
(`sim/divider*/`) establish correct division at one tested CLK frequency; the
harness `sweep` mechanism alters a DC source and cannot move a pulse period
(issue #129 deliberately left that out). This campaign adds only the one thing
missing: a probe at a declared CLK frequency is a normal harness unit whose
`pulse(...)` period, width and the expected division period are all derived
from that single frequency (`stimulus_for`), so they cannot disagree.

Design choices that the evidence record repeats verbatim:

* **Grid search, not free bisection.** Candidate frequencies live on a declared
  resolution grid. Stage 1 probes every `coarse_stride`-th grid point; stage 2
  probes the grid points strictly inside the lowest pass->fail transition.
  Monotonicity is therefore *observed*, never assumed: any pass above a fail is
  reported (`NON_MONOTONIC`), and a pass island hiding between two coarse
  points is a stated limitation, not something the result claims to exclude.
* **Per-period criterion.** Every individual steady-state output period must be
  within `tolerance_frac` of N/f_CLK; leading and trailing silence are checked
  too, so an averaged frequency can never hide a skipped or malformed cycle.
* **Simulator trouble is not an electrical result.** A timeout, `Error:` line,
  missing completion marker, missing/unparseable/truncated dump is
  `INCONCLUSIVE`. Only a completed simulation whose waveform fails the
  criterion (including "too few output edges") is a measured `FAIL`.
* **Never an unbracketed scalar.** A cell is reported as the highest verified
  passing probe plus the *adjacent* failing grid probe, or as an explicit
  censored/inconclusive status. `fmax_bracket` is the only way a number leaves
  this module and it always carries both ends or a status that says why not.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from . import measure as measure_mod

SCHEMA = "sky130-pll.harness.fmax/1"

# Probe verdicts.
PASS = "PASS"
FAIL = "FAIL"
INCONCLUSIVE = "INCONCLUSIVE"

# Cell (boundary) statuses.
BRACKETED = "BRACKETED"
NON_MONOTONIC = "NON_MONOTONIC"
CENSORED_HIGH = "CENSORED_HIGH"
CENSORED_LOW = "CENSORED_LOW"
CELL_INCONCLUSIVE = "INCONCLUSIVE"

#: Cell statuses that count as a resolved, recordable result.
RESOLVED_STATUSES = (BRACKETED, NON_MONOTONIC, CENSORED_HIGH)


class FmaxError(ValueError):
    """A malformed Fmax manifest or an impossible probe request."""


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Search:
    f_min_hz: float
    f_max_hz: float
    resolution_hz: float
    coarse_stride: int


@dataclass(frozen=True)
class Stimulus:
    rise_s: float  # rise time == fall time of the ideal CLK source
    duty: float  # fraction of the period CLK is above mid-rail (50% points)
    reset_low_until_s: float  # RESETB stays low until here ...
    reset_high_at_s: float  # ... and reaches the supply here (linear ramp)
    amplitude: str  # "supply": CLK/RESETB high level tracks each point's VDD


@dataclass(frozen=True)
class Criterion:
    skip_output_periods: int  # expected output periods ignored after reset release
    min_periods: int  # consecutive steady-state periods that must all be good
    margin_periods: int  # extra output periods simulated beyond the above
    tolerance_frac: float  # per-period |T_out - N/f_CLK| / (N/f_CLK) bound
    threshold_frac: float
    hysteresis_frac: float
    tran_step_s: float
    timeout_s: int


@dataclass(frozen=True)
class Modulus:
    n: int
    schematic: str  # path relative to the manifest's testbench/ directory
    note: str = ""


@dataclass(frozen=True)
class FmaxSpec:
    search: Search
    stimulus: Stimulus
    criterion: Criterion
    moduli: tuple

    @classmethod
    def from_manifest(cls, manifest: dict) -> FmaxSpec:
        if manifest.get("schema") != SCHEMA:
            raise FmaxError(f"manifest schema must be {SCHEMA!r}")

        def need(block: dict, key: str, where: str):
            if key not in block:
                raise FmaxError(f"{where}: missing required key {key!r}")
            return block[key]

        s = need(manifest, "search", "manifest")
        search = Search(
            f_min_hz=float(need(s, "f_min_hz", "search")),
            f_max_hz=float(need(s, "f_max_hz", "search")),
            resolution_hz=float(need(s, "resolution_hz", "search")),
            coarse_stride=int(need(s, "coarse_stride", "search")),
        )
        if not (0 < search.f_min_hz < search.f_max_hz):
            raise FmaxError("search: need 0 < f_min_hz < f_max_hz")
        if search.resolution_hz <= 0 or search.coarse_stride < 1:
            raise FmaxError("search: resolution_hz > 0 and coarse_stride >= 1 required")
        span = (search.f_max_hz - search.f_min_hz) / search.resolution_hz
        if abs(span - round(span)) > 1e-6:
            raise FmaxError(
                "search: (f_max_hz - f_min_hz) must be a whole number of resolution_hz "
                "steps, so the declared bounds are themselves grid points"
            )

        w = need(manifest, "stimulus", "manifest")
        stim = Stimulus(
            rise_s=float(need(w, "rise_s", "stimulus")),
            duty=float(need(w, "duty", "stimulus")),
            reset_low_until_s=float(need(w, "reset_low_until_s", "stimulus")),
            reset_high_at_s=float(need(w, "reset_high_at_s", "stimulus")),
            amplitude=str(need(w, "amplitude", "stimulus")),
        )
        if stim.amplitude != "supply":
            raise FmaxError("stimulus.amplitude: only 'supply' is implemented")
        if not (0.1 <= stim.duty <= 0.9):
            raise FmaxError("stimulus.duty must be within [0.1, 0.9]")
        if stim.reset_high_at_s < stim.reset_low_until_s:
            raise FmaxError("stimulus: reset_high_at_s must not precede reset_low_until_s")

        c = need(manifest, "criterion", "manifest")
        crit = Criterion(
            skip_output_periods=int(need(c, "skip_output_periods", "criterion")),
            min_periods=int(need(c, "min_periods", "criterion")),
            margin_periods=int(need(c, "margin_periods", "criterion")),
            tolerance_frac=float(need(c, "tolerance_frac", "criterion")),
            threshold_frac=float(need(c, "threshold_frac", "criterion")),
            hysteresis_frac=float(need(c, "hysteresis_frac", "criterion")),
            tran_step_s=float(need(c, "tran_step_s", "criterion")),
            timeout_s=int(need(c, "timeout_s", "criterion")),
        )
        if crit.min_periods < 2 or crit.skip_output_periods < 0 or crit.margin_periods < 1:
            raise FmaxError("criterion: min_periods >= 2, skip >= 0, margin >= 1 required")
        if not (0 < crit.tolerance_frac < 0.5):
            raise FmaxError("criterion.tolerance_frac must be within (0, 0.5)")

        raw = need(manifest, "moduli", "manifest")
        moduli = tuple(
            Modulus(n=int(m["n"]), schematic=str(m["schematic"]), note=str(m.get("note", "")))
            for m in raw
        )
        if not moduli or len({m.n for m in moduli}) != len(moduli):
            raise FmaxError("moduli: need a non-empty list of distinct N")
        return cls(search=search, stimulus=stim, criterion=crit, moduli=moduli)


# --------------------------------------------------------------------------- #
# grid and two-stage plan
# --------------------------------------------------------------------------- #


def grid(search: Search) -> list:
    """The candidate CLK frequencies, ascending, bounds inclusive, in Hz."""
    steps = round((search.f_max_hz - search.f_min_hz) / search.resolution_hz)
    return [round(search.f_min_hz + i * search.resolution_hz, 3) for i in range(steps + 1)]


def coarse_indices(size: int, stride: int) -> list:
    """Stage 1 grid indices: every `stride`-th point, always including the top."""
    idx = list(range(0, size, stride))
    if idx[-1] != size - 1:
        idx.append(size - 1)
    return idx


def refine_indices(observed: dict) -> list:
    """Stage 2 grid indices for one cell, from its stage-1 observations.

    `observed` maps grid index -> PASS/FAIL/INCONCLUSIVE. The refinement target
    is the lowest coarse pass->fail transition between *adjacent* coarse
    observations; every grid index strictly between them is probed. A pass
    next to an inconclusive probe is deliberately not refined: the bracket is
    not established, and the cell will report that rather than guess.
    """
    ordered = sorted(observed)
    for lo, hi in zip(ordered, ordered[1:]):
        if observed[lo] == PASS and observed[hi] == FAIL:
            return list(range(lo + 1, hi))
    return []


# --------------------------------------------------------------------------- #
# stimulus / target coupling
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ProbePlan:
    """Everything a probe at one CLK frequency needs, derived from that one
    frequency so the stimulus and the pass target cannot disagree."""

    n: int
    freq_hz: float
    supply_v: float
    clk_period_s: float
    clk_width_s: float  # pulse() "pw": time at the high level, excluding edges
    rise_s: float
    expected_out_period_s: float  # N / f_CLK
    reset_low_until_s: float
    reset_high_at_s: float
    steady_from_s: float  # edges before this are ignored by the criterion
    tran_stop_s: float
    min_periods: int
    tolerance_frac: float

    @property
    def clk_card(self) -> str:
        v = self.supply_v
        return (
            f"pulse(0 {v:g} 0 {_si(self.rise_s)} {_si(self.rise_s)} "
            f"{_si(self.clk_width_s)} {_si(self.clk_period_s)})"
        )

    @property
    def reset_card(self) -> str:
        return (
            f"pwl(0 0 {_si(self.reset_low_until_s)} 0 "
            f"{_si(self.reset_high_at_s)} {self.supply_v:g})"
        )


def _si(seconds: float) -> str:
    """A SPICE time literal with full precision (no lossy rounding to ps)."""
    return f"{seconds * 1e12:.6g}p"


def stimulus_for(spec: FmaxSpec, n: int, freq_hz: float, supply_v: float) -> ProbePlan:
    stim, crit = spec.stimulus, spec.criterion
    if freq_hz <= 0 or n < 1:
        raise FmaxError("stimulus_for: need freq_hz > 0 and n >= 1")
    period = 1.0 / freq_hz
    # pulse() pw excludes the edges; the 50% points are high for `duty*period`.
    width = stim.duty * period - stim.rise_s
    low = period - width - 2 * stim.rise_s
    if width <= 0 or low <= 0:
        raise FmaxError(
            f"{freq_hz / 1e6:g} MHz: period {period * 1e12:.1f} ps cannot hold "
            f"{stim.rise_s * 1e12:.1f} ps edges at {stim.duty:.0%} duty"
        )
    out_period = n * period
    steady_from = stim.reset_high_at_s + crit.skip_output_periods * out_period
    stop = steady_from + (crit.min_periods + crit.margin_periods) * out_period
    return ProbePlan(
        n=n,
        freq_hz=freq_hz,
        supply_v=supply_v,
        clk_period_s=period,
        clk_width_s=width,
        rise_s=stim.rise_s,
        expected_out_period_s=out_period,
        reset_low_until_s=stim.reset_low_until_s,
        reset_high_at_s=stim.reset_high_at_s,
        steady_from_s=steady_from,
        tran_stop_s=stop,
        min_periods=crit.min_periods,
        tolerance_frac=crit.tolerance_frac,
    )


_CLK_SRC_RE = re.compile(r"^(V\d+\s+CLK\s+\S+\s+)pulse\([^)]*\)", re.MULTILINE)
_RST_SRC_RE = re.compile(r"^(V\d+\s+RESETB\s+\S+\s+)pwl\([^)]*\)", re.MULTILINE)


def patch_stimulus(netlist_text: str, plan: ProbePlan) -> str:
    """Replace the netlisted CLK `pulse(...)` and RESETB `pwl(...)` sources.

    Exactly one match of each is required: zero means the testbench does not
    have the shape this campaign assumes, more than one would silently drive
    only part of the DUT's clock.
    """
    for pattern, card, what in (
        (_CLK_SRC_RE, plan.clk_card, "CLK pulse source"),
        (_RST_SRC_RE, plan.reset_card, "RESETB pwl source"),
    ):
        found = pattern.findall(netlist_text)
        if len(found) != 1:
            raise FmaxError(f"expected exactly one {what} in the netlist, found {len(found)}")
        netlist_text = pattern.sub(lambda m, c=card: f"{m.group(1)}{c}", netlist_text)
    return netlist_text


def measure_manifest(spec: FmaxSpec, plan: ProbePlan) -> dict:
    """The harness `measure` block that makes `build_control_block` dump FBCLK
    for this probe (no lock block: the criterion here is `classify_waveform`)."""
    return {
        "measure": {
            "node": "FBCLK",
            "tran_step": _si(spec.criterion.tran_step_s),
            "tran_stop": f"{plan.tran_stop_s * 1e9:.6g}n",
            "timeout_s": spec.criterion.timeout_s,
            "threshold_frac": spec.criterion.threshold_frac,
            "hysteresis_frac": spec.criterion.hysteresis_frac,
            "settle_from": "0",
            "min_edges": 2,
            "require_oscillation": False,
        }
    }


# --------------------------------------------------------------------------- #
# per-probe verdict
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ProbeVerdict:
    status: str  # PASS / FAIL / INCONCLUSIVE
    reason: str
    edges: int = 0
    periods: int = 0
    worst_dev_frac: float | None = None


def classify_waveform(times, values, plan: ProbePlan, *, threshold_frac: float,
                      hysteresis_frac: float) -> ProbeVerdict:
    """Judge one completed probe's FBCLK trace against the per-period criterion.

    The trace is the evidence that the simulator ran; what it says about the
    divider is judged here. Order of checks matters and is deliberate:

    1. a trace that stops before the planned window is INCONCLUSIVE (the
       simulation, not the divider, ended early);
    2. leading silence, trailing silence and too few edges are FAILs (the
       divider produced no/too few output edges in a complete window);
    3. every individual period must sit within tolerance of N/f_CLK.
    """
    if not times:
        return ProbeVerdict(INCONCLUSIVE, "empty waveform")
    if times[-1] < plan.tran_stop_s * 0.999:
        return ProbeVerdict(
            INCONCLUSIVE,
            f"waveform ends at {times[-1] * 1e9:.2f} ns, before the planned "
            f"{plan.tran_stop_s * 1e9:.2f} ns window",
        )
    vdd = plan.supply_v
    rising, _ = measure_mod.edge_times(
        times, values, threshold_frac * vdd, hysteresis_frac * vdd
    )
    steady = [t for t in rising if t >= plan.steady_from_s]
    expected = plan.expected_out_period_s
    tol = plan.tolerance_frac
    limit = expected * (1 + tol)
    t_end = times[-1]

    if len(steady) < plan.min_periods + 1:
        return ProbeVerdict(
            FAIL,
            f"missing output edges: {len(steady)} rising edge(s) in the steady window, "
            f"need {plan.min_periods + 1}",
            edges=len(steady),
        )
    if steady[0] - plan.steady_from_s > limit:
        return ProbeVerdict(
            FAIL,
            f"first steady output edge {(steady[0] - plan.steady_from_s) * 1e9:.2f} ns "
            f"after the window opens (limit {limit * 1e9:.2f} ns)",
            edges=len(steady),
        )
    if t_end - steady[-1] > limit:
        return ProbeVerdict(
            FAIL,
            f"output went silent: last edge {(t_end - steady[-1]) * 1e9:.2f} ns before the "
            f"end of the window (limit {limit * 1e9:.2f} ns)",
            edges=len(steady),
        )
    periods = [b - a for a, b in zip(steady, steady[1:])]
    devs = [abs(p - expected) / expected for p in periods]
    worst = max(devs)
    if worst > tol:
        k = devs.index(worst)
        return ProbeVerdict(
            FAIL,
            f"period {k + 1} of {len(periods)} is {periods[k] * 1e9:.3f} ns vs expected "
            f"{expected * 1e9:.3f} ns ({worst:.1%} > {tol:.1%})",
            edges=len(steady),
            periods=len(periods),
            worst_dev_frac=worst,
        )
    return ProbeVerdict(
        PASS,
        f"{len(periods)} consecutive output periods within {tol:.1%} of "
        f"{expected * 1e9:.3f} ns (worst {worst:.2%})",
        edges=len(steady),
        periods=len(periods),
        worst_dev_frac=worst,
    )


# --------------------------------------------------------------------------- #
# boundary selection
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Boundary:
    """The reduced result for one (modulus, PVT point) cell."""

    status: str
    pass_hz: float | None  # highest verified passing probe below the first failure
    fail_hz: float | None  # the adjacent failing grid probe
    detail: str
    non_monotonic_passes_hz: tuple = ()  # passing probes above the first failure
    probes: int = 0
    inconclusive_hz: tuple = field(default=())

    @property
    def resolved(self) -> bool:
        return self.status in RESOLVED_STATUSES


def fmax_bracket(observations: dict, grid_hz: list) -> Boundary:
    """Reduce a cell's probe verdicts to a bracket or an explicit status.

    `observations` maps grid index -> PASS/FAIL/INCONCLUSIVE for the probes that
    were actually run (any subset of the grid). Rules, in order:

    * no failing probe: top-of-range probe passed -> CENSORED_HIGH (the boundary
      is above the search range; `pass_hz` is only a lower bound and
      `fail_hz` is None), otherwise INCONCLUSIVE;
    * no passing probe: lowest-of-range probe failed -> CENSORED_LOW, else
      INCONCLUSIVE;
    * otherwise take the *lowest* failing probe f; the verified pass is the
      highest passing probe below it. They must be adjacent among the probes
      that ran (nothing, in particular no inconclusive probe, between them) and
      adjacent on the grid at the end of stage 2 -- else INCONCLUSIVE. Passes
      above f make the cell NON_MONOTONIC; the bracket is still the lowest one.
    """
    if not observations:
        return Boundary(CELL_INCONCLUSIVE, None, None, "no probes ran")
    order = sorted(observations)
    hz = lambda i: grid_hz[i]  # noqa: E731
    n_probes = len(order)
    inconc = tuple(hz(i) for i in order if observations[i] == INCONCLUSIVE)
    passes = [i for i in order if observations[i] == PASS]
    fails = [i for i in order if observations[i] == FAIL]

    if not fails:
        top = len(grid_hz) - 1
        if observations.get(top) == PASS:
            return Boundary(
                CENSORED_HIGH,
                hz(max(passes)),
                None,
                f"all probes passed through the top of the search range "
                f"({hz(top) / 1e6:g} MHz); the boundary lies above it",
                probes=n_probes,
                inconclusive_hz=inconc,
            )
        return Boundary(
            CELL_INCONCLUSIVE, None, None,
            "no failing probe and the top-of-range probe did not pass",
            probes=n_probes, inconclusive_hz=inconc,
        )
    if not passes:
        if observations.get(0) == FAIL:
            return Boundary(
                CENSORED_LOW, None, hz(min(fails)),
                f"even the lowest searched frequency ({hz(0) / 1e6:g} MHz) failed; "
                "the boundary lies below the search range",
                probes=n_probes, inconclusive_hz=inconc,
            )
        return Boundary(
            CELL_INCONCLUSIVE, None, hz(min(fails)),
            "no passing probe and the bottom-of-range probe did not fail",
            probes=n_probes, inconclusive_hz=inconc,
        )

    first_fail = min(fails)
    below = [i for i in passes if i < first_fail]
    if not below:
        return Boundary(
            CELL_INCONCLUSIVE, None, hz(first_fail),
            "the lowest failing probe has no passing probe below it",
            non_monotonic_passes_hz=tuple(hz(i) for i in passes),
            probes=n_probes, inconclusive_hz=inconc,
        )
    p = max(below)
    between_probed = [i for i in order if p < i < first_fail]
    if between_probed:
        return Boundary(
            CELL_INCONCLUSIVE, hz(p), hz(first_fail),
            "an inconclusive probe lies between the highest pass and the lowest "
            f"failure ({', '.join(f'{hz(i) / 1e6:g} MHz' for i in between_probed)}); "
            "no adjacent bracket is established",
            probes=n_probes, inconclusive_hz=inconc,
        )
    if first_fail - p != 1:
        return Boundary(
            CELL_INCONCLUSIVE, hz(p), hz(first_fail),
            f"pass {hz(p) / 1e6:g} MHz and fail {hz(first_fail) / 1e6:g} MHz are not "
            "adjacent on the resolution grid (refinement incomplete)",
            probes=n_probes, inconclusive_hz=inconc,
        )
    above_passes = tuple(hz(i) for i in passes if i > first_fail)
    if above_passes:
        return Boundary(
            NON_MONOTONIC, hz(p), hz(first_fail),
            f"passing probe(s) above the first failure: "
            f"{', '.join(f'{f / 1e6:g}' for f in above_passes)} MHz -- "
            "division is not monotonic in frequency here; the bracket is the lowest one",
            non_monotonic_passes_hz=above_passes,
            probes=n_probes, inconclusive_hz=inconc,
        )
    return Boundary(
        BRACKETED, hz(p), hz(first_fail),
        f"highest verified pass {hz(p) / 1e6:g} MHz; adjacent failing grid probe "
        f"{hz(first_fail) / 1e6:g} MHz",
        probes=n_probes, inconclusive_hz=inconc,
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
