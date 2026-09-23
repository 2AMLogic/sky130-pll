v {xschem version=3.4.7 file_version=1.2
* tb_loop_ripple.sch -- closed-loop VDD/VCTRL ripple-in-lock testbench (issue #166)
*
* Sibling of sim/pll-lock/testbench/tb_pll_lock.sch (issue #52): same DUT
* (design/top/top.sym, the four-block closed-loop PLL), same reference /
* reset stimulus and the same NSEL[5:0]=011000 (N=25, 250 MHz target)
* strapping, and -- like that testbench -- NO `.tran`/`.print` card of its
* own: sim/harness/measure.py injects the transient window, the DR-005
* cold-start `.ic` cards, the waveform capture and the completion marker
* from sim/loop-ripple/testbench/tb.json's `measure` block.
*
* The ONE structural difference: the supply. tb_pll_lock.sch ties the DUT's
* VDD straight to an ideal voltage source, which makes v(VDD) ripple zero by
* construction -- no measurement of the block's self-generated rail
* disturbance is possible through an ideal source. Here the ideal source V1
* drives an upstream node VSUP, and a series resistor RPDN (1 ohm) stands in
* for the power-delivery network between that source and the block's VDD
* pin. The block's own switching current develops its rail disturbance
* across RPDN, and that is what v(VDD) measures. RPDN is a TESTBENCH
* assumption (no decoupling capacitance, purely resistive), not a design
* value: for a resistive PDN the disturbance scales linearly with it, and
* the manifest's methodology_note says how to read the number. The DUT
* (design/top/top.sch) is untouched.
*
* The NSEL straps tie to the DUT-side VDD (after RPDN), exactly as a
* strap to the block's own rail would in silicon; they are CMOS gate inputs
* and draw no DC current.
*
* Provenance: derived from sim/pll-lock/testbench/tb_pll_lock.sch (this
* repo, last changed at commit f00ce3e) -- instance-for-instance identical
* except for V1's positive node (VSUP instead of VDD), the added RPDN, and
* this header. Schematic-capture convention (label-based wiring, one
* lab_pin/gnd per net, zero drawn wire segments) matches that file's.
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
C {devices/lab_pin.sym} 600 -30 0 0 {name=p12 sig_type=std_logic lab=VSUP}
C {devices/gnd.sym} 600 30 0 0 {name=l1 lab=GND}
C {devices/res.sym} 450 0 0 0 {name=RPDN m=1 value=1 footprint=1206 device=resistor}
C {devices/lab_pin.sym} 450 -30 0 0 {name=p15 sig_type=std_logic lab=VSUP}
C {devices/lab_pin.sym} 450 30 0 0 {name=p16 sig_type=std_logic lab=VDD}
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
** bodies. See sim/pll-lock/testbench/tb_pll_lock.sch's identical include.
.include $::SKYWATER_STDCELLS/sky130_fd_sc_hd.spice
** No .tran/.print card here on purpose -- sim/harness/measure.py injects
** the analysis from this manifest's own measure block (transient window,
** waveform dump, completion marker). See this file's header comment.
"
spice_ignore=false}
C {devices/title.sym} -200 500 0 0 {name=l4 author="2AM Logic (issue #166, sky130 PLL closed-loop VDD/VCTRL ripple-in-lock testbench)"}
