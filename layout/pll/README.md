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
  GDS carries no wires. The one router available (`klt gen-compose`'s) still
  draws a short on this design, and leaves most nets undrawn — chiefly
  because it cannot route a pin buried inside a matched device array (see
  "Friction" below and each record's routing spot-check for the per-leg
  evidence).
- **DRC-clean (issue #17, 2026-09-05).** Through issue #46's `klt` pin, every
  violation was one instance of a single documented `klt gen` limitation (see
  "Friction") — one `li1.space.1` per minimum-gate-length device, 52 of them.
  Issue #17 bumped the `klt` pin past the upstream fix
  ([klayout-tools#1201](https://github.com/2AMLogic/klayout-tools/pull/1201))
  and the violation is gone: the current record's `drc.json` reports
  `status: "clean"`, zero violations. The record's own DRC check now asserts
  that bar directly, so a *new* violation appearing is a FAIL.
- **Not LVS-clean.** The shipped stream carries no routing, so no `klt lvs`
  run is attempted against it (a foregone mismatch is not evidence). Since
  issue #18, `klt lvs` *is* run against the routed routing-spot-check build
  and its result — a large, honest mismatch, not a "clean" claim — is
  recorded in full; see each record's own LVS (spot-check) section. Full LVS
  closure is still issue #18, blocked on the routing gaps below.
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
| ~~MOS generators cannot draw a DRC-clean device at a PDK's minimum gate length: the unit device's source/drain local-metal pads abut the gate, so their spacing equals the gate length, below the metal min-spacing rule~~ **Fixed upstream** ([klayout-tools#1201](https://github.com/2AMLogic/klayout-tools/pull/1201), merged as `bd5c7f4`) | [klayout-tools#1187](https://github.com/2AMLogic/klayout-tools/issues/1187) (closed) | Issue #17 bumped `layout/requirements.txt`'s `klt` pin past the fix (`klayout-tools==0.4.0`) and re-ran this flow: the pads no longer abut the gate, and the layout's DRC comes back clean of this rule (0 violations, confirmed in the current record) — no workaround needed any more |
| `connectivity[]` cannot be declared without also requesting metal — there is no "record the intended topology, draw nothing" mode | [klayout-tools#1188](https://github.com/2AMLogic/klayout-tools/issues/1188) | The unrouted request omits `connectivity[]`; the declared topology is written to the flow's own `plan.json` instead |
| `gen-compose` cannot consume a cell it did not generate — its own response is not a valid block input (no `generator`, no `ports[]`), so hierarchical composition and PDK library cells need a hand-forged `generator_report` | [klayout-tools#1189](https://github.com/2AMLogic/klayout-tools/issues/1189) | Synthesizes the inline block report for the top level and for library cells |

Filed after the `klt` pin bump (#46), by the router the bump made usable:

| Gap | Filed | How this flow copes |
| --- | --- | --- |
| ~~`gen-compose`'s route-vs-route collision check misses two same-block self-nets: both compose `routed: true` with no warning, and extraction reads them back as one node~~ **Fixed upstream** (klayout-tools PR #1216, merged as `dd41d23f`) | [klayout-tools#1197](https://github.com/2AMLogic/klayout-tools/issues/1197) (closed) | Issue #17's DRC-motivated pin bump (`klayout-tools==0.4.0`) turned out to be a strict descendant of this fix too — a re-run of this design's routing spot-check confirmed 0 shorted nodes, down from 3. Still ships the unrouted stream regardless (most legs remain undrawn — see the routing-channel gap below), and the routed build stays as a spot-check under `route-spot-check/` |

Five further gaps this layout originally hit were **already fixed on the tool's
`main`** and reached this repo only through the PyPI pin
(`klayout-tools==0.2.0`). Issue #46 moved `layout/requirements.txt` to a
git-commit pin that carries all five, each verified working on this design
before the entry was dropped from this table — see
[`../klt-pin-decision.md`](../klt-pin-decision.md) for the decision and the
measurements, and `../requirements.txt`'s header for what the current pin
picks up ([#1057](https://github.com/2AMLogic/klayout-tools/issues/1057)
route-vs-route checking,
[#1073](https://github.com/2AMLogic/klayout-tools/issues/1073) bundle-net
routing, [#1059](https://github.com/2AMLogic/klayout-tools/issues/1059) `klt
draw` composition, [#1117](https://github.com/2AMLogic/klayout-tools/issues/1117)
the `cap_array` MiM generator,
[#1166](https://github.com/2AMLogic/klayout-tools/issues/1166) block
orientation).
[klayout-tools#953](https://github.com/2AMLogic/klayout-tools/issues/953), the
PyPI release-cadence gap those five arrived through, stays cross-confirmed
there rather than re-filed.

**The pin was the binding constraint, and it moved — but the layout is still
unrouted.** Two of the five (#1057, #1073) are what made routing impossible at
all; with them the router now draws 51 legs on this design instead of 7
certified shorts. Issue #18 wired `mos_array`'s `params.gate_contact`
([#492](https://github.com/2AMLogic/klayout-tools/issues/492)) for every
matched device group, closing one of the two "this design's own" gaps named
here previously (bare-poly gate pins are now contacted landing pads,
reachable by the router) — 51 legs became 74. A later `klt` pin bump (issue
#17's DRC-motivated bump past `bd5c7f4`, which turned out to be a strict
descendant of klayout-tools#1197's fix too) eliminated the residual
route-vs-route short described below as a side effect: the same design,
re-measured, drew 62 of 917 legs with **zero** shorted nodes (down from three)
— confirming #1197 no longer needs a dedicated bump, only the structural gap
below remains open for this issue.

What still blocks a routed stream is the dominant remaining failure: the
point-to-point router's inability to route a pin buried inside a matched
device array's own interior (263 of 917 legs at the post-pin-bump
measurement above) — routing that would need an actual channel *inside* the
array, which is a floorplan redesign, not a spacing tweak (a throwaway
experiment raising `GROUP_SPACING_UM`/`BLOCK_SPACING_UM` 2.5x barely moved
the numbers, since that spacing is between *groups*, not between an array's
own internal rows/columns).

Issue #18 also tried a genuine floorplan change here, and it **did not
work** — recorded because the reasoning behind it is plausible enough to be
re-proposed otherwise. `klt gen mos_array` draws every unit's gate contact
facing the array's own +y edge regardless of which internal row it is placed
on, so in the near-square grouping (`factor_rows_cols`) only the array's
*top* row has gates within the router's small edge-margin allowance — every
gate below it is interior by construction. Forcing every matched group into
a single row (`rows=1`, so every unit sits on that one reachable row) should
therefore have helped. The gate-orientation premise is real; the conclusion
was not. Measuring the full 2×2 — all four cells on the same `klt` 0.4.0 /
KLayout 0.30.12 / `open_pdks c6d73a35` pin, so they are directly comparable
— gives legs drawn out of legs attempted:

| `topology` \ packing | near-square grid | `rows=1` |
| --- | --- | --- |
| `common_centroid` (even counts) — **shipped** | **62 / 917** | 55 / 945 |
| `array` (forced, *not* adopted) | 76 / 862 | 74 / 827 |

Read by column, the single-row packing is neutral-to-worse in *both*
topology regimes (62 → 55, and 76 → 74), so its own effect is approximately
zero and slightly negative. An earlier revision of this work reported
"62/917 → 74/827, single-row packing improves routing coverage" — that is
the confounded diagonal of this table: the same change also flipped
`topology` from `common_centroid` to an unconditional `array`, and the
topology knob is where the entire gain came from. Both changes were
withdrawn; the plan keeps the near-square grid, which is independently the
better analog choice (a 1×N row spreads a matched group across the widest
possible span — exactly the linear-gradient distance common-centroid
ordering exists to cancel).

The `topology` gain is real and is deliberately **not** taken. The stream
this flow ships is unrouted, so the routing spot-check is a *diagnostic*,
whereas the device-to-position assignment `topology` controls is a property
of the *shipped* geometry: `common_centroid` is `klt gen mos_array`'s own
documented default and a real centroid-symmetric visiting order that pairs
each instance with its point-reflection through the grid centre, which is
what cancels process-gradient mismatch across the VCO ring stages and the
PFD/CP current mirrors. Spending that to improve a diagnostic number would
be laundering a failing result, which this repo's `CLAUDE.md` forbids — the
routing shortfall stays recorded as a miss instead. Two regression tests in
`layout/tests/test_pll_layout_plan.py` now assert both fields, so neither
can move again as an unremarked side effect.

(The remaining orientation — one column, every gate buried but every
source/drain pad reachable — was measured too and is worse still on this
design: 40 of 978 legs; its declared nets lean on gate connectivity more
than on source/drain, empirically.) None of these floorplan choices closes
the gap — a genuine per-unit interior routing channel is still needed and is
not something this flow's floorplan choices alone can supply. The current
record's routing spot-check tabulates
the router's own reason for every leg it declined, and its LVS (spot-check)
section runs `klt lvs` against that build and records the resulting mismatch
in full.

Two capabilities the bump makes available are deliberately **not yet adopted**,
because adopting either changes drawn geometry and needs its own evidence:
`klt gen cap_array` (#1117) in place of this flow's `klt draw` MiM plates, and
block `orientation` (#1166), which the divider's single row does not need
today.

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
        reference.spice      # schematic netlist, top level's .subckt/.ends uncommented for `klt lvs`
        lvs.request.json, lvs.json   # `klt lvs` request/result against the routed build (issue #18)
```

`<record-id>` and the `dirty` flag follow the same convention as
`layout/trivial-cell/reports/` and `sim/` — see `layout/README.md`.
