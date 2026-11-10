# design/divider-iq — I/Q divide-by-2 (DR-010 topology, Proposed)

Issue #422. Two `sky130_fd_sc_hd` flops on the 2x clock `CLK2X`, async
active-low `RESETB` forcing both outputs to 0:

| Instance | Cell | Edge | D | Q |
|---|---|---|---|---|
| `XFI` | `dfrtp_2` | rising | `NQQ` (= ~`CLK90`, from `XFB` `inv_2`) | `CLK` |
| `XFQ` | `dfrtn_1` | falling | `CLK` | `CLK90` |

`CLK90` lags `CLK` by D·T2 plus the clk→Q difference of the two flops (the
closed form in `sim/phase-quadrature-model/README.md`); this cell exists so
that offset is measured on a netlist, not derived. `dfrtn_1` is the only
falling-edge reset flop in this cell family, so the flops are not drive
matched; any skew from that is part of what the campaigns measure. No output
buffers (out of scope for #422). No layout, LVS or Monte Carlo.

Netlist: `netlist/divider_iq.spice`, from `klt netlist` (never raw `xschem`).
Evidence: `sim/vco-2x-iq-scan/`, `sim/vco-2x-iq-25mhz/`, `sim/vco-2x-iq-50mhz/`
(testbench driving it from `design/vco/vco_ring5`, 10 fF stand-in load on each
output, an assumption).
