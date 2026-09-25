v {xschem version=3.4.7 file_version=1.2
* tb_integrator_floor.sch -- ngspice integrator-error null control on the real
* VCO (issue #202)
*
* The DUT is design/vco/vco_ring5.sym -- the same ring sim/pll-lock-mc's
* closed loop is built on -- driven OPEN-LOOP from an ideal DC control
* voltage and an ideal supply. Nothing in this netlist varies with time
* except the ring itself, and a transient analysis carries no device noise,
* so the ring's true period is exactly constant: its true period jitter is
* zero by construction. Whatever period jitter sim/harness/measure.py
* reports for v(CLK) is therefore error the SIMULATION added -- the
* timestep controller's local-truncation error on each edge plus the dump
* grid's resolution floor sim/jitter-floor already measured -- not a
* property of the design.
*
* Why this control, and not sim/jitter-floor's: sim/jitter-floor's DUT is an
* ideal pulse source, whose edges are placed by the source's own breakpoints.
* A ring oscillator's edges are placed by the integrator, so an integrator
* error that a pulse source can never show is exactly the one a
* free-running ring shows. Issue #202 asked for design work on the premise
* that sim/pll-lock-mc's 1.5-3.1% figures are the circuit's; this is the
* control that tests that premise before any design is changed.
*
* V2 (the control voltage) is fixed at 0.86 V: the tt/125 C/1.80 V control
* voltage at which this ring runs at ~250 MHz, the operating point
* sim/pll-lock-mc's Monte Carlo base point locks at. It is a fixed operating
* point, not a sweep.
*
* No `.tran` card here on purpose -- sim/harness/measure.py injects the
* transient window, the optional `.options` card (manifest `measure.options`,
* the knob this experiment exists to exercise), the `linearize`, the `wrdata`
* dump and the completion marker from tb.json's own `measure` block, exactly
* as it does for sim/pll-lock-mc.
*
* Startup kick: RING0 is forced low by a `.ic` card in tb.json, the same
* nudge sim/pll-lock-mc uses; the ring's own loop gain carries it away from
* the initial state.
*
* Provenance: a copy of sim/vco/testbench/tb_vco.sch (issue #52) with V2
* fixed rather than swept; label-based wiring convention unchanged.
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
C {devices/vsource.sym} 800 0 0 0 {name=V2 value=0.86 savecurrent=false}
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
C {devices/title.sym} -200 500 0 0 {name=l3 author="2AM Logic (issue #202, integrator-error null control on design/vco)"}
