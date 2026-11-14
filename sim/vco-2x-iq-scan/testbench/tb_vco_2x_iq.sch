v {xschem version=3.4.7 file_version=1.2
* tb_vco_2x_iq.sch -- VCO + I/Q divide-by-2 PVT bench (issue #422; extends the
* issue #387 bench sim/vco-2x-duty/testbench/tb_vco_2x.sch)
*
* design/vco/vco_ring5.sym (the 2x VCO, net CLK2X) drives design/divider-iq/
* divider_iq.sym (the DR-010 I/Q divide-by-2, transistor level). CLK and CLK90
* each carry a 10 fF load capacitor to GND -- an assumed stand-in for the
* (unratified) consumer + output-buffer load, stated here and in tb.json.
* The harness sweeps VCTRL (source V2) inside one ngspice invocation per PVT
* point and measures CLK frequency/duty, CLK90 duty and the CLK->CLK90 offset
* from the simulated waveforms (sim/harness/measure.py `quadrature` block).
*
* RESETB is a behavioural source (B1 in the MODELS code block) tracking the point's own supply (V1 is
* patched per PVT point; a fixed 1.8 V reset-high would be wrong at 1.62/1.98 V):
* low for 60 ns, then a 1 ns ramp to VDD, so the divider starts from the
* reset-defined state with the VCO already oscillating (VCO is kicked with
* `.ic` + uic, as in tb_vco_2x.sch).
*
* Provenance: written fresh for this issue from tb_vco_2x.sch (issue #387 / #52).
}
G {}
V {}
S {}
E {}
C {design/vco/vco_ring5.sym} 0 0 0 0 {name=XXVCO}
C {devices/lab_pin.sym} 0 -80 0 0 {name=p1 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 0 80 0 0 {name=p2 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 0 0 0 {name=p3 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} 130 0 0 0 {name=p4 sig_type=std_logic lab=CLK2X}
C {design/divider-iq/divider_iq.sym} 400 0 0 0 {name=XDIVIQ}
C {devices/lab_pin.sym} 400 -100 0 0 {name=p7 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 400 100 0 0 {name=p8 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 270 -20 0 0 {name=p9 sig_type=std_logic lab=CLK2X}
C {devices/lab_pin.sym} 270 20 0 0 {name=p10 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 530 -20 0 0 {name=p11 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 530 20 0 0 {name=p12 sig_type=std_logic lab=CLK90}
C {devices/capa.sym} 700 -300 0 0 {name=CL1 m=1 value=10f footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} 700 -330 0 0 {name=p13 sig_type=std_logic lab=CLK}
C {devices/gnd.sym} 700 -270 0 0 {name=l4 lab=GND}
C {devices/capa.sym} 800 -300 0 0 {name=CL2 m=1 value=10f footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} 800 -330 0 0 {name=p14 sig_type=std_logic lab=CLK90}
C {devices/gnd.sym} 800 -270 0 0 {name=l5 lab=GND}
C {devices/vsource.sym} 600 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/lab_pin.sym} 600 -30 0 0 {name=p5 sig_type=std_logic lab=VDD}
C {devices/gnd.sym} 600 30 0 0 {name=l1 lab=GND}
C {devices/vsource.sym} 800 0 0 0 {name=V2 value=0.9 savecurrent=false}
C {devices/lab_pin.sym} 800 -30 0 0 {name=p6 sig_type=std_logic lab=VCTRL}
C {devices/gnd.sym} 800 30 0 0 {name=l2 lab=GND}
C {devices/code.sym} 1300 300 0 0 {name=MODELS
only_toplevel=true
format="tcleval( @value )"
value="
** sky130 PDK model include (tt corner) -- patched per-point by sim/harness
.lib $::SKYWATER_MODELS/sky130.lib.spice tt
** sky130_fd_sc_hd subckt deck -- design/divider-iq's cells need it
.include $::SKYWATER_STDCELLS/sky130_fd_sc_hd.spice
** RESETB: low 60 ns then 1 ns ramp to the point's own VDD (see header)
B1 RESETB GND V=v(vdd)*min(max((time-60n)/1n,0),1)
"
spice_ignore=false}
C {devices/title.sym} -200 500 0 0 {name=l3 author="2AM Logic (issue #422, sky130 2x-VCO + I/Q divide-by-2 PVT bench; from issue #387 bench)"}
