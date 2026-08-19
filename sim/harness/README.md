# sim/harness/ — testbench manifest format

`sim/run_corners.py <slug>` runs the experiment declared at
`sim/<slug>/testbench/tb.json` across a PVT (process/voltage/temperature)
point matrix and writes an append-only evidence record — see `sim/README.md`
for the record schema and directory conventions this package writes into.

Stdlib only, no virtualenv. Package layout:

```
sim/harness/
  pdk.py         resolve the sky130 PDK install (PDK_ROOT/PDK, volare, sim/pdk.json)
  corners.py     build the PVT point matrix from a manifest + CLI overrides
  montecarlo.py  build the Monte Carlo trial matrix from a manifest + CLI overrides
  runner.py      xschem-netlist once, patch per point/trial, run ngspice, judge pass/fail
  report.py      render the append-only records/<record-id>.md evidence record
  cli.py         argparse glue: --check-env / --print-env / --list / <slug> [--mc]
```

This is deliberately scoped down from `2AMLogic/gf180-pll`'s own
`sim/harness/` (source commit `3e3814c11ce6f0781ecfbefb0d109981c4e5eb21`,
which this package's shape is adapted from per this repo's `CLAUDE.md`
harness-bootstrap rule): gf180-pll's package carries PLL-specific
derived-measurement modules (lock detection, jitter reduction, divider-ratio
checks, ...) because it has a real PLL schematic to measure. sky130-pll does
not yet — issue #2 stands up the harness plumbing only, unblocked of spec
ratification (#1). Measurement-specific reduction modules are added by later
issues once there is a PLL netlist.

## `tb.json` manifest schema

```json
{
  "schema": "sky130-pll.harness.tb/1",
  "claim": "one-sentence statement of what this experiment substantiates",
  "schematic": "tb_foo.sch",
  "corner_pattern": "regex, one capture group ending right before the corner token",
  "supply_pattern": "regex, one capture group ending right before the supply value",
  "process_corners": ["tt", "ss", "ff"],
  "temps_c": [-40, 27, 125],
  "supply_nominal": 1.8,
  "supply_tolerance": 0.1,
  "methodology_note": "one clause on what this experiment's DUT is (and is not), spliced into the record's per-point criterion line",
  "analysis": "the ngspice analysis this DUT's schematic runs, e.g. \"DC operating point (`.op`)\" or \"transient (`.tran 50p 200n`)\""
}
```

- **`schematic`** — path relative to the manifest's own `testbench/`
  directory. Netlisted once per run via `xschem -x -n -s -q --rcfile
  sim/xschemrc`; the corner/temperature/supply axes are then applied by
  regex-patching the netlisted text, not by re-netlisting per point (the DUT
  topology does not change across a PVT sweep).
- **`corner_pattern` / `supply_pattern`** — each a Python regex with exactly
  one capturing group: the text immediately *before* the value the harness
  overwrites. `runner.patch_netlist` replaces `group(1) + <new value>` for
  every match. This keeps the harness generic — it never needs to understand
  the DUT's topology, only where in its own netlisted text the process
  corner (a `.lib ... <corner>` line) and the supply (a voltage source's DC
  value) live. Temperature is not pattern-based: a `.temp <T>` card is always
  inserted immediately before the netlist's final, standalone `.end` line.
- **`process_corners`** — must be a subset of `sim/pdk.json`'s
  `process_corners` list (the corners the installed sky130 PDK's combined
  ngspice library actually defines `.lib` sections for).
- **`temps_c`** / **`supply_nominal`** / **`supply_tolerance`** — the default
  PVT grid for this experiment. Supply points are
  `nominal*(1-tol), nominal, nominal*(1+tol)` (tolerance `0` collapses to a
  single nominal point). A CLI override (`--corners`/`--temps`/
  `--supply-tol`) narrows this for a fast pass, and requires
  `--subset-reason` to be recorded when writing evidence — see
  `sim/README.md`'s subset-justification rule.
- **`methodology_note`** / **`analysis`** — free text, spliced verbatim into
  the record's "Methodology / criteria / limitations" line
  (`report.render`/`render_mc`) so that line describes *this* manifest's DUT
  and analysis type rather than a hardcoded sentence. A Monte Carlo campaign
  may override either under its own `monte_carlo` block (falling back to the
  top-level value if absent). Optional — a manifest that omits either falls
  back to a `(no ... stated in manifest)` placeholder rather than failing.

## Running

```sh
python3 sim/run_corners.py --check-env        # PDK + ngspice + xschem availability
python3 sim/run_corners.py --print-env        # `export PDK_ROOT=... PDK=...` for eval
python3 sim/run_corners.py --list             # known experiment slugs
python3 sim/run_corners.py pdk-smoke          # full manifest grid, writes a record
python3 sim/run_corners.py pdk-smoke --no-write   # run, print pass/fail, write nothing
python3 sim/run_corners.py pdk-smoke \
  --corners tt --temps 27 --supply-tol 0 \
  --subset-reason "fast selftest pass, not a design claim"
```

Per-point pass/fail is a **plumbing** criterion, not a design measurement:
ngspice must exit 0, print its analysis-completion marker, and emit no
`Error:` line for that PVT point's patched netlist. A campaign that measures
an actual circuit quantity extends the manifest with a `measure` block (see
below), which layers a stricter *measurement* criterion on top of the same
plumbing check.

## Measurement campaigns (`measure` manifest block)

Issue #52 closed the gap this package's own module docstring used to flag:
"sky130-pll does not yet [carry PLL-specific measurement modules] — issue #2
stands up the harness plumbing only". `sim/harness/measure.py` is that
measurement layer. A manifest that declares a top-level `measure` block hands
the *analysis itself* to the harness — the testbench schematic carries no
`.tran` card of its own (see `sim/pll-lock/testbench/tb_pll_lock.sch` and
`sim/vco/testbench/tb_vco.sch` for the pattern) — so the transient window,
waveform capture, and reduction are all manifest knobs rather than schematic
edits:

```json
{
  "measure": {
    "node": "CLK",
    "tran_step": "200p",
    "tran_stop": "3u",
    "timeout_s": 1800,
    "threshold_frac": 0.5,
    "hysteresis_frac": 0.15,
    "settle_from": "0",
    "min_edges": 4,
    "ic": ["v(xxxvco.ring0)=0"],
    "uic": false,
    "lock": {
      "target_hz": 250000000,
      "tolerance_frac": 0.05,
      "window_cycles": 20,
      "min_hold_cycles": 20
    },
    "require_lock": false,
    "sweep": {"source": "V2", "quantity": "VCTRL", "values": [0.6, 0.8, 1.0]},
    "require_oscillation": false,
    "min_oscillating_points": 2,
    "extra_nodes": []
  }
}
```

- **`node`** — the node measured for frequency/duty/lock (`v(<node>)`, e.g.
  `CLK` for a top-level pin, or a hierarchical path like `xxxtop.vctrl` for an
  internal node — see the caveat below on hierarchical vector names).
- **`tran_step`/`tran_stop`** — the injected `tran` card's arguments, as SPICE
  time literals (`200p`, `3u`, `40u`, ...). This is the knob that makes a
  lock-capable window a manifest edit instead of a schematic edit.
- **`timeout_s`** — per-point ngspice wall-clock budget (default 3600). A
  closed-loop cold-start transient is far more expensive to simulate than a
  short plumbing window; a point that blows this budget is recorded as a
  timed-out FAIL, not a crashed harness run.
- **`threshold_frac`/`hysteresis_frac`** — the crossing threshold and
  hysteresis band, both **fractions of that PVT point's own supply** (so the
  same manifest reads correctly at 1.62 V and 1.98 V, not just the nominal
  rail).
