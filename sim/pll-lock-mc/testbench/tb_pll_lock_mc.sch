v {xschem version=3.4.7 file_version=1.2
* tb_pll_lock_mc.sch -- Monte Carlo statistical companion to
* sim/pll-lock/testbench/tb_pll_lock.sch (issue #20's second acceptance-
* criteria bullet: a real evidence record against ratified target-spec row 9,
* period jitter)
*
* Instance-for-instance identical to sim/pll-lock/testbench/tb_pll_lock.sch --
* same DUT (design/top/top.sym, the four-block closed-loop PLL), same supply/
* reference/reset stimulus, and the same NSEL[5:0]=011000 (N=25) strapping
* against a 10 MHz reference (target closed-loop output N * Fref = 250 MHz).
* A distinct schematic file exists per this repo's one-directory-per-distinct-
* claim convention (sim/README.md) rather than pointing two experiments at one
* file: sim/pll-lock's own PVT-sweep claim and evidence trail stay untouched,
* and this experiment's own claim (a Monte Carlo statistical population at one
* fixed PVT point, not a corner sweep) gets its own netlist-snapshot/record
* history. Like tb_pll_lock.sch, this schematic carries NO `.tran`/`.print`
* card of its own -- sim/harness/measure.py's injected `.control` block
* supplies the transient window, waveform capture, and completion marker, so
* the window length is this experiment's own manifest knob
* (sim/pll-lock-mc/testbench/tb.json's `measure` block), sized for a Monte
* Carlo campaign (many short trials at one point) rather than
* sim/pll-lock's PVT-sweep window (few points, each run once).
*
* DR-006 (spec/decision-records/DR-006-statistical-rows-ratification.md)
* ratifies row 9 "verified over [the ratified PVT grid] plus a local-mismatch
* Monte Carlo population" -- this experiment is the Monte Carlo half of that;
* sim/pll-lock's own PVT sweep (once a fresh full-grid record lands against
* today's cold-start-nudge defaults, see its tb.json's methodology_note) is
* the other half.
*
* Provenance: schematic-capture convention (label-based wiring, one
* ipin/opin/iopin/lab_pin per net, zero drawn wire segments) matches
* sim/pll-lock/testbench/tb_pll_lock.sch's own convention; copied from it
* verbatim except for this header comment and the title block below, since
* the DUT wiring, strapping and stimulus this experiment needs are identical.
}
G {}
V {}
S {}
E {}
C {design/top/top.sym} 0 0 0 0 {name=XXTOP}
C {devices/lab_pin.sym} 0 -240 0 0 {name=p1 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 0 240 0 0 {name=p2 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 -180 0 0 {name=p3 sig_type=std_logic lab=REF}
C {devices/lab_pin.sym} -130 -140 0 0 {name=p4 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} -130 -100 0 0 {name=p5 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 -60 0 0 {name=p6 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 -20 0 0 {name=p7 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 20 0 0 {name=p8 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 60 0 0 {name=p9 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 100 0 0 {name=p10 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 130 0 0 0 {name=p11 sig_type=std_logic lab=CLK}
C {devices/vsource.sym} 600 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/lab_pin.sym} 600 -30 0 0 {name=p12 sig_type=std_logic lab=VDD}
C {devices/gnd.sym} 600 30 0 0 {name=l1 lab=GND}
C {devices/vsource.sym} 800 0 0 0 {name=V2 value="pulse(0 1.8 0 1n 1n 48n 100n)" savecurrent=false}
C {devices/lab_pin.sym} 800 -30 0 0 {name=p13 sig_type=std_logic lab=REF}
C {devices/gnd.sym} 800 30 0 0 {name=l2 lab=GND}
C {devices/vsource.sym} 1000 0 0 0 {name=V3 value="pwl(0 0 5n 0 6n 1.8)" savecurrent=false}
C {devices/lab_pin.sym} 1000 -30 0 0 {name=p14 sig_type=std_logic lab=RESETB}
C {devices/gnd.sym} 1000 30 0 0 {name=l3 lab=GND}
C {devices/code.sym} 1300 300 0 0 {name=MODELS
only_toplevel=true
format="tcleval( @value )"
value="
** sky130 PDK model include (tt corner) -- patched per-trial by sim/harness
.lib $::SKYWATER_MODELS/sky130.lib.spice tt
** sky130_fd_sc_hd standard-cell subcircuit deck -- design/divider's cells
** need it; the primitive-device .lib above does not define these subckt
** bodies. See sim/pll/testbench/tb_pll.sch's identical include.
.include $::SKYWATER_STDCELLS/sky130_fd_sc_hd.spice
** No .tran/.print card here on purpose -- sim/harness/measure.py injects
** the analysis from this manifest's own measure block (transient window,
** waveform dump, completion marker). See this file's header comment.
"
spice_ignore=false}
C {devices/title.sym} -200 500 0 0 {name=l4 author="2AM Logic (issue #20, sky130 PLL Monte Carlo period-jitter testbench)"}
