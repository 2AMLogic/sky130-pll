"""PVT corner harness for sky130-pll.

Stdlib only, no virtualenv required (matches 2AMLogic/gf180-pll's
sim/run_corners.py convention -- source commit
3e3814c11ce6f0781ecfbefb0d109981c4e5eb21). See sim/README.md for the
evidence-record schema every run produces, and sim/harness/README.md for the
testbench manifest format.

This is deliberately scoped down from gf180-pll's own sim/harness/ (which
carries PLL-specific derived-measurement modules, e.g. lock detection and
jitter reduction): sky130-pll has no PLL schematic yet (issue #2 is
plumbing-only, unblocked of spec ratification per CLAUDE.md), so this harness
covers PDK resolution, corner-matrix construction, netlist patching + ngspice
execution, and append-only evidence-record rendering -- the generic machinery
every future campaign will build on. Measurement-specific reduction (lock
criteria, jitter, etc.) is added by later issues once there is a PLL netlist
to measure.
"""
