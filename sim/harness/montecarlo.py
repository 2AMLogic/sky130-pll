"""Build the Monte Carlo (process + local-mismatch) statistical trial matrix
for a run.

A PVT sweep (`sim/harness/corners.py`) crosses process corner x temperature x
supply and asks "does this DUT run at every combination of these fixed,
named points". A Monte Carlo campaign asks a different question at a single,
fixed PVT point: "how does this DUT's behavior scatter across many random
draws of within-die mismatch and/or die-to-die process variation". A trial is
therefore (trial index, RNG seed) at one (base corner, temperature, supply);
the sampling itself happens inside the sky130 device models, not in this
harness.

sky130's ngspice model library wires this up via two `.param` switches that
gate `agauss()`/`gauss()` calls already present in the shipped models (see
e.g. `libs.tech/ngspice/r+c.mrp1monte.spice`'s
`sky130_fd_pr__res_generic_po__tc1_slope` and the `combined/sky130.lib.spice`
`<corner>_mm` `.lib` sections):

  - `MC_PR_SWITCH` -- die-to-die / lot-to-lot *process* variation. Every
    corner's `.lib` section defines it (default 0); it is not tied to any
    particular corner name. A single draw applies uniformly to every
    instance of a given primitive in the netlist (correlated across
    instances -- this is process variation, not mismatch).
  - `MC_MM_SWITCH` -- within-die device *mismatch*. The `<corner>_mm` `.lib`
    sections (`tt_mm`, `ss_mm`, ...) default this to 1; the plain sections
    (`tt`, `ss`, ...) default it to 0. Each device instance gets its own
    independent draw (uncorrelated across instances on the same die).

Both switches read from ngspice's global RNG, seeded per run via
`.options seed=<N>` (verified empirically against this repo's sky130 install:
a fixed seed reproduces the same draw; a different seed draws differently --
see the record this module's first pdk-smoke run produces for the evidence).
`sim/harness/runner.patch_netlist_mc` is what actually injects these cards
into a netlisted DUT; this module only builds the list of trials to run.
"""

from __future__ import annotations

from dataclasses import dataclass


class McConfigError(ValueError):
    pass


@dataclass(frozen=True)
class McTrial:
    trial: int
    seed: int
    corner: str
    temp_c: float
    supply_v: float
    mismatch: bool
    process: bool

    @property
    def lib_corner(self) -> str:
        """The `.lib` section name to netlist against: the sky130 `*_mm`
        sections are the ones that default MC_MM_SWITCH on, so mismatch
        sampling needs that suffix; process-only sampling does not (see this
        module's docstring)."""
        return f"{self.corner}_mm" if self.mismatch else self.corner

    @property
    def corner_id(self) -> str:
        """Filename-safe id: `mc<trial>_seed<seed>_<lib_corner>_<temp>c_<supply>v`,
        the Monte Carlo analogue of `corners.PvtPoint.corner_id` (see
        sim/README.md's `<corner-id>` convention)."""
        temp_txt = f"{self.temp_c:g}"
        return f"mc{self.trial:03d}_seed{self.seed}_{self.lib_corner}_{temp_txt}c_{self.supply_v:.2f}v"


def build_trials(
    manifest: dict,
    valid_process_corners: tuple,
    corner_override: str | None = None,
    trials_override: int | None = None,
    seed_base_override: int | None = None,
    temp_override: float | None = None,
    supply_override: float | None = None,
    mismatch_override: bool | None = None,
    process_override: bool | None = None,
) -> list:
    """Build the ordered list of `McTrial`s for a manifest's `monte_carlo`
    block, with CLI overrides layered on top (mirrors `corners.build_matrix`'s
    override shape).

    Unlike the PVT matrix, this is not a cross product: a Monte Carlo
    campaign samples at one (corner, temp, supply) point, varying only the
    RNG seed across trials 1..N (seed = seed_base + trial - 1, so it is
    reproducible and each campaign's first trial is easy to re-derive by
    hand).
    """
    mc_cfg = manifest.get("monte_carlo")
    if mc_cfg is None:
        raise McConfigError(
            "this manifest has no `monte_carlo` block -- see sim/harness/README.md's "
            "Monte Carlo section for the schema"
        )

    corner = corner_override if corner_override is not None else mc_cfg["corner"]
    if corner not in valid_process_corners:
        raise McConfigError(
            f"corner {corner!r} is not in sim/pdk.json's process_corners {valid_process_corners}"
        )

    trials = trials_override if trials_override is not None else mc_cfg["trials"]
    if trials < 1:
        raise McConfigError(f"trials must be >= 1, got {trials}")

    seed_base = seed_base_override if seed_base_override is not None else mc_cfg.get("seed_base", 1)
    temp_c = temp_override if temp_override is not None else mc_cfg["temp_c"]
    supply_v = supply_override if supply_override is not None else mc_cfg["supply_v"]
    mismatch = mc_cfg.get("mismatch", True) if mismatch_override is None else mismatch_override
    process = mc_cfg.get("process", True) if process_override is None else process_override

    if not mismatch and not process:
        raise McConfigError(
            "at least one of mismatch/process must be enabled -- with both off, "
            "every trial only differs by an RNG seed nothing in the netlist reads, "
            "which is a repeated point, not a Monte Carlo trial"
        )

    return [
        McTrial(
            trial=i,
            seed=seed_base + i - 1,
            corner=corner,
            temp_c=float(temp_c),
            supply_v=float(supply_v),
            mismatch=mismatch,
            process=process,
        )
        for i in range(1, trials + 1)
    ]
