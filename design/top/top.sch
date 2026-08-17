v {xschem version=3.4.7 file_version=1.2
* top.sch -- sky130 PLL top-level integration schematic (issue #28)
*
* Wires the four already-standalone PLL blocks (#24 VCO, #25 PFD + charge
* pump, #26 loop filter, #27 divider) into the standard integer-N
* charge-pump PLL closed loop, purely by hierarchical instantiation of each
* block's own symbol -- no new active/passive devices are added here, and
* no block's internal schematic is modified. Wiring uses this repo's
* established net-label convention (devices/lab_pin.sym / ipin.sym /
* opin.sym / iopin.sym placed coincident with each instantiated block's own
* pin location, connected by matching lab= names -- the same convention
* every one of the four block schematics already uses internally, with zero
* explicit wire (N) segments) rather than drawn wires.
*
* Closed-loop topology:
*   REF (top-level input) -----------------------> PFDCP.REF
*   DIV.FBCLK (feedback) -------------------------> PFDCP.DIV
*   PFDCP.CP  --------------------------------------> LF.CP
*   LF.VCTRL  ---------------------------------------> VCO.VCTRL
*   VCO.CLK   ---------------------------------------> top-level CLK output
*   VCO.CLK   ---------------------------------------> DIV.CLK (feedback tap)
*   RESETB (top-level input) ---------------------> DIV.RESETB
*   NSEL0..NSEL5 (top-level inputs, N-1) ----------> DIV.NSEL0..NSEL5
*   VDD/GND (top-level supply) --------------------> PFDCP, VCO, DIV
*                                                     (LF is purely passive,
*                                                     no VDD pin -- see
*                                                     design/loop-filter/
*                                                     DESIGN.md)
*
* No interface adaptation (level shifting, buffering) is needed between any
* two blocks: every block was independently designed against the same
* ratified 1.8 V core supply flavor (DR-001, spec/target-spec.md row 0,
* sky130_fd_pr__{n,p}fet_01v8 / sky130_fd_sc_hd standard cells, which are
* themselves built from the same core devices), so every digital signal
* crossing a block boundary here (REF, DIV/FBCLK, CLK, RESETB, NSEL[5:0])
* is already a matching VDD/GND rail-to-rail sky130 1.8 V logic signal on
* both sides, and every analog signal crossing a boundary (CP, VCTRL) is
* already in the 0-VDD range each neighboring block's own device sizing
* assumes. See design/top/DESIGN.md for the full rationale, including the
* two coordination notes (PFD/CP's Icp vs. the loop filter's placeholder
* value, and VCO's Kvco vs. the loop filter's design-point Kvco) that this
* issue explicitly does NOT resolve (tracked as a documented follow-up, not
* silently reconciled here).
*
* This is a forward design (CLAUDE.md "Reverse-engineering-free"): a
* textbook charge-pump integer-N PLL topology (PFD -> charge pump -> loop
* filter -> VCO -> feedback divider -> PFD), not derived from any existing
* silicon or netlist. No spec/target-spec.md row is edited by this issue.
*
* Pins: VDD, GND (supply, inout), REF (reference clock, in), RESETB
* (async active-low divider reset, in), NSEL0..NSEL5 (divider config word
* N-1, in), CLK (PLL output, out).
}
G {}
V {}
S {}
E {}
C {design/pfd-cp/pfd_cp.sym} 0 0 0 0 {name=XPFDCP}
C {design/loop-filter/loop_filter.sym} 900 0 0 0 {name=XLF}
C {design/vco/vco_ring5.sym} 1800 0 0 0 {name=XVCO}
C {design/divider/divider_intN.sym} 1800 900 0 0 {name=XDIV}
C {devices/lab_pin.sym} 130 0 0 0 {name=p1 sig_type=std_logic lab=CP}
C {devices/lab_pin.sym} 770 0 0 0 {name=p2 sig_type=std_logic lab=CP}
C {devices/lab_pin.sym} 1030 0 0 0 {name=p3 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} 1670 0 0 0 {name=p4 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} -130 40 0 0 {name=p5 sig_type=std_logic lab=FBCLK}
C {devices/lab_pin.sym} 1930 900 0 0 {name=p6 sig_type=std_logic lab=FBCLK}
C {devices/lab_pin.sym} 1670 760 0 0 {name=p7 sig_type=std_logic lab=CLK}
C {devices/lab_pin.sym} 1800 -80 0 0 {name=p8 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 1800 720 0 0 {name=p9 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 900 80 0 0 {name=p10 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1800 80 0 0 {name=p11 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1800 1080 0 0 {name=p12 sig_type=std_logic lab=GND}
C {devices/iopin.sym} 0 -120 0 0 {name=p13 lab=VDD}
C {devices/iopin.sym} 0 120 0 0 {name=p14 lab=GND}
C {devices/ipin.sym} -130 -40 0 0 {name=p15 lab=REF}
C {devices/ipin.sym} 1670 800 0 0 {name=p16 lab=RESETB}
C {devices/ipin.sym} 1670 840 0 0 {name=p17 lab=NSEL0}
C {devices/ipin.sym} 1670 880 0 0 {name=p18 lab=NSEL1}
C {devices/ipin.sym} 1670 920 0 0 {name=p19 lab=NSEL2}
C {devices/ipin.sym} 1670 960 0 0 {name=p20 lab=NSEL3}
C {devices/ipin.sym} 1670 1000 0 0 {name=p21 lab=NSEL4}
C {devices/ipin.sym} 1670 1040 0 0 {name=p22 lab=NSEL5}
C {devices/opin.sym} 1930 0 0 0 {name=p23 lab=CLK}
C {devices/title.sym} -200 1400 0 0 {name=l1 author="2AM Logic (issue #28, sky130 PLL top-level integration)"}
