# DR-011: bounded feasibility plan for a proposed 500 MHz clock output

- **Status**: proposed. This record is a **plan**. It does **not** ratify or
  edit any spec row, authorizes no simulation, spend or circuit change, and
  claims no measured 500 MHz capability. Rows 2 and 14 stay **DRAFT**; row 9
  stays as ratified. See "Status notes".
- **Date**: 2026-10-19
- **Author**: Builder agent (issue #333)
- **Ratifies against / input to**: #333; input to a later interface-scope
  decision on whether a 500 MHz output belongs in v1
- **Supersedes**: none

One decision per record. The decision here is **how to find out, in bounded
stages, whether a 500 MHz output is feasible for this PLL**, and what must be
true before any stage may run. It does not decide whether 500 MHz is in scope.

## Context

A downstream consumer (a serializer needing a 500 MHz DDR bit clock for 1 Gb/s
per lane) asked whether a 500 MHz output is in scope. Its proposed interface:
500 MHz target (200 MHz fallback, 750 MHz stretch), duty 50 ± 2.5 %, jitter
at most 0.10 UI peak-to-peak per edge (100 ps), 1.8 V rail-to-rail CMOS,
integer-N from the reference.

Against `spec/target-spec.md`:

- **Row 2** (output band 10 – 200 MHz) is DRAFT, carried from the sibling port,
  and stated as not assumed to hold. 500 MHz is 2.5x above its top edge. The
  band is not measured capability in either direction.
- **Row 14** (duty 45 – 55 %) is DRAFT and owed a measurement; the requested
  ± 2.5 % is twice as tight.
- **Row 9** (period jitter ≤ 1.0 % of the period, RMS) is ratified (DR-006).
  It is unchanged by this record.
- **Rows 3/4** (reference 1 – 25 MHz, N = 4 – 64): 25 MHz x 20 = 500 MHz is
  inside the arithmetic range; whether the loop closes there is unevidenced.

On 2026-10-19 the operator chose to prepare a bounded feasibility plan building
on the tuning-range work already owed, and explicitly withheld authorization
for any campaign, spend, circuit work, numerical ratification or merge of
scope. The separate additional-output proposal #339 is independent;
interfaces are coordinated, neither is treated as approval of the other.

**Metric correction.** The original report compared "about 7.1 ps RMS"
(derived from a 100 ps peak-to-peak budget through a dual-Dirac factor of
14.07 at BER 1e-12) with row 9's 20 ps period RMS at 500 MHz, concluding a
roughly 2.8x shortfall. That arithmetic does not establish a capability gap or
an equivalent RMS limit: period (cycle) jitter and absolute time-interval error
(TIE) are different observables, related by the jitter spectrum, and the
dual-Dirac conversion assumes a Gaussian random component plus bounded
deterministic component that nothing here has measured. The 2.8x figure is
recorded as informative only and is not used below.

## Decision

**Adopt the following staged plan (proposed). No stage runs under this
record.** Each stage needs its own separately authorized campaign request
(Step 4 below) before any job is submitted or any cost incurred.

### Step 1 — Reuse existing evidence (inventory, at `173138f`)

| Topic | Evidence at `173138f` | Status for this question |
|---|---|---|
| VCO frequency vs. `VCTRL`, open loop | `sim/vco/records/20260904-163130-f3ae976.md` (45-point DR-003 grid; reports VCO output through roughly 1 GHz at upper `VCTRL` points); `sim/vco/records/20260819-131741-fe0e6df.md` (tt/27 °C/1.80 V: 510.9 MHz at `VCTRL` = 1.0 V); ngspice-tolerance audit legs `20260927-081603-25bc597.md` and `20260927-093607-25bc597.md` | **Open-loop oscillation only.** Shows a bare ring can oscillate near 500 MHz at some `VCTRL`. Says nothing about lock, the divider at that rate, output duty/levels at 500 MHz, or jitter. The tuning-range campaign that would ratify row 2 is still owed. |
| Divider top frequency | `sim/divider-fmax/testbench/fmax.json` exists; **no record** under `sim/divider-fmax/` | **Capability gap**: a bench with no record is not evidence. Divider-only records (`sim/divider*/records/`) use an ideal ~1.1 GHz input for N = 25 and prove division, not a maximum frequency. |
| Closed-loop lock | `sim/pll-lock/records/20260905-193322-0f1934d.md` (N = 25, 10 MHz reference, 250 MHz target); `sim/pll-lock-25mhz/records/20260904-152213-f00ce3e.md` (25 MHz band edge, single nominal point) | Evidence is at ≤ 250 MHz. The 25 MHz-reference record is a **recorded FAIL** (no oscillation, an early-harness result), and the 250 MHz grid record shows locks at only some corners. Neither supports a 500 MHz claim. |
| Closed-loop jitter | `sim/pll-lock-mc/records/*`; `sim/jitter-floor/records/*`; `sim/jitter-calibration/records/*` | Period jitter at ≤ 250 MHz, with a measured resolution floor. **No absolute-TIE reducer** is evidenced. |
| Output buffer duty/levels | `sim/clk-output/testbench/tb.json`, `sim/vco-buffered/testbench/` | Benches exist, **no records** for either. Depends on #232/#303/#304. Gap, not evidence. |
| Buffered-CLK to closed loop | #232 (output stage), #303, #304 (closed-loop sim/layout) | Open, not merged as capability. Not assumed deployed. |

Dependency map: Stage A needs the existing `sim/vco` bench and `sim/divider-fmax`
bench, with no unmerged dependency. Stage B needs the buffered `CLK` stage and
its closed-loop bench, so it depends on #232 → #303 → #304 (and `DR-008` for
the load). Stage C depends on Stage B results and on the owed tuning-range
campaign. The output node and load used by every stage must be consistent
with `DR-008` (provisional 1 pF characterization load) and `DR-009` (single
`CLK`, no phase output); neither is approval of 500 MHz.

