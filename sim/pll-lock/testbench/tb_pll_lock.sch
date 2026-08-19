v {xschem version=3.4.7 file_version=1.2
* tb_pll_lock.sch -- cold-start lock-capable closed-loop PLL testbench (issue #52)
*
* Sibling of sim/pll/testbench/tb_pll.sch (issue #23): same DUT
* (design/top/top.sym, the four-block closed-loop PLL), same supply/
* reference/reset stimulus and the same NSEL[5:0]=011000 (N=25) strapping,
* so the two testbenches are directly comparable. The only structural
* difference is the analysis: this schematic carries NO `.tran`/`.print`
* card of its own -- sim/harness/measure.py's injected `.control` block
* supplies the transient window, waveform capture, and completion marker,
* so the window length is a manifest knob (sim/pll-lock/testbench/tb.json's
* `measure` block) instead of a schematic edit. See
* sim/vco/testbench/tb_vco.sch for the same pattern, applied there to the
* open-loop VCO characterization campaign.
*
* Why a sibling instead of extending tb_pll.sch in place: sim/pll's own
* claim (sim/README.md's directory table) is a harness-plumbing check with
* a stated 200 ns window "far short of a cold-start lock transient" -- that
* claim and its evidence trail stay intact. This testbench's claim is the
* stronger one issue #52 asks for: does the loop actually lock, and to
* what frequency/duty cycle, across a real PVT sweep.
*
* Lock target: NSEL[5:0]=011000 (N=25) against the 10 MHz reference below
* gives a target closed-loop output of N * Fref = 25 * 10 MHz = 250 MHz --
* see sim/pll-lock/testbench/tb.json's `measure.lock` block for the
* tolerance/hold-cycle criterion applied to it, and
* sim/harness/measure.py's module docstring for what "locked" means here.
*
* Provenance: schematic-capture convention (label-based wiring, one
* ipin/opin/iopin/lab_pin per net, zero drawn wire segments) matches
* sim/pll/testbench/tb_pll.sch's own convention; written fresh for this
* issue (no external source netlist), instance-for-instance identical to
* tb_pll.sch except for the MODELS code block described above.
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
** sky130 PDK model include (tt corner) -- patched per-point by sim/harness
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
C {devices/title.sym} -200 500 0 0 {name=l4 author="2AM Logic (issue #52, sky130 PLL cold-start lock testbench)"}
