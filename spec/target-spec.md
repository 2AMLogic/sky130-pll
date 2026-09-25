# PLL target specification

- **Status**: **RATIFIED (rows 0, 1, 9, 19, 20) — row 0 2026-08-13 via
  `DR-001` in #1; row 1 2026-08-19 via `DR-002` in #19; rows 19 and 20
  2026-08-27 via `DR-003` in #77; row 9 2026-09-23 via `DR-006` in #151.**
  The **supply flavor is settled**: the 1.8 V core
  (`nfet_01v8`/`pfet_01v8`). That row is binding, and design/sim/layout work
  may now lock to it. The **supply range is settled**: 1.8 V ± 10 %
  (1.62 – 1.98 V), single supply domain (no ring / PFD-CP / digital split).
  The **PVT process-corner set is settled**: sky130's five standard MOS/BJT
  process corners — `tt`, `ff`, `ss`, `sf`, `fs`. The **operating temperature
  range is settled**: −40 °C to 125 °C, sampled at −40/27/125 °C. Rows 19 and
  20, crossed with the ratified row 1 supply range, define the PVT grid every
  future per-corner row is verified against once that row is itself ratified.
  The **period-jitter target is settled**: ≤ 1.0 % of the output period, RMS,
  at `CLK` in lock, stated under a **DC-quiet supply** anywhere in row 1's
  range and verified over that PVT grid plus a local-mismatch Monte Carlo
  population — the first ratified *performance* row. `DR-006` also
  **explicitly leaves rows 10 (reference spur) and 13 (supply sensitivity)
  DRAFT**, each for a cited structural reason and each with a stated closure
  condition, rather than by omission — see those rows' own sections.
  **No other numeric row below is ratified.** Ratifying a row does not ratify
  the rows it merely informs — each remaining row's "what must be settled on
  sky130" column is a committed obligation (re-derive / confirm /
  port-and-verify) rather than a draft intention. A row marked **re-derive**
  must be closed by a sky130 campaign producing evidence; it may not be closed
  by porting the gf180-pll number.
- **Date**: 2026-08-10 (drafted); 2026-08-13 (row 0 ratified); 2026-08-19
  (row 1 ratified); 2026-08-27 (rows 19, 20 ratified); 2026-09-23 (row 9
  ratified; rows 10 and 13 explicitly left DRAFT)
- **Written by**: scaffold, repo creation
- **Block class**: integer-N, ring-oscillator phase-locked loop.
- **Port relationship**: this is the sky130 port of `2AMLogic/gf180-pll`. Its
  ratified spec is the primary numeric starting point (cited per row below as
  *gf180-pll*), but gf180-pll targets **3.3 V I/O devices**; sky130's core is
  **1.8 V**. Numbers do not port across a supply change unchanged, so each row
  states what must be re-verified on sky130 rather than assuming parity.

---

## How to read this file

