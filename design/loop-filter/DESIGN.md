# Passive loop filter — design rationale (issue #26)

Passive charge-pump loop filter for the sky130 PLL, block 3 of 4 of the
`#14` decomposition. Standalone block: this document records the design
choices behind `loop_filter.sch`/`loop_filter.sym`, not a verified result.
**No `sim/` testbench exists for this block yet** (that is #23 plus whatever
sub-issue runs the sky130 PVT campaign once the rows this design targets are
ratified) — every number below is a design target or a hand-calculated
sanity check, never a claim against `spec/target-spec.md`.

## Forward design, not reverse-engineered

This is a textbook third-order passive RC charge-pump PLL loop filter — the
same R1/C1 zero + C2 pole + R3/C3 isolation-pole structure described in
standard PLL design texts (e.g. Gardner, Best, Razavi) and used throughout
open-source and published charge-pump PLL designs. It was authored fresh
against sky130's own precision-resistor and MiM-capacitor primitives for
this repo; nothing here originates in another chip's silicon or netlist, per
`CLAUDE.md`'s reverse-engineering-free rule. Component **values** are
derived below from this repo's own design-point assumptions (Icp, Kvco, N,
f_ref — see "Design-point inputs"), not ported from `2AMLogic/gf180-pll`'s
numbers; `spec/target-spec.md` row 5 explicitly rules out porting its Kvco
figure, and the same principle is applied here to every other input.

## Scope: standalone block, not the closed loop

