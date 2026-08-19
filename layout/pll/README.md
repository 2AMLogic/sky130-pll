# layout/pll/ — the PLL layout

Issue #16's deliverable: a **device-level layout of the closed-loop PLL
schematic**, drawn headlessly from `design/top/netlist/top.spice` by
`layout/bin/run-pll-layout-flow.sh` and checked in as an append-only
evidence record under `reports/<record-id>/`.

**Read the current record's `record.md` first** — it is the actual pass/fail
evidence this issue delivers, not this file. `reports/LATEST` names it.
The layout stream itself is `reports/<record-id>/pll_top.gds`.

```bash
layout/bin/setup-venv.sh            # once, or after bumping requirements.txt
layout/bin/run-pll-layout-flow.sh   # ~30 s; writes a fresh record
```

## What it is

Every device the schematic declares is physically drawn, at the schematic's
own W/L, and the four blocks are composed into one `pll_top` cell:

| Block | What is drawn |
| --- | --- |
| `pfd_cp` | 59 core-flavor MOS devices in matched arrays grouped by `(flavor, W, L)`, plus the bias resistor |
| `loop_filter` | 2 poly resistors, 3 MiM capacitors |
| `vco_ring5` | 26 core-flavor MOS devices in matched arrays |
| `divider_intN` | the schematic's 29 `sky130_fd_sc_hd` cells, taken from the PDK's own library GDS, abutted in one standard-cell row |

The device set is **derived, not declared**: `layout/bin/pll_layout.py` parses
the schematic netlist at build time and every drawn primitive exists because a
device card asked for it. `klt extract` then reads the drawn stream back into
a netlist with no knowledge of the plan that produced it, and the record
asserts the two multisets are equal — per block, on `(class, W, L)` for MOS
devices and on extracted value for each passive. `layout/tests/
test_pll_layout_plan.py` covers the derivation half with no PDK and no `klt`,
so it runs in `npm run check:ci`.

Devices are sky130 1.8 V core devices throughout (`sky130_fd_pr__nfet_01v8` /
`pfet_01v8`), per DR-001 — asserted by both the record and the unit tests, so
a 3.3 V-class device carried over from the gf180-pll port cannot appear
silently.

## What it is not

Stated plainly, because these are the gaps a reader of "a PLL layout exists"
would otherwise have to discover for themselves:

- **Not routed.** No inter-device interconnect is drawn. The full schematic
  topology *is* recorded — machine-derived — in each record's `plan.json`
  (every group member carries its schematic device name and its port-to-net
  mapping), and the record reports how many nets that is per block. But the
  GDS carries no wires. The one router available (`klt gen-compose`'s
  point-to-point router) draws shorts on this design; see "Friction" below
  and each record's routing spot-check for the evidence.
- **Not DRC-clean.** Every violation is one instance of a single documented
  `klt gen` limitation (see "Friction"), one per minimum-gate-length device.
  The record asserts exactly that, so a *new* violation class appearing is a
  FAIL — but "clean" is issue #17's job, not this one's.
- **Not LVS-compared.** With no routing there is no topology in the stream to
  compare, so no LVS run is attempted rather than reporting a foregone
  mismatch. LVS closure is issue #18.
- **Not a floorplan anyone optimized.** Groups are shelf-packed and blocks
  are placed in a row; area utilization is poor and no matching, symmetry, or
  noise-isolation intent beyond `klt gen`'s own matched-array topology is
  expressed. A hand-considered floorplan is future work.
