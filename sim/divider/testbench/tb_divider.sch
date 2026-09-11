v {xschem version=3.4.7 file_version=1.2
* tb_divider.sch -- standalone divider_intN PVT testbench, N=25 (issue #129)
*
* Instantiates design/divider/divider_intN.sym (the standalone programmable
* integer-N feedback divider, issue #27, retimed to the dual-modulus /2-/3
* prescaler front-end by issue #114) open-loop: no VCO, no PFD/charge pump,
* no loop filter -- CLK is driven directly by an ideal rail-to-rail `pulse`
* source instead of the VCO's own output, exactly the method
* design/divider/DESIGN.md's "Issue #114" section already validated
* (informally) against issue #107's own published table before this issue
* turned it into a committed sim/ record.
*
* NSEL[5:0] is strapped statically via lab_pin ties straight to VDD/GND
* (the same convention sim/pll-lock/testbench/tb_pll_lock.sch uses for
* design/top/top.sch's own NSEL bits) rather than swept -- N is fixed per
* testbench directory, one directory per modulus under test (sim/divider
* for N=25, sim/divider-n4/-n64/-n5/-n63 for the modulus-decode spot
* checks; see each directory's own tb.json `claim`).
*
* This testbench straps N=25 (NSEL[5:0]=011000, the same modulus
* sim/pll-lock straps), the design's own 250 MHz lock-target modulus, at a
* fixed CLK frequency of ~1.100 GHz -- at or above the VCO's own
* characterized top free-running frequency (~1.09 GHz,
* design/vco/DESIGN.md's sanity-check table / sim/vco/records/), which is
* the frequency band design/divider/DESIGN.md's issue #114 section measured
* this design to divide correctly through at every one of the 45 ratified
* PVT points (worst case ~1166 MHz at ss/-40 degC/1.62 V) -- so this record
* substantiates that finding as committed sim/ evidence instead of an
* informal, uncommitted diagnostic.
*
* RESETB is released by a pwl at 5-6 ns, matching sim/pll-lock's own
* power-on-reset stimulus and design/divider/DESIGN.md's issue #114
* standalone-diagnostic method. CLK's rise/fall time (12.5 ps) also matches
* that method exactly, so this record is directly comparable to the design
* document's own informal table.
*
* Measurement: sim/harness/measure.py's `lock` block, applied to FBCLK
* instead of a real closed-loop PLL's CLK -- target_hz = f_CLK / N, which
* scores "the divider produced a clean, steady N:1 division" the same way
* issue #114's own 2%-of-N/f_CLK criterion did, just via the harness's
* general-purpose sliding-window lock detector instead of a bespoke script.
*
* Provenance: schematic-capture convention (label-based wiring, one
* ipin/opin/iopin/lab_pin per net, zero drawn wire segments) matches
* sim/pll-lock/testbench/tb_pll_lock.sch's own convention; written fresh
* for this issue (no external source netlist).
}
G {}
V {}
S {}
E {}
C {design/divider/divider_intN.sym} 0 0 0 0 {name=XXDIV}
C {devices/lab_pin.sym} 0 -180 0 0 {name=p1 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 0 180 0 0 {name=p2 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 -140 0 0 {name=p3 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} -130 -100 0 0 {name=p4 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} -130 -60 0 0 {name=p5 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 -20 0 0 {name=p6 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 20 0 0 {name=p7 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 60 0 0 {name=p8 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 100 0 0 {name=p9 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 140 0 0 {name=p10 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 130 0 0 0 {name=p11 sig_type=std_logic lab=FBCLK}
C {devices/vsource.sym} 600 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/lab_pin.sym} 600 -30 0 0 {name=p12 sig_type=std_logic lab=VDD}
C {devices/gnd.sym} 600 30 0 0 {name=l1 lab=GND}
C {devices/vsource.sym} 800 0 0 0 {name=V2 value="pulse(0 1.8 0 12.5p 12.5p 442p 909p)" savecurrent=false}
C {devices/lab_pin.sym} 800 -30 0 0 {name=p13 sig_type=std_logic lab=CLK}
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
** bodies. See sim/pll-lock/testbench/tb_pll_lock.sch's identical include.
.include $::SKYWATER_STDCELLS/sky130_fd_sc_hd.spice
** No .tran/.print card here on purpose -- sim/harness/measure.py injects
** the analysis from this manifest's own measure block (transient window,
** waveform dump, completion marker). See this file's header comment.
"
spice_ignore=false}
C {devices/title.sym} -200 500 0 0 {name=l4 author="2AM Logic (issue #129, sky130 standalone divider_intN PVT testbench, N=25)"}
