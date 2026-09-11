v {xschem version=3.4.7 file_version=1.2
* tb_divider_n5.sch -- standalone divider_intN PVT testbench, N=5 (issue #129)
*
* Sibling of sim/divider/testbench/tb_divider.sch (same DUT, same open-loop
* topology, same RESETB/CLK stimulus convention) -- see that file's header
* comment for the full rationale. This testbench straps N=5
* (NSEL[5:0]=000100), the smallest *odd* modulus in the DRAFT range
* (spec/target-spec.md row 4, N = 4-64) -- the odd decode path exercises
* exactly one /3 prescaler period per output period (ODD=1;
* design/divider/DESIGN.md's "Modulus correctness across the DRAFT range"
* table), which the N=4/N=64 even-path records do not. CLK is fixed at
* 250 MHz, the design's own lock target. Per issue #129's scope, this
* record covers only the two named corners (tt/27 degC/1.80 V and
* ss/125 degC/1.62 V) rather than the full grid -- see this directory's
* tb.json `methodology_note` and the record's own subset-reason field.
*
* Provenance: schematic-capture convention (label-based wiring, one
* ipin/opin/iopin/lab_pin per net, zero drawn wire segments) matches
* sim/divider/testbench/tb_divider.sch's own convention; written fresh for
* this issue (no external source netlist).
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
C {devices/lab_pin.sym} -130 20 0 0 {name=p7 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 60 0 0 {name=p8 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 100 0 0 {name=p9 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 140 0 0 {name=p10 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 130 0 0 0 {name=p11 sig_type=std_logic lab=FBCLK}
C {devices/vsource.sym} 600 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/lab_pin.sym} 600 -30 0 0 {name=p12 sig_type=std_logic lab=VDD}
C {devices/gnd.sym} 600 30 0 0 {name=l1 lab=GND}
C {devices/vsource.sym} 800 0 0 0 {name=V2 value="pulse(0 1.8 0 12.5p 12.5p 1987.5p 4n)" savecurrent=false}
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
C {devices/title.sym} -200 500 0 0 {name=l4 author="2AM Logic (issue #129, sky130 standalone divider_intN PVT testbench, N=5)"}
