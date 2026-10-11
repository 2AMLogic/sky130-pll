v {xschem version=3.4.7 file_version=1.2
* tb_pfd_cp.sch -- standalone PFD + charge-pump characterization testbench (issue #250, part of #247)
*
* Instantiates the UNCHANGED design/pfd-cp/pfd_cp.sym through its actual
* ports VDD GND REF DIV CP. Nothing inside the block is forced, probed by a
* source, or edited: the block's own bias network, delay chains, latches and
* mirrors all run. There is no VCO, loop filter or divider in the path.
*
*   V1      supply (value patched per PVT point by sim/harness)
*   VREF    REF stimulus -- a pulse source; the harness `alter`s it per sweep coordinate
*   VDIV    DIV stimulus -- same, offset by the swept phase offset
*   VCLAMP  ideal voltage clamp from CP to ground, holding CP at the swept
*           VCTRL. Its positive terminal is CP, so ngspice's i(VCLAMP) is
*           positive when the pump delivers charge INTO CP (UP) and
*           negative for DN.
*
* The values written below are nominal placeholders. The 10 MHz / 50 % duty /
* 100 ps edge / 100 ns first-edge stimulus, the VCTRL and phase-offset grids
* and the integration windows are owned by sim/pfd-cp/testbench/tb.json's
* `cp` block, which the harness injects as a .control section; the schematic
* carries no .tran, .op or sweep card.
*
* Provenance: schematic-capture convention (label-based wiring) follows
* sim/vco/testbench/tb_vco.sch; written fresh for this issue.
}
G {}
V {}
S {}
E {}
C {design/pfd-cp/pfd_cp.sym} 0 0 0 0 {name=x1}
C {devices/lab_pin.sym} 0 -120 0 0 {name=p1 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 0 120 0 0 {name=p2 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 -40 0 0 {name=p3 sig_type=std_logic lab=REF}
C {devices/lab_pin.sym} -130 40 0 0 {name=p4 sig_type=std_logic lab=DIV}
C {devices/lab_pin.sym} 130 0 0 0 {name=p5 sig_type=std_logic lab=CP}
C {devices/vsource.sym} 600 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/lab_pin.sym} 600 -30 0 0 {name=p6 sig_type=std_logic lab=VDD}
C {devices/gnd.sym} 600 30 0 0 {name=l1 lab=GND}
C {devices/vsource.sym} 800 0 0 0 {name=VREF value="pulse(0 1.8 100n 100p 100p 50n 100n)" savecurrent=false}
C {devices/lab_pin.sym} 800 -30 0 0 {name=p7 sig_type=std_logic lab=REF}
C {devices/gnd.sym} 800 30 0 0 {name=l2 lab=GND}
C {devices/vsource.sym} 1000 0 0 0 {name=VDIV value="pulse(0 1.8 100n 100p 100p 50n 100n)" savecurrent=false}
C {devices/lab_pin.sym} 1000 -30 0 0 {name=p8 sig_type=std_logic lab=DIV}
C {devices/gnd.sym} 1000 30 0 0 {name=l3 lab=GND}
C {devices/vsource.sym} 1200 0 0 0 {name=VCLAMP value=0.9 savecurrent=true}
C {devices/lab_pin.sym} 1200 -30 0 0 {name=p9 sig_type=std_logic lab=CP}
C {devices/gnd.sym} 1200 30 0 0 {name=l4 lab=GND}
C {devices/code.sym} 1300 300 0 0 {name=MODELS
only_toplevel=true
format="tcleval( @value )"
value="
** sky130 PDK model include (tt corner) -- patched per-point by sim/harness
.lib $::SKYWATER_MODELS/sky130.lib.spice tt
"
spice_ignore=false}
C {devices/title.sym} -200 500 0 0 {name=l5 author="2AM Logic (issue #250, sky130 PFD/charge-pump campaign)"}
