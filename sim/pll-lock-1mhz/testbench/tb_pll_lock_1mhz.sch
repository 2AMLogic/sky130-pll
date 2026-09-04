v {xschem version=3.4.7 file_version=1.2
* tb_pll_lock_1mhz.sch -- cold-start lock-capable closed-loop PLL testbench,
* reference-input low band edge (issue #55)
*
* Sibling of sim/pll-lock/testbench/tb_pll_lock.sch (issue #52), itself a
* sibling of sim/pll/testbench/tb_pll.sch (issue #23): same DUT
* (design/top/top.sym, the four-block closed-loop PLL), same supply and
* reset stimulus and the same lock-capable manifest-injected `.control`
* analysis convention (no `.tran`/`.print` card here -- see
* tb_pll_lock.sch's own header for why). The only structural differences
* from tb_pll_lock.sch are the reference stimulus (`V2`, here 1 MHz instead
* of 10 MHz) and the `NSEL[5:0]` strap (here N=64 instead of N=25) -- see
* "N choice" below.
*
* Why this sibling exists instead of a manifest-level stimulus-axis
* generalization of sim/harness/corners.py: spec/target-spec.md row 3
* (reference input) states a 1-25 MHz DRAFT range, but every existing
* sim/harness manifest sweeps only (process corner, temperature, supply) --
* reference frequency is baked into the testbench schematic's `V2` source,
* not a harness-generic axis. Generalizing corners.py/runner.py to sweep a
* stimulus parameter would be strictly more invasive than a second sibling
* testbench (the same trade-off issue #55 itself lays out), so this issue
* follows the same "sibling testbench" pattern tb_pll_lock.sch already used
* relative to tb_pll.sch rather than inventing a new harness axis.
*
* N choice (band edge: Fref = 1 MHz):
*   design/divider/DESIGN.md: NSEL[5:0] carries N-1 in plain binary, 6 bits
*   -> N = 1..64 representable, N = 4-64 is spec row 4's DRAFT range. The
*   maximum representable N (64) is chosen here, NOT to land inside the
*   VCO's characterized tuning range, but because it is the *closest
*   achievable* target given the divider's own N <= 64 ceiling:
*     N * Fref = 64 * 1 MHz = 64 MHz
*   sim/vco/records/20260819-131741-fe0e6df.md's characterized VCO tuning
*   range is ~145.1 MHz (VCTRL=0.8V) to ~1.034 GHz (VCTRL=1.6V) -- 64 MHz is
*   BELOW that measured floor, and VCTRL < 0.8V is not characterized (per
*   CLAUDE.md/issue #55, this testbench does not extrapolate past the
*   measured VCO range to claim otherwise). This is itself the evidence
*   spec row 3's low band edge needs recorded: given the current divider's
*   N <= 64 ceiling and the VCO's measured floor, a 1 MHz reference cannot
*   be strapped to land the closed-loop target inside the characterized VCO
*   range at all -- see this testbench's own sim/pll-lock-1mhz/records/
*   entry for the resulting measured behavior. NSEL[5:0] = N-1 = 63 =
*   binary 111111 -> all six NSEL bits strapped to VDD below.
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
C {devices/lab_pin.sym} -130 -60 0 0 {name=p6 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 -20 0 0 {name=p7 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 20 0 0 {name=p8 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 60 0 0 {name=p9 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 100 0 0 {name=p10 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 130 0 0 0 {name=p11 sig_type=std_logic lab=CLK}
C {devices/vsource.sym} 600 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/lab_pin.sym} 600 -30 0 0 {name=p12 sig_type=std_logic lab=VDD}
C {devices/gnd.sym} 600 30 0 0 {name=l1 lab=GND}
C {devices/vsource.sym} 800 0 0 0 {name=V2 value="pulse(0 1.8 0 1n 1n 498n 1000n)" savecurrent=false}
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
C {devices/title.sym} -200 500 0 0 {name=l4 author="2AM Logic (issue #55, sky130 PLL row-3 low band-edge lock testbench)"}
