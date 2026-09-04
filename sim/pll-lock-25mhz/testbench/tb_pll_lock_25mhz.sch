v {xschem version=3.4.7 file_version=1.2
* tb_pll_lock_25mhz.sch -- cold-start lock-capable closed-loop PLL
* testbench, reference-input high band edge (issue #55)
*
* Sibling of sim/pll-lock/testbench/tb_pll_lock.sch (issue #52), itself a
* sibling of sim/pll/testbench/tb_pll.sch (issue #23): same DUT
* (design/top/top.sym, the four-block closed-loop PLL), same supply and
* reset stimulus and the same lock-capable manifest-injected `.control`
* analysis convention (no `.tran`/`.print` card here -- see
* tb_pll_lock.sch's own header for why). The only structural differences
* from tb_pll_lock.sch are the reference stimulus (`V2`, here 25 MHz
* instead of 10 MHz) and the `NSEL[5:0]` strap (here N=10 instead of N=25)
* -- see "N choice" below. See sim/pll-lock-1mhz/testbench/
* tb_pll_lock_1mhz.sch (the sibling low band-edge testbench, issue #55) for
* why a sibling testbench rather than a sim/harness stimulus-axis
* generalization was chosen.
*
* N choice (band edge: Fref = 25 MHz):
*   design/divider/DESIGN.md: NSEL[5:0] carries N-1 in plain binary, 6 bits
*   -> N = 1..64 representable, N = 4-64 is spec row 4's DRAFT range. N=10
*   is chosen here to land the closed-loop target INSIDE
*   sim/vco/records/20260819-131741-fe0e6df.md's characterized VCO tuning
*   range (~145.1 MHz at VCTRL=0.8V to ~1.034 GHz at VCTRL=1.6V):
*     N * Fref = 10 * 25 MHz = 250 MHz
*   250 MHz is deliberately the SAME target frequency
*   sim/pll-lock/testbench/tb_pll_lock.sch already targets (N=25 * 10 MHz
*   Fref), so this record is directly comparable to that one: only the
*   reference frequency (and, by construction, N) changes, not the target
*   output frequency or its position inside the measured VCO range.
*   NSEL[5:0] = N-1 = 9 = binary 001001 -> NSEL0=1, NSEL3=1, all other NSEL
*   bits 0, strapped below (VDD on NSEL0/NSEL3, GND on NSEL1/NSEL2/NSEL4/
*   NSEL5).
*
* Provenance: schematic-capture convention (label-based wiring, one
* ipin/opin/iopin/lab_pin per net, zero drawn wire segments) matches
* tb_pll_lock.sch's own convention; written fresh for this issue (no
* external source netlist), instance-for-instance identical to
* tb_pll_lock.sch except for the `V2` value, the NSEL strap, and this
* header comment.
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
C {devices/lab_pin.sym} -130 -100 0 0 {name=p5 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 -60 0 0 {name=p6 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 -20 0 0 {name=p7 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 20 0 0 {name=p8 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 60 0 0 {name=p9 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 100 0 0 {name=p10 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 130 0 0 0 {name=p11 sig_type=std_logic lab=CLK}
C {devices/vsource.sym} 600 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/lab_pin.sym} 600 -30 0 0 {name=p12 sig_type=std_logic lab=VDD}
C {devices/gnd.sym} 600 30 0 0 {name=l1 lab=GND}
C {devices/vsource.sym} 800 0 0 0 {name=V2 value="pulse(0 1.8 0 1n 1n 19n 40n)" savecurrent=false}
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
C {devices/title.sym} -200 500 0 0 {name=l4 author="2AM Logic (issue #55, sky130 PLL row-3 high band-edge lock testbench)"}
