v {xschem version=3.4.7 file_version=1.2
* divider_iq.sch -- sky130 I/Q divide-by-2 cell (issue #422; DR-010 topology, Proposed)
*
* Two flip-flops on the 2x clock CLK2X, reset-defined start (RESETB async,
* active low, forces both outputs to 0):
*   XFI  (dfrtp_2, rising edge)  : D = ~CLK90, Q = CLK
*   XFQ  (dfrtn_1, falling edge) : D =  CLK,   Q = CLK90
*   XFB  (inv_2)                 : NQQ = ~CLK90
* CLK90 lags CLK by D*T2 (D = CLK2X high fraction) plus the clk->Q
* difference of the two flops, i.e. 180*D degrees of the output period
* plus 180*delta/T2 (docs/phase-output-proposal.md section 10; closed form
* in sim/phase-quadrature-model/README.md). This cell exists so that
* offset is *measured* on a transistor-level netlist, not derived.
*
* Cells are sky130_fd_sc_hd (1.8 V core, DR-001). dfrtn_1 is the only
* falling-edge reset flop the library offers in this family, so the two flops
* are not drive-matched; any resulting skew is part of what is measured.
* No output buffers: the CLK/CLK90 buffers are out of scope here.
* Provenance: written fresh for this issue; wiring convention follows
* design/divider/divider_intN.sch (label-based, no drawn wires).
}
G {}
K {type=subcircuit
format="X@name @pinlist @symname"
template="name=x1"
}
V {}
S {}
E {}
C {devices/iopin.sym} -300 -300 0 0 {name=p1 lab=VDD}
C {devices/iopin.sym} -300 -260 0 0 {name=p2 lab=GND}
C {devices/ipin.sym} -300 -220 0 0 {name=p3 lab=CLK2X}
C {devices/ipin.sym} -300 -180 0 0 {name=p4 lab=RESETB}
C {devices/opin.sym} -300 -140 0 0 {name=p5 lab=CLK}
C {devices/opin.sym} -300 -100 0 0 {name=p6 lab=CLK90}
C {sky130_stdcells/dfrtp_2.sym} 200 -400 0 0 {name=XFI VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 110 -420 0 0 {name=p7 sig_type=std_logic lab=CLK2X}
C {devices/lab_pin.sym} 110 -400 0 0 {name=p8 sig_type=std_logic lab=NQQ}
C {devices/lab_pin.sym} 110 -380 0 0 {name=p9 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 290 -420 0 0 {name=p10 sig_type=std_logic lab=CLK}
C {sky130_stdcells/dfrtn_1.sym} 600 -400 0 0 {name=XFQ VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 510 -420 0 0 {name=p11 sig_type=std_logic lab=CLK2X}
C {devices/lab_pin.sym} 510 -400 0 0 {name=p12 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 510 -380 0 0 {name=p13 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 690 -420 0 0 {name=p14 sig_type=std_logic lab=CLK90}
C {sky130_stdcells/inv_2.sym} 400 -200 0 0 {name=XFB VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 360 -200 0 0 {name=p15 sig_type=std_logic lab=CLK90}
C {devices/lab_pin.sym} 440 -200 0 0 {name=p16 sig_type=std_logic lab=NQQ}
