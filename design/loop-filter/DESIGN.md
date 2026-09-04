# Passive loop filter — design rationale (issues #26, #92)

Passive charge-pump loop filter for the sky130 PLL, block 3 of 4 of the
`#14` decomposition. This document records the design choices behind
`loop_filter.sch`/`loop_filter.sym`.

**Re-sized under #92.** As first authored (#26) this filter was solved for
two inputs that have since been superseded by committed evidence: a
documented `Icp = 5 µA` placeholder (`design/pfd-cp/DESIGN.md` subsequently
landed `Icp = 10 µA`) and `Kvco = 460 MHz/V` read off `design/vco/DESIGN.md`'s
informal sanity-check table (`sim/vco/records/20260904-163130-f3ae976.md`
subsequently measured 692–1751 MHz/V across the full PVT grid). At those real
inputs the as-authored filter missed DRAFT rows 6 and 7 at several PVT points
— that is what `sim/loop-ac/records/20260904-184005-51dae17.md` recorded, and
it is why #92 re-derived the sizing below.

**The realized loop bandwidth and phase margin in this document are
simulated, not hand-calculated.** They are cited from the governing
`sim/loop-ac` record (see "Realized loop performance"); this file no longer
carries a closed-form realized-performance table, because the first
`sim/loop-ac` run showed the closed form used here overstates the margin by
roughly 8° (it approximates the `C2` pole as `1/(R1·Ceff)` and treats the
`R3`/`C3` stage as an independent pole, ignoring that `C3` also loads `CP`).
The closed form is retained below only as the **parameterization** that picks
starting values; the simulation sets the final ones.

## Forward design, not reverse-engineered

This is a textbook third-order passive RC charge-pump PLL loop filter — the
same R1/C1 zero + C2 pole + R3/C3 isolation-pole structure described in
standard PLL design texts (e.g. Gardner, Best, Razavi) and used throughout
open-source and published charge-pump PLL designs. It was authored fresh
against sky130's own precision-resistor and MiM-capacitor primitives for
this repo; nothing here originates in another chip's silicon or netlist, per
`CLAUDE.md`'s reverse-engineering-free rule. Component **values** are
derived below from this repo's own design-point inputs (Icp, Kvco, N,
f_ref — see "Design-point inputs"), two of which are now this repo's own
committed measurements and none of which are ported from
`2AMLogic/gf180-pll`'s numbers; `spec/target-spec.md` row 5 explicitly rules
out porting its Kvco figure, and the same principle is applied here to every
other input.

## Scope: standalone block, not the closed loop

