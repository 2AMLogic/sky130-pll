v {xschem version=3.4.7 file_version=1.2
* tb_jitter_floor.sch -- period-jitter measurement-floor negative control (issue #178)
*
* DELIBERATELY NOT A PLL. The whole DUT is one ideal pulse voltage source and
* one load resistor: v(CLK) is a trapezoid of exactly constant period, so its
* TRUE period jitter is zero by construction. Whatever period jitter
* sim/harness/measure.py reports for it is therefore the measurement
* pipeline's own resolution floor at the dump grid the manifest declares --
* the quantity issue #178 exists to put a number on, so that
* sim/pll-lock-mc/records/20260924-222341-a9375a5.md's measured 1.584% /
* 1.851% / 3.073% RMS figures against ratified row 9's 1.0% bound can be read
* against a measured floor instead of an unquantified one.
*
* Why there is no sky130 device here at all: a control has to isolate the
* thing under test. The thing under test is the harness's own
* `linearize` -> `wrdata` -> `edge_times` -> `period_jitter` path, not a
* circuit, so anything that could itself jitter is removed. The sky130 .lib
* include below is kept anyway, unused, for two reasons: the harness's
* per-point corner substitution (`corner_pattern`) has something real to
* patch, and the record this testbench mints carries the same PDK/model/
* simulator environment provenance every other record under sim/ carries.
*
* No `.tran` card here on purpose -- sim/harness/measure.py injects the
* transient window, the `linearize` onto the manifest's `tran_step` grid, the
* `wrdata` dump and the completion marker from sim/jitter-floor/testbench/
* tb.json's own `measure` block, exactly as it does for every other
* measurement campaign in this repo (see sim/pll-lock/testbench/
* tb_pll_lock.sch's identical note). That is what makes the dump grid a
* manifest knob -- and this campaign's whole subject is that knob.
*
* The VCLK card below is this campaign's VARIANT knob. `pulse(0 1.8 0 TR TF
* PW PER)`: PER is the exactly-constant period, TR/TF the transition time,
* and PW = PER/2 - TR keeps the 50% threshold crossings exactly half a period
* apart (SPICE measures PW between the end of the rise and the start of the
* fall). tb.json's `methodology_note` lists the variant family and which
* record each variant produced; this file holds one variant at a time, and
* each record's own committed corners/<record-id>/*.spice is the
* authoritative statement of what that record ran.
*
* Committed state: variant A3 -- PER = 3.9170 ns (the 255.3 MHz post-lock
* output frequency trial 5 of the Monte Carlo record measured), TR = TF =
* 20 ps (a transition far below the 200 ps dump grid, i.e. an edge the grid
* cannot resolve).
*
* Provenance: schematic-capture convention (label-based wiring, one lab_pin
* per net, zero drawn wire segments) matches sim/pll-lock/testbench/
* tb_pll_lock.sch; written fresh for issue #178, no external source netlist.
}
G {}
V {}
S {}
E {}
C {devices/vsource.sym} 0 0 0 0 {name=VCLK value="pulse(0 1.8 0 20p 20p 1.9385n 3.9170n)" savecurrent=false}
C {devices/lab_pin.sym} 0 -30 0 0 {name=p1 sig_type=std_logic lab=CLK}
C {devices/gnd.sym} 0 30 0 0 {name=l1 lab=GND}
C {devices/res.sym} 300 0 0 0 {name=R1 value=1k}
C {devices/lab_pin.sym} 300 -30 0 0 {name=p2 sig_type=std_logic lab=CLK}
C {devices/gnd.sym} 300 30 0 0 {name=l2 lab=GND}
C {devices/code.sym} 600 100 0 0 {name=MODELS
only_toplevel=true
format="tcleval( @value )"
value="
** sky130 PDK model include (tt corner) -- patched per-point by sim/harness.
** No device in this testbench uses it: it is here so the harness's own
** corner substitution and this record's environment provenance are the same
** as every other campaign's. See this file's header comment.
.lib $::SKYWATER_MODELS/sky130.lib.spice tt
** No .tran/.print card here on purpose -- sim/harness/measure.py injects the
** analysis from this manifest's own measure block.
"
spice_ignore=false}
C {devices/title.sym} -200 300 0 0 {name=l3 author="2AM Logic (issue #178, period-jitter measurement-floor negative control)"}
