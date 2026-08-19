v {xschem version=3.4.7 file_version=1.2
* tb_vco.sch -- VCO frequency-vs-VCTRL characterization testbench (issue #52)
*
* Instantiates design/vco/vco_ring5.sym (the standalone current-starved
* 5-stage ring VCO, issue #24) open-loop: a fixed supply, a DC control
* voltage VCTRL, and the ring's buffered CLK output. The control voltage is
* the swept axis -- sim/harness rewrites V2's DC value once per swept point
* and re-runs the transient inside a single ngspice invocation (see the
* `measure.sweep` block of sim/vco/testbench/tb.json and
* sim/harness/measure.py), so one run per PVT point produces the whole
* frequency-vs-VCTRL curve at that corner.
*
* Why this testbench exists: design/vco/DESIGN.md's tuning-range table is
* explicitly disclaimed there as "a single, informal, uncommitted ngspice
* sanity check ... one process corner (tt), one temperature (27 deg C,
* ngspice default), no PVT sweep, not written as a sim/ record". This
* testbench turns that into real, committed sim/ evidence across the full
* PVT matrix, so a future decision record has something citable to argue
* spec/target-spec.md row 2 (output band) and row 5 (Kvco) from. It does not
* itself ratify any row -- per CLAUDE.md, ratification is a separate
* decision-record act.
*
* Startup kick: a ring oscillator's DC operating point is the (unstable)
* all-stages-at-midrail equilibrium, and a noiseless simulator can sit on it
* indefinitely. The harness therefore runs each swept point with `uic` after
* forcing RING0 low via a `.ic` card (see tb.json's `measure.ic`), which is
* the standard way to start a ring in SPICE and is not a design change --
* the ring's own loop gain is what carries it away from the initial state.
*
* Provenance: schematic-capture convention (label-based wiring, one
* ipin/opin/iopin/lab_pin per net, zero drawn wire segments) matches
* design/vco/vco_ring5.sch's own convention and sim/pll/testbench/tb_pll.sch's
* precedent; written fresh for this issue (no external source netlist).
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
C {devices/vsource.sym} 800 0 0 0 {name=V2 value=0.9 savecurrent=false}
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
C {devices/title.sym} -200 500 0 0 {name=l3 author="2AM Logic (issue #52, sky130 VCO frequency-vs-VCTRL characterization)"}
