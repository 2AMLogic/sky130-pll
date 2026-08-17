v {xschem version=3.4.7 file_version=1.2
* vco_ring5.sch -- sky130 PLL ring-oscillator VCO core (issue #24)
*
* 5-stage current-starved CMOS inverter ring oscillator, built on sky130's
* 1.8 V core devices (nfet_01v8 / pfet_01v8) per the ratified supply flavor
* (DR-001, spec/target-spec.md row 0). Odd stage count (5) closes the loop
* with net inversion, so the ring free-runs. Each stage's tail current is
* set by a shared control voltage VCTRL (NMOS current sink) mirrored to a
* PMOS current-source bias VBP by the diode-connected replica branch
* (MBP0/MBN0). A 2-stage output buffer (MBUFA_*/MBUFB_*) taps RING0,
* isolates the ring from CLK's load, and restores full-swing/duty cycle.
*
* Topology choice, stage count, sizing rationale, and the Kvco/tuning-range
* design target are documented in design/vco/DESIGN.md (not verified by
* simulation -- that is a later issue's testbench, per #24's scope).
*
* This is a forward design (CLAUDE.md "Reverse-engineering-free"): a
* textbook current-starved ring-VCO topology, not derived from any existing
* silicon or netlist.
*
* Pins: VDD, GND (supply), VCTRL (analog control voltage, input),
* CLK (oscillator output, buffered).
}
G {}
V {}
S {}
E {}
C {sky130_fd_pr/pfet_01v8.sym} -800 -300 0 0 {name=MSP0
W=4
L=0.5
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
C {devices/lab_pin.sym} -780 -330 0 0 {name=p1 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -780 -270 0 0 {name=p2 sig_type=std_logic lab=SP0}
C {devices/lab_pin.sym} -820 -300 0 0 {name=p3 sig_type=std_logic lab=VBP}
C {devices/lab_pin.sym} -780 -300 0 0 {name=p4 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} -800 -100 0 0 {name=MP0
W=4
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
C {devices/lab_pin.sym} -780 -130 0 0 {name=p5 sig_type=std_logic lab=SP0}
C {devices/lab_pin.sym} -780 -70 0 0 {name=p6 sig_type=std_logic lab=RING0}
C {devices/lab_pin.sym} -820 -100 0 0 {name=p7 sig_type=std_logic lab=RING4}
C {devices/lab_pin.sym} -780 -100 0 0 {name=p8 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -800 100 0 0 {name=MN0
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
model=nfet_01v8
spiceprefix=X}
C {devices/lab_pin.sym} -780 70 0 0 {name=p9 sig_type=std_logic lab=RING0}
C {devices/lab_pin.sym} -780 130 0 0 {name=p10 sig_type=std_logic lab=SN0}
C {devices/lab_pin.sym} -820 100 0 0 {name=p11 sig_type=std_logic lab=RING4}
C {devices/lab_pin.sym} -780 100 0 0 {name=p12 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} -800 300 0 0 {name=MSN0
W=2
L=0.5
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
C {devices/lab_pin.sym} -780 270 0 0 {name=p13 sig_type=std_logic lab=SN0}
C {devices/lab_pin.sym} -780 330 0 0 {name=p14 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -820 300 0 0 {name=p15 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} -780 300 0 0 {name=p16 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -300 -300 0 0 {name=MSP1
W=4
L=0.5
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
C {devices/lab_pin.sym} -280 -330 0 0 {name=p17 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -280 -270 0 0 {name=p18 sig_type=std_logic lab=SP1}
C {devices/lab_pin.sym} -320 -300 0 0 {name=p19 sig_type=std_logic lab=VBP}
C {devices/lab_pin.sym} -280 -300 0 0 {name=p20 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} -300 -100 0 0 {name=MP1
W=4
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
C {devices/lab_pin.sym} -280 -130 0 0 {name=p21 sig_type=std_logic lab=SP1}
C {devices/lab_pin.sym} -280 -70 0 0 {name=p22 sig_type=std_logic lab=RING1}
C {devices/lab_pin.sym} -320 -100 0 0 {name=p23 sig_type=std_logic lab=RING0}
C {devices/lab_pin.sym} -280 -100 0 0 {name=p24 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -300 100 0 0 {name=MN1
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
model=nfet_01v8
spiceprefix=X}
C {devices/lab_pin.sym} -280 70 0 0 {name=p25 sig_type=std_logic lab=RING1}
C {devices/lab_pin.sym} -280 130 0 0 {name=p26 sig_type=std_logic lab=SN1}
C {devices/lab_pin.sym} -320 100 0 0 {name=p27 sig_type=std_logic lab=RING0}
C {devices/lab_pin.sym} -280 100 0 0 {name=p28 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} -300 300 0 0 {name=MSN1
W=2
L=0.5
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
C {devices/lab_pin.sym} -280 270 0 0 {name=p29 sig_type=std_logic lab=SN1}
C {devices/lab_pin.sym} -280 330 0 0 {name=p30 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -320 300 0 0 {name=p31 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} -280 300 0 0 {name=p32 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 200 -300 0 0 {name=MSP2
W=4
L=0.5
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
C {devices/lab_pin.sym} 220 -330 0 0 {name=p33 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 220 -270 0 0 {name=p34 sig_type=std_logic lab=SP2}
C {devices/lab_pin.sym} 180 -300 0 0 {name=p35 sig_type=std_logic lab=VBP}
C {devices/lab_pin.sym} 220 -300 0 0 {name=p36 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} 200 -100 0 0 {name=MP2
W=4
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
C {devices/lab_pin.sym} 220 -130 0 0 {name=p37 sig_type=std_logic lab=SP2}
C {devices/lab_pin.sym} 220 -70 0 0 {name=p38 sig_type=std_logic lab=RING2}
C {devices/lab_pin.sym} 180 -100 0 0 {name=p39 sig_type=std_logic lab=RING1}
C {devices/lab_pin.sym} 220 -100 0 0 {name=p40 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 200 100 0 0 {name=MN2
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
model=nfet_01v8
spiceprefix=X}
C {devices/lab_pin.sym} 220 70 0 0 {name=p41 sig_type=std_logic lab=RING2}
C {devices/lab_pin.sym} 220 130 0 0 {name=p42 sig_type=std_logic lab=SN2}
C {devices/lab_pin.sym} 180 100 0 0 {name=p43 sig_type=std_logic lab=RING1}
C {devices/lab_pin.sym} 220 100 0 0 {name=p44 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 200 300 0 0 {name=MSN2
W=2
L=0.5
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
C {devices/lab_pin.sym} 220 270 0 0 {name=p45 sig_type=std_logic lab=SN2}
C {devices/lab_pin.sym} 220 330 0 0 {name=p46 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 180 300 0 0 {name=p47 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} 220 300 0 0 {name=p48 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 700 -300 0 0 {name=MSP3
W=4
L=0.5
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
C {devices/lab_pin.sym} 720 -330 0 0 {name=p49 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 720 -270 0 0 {name=p50 sig_type=std_logic lab=SP3}
C {devices/lab_pin.sym} 680 -300 0 0 {name=p51 sig_type=std_logic lab=VBP}
C {devices/lab_pin.sym} 720 -300 0 0 {name=p52 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} 700 -100 0 0 {name=MP3
W=4
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
C {devices/lab_pin.sym} 720 -130 0 0 {name=p53 sig_type=std_logic lab=SP3}
C {devices/lab_pin.sym} 720 -70 0 0 {name=p54 sig_type=std_logic lab=RING3}
C {devices/lab_pin.sym} 680 -100 0 0 {name=p55 sig_type=std_logic lab=RING2}
C {devices/lab_pin.sym} 720 -100 0 0 {name=p56 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 700 100 0 0 {name=MN3
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
model=nfet_01v8
spiceprefix=X}
C {devices/lab_pin.sym} 720 70 0 0 {name=p57 sig_type=std_logic lab=RING3}
C {devices/lab_pin.sym} 720 130 0 0 {name=p58 sig_type=std_logic lab=SN3}
C {devices/lab_pin.sym} 680 100 0 0 {name=p59 sig_type=std_logic lab=RING2}
C {devices/lab_pin.sym} 720 100 0 0 {name=p60 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 700 300 0 0 {name=MSN3
W=2
L=0.5
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
C {devices/lab_pin.sym} 720 270 0 0 {name=p61 sig_type=std_logic lab=SN3}
C {devices/lab_pin.sym} 720 330 0 0 {name=p62 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 680 300 0 0 {name=p63 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} 720 300 0 0 {name=p64 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 1200 -300 0 0 {name=MSP4
W=4
L=0.5
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
C {devices/lab_pin.sym} 1220 -330 0 0 {name=p65 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 1220 -270 0 0 {name=p66 sig_type=std_logic lab=SP4}
C {devices/lab_pin.sym} 1180 -300 0 0 {name=p67 sig_type=std_logic lab=VBP}
C {devices/lab_pin.sym} 1220 -300 0 0 {name=p68 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} 1200 -100 0 0 {name=MP4
W=4
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
C {devices/lab_pin.sym} 1220 -130 0 0 {name=p69 sig_type=std_logic lab=SP4}
C {devices/lab_pin.sym} 1220 -70 0 0 {name=p70 sig_type=std_logic lab=RING4}
C {devices/lab_pin.sym} 1180 -100 0 0 {name=p71 sig_type=std_logic lab=RING3}
C {devices/lab_pin.sym} 1220 -100 0 0 {name=p72 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 1200 100 0 0 {name=MN4
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
model=nfet_01v8
spiceprefix=X}
C {devices/lab_pin.sym} 1220 70 0 0 {name=p73 sig_type=std_logic lab=RING4}
C {devices/lab_pin.sym} 1220 130 0 0 {name=p74 sig_type=std_logic lab=SN4}
C {devices/lab_pin.sym} 1180 100 0 0 {name=p75 sig_type=std_logic lab=RING3}
C {devices/lab_pin.sym} 1220 100 0 0 {name=p76 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 1200 300 0 0 {name=MSN4
W=2
L=0.5
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
C {devices/lab_pin.sym} 1220 270 0 0 {name=p77 sig_type=std_logic lab=SN4}
C {devices/lab_pin.sym} 1220 330 0 0 {name=p78 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1180 300 0 0 {name=p79 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} 1220 300 0 0 {name=p80 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -2400 -300 0 0 {name=MBP0
W=4
L=0.5
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
C {devices/lab_pin.sym} -2380 -330 0 0 {name=p81 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -2380 -270 0 0 {name=p82 sig_type=std_logic lab=VBP}
C {devices/lab_pin.sym} -2420 -300 0 0 {name=p83 sig_type=std_logic lab=VBP}
C {devices/lab_pin.sym} -2380 -300 0 0 {name=p84 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -2400 -100 0 0 {name=MBN0
W=2
L=0.5
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
C {devices/lab_pin.sym} -2380 -130 0 0 {name=p85 sig_type=std_logic lab=VBP}
C {devices/lab_pin.sym} -2380 -70 0 0 {name=p86 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -2420 -100 0 0 {name=p87 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} -2380 -100 0 0 {name=p88 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 1700 -100 0 0 {name=MBUFA_P
W=4
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
C {devices/lab_pin.sym} 1720 -130 0 0 {name=p89 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 1720 -70 0 0 {name=p90 sig_type=std_logic lab=BUF1}
C {devices/lab_pin.sym} 1680 -100 0 0 {name=p91 sig_type=std_logic lab=RING0}
C {devices/lab_pin.sym} 1720 -100 0 0 {name=p92 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 1700 100 0 0 {name=MBUFA_N
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
model=nfet_01v8
spiceprefix=X}
C {devices/lab_pin.sym} 1720 70 0 0 {name=p93 sig_type=std_logic lab=BUF1}
C {devices/lab_pin.sym} 1720 130 0 0 {name=p94 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1680 100 0 0 {name=p95 sig_type=std_logic lab=RING0}
C {devices/lab_pin.sym} 1720 100 0 0 {name=p96 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 2200 -100 0 0 {name=MBUFB_P
W=16
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
C {devices/lab_pin.sym} 2220 -130 0 0 {name=p97 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 2220 -70 0 0 {name=p98 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 2180 -100 0 0 {name=p99 sig_type=std_logic lab=BUF1}
C {devices/lab_pin.sym} 2220 -100 0 0 {name=p100 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 2200 100 0 0 {name=MBUFB_N
W=8
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
C {devices/lab_pin.sym} 2220 70 0 0 {name=p101 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 2220 130 0 0 {name=p102 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 2180 100 0 0 {name=p103 sig_type=std_logic lab=BUF1}
C {devices/lab_pin.sym} 2220 100 0 0 {name=p104 sig_type=std_logic lab=GND}
C {devices/iopin.sym} -2800 -500 0 0 {name=p1 lab=VDD}
C {devices/iopin.sym} -2800 -400 0 0 {name=p2 lab=GND}
C {devices/ipin.sym} -2800 -300 0 0 {name=p3 lab=VCTRL}
C {devices/opin.sym} 2600 -300 0 0 {name=p4 lab=CLK}
C {devices/title.sym} -800 -900 0 0 {name=l1 author="2AM Logic (issue #24, sky130 PLL VCO core)"}
