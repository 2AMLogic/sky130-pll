# Chipalooza Challenge #4 (Sky130) — brief proposal: integer-N ring-oscillator PLL

- **Status: DRAFT, NOT sign-off ready.** This document exists to track brief
  conformance as this repo's design work proceeds — it is not a submission
  claim. Section ["Sign-off status"](#sign-off-status) states plainly which
  acceptance criteria of issue #81 are met and which are not, and why.
- **Epic**: 2AMLogic/2am#542, Phase 4B (`[Epic #542] 4B`, issue #81 in this repo).
- **Rules-4.html status**: unpublished as of this document's writing
  (2026-09-05; the epic's tracking table gives 2026-11-09 as the publish
  date). This proposal assumes the common structure shared by
  rules-2.html/rules-3.html (see issue #81's own description) at sky130's
  ratified native rails. Per issue #81's own instruction, this does not
  block on the unpublished rules — a follow-up issue reconciles the slot
  budget once rules-4.html is live.

## 1. Block type

An **integer-N, ring-oscillator charge-pump phase-locked loop** on the
sky130 open PDK, built entirely on the **ratified 1.8 V core device flavor**
(`nfet_01v8`/`pfet_01v8`, `DR-001`). It is the sky130 port of
`2AMLogic/gf180-pll` — same block, a second open PDK, forward-designed from
a ratified spec (`spec/target-spec.md`), not reverse-engineered from any
existing silicon or netlist (`CLAUDE.md`'s reverse-engineering-free rule).

Standard charge-pump integer-N topology (Gardner/Best/Razavi): a
phase-frequency detector (PFD) compares the reference input against a
divided feedback clock, drives a charge pump, which drives a passive R/C
loop filter, which drives a 5-stage ring VCO; the VCO output is both the
PLL's `CLK` output and the input to a programmable feedback divider that
closes the loop. See `design/top/DESIGN.md` for the wiring rationale and
`design/{vco,pfd-cp,loop-filter,divider}/DESIGN.md` for each block's own
topology and sizing rationale.

## 2. I/O mapped to the slot budget

The brief's common structure (per issue #81: harness-supplied bias/bandgap
reference, 24 digital control inputs, 12 digital test outputs, 4 shared
(multiplexed) analog lines, 0–4 dedicated pads, SPI control interface) is
**not yet wired to this block** — no SPI shim or harness-integration
schematic exists in this repo. The table below maps this block's own native
I/O (`design/top/top.sym`, confirmed against the generated
`design/top/netlist/top.spice` `.subckt` line) onto that budget as a
starting allocation, not a verified harness integration:

| Pin | Direction | Kind | Slot-budget bucket | Notes |
|---|---|---|---|---|
| `VDD` | inout | supply | harness-supplied rail | ratified 1.8 V core, `DR-001`/`DR-002` |
| `GND` | inout | supply | harness-supplied rail | single domain — no ring/PFD-CP/digital split (`spec/target-spec.md` row 1) |
| `REF` | in | digital, clock | 1 of 24 digital control inputs | reference clock, 1–25 MHz target (row 3, DRAFT) |
| `RESETB` | in | digital | 1 of 24 digital control inputs | active-low power-on reset |
| `NSEL0`–`NSEL5` | in (×6) | digital | 6 of 24 digital control inputs | static divide-ratio strap, N = 4–64 (row 4, DRAFT); no runtime SPI reprogramming exists yet — a strap-driven static configuration only |
| `CLK` | out | digital, clock | 1 of 12 digital test outputs | PLL output, target `N * Fref` |

**Totals against the budget**: 8 of 24 digital control inputs used, 1 of 12
digital test outputs used, 0 of 4 shared analog lines used, 0 of 0–4
dedicated pads used. This block currently has **no** analog test-point pin
(e.g. a buffered `VCTRL` monitor) and **no** lock-detector output — both are
DRAFT/unimplemented (`spec/target-spec.md` row 16, "Lock detector": no
digital `lock` output exists in `design/top/top.sch` today). If the brief's
sign-off bench plan below needs one, adding a buffered `VCTRL` tap onto one
of the 4 shared analog lines is a small, scoped follow-up, not a change to
any block already reviewed and merged.

**No SPI control interface exists.** The harness's SPI control shim (per
issue #81's "common structure") has no counterpart in this repo — `NSEL[5:0]`
is presently a static hardware strap, matching row 4's "static configuration"
v1 scope, not an SPI-programmable register. Wiring an SPI-to-strap shim (or
confirming the harness intends bare digital pins for this slot) is future
work, out of this document's scope to invent.

## 3. Functional description

`REF` drives the PFD's reference input; the PFD compares it against
`FBCLK`, the divider's feedback tap, and drives `UP`/`DN` pulses into the
charge pump, whose output current `Icp` charges/discharges the loop filter
node `CP`. The loop filter's `VCTRL` output sets both the ring VCO's tail
currents (`design/vco/DESIGN.md`), producing an oscillation on `CLK`.
`CLK` feeds a programmable `NSEL[5:0]`-strapped divide-by-N counter
(`design/divider/DESIGN.md`, `sky130_fd_sc_hd` standard cells) whose
registered output closes the loop back to the PFD as `FBCLK`. `RESETB`
holds the divider in a defined power-on state. See `design/top/DESIGN.md`
for the full net-by-net wiring table and the interface-compatibility
analysis (no level shifting or buffering needed at any block boundary —
all four blocks share the ratified 1.8 V core flavor).

## 4. Spec table (min/typ/max, re-derived from `sim/` where evidence exists)

Source of truth for every row below is `spec/target-spec.md`. Per that
file's own status legend, **only rows 0, 1, 19, and 20 are RATIFIED** — every
other row is **DRAFT — to be ratified**, carried from `2AMLogic/gf180-pll` as
a starting point and explicitly not assumed to hold on sky130. Consistent
with `CLAUDE.md`'s rule that a spec row may be closed only by a sky130
campaign (never by porting the gf180-pll number), the "sky130 evidence" column
below cites the actual `sim/` record backing each min/typ/max figure, or
states plainly that none exists yet.

| # | Parameter | Target (min/typ/max) | Status | sky130 evidence | Met vs. brief? |
|---|---|---|---|---|---|
| 0 | Supply flavor | 1.8 V core (`nfet_01v8`/`pfet_01v8`) | **RATIFIED** (`DR-001`) | design-wide device choice, confirmed by every block's netlist | **Met** — settled |
| 1 | Supply range | 1.62 / 1.80 / 1.98 V | **RATIFIED** (`DR-002`) | confirmed single-domain by `design/top/netlist/top.spice` | **Met** — settled |
| 2 | Output band | 10–200 MHz (DRAFT, gf180-pll carry-over) | DRAFT | `sim/vco/records/` characterizes `vco_ring5` alone; DESIGN.md's own sanity check shows a free-running range on the order of ~145 MHz at one VCTRL point, not yet a full committed band-map campaign result cited here | **Unmet / unverified** — band map not re-derived on sky130 |
| 3 | Reference input | 1–25 MHz, CMOS, 30–70% duty | DRAFT | exercised at 1, 10, 25 MHz by `sim/pll-lock`, `sim/pll-lock-1mhz`, `sim/pll-lock-25mhz` | **Partially exercised, not ratified** |
| 4 | Multiplication ratio | N = 4–64, static | DRAFT | `sim/pll-lock*` straps N=10/25/64 | **Partially exercised, not ratified** |
| 5 | Kvco | ≤ TBD bound (not the ported 150 MHz/V) | DRAFT | `sim/loop-ac` measures loop gain including Kvco; loop-filter re-sized against a *measured* Kvco (issue #92/#95) | **Unmet** — no ratified bound |
| 6 | Loop bandwidth | f_c < f_ref/10 | DRAFT | `sim/loop-ac` open-loop AC sweep | **Unmet** — not ratified; latest closed-loop lock evidence (below) shows this is not yet closed satisfactorily |
| 7 | Phase margin | ≥ 45° | DRAFT | `sim/loop-ac` | **Unmet** — not ratified |
| 8 | Lock time | < 100 µs | DRAFT | `sim/pll-lock` (see [Sign-off status](#sign-off-status): only 1 of 45 PVT points in the latest record locks at all, at 1.565 µs) | **Unmet** |
| 9 | Period jitter | ≤ 1.0% RMS, conditional on ripple limit | DRAFT | no record | **Unmet / unmeasured** |
| 10 | Reference spur | ≤ −55 dBc (candidate) | DRAFT | no record | **Unmet / unmeasured** |
| 11 | Integrated RMS jitter / phase noise | not spec'd (deliberate) | DRAFT | n/a by design | **N/A** (deliberately unspecified, per gf180-pll precedent) |
| 12 | Power | budget TBD | DRAFT | no record | **Unmet / unmeasured** |
| 13 | Supply sensitivity | ripple + Vctrl-excursion budget TBD | DRAFT | no record | **Unmet / unmeasured** |
| 14 | Output duty cycle | 45–55% | DRAFT | `sim/pll-lock` reports duty at the one locked point (50.2%, within target) | **Partially evidenced, not ratified** |
| 15 | Output levels/drive | rail-to-rail CMOS | DRAFT | not separately measured; `vco_ring5`'s output buffer sized per `design/vco/DESIGN.md` | **Unmet / unmeasured** |
| 16 | Lock detector | digital `lock` output | DRAFT | **not implemented** — no `lock` pin exists in `design/top/top.sch` | **Unmet — not implemented** |
| 17 | Standby / power-down | none in v1 | DRAFT | design choice, not yet ratified | **Unmet** — not ratified |
| 18 | Area | budget TBD | DRAFT | no layout-derived area figure recorded here | **Unmet / unmeasured** |
| 19 | Process corners | `tt`,`ff`,`ss`,`sf`,`fs` | **RATIFIED** (`DR-003`) | applied throughout `sim/pll-lock`, `sim/vco` campaigns | **Met** — settled |
| 20 | Operating temperature | −40/27/125 °C | **RATIFIED** (`DR-003`) | applied throughout `sim/pll-lock`, `sim/vco` campaigns | **Met** — settled |

**No row above is relaxed to make it pass.** Every "Unmet" entry is recorded
as a miss, per `CLAUDE.md`'s instruction that a result missing the spec is
recorded as a miss and the spec is changed only by its own decision record,
never to launder a failing number.

## 5. Bench test plan

This is a **plan**, not yet executed against silicon (none exists) or even
against a completed post-layout netlist. It follows the same measurement
methodology already implemented in `sim/harness/measure.py` so the eventual
bench procedure and the existing pre-silicon evidence stay comparable:

1. **Static I/O check.** Strap `NSEL[5:0]` to each of a representative
   subset of N in [4, 64]; confirm `CLK` is silent with `RESETB` asserted low
   and begins toggling once `RESETB` deasserts (matching `sim/pll-lock`'s
   own reset pulse convention).
2. **Reference range sweep.** Drive `REF` at 1, 10, and 25 MHz (spec row 3's
   band edges plus its `sim/pll-lock` nominal point) and confirm `CLK`
   frequency tracks `N * Fref` post-lock, using a frequency counter or
   time-interval analyzer on `CLK`.
3. **Lock-time measurement.** Time from `RESETB` deassertion to `CLK`
   settling within the ±5% lock-band criterion `sim/harness/measure.py`
   already implements (mean frequency over a 20-cycle sliding window);
   repeat across the ratified PVT grid (rows 19/20: 5 process corners ×
   3 temperatures × supply extremes) to the extent the bench setup can
   control temperature and supply.
4. **Duty cycle and levels.** Measure `CLK` duty cycle and V_OH/V_OL into
   the brief's stated load, at each locked operating point from step 3.
5. **Jitter / spur.** Capture `CLK` period jitter (RMS) and any reference
   spur on a spectrum analyzer once a locked operating point is available
   long enough to characterize — not yet exercised even in simulation (row
   9/10 above).
6. **Power.** Measure supply current at a stated locked operating frequency
   once row 12's budget is ratified.

Every step above reuses this repo's existing measurement conventions
(`sim/harness/measure.py`'s lock/duty extraction, the ratified PVT grid) so
a future bench record and the existing `sim/` evidence remain comparable
apples-to-apples.

## 6. Sign-off status

**Not at the brief's sign-off bar.** Stated plainly, against issue #81's own
acceptance criteria:

- **AC 1** (this document, populated from real `sim/`/`spec/` evidence):
  **done**, this document.
- **AC 2** (every spec row states met/unmet, no row relaxed): **done** — see
  the table in section 4.
- **AC 3** (post-layout PVT simulation and DRC/LVS-clean GDS in-repo):
  **not met.** Concretely:
  - **Closed-loop lock, pre-layout schematic level**
    (`sim/pll-lock/records/20260904-163254-f00ce3e.md`, the current record):
    of the full 45-point ratified PVT grid, only **1 point locks**
    (`tt`, −40 °C, 1.80 V — locks at 1.565 µs, 249.7 MHz, 50.2% duty). The
    other 44 points either fail to oscillate, run away to a frequency far
    from the 250 MHz target and never settle within the 3 µs window, or hit
    a numerical solver error. This is real, committed, append-only evidence
    of an open loop-dynamics problem — not yet a design that locks
    reliably across PVT even before layout parasitics are added. This is
    consistent with `design/top/DESIGN.md`'s own documented `Icp` /
    loop-filter / `Kvco` coordination gap, which issues #92–#95 have begun
    addressing (loop-filter re-sizing against a landed `Icp` and measured
    `Kvco`) but which the latest PVT-grid record above shows is not yet
    resolved across the full grid.
  - **Post-layout simulation**: does not exist. No post-layout (parasitic-
    extracted) netlist or PVT campaign is recorded under `sim/` for this
    design.
  - **Full-chip DRC**: **not clean.** The latest full-chip layout DRC report
    (`layout/pll/reports/LATEST` → `20260821-080803-b0c10bd/report.md`)
    shows open `li1.space.1` (local-interconnect minimum spacing)
    violations across `pll_top`. LVS at the full-chip level is likewise not
    recorded as clean in that report set (only a narrower
    `route-spot-check` LVS exists in that report tree).
  - Consequently, **no DRC/LVS-clean full-chip GDS exists in-repo today.**
- **AC 4** (reconcile against rules-4.html once published): not yet
  applicable — rules-4.html has not published as of this writing (see
  header above); revisit once it does.

**This is a partial contribution, not issue #81's full closure.** This PR
adds the proposal document (AC 1, AC 2) and this honest sign-off status
section; it does not — and cannot, without fabricating evidence — check AC
3's box. The loop-lock and layout-DRC gaps documented above are tracked by
the repo's ongoing design work (the loop-filter/`Icp`/`Kvco` coordination
issues and the layout DRC cleanup); this document should be revised (a new
PR against this same file, not an edit to any `sim/`/`layout/` evidence
record) once that work lands, at which point AC 3 can be re-evaluated
honestly against fresh evidence.
