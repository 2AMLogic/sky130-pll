v {xschem version=3.4.7 file_version=1.2
* tb_divider_n20.sch -- standalone divider_intN testbench, N=20 (issue #352)
*
* Sibling of sim/divider-n5/testbench/tb_divider_n5.sch (same DUT, same
* open-loop topology, same RESETB/CLK stimulus convention) -- see
* sim/divider/testbench/tb_divider.sch's header comment for the full
* rationale. This testbench straps N=20: NSEL[5:0] carries N-1 = 19 in plain
* binary (design/divider/DESIGN.md, "NSEL[5:0] ... carries N - 1"), i.e.
* NSEL[5:0]=010011 (NSEL0=1, NSEL1=1, NSEL2=0, NSEL3=0, NSEL4=1, NSEL5=0).
* N=20 is even, so it takes the even decode path (ODD=0). It is the
* ratio of the proposed 25 MHz x 20 = 500 MHz interface (DR-011 Step 2).
* CLK here is a placeholder 250 MHz pulse; sim/run_fmax.py rewrites the CLK
* and RESETB sources per probe. This bench has no campaign scope of its own.
*
* Provenance: schematic-capture convention (label-based wiring, one
* ipin/opin/iopin/lab_pin per net, zero drawn wire segments) matches
* sim/divider/testbench/tb_divider.sch's own convention; written fresh for
* issue #129; N=20 strapping derived independently for issue #352 (no external source netlist).
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
C {devices/lab_pin.sym} -130 -60 0 0 {name=p5 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 -20 0 0 {name=p6 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 20 0 0 {name=p7 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 60 0 0 {name=p8 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 100 0 0 {name=p9 sig_type=std_logic lab=VDD}
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
C {devices/title.sym} -200 500 0 0 {name=l4 author="2AM Logic (issue #352, sky130 standalone divider_intN testbench, N=20)"}