- **`settle_from`** — discard rising edges before this SPICE time literal
  when computing frequency/duty (startup transient exclusion for an unswept
  oscillation measurement).
- **`min_edges`** — how many post-settle rising edges must be observed for a
  point to count as "oscillating" at all.
- **`ic`/`uic`** — `.ic` cards and the `tran ... uic` flag, for a DUT (like a
  free-running ring oscillator) whose noiseless DC operating point is an
  unstable equilibrium a simulator can otherwise sit on indefinitely.
- **`lock`** — when present, the point is judged by the sliding-window lock
  criterion (see `sim/harness/measure.py`'s module docstring for the exact
  definition) instead of plain oscillation. `require_lock` (default `false`)
  controls whether a point that never locks FAILs the point or is recorded as
  data ("no lock within this window, at this corner" is itself a finding a
  v1 canary campaign may want to *record*, not paper over — see
  `sim/pll-lock/testbench/tb.json`).
- **`sweep`** — when present, one ngspice invocation per PVT point runs
  `len(values)` transients, altering `source`'s DC value between each (e.g.
  a VCO's `VCTRL` bias) and dumping one waveform per swept value. Used by
  `sim/vco`'s frequency-vs-VCTRL characterization. `require_oscillation`
  (only meaningful when `sweep` is absent) and `min_oscillating_points`
  (meaningful when `sweep` is present) control whether a dead point/dead
  swept value fails the whole point outright or is recorded as
  characterization data — a campaign that deliberately sweeps past the edge
  of a tuning range wants the latter.
