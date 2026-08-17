# VCO core — design rationale (issue #24)

Ring-oscillator VCO core for the sky130 PLL, block 1 of 4 of the #14
decomposition. Standalone block: this document records the design choices
behind `vco_ring5.sch`/`vco_ring5.sym`, not a verified result. **No
`sim/` testbench exists for this block yet** (that is #23 plus whatever
sub-issue runs the sky130 tuning-range campaign once #1 ratifies the spec
rows this design targets) — every number below is a design target or an
informal sanity-check observation, never a claim against
`spec/target-spec.md`.

## Forward design, not reverse-engineered

This is a textbook current-starved CMOS ring-oscillator topology — the same
basic structure described in standard analog-IC texts (e.g. Razavi) and
used throughout the open-source ring-VCO literature. It was authored fresh
against sky130's device models for this repo; nothing here originates in
another chip's silicon or netlist, per `CLAUDE.md`'s
reverse-engineering-free rule.

## Topology choice: single-ended current-starved ring, not differential

Two standard ring-VCO families were the candidates:

- **Current-starved single-ended CMOS inverter ring** (chosen). Each stage
  is a plain CMOS inverter whose pull-up/pull-down current is limited
  ("starved") by a series PMOS current source / NMOS current sink per
  stage, both biased from the control voltage. Frequency is set by how much
  the tail devices restrict the inverter's charge/discharge current.
- **Differential ring** (delay cells with a resistive or current-source
  load, driven differentially, closed with one inversion across the ring).
  Better supply/substrate noise rejection and lower even-harmonic content
  for a given stage count, at roughly double the device count per stage and
  the added complexity of a common-mode feedback (CMFB) loop to hold the
  output common-mode level.

**Chosen: single-ended current-starved.** Rationale:

- This is a v1 canary block with no ratified jitter, PSRR, or reference-spur
  budget yet (`spec/target-spec.md` rows 9/10/13 are all DRAFT) — there is
  no numeric target yet that specifically demands differential's better
  noise rejection over single-ended's simplicity.
- Fewer devices, no CMFB loop, and a single control-voltage node (`VCTRL`)
  match the spec's existing v1-scope conservatism elsewhere (no
  auto-calibration FSM per row 4, no power-down mode per row 17) — the
  project is deliberately not front-loading complexity the ratified spec
  doesn't yet call for.
- If a future PVT/jitter campaign shows single-ended's supply sensitivity
  is the binding constraint on row 9 (period jitter) or row 13 (supply
  sensitivity), a differential ring is the natural escalation — tracked as
  a candidate follow-up, not built preemptively here.

## Stage count: 5

Ring oscillators require an **odd** stage count so the loop carries a net
inversion and free-runs rather than latching. Candidates were 3, 5, 7, 9:

- **3 stages** — minimum viable, reaches the highest frequency for a given
  per-stage delay, but each stage's duty-cycle asymmetry contributes a
  larger fraction of the total period, and there is little margin before
  parasitic loading/mismatch pushes the loop out of oscillation.
- **5 stages (chosen)** — a standard middle ground: enough stages that a
  single stage's rise/fall asymmetry averages out better across the period
  (helping row 14's 45–55 % output duty-cycle target) without the frequency
  ceiling paid by 7 or 9 stages, which the DRAFT output-band's upper edge
  (row 2, up to 200 MHz starting point) does not obviously need to give up
  on 130 nm sky130 core devices.
- **7 / 9 stages** — better phase-noise-per-stage averaging in principle,
  but pay directly in maximum achievable frequency; not chosen because
  nothing in the current DRAFT spec rows demands it and it would need
  re-justifying once row 2 (output band) is actually re-derived.

5 is a starting point for that re-derivation, not a number defended by a
sweep across stage counts — a stage-count sensitivity study is exactly the
kind of thing the future sky130 tuning-range campaign (the work that closes
spec row 2) would run before ratification.

## Bias generation

A single control voltage `VCTRL` sets both tail currents via a
diode-connected replica bias branch (`MBP0`/`MBN0`) rather than tying
`VCTRL` only to the NMOS tail devices and picking an unrelated PMOS bias:

- `MBN0` (NMOS, gate tied to `VCTRL`) sets a bias current through
  `MBP0` (PMOS, diode-connected: gate tied to its own drain).
- `MBP0`'s gate node (`VBP`) is then the bias fed to every stage's PMOS
  current-source device (`MSP<i>`), mirroring the same current the replica
  branch draws.
- Every stage's NMOS current-sink device (`MSN<i>`) has its gate tied
  directly to `VCTRL` — the same node driving the replica's `MBN0`, so it is
  itself already a matched mirror of the replica leg (1:1 by construction,
  same `W`/`L` as the per-stage `MSN<i>` devices).

This is the standard structure for translating one control voltage into
matched PMOS/NMOS tail currents without needing a second control input, and
it means `VBP` tracks `VCTRL` automatically as process/temperature shift the
mirror — no separate calibration needed.

## Device sizing rationale

| Role | Devices | W (µm) | L (µm) | Why |
|---|---|---|---|---|
| Inverter core (switching pair) | `MP<i>` (PMOS) / `MN<i>` (NMOS) | 4 / 2 | 0.15 (min) | Minimum channel length for speed (this ring's frequency ceiling is set by these devices' intrinsic switching speed, starved down by the tail). 2:1 PMOS:NMOS width ratio is the standard first-pass compensation for sky130's roughly 2x hole/electron mobility mismatch, targeting symmetric rise/fall (feeds row 14's duty-cycle target). |
| Tail current source/sink | `MSP<i>` (PMOS) / `MSN<i>` (NMOS) | 4 / 2 | 0.5 | Longer channel than the switching devices on purpose: a current-source/sink transistor's output impedance and its current's insensitivity to `Vds` both improve with longer `L`. Same 2:1 W ratio as the switching pair so both tail legs are sized consistently with what they gate. |
| Bias replica (`MBP0`/`MBN0`) | PMOS / NMOS | 4 / 2 | 0.5 | Identical `W`/`L` to the per-stage tail devices — a 1:1 mirror is the simplest, lowest-mismatch choice; no scaling factor to get wrong. |
| Output buffer stage A (`MBUFA_*`) | PMOS / NMOS | 4 / 2 | 0.15 | Sized identically to one ring inverter stage, so tapping `RING0` here loads the ring the same way another ring stage would — avoids skewing the tapped stage's delay relative to its four siblings. |
| Output buffer stage B (`MBUFB_*`, drives `CLK`) | PMOS / NMOS | 16 / 8 | 0.15 | 4x tapered up from stage A for adequate drive into whatever external/testbench load `CLK` sees — a standard tapered-buffer final stage, isolating the ring from `CLK`'s load capacitance. |

