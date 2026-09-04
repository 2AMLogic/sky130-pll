v {xschem version=3.4.7 file_version=1.2
* tb_loop_ac.sch -- linearized open-loop AC testbench for the PLL loop
* dynamics (issue #52): loop bandwidth (spec/target-spec.md row 6) and phase
* margin (row 7).
*
* Why this testbench exists. sim/harness/measure.py deliberately does not
* measure loop bandwidth or phase margin, and says so in its own module
* docstring: they are open-loop quantities, and pulling them out of a closed-
* loop transient means either breaking the loop or fitting a step response
* whose accuracy is dominated by the fit's assumptions. This is the separate
* AC/linearized-model testbench that docstring points at. It replaces
* design/loop-filter/DESIGN.md's hand-calculated f_c and phase margin -- which
* that file explicitly labels 'a hand calculation per the equations above, not
* a simulation result', at one design point, at no stated corner -- with a
* real, PVT-swept sim/ record.
*
* The model. A type-II charge-pump PLL's open-loop transfer function is
*
*   T(s) = (Icp/2pi) * Z(s) * (2pi*Kvco/s) / N = (Icp*Kvco/N) * Z(s)/s
*
* Z(s) -- the loop filter's transimpedance from charge-pump current to VCTRL
* -- is the only frequency-dependent term, and it is simulated for real here:
* the DUT is design/loop-filter/loop_filter.sym, the same sky130 R/C network
* the design uses, so process corner and temperature move its poles and its
* zero exactly as the device models say. Everything else collapses into one
* scalar A = Icp*Kvco/N, which the harness applies as the AC magnitude of I1
* and sweeps over a set of documented design points (see tb.json's
* ac.loop_gain list). That is why there is no VCO, no charge pump and no
* divider in this schematic: their contribution to the open-loop transfer
* function is a pure scalar, and their frequency-shaping contribution is
* outside the continuous-time approximation this analysis makes.
*
* The netlist elements, one at a time:
*   I1    -- AC current source injecting into CP. Its acmag is rewritten per
*            swept loop-gain point by sim/harness/acmeasure.py, so v(CP) is
*            A*Z(s). Oriented GND -> CP so positive current enters CP.
*   XLF   -- the loop filter itself (CP in, VCTRL out, GND).
*   GINT  -- the VCO's phase integrator, ideal: a 1 A/V VCCS driven by
*            v(VCTRL), pushing into CINT. Oriented GND -> PHI so the loop's
*            own inverting summation is NOT folded in, which is what makes
*            phase margin '180 deg + arg T' in the usual convention.
*   CINT  -- 1 F, so v(PHI) = v(VCTRL)/s exactly.
*   RLEAK -- 1 Tohm from PHI to GND. Purely a DC-solvability shunt for the
*            operating point that precedes the AC analysis; it puts a pole at
*            about 1.6e-13 Hz, some twelve decades below the swept band, so it
*            cannot influence any reported number.
*
* v(PHI) is therefore the dimensionless open-loop gain T(j*omega): unity gain
* is 0 dB, and the low-frequency asymptote sits at -180 degrees because the
* loop has two integrators (the filter's C1 and this VCO phase integrator).
*
* What this testbench does NOT claim. It does not simulate the charge pump's
* or the VCO's own small-signal behaviour, their per-corner gain variation
* (that is sim/vco's record, which is where the swept Kvco values come from),
* charge-pump non-idealities (finite output impedance, UP/DN mismatch, dead
* zone), or any sampled-loop correction beyond the continuous-time
* approximation. It ratifies nothing -- per CLAUDE.md, ratification is a
* separate decision-record act argued on its own merits.
*
* Provenance: schematic-capture convention (label-based wiring, one
* lab_pin/gnd per net, zero drawn wire segments) matches
* sim/vco/testbench/tb_vco.sch's own convention; written fresh for this issue
* (no external source netlist).
}
G {}
V {}
S {}
E {}
C {design/loop-filter/loop_filter.sym} 0 0 0 0 {name=XLF}
C {devices/lab_pin.sym} -130 0 0 0 {name=p1 sig_type=std_logic lab=CP}
C {devices/gnd.sym} 0 80 0 0 {name=l1 lab=GND}
C {devices/lab_pin.sym} 130 0 0 0 {name=p2 sig_type=std_logic lab=VCTRL}
C {devices/isource.sym} 400 0 0 0 {name=I1 value="dc 0 ac 1"}
C {devices/gnd.sym} 400 -30 0 0 {name=l2 lab=GND}
C {devices/lab_pin.sym} 400 30 0 0 {name=p3 sig_type=std_logic lab=CP}
C {devices/vccs.sym} 700 0 0 0 {name=GINT value=1}
C {devices/gnd.sym} 700 -30 0 0 {name=l3 lab=GND}
C {devices/lab_pin.sym} 700 30 0 0 {name=p4 sig_type=std_logic lab=PHI}
C {devices/lab_pin.sym} 660 -20 0 0 {name=p5 sig_type=std_logic lab=VCTRL}
C {devices/gnd.sym} 660 20 0 0 {name=l4 lab=GND}
C {devices/capa.sym} 900 0 0 0 {name=CINT m=1 value=1 footprint=1206 device="ceramic capacitor"}
C {devices/lab_pin.sym} 900 -30 0 0 {name=p6 sig_type=std_logic lab=PHI}
C {devices/gnd.sym} 900 30 0 0 {name=l5 lab=GND}
C {devices/res.sym} 1050 0 0 0 {name=RLEAK m=1 value=1T footprint=1206 device=resistor}
C {devices/lab_pin.sym} 1050 -30 0 0 {name=p7 sig_type=std_logic lab=PHI}
C {devices/gnd.sym} 1050 30 0 0 {name=l6 lab=GND}
C {devices/code.sym} 1400 300 0 0 {name=MODELS
only_toplevel=true
format="tcleval( @value )"
value="
** sky130 PDK model include (tt corner) -- patched per-point by sim/harness
.lib $::SKYWATER_MODELS/sky130.lib.spice tt
"
spice_ignore=false}
C {devices/title.sym} -200 500 0 0 {name=l7 author="2AM Logic (issue #52, linearized open-loop PLL loop-dynamics AC testbench)"}