This mirrors the gf180-pll spec structure. Every parameter has a row in the
[summary table](#summary-table) carrying a **DRAFT target (starting point)**,
its **source**, the **sky130 open question** that ratification must resolve, and
a **status** — *DRAFT — to be ratified* for every row that no decision record
has yet disposed of (see the [summary table](#summary-table) for which rows
are RATIFIED, and which are DRAFT by an explicit decision). As rows ratify,
they gain the gf180-pll-style corner bindings and measured/derived/budget
status words, each backed by a `sim/` evidence record.

**The cardinal rule for this file.** No number below is presented as final.
Where a value is carried from gf180-pll or a published sky130 reference, it is a
candidate to be tested, not a commitment. Agents do not invent settled numbers
here, and do not edit a value to match a simulation result — a spec change is a
decision record (`spec/decision-records/DR-NNN`), argued on its merits.

### The first thing #1 must settle — supply flavor

gf180-pll runs its ring, PFD, charge pump, and dividers on gf180's 3.3 V I/O
devices (`nfet_03v3`/`pfet_03v3`) at 3.3 V ±10 %. sky130 does not have that same
flavor. The candidate sky130 flavors are:

- **1.8 V core** (`nfet_01v8`/`pfet_01v8`) at 1.8 V ±10 % (1.62–1.98 V) — the
  natural home for a fast digital ring and CMOS logic, and where sky130's
  standard-cell libraries (`sky130_fd_sc_hd`) and existing open ring-oscillator
  clocking IP (e.g. the Caravel / Chipignite ecosystem) live. **Candidate
  primary.**
- **A medium-/high-voltage arrangement** (sky130's 5 V-class / stacked I/O
  devices) — only if a downstream interface or supply constraint demands it.

This choice drives the output band, Kvco, loop-filter sizing, and power budget,
so it is prerequisite to ratifying the rows below. The mechanism is the same one
sky130-bandgap used for its own supply-flavor scope decision
(`spec/decision-records/DR-001-supply-flavor-scope.md`): a decision record
scopes the flavor as an input to #1. **This draft assumes the 1.8 V core as the
working candidate, flagged per row — it is not ratified.**

### Everything here is pre-schematic and pre-silicon

No schematic, no netlist, no extracted parasitics, no PVT sweep, no silicon
exists yet. Every value is a target to design toward, not a measurement.

---

## Summary table

Rows 0, 1, 9, 19, and 20 are **RATIFIED** (see their own cells below). Rows
10 and 13 are **DRAFT by an explicit decision** (`DR-006`, #151) — each
carries a cited reason and a stated closure condition rather than a bare
DRAFT marker. Every other row's status is uniformly **DRAFT — to be
ratified** until its own decision record closes.

| # | Parameter | DRAFT target (starting point) | Source | sky130 open question to resolve at ratification |
|---|---|---|---|---|
| 0 | [Supply flavor](#supply-flavor) | 1.8 V core (`nfet_01v8`/`pfet_01v8`) — **RATIFIED 2026-08-13 (DR-001, #1)** | sky130 core device menu; `DR-001` | **Settled.** I/O-class (`g5v0`-family) deferred, not rejected — revisit only on a demonstrated downstream interface constraint |
| 1 | [Supply range](#supply-range) | 1.8 V ±10 % (1.62–1.98 V) — **RATIFIED 2026-08-19 (DR-002, #19)** | derived from ratified row 0; tolerance ported with rationale from gf180-pll row 1 (3.3 V ±10 %) | **Settled.** Single supply domain confirmed by `design/top/netlist/top.spice` (one `VDD`/`GND` pair for `pfd_cp`/`vco_ring5`/`divider_intN`) — no ring/PFD-CP/digital split exists in the merged design |
| 2 | [Output band](#output-band) | 10 – 200 MHz continuous, **carried from gf180-pll and NOT assumed to hold** | gf180-pll row 1 | a 130 nm ring on 1.8 V core may reach *higher* or trade range for Kvco — re-derive the band and stage count on sky130 |
| 3 | [Reference input](#reference-input) | 1 – 25 MHz, CMOS square wave, rising-edge triggered, duty 30–70 % | gf180-pll row 2 | confirm input levels for the ratified supply flavor |
| 4 | [Multiplication ratio](#multiplication-ratio) | N = 4 – 64, every integer, static configuration | gf180-pll row 3 | confirm divider retiming closes at the sky130 top frequency |
| 5 | [Kvco](#kvco) | ≤ a fixed-filter-compatible bound (gf180-pll used ≤ 150 MHz/V) | gf180-pll row 17 | the numeric bound depends on the sky130 band map — re-derive; do not port 150 |
| 6 | [Loop bandwidth](#loop-bandwidth) | f_c well below f_ref, hard ceiling `f_c < f_ref/10` | gf180-pll rows 8/8a | the kHz range depends on ratified band + filter; re-derive |
| 7 | [Phase margin](#phase-margin) | ≥ 45° everywhere in the contracted space | gf180-pll row 8a | port the criterion; re-verify the realized margin on sky130 |
| 8 | [Lock time](#lock-time) | < 100 µs to a stated lock criterion | gf180-pll row 9 | re-verify; cold-start owed to a testbench, not a budget number |
| 9 | [Period jitter](#period-jitter) | ≤ 1.0 % of the output period, RMS, at `CLK` in lock, under a **DC-quiet supply** within row 1's range — **RATIFIED 2026-09-23 (DR-006, #151)** | the *percentage* form of gf180-pll row 5 — dimensionless, and therefore the one clause of that row unaffected by the 3.3 V → 1.8 V change `DR-001` ratified; re-argued in `DR-006`, not ported wholesale. gf180-pll's `vdd_vco` ripple *condition* is explicitly **not** ported | **Settled for the DC-quiet supply condition** (ideal DC source at 1.62/1.80/1.98 V, no externally applied AC ripple), verified over the row 19 × 20 × 1 PVT grid plus local-mismatch Monte Carlo. The **ripple-inclusive** form is *not* ratified: row 1 binds a single supply domain, so there is no dedicated VCO rail to port gf180-pll's condition onto — owed at row 13 (`DR-006`) |
| 10 | [Reference spur](#reference-spur) | ≤ −55 dBc (candidate) — **DRAFT by explicit decision (DR-006, #151)**, not by omission | gf180-pll row 7 | **Deliberately left open.** A dBc figure scales as `20·log₁₀(f_out)` and row 2 is DRAFT, so the target has no binding frequency; and at this ring's `Kvco/f_out` (4.3–10.9 /V vs. gf180-pll's 0.31–0.84 /V) porting −55 dBc would covertly ratify a `Kvco` requirement row 5 has never argued. Closure needs rows 2 and 5 ratified plus a sky130 charge-pump charge-asymmetry / `VCTRL`-ripple measurement (`DR-006`) |
| 11 | [Integrated RMS jitter / phase noise](#jitter-and-phase-noise) | **not spec'd** — derived-only, deliberately visible | gf180-pll rows 4/6 | confirm the same deliberate omission applies |
| 12 | [Power](#power) | a budget at a stated frequency (gf180-pll used < 5 mW at 100 MHz on 3.3 V) | gf180-pll row 10 | 1.8 V changes the power story — re-budget; do not port the mW figure |
| 13 | [Supply sensitivity](#supply-sensitivity) | supply-ripple limit + a DC-excursion Vctrl budget — **DRAFT by explicit decision (DR-006, #151)**, not by omission, both budgets | gf180-pll row 12 | **Deliberately left open, per budget.** *AC*: gf180-pll's limit is written against a dedicated `vdd_vco` rail, which ratified row 1 (single supply domain) does not provide — and a shared-rail limit is partly self-imposed, needing a transient measurement that does not exist. *DC*: the budget divides by `Kvco/f_out` (row 5, DRAFT) and by an unmeasured usable `VCTRL` window. `DR-006` records the structural `1/VDD` pushing floor (55.6 %/V at 1.8 V vs. 30.3 %/V at 3.3 V) as the anchor a future derivation starts from |
| 14 | [Output duty cycle](#output-duty-cycle) | 45 – 55 % at CLK, whole band, all corners | gf180-pll row 13 | port target; owed a measurement |
| 15 | [Output levels and drive](#output-levels-and-drive) | rail-to-rail CMOS, V_OH ≥ 0.9·VDD / V_OL ≤ 0.1·VDD into a stated load | gf180-pll row 14 | confirm the load and rail for the ratified supply |
| 16 | [Lock detector](#lock-detector) | digital `lock` output; assert window + hysteresis criteria | gf180-pll row 16 | port the behavioral contract; re-verify the window on sky130 |
| 17 | [Standby / power-down](#standby) | no power-down mode in v1 (always-on) | gf180-pll row 11 | confirm the same v1 scope call |
| 18 | [Area](#area) | a budget, not a result (no layout exists) | gf180-pll row 15 | sky130 area differs from gf180 — set a sky130 budget at ratification |
| 19 | [Process corners](#process-corners) | sky130's five standard MOS/BJT process corners: `tt`, `ff`, `ss`, `sf`, `fs` — **RATIFIED 2026-08-27 (DR-003, #77)** | `sky130.lib.spice`'s own `.lib` corner sections (`sim/pdk.json`'s provenance note); re-derived for this PLL's PFD/charge-pump topology in `DR-003`, not ported from gf180-pll or silently inherited from `tb.json`'s prior `tt`/`ss`/`ff`-only convention | **Settled.** The mixed-skew corners `sf`/`fs` — absent from the prior harness convention — are included because they stress this design's un-cascoded PFD/charge-pump `UP`/`DN` current mirror; interconnect R/C skew corners (`ll`/`hh`) and mismatch Monte Carlo (`_mm`) are separate axes, out of scope here (`DR-003` *Alternatives considered*) |
| 20 | [Operating temperature range](#operating-temperature-range) | −40 °C to 125 °C, sampled at −40 / 27 / 125 °C — **RATIFIED 2026-08-27 (DR-003, #77)** | industrial temperature-range convention; independently adopted by `2AMLogic/sky130-bandgap`'s own ratified target spec for the same sky130 PDK, not silently inherited from this repo's own `tb.json` | **Settled.** Crossed with the ratified row 19 process-corner set and row 1 supply range to form the full PVT grid every future per-corner row is verified against once that row is itself ratified |

---

# Parameters

Each section below states the DRAFT target, its provenance, and the sky130
verification owed. **None of these are settled.**

## Supply flavor

**RATIFIED 2026-08-13** (`DR-001`, ruled in #1). The ring oscillator, PFD,
charge pump, and dividers are built on the **1.8 V core**
(`nfet_01v8`/`pfet_01v8`). Design, sim, and layout may lock to this.

sky130 has no counterpart to gf180's 3.3 V *core* flavor
(`nfet_03v3`/`pfet_03v3`), so porting the flavor was never an available
option — see `DR-001` *Alternatives considered*. The medium-/high-voltage
(`g5v0`-family / I/O-class) arrangement is **deferred, not rejected**: revisit
only if a downstream integration surfaces a real interface constraint (e.g. a
`CLK` that must drive an off-chip rail without a level shifter).

**Two accepted costs this ratification hands to design** (from `DR-001`
*Consequences* — accepted deliberately, not overlooked):

- **Reduced Vctrl headroom.** A 1.8 V rail gives the charge pump and loop
  filter roughly a third of gf180-pll's 3.3 V control-voltage window.
  Current-source compliance, switch overdrive, and the usable linear-tuning
  fraction are all tighter; sub-threshold behaviour of `nfet_01v8`/`pfet_01v8`
  mirrors at reduced headroom is a specific risk to design against. The charge
  pump and loop filter **owe a headroom analysis**, tracked at row 13.
- **Tighter ripple tolerance.** The same absolute ripple consumes a larger
  fraction of a 1.8 V Vctrl window, so gf180-pll's ripple limit must be
  re-derived **smaller, not larger** (rows 9 and 13).

## Supply range

**RATIFIED 2026-08-19** (`DR-002`, ruled via #19). **1.8 V ± 10 %
(1.62 – 1.98 V), a single supply domain** — no separate ring / PFD-CP /
digital domain split.

The ± 10 % tolerance is ported from gf180-pll's own row 1 with rationale,
not as a bare number: the *absolute voltage* does not carry across the
row-0 supply-flavor change, but the ± 10 % figure is a generic
supply-tolerance convention independent of the nominal voltage it applies
to (see `DR-002`). The single-domain answer is confirmed by inspection of
the merged design: `design/top/netlist/top.spice` ties `pfd_cp`,
`vco_ring5`, and `divider_intN` to one shared `VDD`/`GND` pair
(`design/top/DESIGN.md`'s pin-mapping table) — there is no domain-split
structure to verify against. This matches what `sim/pll/testbench/tb.json`
has assumed since #45 (`supply_nominal: 1.8`, `supply_tolerance: 0.1`).

## Output band

**DRAFT — to be ratified.** Starting point 10 – 200 MHz continuous, carried from
gf180-pll — **explicitly not assumed to hold on sky130.** A 130 nm ring on 1.8 V
core devices has a different frequency/gain trade than a 180 nm ring on 3.3 V;
the band edges, the number of ring stages, and the band-map (gf180-pll used
eight overlapping bands with a normative band-selection rule) must be
re-derived from a sky130 VCO tuning-range campaign, not ported.

## Reference input

**DRAFT — to be ratified.** 1 – 25 MHz, CMOS square wave into `REF`,
rising-edge triggered, 30–70 % duty. Ported from gf180-pll as an interface
contract; input levels bind to the ratified supply flavor.

## Multiplication ratio

**DRAFT — to be ratified.** N = 4 – 64, every integer, static configuration
(no auto-calibration FSM, matching gf180-pll v1). Confirm the feedback divider
retiming closes at the sky130 top frequency.

## Kvco

**DRAFT — to be ratified.** A bound chosen to keep the loop inside a single
fixed loop filter across the reference range (gf180-pll used ≤ 150 MHz/V under
its band-selection rule). **The 150 number is not ported** — the sky130 bound
follows from the sky130 band map and must be re-derived.

## Loop bandwidth

**DRAFT — to be ratified.** f_c set well below f_ref with a hard ceiling
`f_c < f_ref/10`, adapted across the reference range by a charge-pump current
trim (gf180-pll's Icp trim-code rule). The realized kHz range depends on the
ratified band and filter and must be re-derived.

## Phase margin

**DRAFT — to be ratified.** ≥ 45° everywhere in the contracted (f_ref, N, trim)
space. Criterion ported; realized margin re-verified on sky130.

## Lock time

**DRAFT — to be ratified.** < 100 µs to a stated lock criterion. Small-signal
settling and cold-start bring-up are each owed a testbench, not a budget number.

## Period jitter

**RATIFIED 2026-09-23** (`DR-006`, ruled via #151). **≤ 1.0 % of the output
period, RMS**, at `CLK`, in lock.

**The spec'd quantity.** The standard deviation of the measured period `T_k`
over a population of consecutive output cycles taken after lock, divided by
that population's mean period, as a percentage. **The percentage form is
normative**; any absolute picosecond figure (100 ps RMS at 100 MHz, 50 ps at
200 MHz) is a derived restatement of it, never the spec'd quantity. Stating
this explicitly closes the 10× drafting ambiguity gf180-pll's own row 5 had
to resolve after the fact.

**The condition it is stated under.** The bound holds with the supply
modelled as an **ideal DC source at any point in row 1's ratified range**
(1.62 / 1.80 / 1.98 V) with **no externally applied AC ripple**, over the
full PVT grid rows 19 × 20 × 1 define, and over a local-mismatch Monte Carlo
population at the nominal point (`sim/run_corners.py <slug> --mc`).

gf180-pll makes its own 1 % line conditional on a `vdd_vco` ripple limit
instead. **That condition is not ported**: ratified row 1 binds a *single*
supply domain, so this design has no dedicated VCO rail to place such a
limit on (`DR-006` *Decision* §1). What ports is the part of gf180-pll's
row 5 that carries no volts — the percentage — exactly the cut `DR-002` made
when it ported gf180-pll's ± 10 % tolerance while refusing the 3.3 V it was
attached to. The **ripple-inclusive** form of this row is owed at row 13 and
is not delivered by this ratification.

**< 0.5 % is retained as an uncommitted stretch** — no evidence either way,
not a second ratified bound.

**This ratifies a target, not a compliance claim.** The first period-jitter
*measurement* in this repo — `sim/pll-lock-mc/records/20260924-222341-a9375a5.md`
(#20), the statistical axis this row is stated over — **records a miss**: of 5
local-mismatch + process draws at `tt`/125 °C/1.80 V, the 3 that locked measured
1.584 %, 1.851 % and 3.073 % RMS against this row's 1.0 % bound. That is
recorded as a miss, not a reason to move the bound (`CLAUDE.md`); this
ratification stands as written. Two limits of that record belong with the
numbers: its 50 µs window is shorter than row 8's 100 µs cold-start budget, and
the 200 ps waveform-dump grid puts a quantization floor under any jitter figure
which can only *inflate* it — so the measured miss cannot be read as a design
miss until a finer-grid re-run separates the two. With this ring's measured
tuning slope
(`Kvco/f_out` = 4.3 – 10.9 per volt), roughly a millivolt of `VCTRL` ripple
consumes the whole budget — so this is a demanding target for the present
design, and a campaign that records a miss records it as a miss.

## Reference spur

**DRAFT — left open by explicit decision** (`DR-006`, #151), not by
omission. The ≤ −55 dBc figure stays a **candidate**.

Two structural reasons, either of which alone is disqualifying:

- **No binding frequency.** A spur in dBc scales as `20·log₁₀(f_out)` for a
  given control-voltage disturbance, and row 2 (output band) is DRAFT.
  gf180-pll's own measurements flip from pass to fail across a 150 → 200 MHz
  rescale of 2.5 dB, so this is not a rounding concern.
- **It would covertly ratify a `Kvco` requirement.** Spur phase deviation
  scales linearly with `Kvco` at fixed `f_out` and fixed `VCTRL` ripple.
  gf180-pll's `Kvco/f_out` spans 0.31 – 0.84 per volt; this design's measured
  692 – 1751 MHz/V against its own 160 MHz design point gives 4.3 – 10.9 per
  volt — 14 – 31 dB more spur for the same ripple. Part of that is the
  structural cost `DR-001` already accepted (a ~2.2× narrower control
  window); the rest is what row 5 owes.

Additionally, the mechanism a sky130 number would have to be *derived* from
is unmeasured (`design/pfd-cp/DESIGN.md`: "no DC operating-point simulation
exists for this block"), and this design's deliberately un-cascoded charge
pump — a 1.8 V headroom choice — has structurally worse `UP`/`DN` matching
than the topology gf180-pll's number was measured on.

**What would ratify this row**: rows 2 and 5 ratified, plus a sky130
charge-pump `UP`/`DN` charge-asymmetry measurement and a `VCTRL`-ripple-in-
lock measurement (or a direct closed-loop sideband measurement).

## Jitter and phase noise

**DRAFT — to be ratified.** Integrated RMS jitter and phase noise are
**deliberately not spec'd** in gf180-pll (derived-only, DR-002 Decision 5),
listed rather than omitted so the omission is visible and attributable. Confirm
the same deliberate stance applies to the sky130 port.

## Power

**DRAFT — to be ratified.** A budget at a stated frequency. gf180-pll used
< 5 mW at 100 MHz on 3.3 V; **the mW figure does not port** — a 1.8 V supply
changes dynamic power materially. Re-budget for sky130 at ratification.

## Supply sensitivity

**DRAFT — left open by explicit decision** (`DR-006`, #151), not by
omission. gf180-pll's structure carries two independent budgets; they fail
ratification for different reasons and are disposed separately.

**Budget 1 (AC) — a supply-ripple limit.** gf180-pll constrains ripple on a
**dedicated `vdd_vco` rail**. Ratified row 1 binds a *single* supply domain
with no such rail, so there is no quantity here to port the limit onto. The
nearest available quantity — ripple on the one shared `VDD` — is partly
generated by the PLL's own divider and PFD switching, making any candidate
limit partly a constraint the block imposes on itself; whether such a limit
is even self-consistent needs a transient measurement of the block's own
rail disturbance, which does not exist (`design/loop-filter/DESIGN.md`:
"`sim/loop-ac` … measures nothing about ripple").

*What is recorded instead*, from topology algebra and ratified row 1 alone:
a current-starved ring runs at `f ≈ I_stage/(n·C_stage·V_swing)` with
`V_swing` = the supply, so fractional-frequency pushing has a **structural
floor of `1/VDD`** — **55.6 %/V at 1.8 V against 30.3 %/V at 3.3 V**, i.e.
this rail is ≥ 1.83× more sensitive *per absolute volt*. That is `DR-001`'s
"re-derive smaller, not larger" made numeric for the first time. It also
bounds any future limit from above: allocating half the ratified row-9
budget to sinusoidal ripple gives `Vpp ≤ 25.4 mV` **at the floor**, so the
eventual limit is strictly below 25 mV pp. No number is ratified, because
narrowing 25 mV to a usable figure currently requires importing two
gf180-pll measurement ratios across a PDK and a supply change.

**Budget 2 (DC) — a rail-excursion `VCTRL` budget.** The required control-
voltage re-positioning is `(Δf/f) / (Kvco/f_out)`, and row 5 (Kvco) is
DRAFT — the budget swings more than 10× between this design's measured slope
and the DRAFT row-5 bound. Its denominator, the usable `VCTRL` window, is
also unmeasured (`design/pfd-cp/DESIGN.md`'s compliance range is "a
design-time qualitative note, not a verified operating-point claim").

*What is recorded instead*: at the `1/VDD` floor, a full-range row-1
excursion (1.62 → 1.98 V) moves the open-loop frequency by **≥ 22 %** — the
**same** fractional figure as gf180-pll's, because row 1's tolerance is
relative (± 10 %). The 1.8 V rail's penalty is concentrated in the **AC**
budget (denominated in absolute millivolts), not the DC one. Do not apply
the 1.83× factor to Budget 2.

**What would ratify this row**: for Budget 1, a sky130 VCO supply-pushing
campaign plus a transient `VDD`/`VCTRL` ripple measurement of the assembled
loop (tracked at #159); for Budget 2, row 5 ratified plus a measured usable
`VCTRL` window (a charge-pump compliance-range DC measurement).

## Output duty cycle

**DRAFT — to be ratified.** 45 – 55 % at `CLK` over the whole band and all
corners. Target ported; owed a loaded measurement.

## Output levels and drive

**DRAFT — to be ratified.** Rail-to-rail CMOS on the output-buffer supply:
V_OH ≥ 0.9·VDD, V_OL ≤ 0.1·VDD into a stated external load. Rail and load bind
to the ratified supply flavor.

## Lock detector

**DRAFT — to be ratified.** A digital `lock` output with an assert window and
hysteresis criteria (gf180-pll row 16). Behavioral contract ported; the window
re-verified on sky130.

## Standby

**DRAFT — to be ratified.** No power-down mode in v1 — always-on whenever rails
are up (gf180-pll row 11). Confirm the same v1 scope call.

## Area

**DRAFT — to be ratified.** A budget, not a result — no layout exists. Set a
sky130-specific area budget at ratification; gf180-pll's 0.15 mm² is a 180 nm
figure and is not portable to sky130's 130 nm geometry.

## Process corners

**RATIFIED 2026-08-27** (`DR-003`, ruled via #77). The **process-corner axis**
of "PVT corner" (row 14's "all corners" and every future per-corner row) is
bound to sky130's five standard MOS/BJT process corners: `tt` (typical-
typical), `ff` (fast-fast), `ss` (slow-slow), `sf` (slow NMOS / fast PMOS),
and `fs` (fast NMOS / slow PMOS) — the five named `.lib` sections
`sky130.lib.spice` defines for `nfet_01v8`/`pfet_01v8` (confirmed against the
installed PDK; see `DR-003` *Context*).

This **adds** the two mixed-skew corners (`sf`, `fs`) that
`sim/pll/testbench/tb.json`'s prior, unratified convention omitted
(`process_corners: ["tt","ss","ff"]`). They are included on a specific,
structural argument, not generic thoroughness: `design/pfd-cp/DESIGN.md`'s
own reference-spur note identifies the charge pump's un-cascoded `MPCP`/
`MNCP` current mirror as the dominant source of `UP`/`DN` current mismatch,
and a mixed-skew corner is exactly the condition that maximizes an NMOS-vs-
PMOS speed/current differential — the case `tt`/`ss`/`ff` (which always move
both device types together) cannot exercise. Interconnect R/C skew corners
(`ll`/`hh`, and the `hl`/`lh`/`*_mm` combinations `sim/pdk.json`'s provenance
note also lists as available in this PDK) and statistical mismatch
(`mc_mm_switch`/Monte Carlo) are each a separate axis from process-corner
skew and are **not** part of this row — see `DR-003` *Alternatives
considered* for why each is deferred rather than folded in here.

## Operating temperature range

**RATIFIED 2026-08-27** (`DR-003`, ruled via #77). The **temperature axis**
of "PVT corner" is bound to **−40 °C to 125 °C**, sampled at three points:
−40 °C, 27 °C, and 125 °C. Unlike the process-corner axis (row 19), sky130's
device models carry no discrete, named temperature set to select from — the
BSIM4 model files (`sky130_fd_pr__nfet_01v8__*`) parameterize temperature
continuously via their own temperature-dependence coefficients around a
30 °C nominal (`tnom`), so the range is a verification-scope choice this row
makes explicitly rather than a PDK-provided enumeration.

−40 °C to 125 °C is the conventional industrial temperature range, and this
choice is corroborated independently of this repo's own (previously
unratified) harness convention: `2AMLogic/sky130-bandgap` — the sibling
canary on the same sky130 PDK — independently ratified the identical
−40…125 °C range for its own target spec. Crossed with row 19's process-
corner set and row 1's supply range, these three points give the full PVT
grid every future per-corner row is verified against.

---

## Verification owed

Everything. No `sim/` evidence exists yet. On ratification, each row above gains
the campaign that substantiates it, recorded per the append-only `sim/`
convention seeded from gf180-pll. Until then, this file is a set of intentions,
not results.

**Row 9 (period jitter), specifically.** Half of what this row is owed now
exists. The *extractor* stopped being the gap at #158
(`sim/harness/measure.py`'s period-jitter metric, alongside the mean frequency,
duty cycle and lock time it already derived), and the **statistical axis** — a
local-mismatch Monte Carlo population (`sim/run_corners.py <slug> --mc`) — has
been run: `sim/pll-lock-mc/records/20260924-222341-a9375a5.md` (#20), which
records a **miss** (1.584 – 3.073 % RMS across the 3 of 5 draws that locked,
against a 1.0 % bound), subject to the 50 µs-window and 200 ps-dump-grid limits
that record states.

That statistical axis has since been **graded** rather than only recorded:
`sim/pll-lock-mc/analysis/yield-evidence/klt-yield-report.json` is a `klt yield`
report over the same 5 draws against this row's ratified bound (0 % empirical
yield, 95 % CI [0, 0.7076], `cpk` −0.491), and it carries the tool's own
`sample_size.verdict: insufficient` — `n` = 3 measurable draws against a
`required_n` of 183 for a ±1 pp interval. So the campaign is a real miss *and*
an unsized one, and neither reading is withheld.

The **deterministic axis** over the ratified rows 19 × 20 × 1 PVT grid is now
*declared but not yet run*. `sim/pll-lock`'s manifest cites row 9 and carries a
`measure.jitter` block gated on the ratified 1.0 % bound (#180), so the grid's
own reducer extracts the figure at every point that locks — but no committed
`sim/pll-lock` record carries that column yet: the most recent full-grid record
(`20260905-193322-0f1934d.md`) predates both the widened window and this block.
The record is owed from the fresh 45-point run tracked by #103, which will mint
it at no extra simulation cost now that the key is declared ahead of it.

Still owed: **that full-grid record**, a finer-grid re-run of the statistical
axis able to separate the measured figure from its own
measurement-resolution floor, and — before any yield claim
is made over this row — a **sized** statistical population with the
deterministic negative control T1 item 6 requires (`sim/pll-lock-mc/analysis/README.md`
states the cost of each and why the floor is the cheaper prerequisite).
`DR-006` ratifies the target; it asserts nothing about whether the present
schematic meets it, and the miss above is a recorded design result, not a
reason to revisit the bound.