All bulk terminals are tied to the standard rail for a non-isolated core
device (PMOS body to `VDD`, NMOS body to `GND`) — no body-effect tuning in
this v1.

## Tuning range / Kvco — design target, not a verified result

**No `sim/` evidence exists for this block.** The numbers below come from a
single, informal, uncommitted ngspice sanity check run against this exact
schematic's netlist during authoring — one process corner (`tt`), one
temperature (27 °C, ngspice default), no PVT sweep, not written as a `sim/`
record, and not a claim against any `spec/target-spec.md` row. Its only
purpose is to confirm the topology actually free-runs and tunes
monotonically with `VCTRL` before committing the schematic — exactly the
kind of check `sim/pdk-smoke`'s harness will formalize once a real `vco`
testbench exists (#23).

| `VCTRL` (V) | Observed period | Observed frequency |
|---|---|---|
| 0.8 | ~20.7 ns | ~145 MHz |
| 0.9 | ~3.13 ns | ~319 MHz |
| 1.0 | ~1.92 ns | ~522 MHz |
| 1.2 | ~1.21 ns | ~830 MHz |
| 1.4 | ~1.00 ns | ~998 MHz |
| 1.6 | ~0.92 ns | ~1.09 GHz |

Below ~0.8 V the tail current is too small for the loop to complete enough
cycles in a reasonable simulated window at this sizing (consistent with the
tail devices approaching sub-threshold); above ~1.6 V the informal
transient run became numerically difficult and was not pursued further —
neither edge is a characterized operating limit, just where this one-shot
check stopped.

**Reading this against spec row 5 (Kvco).** The DRAFT bound (≤ 150 MHz/V,
explicitly *not* ported from gf180-pll — see spec row 5) is far below the
slope this sizing shows locally (roughly 500 MHz/V–2 GHz/V across the table
above). That gap is expected and informative, not a design failure: this
schematic's job (#24) is to stand up a working, tunable ring; bringing Kvco
down to whatever bound the sky130 band map actually needs (spec row 5's own
"re-derive" instruction) is loop-filter/PVT-campaign work for a later issue,
and the likely levers are already visible from this sizing table — longer
tail-device `L` (lower transconductance, gentler current-vs-`Vctrl` slope),
a narrower usable `VCTRL` range (e.g. operating only over the gentler
low-`VCTRL` end of the table), or source degeneration on the tail devices.
None of that is applied here; this issue's scope is the schematic and its
design target, not the tuning pass.

**Design target stated plainly:** this VCO is designed to free-run and tune
monotonically with `VCTRL` across at least a few-hundred-MHz span in the
neighborhood of the DRAFT output-band starting point (row 2), with the
above table as the starting evidence for the follow-up campaign that
re-derives the actual band, Kvco bound, and any resizing it implies. It is
not designed to already meet the ≤ 150 MHz/V DRAFT bound — nothing in this
issue's acceptance criteria required that, and forcing it here without
simulation evidence would be exactly the kind of unverified claim
`CLAUDE.md` rules out ("no claim without a testbench").

## No spec edits

Nothing in `spec/target-spec.md` is edited by this issue. Rows 2 (output
band) and 5 (Kvco) stay DRAFT; the table above is design-time evidence
toward a future decision, not a ratification. Any change to those rows
still requires its own decision record (`spec/decision-records/DR-NNN`),
argued on its own merits, per `CLAUDE.md`.

## Files

- `vco_ring5.sch` — top schematic (26 devices: 5 ring stages x 4 devices,
  1 bias replica pair, 2-stage output buffer).
- `vco_ring5.sym` — block symbol (`VDD`, `GND`, `VCTRL` in, `CLK` out), for
  the future integration schematic to instantiate.
- `netlist/vco_ring5.spice` — connectivity-only netlist snapshot, generated
  and verified per the command in `../README.md`.

## Verification performed for this issue

- `xschem -n -q -x --rcfile sim/xschemrc design/vco/vco_ring5.sch -o
  design/vco/netlist` — exits 0, no stdout/stderr output (no netlister
  errors or warnings).
- The symbol (`vco_ring5.sym`) was checked by instantiating it from a
  throwaway top-level schematic (not committed) and confirming xschem
  descends into `vco_ring5.sch` and expands the full 26-device subcircuit
  under the instance call `X<name> VDD GND VCTRL CLK vco_ring5` — i.e. the
  symbol's pin order matches the schematic's pin declaration order and
  hierarchical instantiation nets correctly, ready for the future
  integration sub-issue.
- The informal oscillation/tuning sanity check described above (not
  committed as `sim/` evidence).
