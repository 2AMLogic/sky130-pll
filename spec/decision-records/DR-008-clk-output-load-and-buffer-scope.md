# DR-008: provisional 1 pF `CLK` characterization load and buffered-output regression scope (rows 14/15)

- **Status**: proposed. This record does **not** ratify spec rows 14 or 15,
  which stay **DRAFT**. See "Status notes".
- **Date**: 2026-10-15
- **Author**: Builder agent (issue #232)
- **Ratifies against / input to**: #232 (output stage); input to the eventual
  ratification of rows 14 (duty cycle) and 15 (output levels)
- **Supersedes**: none

One decision per record. The decision here is the **load the `CLK` pin is
characterized into, and the bounded regression set that follows from adding an
output buffer**. The circuit is `design/clk-buf/`; the numbers it produces are
evidence records under `sim/`.

## Context

Rows 14 and 15 describe `CLK` as a chip output. Before #232 the exported `CLK`
was the VCO's own output node (`design/top/DESIGN.md`): the same net drove the
pin and `divider_intN.CLK`, so any capacitance placed on the pin loaded the
ring-side node directly, and row 15's "stated external load" was undefined, so
the row had nothing to be measured against. No downstream receiver, pad or
package is specified anywhere in the spec.

The operator's 2026-10-15 disposition on #232 authorized option (a): a
provisional 1 pF buffered-`CLK` characterization with a bounded paired
regression, rows 14/15 left DRAFT, pad/package/ESD signoff excluded, and #98's
convergence work ruled non-blocking.

## Decision

1. **Load.** `CLK` is characterized into a **lumped 1 pF capacitor from `CLK`
   to `GND`** on the existing shared `VDD`/`GND` supply. This is a
   *characterization contract*, chosen to be a plausible small on-board/next-
   chip input plus routing; it is **not** a measured or specified receiver, and
   it is not a pad/package model (no bond-wire inductance, no ESD structure, no
   series resistance).
2. **Hardware.** The exported `CLK` is the output of a **non-inverting
   two-inverter chain** (`design/clk-buf`), fed from the VCO node. The
   feedback divider stays on the VCO node (`VCOCLK` in `design/top`), so the
   divider's input timing is the ring-side net exactly as before; the chain's
   first stage is minimal (W 1/2 µm n/p) to keep the capacitance the ring sees
   small, and the second stage (W 12/24 µm) is sized by simulation to drive
   1 pF. Sizing evidence is in `design/clk-buf/DESIGN.md`.
3. **Regression set** (bounded; nothing else is re-run on the strength of this
   record):
   - a **45-point loaded output campaign** (`sim/clk-output`): V_OH, V_OL,
     duty and 10-90 % edge time at the pin;
   - **paired buffered/unbuffered VCO tuning sweeps**: the buffered half is
     `sim/vco-buffered`, the unbuffered half is the existing 45-point
     `sim/vco` record `20260904-163130-f3ae976`;
   - **paired nominal closed-loop runs**: `sim/pll-lock`, `sim/pll-lock-1mhz`
     and `sim/pll-lock-25mhz` at tt / 27 °C / 1.80 V, with the load on `CLK`,
     each read against its existing record, reporting feedback frequency, lock,
     duty and row-9 period jitter.
4. **Evidence rules.** Every new run mints a new append-only record naming the
   baseline it is compared with. No existing record is edited or deleted. A
   figure that misses a DRAFT bound is recorded as a miss; the bounds in rows
   14/15 are not altered by this record.

## Alternatives considered

- **Settle the downstream load first** (operator option b). Avoids choosing an
  arbitrary number, but postpones all output-stage evidence until a receiver
  exists, and the spec supplies none. Revisit when a downstream interface is
  specified: a different load only needs `sim/clk-output` and the three
  closed-loop runs repeated, which is why the load is a single schematic value.
- **Defer until #98 converges** (option c). Rejected by the operator: it would
  leave `CLK` loading the ring and rows 14/15 without loaded evidence.
- **Re-run every closed-loop campaign.** Rejected as unbounded while #98 is
  open. The campaigns that instantiate `design/top` and are *not* in the set
  above (`sim/pll`, `sim/pll-lock-mc*`, `sim/loop-ripple`,
  `sim/lf-c{1,2}-jitter-sensitivity`) now netlist the buffer with its output
  **unloaded**. Their existing records describe the pre-buffer top level and
  stay valid as such; any new record from them is a different circuit, and
  should say so when it is minted.
- **A larger or tapered chain.** Not needed at 1 pF in the probes; a heavier
  load would be a separate decision.

## Consequences

- The `CLK` pin is isolated from the ring-side net by one small gate load. The
  cost is that gate load on the VCO node (measured by the paired sweeps, not
  assumed to be negligible), one extra stage delay in the pin path (irrelevant
  to the loop, which taps `VCOCLK`) and the buffer's dynamic power at 1 pF.
- Rows 14/15 now have a defined measurement point and load, but remain DRAFT
  and have **no pad, package or ESD** evidence.
- `design/top/netlist/top.spice` and `signoff/design-snapshot-consistency.py`
  gain a `clk_buf` block. No layout exists for the buffer, so anything keyed to
  the pre-buffer top-level device plan is stale until a layout issue adds it.
- The load rationale lives here, not in a testbench: the three closed-loop
  testbenches, `sim/clk-output` and `sim/vco-buffered` each carry a `CL`
  capacitor that cites this record.

## Status notes

`proposed`. A later record may ratify rows 14/15 against evidence minted under
this contract, or replace the 1 pF figure once a real receiver is specified.
The grid-scale runs listed under "Regression set" are tracked on the PR for
#232; this record is the contract they are measured against and does not claim
their results.
