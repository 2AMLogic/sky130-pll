# Stage A campaign request: oscillator and divider screening for a proposed 500 MHz output

- **Status**: proposed, **unexecuted**. This document authorizes nothing by
  itself: no simulation, batch job, spend, circuit change or spec edit. It is
  the "concrete bounded campaign request" that
  [DR-011](../spec/decision-records/DR-011-500mhz-feasibility-plan.md) Step 4
  requires before any stage may run.
- **Issue**: #333 (`Part of`, not `Closes`; the issue stays open for the later
  interface-scope disposition). Bench preparation for section 2.2 is #352
  (offline preparation only; nothing in it was simulated).
- **Plan it implements**: DR-011 Stage A (oscillator and divider screening).
  The measurement contract (ratio, output node and load, PVT coverage, lock
  criterion, period RMS versus consumer-edge TIE) is defined in DR-011 Step 2
  and is **cited, not redefined, here**. Stage A measures neither jitter
  observable.
- **Evidence pin**: `origin/main` at `e786d18` (the DR-011 pin, `173138f`, is
  older; the records cited below are unchanged between the two).
- **Out of scope**: Stage B (closed loop and output buffer, depends on
  #232 → #303 → #304) and Stage C (full coverage). Both are referenced only as
  out of scope. Rows 2, 9 and 14 of `spec/target-spec.md` are untouched; row 2
  and row 14 stay DRAFT, row 9 stays as ratified. No 500 MHz capability is
  claimed anywhere below.

## 1. Question Stage A asks

DR-011 Step 3: does a usable tuning range reaching 500 MHz exist across
process, and does the integer-N divider divide correctly at that rate?
Screening only: a pass is not ratification-grade evidence and settles nothing
about lock, duty at the output pin, or jitter.

## 2. Reused benches and exact proposed matrix

### 2.1 VCO tuning range: `sim/vco` (no bench change needed)

- Bench: `sim/vco/testbench/tb.json` (open-loop `design/vco/vco_ring5.sch`,
  `tran 50p 200n uic`, settle from 60 ns, one `ngspice` invocation per PVT
  point, `VCTRL` swept on source `V2`).
- Existing coverage to reuse, not repeat: record
  `sim/vco/records/20260904-163130-f3ae976.md`, 45 PVT points (5 process
  corners × 3 temperatures × 3 supplies, per the record's "Total points: 45")
  × 6 `VCTRL` values (0.8, 0.9, 1.0, 1.2, 1.4, 1.6 V) = **270 oscillation
  measurements**. The per-corner artefacts under
  `sim/vco/corners/20260904-163130-f3ae976/` hold 45 `.spice` decks and 45
  `.log` files plus `tb_vco.spice` (91 files).
- What the record already shows (read from its per-point table; open loop
  only): at every one of the 45 points the ring oscillates at all six `VCTRL`
  values, and the 500 MHz crossing lies between `VCTRL` = 0.9 V and 1.2 V at
  every point. Examples: the table's `ss | 27 | 1.62` row has 415 MHz at
  1.0 V and 583.5 MHz at 1.2 V; its `tt | 27 | 1.80` row has 510.9 MHz at
  1.0 V. The grid has **no point between 0.9 V and 1.0 V or between 1.0 V
  and 1.2 V**, so the crossing is bracketed but not located. Counting the
  record's 45 PASS rows at `VCTRL` = 1.0 V, 19 of 45 points are already
  ≥ 500 MHz there (crossing in 0.9 – 1.0 V); the other 26 cross in
  1.0 – 1.2 V.
- **Proposed new points** (a bench value change, which this request *names*
  and does not make): add `VCTRL` = 0.95, 1.05, 1.10 and 1.15 V to
  `measure.sweep.values`. The 0.95 V value is one global point that brackets
  the crossing at the 19 points where it lies in 0.9 – 1.0 V; 1.05 – 1.15 V
  bracket it at the 26 points where it lies in 1.0 – 1.2 V. That is 4 new
  values × 45 PVT points = **180 new oscillation measurements** (135 before
  0.95 V was added), still 45 `ngspice` invocations (one per PVT point),
  each now with 10 swept values. The existing 6-value record is reused
  as-is for the other 270. Total after the request: 10 × 45 = 450
  measurements, of which 180 are **unique new** ones. The bench sweeps its
  whole `measure.sweep.values` list in every invocation, so one invocation
  set of 45 would **recompute** the 270 values the existing record already
  holds as well as measuring the 180 new ones (450 simulated points per
  set); recomputation is not new evidence, and whether to avoid it (for
  example by sweeping only the four added values) is a bench-change and
  quote decision left to the operator gate, not made here.
- Caveat inherited from the bench (`tb.json` methodology note, citing
  `sim/tolerance-audit/README.md`): points above roughly 750 MHz carry a
  dump-grid bias of order 1 %; the proposed points (about 500 – 650 MHz at
  nominal) sit below that region, but a number quoted near 500 MHz must still
  be stated as a screening bound, not a measured value, and the tolerance
  audit's check applies.
- A reduced fallback if the full 45 is not authorized: the three process
  corners that bound the crossing at nominal supply and temperature
  (`ss`, `tt`, `ff` at 27 °C, 1.80 V; 3 PVT points × 4 new values = 12 new
  measurements). The operator picks the full or reduced matrix in the
  authorization gate (section 6); the reduced one cannot support the
  "slow corner" stop condition below across supply and temperature.

### 2.2 Divider top frequency: `sim/divider-fmax` (bench change needed)

- Bench: `sim/divider-fmax/testbench/fmax.json` (driver `sim/run_fmax.py`,
  `klt sim` batch route in `sim/harness/fmax_klt.py`). Declared moduli are
  **N = 4, 5, 25, 63, 64**. Its search band is **800 – 2600 MHz** on the grid
  of 25 MHz, coarse stride 8, i.e. 73 grid points with 10 coarse probes per
  cell before refinement.
- **Mismatch with Stage A, stated, not assumed away** (as of `origin/main`
  `7d20210`):
  1. `fmax.json` has **no N = 20** modulus. The plan's default ratio is
     25 MHz × 20 = 500 MHz (DR-011 Step 2).
  2. The divider's `CLK` input is the VCO output. At N = 20 and a 500 MHz
     output the input to be screened is **500 MHz**, which is **below**
     `fmax.json`'s `f_min_hz` of 800 MHz. A pass there reports "highest
     passing grid probe in 800 – 2600 MHz" and says nothing about 500 MHz.
     Lowering the bound alone would not fix this: the coarse stage visits
     every 8th grid point, so a 500 MHz probe is not guaranteed to be among
     them.
  3. **No record exists** under `sim/divider-fmax/` (the directory holds only
     `testbench/`). See section 4 for the dated, non-record observations
     reported on #244.
- **Prepared by #352 (offline, unexecuted)**:
  - `sim/divider-n20/testbench/{tb_divider_n20.sch,tb.json}`: the fixed
    frequency N = 20 bench. `NSEL[5:0]` carries N − 1 in plain binary
    (`design/divider/DESIGN.md`), so N = 20 is `010011` (19), not `010100`
    (which would be N = 21); an offline test decodes the schematic's straps
    and checks N = 20, with a wrong-strap negative control. The schematic
    has not been netlisted (that needs `klt netlist`/xschem and the PDK) and
    its tb.json has not been simulated; both remain outstanding.
  - `sim/divider-fmax/testbench/fmax-stage-a-500mhz.json`: a **separate**
    Stage A configuration, additive to `fmax.json` (which is unchanged, as
    are #244's declared defaults and every `records/` directory). It declares
    N = 20 only, a 400 – 2600 MHz grid at 25 MHz resolution (89 points,
    coarse stride 8) and `mandatory_probes_hz: [500e6]`. 500 MHz is grid
    index 4, **not** a coarse probe (coarse probes are 400, 600, …, 2600
    MHz), so the driver now schedules it explicitly in stage 1 of every
    cell and reports its verdict apart from the boundary. A FAIL
    (completed waveform misses the per-period criterion) and an INCONCLUSIVE
    (invalid run: simulator trouble, truncated or missing waveform) are
    reported distinctly; neither, nor a probe that never ran, is a pass.
    Running both manifests would be two characterization campaigns; this
    configuration is meant to be the screening request, not an addition to
    the full #244 grid.
- **Mapping choice for the operator (section 6):**
  - *Option M1, existing moduli, edit `fmax.json`*: lower `search.f_min_hz`
    to 400 MHz and keep N = 4, 5, 25, 63, 64. N = 20 would be inferred from
    the bracketing even-path moduli N = 4 and N = 64 and is **not tested**
    (the bench's own note says "untested moduli are NOT claimed to share
    these bounds"). It also edits #244's manifest and does not guarantee a
    500 MHz probe. Not prepared. 225 cells.
  - *Option M2, N = 20 through the prepared Stage A configuration*:
    45 cells (1 modulus × 45 PVT). Recommended for approval, because the
    ratio the plan names is N = 20 and M1 leaves it as an inference. It
    needs the reviewed #352 files merged and the section 4 unknowns settled.
- Probe counts for M2 (derived from the manifest; `--dry-run` prints them and
  submits nothing): stage 1 is 12 coarse probes plus the mandatory 500 MHz
  probe = **13 per cell**, 45 × 13 = **585** planned stage-1 probes; stage 2
  adds at most 7 probes per cell (every grid point strictly inside the
  lowest coarse-or-mandatory pass-to-fail interval, the widest of which is
  7 points), so at most 315 more. The planned-probe upper bound is 900; it
  is a bound, not a forecast, and stage 2 depends on where each cell's
  first pass-to-fail transition falls. (For M1: 225 cells × 12 coarse =
  2700 stage-1 probes in the 400 – 2600 MHz grid, not a 500 MHz guarantee.)
- Unique versus recomputed work: every probe above is a distinct
  (modulus, PVT point, frequency) measurement not present in any existing
  record, so there is no recomputed share for the divider bench. (This is
  unlike the VCO sweep in section 2.1.)
- The `klt sim` batch route groups one modulus and one supply per request
  with every probe frequency as its own DUT copy and the process ×
  temperature matrix as `klt sim` corners (`sim/harness/fmax_klt.py` module
  docstring). For M2 that is 1 modulus × 3 supplies = **3 groups** in
  stage 1 (13 DUT copies each) and up to 3 more in stage 2 (up to 7 copies
  each); M1 would be 5 × 3 = 15 per stage. Whether the batch route accepts
  these group sizes is unverified (section 4).

## 3. Prerequisites (named, none assumed met)

- **Execution route**: multi-corner and probe-grid work is submitted as
  `klt sim` requests to the batch fleet (`KLT_SIM_BACKEND=batch`; outputs
  return into the `-o` report, job id in `environment.remote`). It is **not**
  hand-launched `ngspice` loops on a dispatch worker. If a batch submit
  fails, the failure is reported; the grid is not run locally.
- **Pinned tools**: `klt` (`klayout-tools==0.7.0` per the repository's
  headless audit wrapper) and the `ngspice` and PDK versions that produced
  the reused records (ngspice-46 and `sky130A` per
  `sim/vco/records/20260904-163130-f3ae976.md` provenance); the request
  must restate the pins it will run under and note any difference from the
  reused records.
- **Divider-fmax capability gap**: the bench has never produced a record
  (section 2.2). A first run is therefore also the first validation of the
  Fmax driver and its batch adapter; a driver defect is a possible
  outcome, and it is a stop condition below, not a pass or a fail of the
  divider.
- **Bench changes the request depends on** (named only; each is filed and
  reviewed separately, none is made by this document): `sim/vco` sweep
  values (four added), and either `fmax.json` `search.f_min_hz` (M1) or, for
  option M2, the #352 N = 20 testbench and Stage A configuration (prepared,
  pending review).
- **Not required at Stage A**: the absolute-TIE reducer, the buffered `CLK`
  stage, and #232/#303/#304. These gate Stage B only.

## 4. Runtime and cost basis

No figure below is a budget.

- **Cited, measured**: the reused 45-point `sim/vco` record
  (`sim/vco/records/20260904-163130-f3ae976.md`) was produced with a
  per-point timeout of 3600 s declared in `tb.json` (`measure.timeout_s`);
  the declared timeout is a **limit**, not a measured runtime. The record's
  own measured per-point runtime, if any, must be read from the per-corner
  `.log` files under `sim/vco/corners/20260904-163130-f3ae976/` and cited
  by file before the request is raised; this document does not state one
  because none was extracted.
- **Named unknowns** (each to be obtained before the operator is asked):

  | Unknown | Measured or quoted by | Needed for |
  |---|---|---|
  | Per-point runtime of the 10-value `sim/vco` sweep | read from the reused record's corner logs, or a single-point probe run if the operator authorizes one | Stage A VCO compute estimate |
  | Per-probe and per-group runtime of the divider Fmax transient at 400 – 800 MHz input and N = 20 (M1: N = 4 – 64) | no record exists (section 2.2); the dated #244 observations below are not a quote | Stage A divider compute estimate |
  | Batch-fleet compute quote per group | fleet operator or the fleet's published rate | Stage A compute charge |
  | Storage charge for returned waveforms | batch backend | Stage A storage charge |
  | Whether the batch route accepts the group sizes in section 2.2 (DUT copies per group) | a dry run (`python3 sim/run_fmax.py divider-fmax --dry-run`, which submits nothing) | feasibility of the grouping |

- **Dated observations reported on #244 (2026-10-10, not a record)**: the
  comment of 2026-10-10T06:13Z (issuecomment-6094540228) reports a one-cell
  smoke through the batch route (`--no-write`, 5 batch jobs, N = 4, tt,
  27 °C, 1.80 V: BRACKETED, 2100 MHz pass / 2125 MHz fail) and a partial
  full-grid attempt (04:50 – 06:15 UTC) in which 4 of about 45 stage-1
  jobs were collected in about 85 min, 614 – 1948 s each, other
  submissions meeting `fleet at capacity` retries, stage 2 never reached,
  and collected reports carrying `runner_compatibility: mismatch` (fleet
  runner klt 0.5.0 against client 0.7.0). These are a single day's
  reported observations of a different grid (N = 4 – 64, 800 – 2600 MHz).
  They are **not** a complete or valid record, **not** current backend
  capacity, **not** a runtime estimate for this request and **not** a
  quote. No committed record exists, the cited logs were not re-read by
  this document's preparation, and no fresh measurement was made.
- A dry run that only plans (no jobs submitted, no spend) is the one
  measurement this request proposes to do *before* authorization, and it is
  itself noted as needing the operator's go-ahead if the repository's
  rules treat any planning run as a sim action.

## 5. Stop conditions and execution limits

Stop conditions are copied from DR-011 Stage A; any one ends the stage and
records the interface as not feasible as designed (they are not relaxed here
to make results pass):

1. No `VCTRL` within the allowed range yields ≥ 500 MHz at the **slow
   corner** (the `ss` corner at the slow supply and temperature points of
   the screened set; with the reused record, `ss`, −40 °C, 1.62 V reaches
   691.3 MHz at `VCTRL` = 1.6 V, so this condition is *testable*, not
   pre-decided). Adding the 0.95 V point to the matrix does not change
   this condition or its threshold.
2. The divider fails correct division at 500 MHz across the screened
   corners.
3. Measurement invalid: the reducer's floor is not resolved at the stated
   frequency (`sim/jitter-floor`), solver non-convergence is flagged by the
   tolerance audit, or the Fmax driver itself misbehaves (for example a
   probe-window cut error in the batch adapter). An invalid run is reported
   as unresolved, never as a pass.

Execution limits (to be filled with numbers by the operator at the gate,
each bounded; proposed defaults are marked and are **proposals**):

| Limit | Value |
|---|---|
| Concurrency | proposed: at most the fleet's default per-request width; no more than 2 local processes on any dispatch worker (a debug single point only) |
| Per-job timeout | proposed: the bench's own value (`sim/vco` 3600 s per point; `fmax.json` 1800 s per probe) |
| Total stop limit | **unfilled**: needs the section 4 quote; the operator sets it |
| Retry policy | no automatic re-run of a failed group beyond one; a second failure is reported |

## 6. Authorization gate (operator only)

This request is **not** an authorization. Execution of Stage A requires the
operator's explicit, written approval recorded on #333, naming:

- [ ] VCO matrix: full 45 PVT points × 4 new `VCTRL` values (180 new
      measurements) / reduced 3-point fallback (12 new measurements)
- [ ] Divider mapping: M1 (edit `fmax.json`, existing moduli, 225 cells) /
      M2 (prepared N = 20 Stage A configuration, 45 cells, 13 planned
      stage-1 probes each; needs the #352 files reviewed and merged first)
- [ ] The bench changes in section 3 reviewed and merged (the VCO sweep
      change is still unfiled and unmade; the N = 20 files are #352)
- [ ] Section 4 unknowns measured or quoted, and a total stop limit set
- [ ] Execution on the batch fleet via `klt sim` (no local grid)

Approval to *plan* (the 2026-10-19 ruling) does not satisfy this gate.
Stage B and Stage C each need their own separate request after Stage A
results are reviewed.

## 7. What a result will and will not be allowed to say

- A clean Stage A means only that screening hit no stop condition. It is
  written up as a screening record under `sim/` with the usual PVT detail,
  and it names itself as not ratification-grade.
- It does not edit rows 2, 9 or 14, does not claim 500 MHz capability, and
  does not decide scope. The interface-scope disposition (accept, exclude or
  redesign) stays an operator decision on a later reviewed evidence package.
- Period RMS and consumer-edge TIE are not reported by Stage A and are not
  converted into one another; see DR-011 Step 2.