Not duplicated here: the owed tuning-range campaign (row 2). Stage A is
defined as a sub-slice of it, not a second campaign.

### Step 2 — Measurement contract (defined before any job)

The contract below applies to every stage. Frequency, duty and the jitter
definitions are **proposed investigation inputs**, not ratified targets.

- **Ratio and reference**: default 25 MHz x N = 20 (500 MHz); a lower-reference
  point (for example 10 MHz x 50) is a named variant to separate divider
  limits from loop limits.
- **Output node and load**: buffered `CLK` pin into the `DR-008` 1 pF load.
  The raw VCO node is not the output (DR-009 gap 2).
- **PVT coverage**: supply 1.62 / 1.80 / 1.98 V (row 1), the DR-003 five
  process corners x −40 / 27 / 125 °C. Stages A and B use a named subset; the
  subset is stated in each campaign request.
- **Lock criterion**: reuse the harness lock criterion of
  `sim/pll-lock`, with window and tolerance restated for 500 MHz in the
  request. No new definition is invented here.
- **Settling window and observation duration**: settled when the lock criterion
  holds; observation must span enough output cycles that the statistic is
  resolvable above the measured harness floor (`sim/jitter-floor`). The exact
  cycle count is an input to the request, not fixed here.
- **Sampling resolution**: time step and dump grid chosen so that the
  reducer's floor, measured at 500 MHz, is at least several times below the
  quantity reported. If that cannot be met, the result is reported as
  unresolved, not as a pass.
- **Duty**: measured at a stated threshold (50 % of `VDD`) over the same
  window; 50 ± 2.5 % is a proposed threshold to report against, row 14 stays
  45 – 55 % DRAFT.
- **Period RMS (row 9 observable)**: standard deviation of single-cycle periods
  after lock, as the existing reducer computes it.
- **Consumer-edge TIE**: edge-time error against an ideal clock of the
  *locked mean* period, over the same edges, with a stated detrending
  (linear removal of phase drift, none of low-frequency wander beyond that),
  edge selection (all rising edges after lock) and population size. It is
  reported separately from period RMS. A peak-to-peak or BER-referred figure
  requires a stated statistical model (for example dual-Dirac) **and**
  evidence that its assumptions (Gaussian random part, bounded deterministic
  part) hold; absent that evidence the conversion is flagged **unsupported**
  and only the directly measured RMS and observed extremes are reported.
- **Unsupported conversions**: no conversion between period RMS and TIE, and
  no extrapolation to BER 1e-12 from a finite transient, is reported as a
  result in this plan's stages.

### Step 3 — Staged feasibility work (prospective; none authorized)

Screening is **not** ratification-grade evidence at any stage.

**Stage A — oscillator and divider screening.**
Matrix: tt corner at 1.80 V / 27 °C first, then the supply and temperature
extremes of the DR-003 set, `VCTRL` swept across the point(s) that bracket
500 MHz (reusing the `sim/vco` bench) and the `sim/divider-fmax` bench at
N = 20 and neighbours. Question: does a usable tuning range reaching 500 MHz
exist across process, and does the divider divide correctly at that rate?
Stop conditions: (1) no `VCTRL` within the allowed range yields ≥ 500 MHz
at the slow corner, or (2) the divider fails correct division at 500 MHz
across the screened corners, or (3) measurement invalid (reducer floor not
resolved, solver non-convergence flagged by the tolerance audit).
Any stop condition ends the plan and records the interface as not feasible
as designed.

