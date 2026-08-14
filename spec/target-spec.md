# PLL target specification

- **Status**: **RATIFIED (row 0) — 2026-08-13, via `DR-001` in #1.**
  The **supply flavor is settled**: the 1.8 V core
  (`nfet_01v8`/`pfet_01v8`). That row is binding, and design/sim/layout work
  may now lock to it.
  **No numeric row below is ratified.** Ratifying row 0 does not ratify the
  values it gates — it makes their *stance* binding: each row's "what must be
  settled on sky130" column is now a committed obligation (re-derive / confirm /
  port-and-verify) rather than a draft intention. A row marked **re-derive**
  must be closed by a sky130 campaign producing evidence; it may not be closed
  by porting the gf180-pll number.
- **Date**: 2026-08-10 (drafted); 2026-08-13 (row 0 ratified)
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
a **status** — which for now is uniformly *DRAFT — to be ratified*. Once #1
ratifies, rows gain the gf180-pll-style corner bindings and measured/derived/
budget status words, each backed by a `sim/` evidence record.

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

Status is uniformly **DRAFT — to be ratified (#1)** until ratification.

| # | Parameter | DRAFT target (starting point) | Source | sky130 open question to resolve at ratification |
|---|---|---|---|---|
| 0 | [Supply flavor](#supply-flavor) | 1.8 V core (`nfet_01v8`/`pfet_01v8`) — **RATIFIED 2026-08-13 (DR-001, #1)** | sky130 core device menu; `DR-001` | **Settled.** I/O-class (`g5v0`-family) deferred, not rejected — revisit only on a demonstrated downstream interface constraint |
| 1 | [Supply range](#supply-range) | 1.8 V ±10 % (1.62–1.98 V) *if* 1.8 V core | derived from row 0 candidate; cf. gf180-pll 3.3 V ±10 % | confirm the tolerance band and the domain split (ring / PFD-CP / digital) on sky130 |
| 2 | [Output band](#output-band) | 10 – 200 MHz continuous, **carried from gf180-pll and NOT assumed to hold** | gf180-pll row 1 | a 130 nm ring on 1.8 V core may reach *higher* or trade range for Kvco — re-derive the band and stage count on sky130 |
| 3 | [Reference input](#reference-input) | 1 – 25 MHz, CMOS square wave, rising-edge triggered, duty 30–70 % | gf180-pll row 2 | confirm input levels for the ratified supply flavor |
| 4 | [Multiplication ratio](#multiplication-ratio) | N = 4 – 64, every integer, static configuration | gf180-pll row 3 | confirm divider retiming closes at the sky130 top frequency |
| 5 | [Kvco](#kvco) | ≤ a fixed-filter-compatible bound (gf180-pll used ≤ 150 MHz/V) | gf180-pll row 17 | the numeric bound depends on the sky130 band map — re-derive; do not port 150 |
| 6 | [Loop bandwidth](#loop-bandwidth) | f_c well below f_ref, hard ceiling `f_c < f_ref/10` | gf180-pll rows 8/8a | the kHz range depends on ratified band + filter; re-derive |
| 7 | [Phase margin](#phase-margin) | ≥ 45° everywhere in the contracted space | gf180-pll row 8a | port the criterion; re-verify the realized margin on sky130 |
| 8 | [Lock time](#lock-time) | < 100 µs to a stated lock criterion | gf180-pll row 9 | re-verify; cold-start owed to a testbench, not a budget number |
| 9 | [Period jitter](#period-jitter) | ≤ 1.0 % of the output period, RMS, conditional on a stated supply-ripple limit | gf180-pll row 5 | re-derive the ripple condition on the sky130 supply |
| 10 | [Reference spur](#reference-spur) | ≤ −55 dBc (candidate) | gf180-pll row 7 | re-derive from sky130 charge-pump mismatch, not ported |
| 11 | [Integrated RMS jitter / phase noise](#jitter-and-phase-noise) | **not spec'd** — derived-only, deliberately visible | gf180-pll rows 4/6 | confirm the same deliberate omission applies |
| 12 | [Power](#power) | a budget at a stated frequency (gf180-pll used < 5 mW at 100 MHz on 3.3 V) | gf180-pll row 10 | 1.8 V changes the power story — re-budget; do not port the mW figure |
| 13 | [Supply sensitivity](#supply-sensitivity) | supply-ripple limit + a DC-excursion Vctrl budget | gf180-pll row 12 | re-derive both budgets on the sky130 supply |
| 14 | [Output duty cycle](#output-duty-cycle) | 45 – 55 % at CLK, whole band, all corners | gf180-pll row 13 | port target; owed a measurement |
| 15 | [Output levels and drive](#output-levels-and-drive) | rail-to-rail CMOS, V_OH ≥ 0.9·VDD / V_OL ≤ 0.1·VDD into a stated load | gf180-pll row 14 | confirm the load and rail for the ratified supply |
| 16 | [Lock detector](#lock-detector) | digital `lock` output; assert window + hysteresis criteria | gf180-pll row 16 | port the behavioral contract; re-verify the window on sky130 |
| 17 | [Standby / power-down](#standby) | no power-down mode in v1 (always-on) | gf180-pll row 11 | confirm the same v1 scope call |
| 18 | [Area](#area) | a budget, not a result (no layout exists) | gf180-pll row 15 | sky130 area differs from gf180 — set a sky130 budget at ratification |

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

**DRAFT — to be ratified.** 1.8 V ±10 % (1.62–1.98 V) *conditional on the 1.8 V
core*. gf180-pll's 3.3 V ±10 % does not carry over. Confirm the tolerance and
the number of supply domains (gf180-pll split ring / reference / digital).

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

**DRAFT — to be ratified.** ≤ 1.0 % of the output period, RMS, **conditional on
a stated supply-ripple limit** (gf180-pll made the jitter target conditional on
≤ 20 mV pp VCO-supply ripple). The ripple condition is re-derived on the sky130
supply, not ported.

## Reference spur

**DRAFT — to be ratified.** ≤ −55 dBc candidate, to be re-derived from sky130
charge-pump mismatch and leakage, not ported as a number.

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

**DRAFT — to be ratified.** A supply-ripple limit plus a DC-rail-excursion
budget stated as consumed Vctrl window (gf180-pll's structure). Both budgets
re-derived on the sky130 supply.

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

---

## Verification owed

Everything. No `sim/` evidence exists yet. On ratification, each row above gains
the campaign that substantiates it, recorded per the append-only `sim/`
convention seeded from gf180-pll. Until then, this file is a set of intentions,
not results.
