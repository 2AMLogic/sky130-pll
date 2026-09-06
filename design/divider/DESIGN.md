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
| 800 MHz | 1.25 ns | **÷32, not ÷25** (40.0 ns ÷ 1.25 ns = 32 input cycles) — raw measurement was `FBCLK` at 25.0 MHz, all periods 40.0 ns; see "Reconciliation (issue #112)" below |
| 950 MHz | 1.053 ns | **Broken**: 0 `FBCLK` rising edges over 475 input cycles (475 ns), despite the internal `ZERO` node still toggling 29 times — `ZERO` is asserting but never being cleanly registered onto `FBCLK` |
| 1.07 GHz (the free-running frequency PR #101's own single-corner diagnostic observed) | 0.935 ns | **Broken**: 0 `FBCLK` rising edges over 642 input cycles (600 ns); `ZERO` never even registers a clean rising edge either (0, vs. control runs' ~1 per divide period) |

### Reconciliation (issue #112): the 800 MHz row above was a misread, not a re-measurement discrepancy

The table's 800 MHz row originally read "Clean divide-by-25" here, while the
"Issue #104" section later in this document (added in the same push window)
reports ÷32 at 800 MHz — a direct contradiction at the same corner, modulus,
and reset release. A third, independent re-run (issue #112, 2026-09-06)
rebuilt the standalone testbench from scratch and reproduced this section's
own raw numbers exactly: `FBCLK` at 25.0 MHz, period 40.0 ns, at 800 MHz. The
raw data was never in dispute between the two write-ups; only the verdict
drawn from it was wrong here. At an 800 MHz input the `CLK` period is
1.25 ns, so 40.0 ns / 1.25 ns = 32 input cycles per `FBCLK` period — N = 32,
not 25. A correct ÷25 at 800 MHz would show `FBCLK` at 32.0 MHz (period
31.25 ns), not 25.0 MHz.

The misread was a numerical coincidence: 800 / 32 = 25.0 exactly, so the
*frequency* produced by the failing ÷32 mode happened to equal the
*modulus* N = 25, and this section's pass criterion ("`FBCLK` lands on the
expected number") matched against the modulus instead of the expected
output frequency. The 250 MHz and 500 MHz rows above are unaffected — their
expected outputs (10 MHz, 20 MHz) are nowhere near 25, so the coincidence
only bites at 800 MHz. The corrected `tt`/27 °C/1.80 V breakpoint is not
800 MHz; it is the **765/780 MHz** figure measured later in this document's
"Issue #104: root cause of the `FBCLK` dropout at high `CLK` frequency"
section, which stands as originally reported and reproduces independently
under issue #112's re-run.

**Conclusion**: this is a real, reproducible, **frequency-threshold** failure
of the synchronous counter's own combinational path (the borrow chain and/or
the `ZERO`-to-`FBCLK` registration path), not a cold-start reset race, not a
loop-filter/VCO coordination artifact, and not a measurement-window
artifact — the counter is driven by a clean, glitch-free ideal clock source
for hundreds of cycles with no other circuit attached, and it never reaches
its own zero-detect state above roughly 765-780 MHz at `tt`/27 °C/1.80 V
(the precise breakpoint measured in the "Issue #104" section below;
corrected per the reconciliation note above from this section's original,
mistaken "800-950 MHz" reading). That failure threshold sits **below**, not
"comfortably inside," the VCO's own characterized ~1.09 GHz tuning-range
ceiling (`design/vco/DESIGN.md`'s sanity-check table) — the "well inside a
~1 ns period" plausibility argument this section opened with was never
checked against real standard-cell delays and does not hold up. Practically,
this means: (1) the divider is **not** the limiting factor for this design's
actual 250 MHz lock target (clean operation is demonstrated well past it,
through ~765 MHz at `tt`/27 °C/1.80 V — see the #104 section's PVT sweep
below for the tighter figures at other corners); (2) the divider **is** a
real hazard during any cold-start transient that lets the VCO's `VCTRL`
wander into the ~765 MHz(`tt`)-to-top-of-range band before the loop achieves
negative feedback — and this band is materially wider, and the hazard
correspondingly worse, at `ss`/125 °C/1.62 V, where the #104 section's PVT
sweep measures the same trap closing at only ~475-500 MHz, just ~2× above
the 250 MHz target — which is exactly the "no lock, `VCTRL` pinned near
`VDD`" failure mode `sim/pll-lock`'s 45-point baseline records; and (3)
closing this at the standard-cell level (faster drive strengths on the
borrow-chain/output-register critical path, or a retimed/pipelined counter,
or the dual-modulus escalation this section already named as a candidate)
is a real option, but so is simply keeping the closed loop's cold-start
`VCTRL` excursion below this now-measured ~765 MHz (`tt`) / ~475-500 MHz
(`ss`/125 °C/1.62 V) ceiling via the VCO-bias/`Icp`/loop-filter levers issue
#98 already scoped — the latter avoids touching an already-reviewed digital
block's standard-cell sizing at all. Neither redesign is attempted in this
pass; see `design/top/DESIGN.md`'s "Known gap" section and issue #100 for
how this finding feeds the next design decision.

**Update (issue #104): the plausibility argument above has now been measured,
and it was optimistic.** (The Conclusion paragraph above was itself corrected
by issue #112 after a self-contradictory 800 MHz reading was found — see the
"Reconciliation (issue #112)" note above; the figures below are unchanged from
#104's original measurement.) The measured result is in "Issue #104: root
cause of the `FBCLK` dropout at high `CLK` frequency" at the end of this
document. In short: the counter does *not* close "comfortably inside the
few-hundred-MHz-to-~1 GHz range." Measured maximum correct-division
frequency is **≈765–780 MHz at `tt`/27 °C/1.80 V** and **≈475–500 MHz at
`ss`/125 °C/1.62 V**, because the limiting path is not the "one `dfrtp_2`
D-to-Q, through the reload mux and one borrow-chain gate" the paragraph
above assumed — it is the *full six-deep ripple-borrow chain* into the
zero-detect and the reload mux, ~1.2 ns of combinational delay at `tt`/27 °C/
1.80 V. The escalation named in the paragraph above (a prescaler front-end,
or an equivalent restructuring of the borrow chain) is therefore now an
open, evidence-backed follow-up rather than a hypothetical one.

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

## Issue #104: root cause of the `FBCLK` dropout at high `CLK` frequency

`design/top/DESIGN.md`'s "Known gap: closed-loop cold-start convergence
(issue #98)" section, point 4, recorded that at `tt`/27 °C/1.80 V with the
loop free-running near ~1.07 GHz, this block's `FBCLK` output "pulses
exactly once, at reset release, and then never toggles again," and left
*why* unanswered. Issue #104 answered it by measurement.

**Answer, in one line**: it is a **setup-time (retiming) failure of this
block's own ripple-borrow → zero-detect → reload-mux combinational path** —
candidate mechanism 1 of the three #98 named, with an important refinement
(below) — and the failure is *latching*, because a mistimed borrow drops the
counter into a short limit cycle in the upper half of the count space that
can never reach zero, so `ZERO` (and therefore `FBCLK`) never asserts again.
Candidate mechanisms 2 (a Boolean logic bug in the borrow/zero-detect
equations) and 3 (a reset-release race) are both **ruled out** by the
evidence below.

### Status of the evidence below: informal, uncommitted diagnostics

Everything in this section comes from ad hoc ngspice runs in a scratch
directory — **not** a `sim/` evidence record, and not a claim against any
`spec/target-spec.md` row. That follows the precedent this repo already
uses for narrow diagnostic runs (`design/vco/DESIGN.md`'s "informal sanity
check" table, and `design/top/DESIGN.md`'s own treatment of the #98
diagnostics) and issue #104's explicit scope, which allows informal
diagnostics for a root-cause writeup and requires a fresh `sim/pll-lock`
grid record only if a *fix* is proposed. No fix is proposed here (see "No
fix proposed in this pass" below), so no new `sim/` record is minted.

Environment for every run below: `ngspice-46`; sky130A via `volare` at
`open_pdks` `c6d73a35f524070e85faff4a6a9eef49553ebc2b` (the pin in
`sim/pdk.json`); `sim/spiceinit` copied in as `.spiceinit`; the PDK's
`libs.tech/combined/sky130.lib.spice` for devices and
`libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice` for the standard-cell
subcircuit bodies — the same two includes `sim/pll-lock`'s own testbench
uses.

### The two diagnostic testbenches

**(A) Standalone divider, ideal clock.** `divider_intN` instantiated
instance-for-instance from `netlist/divider_intN.spice`, driven by an
*ideal* rail-to-rail `pulse` source (20 ps edges, 50 % duty), `NSEL[5:0]` =
`011000` (24, i.e. N = 25 — the same modulus `sim/pll-lock` straps),
`RESETB` a `pwl` released at 5 ns, 200 `CLK` cycles simulated. Probed
`CLK`, `FBCLK`, `Q0`..`Q5`, `BOR2`..`BOR5`, `ZERO` (and `D3`/`D4`/`D5` in
two dedicated runs). This deliberately removes the VCO, the loop, and any
interaction with reset-release timing — the clock is a perfect,
free-running, phase-fixed source.

**(B) Closed loop, `top.sch`.** The committed frozen netlist
`sim/pll-lock/corners/20260905-193322-0f1934d/tt_27c_1.80v.spice` reused
verbatim, with only its `.control` block replaced: the harness's own
documented cold-start nudge (`.ic v(xxxtop.xxvco.ring0)=0`, the
`measure.ic` field in `sim/harness/measure.py`) plus a 5 µs / 100 ps
transient, saving the same divider-internal nodes hierarchically
(`v(xxxtop.xxdiv.q0)` … `v(xxxtop.xxdiv.zero)`). This reproduces #98
point 4's diagnostic and adds the internal instrumentation it lacked.

### (B) Closed-loop reproduction — where in the chain the toggling stops

The 5 µs run reproduces #98 point 4 exactly and localizes the failure:

| Observable | Value over the 5 µs window |
|---|---|
| VCO free-running frequency | 1.073–1.075 GHz, flat for the whole window |
| `VCTRL` | 1.790 V at 0.2 µs, creeping to 1.798 V at 4.9 µs — railed, never corrected |
| `FBCLK` | **1 rising edge** (at t ≈ 0.53 ns) and 1 falling edge, then flat for 5373 `CLK` cycles |
| `Q0` transitions | 5365 (≈ one per `CLK` edge — the LSB is clocking fine) |
| `Q1` / `Q2` / `Q3` transitions | 2683 / 1342 / 593 |
| **`Q4` transitions** | **1** |
| **`Q5` transitions** | **0** |
| `ZERO` transitions | 1 |
| sampled count at 0.2 / 0.5 / 1 / 2 / 3 / 4 / 4.9 µs | 17, 22, 21, 27, 24, 22 — **every sample inside [16, 31]** |

So the toggling does not stop at `FBCLK`, and it does not stop at the
flip-flops: bits 0–3 keep counting at 1.07 GHz for the entire 5 µs. It
stops at **bit 4**. `Q4` is stuck at 1 and `Q5` at 0, which pins the count
inside [16, 31]; `ZERO = BOR5 · NQ5` requires `Q4 = 0`, so `ZERO` can never
assert, so the `FBCLK` output register can never capture a 1 again. The
single `FBCLK` pulse at t ≈ 0.53 ns is simply the power-up capture of
`ZERO = 1` from the async-reset all-zero state — which is why the symptom
reads as "one pulse at reset release, then silence."

Note what this already rules out: the `dfrtp_2` flip-flops themselves clock
perfectly well at 1.07 GHz (bit 0 toggles 5365 times). Whatever is failing
is *combinational*, upstream of the higher bits' `D` inputs.

### (A) Ideal-clock frequency sweep at `tt`/27 °C/1.80 V — a hard, graded threshold

Divide ratio inferred from consecutive `FBCLK` rising edges; count sequences
read by sampling `Q[5:0]` immediately before each `CLK` rising edge.

| `CLK` frequency | Behaviour | Count sequence after the first reload |
|---|---|---|
| 250, 400, 500, 600, 700, 720, 750, 765 MHz | **÷25, exact** | 24, 23, …, 1, 0, 24, … |
| 780 MHz | ÷32 | reload fails: 0 → **31** (should be 24), then a clean 31→0 modulo-32 loop |
| 800 MHz | ÷32 | same as 780 MHz |
| 900 MHz | one more pulse, then dead | reload fails harder: 0 → **63**, then traps in a modulo-32 loop over [32, 63] |
| 1.00 GHz | **dead after the power-up pulse** | 24, 23, …, 17, 16 → **31** (borrow into bit 4 fails), then a modulo-16 loop over [16, 31] |
| 1.07 GHz | **dead after the power-up pulse** | identical to 1.00 GHz: modulo-16 loop over [16, 31] |
| 1.20 GHz | **dead after the power-up pulse** | borrow into bit 3 also fails: modulo-8 loop over [24, 31] |

The 1.00/1.07 GHz row is exactly the closed-loop signature in (B): the
counter reloads 24 correctly, decrements normally down to 16, and then — on
the one transition that needs the borrow to propagate all the way into bit 4
(16 → 15) — bit 4 fails to clear, giving 31 instead of 15. From there the
low four bits keep decrementing to 16, bit 4 fails again, and the counter
orbits [16, 31] forever. **It never revisits zero, so `FBCLK` is dead
permanently, not intermittently.**

The degradation is monotone and structural: as the period shrinks, the
*deepest* borrow that still completes gets shallower — first the reload
(which needs the full `ZERO` path) fails at 780 MHz, then the borrow into
bit 4 at 1.00 GHz, then the borrow into bit 3 at 1.20 GHz.

### (A) The same sweep across PVT — a ~2.4× spread, which is the decisive test

Same ideal clock, same `NSEL`, same reset; only the model corner, the
temperature, and the supply change.

| Corner (process / temp / supply) | Highest frequency measured **÷25 exact** | Lowest frequency measured **wrong** |
|---|---|---|
| `ss` / 125 °C / 1.62 V | 475 MHz | 500 MHz (÷32) |
| `sf` / 27 °C / 1.80 V | 700 MHz | 1.07 GHz (dead) |
| `fs` / 27 °C / 1.80 V | 700 MHz | 1.07 GHz (dead) |
| `tt` / 27 °C / 1.80 V | 765 MHz | 780 MHz (÷32) |
| `ff` / −40 °C / 1.98 V | **1.07 GHz (÷25 exact)** | 1.15 GHz (mixed ÷31/÷64) |

The maximum correct-division frequency moves by roughly **2.4×** between the
slow and fast PVT extremes, and it moves in the direction gate delay moves.
At `ff`/−40 °C/1.98 V the *same netlist* divides by exactly 25 at the very
frequency (1.07 GHz) where `tt`/27 °C/1.80 V is completely dead. That is the
signature of a timing limit and of nothing else — a Boolean logic error
would be corner-independent.

### (A) Reset-release phase sweep — mechanism 3 ruled out directly

`RESETB` release swept across a full `CLK` period in five steps
(0, 0.2, 0.4, 0.6, 0.8 of a period), at both a passing and a failing
frequency, `tt`/27 °C/1.80 V:

| Reset-release phase | 700 MHz | 1.07 GHz |
|---|---|---|
| 0.0 / 0.2 / 0.4 / 0.6 / 0.8 × period | ÷25 exact at every phase | dead at every phase |

There is no phase of reset release at which 1.07 GHz works, and none at
which 700 MHz fails. A reset-release race would show phase dependence; this
shows none. (Testbench (A) also has no reset-release *transient* to race
with in the first place — `RESETB` is an ideal 100 ps `pwl` edge and the
clock has been running at full amplitude since t = 0.)

### Critical-path delay, measured

Propagation delays from the `CLK` rising edge to each node's own transition,
`tt`/27 °C/1.80 V. Per-stage breakdown taken from the 250 MHz run (waveform
sample grid 100 ps, so these are quantized to ±100 ps); the `D`-input
numbers from dedicated 750/780 MHz runs (sample grid ≈ 33 ps):

| Node | Worst-case `CLK`-rise → node settle |
|---|---|
| `Q0` (flip-flop clk→Q) | ≈ 230 ps |
| `BOR2` | ≈ 500 ps |
| `BOR3` | ≈ 730 ps |
| `BOR4` | ≈ 830 ps |
| `BOR5` | ≈ 1030 ps |
| `ZERO` | ≈ 1020–1230 ps |
| `D3` (reload-mux output, bit 3) | ≈ 820 ps |
| `D4` | ≈ 950 ps |
| **`D5`** | **≈ 1180 ps** |

`D5` is the critical path, and its structure is exactly the one this
document's "Per-bit logic" section describes:
`CLK → Q0 → QINV0 → BORAND2 → BORAND3 → BORAND4 → BORAND5 →`
(`DECXOR5`, and `ZDET` → the `LDMUX5` select) `→ D5` — one flip-flop
clk→Q plus **seven** loaded combinational stages. At 765 MHz the period is
1307 ps, leaving ~125 ps over the measured 1180 ps `D5` settle for the
`dfrtp_2` setup time; at 780 MHz the period is 1282 ps and the margin is
gone. The measured pass/fail breakpoint (765 MHz passes, 780 MHz fails)
sits exactly where that arithmetic puts it, which is the quantitative
confirmation that the failure is setup-time and not something else wearing
a timing costume.

### Verdict against #98's three candidate mechanisms

| # | Candidate mechanism | Verdict | Evidence |
|---|---|---|---|
| 1 | Standard-cell timing limit at ~1.07 GHz | **Ruled in — with a refinement (below)** | Hard, PVT-graded frequency threshold (475 MHz at `ss`/125 °C/1.62 V → 1.07 GHz at `ff`/−40 °C/1.98 V); measured 1180 ps critical-path delay vs. the 1282 ps period at the breakpoint; failure depth shifts monotonically with period (reload → bit 4 → bit 3) |
| 2 | Borrow-chain / zero-detect **logic** bug | **Ruled out** | The same netlist divides by exactly **25** at 250–765 MHz at `tt`, at 250–475 MHz at `ss`/125 °C/1.62 V, and at 250 MHz–1.07 GHz at `ff`/−40 °C/1.98 V. A wrong Boolean equation cannot produce the right answer at one frequency/corner and the wrong one at another; and no corner or frequency produces a *wrong but stable* modulus that would indicate a mis-wired borrow tap |
| 3 | Cold-start reset-release race | **Ruled out** | The dropout reproduces in testbench (A), which has no VCO, no loop, and an ideal clock running at full amplitude from t = 0; and a five-point sweep of the reset-release phase across a full `CLK` period changes nothing at either 700 MHz (always passes) or 1.07 GHz (always fails). The single `FBCLK` pulse at reset release is fully explained as the output register's power-up capture of `ZERO = 1` from the async-reset all-zero state — it is a *correct* pulse, not a symptom |

**The refinement on mechanism 1**: #98 phrased this candidate as "a
fundamental timing limit of the chosen standard cells
(`sky130_fd_sc_hd__dfrtp_2`)." That phrasing is not what the evidence
supports, and the distinction matters for whoever fixes it. The
**flip-flops are not the limit** — `Q0` toggles cleanly on every one of
5373 `CLK` edges at 1.07 GHz in the closed-loop run, and at 1.2 GHz in the
ideal-clock run. What fails is **this design's own combinational depth**:
an eight-level path (clk→Q plus seven gates) built from the drive-strength-2
cells this block picked "uniformly … with no fanout/timing analysis
performed yet" (see "Implementation" above). This is a *retiming* failure of
the architecture as drawn, not an intrinsic ceiling of the cell library.

### Why this matters to the loop, and why it is a trap rather than a defect at the target

At the 250 MHz design target the divider is correct at **every** corner
probed (`tt`, `ss`/125 °C/1.62 V, `sf`, `fs`, `ff`/−40 °C/1.98 V). This
block is not the reason the PLL fails to *reach* 250 MHz.

What it is, is a **one-way trap**. If the loop ever transits above the
corner's maximum correct-division frequency — which a cold start from a
railed `VCTRL` does routinely — the divider stops producing `FBCLK`
entirely. The PFD/charge pump then has no feedback edge at all, `VCTRL`
keeps integrating toward the rail, the VCO stays fast, and nothing can ever
bring the loop back down: the condition that broke the divider is the
condition the divider's failure now sustains. That is the mechanism behind
#98 point 4's "genuine loss-of-feedback lockup, not a slow convergence," and
it is why widening `tran_stop` cannot rescue that corner. The margin is
thinnest exactly where it hurts most: at `ss`/125 °C/1.62 V the trap closes
at ~500 MHz, only ~2× above the 250 MHz target.

### No fix proposed in this pass

Per issue #104's own scope rule, a fix belongs in this issue's PR only if
the root cause is candidate mechanism 2 (a small, well-scoped logic bug).
It is not — it is mechanism 1, a retiming failure — so no schematic change
is made here and no new `sim/pll-lock` record is minted. The retiming work
is filed as a follow-up, **issue #107**. Candidate escalations, for that
issue to choose between and verify, all of which are larger than "a small,
well-understood change to the borrow-chain/zero-detect logic":

- **Flatten the borrow chain** (carry-lookahead-style: compute `BOR3`/`BOR5`
  from a wider AND rather than rippling through every intermediate),
  trading gate count for depth.
- **Pipeline / pre-compute `ZERO`** so the reload decision is registered a
  cycle early (e.g. detect "count == 1" combinationally at the same depth
  the current design detects "count == 0", and register it), removing the
  zero-detect and the mux select from the critical path entirely.
- **Raise drive strength** on the borrow chain (`_2` → `_4`) — the cheapest
  change, but it buys a percentage, not an architecture, and would still
  leave a hard threshold somewhere.
- **A dual-modulus prescaler front-end**, the escalation the "Retiming /
  top-frequency target" section above already named as the natural one.

Whichever is chosen, `CLAUDE.md`'s append-only evidence rule applies: it
needs a fresh full `sim/pll-lock` grid record before any claim that it
works. A useful cheap acceptance check for that work, derived from this
pass, is the ideal-clock sweep in testbench (A): the fix should move the
maximum correct-division frequency at `ss`/125 °C/1.62 V comfortably above
the VCO's own top free-running frequency, so that no reachable VCO state
can kill the feedback path.

### No spec edits from this investigation

Nothing in `spec/target-spec.md` is edited or ratified by issue #104. Row 4
(multiplication ratio) and row 2 (output band) stay DRAFT. The measured
maximum-division-frequency numbers above are diagnostic evidence about the
current schematic, not a specification of what the divider shall do.

## Issue #107: retiming attempt -- a real, measured, but partial improvement

Issue #104 (above) named four candidate retiming approaches and asked #107 to
choose one, justify it, and re-measure. This section records that attempt,
its result, and why the result is an honest partial improvement rather than
the durable fix #107's own scope asked for.

### Chosen approach: flatten the borrow chain (candidate 1), evaluated
### against a naive drive-strength bump (candidate 3)

**Chosen: flatten the ripple-borrow chain.** `BOR3` and `BOR4` (borrow into
bits 3 and 4) are now each computed by a single wide AND gate
(`and3_2`/`and4_2`) directly off `NQ0..NQ3`, instead of rippling through one
`and2_2` per intermediate bit (`BOR2 -> BOR3 -> BOR4`). `ZERO` is
restructured similarly: instead of `ZERO = BOR5 AND NQ5` (which required
`BOR5` -- itself the deepest node in the old chain -- to settle first),
`ZERO` is now `BOR4 AND NQ45`, where `NQ45 = NQ4 AND NQ5` is computed in
parallel off the bit-4/5 inverters. Both are algebraically identical to the
original equations (`BOR3 = NQ0*NQ1*NQ2`, `BOR4 = NQ0*NQ1*NQ2*NQ3`,
`ZERO = NQ0*NQ1*NQ2*NQ3*NQ4*NQ5`), so this is a pure retiming: same Boolean
function, fewer series gate levels. `BOR5` (still needed for the bit-5
decrement, `D5 = Q5 XOR BOR5`) is now computed as `BOR4 AND NQ4`, one level
deeper than `BOR4` -- with `and2_2`/`and3_2`/`and4_2` as the widest AND gates
`sky130_fd_sc_hd` offers (no `and5`), a depth-3 tree (`NQi` -> `BOR4` ->
`BOR5`) is the shallowest structure available for a 5-input AND, so this is
architecturally at or near the floor for this borrow-chain approach.

Net effect on `D5`'s combinational depth (`CLK` -> `Q0` -> `NQ0` -> ... ->
`D5`, not counting the `dfrtp_2` clk->Q itself): the old design was 7 gate
levels (`QINV0, BORAND2, BORAND3, BORAND4, BORAND5,` then `DECXOR5` or
`ZDET`+`LDMUX5` select, whichever was later). The retimed design is 5 levels
(`QINV0/QINV4/QINV5` in parallel at level 1, `BORAND4` at level 2, `BORAND5`
at level 3, `DECXOR5` at level 4, `LDMUX5` at level 5) -- `ZERO` now settles
at level 3 (`BORAND4` and `BORZ45` both at level 2, `ZDET` at level 3), one
level *before* the `DECXOR5` data path it used to co-determine the critical
path with, so `ZERO`/`LDMUX5`'s select is no longer the bottleneck at all;
the bottleneck is now purely the `BOR5`/`DECXOR5` decrement **data** path.

**Evaluated and rejected: uniform drive-strength bump (`_2` -> `_4`).**
Candidate 3 (#104's "cheapest" option) was tried as a second lever on top of
the flattened chain: every one of the 30 standard-cell instances in
`divider_intN.sch` was swapped from its `_2` variant to the PDK's `_4`
variant (same netlist connectivity, `sky130_fd_sc_hd__and2_2` ->
`__and2_4`, etc.), netlisted clean, and re-measured with the same
standalone diagnostic (below). **Result: it made timing worse, not
better** -- at `tt`/27 °C/1.80 V the `_2` design divides correctly through
1000 MHz; the otherwise-identical `_4` design fails already at 1000 MHz
(the same frequency the `_2` design still passes at). This is not a
netlisting error (pin order and connectivity were checked instance-by-
instance against the `_2` netlist; only the cell-type suffix differs) --
it is a real consequence of this circuit's **low fanout**. Every gate in
this chain drives at most 1-2 downstream gates; a `_4` cell's larger
output transistors and larger intrinsic self-capacitance cost more
switching time than they save on an already-light load, so uniformly
upsizing loses on every stage instead of winning on any of them. This
matches standard cell-sizing theory (oversizing a lightly loaded stage is a
net loss) but is worth recording plainly since #104 characterized this
lever as "the cheapest, buys a percentage" without measuring it -- measured,
for this circuit, it buys a **negative** percentage. A fanout-aware sizing
pass (upsize only genuinely high-fanout nodes like `NQ0`, which drives four
downstream gates; leave or downsize the single-fanout tail stages) might
still help, but that is a distinct, more fiddly optimization this pass did
not pursue given the schedule/verification-risk tradeoff the issue asked to
weigh -- the schematic in this PR keeps the `_2` drive strength throughout
(the flattening-only design), since it measured strictly better than the
`_2`+`_4` combination.

**Approaches not chosen.** Candidate 2 (pipeline/pre-compute `ZERO` a cycle
early) would have helped the *old* design, where the `ZERO`/`LDMUX5`-select
path was co-critical with the `DECXOR5` data path. It does not help *this*
design, because flattening `ZERO`'s own path (via `BOR4`/`NQ45`) already
moved it a level ahead of `DECXOR5` -- registering an already-non-critical
signal earlier buys nothing. Candidate 4 (dual-modulus prescaler) was not
attempted in this pass; see "What #107 does not close" below. Neither
choice is revisited here in code, only in the recommendation for the
follow-up.

### Standalone diagnostic: same method as #104's testbench (A)

Informal, uncommitted diagnostic -- same status and convention as #104's
diagnostics above and `design/vco/DESIGN.md`'s "informal sanity check"
table, not a `sim/` evidence record. `divider_intN` netlisted standalone
(`netlist/divider_intN.spice`, this PR's retimed version), driven by an
ideal rail-to-rail `pulse` `CLK` source (~12.5 ps edges), `RESETB` a `pwl`
released at 5-6 ns, 250 `CLK` cycles simulated per point (long enough for
roughly 10 divide-by-25 periods), `ngspice-46`, the same `sky130A` PDK
install and `sky130_fd_sc_hd.spice` include #104 used. `FBCLK` rising edges
and their spacing are read back from a `wrdata` dump at each point; a point
is scored **correct** only if it produces the expected edge count for the
window at a period matching `N / f_CLK` to within 2% (the very first
inter-edge gap, from reset release to the first steady-state reload, is
excluded from that check, since reset release is not phase-aligned to an
`N`-cycle boundary).

**Maximum correct-division frequency, `N = 25`, before vs. after this PR**
(the "before" column is #104's own table, reproduced from above):

| Corner (process / temp / supply) | Before #107 (exact / wrong) | After #107 (exact / wrong) | VCO top free-running freq. | Clears it? |
|---|---|---|---|---|
| `ss` / 125 °C / 1.62 V | 475 MHz / 500 MHz | **650 MHz** / 700 MHz | ~1.09 GHz | **No** |
| `sf` / 27 °C / 1.80 V | 700 MHz / 1.07 GHz | **950 MHz** / 1.0 GHz | ~1.09 GHz | **No** |
| `fs` / 27 °C / 1.80 V | 700 MHz / 1.07 GHz | **1.0 GHz** / 1.09 GHz | ~1.09 GHz | **No** (fails at exactly the target) |
| `tt` / 27 °C / 1.80 V | 765 MHz / 780 MHz | **1.0 GHz** / 1.09 GHz | ~1.09 GHz | **No** (close) |
| `ff` / −40 °C / 1.98 V | 1.07 GHz / 1.15 GHz | **≥1.3 GHz** / 1.8 GHz | ~1.09 GHz | **Yes** |

Every corner improved by roughly 25-45% (`ss`: +37%, `sf`: +36%, `fs`: +43%,
`tt`: +31%, `ff`: at least +21%, likely more -- the `ff` ceiling was not
pinned more precisely than "between 1.3 and 1.8 GHz" since it already clears
the target comfortably). This is a real, verified improvement, not a
rounding artifact: the `tt`/780 MHz and `ss`/500 MHz points that were wrong
before #107 are now measured exact-÷25 with the retimed netlist. But only
`ff` -- already the fastest, least-marginal corner before this issue -- now
clears the VCO's own ~1.09 GHz top free-running frequency (`design/vco/
DESIGN.md`'s sanity-check table). `ss`, `sf`, `fs` and `tt` all still fall
short, `ss` by the widest margin (650 MHz vs. a 1.09 GHz target -- still
only a 1.7x margin over the 250 MHz design target, up from #104's ~1.9x-
at-worst-corner, i.e. barely moved at the corner that matters most).

**Edge cases (test plan spot-check): `N = 4` and `N = 64` at 250 MHz,
`tt`/27 °C/1.80 V** -- both divide correctly with the retimed netlist
(`N = 4`: 62 `FBCLK` edges over the window, 16.000 ns period, exact;
`N = 64`: 4 edges, 256.000 ns period, exact). The retiming only changed how
the borrow/zero-detect signals are computed, not the reload mux or the
`NSEL` interface, so this is the expected result -- included here as the
direct confirmation the test plan asked for, not a surprise.

### What #107 does not close, and why

The scope this issue set for itself -- "the maximum correct-division
frequency at the worst ratified PVT corner sits comfortably above the VCO's
own top free-running frequency ... so no reachable VCO state can kill the
feedback path" -- is **not met** by this schematic change. Recorded here
honestly, per `CLAUDE.md`'s rule against laundering a miss, rather than
narrowed after the fact to fit what was achieved:

- The one-way trap #104 described (a cold start that pushes the VCO above
  the divider's ceiling permanently kills `FBCLK`, which removes negative
  feedback, which keeps `VCTRL` railed, which keeps the VCO above the
  ceiling) is **still reachable** at `ss`, `sf`, `fs`, and `tt` -- just at a
  25-45% higher frequency than before. It is closed only at `ff`.
- The fundamental obstacle this pass exposed: `BOR5` (needed for the bit-5
  decrement on every cycle, not only at reload -- see #104's finding that a
  mid-count borrow failure, not just a reload failure, is what causes the
  limit-cycle trap) is a 5-input AND of `NQ0..NQ4`. With `sky130_fd_sc_hd`'s
  widest AND gate being `and4_2`/`and4_4` (no `and5`), a depth-3 tree
  (inverters -> `and4` -> `and2`) is the shallowest structure available,
  and this pass already uses it. Going faster than that, for this counter
  *encoding* (binary, ripple-borrow), needs either faster gates (measured
  above to be a net loss at this fanout, at least without per-node
  fanout-aware sizing) or a different encoding entirely.
- **Recommendation for the follow-up** (not attempted here, to keep this
  PR's verification/schedule risk bounded as the issue asked): a
  dual-modulus prescaler front-end (#104/#100's already-named escalation,
  and `design/divider/DESIGN.md`'s original "Architecture choice" section's
  candidate that was deferred for being unneeded at v1's target frequency)
  is the structurally correct fix -- it replaces the long ripple-borrow
  path with a small, shallow fast counter clocked directly by the VCO, so
  the *slow*-clocked back-end counter (this design's own borrow chain,
  unmodified) gets a full divided-down clock period to settle instead of
  one VCO period. A fanout-aware gate-sizing pass (per the drive-strength
  finding above) is a smaller, cheaper thing to try first, but is not
  guaranteed to close a ~1.7x-to-1.09-GHz gap at `ss` on its own.

### No fresh `sim/pll-lock` record minted in this pass

Per `CLAUDE.md`'s append-only rule and this issue's own acceptance
criteria, a fresh closed-loop `sim/pll-lock` PVT-grid record is required
**before any claim that the retiming improves closed-loop behaviour**. This
pass makes no such claim -- the honest result above is that the one-way
trap is still reachable at 4 of 5 corners, so closed-loop cold-start
behaviour at those corners is not expected to differ materially from #104's
own closed-loop reproduction (still a real hazard, just at a higher VCTRL
excursion threshold). Minting a full-grid closed-loop record was also found
to be impractical within a single work session at the current manifest's
cost (`sim/pll-lock/testbench/tb.json`'s `tran_stop = 100us` /
`timeout_s = 10800`, no per-point parallelism in `sim/harness/runner.py`
-- an observed ~1.5-2 hours per point, i.e. days for the full 45-point
grid), independent of anything this issue changed; that cost is the same
one issue #103 already tracks for a fresh full-grid run against the current
manifest defaults. The follow-up recommended above should fold in a
closed-loop re-verification once a durable fix exists, rather than spending
that multi-hour cost against a design already known (from the standalone
diagnostic above) to still trip the trap at most corners.

### No spec edits from this issue

Nothing in `spec/target-spec.md` is edited or ratified by issue #107. Row 4
(multiplication ratio) and row 2 (output band) stay DRAFT.
