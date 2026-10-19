# Proposal: quarter-cycle phase output vs. multiplied-clock output for v1

- **Status**: proposal, for operator review. Not approved, not ratified. No
  design, simulation or spec-number change accompanies it.
- **Issue**: #339 (follow-on to #332, option 2 of the operator's 2026-10-19
  response). Decision record: `spec/decision-records/DR-010-phase-or-multiplied-output-proposal.md`.
- **Scope of the ruling this answers**: a request for this proposal. It does not
  select a topology, ratify a numeric target, approve implementation, authorize
  simulation spend, or authorize merge. `DR-009` is kept as history; its
  single-output default is the rejected option, not the accepted one.

Everything below is **analysis from the committed design notes and records**
unless a sentence cites a `sim/` record. Where a quantity is unknown it is
marked *unknown*; where a number is a suggestion it is marked *proposed*. No
accepted limit is invented here.

## 1. What the consumer needs (generic)

A downstream block uses `CLK` as a system clock and needs a second clock a
quarter period later than `CLK`, today derived with a delay element
(`DR-009` Context, gap 1). Recorded operating points: 25 MHz and 50 MHz
output, 100 MHz stretch (`DR-009` gap 3). The 500 MHz request in #333 is a
separate, unanswered decision and is **not** part of this proposal.

A delay element gives T/4 only at the one frequency and PVT point it was
tuned for. The need is therefore best read as "a quarter-cycle relationship
that tracks the output period across the band", which is what the two options
below are measured against.

## 2. Facts about the present design that bound the options

- The VCO is a **5-stage single-ended current-starved ring**
  (`design/vco/DESIGN.md`). With stage delay t_d, T = 10·t_d. The ring offers
  10 phases (5 taps and their inversions) spaced **T/10 = 36°** apart. 90° is
  2.5 stage delays: it is **not on the tap grid**. The nearest taps are 72° and
  108°, an 18° (T/20) error, and an odd-stage ring cannot produce an exact
  quadrature pair from taps at all.
- `CLK` is the output of a two-inverter buffer fed from the VCO node
  `VCOCLK`; the feedback divider is on `VCOCLK` (`DR-008`, `design/top/DESIGN.md`).
- The feedback divider is a synchronous 6-bit down-counter, N = 4 – 64
  (`design/divider/DESIGN.md`, row 4 DRAFT).
- Measured tuning (`sim/vco` record `20260819-131741-fe0e6df`, 45-point
  `20260904-163130-f3ae976`; Kvco 692 – 1751 MHz/V per `DR-006`) comfortably
  covers hundreds of MHz at `tt`; the **low end** (tens of MHz) is *unknown* —
  the design notes record the loop failing to complete cycles below about
  VCTRL = 0.8 V (~145 MHz, informal). This is the open row-2 question, not a
  new one.
