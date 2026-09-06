v {xschem version=3.4.7 file_version=1.2
* divider_intN.sch -- sky130 PLL programmable integer-N feedback divider
* (issue #27; retimed by #107; dual-modulus front-end by #114)
*
* Divide-by-N for N = 4-64, from a static 6-bit configuration word
* NSEL[5:0] = N-1 (no auto-calibration FSM, per spec row 4). Built
* entirely from sky130_fd_sc_hd standard cells via the PDK's
* sky130_stdcells xschem symbol library -- each cell's own transistors
* are sky130's 1.8 V core devices, per the ratified supply flavor
* (DR-001, spec/target-spec.md row 0).
*
* ARCHITECTURE (issue #114): dual-modulus (divide-by-2/3) prescaler
* front-end + 5-bit synchronous down-counter back-end.
*
*   N = 2*M + S,  M = floor(N/2) (the back-end's modulus),
*                 S = N mod 2    (0 or 1 swallowed CLK cycles)
*
* Only the two prescaler flip-flops (XPA/XPB) run at the full CLK
* (VCO) rate, and each of them sees exactly ONE gate between
* flip-flops (XPANOR / XPBAND). The back-end counter -- which carries
* the deep borrow chain -- is clocked by PCLK = ~PA at CLK/2 or CLK/3,
* so it has two to three CLK periods to settle instead of one. That is
* what lifts the block's maximum correct-division frequency above the
* VCO's own ~1.09 GHz top free-running frequency at every ratified PVT
* corner; see design/divider/DESIGN.md's "Issue #114" section for the
* measured before/after table and for why retiming or gate sizing alone
* provably could not get there (issues #104/#107).
*
* Prescaler (XPA/XPB, CLK-rate, 3 states, self-correcting):
*   DPA = ~(PA | PB)          [XPANOR]   -- s0 -> s1 -> s0        (/2)
*   DPB = PA & MC             [XPBAND]   -- s0 -> s1 -> s2 -> s0  (/3)
*   PCLK = ~PA                [XPCKINV]  -- back-end clock
* PA is high for exactly one CLK cycle per prescaler period, so PCLK
* has one rising edge per period. MC (modulus control) is registered in
* the back-end domain and is therefore stable for a full prescaler
* period (2-3 CLK cycles) before the CLK edge that samples it -- the
* usual pulse-swallow race is avoided by taking the back-end clock off
* PA's FALLING edge.
*
* Back-end (XCNT0..XCNT4 + reload muxes, PCLK-rate): the same
* comparator-free synchronous down-counter with a flattened
* (issue #107) borrow chain the 6-bit version used, one bit narrower.
* It reloads L[4:0] = M-1 whenever ZERO (all five bits zero) is
* asserted, so it divides PCLK by M.
*
* Swallow control (XMCFF/XMCAND): MC = ODD & ZERO, registered on PCLK,
* so MC is high for exactly one back-end period out of M, and only when
* N is odd. That inserts exactly one extra CLK cycle (one /3 prescaler
* period) per output period -- no separate swallow counter is needed,
* and there is no S <= M coverage restriction, so the full N = 4-64
* range is reachable (unlike a /4-/5 pulse-swallow, which cannot
* synthesize N = 6, 7 or 11).
*
* Static decode (XODD, XNB*, XLDEC*): pure combinational logic on the
* static NSEL[5:0] pins, off every timing path.
*   ODD  = ~NSEL0                    (N = NSEL+1 is odd iff NSEL0 = 0)
*   L[4:0] = bits [5:1] of (NSEL - 1) = floor((NSEL-1)/2) = M - 1
* so the back-end divides PCLK by M = floor(N/2). Worked examples:
* N = 4 -> L = 1, ODD = 0 -> 2*2   = 4;  N = 25 -> L = 11, ODD = 1 ->
* 2*12+1 = 25;  N = 64 -> L = 31, ODD = 0 -> 2*32 = 64.
*
* FBCLK (XFBFF) is ZERO registered on PCLK: one clean pulse, one
* prescaler period (2-3 CLK cycles) wide, once every N CLK cycles.
* The PFD (design/pfd-cp) is rising-edge triggered, so the wider pulse
* is equivalent to the old one-CLK-period pulse for the loop.
*
* This is a forward design (CLAUDE.md "Reverse-engineering-free"): a
* textbook dual-modulus prescaler / programmable-counter divider, not
* derived from any existing silicon or netlist.
*
* Pins: VDD, GND (supply), CLK (in, from the VCO), RESETB (in, async
* active-low reset), NSEL0..NSEL5 (in, static config bits = N-1,
* LSB..MSB), FBCLK (out, divided feedback clock).
}
G {}
V {}
S {}
E {}
C {sky130_stdcells/dfrtp_2.sym} 200 -400 0 0 {name=XCNT0 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 110 -420 0 0 {name=p1 sig_type=std_logic lab=PCLK}
C {devices/lab_pin.sym} 110 -400 0 0 {name=p2 sig_type=std_logic lab=D0}
C {devices/lab_pin.sym} 110 -380 0 0 {name=p3 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 290 -420 0 0 {name=p4 sig_type=std_logic lab=Q0}
C {sky130_stdcells/mux2_2.sym} 200 -200 0 0 {name=XLDMUX0 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 160 -220 0 0 {name=p5 sig_type=std_logic lab=NQ0}
C {devices/lab_pin.sym} 160 -180 0 0 {name=p6 sig_type=std_logic lab=L0}
C {devices/lab_pin.sym} 160 -140 0 0 {name=p7 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 240 -200 0 0 {name=p8 sig_type=std_logic lab=D0}
C {sky130_stdcells/inv_2.sym} 200 400 0 0 {name=XQINV0 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 160 400 0 0 {name=p9 sig_type=std_logic lab=Q0}
C {devices/lab_pin.sym} 240 400 0 0 {name=p10 sig_type=std_logic lab=NQ0}
C {sky130_stdcells/dfrtp_2.sym} 750 -400 0 0 {name=XCNT1 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 660 -420 0 0 {name=p11 sig_type=std_logic lab=PCLK}
C {devices/lab_pin.sym} 660 -400 0 0 {name=p12 sig_type=std_logic lab=D1}
C {devices/lab_pin.sym} 660 -380 0 0 {name=p13 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 840 -420 0 0 {name=p14 sig_type=std_logic lab=Q1}
C {sky130_stdcells/mux2_2.sym} 750 -200 0 0 {name=XLDMUX1 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 710 -220 0 0 {name=p15 sig_type=std_logic lab=DDEC1}
C {devices/lab_pin.sym} 710 -180 0 0 {name=p16 sig_type=std_logic lab=L1}
C {devices/lab_pin.sym} 710 -140 0 0 {name=p17 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 790 -200 0 0 {name=p18 sig_type=std_logic lab=D1}
C {sky130_stdcells/xor2_2.sym} 750 0 0 0 {name=XDECXOR1 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 690 -20 0 0 {name=p19 sig_type=std_logic lab=Q1}
C {devices/lab_pin.sym} 690 20 0 0 {name=p20 sig_type=std_logic lab=NQ0}
C {devices/lab_pin.sym} 810 0 0 0 {name=p21 sig_type=std_logic lab=DDEC1}
C {sky130_stdcells/inv_2.sym} 750 400 0 0 {name=XQINV1 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 710 400 0 0 {name=p22 sig_type=std_logic lab=Q1}
C {devices/lab_pin.sym} 790 400 0 0 {name=p23 sig_type=std_logic lab=NQ1}
C {sky130_stdcells/dfrtp_2.sym} 1300 -400 0 0 {name=XCNT2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1210 -420 0 0 {name=p24 sig_type=std_logic lab=PCLK}
C {devices/lab_pin.sym} 1210 -400 0 0 {name=p25 sig_type=std_logic lab=D2}
C {devices/lab_pin.sym} 1210 -380 0 0 {name=p26 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 1390 -420 0 0 {name=p27 sig_type=std_logic lab=Q2}
C {sky130_stdcells/mux2_2.sym} 1300 -200 0 0 {name=XLDMUX2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1260 -220 0 0 {name=p28 sig_type=std_logic lab=DDEC2}
C {devices/lab_pin.sym} 1260 -180 0 0 {name=p29 sig_type=std_logic lab=L2}
C {devices/lab_pin.sym} 1260 -140 0 0 {name=p30 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 1340 -200 0 0 {name=p31 sig_type=std_logic lab=D2}
C {sky130_stdcells/xor2_2.sym} 1300 0 0 0 {name=XDECXOR2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1240 -20 0 0 {name=p32 sig_type=std_logic lab=Q2}
C {devices/lab_pin.sym} 1240 20 0 0 {name=p33 sig_type=std_logic lab=BOR2}
C {devices/lab_pin.sym} 1360 0 0 0 {name=p34 sig_type=std_logic lab=DDEC2}
C {sky130_stdcells/and2_2.sym} 1300 200 0 0 {name=XBORAND2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1240 180 0 0 {name=p35 sig_type=std_logic lab=NQ0}
C {devices/lab_pin.sym} 1240 220 0 0 {name=p36 sig_type=std_logic lab=NQ1}
C {devices/lab_pin.sym} 1360 200 0 0 {name=p37 sig_type=std_logic lab=BOR2}
C {sky130_stdcells/inv_2.sym} 1300 400 0 0 {name=XQINV2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1260 400 0 0 {name=p38 sig_type=std_logic lab=Q2}
C {devices/lab_pin.sym} 1340 400 0 0 {name=p39 sig_type=std_logic lab=NQ2}
C {sky130_stdcells/dfrtp_2.sym} 1850 -400 0 0 {name=XCNT3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1760 -420 0 0 {name=p40 sig_type=std_logic lab=PCLK}
C {devices/lab_pin.sym} 1760 -400 0 0 {name=p41 sig_type=std_logic lab=D3}
C {devices/lab_pin.sym} 1760 -380 0 0 {name=p42 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 1940 -420 0 0 {name=p43 sig_type=std_logic lab=Q3}
C {sky130_stdcells/mux2_2.sym} 1850 -200 0 0 {name=XLDMUX3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1810 -220 0 0 {name=p44 sig_type=std_logic lab=DDEC3}
C {devices/lab_pin.sym} 1810 -180 0 0 {name=p45 sig_type=std_logic lab=L3}
C {devices/lab_pin.sym} 1810 -140 0 0 {name=p46 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 1890 -200 0 0 {name=p47 sig_type=std_logic lab=D3}
C {sky130_stdcells/xor2_2.sym} 1850 0 0 0 {name=XDECXOR3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1790 -20 0 0 {name=p48 sig_type=std_logic lab=Q3}
C {devices/lab_pin.sym} 1790 20 0 0 {name=p49 sig_type=std_logic lab=BOR3}
C {devices/lab_pin.sym} 1910 0 0 0 {name=p50 sig_type=std_logic lab=DDEC3}
C {sky130_stdcells/and3_2.sym} 1850 200 0 0 {name=XBORAND3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1790 160 0 0 {name=p51 sig_type=std_logic lab=NQ0}
C {devices/lab_pin.sym} 1790 200 0 0 {name=p52 sig_type=std_logic lab=NQ1}
C {devices/lab_pin.sym} 1790 240 0 0 {name=p94 sig_type=std_logic lab=NQ2}
C {devices/lab_pin.sym} 1910 200 0 0 {name=p53 sig_type=std_logic lab=BOR3}
C {sky130_stdcells/inv_2.sym} 1850 400 0 0 {name=XQINV3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1810 400 0 0 {name=p54 sig_type=std_logic lab=Q3}
C {devices/lab_pin.sym} 1890 400 0 0 {name=p55 sig_type=std_logic lab=NQ3}
C {sky130_stdcells/dfrtp_2.sym} 2400 -400 0 0 {name=XCNT4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2310 -420 0 0 {name=p56 sig_type=std_logic lab=PCLK}
C {devices/lab_pin.sym} 2310 -400 0 0 {name=p57 sig_type=std_logic lab=D4}
C {devices/lab_pin.sym} 2310 -380 0 0 {name=p58 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 2490 -420 0 0 {name=p59 sig_type=std_logic lab=Q4}
C {sky130_stdcells/mux2_2.sym} 2400 -200 0 0 {name=XLDMUX4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2360 -220 0 0 {name=p60 sig_type=std_logic lab=DDEC4}
C {devices/lab_pin.sym} 2360 -180 0 0 {name=p61 sig_type=std_logic lab=L4}
C {devices/lab_pin.sym} 2360 -140 0 0 {name=p62 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 2440 -200 0 0 {name=p63 sig_type=std_logic lab=D4}
C {sky130_stdcells/xor2_2.sym} 2400 0 0 0 {name=XDECXOR4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2340 -20 0 0 {name=p64 sig_type=std_logic lab=Q4}
C {devices/lab_pin.sym} 2340 20 0 0 {name=p65 sig_type=std_logic lab=BOR4}
C {devices/lab_pin.sym} 2460 0 0 0 {name=p66 sig_type=std_logic lab=DDEC4}
C {sky130_stdcells/and4_2.sym} 2400 200 0 0 {name=XBORAND4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2340 140 0 0 {name=p95 sig_type=std_logic lab=NQ0}
C {devices/lab_pin.sym} 2340 180 0 0 {name=p67 sig_type=std_logic lab=NQ1}
C {devices/lab_pin.sym} 2340 220 0 0 {name=p68 sig_type=std_logic lab=NQ2}
C {devices/lab_pin.sym} 2340 260 0 0 {name=p96 sig_type=std_logic lab=NQ3}
C {devices/lab_pin.sym} 2460 200 0 0 {name=p69 sig_type=std_logic lab=BOR4}
C {sky130_stdcells/inv_2.sym} 2400 400 0 0 {name=XQINV4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2360 400 0 0 {name=p70 sig_type=std_logic lab=Q4}
C {devices/lab_pin.sym} 2440 400 0 0 {name=p71 sig_type=std_logic lab=NQ4}
C {sky130_stdcells/and2_2.sym} 2950 200 0 0 {name=XZDET VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2890 180 0 0 {name=p88 sig_type=std_logic lab=BOR4}
C {devices/lab_pin.sym} 2890 220 0 0 {name=p89 sig_type=std_logic lab=NQ4}
C {devices/lab_pin.sym} 3010 200 0 0 {name=p90 sig_type=std_logic lab=ZERO}
C {sky130_stdcells/dfrtp_2.sym} 200 700 0 0 {name=XPA VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 110 680 0 0 {name=p100 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 110 700 0 0 {name=p101 sig_type=std_logic lab=DPA}
C {devices/lab_pin.sym} 110 720 0 0 {name=p102 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 290 680 0 0 {name=p103 sig_type=std_logic lab=PA}
C {sky130_stdcells/nor2_2.sym} 750 700 0 0 {name=XPANOR VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 690 680 0 0 {name=p104 sig_type=std_logic lab=PA}
C {devices/lab_pin.sym} 690 720 0 0 {name=p105 sig_type=std_logic lab=PB}
C {devices/lab_pin.sym} 810 700 0 0 {name=p106 sig_type=std_logic lab=DPA}
C {sky130_stdcells/dfrtp_2.sym} 1300 700 0 0 {name=XPB VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1210 680 0 0 {name=p107 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 1210 700 0 0 {name=p108 sig_type=std_logic lab=DPB}
C {devices/lab_pin.sym} 1210 720 0 0 {name=p109 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 1390 680 0 0 {name=p110 sig_type=std_logic lab=PB}
C {sky130_stdcells/and2_2.sym} 1850 700 0 0 {name=XPBAND VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1790 680 0 0 {name=p111 sig_type=std_logic lab=PA}
C {devices/lab_pin.sym} 1790 720 0 0 {name=p112 sig_type=std_logic lab=MC}
C {devices/lab_pin.sym} 1910 700 0 0 {name=p113 sig_type=std_logic lab=DPB}
C {sky130_stdcells/inv_2.sym} 2400 700 0 0 {name=XPCKINV VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2360 700 0 0 {name=p114 sig_type=std_logic lab=PA}
C {devices/lab_pin.sym} 2440 700 0 0 {name=p115 sig_type=std_logic lab=PCLK}
C {sky130_stdcells/dfrtp_2.sym} 200 900 0 0 {name=XMCFF VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 110 880 0 0 {name=p116 sig_type=std_logic lab=PCLK}
C {devices/lab_pin.sym} 110 900 0 0 {name=p117 sig_type=std_logic lab=DMC}
C {devices/lab_pin.sym} 110 920 0 0 {name=p118 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} 290 880 0 0 {name=p119 sig_type=std_logic lab=MC}
C {sky130_stdcells/and2_2.sym} 750 900 0 0 {name=XMCAND VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 690 880 0 0 {name=p120 sig_type=std_logic lab=ODD}
C {devices/lab_pin.sym} 690 920 0 0 {name=p121 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 810 900 0 0 {name=p122 sig_type=std_logic lab=DMC}
C {sky130_stdcells/dfxtp_2.sym} 200 1100 0 0 {name=XFBFF VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 110 1090 0 0 {name=p91 sig_type=std_logic lab=PCLK}
C {devices/lab_pin.sym} 110 1110 0 0 {name=p92 sig_type=std_logic lab=ZERO}
C {devices/lab_pin.sym} 290 1090 0 0 {name=p93 sig_type=std_logic lab=FBCLK}
C {sky130_stdcells/inv_2.sym} 200 1300 0 0 {name=XODD VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 160 1300 0 0 {name=p123 sig_type=std_logic lab=NSEL0}
C {devices/lab_pin.sym} 240 1300 0 0 {name=p124 sig_type=std_logic lab=ODD}
C {sky130_stdcells/nor2_2.sym} 750 1300 0 0 {name=XNB2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 690 1280 0 0 {name=p125 sig_type=std_logic lab=NSEL0}
C {devices/lab_pin.sym} 690 1320 0 0 {name=p126 sig_type=std_logic lab=NSEL1}
C {devices/lab_pin.sym} 810 1300 0 0 {name=p127 sig_type=std_logic lab=NB2}
C {sky130_stdcells/nor3_2.sym} 1300 1300 0 0 {name=XNB3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1240 1260 0 0 {name=p128 sig_type=std_logic lab=NSEL0}
C {devices/lab_pin.sym} 1240 1300 0 0 {name=p129 sig_type=std_logic lab=NSEL1}
C {devices/lab_pin.sym} 1240 1340 0 0 {name=p130 sig_type=std_logic lab=NSEL2}
C {devices/lab_pin.sym} 1360 1300 0 0 {name=p131 sig_type=std_logic lab=NB3}
C {sky130_stdcells/nor4_2.sym} 1850 1300 0 0 {name=XNB4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1790 1240 0 0 {name=p132 sig_type=std_logic lab=NSEL0}
C {devices/lab_pin.sym} 1790 1280 0 0 {name=p133 sig_type=std_logic lab=NSEL1}
C {devices/lab_pin.sym} 1790 1320 0 0 {name=p134 sig_type=std_logic lab=NSEL2}
C {devices/lab_pin.sym} 1790 1360 0 0 {name=p135 sig_type=std_logic lab=NSEL3}
C {devices/lab_pin.sym} 1910 1300 0 0 {name=p136 sig_type=std_logic lab=NB4}
C {sky130_stdcells/inv_2.sym} 2400 1300 0 0 {name=XNS4INV VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2360 1300 0 0 {name=p137 sig_type=std_logic lab=NSEL4}
C {devices/lab_pin.sym} 2440 1300 0 0 {name=p138 sig_type=std_logic lab=NNSEL4}
C {sky130_stdcells/and2_2.sym} 2950 1300 0 0 {name=XNB5 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2890 1280 0 0 {name=p139 sig_type=std_logic lab=NB4}
C {devices/lab_pin.sym} 2890 1320 0 0 {name=p140 sig_type=std_logic lab=NNSEL4}
C {devices/lab_pin.sym} 3010 1300 0 0 {name=p141 sig_type=std_logic lab=NB5}
C {sky130_stdcells/xnor2_2.sym} 200 1550 0 0 {name=XLDEC0 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 140 1530 0 0 {name=p142 sig_type=std_logic lab=NSEL1}
C {devices/lab_pin.sym} 140 1570 0 0 {name=p143 sig_type=std_logic lab=NSEL0}
C {devices/lab_pin.sym} 260 1550 0 0 {name=p144 sig_type=std_logic lab=L0}
C {sky130_stdcells/xor2_2.sym} 750 1550 0 0 {name=XLDEC1 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 690 1530 0 0 {name=p145 sig_type=std_logic lab=NSEL2}
C {devices/lab_pin.sym} 690 1570 0 0 {name=p146 sig_type=std_logic lab=NB2}
C {devices/lab_pin.sym} 810 1550 0 0 {name=p147 sig_type=std_logic lab=L1}
C {sky130_stdcells/xor2_2.sym} 1300 1550 0 0 {name=XLDEC2 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1240 1530 0 0 {name=p148 sig_type=std_logic lab=NSEL3}
C {devices/lab_pin.sym} 1240 1570 0 0 {name=p149 sig_type=std_logic lab=NB3}
C {devices/lab_pin.sym} 1360 1550 0 0 {name=p150 sig_type=std_logic lab=L2}
C {sky130_stdcells/xor2_2.sym} 1850 1550 0 0 {name=XLDEC3 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 1790 1530 0 0 {name=p151 sig_type=std_logic lab=NSEL4}
C {devices/lab_pin.sym} 1790 1570 0 0 {name=p152 sig_type=std_logic lab=NB4}
C {devices/lab_pin.sym} 1910 1550 0 0 {name=p153 sig_type=std_logic lab=L3}
C {sky130_stdcells/xor2_2.sym} 2400 1550 0 0 {name=XLDEC4 VGND=GND VNB=GND VPB=VDD VPWR=VDD}
C {devices/lab_pin.sym} 2340 1530 0 0 {name=p154 sig_type=std_logic lab=NSEL5}
C {devices/lab_pin.sym} 2340 1570 0 0 {name=p155 sig_type=std_logic lab=NB5}
C {devices/lab_pin.sym} 2460 1550 0 0 {name=p156 sig_type=std_logic lab=L4}
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
