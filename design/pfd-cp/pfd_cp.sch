v {xschem version=3.4.7 file_version=1.2
* pfd_cp.sch -- sky130 PLL tri-state phase-frequency detector + charge pump
* (issue #25)
*
* Tri-state (three-state) edge-triggered PFD: REF and DIV each drive an
* edge-pulse generator (inverter delay chain + AND2) that momentarily SETs
* a NOR-based SR latch (UP for REF, DN for DIV) on that input's rising
* edge -- functionally a positive-edge-triggered D flip-flop with D tied
* permanently to logic 1, built directly as an edge-triggered SR structure
* since a full master-slave D-latch datapath is unnecessary once D is
* constant. Both latches share a common asynchronous reset RST, generated
* as AND(UP, DN) run through a deliberately long-L (dead-zone-avoidance)
* delay element, so every reference cycle -- even at zero phase error --
* forces a minimum-width UP/DN pulse before reset fires, keeping the
* charge pump out of its nonlinear near-zero dead zone. Built entirely
* from sky130's 1.8 V core devices (nfet_01v8/pfet_01v8) at the bare
* transistor level -- a small digital sequential circuit, not a
* sky130_fd_sc_hd standard-cell instantiation (there is no PDK standard
* cell for a tri-state PFD; design/divider/DESIGN.md's std-cell precedent
* does not apply to this custom sequential topology) -- per the ratified
* 1.8 V core supply flavor (DR-001, spec/target-spec.md row 0).
*
* Charge pump: a single-stage (non-cascoded) PMOS current-source / NMOS
* current-sink pair, each with its own series switch transistor (MPSW
* gated by UPB=~UP, MNSW gated by DN) placed directly between the mirror
* device and the CP output node -- one mirror device plus one switch
* between rail and output, not a stacked cascode -- a deliberate headroom
* choice under the 1.8 V rail (see design/pfd-cp/DESIGN.md's headroom
* analysis). Bias generated from a single resistor-set reference current
* (RBIAS/MNBIAS) mirrored into a matched PMOS bias (MPBIAS/MNBIAS2) so a
* single IREF sets both the PMOS source and NMOS sink legs.
*
* Design rationale (topology alternatives considered, dead-zone
* mechanism, headroom analysis, Icp design point, and the explicit
* decision not to implement a current trim in this pass) is documented in
* design/pfd-cp/DESIGN.md -- a design target, not verified by simulation
* (no testbench exists for this block yet, per #25's own scope).
*
* This is a forward design (CLAUDE.md "Reverse-engineering-free"): a
* textbook tri-state PFD + three-state charge pump topology (Gardner,
* Best, Razavi), not derived from any existing silicon or netlist.
*
* Pins: VDD, GND (supply), REF (reference clock, input), DIV (divider
* feedback clock, input), CP (charge-pump current output -- drives
* design/loop-filter/loop_filter.sch's CP input net).
}
G {}
V {}
S {}
E {}
C {sky130_fd_pr/pfet_01v8.sym} -4000 -300 0 0 {name=REDLY1_P
W=2
L=0.3
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
C {devices/lab_pin.sym} -3980 -330 0 0 {name=p1 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -3980 -270 0 0 {name=p2 sig_type=std_logic lab=REFD1}
C {devices/lab_pin.sym} -4020 -300 0 0 {name=p3 sig_type=std_logic lab=REF}
C {devices/lab_pin.sym} -3980 -300 0 0 {name=p4 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -4000 100 0 0 {name=REDLY1_N
W=1
L=0.3
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
C {devices/lab_pin.sym} -3980 70 0 0 {name=p5 sig_type=std_logic lab=REFD1}
C {devices/lab_pin.sym} -3980 130 0 0 {name=p6 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -4020 100 0 0 {name=p7 sig_type=std_logic lab=REF}
C {devices/lab_pin.sym} -3980 100 0 0 {name=p8 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -3780 -300 0 0 {name=REDLY2_P
W=2
L=0.3
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
C {devices/lab_pin.sym} -3760 -330 0 0 {name=p9 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -3760 -270 0 0 {name=p10 sig_type=std_logic lab=REFD2}
C {devices/lab_pin.sym} -3800 -300 0 0 {name=p11 sig_type=std_logic lab=REFD1}
C {devices/lab_pin.sym} -3760 -300 0 0 {name=p12 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -3780 100 0 0 {name=REDLY2_N
W=1
L=0.3
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
C {devices/lab_pin.sym} -3760 70 0 0 {name=p13 sig_type=std_logic lab=REFD2}
C {devices/lab_pin.sym} -3760 130 0 0 {name=p14 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -3800 100 0 0 {name=p15 sig_type=std_logic lab=REFD1}
C {devices/lab_pin.sym} -3760 100 0 0 {name=p16 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -3560 -300 0 0 {name=REDLY3_P
W=2
L=0.3
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
C {devices/lab_pin.sym} -3540 -330 0 0 {name=p17 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -3540 -270 0 0 {name=p18 sig_type=std_logic lab=REFD}
C {devices/lab_pin.sym} -3580 -300 0 0 {name=p19 sig_type=std_logic lab=REFD2}
C {devices/lab_pin.sym} -3540 -300 0 0 {name=p20 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -3560 100 0 0 {name=REDLY3_N
W=1
L=0.3
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
C {devices/lab_pin.sym} -3540 70 0 0 {name=p21 sig_type=std_logic lab=REFD}
C {devices/lab_pin.sym} -3540 130 0 0 {name=p22 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -3580 100 0 0 {name=p23 sig_type=std_logic lab=REFD2}
C {devices/lab_pin.sym} -3540 100 0 0 {name=p24 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -3340 -300 0 0 {name=RUPNAND_P1
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
C {devices/lab_pin.sym} -3320 -330 0 0 {name=p25 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -3320 -270 0 0 {name=p26 sig_type=std_logic lab=RUP_NAND}
C {devices/lab_pin.sym} -3360 -300 0 0 {name=p27 sig_type=std_logic lab=REF}
C {devices/lab_pin.sym} -3320 -300 0 0 {name=p28 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} -3120 -300 0 0 {name=RUPNAND_P2
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
C {devices/lab_pin.sym} -3100 -330 0 0 {name=p29 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -3100 -270 0 0 {name=p30 sig_type=std_logic lab=RUP_NAND}
C {devices/lab_pin.sym} -3140 -300 0 0 {name=p31 sig_type=std_logic lab=REFD}
C {devices/lab_pin.sym} -3100 -300 0 0 {name=p32 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -2900 100 0 0 {name=RUPNAND_N1
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
C {devices/lab_pin.sym} -2880 70 0 0 {name=p33 sig_type=std_logic lab=RUP_NAND}
C {devices/lab_pin.sym} -2880 130 0 0 {name=p34 sig_type=std_logic lab=RUP_MID}
C {devices/lab_pin.sym} -2920 100 0 0 {name=p35 sig_type=std_logic lab=REF}
C {devices/lab_pin.sym} -2880 100 0 0 {name=p36 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} -2680 100 0 0 {name=RUPNAND_N2
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
C {devices/lab_pin.sym} -2660 70 0 0 {name=p37 sig_type=std_logic lab=RUP_MID}
C {devices/lab_pin.sym} -2660 130 0 0 {name=p38 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -2700 100 0 0 {name=p39 sig_type=std_logic lab=REFD}
C {devices/lab_pin.sym} -2660 100 0 0 {name=p40 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -2460 -300 0 0 {name=RUPINV_P
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
C {devices/lab_pin.sym} -2440 -330 0 0 {name=p41 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -2440 -270 0 0 {name=p42 sig_type=std_logic lab=SETU}
C {devices/lab_pin.sym} -2480 -300 0 0 {name=p43 sig_type=std_logic lab=RUP_NAND}
C {devices/lab_pin.sym} -2440 -300 0 0 {name=p44 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -2460 100 0 0 {name=RUPINV_N
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
C {devices/lab_pin.sym} -2440 70 0 0 {name=p45 sig_type=std_logic lab=SETU}
C {devices/lab_pin.sym} -2440 130 0 0 {name=p46 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -2480 100 0 0 {name=p47 sig_type=std_logic lab=RUP_NAND}
C {devices/lab_pin.sym} -2440 100 0 0 {name=p48 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -2240 -300 0 0 {name=DIDLY1_P
W=2
L=0.3
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
C {devices/lab_pin.sym} -2220 -330 0 0 {name=p49 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -2220 -270 0 0 {name=p50 sig_type=std_logic lab=DIVD1}
C {devices/lab_pin.sym} -2260 -300 0 0 {name=p51 sig_type=std_logic lab=DIV}
C {devices/lab_pin.sym} -2220 -300 0 0 {name=p52 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -2240 100 0 0 {name=DIDLY1_N
W=1
L=0.3
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
C {devices/lab_pin.sym} -2220 70 0 0 {name=p53 sig_type=std_logic lab=DIVD1}
C {devices/lab_pin.sym} -2220 130 0 0 {name=p54 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -2260 100 0 0 {name=p55 sig_type=std_logic lab=DIV}
C {devices/lab_pin.sym} -2220 100 0 0 {name=p56 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -2020 -300 0 0 {name=DIDLY2_P
W=2
L=0.3
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
C {devices/lab_pin.sym} -2000 -330 0 0 {name=p57 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -2000 -270 0 0 {name=p58 sig_type=std_logic lab=DIVD2}
C {devices/lab_pin.sym} -2040 -300 0 0 {name=p59 sig_type=std_logic lab=DIVD1}
C {devices/lab_pin.sym} -2000 -300 0 0 {name=p60 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -2020 100 0 0 {name=DIDLY2_N
W=1
L=0.3
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
C {devices/lab_pin.sym} -2000 70 0 0 {name=p61 sig_type=std_logic lab=DIVD2}
C {devices/lab_pin.sym} -2000 130 0 0 {name=p62 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -2040 100 0 0 {name=p63 sig_type=std_logic lab=DIVD1}
C {devices/lab_pin.sym} -2000 100 0 0 {name=p64 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -1800 -300 0 0 {name=DIDLY3_P
W=2
L=0.3
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
C {devices/lab_pin.sym} -1780 -330 0 0 {name=p65 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -1780 -270 0 0 {name=p66 sig_type=std_logic lab=DIVD}
C {devices/lab_pin.sym} -1820 -300 0 0 {name=p67 sig_type=std_logic lab=DIVD2}
C {devices/lab_pin.sym} -1780 -300 0 0 {name=p68 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -1800 100 0 0 {name=DIDLY3_N
W=1
L=0.3
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
C {devices/lab_pin.sym} -1780 70 0 0 {name=p69 sig_type=std_logic lab=DIVD}
C {devices/lab_pin.sym} -1780 130 0 0 {name=p70 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -1820 100 0 0 {name=p71 sig_type=std_logic lab=DIVD2}
C {devices/lab_pin.sym} -1780 100 0 0 {name=p72 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -1580 -300 0 0 {name=RDNNAND_P1
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
C {devices/lab_pin.sym} -1560 -330 0 0 {name=p73 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -1560 -270 0 0 {name=p74 sig_type=std_logic lab=RDN_NAND}
C {devices/lab_pin.sym} -1600 -300 0 0 {name=p75 sig_type=std_logic lab=DIV}
C {devices/lab_pin.sym} -1560 -300 0 0 {name=p76 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} -1360 -300 0 0 {name=RDNNAND_P2
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
C {devices/lab_pin.sym} -1340 -330 0 0 {name=p77 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -1340 -270 0 0 {name=p78 sig_type=std_logic lab=RDN_NAND}
C {devices/lab_pin.sym} -1380 -300 0 0 {name=p79 sig_type=std_logic lab=DIVD}
C {devices/lab_pin.sym} -1340 -300 0 0 {name=p80 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -1140 100 0 0 {name=RDNNAND_N1
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
C {devices/lab_pin.sym} -1120 70 0 0 {name=p81 sig_type=std_logic lab=RDN_NAND}
C {devices/lab_pin.sym} -1120 130 0 0 {name=p82 sig_type=std_logic lab=RDN_MID}
C {devices/lab_pin.sym} -1160 100 0 0 {name=p83 sig_type=std_logic lab=DIV}
C {devices/lab_pin.sym} -1120 100 0 0 {name=p84 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} -920 100 0 0 {name=RDNNAND_N2
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
C {devices/lab_pin.sym} -900 70 0 0 {name=p85 sig_type=std_logic lab=RDN_MID}
C {devices/lab_pin.sym} -900 130 0 0 {name=p86 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -940 100 0 0 {name=p87 sig_type=std_logic lab=DIVD}
C {devices/lab_pin.sym} -900 100 0 0 {name=p88 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -700 -300 0 0 {name=RDNINV_P
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
C {devices/lab_pin.sym} -680 -330 0 0 {name=p89 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -680 -270 0 0 {name=p90 sig_type=std_logic lab=SETD}
C {devices/lab_pin.sym} -720 -300 0 0 {name=p91 sig_type=std_logic lab=RDN_NAND}
C {devices/lab_pin.sym} -680 -300 0 0 {name=p92 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -700 100 0 0 {name=RDNINV_N
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
C {devices/lab_pin.sym} -680 70 0 0 {name=p93 sig_type=std_logic lab=SETD}
C {devices/lab_pin.sym} -680 130 0 0 {name=p94 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -720 100 0 0 {name=p95 sig_type=std_logic lab=RDN_NAND}
C {devices/lab_pin.sym} -680 100 0 0 {name=p96 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} -480 -300 0 0 {name=UPNORA_P1
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
C {devices/lab_pin.sym} -460 -330 0 0 {name=p97 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -460 -270 0 0 {name=p98 sig_type=std_logic lab=UPNORA_MID}
C {devices/lab_pin.sym} -500 -300 0 0 {name=p99 sig_type=std_logic lab=RST}
C {devices/lab_pin.sym} -460 -300 0 0 {name=p100 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} -260 -300 0 0 {name=UPNORA_P2
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
C {devices/lab_pin.sym} -240 -330 0 0 {name=p101 sig_type=std_logic lab=UPNORA_MID}
C {devices/lab_pin.sym} -240 -270 0 0 {name=p102 sig_type=std_logic lab=UP}
C {devices/lab_pin.sym} -280 -300 0 0 {name=p103 sig_type=std_logic lab=UPN}
C {devices/lab_pin.sym} -240 -300 0 0 {name=p104 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} -40 100 0 0 {name=UPNORA_N1
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
C {devices/lab_pin.sym} -20 70 0 0 {name=p105 sig_type=std_logic lab=UP}
C {devices/lab_pin.sym} -20 130 0 0 {name=p106 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -60 100 0 0 {name=p107 sig_type=std_logic lab=RST}
C {devices/lab_pin.sym} -20 100 0 0 {name=p108 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 180 100 0 0 {name=UPNORA_N2
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
C {devices/lab_pin.sym} 200 70 0 0 {name=p109 sig_type=std_logic lab=UP}
C {devices/lab_pin.sym} 200 130 0 0 {name=p110 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 160 100 0 0 {name=p111 sig_type=std_logic lab=UPN}
C {devices/lab_pin.sym} 200 100 0 0 {name=p112 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 400 -300 0 0 {name=UPNORB_P1
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
C {devices/lab_pin.sym} 420 -330 0 0 {name=p113 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 420 -270 0 0 {name=p114 sig_type=std_logic lab=UPNORB_MID}
C {devices/lab_pin.sym} 380 -300 0 0 {name=p115 sig_type=std_logic lab=SETU}
C {devices/lab_pin.sym} 420 -300 0 0 {name=p116 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} 620 -300 0 0 {name=UPNORB_P2
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
C {devices/lab_pin.sym} 640 -330 0 0 {name=p117 sig_type=std_logic lab=UPNORB_MID}
C {devices/lab_pin.sym} 640 -270 0 0 {name=p118 sig_type=std_logic lab=UPN}
C {devices/lab_pin.sym} 600 -300 0 0 {name=p119 sig_type=std_logic lab=UP}
C {devices/lab_pin.sym} 640 -300 0 0 {name=p120 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 840 100 0 0 {name=UPNORB_N1
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
C {devices/lab_pin.sym} 860 70 0 0 {name=p121 sig_type=std_logic lab=UPN}
C {devices/lab_pin.sym} 860 130 0 0 {name=p122 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 820 100 0 0 {name=p123 sig_type=std_logic lab=SETU}
C {devices/lab_pin.sym} 860 100 0 0 {name=p124 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 1060 100 0 0 {name=UPNORB_N2
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
C {devices/lab_pin.sym} 1080 70 0 0 {name=p125 sig_type=std_logic lab=UPN}
C {devices/lab_pin.sym} 1080 130 0 0 {name=p126 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1040 100 0 0 {name=p127 sig_type=std_logic lab=UP}
C {devices/lab_pin.sym} 1080 100 0 0 {name=p128 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 1280 -300 0 0 {name=DNNORA_P1
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
C {devices/lab_pin.sym} 1300 -330 0 0 {name=p129 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 1300 -270 0 0 {name=p130 sig_type=std_logic lab=DNNORA_MID}
C {devices/lab_pin.sym} 1260 -300 0 0 {name=p131 sig_type=std_logic lab=RST}
C {devices/lab_pin.sym} 1300 -300 0 0 {name=p132 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} 1500 -300 0 0 {name=DNNORA_P2
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
C {devices/lab_pin.sym} 1520 -330 0 0 {name=p133 sig_type=std_logic lab=DNNORA_MID}
C {devices/lab_pin.sym} 1520 -270 0 0 {name=p134 sig_type=std_logic lab=DN}
C {devices/lab_pin.sym} 1480 -300 0 0 {name=p135 sig_type=std_logic lab=DNN}
C {devices/lab_pin.sym} 1520 -300 0 0 {name=p136 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 1720 100 0 0 {name=DNNORA_N1
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
C {devices/lab_pin.sym} 1740 70 0 0 {name=p137 sig_type=std_logic lab=DN}
C {devices/lab_pin.sym} 1740 130 0 0 {name=p138 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1700 100 0 0 {name=p139 sig_type=std_logic lab=RST}
C {devices/lab_pin.sym} 1740 100 0 0 {name=p140 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 1940 100 0 0 {name=DNNORA_N2
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
C {devices/lab_pin.sym} 1960 70 0 0 {name=p141 sig_type=std_logic lab=DN}
C {devices/lab_pin.sym} 1960 130 0 0 {name=p142 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1920 100 0 0 {name=p143 sig_type=std_logic lab=DNN}
C {devices/lab_pin.sym} 1960 100 0 0 {name=p144 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 2160 -300 0 0 {name=DNNORB_P1
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
C {devices/lab_pin.sym} 2180 -330 0 0 {name=p145 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 2180 -270 0 0 {name=p146 sig_type=std_logic lab=DNNORB_MID}
C {devices/lab_pin.sym} 2140 -300 0 0 {name=p147 sig_type=std_logic lab=SETD}
C {devices/lab_pin.sym} 2180 -300 0 0 {name=p148 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} 2380 -300 0 0 {name=DNNORB_P2
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
C {devices/lab_pin.sym} 2400 -330 0 0 {name=p149 sig_type=std_logic lab=DNNORB_MID}
C {devices/lab_pin.sym} 2400 -270 0 0 {name=p150 sig_type=std_logic lab=DNN}
C {devices/lab_pin.sym} 2360 -300 0 0 {name=p151 sig_type=std_logic lab=DN}
C {devices/lab_pin.sym} 2400 -300 0 0 {name=p152 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 2600 100 0 0 {name=DNNORB_N1
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
C {devices/lab_pin.sym} 2620 70 0 0 {name=p153 sig_type=std_logic lab=DNN}
C {devices/lab_pin.sym} 2620 130 0 0 {name=p154 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 2580 100 0 0 {name=p155 sig_type=std_logic lab=SETD}
C {devices/lab_pin.sym} 2620 100 0 0 {name=p156 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 2820 100 0 0 {name=DNNORB_N2
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
C {devices/lab_pin.sym} 2840 70 0 0 {name=p157 sig_type=std_logic lab=DNN}
C {devices/lab_pin.sym} 2840 130 0 0 {name=p158 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 2800 100 0 0 {name=p159 sig_type=std_logic lab=DN}
C {devices/lab_pin.sym} 2840 100 0 0 {name=p160 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 3040 -300 0 0 {name=RSTGNAND_P1
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
C {devices/lab_pin.sym} 3060 -330 0 0 {name=p161 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 3060 -270 0 0 {name=p162 sig_type=std_logic lab=RSTG_NAND}
C {devices/lab_pin.sym} 3020 -300 0 0 {name=p163 sig_type=std_logic lab=UP}
C {devices/lab_pin.sym} 3060 -300 0 0 {name=p164 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} 3260 -300 0 0 {name=RSTGNAND_P2
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
C {devices/lab_pin.sym} 3280 -330 0 0 {name=p165 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 3280 -270 0 0 {name=p166 sig_type=std_logic lab=RSTG_NAND}
C {devices/lab_pin.sym} 3240 -300 0 0 {name=p167 sig_type=std_logic lab=DN}
C {devices/lab_pin.sym} 3280 -300 0 0 {name=p168 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 3480 100 0 0 {name=RSTGNAND_N1
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
C {devices/lab_pin.sym} 3500 70 0 0 {name=p169 sig_type=std_logic lab=RSTG_NAND}
C {devices/lab_pin.sym} 3500 130 0 0 {name=p170 sig_type=std_logic lab=RSTG_MID}
C {devices/lab_pin.sym} 3460 100 0 0 {name=p171 sig_type=std_logic lab=UP}
C {devices/lab_pin.sym} 3500 100 0 0 {name=p172 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 3700 100 0 0 {name=RSTGNAND_N2
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
C {devices/lab_pin.sym} 3720 70 0 0 {name=p173 sig_type=std_logic lab=RSTG_MID}
C {devices/lab_pin.sym} 3720 130 0 0 {name=p174 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 3680 100 0 0 {name=p175 sig_type=std_logic lab=DN}
C {devices/lab_pin.sym} 3720 100 0 0 {name=p176 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 3920 -300 0 0 {name=RSTGINV_P
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
C {devices/lab_pin.sym} 3940 -330 0 0 {name=p177 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 3940 -270 0 0 {name=p178 sig_type=std_logic lab=RSTPRE}
C {devices/lab_pin.sym} 3900 -300 0 0 {name=p179 sig_type=std_logic lab=RSTG_NAND}
C {devices/lab_pin.sym} 3940 -300 0 0 {name=p180 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 3920 100 0 0 {name=RSTGINV_N
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
C {devices/lab_pin.sym} 3940 70 0 0 {name=p181 sig_type=std_logic lab=RSTPRE}
C {devices/lab_pin.sym} 3940 130 0 0 {name=p182 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 3900 100 0 0 {name=p183 sig_type=std_logic lab=RSTG_NAND}
C {devices/lab_pin.sym} 3940 100 0 0 {name=p184 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 4140 -300 0 0 {name=RSTDLY1_P
W=2
L=1.0
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
C {devices/lab_pin.sym} 4160 -330 0 0 {name=p185 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 4160 -270 0 0 {name=p186 sig_type=std_logic lab=RSTD1}
C {devices/lab_pin.sym} 4120 -300 0 0 {name=p187 sig_type=std_logic lab=RSTPRE}
C {devices/lab_pin.sym} 4160 -300 0 0 {name=p188 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 4140 100 0 0 {name=RSTDLY1_N
W=1
L=1.0
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
C {devices/lab_pin.sym} 4160 70 0 0 {name=p189 sig_type=std_logic lab=RSTD1}
C {devices/lab_pin.sym} 4160 130 0 0 {name=p190 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 4120 100 0 0 {name=p191 sig_type=std_logic lab=RSTPRE}
C {devices/lab_pin.sym} 4160 100 0 0 {name=p192 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 4360 -300 0 0 {name=RSTDLY2_P
W=2
L=1.0
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
C {devices/lab_pin.sym} 4380 -330 0 0 {name=p193 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 4380 -270 0 0 {name=p194 sig_type=std_logic lab=RST}
C {devices/lab_pin.sym} 4340 -300 0 0 {name=p195 sig_type=std_logic lab=RSTD1}
C {devices/lab_pin.sym} 4380 -300 0 0 {name=p196 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 4360 100 0 0 {name=RSTDLY2_N
W=1
L=1.0
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
C {devices/lab_pin.sym} 4380 70 0 0 {name=p197 sig_type=std_logic lab=RST}
C {devices/lab_pin.sym} 4380 130 0 0 {name=p198 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 4340 100 0 0 {name=p199 sig_type=std_logic lab=RSTD1}
C {devices/lab_pin.sym} 4380 100 0 0 {name=p200 sig_type=std_logic lab=GND}
C {sky130_fd_pr/res_xhigh_po.sym} 4580 -600 0 0 {name=RBIAS
W=1
L=300
mult=1
model=res_xhigh_po
spiceprefix=X}
C {devices/lab_pin.sym} 4580 -630 0 0 {name=p201 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 4580 -570 0 0 {name=p202 sig_type=std_logic lab=NB}
C {devices/lab_pin.sym} 4560 -600 0 0 {name=p203 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 4800 100 0 0 {name=MNBIAS
W=2
L=1.0
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
C {devices/lab_pin.sym} 4820 70 0 0 {name=p204 sig_type=std_logic lab=NB}
C {devices/lab_pin.sym} 4820 130 0 0 {name=p205 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 4780 100 0 0 {name=p206 sig_type=std_logic lab=NB}
C {devices/lab_pin.sym} 4820 100 0 0 {name=p207 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 5020 -300 0 0 {name=MPBIAS
W=4
L=1.0
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
C {devices/lab_pin.sym} 5040 -330 0 0 {name=p208 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 5040 -270 0 0 {name=p209 sig_type=std_logic lab=PB}
C {devices/lab_pin.sym} 5000 -300 0 0 {name=p210 sig_type=std_logic lab=PB}
C {devices/lab_pin.sym} 5040 -300 0 0 {name=p211 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 5240 100 0 0 {name=MNBIAS2
W=2
L=1.0
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
C {devices/lab_pin.sym} 5260 70 0 0 {name=p212 sig_type=std_logic lab=PB}
C {devices/lab_pin.sym} 5260 130 0 0 {name=p213 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 5220 100 0 0 {name=p214 sig_type=std_logic lab=NB}
C {devices/lab_pin.sym} 5260 100 0 0 {name=p215 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 5460 -300 0 0 {name=MPCP
W=20
L=1.0
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
C {devices/lab_pin.sym} 5480 -330 0 0 {name=p216 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 5480 -270 0 0 {name=p217 sig_type=std_logic lab=SP}
C {devices/lab_pin.sym} 5440 -300 0 0 {name=p218 sig_type=std_logic lab=PB}
C {devices/lab_pin.sym} 5480 -300 0 0 {name=p219 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/pfet_01v8.sym} 5680 -300 0 0 {name=MPSW
W=20
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
C {devices/lab_pin.sym} 5700 -330 0 0 {name=p220 sig_type=std_logic lab=SP}
C {devices/lab_pin.sym} 5700 -270 0 0 {name=p221 sig_type=std_logic lab=CP}
C {devices/lab_pin.sym} 5660 -300 0 0 {name=p222 sig_type=std_logic lab=UPB}
C {devices/lab_pin.sym} 5700 -300 0 0 {name=p223 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 5900 100 0 0 {name=MNCP
W=10
L=1.0
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
C {devices/lab_pin.sym} 5920 70 0 0 {name=p224 sig_type=std_logic lab=SN}
C {devices/lab_pin.sym} 5920 130 0 0 {name=p225 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 5880 100 0 0 {name=p226 sig_type=std_logic lab=NB}
C {devices/lab_pin.sym} 5920 100 0 0 {name=p227 sig_type=std_logic lab=GND}
C {sky130_fd_pr/nfet_01v8.sym} 6120 100 0 0 {name=MNSW
W=10
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
C {devices/lab_pin.sym} 6140 70 0 0 {name=p228 sig_type=std_logic lab=CP}
C {devices/lab_pin.sym} 6140 130 0 0 {name=p229 sig_type=std_logic lab=SN}
C {devices/lab_pin.sym} 6100 100 0 0 {name=p230 sig_type=std_logic lab=DN}
C {devices/lab_pin.sym} 6140 100 0 0 {name=p231 sig_type=std_logic lab=GND}
C {sky130_fd_pr/pfet_01v8.sym} 6340 -300 0 0 {name=UPINV_P
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
C {devices/lab_pin.sym} 6360 -330 0 0 {name=p232 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 6360 -270 0 0 {name=p233 sig_type=std_logic lab=UPB}
C {devices/lab_pin.sym} 6320 -300 0 0 {name=p234 sig_type=std_logic lab=UP}
C {devices/lab_pin.sym} 6360 -300 0 0 {name=p235 sig_type=std_logic lab=VDD}
C {sky130_fd_pr/nfet_01v8.sym} 6340 100 0 0 {name=UPINV_N
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
C {devices/lab_pin.sym} 6360 70 0 0 {name=p236 sig_type=std_logic lab=UPB}
C {devices/lab_pin.sym} 6360 130 0 0 {name=p237 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 6320 100 0 0 {name=p238 sig_type=std_logic lab=UP}
C {devices/lab_pin.sym} 6360 100 0 0 {name=p239 sig_type=std_logic lab=GND}
C {devices/iopin.sym} -4200 -2200 0 0 {name=t1 lab=VDD}
C {devices/iopin.sym} -4200 -2100 0 0 {name=t2 lab=GND}
C {devices/ipin.sym} -4200 -2000 0 0 {name=t3 lab=REF}
C {devices/ipin.sym} -4200 -1900 0 0 {name=t4 lab=DIV}
C {devices/opin.sym} 6560 -2200 0 0 {name=t5 lab=CP}
C {devices/title.sym} -4000 -2600 0 0 {name=l1 author="2AM Logic (issue #25, sky130 PLL PFD + charge pump)"}
