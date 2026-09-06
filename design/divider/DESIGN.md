# Programmable integer-N feedback divider — design rationale (issue #27)

Programmable integer-N feedback divider for the sky130 PLL, block 4 of 4 of
the `#14` decomposition. Standalone block: this document records the design
choices behind `divider_intN.sch`/`divider_intN.sym`, not a verified result.
**No `sim/` testbench exists for this block yet** (that is #23 plus whatever
sub-issue runs the sky130 PVT campaign once the rows this design targets are
ratified) — every number below is a design target or an informal
connectivity check, never a claim against `spec/target-spec.md`. Issue #44
fixed a SPICE instance-naming defect (below) that had made this block's
netlist unsimulatable by ngspice; that fix has been verified with an ad hoc
ngspice run (also below), which is still not a `sim/` evidence record.

## Forward design, not reverse-engineered

This is a textbook synchronous binary down-counter with a comparator-free
zero-detect and a synchronous reload mux — a standard programmable-modulus
counter structure described in any digital-design text and used throughout
open-source clock-divider IP. It was authored fresh against sky130's
standard-cell library for this repo; nothing here originates in another
chip's silicon or netlist, per `CLAUDE.md`'s reverse-engineering-free rule.

## Scope: standalone block, not the closed loop

This issue authors the divider block only. It is not wired to the VCO
(`design/vco/vco_ring5.sch`, issue #24), a PFD/charge pump, or a loop filter
here — that is the integration sub-issue tracked on `#14`. `CLK` (this
block's clock input) is documented as "driven by the VCO output" as the
intended usage, but no hierarchical instantiation of `vco_ring5.sym` happens
in this schematic.

## Architecture choice: synchronous down-counter vs. dual-modulus/pulse-swallow

Two standard programmable-divider families were the candidates:

- **Synchronous down-counter with programmable reload** (chosen). An
  N-bit counter decrements every input clock cycle; when it reaches zero, a
  zero-detect signal reloads a static N−1 configuration word on the next
  edge and (registered) drives the divided output. Straightforward, one
  clock domain, no prescaler.
- **Dual-modulus prescaler / pulse-swallow counter** (e.g. a fast ÷4/÷5
  prescaler gated by a swallow counter, the classic architecture for
  fractional-N or very-high-frequency (multi-GHz, RF synthesizer class)
  integer-N dividers where a single monolithic counter cannot close timing
  at the input frequency). Needs two counters, a mode-control state machine,
  and more careful multi-phase retiming.

**Chosen: synchronous down-counter.** Rationale:

- Row 4's DRAFT range (N = 4–64) is modest — a plain 6-bit counter
  (`2^6 = 64`, comfortably covering N−1 = 3…63) is not a case a dual-modulus
  prescaler exists to solve; that architecture earns its complexity only
  once a single synchronous counter can no longer meet the input period at
  the target frequency, which is not demonstrated here (see "Retiming
  target" below).
- Row 4 explicitly scopes v1 to **static configuration, no auto-calibration
  FSM** — a plain counter with a static reload word is the minimum
  structure satisfying that scope; a prescale/swallow architecture would add
  a mode-control FSM the spec doesn't call for.
- Matches the project's demonstrated v1-scope conservatism elsewhere (no
  power-down mode per row 17, no auto-cal per row 4) — build the simplest
  structure the ratified/DRAFT spec actually needs, escalate only if a
  future PVT/timing campaign shows the plain counter doesn't close.

## Counter direction and zero-detect: down-counting, comparator-free

A **down**-counter (decrementing to zero, then reloading) was chosen over an
**up**-counter (incrementing to a programmable terminal count, then
clearing) specifically because down-counting makes the "terminal count"
condition trivial: it is simply "all bits are zero," detected by ANDing each
bit's complement together. An up-counter's terminal-count condition is
"count equals NSEL," which needs a real per-bit magnitude comparator
(bitwise XNOR + AND-reduce) — strictly more logic for the same function.
Down-counting reuses the same borrow-propagate chain that already computes
the decrement itself, so the "all-zero" detector falls out for free (see
"Per-bit logic" below) instead of needing a separate comparator tree.

## Per-bit logic

Each bit `i` (`i` = 0..5, LSB to MSB) has:

- **Decrement path** (borrow-chain subtractor, no separate adder/comparator
  block): bit 0 always toggles (`D_dec0 = ~Q0`, wired directly from an
  inverter — subtracting 1 flips the LSB unconditionally, no gating
  needed). Bit `i` (`i` >= 1) is `D_dec_i = Qi XOR borrow_i`, where
  `borrow_i` (borrow propagating into bit `i`) is `~Q0` for `i = 1` (free,
  same inverter bit 0 already needed) and `borrow_{i-1} AND ~Q_{i-1}` for
  `i` >= 2 (one `AND2` per bit, chained) — the standard synchronous-counter
  borrow-propagate structure, using each bit's own inverted output
  (`NQi = ~Qi`) as the local "would-borrow" signal.
- **Zero detect** (`ZERO`): the borrow chain already reaches
  `borrow_5 = AND(~Q0, ~Q1, ~Q2, ~Q3, ~Q4)` (bits 0–4 all zero) by
  construction; one more `AND2` (`ZERO = borrow_5 AND ~Q5`) folds in the
  MSB, giving "all 6 bits are zero" with a single extra gate — not a
  separate 6-input comparator tree.
- **Synchronous reload mux** (`mux2`): each bit's flip-flop `D` input
  selects between the decrement path (`A0`) and the static configuration
  bit `NSELi` (`A1`), with `ZERO` as the select. When the counter reaches
  zero, the *next* state is `NSEL[5:0]` (= N−1) instead of continuing to
  decrement into a wraparound; every other cycle it just keeps counting
  down.
- **Counter flip-flop**: `sky130_fd_sc_hd__dfrtp_2` (async active-low
  reset), so every bit has a defined power-up state (`Qi = 0` for all `i`).
  Because `ZERO` is a comb function of the *current* state, an all-zero
  power-up state already asserts `ZERO`, so the very next active clock edge
  after reset deassertion loads `NSEL[5:0]` and the divider is in normal
  periodic operation within one cycle — no separate "first load" sequencing
  is needed.

## Output register

`ZERO` is combinational and could glitch transiently during the borrow
chain's propagation within a cycle. Rather than exposing that raw signal as
the block's output, one extra flip-flop (`sky130_fd_sc_hd__dfxtp_2`, no
reset — its output is don't-care until the first `CLK` edge, same as any
other pipeline register) registers `ZERO` on the same `CLK` edge that
updates the counter, producing `FBCLK`: a single, clean, one-`CLK`-period-
wide pulse once every N input cycles, edge-aligned to `CLK`, with no
combinational glitch risk propagating to the block's output pin.

## Programming interface: static configuration bits, not a calibration loop

`NSEL[5:0]` (LSB `NSEL0`, MSB `NSEL5`) is a 6-bit static input carrying
**N − 1** in plain binary — e.g. `NSEL[5:0] = 000011` (3) for N = 4,
`NSEL[5:0] = 111111` (63) for N = 64. There is no shift register, I²C/SPI
register file, or runtime calibration state machine in this block: per row
4's explicit v1 scope ("static configuration," "no auto-calibration FSM,
matching gf180-pll v1"), `NSEL[5:0]` is exposed as six plain digital input
pins, exactly like `VCTRL` was exposed as a plain analog input pin by the
VCO block (issue #24) rather than being generated internally. Whoever
instantiates this block — the future integration sub-issue tracked on `#14`
— is responsible for strapping `NSEL[5:0]` to `VDD`/`GND` (or driving it
from some higher-level config source, out of this issue's scope) to select
N. `RESETB` (active-low, asynchronous) is likewise exposed as a plain input,
for whatever system-level reset the integration schematic provides.

6 bits covers `NSEL[5:0]` = 0…63 (N − 1 = 0…63, i.e. N = 1…64) — more range
than row 4's N = 4–64 needs at the low end (N = 1–3 are representable but
outside the DRAFT spec's stated floor); no bits are wasted at the top end,
since N = 64 exactly saturates a 6-bit word (`2^6 = 64`). A 5-bit word
(`2^5 = 32`) would not reach N = 64, so 6 bits is the minimum word width
that covers the full DRAFT range.

## Implementation: sky130_fd_sc_hd standard cells, not custom transistor-level logic

The VCO block (issue #24) is analog/mixed-signal and was built from bare
`sky130_fd_pr` primitive transistors, because a current-starved ring's
device sizing *is* the design. A synchronous digital counter has no
comparable analog design freedom — its function is fully specified by its
Boolean/state equations above, and hand-sizing custom transistor-level
flip-flops/gates would only reproduce what sky130's own standard-cell
library already provides, verified and characterized. This design is built
entirely from `sky130_fd_sc_hd` standard cells (`dfrtp_2`, `dfxtp_2`,
`inv_2`, `and2_2`, `xor2_2`, `mux2_2` — the `_2`-drive-strength variant used
uniformly, a reasonable first-pass choice with no fanout/timing analysis
performed yet), instantiated in xschem via the PDK-provided
`sky130_stdcells` xschem symbol library (already on this repo's
`XSCHEM_LIBRARY_PATH` through `sim/xschemrc` -> the PDK's own `xschemrc`;
no new symbol library was vendored for this issue). This is the standard-
cell-based option the issue text calls out as "a reasonable starting point
for the digital counter logic" — chosen over custom transistor-level logic
because both are acceptable per the issue's own scope language, and the
standard-cell path carries materially less design/verification risk for a
block whose function is purely digital/combinational-plus-state.

Every standard-cell instance ties its power/body pins
(`VPWR`/`VGND`/`VPB`/`VNB`, sky130_fd_sc_hd's standard cell-internal power
strap names) to this block's own `VDD`/`GND` nets
(`VPWR=VDD VGND=GND VPB=VDD VNB=GND`) — the non-isolated-well convention (no
body-effect tuning, no separate deep-nwell strap), consistent with the VCO
block's own bulk-tie convention (PMOS body to `VDD`, NMOS body to `GND`).

## Retiming / top-frequency target — design target, not a verified result

**No `sim/` evidence exists for this block; no timing analysis (STA or
transient) was run.** Row 4 asks the divider's retiming to "close at the
sky130 top frequency" — read here as the VCO block's (issue #24) informal
sanity-check table in `design/vco/DESIGN.md`, whose highest observed
free-running frequency was **~1.09 GHz at `VCTRL` = 1.6 V** (that table's
own upper edge, not a characterized operating limit — the VCO's own design
target is "a few-hundred-MHz span in the neighborhood of the DRAFT
output-band starting point," row 2's 10–200 MHz).

This design's stated target: **close a single synchronous-counter stage
(one `dfrtp_2` D-to-Q, through the reload mux and one borrow-chain gate, on
the critical bit) within one `CLK` period at whatever top frequency the VCO
sub-issue ultimately targets** — informally, comfortably inside the
few-hundred-MHz-to-~1 GHz range the VCO's sanity-check table spans. This is
plausible on sky130 130 nm standard cells (a `dfrtp_2`/`mux2_2`/`and2_2`
chain is a handful of gate-delays, well inside a ~1 ns period at 1 GHz for
a 130 nm node's drive-strength-2 cells) but is **not verified here** — no
STA run, no transient closure check, no PVT corner. This is exactly the
kind of claim `CLAUDE.md` rules out without a testbench: the plausibility
argument above is a rationale for the architecture choice (why a single
synchronous counter, not a dual-modulus prescaler, was judged adequate), not
a timing-closure result. A future testbench issue (the same PVT campaign
gated on the VCO's own row-2/row-5 ratification) owes the actual measured
closure — the borrow chain's worst-case bit (bit 5, the deepest borrow-AND
chain) is the natural place to start a timing check once that testbench
exists.

If a future campaign shows the plain synchronous counter does not close at
the ratified top frequency, the natural escalation is a dual-modulus
prescaler front-end (a fast, fixed-modulus stage ahead of this counter) —
tracked as a candidate follow-up, not built preemptively here.

## Measured finding (issue #98/#100): the counter does not close timing
## "comfortably inside ~1 GHz" as this section originally speculated

The plausibility argument above ("well inside a ~1 ns period at 1 GHz for a
130 nm node's drive-strength-2 cells") turns out to be **wrong** once
actually measured. `sim/pll-lock`'s closed-loop evidence (issue #98) showed
the divider's `FBCLK` output going permanently silent — one pulse at reset
release, then nothing — whenever the VCO free-ran near the top of its own
tuning range during a cold start; PR #101/#105 (`design/top/DESIGN.md`'s
"Known gap" section) suspected this was the divider failing to close
timing at that frequency but did not isolate the divider from the rest of
the closed loop to confirm it. This section closes that gap with a direct,
standalone measurement of `divider_intN` alone, decoupled from the VCO/PFD/
loop-filter entirely.

**Method (informal, uncommitted diagnostic — same convention as this
document's own "Retiming" section above and `design/vco/DESIGN.md`'s
"informal sanity check" table, not a `sim/` evidence record)**: a scratch
ngspice deck instantiates `design/divider/netlist/divider_intN.spice`'s
`divider_intN` subcircuit directly (no `top.sch`, no VCO/PFD/charge pump/
loop filter in the circuit at all), strapped identically to
`sim/pll-lock/testbench/tb_pll_lock.sch` (`NSEL[5:0]=011000`, i.e. N = 25;
`RESETB` released via the same `pwl(0 0 5n 0 6n 1.8)`), driven by an
**ideal** `pulse()` voltage source directly on `CLK` at a fixed frequency
(not a VCO — this isolates the counter's own timing from any analog
settling behavior), tt corner, 27 °C (ngspice default), `VDD` = 1.8 V. Each
run is a few hundred nanoseconds to 1 µs of `tran 20p <stop>`, long enough
to observe 250-650 input `CLK` cycles (10-26 expected `FBCLK` periods at
N = 25). `FBCLK` and the internal `ZERO` node's rising-edge counts and
spacing are read back from a `wrdata` dump, the same threshold/edge method
`sim/harness/measure.py` uses (0.9 V rising threshold, no hysteresis needed
for a clean digital signal).

| `CLK` frequency | `CLK` period | Result |
|---|---|---|
| 250 MHz (control; the `sim/pll-lock` reference-clock-times-N target) | 4.0 ns | Clean divide-by-25: `FBCLK` at 10.0 MHz, 9 edges/µs, all 100.0 ns apart |
| 500 MHz | 2.0 ns | Clean divide-by-25: `FBCLK` at 20.0 MHz, all periods 50.0 ns |
| 800 MHz | 1.25 ns | Clean divide-by-25: `FBCLK` at 25.0 MHz, all periods 40.0 ns |
| 950 MHz | 1.053 ns | **Broken**: 0 `FBCLK` rising edges over 475 input cycles (475 ns), despite the internal `ZERO` node still toggling 29 times — `ZERO` is asserting but never being cleanly registered onto `FBCLK` |
| 1.07 GHz (the free-running frequency PR #101's own single-corner diagnostic observed) | 0.935 ns | **Broken**: 0 `FBCLK` rising edges over 642 input cycles (600 ns); `ZERO` never even registers a clean rising edge either (0, vs. control runs' ~1 per divide period) |

**Conclusion**: this is a real, reproducible, **frequency-threshold** failure
of the synchronous counter's own combinational path (the borrow chain and/or
the `ZERO`-to-`FBCLK` registration path), not a cold-start reset race, not a
loop-filter/VCO coordination artifact, and not a measurement-window
artifact — the counter is driven by a clean, glitch-free ideal clock source
for hundreds of cycles with no other circuit attached, and it still never
reaches its own zero-detect state above roughly 800-950 MHz. That failure
threshold sits **below**, not "comfortably inside," the VCO's own
characterized ~1.09 GHz tuning-range ceiling (`design/vco/DESIGN.md`'s
sanity-check table) — the "well inside a ~1 ns period" plausibility argument
this section opened with was never checked against real standard-cell
delays and does not hold up. Practically, this means: (1) the divider is
**not** the limiting factor for this design's actual 250 MHz lock target
(clean operation is demonstrated well past it, through 800 MHz); (2) the
divider **is** a real hazard during any cold-start transient that lets the
VCO's `VCTRL` wander into the 800 MHz-to-top-of-range band before the loop
achieves negative feedback, which is exactly the "no lock, `VCTRL` pinned
near `VDD`" failure mode `sim/pll-lock`'s 45-point baseline records; and (3)
closing this at the standard-cell level (faster drive strengths on the
borrow-chain/output-register critical path, or a retimed/pipelined counter,
or the dual-modulus escalation this section already named as a candidate)
is a real option, but so is simply keeping the closed loop's cold-start
`VCTRL` excursion below this now-measured ~800 MHz ceiling via the VCO-bias/
`Icp`/loop-filter levers issue #98 already scoped — the latter avoids
touching an already-reviewed digital block's standard-cell sizing at all.
Neither redesign is attempted in this pass; see `design/top/DESIGN.md`'s
"Known gap" section and issue #100 for how this finding feeds the next
design decision.

## No spec edits

Nothing in `spec/target-spec.md` is edited by this issue. Row 4
(multiplication ratio) and row 2 (output band, referenced for the retiming
target) stay DRAFT; the discussion above is design-time rationale toward a
future decision, not a ratification. Any change to those rows still
requires its own decision record (`spec/decision-records/DR-NNN`), argued on
its own merits, per `CLAUDE.md`.

## Files

- `divider_intN.sch` — top schematic (29 standard-cell instances: 6 counter
  flip-flops + 6 reload muxes + 5 decrement XORs + 5 borrow/zero-detect ANDs
  + 6 bit-complement inverters + 1 output register).
- `divider_intN.sym` — block symbol (`VDD`, `GND`, `CLK` in, `RESETB` in,
  `NSEL0`..`NSEL5` in, `FBCLK` out), for the future integration schematic to
  instantiate.
- `netlist/divider_intN.spice` — connectivity-only netlist snapshot,
  generated and verified per the command in `../README.md`.

## Verification performed for this issue

- `xschem -n -q -x --rcfile sim/xschemrc design/divider/divider_intN.sch -o
  design/divider/netlist` — exits 0, no stdout/stderr output (no netlister
  errors or warnings).
- Manual inspection of the generated netlist confirms: 29 standard-cell
  instances, each cell's pin order matches its `sky130_stdcells` symbol's
  `format=` string (e.g. `dfrtp_2`: `CLK D RESET_B VGND VNB VPB VPWR Q`),
  the borrow chain and zero-detect wiring match the per-bit logic described
  above bit-by-bit (`BOR2`..`BOR5`, `ZERO`), and every cell's power pins tie
  to this block's own `VDD`/`GND`.
- The symbol (`divider_intN.sym`) was checked by instantiating it from a
  throwaway top-level schematic (not committed) and confirming xschem
  descends into `divider_intN.sch` and expands the full 29-device subcircuit
  under the instance call
  `X<name> VDD GND CLK RESETB NSEL0 NSEL1 NSEL2 NSEL3 NSEL4 NSEL5 FBCLK
  divider_intN` — i.e. the symbol's pin order matches the schematic's pin
  declaration order and hierarchical instantiation nets correctly, ready for
  the future integration sub-issue.

## Issue #44: standard-cell instance names collided with SPICE's implicit
## device-type-by-prefix rule, breaking simulation

All 29 standard-cell instances above were originally named with plain
descriptive names (`CNT0`-`CNT5`, `LDMUX0`-`LDMUX5`, `QINV0`-`QINV5`,
`DECXOR1`-`DECXOR5`, `BORAND2`-`BORAND5`, `ZDET`, `FBFF`) rather than an
`X`-prefixed instance name. SPICE infers device type from an instance
name's first letter when no `X` prefix marks it as a subcircuit call: `C`
is the capacitor prefix (`CNT*`), `L` is inductor (`LDMUX*`), `Q` is BJT
(`QINV*`), `D` is diode (`DECXOR*`), `B` is a behavioral source
(`BORAND*`), `Z` is MESFET (`ZDET`), and `F` is a CCCS (`FBFF`) — so
ngspice misparsed every one of them as a native device instead of a
`sky130_fd_sc_hd__*` subcircuit call. `xschem`'s netlister does not enforce
this SPICE convention, so the "Verification performed for this issue"
section above (netlisting-only, no ngspice run) could not have caught it;
this was first exposed while building #23's closed-loop testbench, which
hit `ERROR: mal formed B source instance` and a string of `warning, can't
find model` lines pointing at these instances.

**Fix**: every one of the 29 instances above renamed with an `X` prefix in
`divider_intN.sch` (`CNT0`->`XCNT0`, `LDMUX0`->`XLDMUX0`, etc.) — a pure
instance-name rename, no connectivity, pin-order, or device change — and
`netlist/divider_intN.spice` regenerated via the same `xschem -n -q -x`
command above (still exits 0, still no netlister errors/warnings). A diff
of the regenerated netlist against its pre-fix version shows only the
instance-name column changing on the 29 renamed lines (identical node
lists, identical `sky130_fd_sc_hd__*` subcircuit names and pin order) plus
the `sch_path` comment line (reflects the absolute path of whichever
machine/worktree last ran the netlister, not a content change).
`grep -oE '^[A-Za-z0-9_]+' netlist/divider_intN.spice` now shows all 29
instance lines starting with `X`.

**ngspice verification (ad hoc, not a `sim/` evidence record)**: wrapped
the regenerated `netlist/divider_intN.spice` in a scratch top-level
testbench (power/clock/reset/`NSEL` stimuli, the PDK's
`sky130_fd_sc_hd.spice` stdcell deck, and the `tt`-corner analog model
library) and ran `ngspice -b` with a `.tran 50p 200n`. The transient ran to
completion with exit 0; grepping the run log for `mal formed`, `can't find
model`, and `unknown parameter` found none. This is a plumbing
confirmation the block is now simulatable, not a functional or PVT
performance claim — that remains #23/the future PVT campaign's job, and
sits in `sim/`, not here.
