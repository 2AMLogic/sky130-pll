v {xschem version=3.4.7 file_version=1.2
* tb_clk_output.sch -- CLK output-pin levels / duty / edge testbench (issue #232)
*
* design/vco/vco_ring5.sym open-loop at a FIXED control voltage (VCTRL 0.865 V,
* the same near-250 MHz point sim/vco-clk-transition uses) driving
* design/clk-buf/clk_buf.sym, whose CLKOUT drives the provisional 1 pF
* CLK-to-GND characterization load CL of
* spec/decision-records/DR-008-clk-output-load-and-buffer-scope.md. The
* measured node is the buffered pin `clk`, not the ring-side net `vcoclk`.
* Open loop on purpose: spec rows 14/15 are statements about the pin, and the
* loaded closed-loop view is sim/pll-lock{,-1mhz,-25mhz} (same load).
*
* Startup kick: same `.ic` + `uic` convention as sim/vco/testbench (see
* tb.json `measure.ic`); a noiseless ring sits on its midrail equilibrium.
*
* Provenance: written fresh from sim/vco/testbench/tb_vco.sch's open-loop
* shape (label-based wiring, no drawn wires); the buffer and load are new.
}
G {}
V {}
S {}
E {}
C {design/vco/vco_ring5.sym} 0 0 0 0 {name=XXVCO}
C {devices/lab_pin.sym} 0 -80 0 0 {name=p1 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 0 80 0 0 {name=p2 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 0 0 0 {name=p3 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} 130 0 0 0 {name=p4 sig_type=std_logic lab=VCOCLK}
C {design/clk-buf/clk_buf.sym} 400 0 0 0 {name=XXBUF}
C {devices/lab_pin.sym} 400 -80 0 0 {name=p5 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 400 80 0 0 {name=p6 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 270 0 0 0 {name=p7 sig_type=std_logic lab=VCOCLK}
C {devices/lab_pin.sym} 530 0 0 0 {name=p8 sig_type=std_logic lab=CLK}
C {devices/capa.sym} 650 0 0 0 {name=CL m=1 value=1p footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} 650 -30 0 0 {name=p9 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 650 30 0 0 {name=p10 sig_type=std_logic lab=GND}
C {devices/vsource.sym} 900 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/lab_pin.sym} 900 -30 0 0 {name=p11 sig_type=std_logic lab=VDD}
C {devices/gnd.sym} 900 30 0 0 {name=l1 lab=GND}
C {devices/vsource.sym} 1100 0 0 0 {name=V2 value=0.865 savecurrent=false}
C {devices/lab_pin.sym} 1100 -30 0 0 {name=p12 sig_type=std_logic lab=VCTRL}
C {devices/gnd.sym} 1100 30 0 0 {name=l2 lab=GND}
C {devices/code.sym} 1300 300 0 0 {name=MODELS
only_toplevel=true
format="tcleval( @value )"
value="
** sky130 PDK model include (tt corner) -- patched per-point by sim/harness
.lib $::SKYWATER_MODELS/sky130.lib.spice tt
"
spice_ignore=false}
C {devices/title.sym} -200 500 0 0 {name=l3 author="2AM Logic (issue #232, sky130 PLL CLK output levels / duty)"}