This issue authors the loop-filter block only. It is not wired to the
charge pump (`design/pfd-cp/`, issue #25, not yet landed at authoring time),
the VCO (`design/vco/vco_ring5.sch`, issue #24), or the divider
(`design/divider/divider_intN.sch`, issue #27) here — that is the
integration sub-issue tracked on `#14`. `CP` (this block's current-injection
input) is documented as "driven by the charge pump's output" and `VCTRL`
(this block's output) as "drives the VCO's control input" as the intended
usage, but no hierarchical instantiation of either sibling symbol happens in
this schematic.

## Coordination note: PFD/CP (#25) had not landed a value at authoring time

The issue text flags that this block's sizing is most accurate once the
PFD/charge-pump sub-issue (#25) has landed its own `Icp` value, and permits
"a first-pass sizing against the DRAFT targets ... as an acceptable starting
point" if it hasn't. At authoring time, #25 was still `loom:building` with no
`design/pfd-cp/` committed on `main` and no uncommitted work in its own
worktree to coordinate against (verified by inspecting
`.loom/worktrees/issue-25`: clean working tree, `HEAD` behind `main`, no
`design/pfd-cp/` present). This design therefore uses a documented **Icp
design-point assumption** (see below), not a value read from #25. The
filter's R/C values are derived from closed-form equations parameterized by
`Icp`, `Kvco`, `N`, and `f_ref` (see "Sizing derivation" below) specifically
so a future value from #25 (or a re-derived `Kvco` from a VCO tuning
campaign) can be dropped in and the component values recomputed without a
topology change.

## Filter order: 3rd order, not 2nd order

Two standard passive charge-pump filter orders were the candidates:

- **2nd order** (a single `R1`+`C1` series zero branch, plus a shunt `C2` at
  the charge-pump node for a first extra pole) — the minimum structure that
  gives a charge-pump PLL a stable, non-zero phase margin (the zero) while
  adding one pole beyond the two the loop already has (PFD/CP integrator +
  VCO integrator) to attenuate reference-frequency ripple reaching `VCTRL`.
- **3rd order** (chosen: adds `R3`+`C3`, an additional series-R/shunt-C
  stage between the charge-pump node and `VCTRL`) — one more pole, isolating
  the voltage the VCO actually sees from the charge-pump node's own
  switching transients.

**Chosen: 3rd order.** Rationale:

- `spec/target-spec.md` row 13 (supply sensitivity) and `DR-001`'s own
  *Consequences* section both flag that the 1.8 V core rail leaves the
  charge pump and loop filter "roughly a third of gf180-pll's 3.3 V
  control-voltage window" and that "the same absolute ripple consumes a
  larger fraction of a 1.8 V Vctrl window, so gf180-pll's ripple limit must
  be re-derived smaller, not larger." A tighter ripple budget is exactly the
  case for spending one more filter pole on spur suppression rather than
  minimizing filter order.
- `R3`+`C3` sits between the charge-pump node and the VCO's control input,
  and the VCO's control node is a MOSFET gate — no static current flows
  through `R3` in steady state (see "Vctrl headroom analysis" below), so
  this extra pole is close to free in DC accuracy terms: it does not
  introduce a steady-state IR-drop error at `VCTRL`, only a settling-time
  cost during transients (an additional real pole in the loop, priced into
  the phase-margin budget below).
- This is the standard move in published charge-pump PLL designs once a
  design needs more reference-spur attenuation than a 2nd-order filter
  gives without shrinking loop bandwidth further (which would cost lock
  time, row 8) — spend an extra, lightly-loaded pole instead.

## Topology

```
        R1            C2                R3
CP o----/\/\----+  +--||--+   CP o------/\/\------+
                 |  |      |                       |
                Z1  |     GND                     VCTRL
                 |  |                               |
                C1  |                               C3
                 |  |                               |
                GND-+                              GND
```

(Drawn as two views of the same node for clarity — `CP` is a single node in
the schematic.) At the charge-pump node `CP`: `R1` in series with `C1`
(`CP`→`Z1`→`GND`) forms the loop's compensation zero; `C2` (`CP`→`GND`,
shunt) adds the filter's first non-zero pole. From `CP`, `R3` in series to
`VCTRL`, with `C3` (`VCTRL`→`GND`) forming the third, isolating pole that
filters what the VCO actually sees.

## Design-point inputs

Every input below is a **first-pass design-point assumption**, chosen to be
self-consistent with the DRAFT spec rows it depends on and, where possible,
grounded in evidence already in this repo (not ported from gf180-pll). None
of these are ratified spec values, and this filter's own component values
are recomputed trivially (see "Sizing derivation") once a real value lands.

| Input | Design-point value | Basis |
|---|---|---|
| `Icp` (charge-pump current) | 5 µA | First-pass assumption — PFD/CP (#25) had not landed its own value at authoring time (see "Coordination note" above); a modest current keeps ripple (below) and filter-cap area from both scaling up. |
| `Kvco` | 460 MHz/V | This repo's own gentlest locally-observed VCO gain, taken directly from `design/vco/DESIGN.md`'s sanity-check table (the `VCTRL` = 1.4 V → 1.6 V segment: `(1090 − 998) MHz / 0.2 V ≈ 460 MHz/V`) — the least-aggressive slope that table shows, used here as the best current same-repo evidence toward "a fixed-filter-compatible bound" (row 5) without inventing a number or porting gf180-pll's 150 MHz/V (row 5 explicitly rules that out). |
| `N` (feedback divide) | 20 | Design point within row 4's DRAFT range (4–64). |
| `f_ref` (reference frequency) | 8 MHz | Design point within row 3's DRAFT range (1–25 MHz). |
| `f_out = N · f_ref` | 160 MHz | Falls within row 2's DRAFT output band (10–200 MHz continuous) — chosen so this design point is internally self-consistent across rows 2/3/4, not just row 6/7 in isolation. |
| `f_c` (loop bandwidth target) | ≈ f_ref / 20 ≈ 400 kHz | Row 6's hard ceiling is `f_c < f_ref/10` (800 kHz here); targeting `f_ref/20` leaves a 2x margin under the ceiling for corner-to-corner variation not modeled by this hand calculation. |
| `φm` (phase-margin target, zero-only base) | 70° | A base target for the classic 2-pole/1-zero design equations (see below), chosen high enough that the *realized* margin after adding the `C2` and `R3`/`C3` poles still clears row 7's ≥45° floor with comfortable headroom — the base target is not itself the delivered margin. |

## Sizing derivation

Standard type-II charge-pump PLL open-loop transfer function, with the
3rd-order filter's impedance `Z(s)`:

```
G(s) = (Icp · Kv) / (2π · N · s) · Z(s) / s     [Kv = 2π·Kvco, rad/s/V]
```

**Step 1 — `R1`, `C1` (the zero), from the classic 2-element formulas**
(ignoring `C2`/`C3` initially, then verifying the realized margin below with
them included):

```
R1·C1 = tan(φm) / ωc          [places the zero to hit φm at ωc]
C1    = Icp·Kv·sec(φm) / (2π·N·ωc²)   [sets |G(jωc)| = 1]
```

with `ωc = 2π·f_c` and `φm` the 70° base target above.

**Step 2 — `C2` (first extra pole)**, sized as `C1/K2` with `K2 = 20`
(pole placed roughly a decade-plus beyond `ωc` so it costs only a modest
slice of phase margin — the standard rule of thumb for this filter family).

**Step 3 — `R3`, `C3` (isolating pole)**, `R3` fixed at a convenient 10 kΩ,
`C3` chosen to place this pole at `K3 = 10×ωc` — comfortably above the loop
crossover so its phase cost at `ωc` is small, while still well below `f_ref`
so it meaningfully attenuates the reference spur.

**Step 4 — verify the realized `ωc` and phase margin numerically**, solving
`|G(jω)| = 1` for the actual crossover (magnitude now includes `C2` and
`R3`/`C3`'s contribution, which lowers the crossover slightly from the
`C1`-only estimate) and evaluating the full phase expression at that
frequency:

```
phase(G(jω)) = −180° + arctan(ω·R1·C1) − arctan(ω·R1·Ceff) − arctan(ω/p3)
  where Ceff = C1·C2/(C1+C2),  p3 = 1/(R3·C3)
PM = 180° + phase(G(jω))
```

## Component values

| Device | sky130 primitive | Parameters | Resulting value |
|---|---|---|---|
| `R1` | `sky130_fd_pr__res_xhigh_po` | `W=1µm L=10.3µm` | 20.6 kΩ |
| `C1` | `sky130_fd_pr__cap_mim_m3_1` | `W=L=163µm` | 53.26 pF |
| `C2` | `sky130_fd_pr__cap_mim_m3_1` | `W=L=35µm` | 2.48 pF |
| `R3` | `sky130_fd_pr__res_xhigh_po` | `W=1µm L=5µm` | 10.0 kΩ |
| `C3` | `sky130_fd_pr__cap_mim_m3_1` | `W=L=42µm` | 3.56 pF |

Resistor value from the primitive's own sheet-resistance model
(`R = 2000·L/W/mult` Ω, `res_xhigh_po`'s extra-high-sheet-rho poly — chosen
over the lower-sheet-rho `res_high_po` specifically to keep the physical
resistor length manageable at these kΩ-range values). Capacitor value from
`cap_mim_m3_1`'s own area-plus-perimeter model
(`C = MF·(W·L·2 fF/µm² + (W+L)·0.38 fF/µm)`). Both formulas are read
directly off each symbol's own `.sym` file in the sky130 PDK's xschem
library (`sky130_fd_pr/res_xhigh_po.sym`, `sky130_fd_pr/cap_mim_m3_1.sym`),
not assumed.

**Realized loop performance at these (rounded) component values** — a hand
calculation per the equations above, not a simulation result:

| Metric | Value | Target |
|---|---|---|
| Realized `f_c` | ≈ 381 kHz | Row 6: `f_c < f_ref/10` = 800 kHz — realized value is 4.8 % of `f_ref`, well inside the ceiling. |
| Realized phase margin | ≈ 57.6° | Row 7: ≥ 45° everywhere in the contracted space — realized value clears the floor by ~13° at this one design point (not verified across corners). |
| Zero frequency `1/(R1·C1)` | ≈ 145 kHz | — |
| `C2` pole | ≈ 3.3 MHz | — |
| `R3`/`C3` pole | ≈ 4.5 MHz | Below `f_ref` (8 MHz) — provides meaningful additional attenuation at the reference frequency itself (row 10, reference spur), the specific motivation for the 3rd pole. |

## Vctrl headroom analysis (row 13's owed headroom analysis, first pass)

`DR-001` explicitly hands the charge pump and loop filter a headroom
analysis obligation for row 13 (supply sensitivity) — this is that
analysis's first pass for this block, not the full verified result (which
needs a real `Icp` from #25 and a transient/AC testbench, neither of which
exist yet).

**DC operating point.** In lock, the charge pump's *average* current into
the filter is zero (equal up/down pulse charge), so `R1` and `R3` carry no
average DC current in steady state — neither resistor introduces a
steady-state IR-drop error at `VCTRL`. `VCTRL`'s DC level is set entirely by
where `C1`/`C2`/`C3` equilibrate, which is wherever the VCO's own control
input needs to sit (per `design/vco/DESIGN.md`'s demonstrated free-running
range, roughly 0.8–1.6 V) — the loop filter's passive components do not by
themselves constrain that DC level.

**Ripple (AC) excursion.** Each charge-pump correction pulse of current
`Icp` flowing briefly through `R1` produces a peak voltage step of
`Icp · R1`:

```
Icp · R1 = 5 µA × 20.6 kΩ ≈ 103 mV
```

Read against the two candidate reference windows:

- **103 mV / 1.8 V rail ≈ 5.7 %** of the full supply.
- **103 mV / ~0.8 V** (the VCO's own demonstrated usable `VCTRL` span,
  `design/vco/DESIGN.md`'s 0.8–1.6 V table) **≈ 12.9 %** — the tighter,
  more relevant comparison per `DR-001`'s framing (headroom is scarce
  relative to the *tuning* range that actually matters, not the full rail).

**Design intent stated plainly.** A single-pulse ~103 mV excursion against
a ~0.8 V usable tuning window is a real but not disqualifying fraction —
consistent with `DR-001`'s accepted-cost framing that this rail leaves
"roughly a third" of gf180-pll's headroom, not zero headroom. This is a
*design-time estimate*, not a verified result: it assumes a worst-case
single full-`Icp`-width pulse (the actual ripple in lock is smaller, since
steady-state correction pulses are much narrower than a full reference
period) and ignores `C2`/`C3`'s own smoothing of that same transient. The
future PVT/transient testbench campaign (gated on #25 landing a real `Icp`
and #23's testbench infrastructure) owes the verified number; if it shows
this ripple is a binding constraint on row 9 (period jitter) or row 13
itself, the natural levers are a smaller `Icp` (shrinks ripple linearly,
grows `C1`/area for the same zero placement) or a smaller `R1` (shrinks
ripple linearly, at the same area cost trade against `C1`) — both are
straightforward re-derivations from the parameterized equations above, not
a topology change.

## Area — a real, documented cost

Total on-chip MiM capacitor area at these component values:

```
C1 (163µm x 163µm) + C2 (35µm x 35µm) + C3 (42µm x 42µm)
  = 26,569 + 1,225 + 1,764 µm² = 29,558 µm² ≈ 0.0296 mm²
```

This is a materially large single-block area cost for a v1 canary design —
documented candidly here rather than minimized, per the same pattern
`design/vco/DESIGN.md` and `design/divider/DESIGN.md` use for their own
open gaps. It is expected to shrink once real inputs land: filter
capacitance in these equations scales with `Icp · Kvco / N`, so a smaller
real `Icp` from #25, or a lower re-derived `Kvco` from a future VCO
resizing/tuning campaign (`design/vco/DESIGN.md`'s own noted escalation
path), both shrink `C1` (and proportionally `C2`, `C3`) directly. No layout
exists for this block yet (`spec/target-spec.md` row 18, area budget, stays
DRAFT) — this is a schematic-stage area *estimate* from the primitive
capacitor model, not a layout measurement.

## No spec edits

Nothing in `spec/target-spec.md` is edited by this issue. Rows 5 (Kvco), 6
(loop bandwidth), 7 (phase margin), 13 (supply sensitivity), and 18 (area)
all stay DRAFT; the calculations above are design-time evidence toward a
future decision, not a ratification. Any change to those rows still
requires its own decision record (`spec/decision-records/DR-NNN`), argued on
its own merits, per `CLAUDE.md`.

## Files

- `loop_filter.sch` — top schematic (5 passive-device instances: `R1`,
  `C1`, `C2`, `R3`, `C3`), no active devices, no `VDD` pin (purely passive,
  draws no supply current — the one deliberate divergence from the
  VDD/GND/in/out pin shape the VCO and divider blocks both use, because
  unlike those two blocks this one genuinely has nothing to tie to a
  supply rail).
- `loop_filter.sym` — block symbol (`CP` in, `GND` inout, `VCTRL` out), for
  the future integration schematic to instantiate.
- `netlist/loop_filter.spice` — connectivity-only netlist snapshot,
  generated and verified per the command in `../README.md`.

## Verification performed for this issue

- `xschem -n -q -x --rcfile sim/xschemrc design/loop-filter/loop_filter.sch
  -o design/loop-filter/netlist` — exits 0, no stdout/stderr output (no
  netlister errors or warnings). The resulting netlist's five device lines
  match the topology described above exactly (`XR1 Z1 CP GND ...`, `XC1 Z1
  GND ...`, `XC2 CP GND ...`, `XR3 VCTRL CP GND ...`, `XC3 VCTRL GND ...`).
- The symbol (`loop_filter.sym`) was checked by instantiating it from a
  throwaway top-level schematic (not committed) and confirming xschem
  descends into `loop_filter.sch` and expands the full 5-device subcircuit
  under the instance call `X<name> CP GND VCTRL loop_filter` — i.e. the
  symbol's pin order matches the schematic's pin declaration order and
  hierarchical instantiation nets correctly, ready for the future
  integration sub-issue. (The same throwaway-instantiation check, run
  against the already-merged `design/vco/vco_ring5.sym` for comparison,
  reproduces the same nonzero `xschem` exit code this check itself
  produces — confirming that exit code is an artifact of a dangling
  top-level `ipin`/`opin` port structure in this checker pattern, common to
  both blocks, not a defect specific to this new symbol.)
- The hand-calculated loop-bandwidth, phase-margin, and Vctrl-ripple numbers
  above were computed with a scratch Python script (not committed — informal
  design-time sanity check only, same status as `design/vco/DESIGN.md`'s own
  informal transient check).