- Rows 2, 14, 15 are DRAFT. The loaded-output evidence owed by `DR-008`
  (#232, #303, #304) is not yet complete: `sim/clk-output` has a testbench and
  no committed record.
- Row 9 (ratified, ≤ 1.0 % RMS period jitter) currently has a **recorded miss**
  (1.58 – 3.07 % on 3 locked of 5 draws, `sim/pll-lock-mc`). Nothing here
  changes that bound or that record.

## 3. The options

### Option P — quarter-cycle phase output (`CLK` + `CLK90`)

Consumer-visible contract (proposed): `CLK90` lags `CLK` by T/4 across the
output band; both have the same loading rule as `DR-008`.

Two ways to make it:

- **P1, direct, from the existing ring.** Tap two ring nodes or add a delay
  stage. *Rejected on analysis*: no exact 90° tap exists (§2); a delay-based
  version is what the consumer already does and has the same PVT drift; an
  even-stage or differential ring that does have 45°/90° taps is a new VCO
  that discards every committed `sim/vco*`, jitter and lock record.
- **P2, quadrature divider from a 2x VCO.** Run the VCO at 2·f_out and derive
  `CLK` and `CLK90` from an I/Q ÷2 (two flip-flops in a Johnson-style
  arrangement) clocked on opposite edges of the 2x clock. The quarter-cycle
  relationship is then **one half-period of the 2x clock by construction**,
  independent of ring tap position and tracking frequency automatically.

### Option M — multiplied-clock output (`CLK` + exported 2x or 4x)

Export the VCO-rate clock (or a 4x clock) in addition to `CLK`. Consumer
contract (proposed): `CLK2X`/`CLK4X` is phase-locked to `CLK` with an edge
alignment relationship that is itself *unknown* until defined and measured.

- The consumer still has to build its quarter-cycle clock: with 2x it gets
  edges at T/2, not T/4, so a 90° clock needs a further divider with its own
  startup ambiguity; with 4x it gets T/4 edges directly but must run the
  full-rate clock tree.
- A 4x export at the 100 MHz stretch point is 400 MHz and 800 MHz at the 200 MHz
  band edge, past what the 1-pF output stage and the ring's jitter have been
  evaluated at; the exported clock's duty cycle is the raw ring duty, not a
  divided 50 %.
- The exported fast clock needs its own buffer and load contract (another
  `DR-008`-style 1 pF characterization), and the extra distribution is
  consumer-visible power and noise.

## 4. Comparison

| Aspect | P1 direct taps | **P2 2x VCO + I/Q ÷2** | M2 export 2x | M4 export 4x |
|---|---|---|---|---|
| Exact T/4 relationship | no (18° grid error) | **yes, by construction** | no (T/2 edges) | yes, consumer-side |
| Timing work left to consumer | none claimed, but wrong phase | none | derive 90° itself | distribute 4x clock |
| VCO / ring | unchanged | **unchanged topology**, runs 2x faster | 2x faster | 4x faster |
| Divider (counter) | unchanged | unchanged if feedback is taken from `CLK` (after ÷2) | same | needs ÷4 stage |
| Loop gain | unchanged | Kvco and total ratio both double: loop gain unchanged (analysis) | same as P2 | same, ×4 |
| Output duty (row 14) | raw ring duty | **÷2 stage gives ~50 % by construction** (flop skew unknown) | raw ring duty on 2x | raw on 4x |
| Period jitter in % of period (row 9) | unchanged | ÷2 spans two VCO cycles: for uncorrelated noise ≈ 1/√2 better in %, *analysis only* | worse: exposed VCO-rate clock | worse |
| Startup | n/a | I/Q ordering (+90° vs −90°) is ambiguous at power-up; needs the existing `RESETB` to fix | none | needs reset for ÷4 |
| Lock behaviour (REF/FB path, row 16, DR-007) | unchanged | unchanged (feedback from `CLK`) | unchanged | unchanged |
| Extra loads to characterize | `CLK90` buffer | `CLK90` buffer (matched to `CLK`) | `CLK2X` buffer | `CLK4X` buffer |
| Dynamic power | + small | + VCO at 2x, + ÷2 and second buffer | + 2x buffer | + 4x buffer |

"Analysis" cells are reasoning from the topology, not measurements.

## 5. Recommendation

**Adopt P2**: a quarter-cycle phase interface (`CLK`, `CLK90`) realized by
running the existing ring at 2·f_out and deriving both outputs from an I/Q ÷2
that is reset by `RESETB`; feedback to the counter is taken from `CLK`. Do not
export a multiplied clock in v1.

Why:
- It is the only option that gives an exact, frequency-tracking T/4
  relationship, which is the stated need, without moving timing work back to
  the consumer.
- It keeps the VCO topology, so existing VCO, tuning, loop-filter and lock
  evidence stays the reference rather than being thrown away (P1 even-stage
  alternative).
- Putting the divider after `CLK` keeps the counter and the lock detector at
  the same rate and behavior as today.
- It helps rather than hurts the DRAFT duty row; it does not touch rows 9, 14,
  15 bounds.

Expected complexity: **medium**. New: one I/Q ÷2 cell, one matched buffer,
a top-level pin (`CLK90`), reset behavior. Changed: the VCO now needs
2·f_out, so row 2's tuning-range campaign must cover 2x the output band
(consumer points become VCO 50 / 100 / 200 MHz; band edge 400 MHz).

Key unknowns:
1. VCO behaviour at the ends of the 2x band (low end tens of MHz; 400 MHz top
   at slow corner). Same open question as row 2, shifted.
2. CLK-to-CLK90 skew from flop and buffer mismatch (local Monte Carlo), and
   the load imbalance between the two outputs.
3. Whether the extra ÷2 stage's noise or supply coupling worsens the already
   recorded row-9 miss. The 1/√2 figure is an idealization.
4. I/Q ordering at startup and after a missing clock.
5. Power at 2·f_out on 1.8 V (row 12 is DRAFT).

If the operator prefers Option M, M2 is the lower-risk variant of it, but it
leaves the quarter-cycle derivation with the consumer, which is the gap this
request is meant to close.

## 6. Bounded implementation and verification breakdown (not authorized)

Each step is a separate issue after operator review; none is started here.

1. Behavioral model + testbench plan for the I/Q ÷2 and reset (no EDA spend).
2. Schematic/netlist: ÷2 I/Q cell and `CLK90` buffer; top-level pin and
   `design/top` change; `DR-008` load contract extended to `CLK90`.
3. Open-loop checks: skew, duty, edges at both outputs (extends the 45-point
   `sim/clk-output` campaign; reuses it where the `CLK` half is unchanged).
4. Closed-loop checks at the existing nominal points
   (`sim/pll-lock`, `-1mhz`, `-25mhz`) with the 2x VCO, reporting lock, jitter,
   `CLK` to `CLK90` offset.
5. Row-2 tuning-range campaign updated to the 2x requirement (already owed).
6. Layout/DRC/LVS impact assessed separately; no layout exists for the buffer
   either (`DR-008`).

## 7. Evidence needed before adopting the interface

- PVT: the ratified grid of rows 19 × 20 × 1 (5 process × 3 temperatures ×
  3 supplies = 45 points).
- Metrics: `CLK90 − CLK` offset (mean and spread, in degrees and ps), duty of
  both outputs, 10 – 90 % edges, V_OH/V_OL (rows 14/15 DRAFT bounds read as
  recorded pass/miss), period jitter at `CLK` per row 9 definition, and
  `CLK90` period jitter.
- Startup/lock: reset release to a defined I/Q ordering; lock time and lock
  assertion unchanged vs. the existing records; behavior with the reference
  absent and restored.
- Loading: both outputs at the `DR-008` 1 pF contract; sensitivity to
  imbalance (e.g. ±) *proposed*, not accepted.
- Reuse: existing characterization stays valid where the circuit is unchanged
  (REF/PFD/CP/filter/lock detector); VCO and `CLK`-path records are stale
  once the VCO runs at 2x and must be re-minted as new records naming what
  they supersede.
- Already owed regardless of this proposal: `DR-008` loaded campaign (#303,
  #304) and the row-2 tuning-range campaign. They are not extra cost caused by
  this proposal, except for the 2x range extension and the `CLK90` additions.

## 8. Campaign resource estimate (preparation only; no run authorized)

Inputs needed to firm this up: per-point wall time on the target host for an
open-loop `CLK`+`CLK90` transient (the `sim/vco` notes record roughly 5 – 10 min
per swept point for the VCO alone), per-point time of the closed-loop
benches, and the Monte Carlo draw count wanted for skew.

Order-of-magnitude, *unverified*: open-loop 45-point campaign ≈ 4 – 8 CPU-hours
(45 points at 5 – 10 min); three nominal closed-loop reruns ≈ hours;
Monte Carlo skew is the dominant, unbounded term (draw count × per-draw
time). This fits a local run; no cloud spend is requested or implied. Replace
with measured numbers once the per-point times above are known.

## 9. Remaining design choices for the operator

1. Option P2 (recommended) vs. M2/M4 vs. keep `DR-009` default (P0).
2. Whether `CLK2X` should additionally be exported (not recommended).
3. Whether an offset tolerance, in degrees or ps, is wanted as a ratifiable
   row; none is proposed here.
4. Whether to proceed to the breakdown in §6 and in what order.

#332 stays open and blocked until the operator rules on this.
