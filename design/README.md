# design/ — schematic capture convention

This directory holds the PLL's own schematics (xschem), symbols, generated
netlists, and per-block design-rationale notes — the design content itself,
as distinct from `sim/` (evidence records) and `layout/` (DRC/LVS flow).

No convention existed here before issue #24 (this directory previously held
only a `.gitkeep`). This file documents the convention that issue set, so
the sibling block sub-issues of #14 (PFD/charge pump, loop filter, divider)
and the eventual integration sub-issue follow the same shape.

## Directory / naming convention

One directory per PLL sub-block, named for the block, kebab/lowercase:

```
design/
  README.md                  # this file
  <block>/
    <block>.sch               # top xschem schematic for the block
    <block>.sym                # xschem symbol, for hierarchical reuse by
                                 # the integration schematic
    DESIGN.md                   # topology choice, sizing rationale, and
                                 # the design targets this block is built
                                 # toward (not verified results — those are
                                 # sim/ evidence, produced by a later
                                 # testbench issue)
    netlist/
      <block>.spice              # ngspice-compatible netlist snapshot,
                                   # generated from <block>.sch and
                                   # committed (regeneration command
                                   # documented in the block's DESIGN.md)
```

- **`<block>`** — a short slug for the sub-block. First instance:
  `vco` (issue #24, the ring-oscillator VCO core). Sibling blocks (PFD/charge
  pump, loop filter, feedback divider) get their own `<block>/` directory
  when their sub-issue lands. `top` (issue #28) is the one exception to
  "sub-block": it is the integration schematic that hierarchically
  instantiates all four sibling blocks into the closed PLL loop, following
  the same internal file shape (`top.sch`/`top.sym`/`DESIGN.md`/
  `netlist/top.spice`) for consistency, even though it isn't itself a
  sub-block.
- **`<block>.sch` / `<block>.sym`** — hand-authored (or, once available,
  xschem-generated) schematic and symbol pair. The symbol's pin order must
  match the schematic's own `ipin`/`opin`/`iopin` declaration order, so
  `@pinlist` nets correctly when the symbol is instantiated from a parent
  (integration) schematic.
- **`netlist/<block>.spice`** — a **connectivity snapshot**, not a
  simulation-ready testbench: it nets out the block's own devices against
  sky130 primitives (`sky130_fd_pr__nfet_01v8` / `pfet_01v8` etc., per the
  ratified 1.8 V core supply flavor, `DR-001`) but carries no supply
  sources, no `.lib` model include, and no analysis statements — those are
  added by whatever testbench (`sim/<experiment-slug>/testbench/`)
  instantiates the block. Regenerate with:

  ```sh
  source sim/bin/pdk-env.sh
  xschem -n -q -x --rcfile sim/xschemrc design/<block>/<block>.sch \
    -o design/<block>/netlist
  ```

  Unlike `sim/`'s `netlist-snapshots/` (one frozen file per evidence
  record, append-only), `design/<block>/netlist/<block>.spice` is **not**
  append-only — it is the current netlist for the current schematic,
  regenerated and overwritten in place as the schematic changes. The
  append-only, one-per-record convention lives entirely under `sim/` (see
  `sim/README.md`), where a netlist is frozen alongside the evidence it
  produced.

### Regenerating parents after a child changes

`design/top/netlist/top.spice` embeds a copy of every child block's netlist
(`pfd_cp`, `loop_filter`, `vco_ring5`, `divider_intN`). xschem does not
refresh a parent when only a child schematic is saved, so after changing any
child, regenerate every ancestor with the same command (for the top level,
`design/top/top.sch -o design/top/netlist`), and commit the changed snapshots
together. The layout flow reads the top snapshot, so a stale embedded copy
silently changes the device plan and LVS reference.

`python3 signoff/design-snapshot-consistency.py` (part of `npm run check:ci`,
and run by `layout/bin/run-pll-layout-flow.sh` before a record is minted)
compares each embedded block with its standalone snapshot: pin order, device
connections, model names and parameter values, ignoring generated path
comments and formatting. It needs neither xschem nor a PDK. It establishes
snapshot-to-snapshot consistency only; it does not prove that a snapshot
matches its `.sch`, which only regenerating with xschem does.

## Relationship to `sim/`

`design/<block>/<block>.sch` is the DUT a `sim/<experiment-slug>/testbench/`
schematic instantiates (once a testbench exists for that block — none does
yet for `vco`, that is a later issue, see #23). `sim/pdk-smoke` is unrelated
plumbing (harness self-test, not a PLL block) and predates this convention;
its own throwaway testbench circuit intentionally stays under
`sim/pdk-smoke/testbench/`, not `design/`.

## Relationship to `layout/`

`layout/` (klayout-tools DRC/LVS flow) is unrelated at this stage — no block
here has layout yet. When a block gets one, `layout/<block>/` is expected to
mirror this same `<block>` slug for cross-referencing.

## Provenance

Directory shape and the netlist-regeneration command are new with issue #24
(no existing convention to adapt — `design/` held only `.gitkeep` before this
issue). The xschem/ngspice invocation pattern itself (`--rcfile sim/xschemrc`,
`PDK_ROOT`/`PDK` via `sim/bin/pdk-env.sh`) is the one `sim/harness/runner.py`
already established (issue #9, adapted from `2AMLogic/sky130-bandgap`) — reused
here unmodified, not re-derived.
