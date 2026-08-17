v {xschem version=3.4.7 file_version=1.2
* loop_filter.sch -- sky130 PLL passive loop filter (issue #26)
*
* 3rd-order passive RC charge-pump loop filter, built on sky130's dedicated
* precision-poly-resistor and MiM-cap primitives (sky130_fd_pr__res_xhigh_po,
* sky130_fd_pr__cap_mim_m3_1). No active devices -- this block is entirely
* passive, per the ratified 1.8 V core supply flavor (DR-001,
* spec/target-spec.md row 0) it shares with its sibling blocks, though this
* block itself draws no supply current.
*
* Topology: charge-pump current is injected at CP. R1+C1 (series, CP->Z1->GND)
* form the loop's compensation zero. C2 (CP->GND, shunt) adds the filter's
* first non-zero pole for reference-spur attenuation, standard for a
* charge-pump PLL's "2nd order" filter section. R3+C3 (CP->VCTRL->GND) add a
* third, more lightly loaded pole that isolates the voltage the VCO actually
* sees (VCTRL) from the charge-pump node's own switching transients, without
* disturbing the DC operating point (the VCO's gate-only VCTRL load draws no
* static current through R3).
*
* Component sizing, the loop-bandwidth/phase-margin/Vctrl-headroom design
* targets this sizing is built toward, and the Icp/Kvco design-point
* assumptions this first-pass sizing coordinates against (the PFD/charge
* pump sub-issue, #25, had not landed its own Icp value at authoring time)
* are documented in design/loop-filter/DESIGN.md. Not verified by
* simulation -- that is a later issue's testbench, per #26's own scope.
*
* This is a forward design (CLAUDE.md "Reverse-engineering-free"): a
* textbook 3rd-order passive charge-pump PLL loop filter topology, not
* derived from any existing silicon or netlist.
*
* Pins: CP (charge-pump current injection, input), GND (reference return),
* VCTRL (filtered control voltage, output to the VCO).
}
G {}
V {}
S {}
E {}
C {sky130_fd_pr/res_xhigh_po.sym} -400 -100 0 0 {name=R1
W=1
L=10.3
mult=1
model=res_xhigh_po
spiceprefix=X}
C {devices/lab_pin.sym} -400 -70 0 0 {name=p1 sig_type=std_logic lab=Z1}
C {devices/lab_pin.sym} -400 -130 0 0 {name=p2 sig_type=std_logic lab=CP}
C {devices/lab_pin.sym} -420 -100 0 0 {name=p3 sig_type=std_logic lab=GND}
C {sky130_fd_pr/cap_mim_m3_1.sym} -400 100 0 0 {name=C1
model=cap_mim_m3_1
W=163
L=163
MF=1
spiceprefix=X}
C {devices/lab_pin.sym} -400 70 0 0 {name=p4 sig_type=std_logic lab=Z1}
C {devices/lab_pin.sym} -400 130 0 0 {name=p5 sig_type=std_logic lab=GND}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 0 0 0 {name=C2
model=cap_mim_m3_1
W=35
L=35
MF=1
spiceprefix=X}
C {devices/lab_pin.sym} 0 -30 0 0 {name=p6 sig_type=std_logic lab=CP}
C {devices/lab_pin.sym} 0 30 0 0 {name=p7 sig_type=std_logic lab=GND}
C {sky130_fd_pr/res_xhigh_po.sym} 400 -100 0 0 {name=R3
W=1
L=5
mult=1
model=res_xhigh_po
spiceprefix=X}
C {devices/lab_pin.sym} 400 -70 0 0 {name=p8 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} 400 -130 0 0 {name=p9 sig_type=std_logic lab=CP}
C {devices/lab_pin.sym} 380 -100 0 0 {name=p10 sig_type=std_logic lab=GND}
C {sky130_fd_pr/cap_mim_m3_1.sym} 400 100 0 0 {name=C3
model=cap_mim_m3_1
W=42
L=42
MF=1
spiceprefix=X}
C {devices/lab_pin.sym} 400 70 0 0 {name=p11 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} 400 130 0 0 {name=p12 sig_type=std_logic lab=GND}
C {devices/ipin.sym} -700 -100 0 0 {name=p13 lab=CP}
C {devices/iopin.sym} -700 300 0 0 {name=p14 lab=GND}
C {devices/opin.sym} 700 -100 0 0 {name=p15 lab=VCTRL}
C {devices/title.sym} -400 -900 0 0 {name=l1 author="2AM Logic (issue #26, sky130 PLL loop filter)"}
