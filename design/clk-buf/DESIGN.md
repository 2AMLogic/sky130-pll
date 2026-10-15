# CLK output buffer — design rationale (issue #232)

`clk_buf.sch` is a **non-inverting two-inverter chain** between the VCO's `CLK`
node and the exported `CLK` pin of `design/top`. It exists so spec rows 14
(duty cycle) and 15 (output levels) have a pin to measure and so the pin's load
no longer sits on the ring-side net. The load it is characterized into, and
what is and is not claimed, is `spec/decision-records/DR-008-clk-output-load-and-buffer-scope.md`.

Forward design (CLAUDE.md "Reverse-engineering-free"): a textbook inverter
chain on the ratified 1.8 V core devices (`DR-001`), not derived from any
existing silicon or netlist.

## Topology and sizing

| Device | Type | W (µm) | L (µm) | Role |
|---|---|---|---|---|
| `MB1_P` / `MB1_N` | pfet / nfet 01v8 | 2 / 1 | 0.15 | stage 1: kept minimal so the ring-side node sees ~one small gate |
| `MB2_P` / `MB2_N` | pfet / nfet 01v8 | 24 / 12 | 0.15 | stage 2: drives the 1 pF characterization load |

Pins: `VDD`, `GND`, `CLKIN` (from the VCO node `VCOCLK`), `CLKOUT` (the pin).
Top-level wiring: `VCO.CLK -> VCOCLK -> {divider_intN.CLK, clk_buf.CLKIN}`;
`clk_buf.CLKOUT -> CLK`. The divider stays on the VCO node, so feedback timing
is the ring-side net as before.

## How the sizing was chosen (pre-campaign probes — not evidence)

Three candidate sizes were run once each, and four extreme corners once each,
as ad-hoc single-point ngspice transients (the `design/vco` netlist at
VCTRL = 0.865 V driving the chain into 1 pF; scratch decks, not committed, not
`sim/` records, no PVT claim). They were used only to pick a size:

| stage 1 (n/p) | stage 2 (n/p) | tt/27 °C/1.8 V duty | 10-90 % edges (rise / fall) |
|---|---|---|---|
| 1 / 2 | 12 / 24 | 50.5 % | 140 ps / 136 ps |
| 2 / 4 | 12 / 24 | 49.7 % | 134 ps / 133 ps |
| 2 / 4 | 8 / 16 | 48.7 % | 198 ps / 196 ps |

Stage 1 = 1/2 with stage 2 = 12/24 was kept: the smallest first-stage load that
still gave rail-to-rail swing and a duty close to 50 %. In the four extreme
single points tried (ss/125 °C/1.62 V, ff/−40 °C/1.98 V, sf/27 °C/1.62 V,
fs/27 °C/1.98 V) duty ranged 48.1-51.2 % and the output swung to within a few mV
of both rails. **These are sizing probes, not the 45-point record**; the
campaign that measures rows 14/15 is `sim/clk-output`.

## What this design does not claim

- No pad, package, bond-wire or ESD capability: the load is a lumped 1 pF.
- No claim that rows 14/15 are met or ratified; both stay DRAFT.
- No layout exists for this block.
- No claim about the loop's behavior with the buffer attached: the paired
  tuning and closed-loop campaigns listed in DR-008 measure that.

## Regenerating the netlist

`netlist/clk_buf.spice` is the connectivity snapshot, regenerated per
`design/README.md`. On a host whose xschem leaves the PDK symbols'
`ad/as/pd/ps/nrd/nrs` `expr(...)` attributes unevaluated, the committed
snapshots carry the evaluated numbers (`ad = int((nf+1)/2)·W/nf·0.29`, etc.),
so evaluate those before committing; the same step reproduces the committed
`design/vco/netlist/vco_ring5.spice` exactly.