`loop_filter.sch` itself is the block alone. It does not instantiate the
charge pump (`design/pfd-cp/`, issue #25), the VCO
(`design/vco/vco_ring5.sch`, issue #24), or the divider
(`design/divider/divider_intN.sch`, issue #27) — the four blocks are wired
together one level up, in `design/top/top.sch`. `CP` (this block's
current-injection input) is driven by the charge pump's output and `VCTRL`
(this block's output) drives the VCO's control input; neither connection is
made in this schematic.

The same boundary applies to the evidence: `sim/loop-ac` measures this
block's `Z(s)` for real and applies the other three blocks as a scalar loop
gain, so everything below is a statement about the *filter's* contribution
to loop dynamics, not a closed-loop result. `sim/pll-lock` is the
closed-loop campaign.

## Coordination note: the `Icp` mismatch is resolved

The first authoring of this block (#26) could not read an `Icp` from the
PFD/charge-pump sub-issue (#25), which had not landed one, so it used a
documented 5 µA placeholder and derived the R/C values from closed-form
equations parameterized by `Icp`, `Kvco`, `N` and `f_ref` specifically so a
real value could be dropped in later without a topology change. That is what
#92 did: **the filter is now sized for the `Icp = 10 µA` that
`design/pfd-cp/DESIGN.md` landed**, and the two blocks no longer disagree.
`design/pfd-cp/DESIGN.md`'s own "Coordination note" section still describes
the reconciliation as owed to `#14`; that note is stale in one direction only
— this block consumed the PFD/CP value rather than renegotiating it, so no
change to the charge pump is implied or made.

The same parameterization also absorbed the second stale input: `Kvco` now
comes from `sim/vco`'s committed measurement rather than from
`design/vco/DESIGN.md`'s informal table (see "Design-point inputs").

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

None of these are ratified spec values. `Icp` and `Kvco` are now read from
committed evidence rather than assumed; `N` and `f_ref` remain documented
design points inside their DRAFT ranges; `f_c` and `φm` are the sizing
derivation's own knobs, not contracts. The component values below are
recomputed trivially (see "Sizing derivation") if any of them moves.

| Input | Design-point value | Basis |
|---|---|---|
| `Icp` (charge-pump current) | **10 µA** | The value `design/pfd-cp/DESIGN.md` actually landed for the charge pump this filter is driven by (its own "Design-point inputs" table). Replaces #26's documented 5 µA placeholder, which existed only because #25 had not landed a current yet. |
| `Kvco` (sizing design point) | **1101 MHz/V** | The geometric mean of the 692–1751 MHz/V mean tuning slope `sim/vco/records/20260904-163130-f3ae976.md` measured across its 45-point PVT grid — `√(692 · 1751) = 1101`. See "Choosing a single `Kvco` for a fixed filter" below for why the geometric mean and not the min, max or arithmetic mean. Replaces #26's 460 MHz/V, which was read off `design/vco/DESIGN.md`'s explicitly informal single-corner sanity-check table and sits *below* the measured minimum. |
| `Kvco` (range the filter must survive) | **692 – 1751 MHz/V** | The full measured spread from the same record (692 MHz/V at `ss`/125 °C/1.62 V; 1751 MHz/V at `ff`/−40 °C/1.98 V). The sizing is *solved* at the design point above but *verified* across this whole range — the filter is fixed, the VCO gain is not. |
| `N` (feedback divide) | 20 | Design point within row 4's DRAFT range (4–64). Unchanged from #26. |
| `f_ref` (reference frequency) | 8 MHz | Design point within row 3's DRAFT range (1–25 MHz). Unchanged from #26. |
| `f_out = N · f_ref` | 160 MHz | Falls within row 2's DRAFT output band (10–200 MHz continuous) — chosen so this design point is internally self-consistent across rows 2/3/4, not just row 6/7 in isolation. |
| `A = Icp · Kvco / N` (scalar loop gain) | 550.5 at the design point; 346 – 875.5 across the `Kvco` range | The only place `Icp`, `Kvco` and `N` enter the open-loop transfer function (see "Sizing derivation"). The 2.53x spread in this one number is the whole of this block's re-sizing problem. |
| `f_c` (loop bandwidth target, at the design point) | 480 kHz | Row 6's hard ceiling is `f_c < f_ref/10` = 800 kHz. #26 targeted `f_ref/20` = 400 kHz for a 2x margin — but that margin was budgeted at the *design point*, and with a 2.53x loop-gain spread the ceiling has to be met at the *top* of the spread, where the crossover runs ~1.5x the design-point value. 480 kHz at the design point is what puts the worst-corner, top-of-spread crossover ~8 % under the ceiling (measured: 733.5 kHz, see "Realized loop performance"). |
| `φm` (phase-margin target, zero-only base) | 73° | Base target for the classic 2-pole/1-zero equations below; the realized margin is lower once the `C2` and `R3`/`C3` poles are added. #26 used 70°, sized for a single loop-gain point. 73° is what leaves ≥45° at **both** ends of the 2.53x spread across the `ll`/`hh` passive corners — at the bottom of the spread the crossover falls ~1.6x below the design point, moving it closer to the compensation zero and costing phase lead. |

## Choosing a single `Kvco` for a fixed filter

`sim/vco`'s record does not give this block one `Kvco`; it gives it a 2.53x
range (692–1751 MHz/V) that the filter cannot adapt to, because the filter is
five fixed passives. Something has to be chosen, and the choice matters:
loop gain `A` is linear in `Kvco`, so the whole 2.53x range lands directly on
the crossover frequency.

**Chosen: the geometric mean, 1101 MHz/V.** Rationale:

- Both quantities row 6 and row 7 are written in terms of — crossover
  frequency and the phase of the loop at that frequency — are functions of
  **log** frequency. Multiplying `A` by *k* slides the crossover by roughly a
  factor of *k* along the log-frequency axis, and the phase-margin curve is
  smooth and single-peaked in that axis. Centring the design at the geometric
  mean therefore puts the ±1.59x gain excursion symmetrically either side of
  the design point, which is what maximizes the worst-case phase margin over
  the range. The arithmetic mean (1222 MHz/V) is not the centre of anything
  the loop cares about.
- Sizing at the measured **minimum** (692 MHz/V) would push the top-of-spread
  crossover far past row 6's ceiling. Sizing at the measured **maximum**
  (1751 MHz/V) buys row-6 headroom but starves the bottom of the spread of
  phase lead — the crossover there falls to roughly a third of the design
  point, close enough to the compensation zero to drop the margin under 45°.
- `design/vco/DESIGN.md`'s informal table is deliberately **not** used. Row 5
  of `spec/target-spec.md` already says the `Kvco` bound must be re-derived
  rather than ported, and `sim/vco`'s committed record is the only measured
  evidence in this repo about what the ring actually does.

**Stated trade-off.** Sizing for the geometric mean does *not* make the whole
range comfortable, only survivable: the measured worst case (see "Realized
loop performance") clears row 6 by 8 % and row 7 by 3.3°, and it costs a
3.7x increase in this block's capacitor area (see "Area"). Both worst cases
sit at the ends of the `Kvco` spread. **A 2.53x uncontrolled loop-gain spread
is the root cause, not the filter's sizing**, and the levers that actually
fix it are outside this block: a ratified row-5 `Kvco` bound argued in a
decision record, a VCO re-design that flattens the tuning slope, or an `Icp`
trim in the charge pump (`design/pfd-cp/DESIGN.md` explicitly does not
implement one). This block absorbs the spread with area because that is the
only lever it owns.

One further scaling relation, recorded here because it is not obvious and a
future re-pick of the design point should know it: at a *fixed* `f_out`, the
`R1` this derivation can afford is `2π·f_out / (10·Icp·Kvco_max)` — it does
not depend on `f_ref` at all — while the required `C1` scales as `1/f_ref`.
The filter's capacitor area is therefore roughly inversely proportional to
the `f_ref` its design point is chosen at. This block's design point is
`f_ref` = 8 MHz, near the low end of row 3's 1–25 MHz DRAFT range; re-picking
it higher would shrink `C1` proportionally. That is a design-point decision
with consequences well beyond this block (it changes which `N`, and therefore
which divider configuration, the loop is optimized for), so it is recorded as
an option, not taken here.

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

with `ωc = 2π·f_c` and `φm` the 73° base target above. Note that
`Icp·Kv/(2π·N) = Icp·Kvco/N = A`, the scalar loop gain — the three inputs
`Icp`, `Kvco` and `N` enter only through that product, which is why
re-sizing for a landed `Icp` and a measured `Kvco` is arithmetic on `A` and
not a topology change.

**Step 2 — `C2` (first extra pole)**, sized as `C1/K2` with `K2 = 20`
(pole placed roughly a decade-plus beyond `ωc` so it costs only a modest
slice of phase margin — the standard rule of thumb for this filter family).

**Step 3 — `R3`, `C3` (isolating pole)**, `R3` fixed at a convenient 10 kΩ,
`C3` chosen to place this pole at `K3 = 10×ωc` — comfortably above the loop
crossover so its phase cost at `ωc` is small, while still well below `f_ref`
so it meaningfully attenuates the reference spur.

**Step 4 — verify the realized `ωc` and phase margin by simulation, across
the whole `Kvco` range and the passive corners.** This step is where the
first authoring of this block went wrong, and it is worth being explicit
about why. #26 closed the derivation with a closed-form check:

```
phase(G(jω)) = −180° + arctan(ω·R1·C1) − arctan(ω·R1·Ceff) − arctan(ω/p3)
  where Ceff = C1·C2/(C1+C2),  p3 = 1/(R3·C3)
PM = 180° + phase(G(jω))
```

That expression is **optimistic by roughly 8°**. It approximates the `C2`
pole as `1/(R1·Ceff)` and treats the `R3`/`C3` stage as an independent pole,
but in the real network `C3` also loads the `CP` node, so the exact `Z(s)`
rolls off faster and the phase at crossover is worse. Measured against
`sim/loop-ac/records/20260904-184005-51dae17.md` at the identical operating
point (`tt`/−40 °C, the as-authored values, `A` = 115), the closed form
claimed 381 kHz / 57.6° where the simulation reports 365 kHz / 49.8°.

The closed form is therefore used here only to **parameterize** — to turn a
target (`f_c`, `φm`) into starting values for `R1`/`C1`/`C2`/`C3` that are in
the right neighbourhood. The final values are the ones the `sim/loop-ac`
campaign confirms, and the `f_c` and `φm` targets in "Design-point inputs"
were themselves adjusted until the *simulated* worst case across the `Kvco`
range and the `ll`/`hh` passive corners cleared both DRAFT bounds. No number
in "Realized loop performance" below is hand-calculated.

## Component values

| Device | sky130 primitive | Parameters | Value (`tt`) | Was (#26) |
|---|---|---|---|---|
| `R1` | `sky130_fd_pr__res_xhigh_po` | `W=1µm L=2.53µm` | 5.23 kΩ | 21.7 kΩ (`L=10.3µm`) |
| `C1` | `sky130_fd_pr__cap_mim_m3_1` | `W=L=322µm` | 207.6 pF | 53.25 pF (`W=L=163µm`) |
| `C2` | `sky130_fd_pr__cap_mim_m3_1` | `W=L=72µm` | 10.42 pF | 2.47 pF (`W=L=35µm`) |
| `R3` | `sky130_fd_pr__res_xhigh_po` | `W=1µm L=5µm` | 10.47 kΩ | 10.47 kΩ (unchanged) |
| `C3` | `sky130_fd_pr__cap_mim_m3_1` | `W=L=40µm` | 3.23 pF | 3.56 pF (`W=L=42µm`) |

Derived pole/zero locations at these values (`tt`): compensation zero
`1/(2π·R1·C1)` = 146 kHz, `C2` pole `1/(2π·R1·Ceff)` = 3.07 MHz, `R3`/`C3`
pole `1/(2π·R3·C3)` = 4.71 MHz (still below `f_ref` = 8 MHz, so the third
pole keeps doing the reference-spur job it was added for).

**On how the resistor value is computed.** #26 quoted `R = 2000·L/W/mult` Ω
off `res_xhigh_po.sym`. That is the drawn-dimension sheet formula; the PDK's
own subcircuit (`sky130_fd_pr__res_xhigh_po.model.spice`) uses *effective*
dimensions, `R = rsheet·(L − 0.0592)/(W − 0.056)` with `rsheet` = 2000 Ω/□.
At `W = 1µm` the width bias alone is a 5.9 % error, and it grows as `L`
shrinks — at the short `L = 2.53µm` this re-sizing needs, the drawn formula
would be off by 3.4 %, which lands directly on the crossover frequency. The
values in the table above are the **effective**-dimension ones, and they are
what the simulation confirms. Capacitor values likewise use the subcircuit's
own expression, `C = camimc·wc·lc + 2·cpmimc·(wc + lc)·2` with
`wc = W + m3_dw`, `m3_dw` = −0.025 µm and typical `camimc` = 2 fF/µm²,
`cpmimc` = 0.19 fF/µm — numerically within 0.1 % of the
`W·L·2 fF/µm² + (W+L)·0.38 fF/µm` form #26 quoted. Note also that
`cap_mim_m3_1`'s `MF` parameter appears only in its mismatch term and does
**not** multiply the capacitance, so `MF` is left at 1 and area is bought
with `W`/`L`.

**Targets vs. realized, so the derivation can be checked.** With `A` = 550.5,
`f_c` = 480 kHz, `φm` = 73°, `K2` = 20 and `K3` = 10, the closed form asks
for `R1` = 5239 Ω, `C1` = 207.0 pF, `C2` = 10.35 pF, `C3` = 3.17 pF; the
integer-micron geometries above deliver 5235 Ω, 207.6 pF, 10.42 pF and
3.23 pF — each within 2 % of its target.

## Realized loop performance

**Governing evidence: `sim/loop-ac/records/20260904-204534-3fcd920.md`**
(21 PVT points — seven process corners including the `ll`/`hh` passive-skew
corners × three temperatures — × four swept loop-gain design points; it
supersedes `20260904-184005-51dae17.md`, which measured the as-authored
values). Nothing in this section is hand-calculated; every number below is
copied from that record's own worst-case table.

Worst case over the **measured `Kvco` range** the filter is designed for
(692–1751 MHz/V at `Icp` = 10 µA, `N` = 20):

| Loop-gain point | `Kvco` | Worst `f_c` | Row 6 (`f_c` < 800 kHz) | Worst phase margin | Row 7 (≥ 45°) |
|---|---|---|---|---|---|
| `measured-kvco-min` | 692 MHz/V | 329.8 kHz (`hh`/27 °C) | **meets**, 59 % under the ceiling | 48.4° (`ll`/125 °C) | **meets**, +3.4° |
| `lf-sizing-point-v2` | 1101 MHz/V | 495.2 kHz (`hh`/27 °C) | **meets**, 38 % under | 53.9° (`ll`/125 °C) | **meets**, +8.9° |
| `measured-kvco-max` | 1751 MHz/V | 733.5 kHz (`hh`/27 °C) | **meets**, 8.3 % under | 48.3° (`hh`/27 °C) | **meets**, +3.3° |

**All 63 in-range measurements (21 PVT points × 3 loop-gain points) meet both
DRAFT bounds.** The two worst cases sit, as expected, at opposite ends of the
`Kvco` spread and at opposite passive corners: row 6 is tightest at the top
of the spread on `hh` (high R *and* high C), row 7 at the bottom of the
spread on `ll`. The margins are real but not generous — 8.3 % and 3.3° — and
that is the honest price of a fixed filter serving a 2.53x loop-gain range
(see "Choosing a single `Kvco` for a fixed filter").

**One recorded miss, and what it is not.** That record also sweeps a fourth
loop-gain point, `cp-landed-icp` (`Icp` = 10 µA, `Kvco` = 460 MHz/V), which
misses row 7 at the three `ll` points (42.2–42.4°). It is retained verbatim
from the superseded record purely so the two filters can be compared at an
identical loop gain, and **460 MHz/V is below the 692 MHz/V floor `sim/vco`
measured** — the loop does not operate there. The miss is reported rather
than dropped, because narrowing a sweep to improve a table is exactly the
kind of laundering `CLAUDE.md` forbids; it is not a statement about this
design's contracted space.

**Comparison with the as-authored filter**, from the superseded record
`20260904-184005-51dae17.md`, which measured the same `measured-kvco-min` /
`measured-kvco-max` points on the #26 component values:

| Loop-gain point | As authored (#26) | Re-sized (#92) |
|---|---|---|
| `measured-kvco-min` | 880.1 kHz / 32.7° — **missed both rows** at all 21 points | 329.8 kHz / 48.4° — meets both |
| `measured-kvco-max` | 1.596 MHz / 16.5° — **missed both rows** at all 21 points | 733.5 kHz / 48.3° — meets both |

Derived pole/zero locations at the new values are listed under "Component
values"; the `R3`/`C3` pole stays at 4.71 MHz, below `f_ref` = 8 MHz, so it
still provides the reference-frequency attenuation (row 10, reference spur)
that was the specific motivation for making this filter 3rd order.

**What this evidence does not cover.** The `sim/loop-ac` campaign simulates
only the filter's own `Z(s)`; the charge pump and VCO enter as the scalar
`A = Icp·Kvco/N`. It therefore says nothing about charge-pump output
impedance, `UP`/`DN` mismatch, dead-zone behaviour, the VCO control node's
own input capacitance, or the sampled nature of a real phase detector. Read
the record's own limitations section before citing it further.

## Vctrl headroom analysis (row 13's owed headroom analysis, first pass)

`DR-001` explicitly hands the charge pump and loop filter a headroom
analysis obligation for row 13 (supply sensitivity) — this is that
analysis's first pass for this block, not the full verified result (which
still needs a transient testbench that models the charge pump's actual
current pulses; `sim/loop-ac` is a small-signal AC campaign and measures
nothing about ripple).

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
Icp · R1 = 10 µA × 5.23 kΩ ≈ 52 mV
```

Read against the two candidate reference windows:

- **52 mV / 1.8 V rail ≈ 2.9 %** of the full supply.
- **52 mV / ~0.8 V** (the VCO's own demonstrated usable `VCTRL` span,
  `design/vco/DESIGN.md`'s 0.8–1.6 V table) **≈ 6.5 %** — the tighter,
  more relevant comparison per `DR-001`'s framing (headroom is scarce
  relative to the *tuning* range that actually matters, not the full rail).

**This got better, not worse, when `Icp` doubled.** #26's estimate was
103 mV (5 µA × 20.6 kΩ). Ripple scales as `Icp · R1`, and the re-sizing cut
`R1` by 4.1x while `Icp` only doubled, so the net excursion halves. The
mechanism is worth naming: a higher loop gain forces a *smaller* `R1` to
hold the crossover under row 6's ceiling, and `R1` is exactly the resistor
the charge-pump pulse develops its step across.

**Design intent stated plainly.** A single-pulse ~52 mV excursion against a
~0.8 V usable tuning window is a modest fraction — comfortably inside
`DR-001`'s accepted-cost framing that this rail leaves "roughly a third" of
gf180-pll's headroom. This is still a *design-time estimate*, not a verified
result: it assumes a worst-case single full-`Icp`-width pulse (the actual
ripple in lock is smaller, since steady-state correction pulses are much
narrower than a full reference period) and ignores `C2`/`C3`'s own smoothing
of that same transient. A transient testbench still owes the verified
number; if it shows this ripple is a binding constraint on row 9 (period
jitter) or row 13 itself, the natural levers are a smaller `Icp` (shrinks
ripple linearly, grows `C1`/area for the same zero placement) or a smaller
`R1` (shrinks ripple linearly, at the same area cost trade against `C1`) —
both are straightforward re-derivations from the parameterized equations
above, not a topology change.

## Area — a real, documented cost that grew

Total on-chip MiM capacitor area at these component values:

```
C1 (322µm x 322µm) + C2 (72µm x 72µm) + C3 (40µm x 40µm)
  = 103,684 + 5,184 + 1,600 µm² = 110,468 µm² ≈ 0.1105 mm²
```

That is **3.7x** #26's 29,558 µm² (0.0296 mm²), and it is the single largest
cost of this re-sizing. It is documented candidly here rather than minimized,
per the same pattern `design/vco/DESIGN.md` and `design/divider/DESIGN.md`
use for their own open gaps.

**Why it grew.** Filter capacitance scales as `A/ωc²` with
`A = Icp · Kvco / N`. Between #26 and #92, `A` at the sizing point went from
115 to 550.5 — 4.8x — because `Icp` doubled (5 → 10 µA, a landed value, not
an assumption) and `Kvco` went from an informal 460 MHz/V to a measured
1101 MHz/V design point. Row 6's ceiling caps how much of that can be paid
back by raising `ωc`: the crossover could only move from 400 kHz to 480 kHz
at the design point before the top of the `Kvco` spread ran into the 800 kHz
ceiling. The remainder lands on `C1`. #26 predicted exactly this dependency
("filter capacitance in these equations scales with `Icp · Kvco / N`") and
guessed the real values would push it *down*; the measurements pushed it up.

**What would shrink it**, in decreasing order of leverage:

- **A tighter `Kvco`.** The 692–1751 MHz/V spread is what forces the design
  point up and the row-6 margin down; a ratified row-5 bound or a VCO
  re-design that flattens the tuning slope would shrink `C1` roughly
  proportionally.
- **A smaller `Icp`.** `C1` is linear in `Icp`. This is the charge pump's
  call, not this block's, and `design/pfd-cp/DESIGN.md` argues its 10 µA on
  its own device-operating-region grounds.
- **A higher-`f_ref` design point.** Per the scaling relation recorded under
  "Choosing a single `Kvco` for a fixed filter", `C1` goes as `1/f_ref` at
  fixed `f_out`; this block's 8 MHz sits near the bottom of row 3's DRAFT
  1–25 MHz range.

No layout exists for this block yet (`spec/target-spec.md` row 18, area
budget, stays DRAFT and has no number) — this is a schematic-stage area
*estimate* from the primitive capacitor model, not a layout measurement.

## No spec edits

Nothing in `spec/target-spec.md` is edited by #26 or by #92. Rows 5 (Kvco),
6 (loop bandwidth), 7 (phase margin), 13 (supply sensitivity), and 18 (area)
all stay DRAFT; the numbers above are design-time evidence toward a future
decision, not a ratification. In particular, the fact that the re-sized
filter now *meets* the DRAFT row-6 and row-7 bounds across the measured
`Kvco` range does not ratify either row, and the `Kvco` design point chosen
here (1101 MHz/V) is a **sizing** choice for this block, not a proposed
row-5 bound — row 5 asks for "a fixed-filter-compatible bound", which is a
constraint on the VCO, and arguing one is a decision record's job. Any change
to those rows still requires its own decision record
(`spec/decision-records/DR-NNN`), argued on its own merits, per `CLAUDE.md`.

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

## Verification performed

**For the re-sizing (#92):**

- `sim/loop-ac` re-run against the re-sized filter across its full grid —
  seven process corners (`tt`/`ff`/`ss`/`sf`/`fs` plus the `ll`/`hh`
  passive-skew corners) × three temperatures × four swept loop-gain design
  points, 21/21 points passing the harness's plumbing *and* measurement
  criteria. Record: `sim/loop-ac/records/20260904-204534-3fcd920.md`,
  superseding `20260904-184005-51dae17.md` per `sim/README.md`'s append-only
  convention. Results are summarized under "Realized loop performance"; the
  record is the authority, this file is not.
- `xschem -n -q -x --rcfile sim/xschemrc design/loop-filter/loop_filter.sch
  -o design/loop-filter/netlist` re-run after the value edits — exits 0, and
  `netlist/loop_filter.spice` carries the re-sized `W`/`L` on all five
  devices with the topology unchanged.

**For the original authoring (#26):**

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
  were computed with a scratch Python script (not committed — informal
  design-time sanity check only, same status as `design/vco/DESIGN.md`'s own
  informal transient check). #92 replaced the loop-bandwidth and
  phase-margin figures with the simulated record above after that same
  campaign showed the closed form optimistic by ~8°; the `Icp · R1` ripple
  estimate is still a hand calculation and is still labelled as one.
