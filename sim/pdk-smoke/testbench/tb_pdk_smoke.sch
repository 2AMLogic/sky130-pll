v {xschem version=3.4.7 file_version=1.2
* tb_pdk_smoke.sch -- environment-bootstrap smoke test (issue #2)
*
* Throwaway circuit only: a resistor divider built from two sky130 generic
* poly resistor primitives (sky130_fd_pr__res_generic_po), driven by a fixed
* DC source. This exercises xschem netlisting, the sim/harness PVT corner
* substitution, and ngspice model resolution against the sky130 PDK -- it
* carries no PLL design content, spec values, or measurement data. The 1.8 V
* source value is an arbitrary smoke-test bias, not a ratified supply (the
* supply flavor is an open question pending #1 -- see spec/target-spec.md).
*
* Provenance: adapted from 2AMLogic/sky130-bandgap's design/smoke_test.sch
* (source commit 7b88134ba17cd6536e389f45b3e8a512d6245b15) per this repo's
* CLAUDE.md harness-bootstrap rule -- same trivial circuit, moved under
* sim/pdk-smoke/testbench/ (this repo's design/ is reserved for the PLL
* schematic itself) and re-used as sim/harness's own corner-sweep selftest
* target (sim/harness/README.md).
}
G {}
V {}
S {}
E {}
N 0 30 300 30 {lab=VDD}
N 300 -30 300 -130 {lab=OUT}
C {devices/vsource.sym} 0 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/gnd.sym} 0 -30 0 0 {name=l1 lab=GND}
C {sky130_fd_pr/res_generic_po.sym} 300 0 0 0 {name=R1 W=1 L=1 model=res_generic_po spiceprefix=X mult=1}
C {sky130_fd_pr/res_generic_po.sym} 300 -160 0 0 {name=R2 W=1 L=1 model=res_generic_po spiceprefix=X mult=1}
C {devices/gnd.sym} 300 -190 0 0 {name=l2 lab=GND}
C {devices/code.sym} 500 100 0 0 {name=MODELS
only_toplevel=true
format="tcleval( @value )"
value="
** sky130 PDK model include (tt corner) -- patched per-point by sim/harness
.lib $::SKYWATER_MODELS/sky130.lib.spice tt
.op
"
spice_ignore=false}
C {devices/title.sym} 0 -260 0 0 {name=l3 author="2AM Logic (issue #2 harness smoke test)"}