- **`extra_nodes`** — additional `v(...)` vectors saved and dumped alongside
  `node`, for diagnostic visibility. **Caveat**: a node's ngspice vector name
  after hierarchical flattening does not always match the schematic label
  syntax that works fine for `save`/`display` post-run introspection — an
  internal node one level down a hierarchy (e.g. the loop filter's `VCTRL`,
  which is internal to `design/top/top.sch`'s `top` subckt, itself
  instantiated as `XXXTOP`) may need to be discovered empirically (netlist by
  hand, `save all` + `tran` + `run` + `display` in a scratch `.control`
  block, per this section) rather than assumed from the schematic's own net
  label. Getting it wrong surfaces as `Error: no such vector <name>` and
  aborts that point's `wrdata` — a hard failure, not a silent one, but it
  costs a wasted run to discover. `sim/pll-lock`'s manifest does not declare
  `extra_nodes` for this reason: `CLK` (a genuine top-level pin) is the only
  node it needs for frequency/duty/lock, and the VCTRL diagnostic was not
  worth chasing for issue #52's scope.

Every measurement record renders a stricter criterion than the plain
plumbing table: "ngspice ran to completion" is necessary but not
sufficient — see `report._render_measurement_criteria` for the exact
wording a record carries, and `sim/pll-lock/records/` /
`sim/vco/records/` for real examples.

### What `measure` deliberately does not cover

Loop bandwidth and phase margin are **not** extracted by this reducer —
they are open-loop quantities, and pulling them out of a closed-loop
transient needs either a broken-loop AC testbench or a step-response fit
whose accuracy is dominated by the fit's own assumptions, neither of which
this transient reducer attempts. See `sim/harness/measure.py`'s module
docstring for the full scoping rationale (issue #52 explicitly allows
deferring this to a dedicated AC/linearized-model testbench).

## Monte Carlo (`--mc`)

