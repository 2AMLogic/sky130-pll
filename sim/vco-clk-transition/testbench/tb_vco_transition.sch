v {xschem version=3.4.7 file_version=1.2
* tb_vco_transition.sch -- design/vco's CLK transition-time probe (issue #186)
*
* Instantiates design/vco/vco_ring5.sym (the standalone current-starved
* 5-stage ring VCO, issue #24) open-loop, exactly as sim/vco/testbench/
* tb_vco.sch does -- a fixed supply, a DC control voltage VCTRL, and the
* ring's buffered CLK output -- but with VCTRL held at a single FIXED value
* instead of swept: 0.865 V, design/top/DESIGN.md's own log-interpolated
* "VCTRL @ 250 MHz" figure for the tt/125 C/1.80 V point (that document's
* capture-window table, derived from the committed 45-point
* sim/vco/records/20260904-163130-f3ae976.md). That is also
* sim/pll-lock-mc's own base (corner, temperature, supply) point -- the one
* this repo's row-9 period-jitter evidence is measured at -- so this probe
* sits at (or as near as an open-loop point can get to) the closed loop's
* own row-9 operating point.
*
* Why this testbench exists: sim/harness/measure.py's period-jitter
* reducer's own measurement-resolution floor (sim/jitter-floor/, issue #178)
* depends on the ratio of the measured clock's transition (edge) time to the
* dump-grid step, and no sim/ record had ever measured that transition time
* for design/vco's own CLK -- so the applicable member of sim/jitter-floor's
* variant family could not be read off it. This testbench measures that
* figure directly, via sim/harness/measure.py's `transition_time` extractor
* (a `measure.transition` manifest block alongside `measure.duty_cycle`),
* dumped at a fine step (tens of ps) over a window long enough (200 ns) to
* average several dozen edges.
*
* Startup kick: a ring oscillator's DC operating point is the (unstable)
* all-stages-at-midrail equilibrium, and a noiseless simulator can sit on it
* indefinitely. The harness therefore runs this point with `uic` after
* forcing RING0 low via a `.ic` card (see tb.json's `measure.ic`), the same
* convention sim/vco/testbench/tb_vco.sch uses.
*
* Provenance: schematic-capture convention (label-based wiring, one
* ipin/opin/iopin/lab_pin per net, zero drawn wire segments) and topology
* copied from sim/vco/testbench/tb_vco.sch (issue #52) -- same DUT, same
* open-loop harness, only VCTRL's fixed value and the injected `measure`
* block differ. No external source netlist.
}
G {}
V {}
S {}
E {}
C {design/vco/vco_ring5.sym} 0 0 0 0 {name=XXVCO}
C {devices/lab_pin.sym} 0 -80 0 0 {name=p1 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 0 80 0 0 {name=p2 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 0 0 0 {name=p3 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} 130 0 0 0 {name=p4 sig_type=std_logic lab=CLK}
C {devices/vsource.sym} 600 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/lab_pin.sym} 600 -30 0 0 {name=p5 sig_type=std_logic lab=VDD}
C {devices/gnd.sym} 600 30 0 0 {name=l1 lab=GND}
C {devices/vsource.sym} 800 0 0 0 {name=V2 value=0.865 savecurrent=false}
C {devices/lab_pin.sym} 800 -30 0 0 {name=p6 sig_type=std_logic lab=VCTRL}
C {devices/gnd.sym} 800 30 0 0 {name=l2 lab=GND}
C {devices/code.sym} 1300 300 0 0 {name=MODELS
only_toplevel=true
format="tcleval( @value )"
value="
** sky130 PDK model include (tt corner) -- patched per-point by sim/harness
.lib $::SKYWATER_MODELS/sky130.lib.spice tt
"
spice_ignore=false}
C {devices/title.sym} -200 500 0 0 {name=l3 author="2AM Logic (issue #186, design/vco CLK transition-time probe)"}
}
