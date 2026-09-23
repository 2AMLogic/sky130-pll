v {xschem version=3.4.7 file_version=1.2
* tb_vco_pushing.sch -- VCO frequency-vs-VDD supply-pushing testbench (issue #165)
*
* Sibling of sim/vco/testbench/tb_vco.sch: same DUT (design/vco/vco_ring5.sym,
* the standalone current-starved 5-stage ring VCO, issue #24), same open-loop
* harness, same measurement layer. The one difference is which axis is the
* measured independent variable.
*
*   sim/vco            VDD fixed per PVT point, VCTRL swept  -> Kvco (MHz/V)
*   sim/vco-supply-pushing (this)  VCTRL fixed, VDD swept    -> pushing (%/V)
*
* VCTRL is held at a small set of FIXED operating points inside the
* 0.8-1.6 V free-running span sim/vco/records/20260904-163130-f3ae976.md
* already characterizes; at each of those fixed points the supply is the
* swept quantity, taken from the corner runner's own supply axis
* (spec/target-spec.md row 1's ratified 1.80 V +/- 10 % range: 1.62, 1.80,
* 1.98 V). V1's DC value is what sim/harness rewrites per PVT point (see the
* manifest's `supply_pattern`); V2's DC value is rewritten per swept VCTRL
* point inside a single ngspice invocation (see the manifest's
* `measure.sweep` block and sim/harness/measure.py).
*
* Why this testbench exists: spec/decision-records/DR-006-statistical-rows-
* ratification.md leaves spec row 13 (supply sensitivity) DRAFT by explicit
* decision, and names, as the first of two prerequisites for its Budget 1
* (the AC supply-ripple limit), "a VCO supply-pushing campaign on sky130
* (frequency vs. VDD at fixed VCTRL, across the ratified PVT grid) to
* replace the borrowed 1.67x ratio". No manifest in this repo produced that
* curve before: sim/vco's own manifest sweeps VCTRL only. This testbench
* produces it. It ratifies nothing -- per CLAUDE.md, ratification is a
* separate decision-record act, and DR-006 itself is merged and not edited
* by the issue that added this file.
*
* Startup kick: identical to tb_vco.sch's, and for the same reason -- a ring
* oscillator's DC operating point is the (unstable) all-stages-at-midrail
* equilibrium, and a noiseless simulator can sit on it indefinitely. Each
* swept point runs with `uic` after forcing RING0 low via a `.ic` card (see
* tb.json's `measure.ic`). Not a design change: the ring's own loop gain is
* what carries it away from the initial state.
*
* Threshold tracking (load-bearing for THIS measurement in particular): the
* reducer compares v(clk) against 0.5 * the point's OWN supply, not against
* a fixed 0.9 V (sim/harness/measure.py's `extract_edges`, `supply_v`
* argument). A pushing measurement varies exactly that rail, so a
* nominal-pinned threshold would fold a supply-dependent measurement
* artefact straight into the reported %/V slope.
*
* Provenance: adapted from sim/vco/testbench/tb_vco.sch (this repo, issue
* #52) -- same label-based wiring convention, same instance names, same
* MODELS code block; the VCTRL source's default value and the commentary are
* what differ. No external source netlist.
}
G {}
V {}
S {}
E {}
C {design/vco/vco_ring5.sym} 0 0 0 0 {name=XXVCO}
C {devices/lab_pin.sym} 0 -80 0 0 {name=p1 sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 0 80 0 0 {name=p2 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -130 0 0 0 {name=p3 sig_type=std_logic lab=VCTRL}
C {devices/lab_pin.sym} 130 0 0 0 {name=p4 sig_type=std_logic lab=CLK}
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
"
spice_ignore=false}
C {devices/title.sym} -200 500 0 0 {name=l3 author="2AM Logic (issue #165, sky130 VCO frequency-vs-VDD supply-pushing characterization)"}
