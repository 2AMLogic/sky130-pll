v {xschem version=3.4.7 file_version=1.2
* tb_pll.sch -- closed-loop PLL testbench (issue #23)
*
* Instantiates design/top/top.sym (the four-block closed-loop PLL: PFD +
* charge pump, loop filter, VCO, divider -- issue #28) as a single
* hierarchical block, drives it with a fixed 1.8 V supply, a reference clock,
* and a power-on reset, and straps NSEL[5:0] to a fixed divide ratio. This is
* the first PLL-specific testbench under sim/ -- everything under
* sim/pdk-smoke/ instead exercises a throwaway resistor divider, not the PLL
* (see sim/pdk-smoke/testbench/tb.json).
*
* Per this repo's CLAUDE.md ("Verification is the product" / "no claim
* without a testbench"), running this through sim/run_corners.py produces a
* harness-plumbing record only: does xschem+ngspice+sky130 netlist and
* simulate this closed-loop DUT to completion across a real PVT sweep? It is
* NOT a lock-time, output-frequency, or jitter claim against
* spec/target-spec.md -- none of that file's numeric rows are ratified yet
* (pending #1), and the .tran window below (200 ns, two reference periods) is
* far short of a cold-start lock transient for any realistic loop bandwidth.
* A future PVT/lock-time/jitter campaign extends this testbench (or adds a
* sibling one) once those spec rows are ratified.
*
* NSEL[5:0] strapping: NSEL[5:0] = 011000 (binary, NSEL5 is the MSB per
* design/divider/DESIGN.md's "NSEL[5:0] (LSB NSEL0, MSB NSEL5)" convention)
* = N-1 = 24, i.e. N = 25. Chosen so the target closed-loop output
* (N * Fref = 25 * 10 MHz = 250 MHz) lands inside vco_ring5's own
* demonstrated free-running tuning range (design/vco/DESIGN.md's sanity-check
* table: ~145 MHz at VCTRL=0.8 V to ~1.09 GHz at VCTRL=1.6 V) -- an
* arbitrary-but-plausible operating point for a plumbing smoke test, not a
* value derived from any ratified spec row (row 4's N = 4-64 range, row 3's
* 1-25 MHz reference range).
*
* Reference (V2): 10 MHz, ~48% duty CMOS pulse (row 3's 1-25 MHz / 30-70%
* duty DRAFT target). Reset (V3): power-on RESETB pwl, low from t=0 (divider
* held in reset) then rising to VDD at t=6 ns (matching
* design/divider/DESIGN.md's "after reset deassertion loads NSEL[5:0]"
* behavior) -- long enough to guarantee the divider's registers see at least
* one full RESETB-low interval before the first REF edge.
*
* Provenance: schematic-capture convention (label-based wiring, one
* ipin/opin/iopin/lab_pin per net, zero drawn wire segments) matches
* design/top/top.sch's own convention and this repo's sim/pdk-smoke/testbench/
* tb_pdk_smoke.sch harness-bootstrap precedent; written fresh for this issue
* (no external source netlist).
}
G {}
V {}
S {}
E {}
C {design/top/top.sym} 0 0 0 0 {name=XXTOP}
C {devices/lab_pin.sym} 0 -240 0 0 {name=p1 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 0 240 0 0 {name=p2 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 -180 0 0 {name=p3 sig_type=std_logic lab=REF}
C {devices/lab_pin.sym} -130 -140 0 0 {name=p4 sig_type=std_logic lab=RESETB}
C {devices/lab_pin.sym} -130 -100 0 0 {name=p5 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 -60 0 0 {name=p6 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 -20 0 0 {name=p7 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 20 0 0 {name=p8 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 60 0 0 {name=p9 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -130 100 0 0 {name=p10 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 130 0 0 0 {name=p11 sig_type=std_logic lab=CLK}
C {devices/vsource.sym} 600 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/lab_pin.sym} 600 -30 0 0 {name=p12 sig_type=std_logic lab=VDD}
C {devices/gnd.sym} 600 30 0 0 {name=l1 lab=GND}
C {devices/vsource.sym} 800 0 0 0 {name=V2 value="pulse(0 1.8 0 1n 1n 48n 100n)" savecurrent=false}
C {devices/lab_pin.sym} 800 -30 0 0 {name=p13 sig_type=std_logic lab=REF}
C {devices/gnd.sym} 800 30 0 0 {name=l2 lab=GND}
C {devices/vsource.sym} 1000 0 0 0 {name=V3 value="pwl(0 0 5n 0 6n 1.8)" savecurrent=false}
C {devices/lab_pin.sym} 1000 -30 0 0 {name=p14 sig_type=std_logic lab=RESETB}
C {devices/gnd.sym} 1000 30 0 0 {name=l3 lab=GND}
C {devices/code.sym} 1300 300 0 0 {name=MODELS
only_toplevel=true
format="tcleval( @value )"
value="
** sky130 PDK model include (tt corner) -- patched per-point by sim/harness
.lib $::SKYWATER_MODELS/sky130.lib.spice tt
.tran 50p 200n
"
spice_ignore=false}
C {devices/title.sym} -200 500 0 0 {name=l4 author="2AM Logic (issue #23, sky130 PLL closed-loop testbench)"}