`sim/run_corners.py <slug> --mc` runs a **statistical variation** campaign
instead of a PVT sweep: many trials at one fixed (corner, temperature,
supply) point, each drawing a fresh random sample of sky130's device-level
process/mismatch variation, rather than many fixed named PVT points. This
stands up the *capability* generically (issue #20); it is not itself a PLL
statistical-spec measurement — see `sim/README.md`'s Monte Carlo section for
what a record produced this way can and cannot support.

```sh
python3 sim/run_corners.py pdk-smoke --mc                  # manifest's monte_carlo config, writes a record
python3 sim/run_corners.py pdk-smoke --mc --no-write       # run, print pass/fail, write nothing
python3 sim/run_corners.py pdk-smoke --mc \
  --mc-trials 3 --subset-reason "fast selftest pass, not a design claim"
```

### Sampling mechanism

sky130's own ngspice models already wire up Monte Carlo sampling via two
`.param` switches that gate `agauss()`/`gauss()` calls inside the shipped
device models (e.g. `sky130_fd_pr__res_generic_po`'s `tc1`/`tc2` slope params
in `libs.tech/ngspice/r+c.mrp1monte.spice`, and the same convention wired
into the BSIM4 device models):

- **`MC_PR_SWITCH`** — die-to-die / lot-to-lot *process* variation. Defined
  (default `0`) in every corner's `.lib` section, not tied to a particular
  corner name. One draw applies uniformly to every instance of a primitive in
  the netlist (correlated across instances).
- **`MC_MM_SWITCH`** — within-die device *mismatch*. The `<corner>_mm` `.lib`
  sections (`tt_mm`, `ss_mm`, `ff_mm`, ...) default this to `1`; the plain
  sections (`tt`, `ss`, `ff`, ...) default it to `0`. Each device instance
  gets its own independent draw.

`sim/harness/runner.patch_netlist_mc` selects the trial's `.lib` section
(`<corner>_mm` when mismatch sampling is enabled, else the plain corner),
overrides both `.param`s to the trial's `mismatch`/`process` settings, and
injects a per-trial `.options seed=<N>` card before `.end` — ngspice's global
RNG seed, which every `agauss()`/`gauss()` call in the included models reads
from. This was verified empirically against this repo's pinned sky130
install: a fixed seed reproduces the same device draw exactly; a different
seed draws differently. See `sim/harness/montecarlo.py`'s module docstring
for the verification detail and `sim/pdk-smoke/records/` for the first
harness self-test record produced this way.

### `monte_carlo` manifest block

```json
{
  "monte_carlo": {
    "claim": "one-sentence statement of what this MC campaign substantiates",
    "corner": "tt",
    "temp_c": 27,
    "supply_v": 1.8,
    "mismatch": true,
    "process": true,
    "trials": 10,
    "seed_base": 1
  }
}
```

- **`corner`** — the base process corner (must be a member of `sim/pdk.json`'s
  `process_corners`, same rule as PVT's `process_corners`). The `_mm` suffix
  is applied automatically when `mismatch` is on; do not include it here.
- **`temp_c`** / **`supply_v`** — the single fixed PVT point every trial in
  this campaign runs at (a Monte Carlo campaign resamples device variation at
  one point; it does not cross a PVT grid — run separate `--mc` invocations,
  or a future PVT × MC campaign type, if multiple PVT points each need their
  own trial set).
- **`mismatch`** / **`process`** — whether `MC_MM_SWITCH`/`MC_PR_SWITCH` are
  on for this campaign. At least one must be `true`: with both off, every
  trial is identical to a plain PVT point run N times, which is not a Monte
  Carlo campaign.
- **`trials`** — how many independent draws to run.
- **`seed_base`** — the first trial's ngspice RNG seed; trial *i*'s seed is
  `seed_base + i - 1`, so seeds are reproducible and sequential.
- **`claim`** — used instead of the manifest's top-level `claim` for `--mc`
  records, since an MC campaign's claim (what does this trial matrix
  substantiate) is typically distinct from its PVT sibling's.

`--mc-corner` / `--mc-trials` / `--mc-seed-base` / `--mc-temp` / `--mc-supply`
/ `--mc-mismatch` / `--no-mc-mismatch` / `--mc-process` / `--no-mc-process`
override the manifest's `monte_carlo` block the same way `--corners`/
`--temps`/`--supply-tol` override the PVT grid, and require `--subset-reason`
when combined with `--write` — see `sim/README.md`'s subset-justification
rule.

Per-trial pass/fail is the same **plumbing** criterion as the PVT matrix:
ngspice must exit 0, print its analysis-completion marker, and emit no
`Error:` line. It proves the sampling mechanism runs to completion, seed by
seed — it is not, by itself, a claim about any circuit quantity's statistical
distribution landing inside a spec limit. A campaign that measures an actual
circuit quantity's spread (once a PLL schematic exists and a targeted
statistical spec row is ratified) extends `runner.py`/`report.py` with its
own reduction over the per-trial results, the same way a future PVT
measurement campaign would.
