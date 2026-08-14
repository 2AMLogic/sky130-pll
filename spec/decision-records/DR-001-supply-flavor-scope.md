# DR-001: sky130 supply-flavor and port scope

- **Status**: proposed
- **Date**: 2026-08-13
- **Author**: Builder agent (drafted per #3)
- **Ratifies against / input to**: #1 (Ratify the target spec — T1-gate entry).
  This record does **not** ratify anything itself; it stays `proposed` and is
  an input for the operator to rule on when closing #1.
- **Supersedes**: none

This record follows the same drafting mechanism `2AMLogic/sky130-bandgap`
used for its own supply-flavor scope decision (agents draft and argue the
scope; the operator ratifies it in the corresponding ratification issue) —
its content is written fresh from sky130 PDK device-menu facts, not copied
from that repo.

## Context

`spec/target-spec.md` row 0 ("Supply flavor") is the single prerequisite
that gates every other row in the draft spec: output band, Kvco, loop-filter
sizing, and power budget all depend on which sky130 device flavor the ring,
PFD, charge pump, and dividers are built on. The spec cannot be ratified
(#1) until this is settled, and it is deliberately scoped out to its own
decision record rather than argued inline in the spec.

`2AMLogic/gf180-pll` — the sibling canary this repo ports — is built
entirely on gf180's 3.3 V I/O device flavor (`nfet_03v3`/`pfet_03v3`), run
at 3.3 V ±10 %. sky130 does not offer that flavor; its device menu is
organized differently:

- **1.8 V core devices** (`nfet_01v8`/`pfet_01v8`, plus `_lvt`/`_hvt`
  threshold variants) — sky130's general-purpose logic/analog devices, the
  ones `sky130_fd_sc_hd` (and the other standard-cell corners) are built on,
  and the ones nearly every open sky130 digital block — including ring-
  oscillator IP already circulating in the open sky130 ecosystem (e.g.
  ring-oscillator test structures and PLL-adjacent clocking blocks built on
  Caravel/ChipIgnite-class user-project harnesses) — targets by default.
- **A medium-/high-voltage arrangement** — sky130's 5 V-tolerant I/O-class
  devices (the `g5v0`-family devices used inside `sky130_fd_io`, generally
  operated with a 3.3 V or 5 V pad-ring rail) and the higher-voltage
  `nfet_20v0`/`pfet_20v0` devices reserved for genuinely high-voltage
  applications. These exist to drive or tolerate off-chip I/O rails, not as
  a general-purpose fast-logic flavor.

Neither sky130 alternative is a literal counterpart to gf180's 3.3 V core
flavor — sky130 simply does not have a 3.3 V *core* device family the way
gf180 does. So "port the flavor" is not an available option; the choice is
between building the ring/PFD/CP/dividers on sky130's core (1.8 V) devices,
or building them on sky130's I/O-class (5 V-tolerant, typically 3.3 V-rail)
devices instead.

## Decision

**Recommend the 1.8 V core flavor** (`nfet_01v8`/`pfet_01v8`) as the device
family for the ring oscillator, PFD, charge pump, and dividers, and
**defer** the medium-/high-voltage (`g5v0`-family / I/O-class) flavor —
this record does not reject it outright, but does not find a case for it
as the primary flavor either.

This is a recommendation for #1 to rule on, not a ratification. The spec
draft (`spec/target-spec.md` row 0) already carries the 1.8 V core as its
"candidate primary," consistent with this recommendation; this record
provides the argued rationale #1 needs to close on it (or override it).

### Why the 1.8 V core is the working candidate

1. **It is where sky130's standard-cell logic lives.** `sky130_fd_sc_hd`
   (and its sibling corners) is built entirely on `nfet_01v8`/`pfet_01v8`.
   A ring-oscillator PLL is fundamentally a fast-digital-logic block (ring
   stages, PFD, digital dividers, lock detector) wrapped around one analog
   element (the charge pump / loop filter). Building the digital majority
   of the design on the same device family the standard-cell libraries use
   keeps the design compatible with sky130's normal digital flow (synthesis
   libraries, timing views, DRC/LVS decks tuned for `nfet_01v8`/`pfet_01v8`
   usage) rather than fighting an I/O-class device menu built for pad rings.
2. **It is the natural home for a fast ring.** Ring-oscillator frequency
   scales with device speed and available headroom; 1.8 V core devices are
   sky130's fastest, smallest-geometry devices, which is exactly the
   direction a wide, continuous output band wants. I/O-class devices are
   optimized for voltage tolerance and drive strength into external loads,
   not for the highest achievable ring speed at a given stage count.
3. **It matches the sky130 open-source ecosystem's default.** Ring-
   oscillator and PLL-adjacent clocking IP already circulating in the open
   sky130 ecosystem is built on the 1.8 V core devices as a matter of
   course — this is the flavor a downstream integrator plugging this PLL
   into a `sky130_fd_sc_hd`-based digital core will already expect the
   clock generator to run on, minimizing level-shifting at the
   digital-core boundary.

### Why the medium-/high-voltage flavor is deferred, not chosen

The `g5v0`-family / I/O-class devices exist to drive or tolerate an
off-chip pad rail, not to serve as a general-purpose fast-logic flavor.
Choosing them as the primary flavor would mean designing the entire ring,
PFD, charge pump, and divider chain around I/O-class devices with no
demonstrated need — nothing in the draft spec's interface contract (CMOS
`REF` input, CMOS `CLK` output, digital `lock` output) requires tolerating
an off-chip 5 V (or 3.3 V I/O) rail on the PLL core itself. The 3.3 V-class
devices would only earn consideration if a downstream integration surfaces
a genuine interface constraint — e.g. a `CLK` output that must directly
drive an off-chip load or a 3.3 V I/O ring without a level shifter — and no
such constraint has been identified. Absent that, this record does not find
a case to argue for it as primary, and defers it: if a future downstream
requirement surfaces such a need, revisit this record (or supersede it)
rather than mixing device flavors within the same core loop without cause.