**Stage B — closed loop and output buffer.**
Only if Stage A completes without a stop condition and #232/#303/#304 have
merged. Matrix: one closed-loop transient at the Stage-A-selected ratio with
the buffered `CLK` into the `DR-008` load at nominal PVT, then the DR-003
corner set at nominal supply/temperature. Observables: lock, duty, V_OH/V_OL,
period RMS and consumer-edge TIE as separately defined in Step 2. Stop
conditions: no lock inside the observation window; duty outside the stated
reporting band at nominal; reducer floor not resolved; any measurement flagged
invalid. A stop records the miss against the proposed interface.

**Stage C — full coverage.**
Only if Stage B is clean. The full 45-point PVT grid plus the mismatch Monte
Carlo already used by `sim/pll-lock-mc`, sized from Stage B results. Required
before any ratification proposal, and not described further here because its
matrix depends on Stage A/B outcomes.

### Step 4 — Estimate and bound execution

Costs and runtimes are **currently unmeasured**. This record does not invent a
budget. For each stage, the campaign request must state all of:

- existing job/bench reused, and the exact proposed matrix (corner x
  temperature x supply x ratio x `VCTRL` points);
- executor and tool-capability prerequisites (batch backend availability,
  harness support for a 500 MHz timestep and for the TIE reducer, the pinned
  `klt`/ngspice versions);
- expected runtime basis, citing a measured prior run of the same bench
  (for instance the 45-point `sim/vco` record), not an estimate from scaling;
- storage and compute charges, concurrency and per-job timeout, and a total
  stop limit.

Named unknowns today: per-job runtime of a 500 MHz closed-loop transient
(none recorded at this rate), the batch-fleet quote for Stage B/C, and the
size of the TIE reducer change. These are listed as missing measurements or
quotes, to be obtained before a request is raised.

### Step 5 — Return for a scope decision

Each stage's execution requires **a separate authorization gate**: a written
campaign request linked from #333 and approved by the operator. Only then may
jobs run (on the batch fleet; multi-corner grids are submitted as a `klt sim`
request, not hand-launched).

**Go / no-go criteria** (for the later scope decision, not for any stage):

- *Go* only on a reviewed evidence package showing, with the Step 2 contract:
  locked closed-loop operation at 500 MHz at the stated coverage, duty within
  the reporting band, and period RMS and consumer-edge TIE each resolved above
  the measured floor and each compared with its own requirement.
- *No-go / exclude* if Stage A or B hits a stop condition.
- *Redesign* if the failure is isolable (for example a divider limit or
  buffer duty) and a bounded change is identifiable.

**Fallback options**: exclude 500 MHz and tell the consumer to route it
elsewhere; accept the 200 MHz fallback point (the top edge of the DRAFT row 2
band, which is itself unevidenced); or redesign (a higher-speed divider, or a
different oscillator structure) under its own issue and DR.

## Alternatives considered

- **Run a screening simulation now.** Rejected: the 2026-10-19 ruling
  authorizes planning only. Revisit when a Step 4 request is approved.
- **Edit rows 2, 9 or 14 to a 500 MHz-compatible value.** Rejected: that would
  relax or extend a spec to fit a proposal without evidence. Rows change only
  by their own decision record on measured results.
- **Decide scope now from the open-loop VCO records.** Rejected: open-loop
  oscillation at some `VCTRL` is necessary, not sufficient (no divider, lock,
  duty or jitter evidence).
- **Accept the original 2.8x comparison as the gap.** Rejected: period RMS and
  absolute TIE are different observables, and the dual-Dirac conversion is
  unevidenced here.
- **Fold #339 (additional output) into this plan.** Rejected: independent
  proposal; interfaces are coordinated only.

## Consequences

- Fixes a measurement contract and stage structure so the owed tuning-range
  campaign can be sized once, with a 500 MHz slice defined.
- Constrains any future 500 MHz claim to a reviewed evidence package; an
  arithmetic frequency ratio or a nominal oscillator result does not settle it.
- Costs: adds a TIE reducer capability gap to the harness that does not exist
  today, and ties Stage B to the unmerged #232/#303/#304 chain.
- No spec row changes. Rows 2 and 14 remain DRAFT; row 9 remains ratified.

## Status notes

`proposed`. It takes effect only on operator acceptance through normal review.
Issue #333 stays open for the later interface-scope disposition. Re-check the
evidence table's commit pin (`173138f`) and the state of #232/#303/#304 when a
campaign request is raised; both can drift. The ratifying action for any
scope outcome is a separate decision record on reviewed evidence.