- **Not a verified circuit.** Nothing here is a claim against
  `spec/target-spec.md`, and no simulation was run from this layout (PEX is
  issue #21).

## Friction: `klt` gaps found drawing this

Per the root `CLAUDE.md` friction protocol, every gap was checked against
[`2AMLogic/klayout-tools`](https://github.com/2AMLogic/klayout-tools) first
and either filed there (generic tool-gap description only — tool behaviour,
none of this repo's design or spec content) or cross-confirmed where it was
already tracked.

Filed here:

| Gap | Filed | How this flow copes |
| --- | --- | --- |
| MOS generators cannot draw a DRC-clean device at a PDK's minimum gate length: the unit device's source/drain local-metal pads abut the gate, so their spacing equals the gate length, below the metal min-spacing rule | [klayout-tools#1187](https://github.com/2AMLogic/klayout-tools/issues/1187) | Draws them anyway (the schematic's minimum-length devices are real); the record asserts the resulting violations are exactly one per such device and of no other rule class, so a *new* violation class is a FAIL |
| `connectivity[]` cannot be declared without also requesting metal — there is no "record the intended topology, draw nothing" mode | [klayout-tools#1188](https://github.com/2AMLogic/klayout-tools/issues/1188) | The unrouted request omits `connectivity[]`; the declared topology is written to the flow's own `plan.json` instead |
| `gen-compose` cannot consume a cell it did not generate — its own response is not a valid block input (no `generator`, no `ports[]`), so hierarchical composition and PDK library cells need a hand-forged `generator_report` | [klayout-tools#1189](https://github.com/2AMLogic/klayout-tools/issues/1189) | Synthesizes the inline block report for the top level and for library cells |

Already tracked upstream — cross-confirmed on
[klayout-tools#953](https://github.com/2AMLogic/klayout-tools/issues/953)
rather than re-filed, since every one of them is **already fixed on the
tool's `main`** and reaches this repo only because `layout/requirements.txt`
pins the PyPI release (`klayout-tools==0.2.0`), which is far behind it:

| Gap | Tracked as | How this flow copes |
| --- | --- | --- |
| `gen-compose`'s router never checks a route against another route, so routes drawn inside one block short each other — extraction reads every routed net back as one merged node | [#1057](https://github.com/2AMLogic/klayout-tools/issues/1057) | Ships the unrouted stream; keeps the routed build as a spot-check under `route-spot-check/` so the claim is evidenced, not asserted |
| The router is two-pin only, so every shared rail or fanout net is unroutable | [#1073](https://github.com/2AMLogic/klayout-tools/issues/1073) | 53 of the 60 declared nets are bundles; all are recorded in `plan.json` rather than drawn |
| A `klt draw` response is not accepted as a `gen-compose` block | [#1059](https://github.com/2AMLogic/klayout-tools/issues/1059) | Same hand-forged inline report as for library cells |
| No MiM-capacitor generator, although the curated extraction deck recognises the device | [#1117](https://github.com/2AMLogic/klayout-tools/issues/1117) | Draws the plates with `klt draw` on the two layers the deck keys off; the record cross-checks each extracted capacitance against the schematic's own W x L |
| No block orientation in `gen-compose`'s placement, so standard-cell rows cannot be mirrored | [#1166](https://github.com/2AMLogic/klayout-tools/issues/1166) | Places the divider's cells in one unmirrored row, so no power rail ever abuts its opposite |

**The pin is the binding constraint here, not the tool.** Five of the eight
gaps above are already fixed upstream. Whether this repo should move
`layout/requirements.txt` off the PyPI release — and what that costs in
reproducibility, which is why it moved *to* a version pin in the first place
(see `layout/requirements.txt`'s own header) — is its own decision, tracked
in #46; it is deliberately not made inside this issue.

## Directory layout

```
layout/pll/
  README.md                  # this file
  reports/
    LATEST                   # plain-text pointer to the newest record id
    <record-id>/             # <YYYYMMDD-HHMMSS>-<short-git-sha>, one per run
      record.md              # verdicts + the schematic-vs-extracted tables (read first)
      plan.json              # the schematic-derived plan: device set + full port/net map
      build.json             # placement/composition summary
      pll_top.gds            # the layout
      pll_<block>.gds        # per-block composed cells
      <group>.gds            # per-group `klt gen`/`klt draw` primitives
      gen.<group>.json       # each generator's own response envelope
      compose.<block>.request.json / .response.json
      drc.json, extract.json, extract.<cell>.json, *.extract.spice
      cells.top.json, cells.<block>.json
      renders/overview.png   # `klt render` all-layer overview
      report.md              # `klt report --format github-summary` rendering
      route-spot-check/      # the same build with the router enabled (GDS deleted)
```

`<record-id>` and the `dirty` flag follow the same convention as
`layout/trivial-cell/reports/` and `sim/` — see `layout/README.md`.
