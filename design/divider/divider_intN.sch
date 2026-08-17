v {xschem version=3.4.7 file_version=1.2
* divider_intN.sch -- sky130 PLL programmable integer-N feedback divider
* (issue #27)
*
* 6-bit synchronous down-counter, divide-by-N for N = 4-64 (static
* 6-bit configuration word NSEL[5:0] = N-1, no auto-calibration FSM,
* per spec row 4). Built entirely from sky130_fd_sc_hd standard cells
* via the PDK's sky130_stdcells xschem symbol library (dfrtp_2/
* dfxtp_2/inv_2/and2_2/xor2_2/mux2_2) -- each cell's own transistors
* are sky130's 1.8 V core devices, per the ratified supply flavor
* (DR-001, spec/target-spec.md row 0).
*
* Each counter bit i has a decrement path (borrow-chain subtractor,
* comparator-free) muxed against the static NSELi input, selected by
* ZERO (all-bits-zero detect, itself built from the same borrow
* chain): when ZERO=1 the counter synchronously reloads NSEL[5:0]
* (=N-1) instead of continuing to decrement past 0. The registered
* copy of ZERO (FBFF) is FBCLK -- a clean, one-CLK-period-wide pulse
* every N input cycles. Architecture choice, the programming
* interface, and the retiming/top-frequency target are documented in
* design/divider/DESIGN.md (design target, not verified by
* simulation -- that is a later issue's testbench, per #27's scope).
*
* This is a forward design (CLAUDE.md "Reverse-engineering-free"): a
* textbook synchronous down-counter with a comparator-free zero
* detect, not derived from any existing silicon or netlist.
*
* Pins: VDD, GND (supply), CLK (in, from the VCO), RESETB (in, async
* active-low reset), NSEL0..NSEL5 (in, static config bits = N-1,
* LSB..MSB), FBCLK (out, divided feedback clock).
}
G {}
V {}
S {}
E {}
C {sky130_stdcells/dfrtp_2.sym} 200 -400 0 0 {name=CNT0 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 110 -420 0 0 {name=p1 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 110 -400 0 0 {name=p2 sig_type=std_logic lab=D0}
C {devices/lab_pin.sym} 110 -380 0 0 {name=p3 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 290 -420 0 0 {name=p4 sig_type=std_logic lab=Q0}
C {sky130_stdcells/mux2_2.sym} 200 -200 0 0 {name=LDMUX0 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 160 -220 0 0 {name=p5 sig_type=std_logic lab=NQ0}
C {devices/lab_pin.sym} 160 -180 0 0 {name=p6 sig_type=std_logic lab=NSEL0}
C {devices/lab_pin.sym} 160 -140 0 0 {name=p7 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 240 -200 0 0 {name=p8 sig_type=std_logic lab=D0}
C {sky130_stdcells/inv_2.sym} 200 400 0 0 {name=QINV0 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 160 400 0 0 {name=p9 sig_type=std_logic lab=Q0}
C {devices/lab_pin.sym} 240 400 0 0 {name=p10 sig_type=std_logic lab=NQ0}
C {sky130_stdcells/dfrtp_2.sym} 750 -400 0 0 {name=CNT1 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 660 -420 0 0 {name=p11 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 660 -400 0 0 {name=p12 sig_type=std_logic lab=D1}
C {devices/lab_pin.sym} 660 -380 0 0 {name=p13 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 840 -420 0 0 {name=p14 sig_type=std_logic lab=Q1}
C {sky130_stdcells/mux2_2.sym} 750 -200 0 0 {name=LDMUX1 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 710 -220 0 0 {name=p15 sig_type=std_logic lab=DDEC1}
C {devices/lab_pin.sym} 710 -180 0 0 {name=p16 sig_type=std_logic lab=NSEL1}
C {devices/lab_pin.sym} 710 -140 0 0 {name=p17 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 790 -200 0 0 {name=p18 sig_type=std_logic lab=D1}
C {sky130_stdcells/xor2_2.sym} 750 0 0 0 {name=DECXOR1 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 690 -20 0 0 {name=p19 sig_type=std_logic lab=Q1}
C {devices/lab_pin.sym} 690 20 0 0 {name=p20 sig_type=std_logic lab=NQ0}
C {devices/lab_pin.sym} 810 0 0 0 {name=p21 sig_type=std_logic lab=DDEC1}
C {sky130_stdcells/inv_2.sym} 750 400 0 0 {name=QINV1 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 710 400 0 0 {name=p22 sig_type=std_logic lab=Q1}
C {devices/lab_pin.sym} 790 400 0 0 {name=p23 sig_type=std_logic lab=NQ1}
C {sky130_stdcells/dfrtp_2.sym} 1300 -400 0 0 {name=CNT2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1210 -420 0 0 {name=p24 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 1210 -400 0 0 {name=p25 sig_type=std_logic lab=D2}
C {devices/lab_pin.sym} 1210 -380 0 0 {name=p26 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 1390 -420 0 0 {name=p27 sig_type=std_logic lab=Q2}
C {sky130_stdcells/mux2_2.sym} 1300 -200 0 0 {name=LDMUX2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1260 -220 0 0 {name=p28 sig_type=std_logic lab=DDEC2}
C {devices/lab_pin.sym} 1260 -180 0 0 {name=p29 sig_type=std_logic lab=NSEL2}
C {devices/lab_pin.sym} 1260 -140 0 0 {name=p30 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 1340 -200 0 0 {name=p31 sig_type=std_logic lab=D2}
C {sky130_stdcells/xor2_2.sym} 1300 0 0 0 {name=DECXOR2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1240 -20 0 0 {name=p32 sig_type=std_logic lab=Q2}
C {devices/lab_pin.sym} 1240 20 0 0 {name=p33 sig_type=std_logic lab=BOR2}
C {devices/lab_pin.sym} 1360 0 0 0 {name=p34 sig_type=std_logic lab=DDEC2}
C {sky130_stdcells/and2_2.sym} 1300 200 0 0 {name=BORAND2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1240 180 0 0 {name=p35 sig_type=std_logic lab=NQ0}
C {devices/lab_pin.sym} 1240 220 0 0 {name=p36 sig_type=std_logic lab=NQ1}
C {devices/lab_pin.sym} 1360 200 0 0 {name=p37 sig_type=std_logic lab=BOR2}
C {sky130_stdcells/inv_2.sym} 1300 400 0 0 {name=QINV2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1260 400 0 0 {name=p38 sig_type=std_logic lab=Q2}
C {devices/lab_pin.sym} 1340 400 0 0 {name=p39 sig_type=std_logic lab=NQ2}
C {sky130_stdcells/dfrtp_2.sym} 1850 -400 0 0 {name=CNT3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1760 -420 0 0 {name=p40 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 1760 -400 0 0 {name=p41 sig_type=std_logic lab=D3}
C {devices/lab_pin.sym} 1760 -380 0 0 {name=p42 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 1940 -420 0 0 {name=p43 sig_type=std_logic lab=Q3}
C {sky130_stdcells/mux2_2.sym} 1850 -200 0 0 {name=LDMUX3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1810 -220 0 0 {name=p44 sig_type=std_logic lab=DDEC3}
C {devices/lab_pin.sym} 1810 -180 0 0 {name=p45 sig_type=std_logic lab=NSEL3}
C {devices/lab_pin.sym} 1810 -140 0 0 {name=p46 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 1890 -200 0 0 {name=p47 sig_type=std_logic lab=D3}
C {sky130_stdcells/xor2_2.sym} 1850 0 0 0 {name=DECXOR3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1790 -20 0 0 {name=p48 sig_type=std_logic lab=Q3}
C {devices/lab_pin.sym} 1790 20 0 0 {name=p49 sig_type=std_logic lab=BOR3}
C {devices/lab_pin.sym} 1910 0 0 0 {name=p50 sig_type=std_logic lab=DDEC3}
C {sky130_stdcells/and2_2.sym} 1850 200 0 0 {name=BORAND3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1790 180 0 0 {name=p51 sig_type=std_logic lab=BOR2}
C {devices/lab_pin.sym} 1790 220 0 0 {name=p52 sig_type=std_logic lab=NQ2}
C {devices/lab_pin.sym} 1910 200 0 0 {name=p53 sig_type=std_logic lab=BOR3}
C {sky130_stdcells/inv_2.sym} 1850 400 0 0 {name=QINV3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1810 400 0 0 {name=p54 sig_type=std_logic lab=Q3}
C {devices/lab_pin.sym} 1890 400 0 0 {name=p55 sig_type=std_logic lab=NQ3}
C {sky130_stdcells/dfrtp_2.sym} 2400 -400 0 0 {name=CNT4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2310 -420 0 0 {name=p56 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 2310 -400 0 0 {name=p57 sig_type=std_logic lab=D4}
C {devices/lab_pin.sym} 2310 -380 0 0 {name=p58 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 2490 -420 0 0 {name=p59 sig_type=std_logic lab=Q4}
C {sky130_stdcells/mux2_2.sym} 2400 -200 0 0 {name=LDMUX4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2360 -220 0 0 {name=p60 sig_type=std_logic lab=DDEC4}
C {devices/lab_pin.sym} 2360 -180 0 0 {name=p61 sig_type=std_logic lab=NSEL4}
C {devices/lab_pin.sym} 2360 -140 0 0 {name=p62 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 2440 -200 0 0 {name=p63 sig_type=std_logic lab=D4}
C {sky130_stdcells/xor2_2.sym} 2400 0 0 0 {name=DECXOR4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2340 -20 0 0 {name=p64 sig_type=std_logic lab=Q4}
C {devices/lab_pin.sym} 2340 20 0 0 {name=p65 sig_type=std_logic lab=BOR4}
C {devices/lab_pin.sym} 2460 0 0 0 {name=p66 sig_type=std_logic lab=DDEC4}
C {sky130_stdcells/and2_2.sym} 2400 200 0 0 {name=BORAND4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2340 180 0 0 {name=p67 sig_type=std_logic lab=BOR3}
C {devices/lab_pin.sym} 2340 220 0 0 {name=p68 sig_type=std_logic lab=NQ3}
C {devices/lab_pin.sym} 2460 200 0 0 {name=p69 sig_type=std_logic lab=BOR4}
C {sky130_stdcells/inv_2.sym} 2400 400 0 0 {name=QINV4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2360 400 0 0 {name=p70 sig_type=std_logic lab=Q4}
C {devices/lab_pin.sym} 2440 400 0 0 {name=p71 sig_type=std_logic lab=NQ4}
C {sky130_stdcells/dfrtp_2.sym} 2950 -400 0 0 {name=CNT5 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2860 -420 0 0 {name=p72 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 2860 -400 0 0 {name=p73 sig_type=std_logic lab=D5}
C {devices/lab_pin.sym} 2860 -380 0 0 {name=p74 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 3040 -420 0 0 {name=p75 sig_type=std_logic lab=Q5}
C {sky130_stdcells/mux2_2.sym} 2950 -200 0 0 {name=LDMUX5 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2910 -220 0 0 {name=p76 sig_type=std_logic lab=DDEC5}
C {devices/lab_pin.sym} 2910 -180 0 0 {name=p77 sig_type=std_logic lab=NSEL5}
C {devices/lab_pin.sym} 2910 -140 0 0 {name=p78 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 2990 -200 0 0 {name=p79 sig_type=std_logic lab=D5}
C {sky130_stdcells/xor2_2.sym} 2950 0 0 0 {name=DECXOR5 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2890 -20 0 0 {name=p80 sig_type=std_logic lab=Q5}
C {devices/lab_pin.sym} 2890 20 0 0 {name=p81 sig_type=std_logic lab=BOR5}
C {devices/lab_pin.sym} 3010 0 0 0 {name=p82 sig_type=std_logic lab=DDEC5}
C {sky130_stdcells/and2_2.sym} 2950 200 0 0 {name=BORAND5 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2890 180 0 0 {name=p83 sig_type=std_logic lab=BOR4}
C {devices/lab_pin.sym} 2890 220 0 0 {name=p84 sig_type=std_logic lab=NQ4}
C {devices/lab_pin.sym} 3010 200 0 0 {name=p85 sig_type=std_logic lab=BOR5}
C {sky130_stdcells/inv_2.sym} 2950 400 0 0 {name=QINV5 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2910 400 0 0 {name=p86 sig_type=std_logic lab=Q5}
C {devices/lab_pin.sym} 2990 400 0 0 {name=p87 sig_type=std_logic lab=NQ5}
C {sky130_stdcells/and2_2.sym} 2950 500 0 0 {name=ZDET VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2890 480 0 0 {name=p88 sig_type=std_logic lab=BOR5}
C {devices/lab_pin.sym} 2890 520 0 0 {name=p89 sig_type=std_logic lab=NQ5}
C {devices/lab_pin.sym} 3010 500 0 0 {name=p90 sig_type=std_logic lab=ZERO}
C {sky130_stdcells/dfxtp_2.sym} 3800 -400 0 0 {name=FBFF VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 3710 -410 0 0 {name=p91 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 3710 -390 0 0 {name=p92 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 3890 -410 0 0 {name=p93 sig_type=std_logic lab=FBCLK}
C {devices/iopin.sym} -200 -900 0 0 {name=t1 lab=VDD}
C {devices/iopin.sym} -200 -800 0 0 {name=t2 lab=GND}
C {devices/ipin.sym} -200 -700 0 0 {name=t3 lab=CLK}
C {devices/ipin.sym} -200 -600 0 0 {name=t4 lab=RESETB}
C {devices/ipin.sym} -200 -500 0 0 {name=t5 lab=NSEL0}
C {devices/ipin.sym} -200 -440 0 0 {name=t6 lab=NSEL1}
C {devices/ipin.sym} -200 -380 0 0 {name=t7 lab=NSEL2}
C {devices/ipin.sym} -200 -320 0 0 {name=t8 lab=NSEL3}
C {devices/ipin.sym} -200 -260 0 0 {name=t9 lab=NSEL4}
C {devices/ipin.sym} -200 -200 0 0 {name=t10 lab=NSEL5}
C {devices/opin.sym} 4100 -410 0 0 {name=t11 lab=FBCLK}
C {devices/title.sym} 200 -1100 0 0 {name=l1 author="2AM Logic (issue #27, sky130 PLL feedback divider)"}