## Alternatives considered

- **Port gf180-pll's exact 3.3 V flavor unchanged.** Rejected outright —
  sky130 has no `nfet_03v3`/`pfet_03v3` equivalent device family; there is
  no literal device to port to. This is not an available option, only a
  category error to rule out explicitly.
- **1.8 V core, chosen as above.** Recommended.
- **Medium-/high-voltage (`g5v0`-family / I/O-class) arrangement.**
  Deferred — see "Why the medium-/high-voltage flavor is deferred" above.
- **A mixed flavor** (e.g. 1.8 V core ring/PFD/dividers with an I/O-class
  charge pump for extra Vctrl headroom). Not evaluated in this record —
  worth naming as a future option if the 1.8 V charge-pump headroom
  consequence below (see "Consequences") proves unworkable in practice, but
  out of scope for this scoping decision, which is choosing the *primary*
  flavor, not designing the charge pump.

## Consequences

**What choosing the 1.8 V core fixes:**

- **It commits the ring stage count and band map to a 1.8 V-appropriate
  re-derivation**, not a ported gf180-pll number. gf180-pll's output band
  (10–200 MHz, gf180-pll row 1) and Kvco bound (≤150 MHz/V, gf180-pll
  row 17) were both derived from a 3.3 V, 180 nm-class ring; neither number
  is meaningful once the ring runs on 1.8 V, 130 nm-class devices — process
  and supply both changed. `spec/target-spec.md` already flags both rows as
  "carried from gf180-pll and NOT assumed to hold" / "do not port 150";
  this decision is what makes that flag concrete rather than speculative —
  a sky130 VCO tuning-range campaign on 1.8 V core devices is now the
  correctly-scoped next step, not a ported placeholder.
- **It commits the power budget to a 1.8 V re-budget.** gf180-pll's power
  figure (<5 mW at 100 MHz, gf180-pll row 10) was measured on a 3.3 V rail;
  dynamic power scales with V² for a fixed switched capacitance, so a 1.8 V
  rail is not a free win even before accounting for the different process
  node's capacitance — the number must be re-derived, not scaled by a rule
  of thumb.
- **It commits the loop filter's sizing (row 6/6a, row 5) to a
  1.8 V-appropriate re-derivation**, since loop bandwidth and phase-margin
  realization both depend on the charge-pump current range and Kvco, which
  in turn depend on the ratified band map above.

**Bad consequences this decision does not resolve, and hands to design:**

- **Reduced Vctrl headroom for the charge pump.** A 1.8 V supply gives the
  charge pump and loop filter roughly a third of the control-voltage window
  gf180-pll's 3.3 V rail gave it. Charge-pump current-source compliance
  range, switch overdrive, and the usable fraction of the Vctrl window for
  linear VCO tuning are all correspondingly tighter on 1.8 V core devices.
  This is a real design cost of the recommended flavor, not a free
  simplification — the charge pump and loop filter owe a headroom analysis
  once the flavor is ratified, and the "supply sensitivity" row (row 13,
  DC-excursion Vctrl budget) is exactly where that gets tracked.
  Sub-threshold and near-threshold behavior of `nfet_01v8`/`pfet_01v8`
  current mirrors at reduced headroom is a specific risk to design against,
  not merely note.
- **Tighter ripple tolerance.** Row 9 (period jitter, ≤1.0% conditional on
  a supply-ripple limit) and row 13 (supply sensitivity) both scale badly
  with reduced headroom: the same absolute millivolt of supply ripple
  consumes a proportionally larger fraction of a 1.8 V Vctrl window than a
  3.3 V one, so the ripple limit gf180-pll used cannot be assumed to carry
  over even as a starting point — it must be re-derived smaller, not
  larger, on sky130.

None of the numeric consequences above are settled by this record — they
are named so the ratifying decision in #1 is made with the downstream cost
visible, per this record's scope: argue the flavor, not the values.

## Status notes

This record stays `proposed` until #1 closes. #1 is the operator-only
ratification issue for `spec/target-spec.md`; only the operator's ruling
there — not this record on its own — flips `spec/target-spec.md` row 0 (and
the rows that depend on it) from DRAFT to ratified. If #1 rules differently
than this record's recommendation, this record should be updated (or a
superseding record filed) to match the ratified outcome, per the normal
decision-record discipline in `CLAUDE.md`.
