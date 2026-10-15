v {xschem version=3.4.7 file_version=1.2
* clk_buf.sch -- sky130 PLL CLK output buffer (issue #232)
*
* Non-inverting two-inverter chain between the VCO's CLK node (VCOCLK at the
* top level) and the exported CLK pin, so the output pin -- and whatever load
* it is characterised into -- is isolated from the ring-side net that also
* feeds the feedback divider. Stage 1 is deliberately small (W 1/2 um) to
* keep the added capacitance on the VCO node minimal; stage 2 (W 12/24 um)
* drives the provisional 1 pF CLK-to-GND characterisation load of
* spec/decision-records/DR-008-clk-output-load-and-buffer-scope.md. Sizing
* rationale and the pre-campaign single-corner probes are in
* design/clk-buf/DESIGN.md. Built on sky130 1.8 V core devices (DR-001) on the
* shared VDD/GND supply.
*
* This is a forward design (CLAUDE.md "Reverse-engineering-free"): a textbook
* inverter chain, not derived from any existing silicon or netlist.
*
* Pins: VDD, GND (supply), CLKIN (from the VCO), CLKOUT (buffered output).
}
G {}
V {}
S {}
E {}
C {sky130_fd_pr/pfet_01v8.sym} -300 -100 0 0 {name=MB1_P
W=2
L=0.15
nf=1
mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')"
nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=pfet_01v8
spiceprefix=X}
C {devices/lab_pin.sym} -280 -130 0 0 {name=p1 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -280 -70 0 0 {name=p2 sig_type=std_logic lab=N1}
C {devices/lab_pin.sym} -320 -100 0 0 {name=p3 sig_type=std_logic lab=CLKIN}
C {devices/lab_pin.sym} -280 -100 0 0 {name=p4 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -300 100 0 0 {name=MB1_N
W=1
L=0.15
nf=1
mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')"
nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=nfet_01v8
spiceprefix=X}
C {devices/lab_pin.sym} -280 70 0 0 {name=p5 sig_type=std_logic lab=N1}
C {devices/lab_pin.sym} -280 130 0 0 {name=p6 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -320 100 0 0 {name=p7 sig_type=std_logic lab=CLKIN}
C {devices/lab_pin.sym} -280 100 0 0 {name=p8 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 300 -100 0 0 {name=MB2_P
W=24
L=0.15
nf=1
mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')"
nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=pfet_01v8
spiceprefix=X}
C {devices/lab_pin.sym} 320 -130 0 0 {name=p9 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 320 -70 0 0 {name=p10 sig_type=std_logic lab=CLKOUT}
C {devices/lab_pin.sym} 280 -100 0 0 {name=p11 sig_type=std_logic lab=N1}
C {devices/lab_pin.sym} 320 -100 0 0 {name=p12 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 300 100 0 0 {name=MB2_N
W=12
L=0.15
nf=1
mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')"
nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=nfet_01v8
spiceprefix=X}
C {devices/lab_pin.sym} 320 70 0 0 {name=p13 sig_type=std_logic lab=CLKOUT}
C {devices/lab_pin.sym} 320 130 0 0 {name=p14 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 280 100 0 0 {name=p15 sig_type=std_logic lab=N1}
C {devices/lab_pin.sym} 320 100 0 0 {name=p16 sig_type=std_logic lab=GND}
C {devices/iopin.sym} -700 -300 0 0 {name=p90 lab=VDD}
C {devices/iopin.sym} -700 -200 0 0 {name=p91 lab=GND}
C {devices/ipin.sym} -700 -100 0 0 {name=p92 lab=CLKIN}
C {devices/opin.sym} 700 -100 0 0 {name=p93 lab=CLKOUT}
C {devices/title.sym} -700 500 0 0 {name=l1 author="2AM Logic (issue #232, sky130 PLL CLK output buffer)"}
