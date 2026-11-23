# PLL layout record: 20261121-015858-147252b9

Device-level layout of the closed-loop PLL schematic (`design/top/netlist/top.spice`), drawn by `layout/bin/run-pll-layout-flow.sh` (issue #16). Read this file first; everything else in this directory is the raw `klt` evidence it summarises.

- **Spec row(s)**: none -- none. This flow draws a device-level, *unrouted* floorplan of design/top/netlist/top.spice and checks it against the schematic's own device set (issue #16) -- every record it mints says so itself under 'What this layout is not': no simulation is run from the layout, so it makes no claim against any spec/target-spec.md row. Area (row 18) is deliberately NOT cited: the placed sizes this record reports are an unrouted floorplan's extent, not a block area, and reporting them against a row whose target is 'a budget, not a result' would read as evidence toward an area number this flow cannot yet support. Revisit this declaration when routing closes (issue #18) and an area result becomes meaningful.
- **Supersedes**: `20261106-075813-16557e3` (the newest record when this one was minted; it is kept unedited)

## Overall verdict: PASS

- [x] Every device card in the schematic netlist drew a layout primitive -- pfd_cp: 60 -> 60, loop_filter: 5 -> 5, vco_ring5: 26 -> 26, divider_intN: 42 -> 42, clk_buf: 4 -> 4
- [x] Every MOS device is a sky130 1.8 V core device (DR-001) -- no 3.3 V-class device is drawn -- sky130_fd_pr__nfet_01v8, sky130_fd_pr__pfet_01v8
- [x] `pfd_cp`: the `(class, W, L)` device multiset extracted from the drawn GDS equals the schematic's -- MOS 59, R 1, C 0
- [x] `loop_filter`: the `(class, W, L)` device multiset extracted from the drawn GDS equals the schematic's -- MOS 0, R 2, C 3
- [x] `vco_ring5`: the `(class, W, L)` device multiset extracted from the drawn GDS equals the schematic's -- MOS 26, R 0, C 0
- [x] `clk_buf`: the `(class, W, L)` device multiset extracted from the drawn GDS equals the schematic's -- MOS 4, R 0, C 0
- [x] `divider_intN`: the composed cell instantiates exactly the schematic's 42 standard-cell instances, each from the library cell the schematic names -- pll_divider_intN: 42 instances, 42 distinct library cells placed
- [x] `pll_top` instantiates all 5 block cells -- pll_clk_buf__pll_clk_buf, pll_divider_intN__pll_divider_intN, pll_loop_filter__pll_loop_filter, pll_pfd_cp__pll_pfd_cp, pll_vco_ring5__pll_vco_ring5
- [x] DRC is clean -- zero violations (previously 56 `li1.space.1` violations, one per minimum-gate-length device, traced to klayout-tools#1187 and fixed upstream by klayout-tools#1201) -- status=clean, violation_count=0, rule_counts={}
- [x] Routing-lever table's final row is this run's own tally (re-derived from this run's envelopes and compared field by field) -- all headline fields agree

## What this layout is

A **device-level floorplan**: every device the schematic declares is physically drawn, at the schematic's own W/L, in a matched array grouped by `(flavor, W, L)`, and the five blocks are composed into one `pll_top` cell. The device set is derived from the schematic netlist at build time -- nothing about it is typed in by hand -- which is what makes the device-set checks above reproducible rather than declarative.

![composed PLL layout](renders/overview.png)

(All layers, `klt render`. Left to right in the strip along the top: the divider's standard-cell row; below it the PFD/charge pump's device groups and its 300 um bias resistor; right: the loop filter's three MiM capacitors; far right: the VCO's ring and buffer devices.)

| Block | Cell | Schematic devices | Groups | Placed size (um) |
| --- | --- | --- | --- | --- |
| `pfd_cp` | `pll_pfd_cp` | 60 | 17 | 301.28 x 28.02 |
| `loop_filter` | `pll_loop_filter` | 5 | 5 | 322.4 x 405.4 |
| `vco_ring5` | `pll_vco_ring5` | 26 | 6 | 41.61 x 17.42 |
| `divider_intN` | `pll_divider_intN` | 42 | 42 | 203.78 x 2.72 |
| `clk_buf` | `pll_clk_buf` | 4 | 4 | 17.46 x 25.42 |
| **top** | `pll_top` | 137 | 5 | 705.515 x 451.62 |

## What this layout is not

- **Not routed.** No inter-device interconnect is drawn. The full schematic topology *is* recorded, machine-derived, in `plan.json` (every group member carries its schematic device name and its port-to-net mapping), and 65 nets are declared across the five blocks -- but the composed GDS carries no wires between them. See the routing spot-check below for why.
- **DRC-clean.** 0 violations (see the DRC check above) -- issue #17. Through issue #46's `klt` pin this reported 56 `li1.space.1` violations, one per minimum-gate-length device, traced to a documented `klt gen` limitation (klayout-tools#1187); issue #17 bumped the pin past the upstream fix (klayout-tools#1201) and the violation is gone.
- **Not LVS-clean.** The shipped stream carries no routing, so no `klt lvs` run is attempted against it (a foregone mismatch is not evidence). `klt lvs` *is* run against the routed routing-spot-check build below, and reports a large, honestly-recorded mismatch -- see the spot-check's own LVS section for the counts and why. LVS closure is issue #18.
- **Not a verified circuit.** Nothing here is a claim against `spec/target-spec.md`; no simulation was run from this layout (PEX is issue #21).

## Routing spot-check (why the shipped layout is unrouted)

The same build was re-run with `klt gen-compose`'s router enabled (`route-spot-check/`). Of 65 declared nets it drew 14 in full and 12 in part, leaving 39 with no geometry at all -- 111 of 365 two-pin legs drawn. The router declined the rest, with its own reason per leg:

| Why a leg was not drawn | Legs |
| --- | --- |
| would cross an already-drawn route (the router's own route-vs-route collision check, klayout-tools#1057) | 226 |
| would come closer to an already-drawn route than the resolved deck's own same-layer minimum spacing (the router's spacing-aware collision check, new at `klayout-tools==0.6.0` -- it is why the routed spot-check's own DRC no longer reports `met1.space.1`) | 28 |

**No drawn short:** the routed run's extracted netlist carries no multi-label node, so nothing the router drew merged two declared nets. The shipped stream is still the unrouted one because most nets remain undrawn (see the table above), not because the drawn ones are wrong.

Its DRC reports 4 violations ({'met3.space.1': 4}) against 0 for the unrouted build, and its extraction finds 529 nets against 638 for the unrouted build. Most of that difference is the routing doing its job -- each drawn leg merges two device pads that the unrouted stream counts as two separate nets -- which is why the multi-label node count above, not the net-count delta, is what identifies a short.

Per-block routing outcome from the spot-check:

| Block | Declared nets | Fully routed | Not fully routed |
| --- | --- | --- | --- |
| `pfd_cp` | 35 | 4 | 31 |
| `loop_filter` | 4 | 3 | 1 |
| `vco_ring5` | 21 | 4 | 17 |
| `divider_intN` | 0 | 0 | 0 |
| `clk_buf` | 5 | 3 | 2 |

(The spot-check's own GDS streams are deleted by the flow after its DRC/extract run -- the JSON envelopes are the evidence, and `run-pll-layout-flow.sh` regenerates the streams on demand.)

### LVS (spot-check)

`klt lvs` compared the spot-check's routed `pll_top` against the authored schematic (`reference.spice`, the same netlist `pll_layout.py` derives the plan from, with its top level's `.subckt`/`.ends` uncommented so `klt lvs`'s SPICE reader recognises it -- both sides flattened first, since this flow's composed block names (`pll_pfd_cp`, ...) differ from the schematic's own subcircuit names (`pfd_cp`, ...) and `klt lvs` does not resolve that across un-flattened circuit boundaries).

**Status: `mismatch`, 1489 mismatches** -- nets 0/105 reference nets matched (529 in the layout), devices 0/95 reference devices matched (749 in the layout).

| Mismatch category | Count |
| --- | --- |
| `device.unmatched` | 844 |
| `net.unmatched` | 593 |
| `reference.unresolved_subckt_call` | 42 |
| `device.body_unverified` | 2 |
| `device.geometry_not_compared` | 2 |
| `device.placeholder_value` | 2 |
| `net.supply_fragmented` | 2 |
| `topology` | 1 |
| `topology.flattened` | 1 |

This is the expected shape of the result, not a surprise: only 111 of 365 two-pin legs are drawn (see the table above), so almost every reference net and device is structurally unreachable from the layout side. `klt lvs` is run and its result recorded in full precisely so that claim rests on the tool's own comparison rather than on this record's own leg-reason tally -- per this repo's CLAUDE.md, a miss is recorded as a miss, never rounded up to "clean." Full `klt lvs` closure (issue #18) needs the router's structural gaps above closed first: the order-dependent plane/track assignment problem (klayout-tools#1962), the cross-plane drawn-short defect the second-plane lever exposes (klayout-tools#7024), and the top-level connectivity this flow does not yet declare -- see `layout/pll/README.md` and the routing-lever measurement below.

## Routing-lever measurement (issue #548)

The spot-check above was re-measured once per shipped routing lever the generator had never requested, applied cumulatively in the issue's order, one full flow run per step. Every row below is derived from that run's own `klt` envelopes by `layout/bin/route_lever_tally.py` (the row also carries each envelope's sha256 -- fetch any of them from the artifact store with `klt artifact get <sha256>`); the first row is the committed baseline record, quoted from its own `record.md`. The levers this record's own run requests:

- `routing.cross_block_layer_role = 'metal3'` -- a second plane for same-block self-net legs (klayout-tools#1168)
- `mos_array` `interior_channel_um = 1.0` on every multi-unit matched array, routed build only (klayout-tools#1531/#1835)
- per-net `connectivity[].layer_role = 'metal3'` for the supplies ['VDD', 'GND'], ordered ahead of every signal net (klayout-tools#1655)
- per-net `connectivity[].layer_role = 'metal4'` for the 4 highest-pin-count signal nets ['UP', 'DN', 'VBP', 'VCTRL'] (derived from the plan, not typed in)

| Step (run) | Levers requested | Legs drawn | Nets full / partial / none | Declined legs by reason | Shorted nodes | Routed DRC | LVS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `20261106-075813-16557e3` (committed baseline, quoted from its own record.md) | none | 60 / 993 | 5 / 20 / 40 | route-vs-route 882; same-layer spacing 51 | 0 | 0 | `mismatch`, 1538 |
| `20261121-011715-147252b9` (baseline re-measured on this host/tool/PDK before any lever) | none | 60 / 993 | 5 / 20 / 40 | route-vs-route 882; same-layer spacing 51 | 0 | 0 | `mismatch`, 1538 |
| `20261121-013340-147252b9` (a. + routing.cross_block_layer_role second plane) | cross-block-plane | 78 / 946 | 13 / 17 / 35 | route-vs-route 861; same-layer spacing 7 | 1 | 2 | `mismatch`, 1520 |
| `20261121-013742-147252b9` (ab. + interior_channel_um on every multi-unit matched array) | cross-block-plane, interior-channel | 82 / 941 | 13 / 18 / 34 | route-vs-route 823; same-layer spacing 36 | 1 | 2 | `mismatch`, 1515 |
| `20261121-014158-147252b9` (abc. + supplies on their own plane, ordered first) | cross-block-plane, interior-channel, supply-plane | 109 / 385 | 14 / 12 / 39 | route-vs-route 224; same-layer spacing 52 | 0 | 1 | `mismatch`, 1491 |
| `20261121-015858-147252b9` (abcd. + per-net plane for the 4 highest-fanout signal nets) | cross-block-plane, fanout-plane, interior-channel, supply-plane | 111 / 365 | 14 / 12 / 39 | route-vs-route 226; same-layer spacing 28 | 0 | 4 | `mismatch`, 1489 |

### Reading the ladder

**The legs-total column is not a fixed basis.** The bundle router decomposes a multi-pin net into two-pin legs from the trunk it picks, and the trunk changes with the lever set (the supplies going first, onto their own plane, re-picks trunks for everything after them) -- 993, 993, 946, 941, 385, 365 legs across these runs. Compare *nets routed in full* and the decline reasons, not leg percentages across rows.

**The second-plane lever introduces a drawn short.** The cross-block-plane-only step carries 1 shorted node(s) and 2 DRC violation(s) in its routed build: a same-block leg retried on the `cross_block_layer_role` plane composed `routed: true` while another net's leg crossed its via-drop landing zone. Filed upstream, with a two-net minimal repro, as [klayout-tools#7024](https://github.com/2AMLogic/klayout-tools/issues/7024) -- the cross-plane analogue of the single-plane short #1197 fixed. Later levers remove it here (the rails no longer compete for the primary plane at that spot), and the final run's 0 shorted nodes is what any later citation of this stream relies on.

**The fanout-plane lever buys legs at a DRC cost.** The last step adds 2 legs and 3 more routed-build DRC violations (1 -> 4): the per-net higher planes' via-drop ladders land on intermediate planes where the spacing check does not model them -- the same ladder-footprint gap the #1962 discussion records as rejections, here surfacing as drawn violations. Both are reported upstream (#7024 carries the family).

**What the remainder needs.** With every shipped lever enabled, the residual is the assignment problem itself: 226 legs are still declined as crossing an already-drawn route, one net at a time in `connectivity[]` order, with no way to ask up front which *set* of planes/tracks is mutually consistent -- exactly the gap klayout-tools#1962 tracks, so #18 stays parked on it with this narrower, measured residual. The top-level composition also declares no connectivity at all (see the supply section below), which no per-net lever can change.

### Supply rails under the supply-plane lever

- **`GND`**: routes in full inside `clk_buf`, `loop_filter`, `pfd_cp`, `vco_ring5`.
- **`VDD`**: routes in full inside `clk_buf`, `pfd_cp`, `vco_ring5`.

No supply routes as a single island *across* blocks, and none can in this build: the top-level composition declares no connectivity at all (the composed block cells promote no ports this flow could name), so each block's rail is drawn inside that block only. That structural top-level gap -- not the per-block router -- is what stands between this measurement and a design-wide rail, and it is the input issue #156 takes from this record.

Full `klt lvs` closure (issue #18) remains open on the residual declined legs tabulated above; see the issue-#548 report on klayout-tools#1962 for the generic residual with every shipped lever enabled.

## Device set: schematic vs. extracted

`klt extract` reads the drawn stream back into a netlist with no knowledge of the plan that produced it, so this table compares two independently-derived multisets.

| Block | Kind | Schematic (from netlist) | Extracted (from GDS) | Match |
| --- | --- | --- | --- | --- |
| `pfd_cp` | MOS (class, W um, L um) | 59: 18x nfet/1/0.15; 6x nfet/1/0.3; 2x nfet/1/1; 1x nfet/10/0.15; 1x nfet/10/1; 2x nfet/2/1; 18x pfet/2/0.15; 6x pfet/2/0.3; 2x pfet/2/1; 1x pfet/20/0.15; 1x pfet/20/1; 1x pfet/4/1 | 59: 18x nfet/1/0.15; 6x nfet/1/0.3; 2x nfet/1/1; 1x nfet/10/0.15; 1x nfet/10/1; 2x nfet/2/1; 18x pfet/2/0.15; 6x pfet/2/0.3; 2x pfet/2/1; 1x pfet/20/0.15; 1x pfet/20/1; 1x pfet/4/1 | yes |
| `pfd_cp` | resistors (class, ohm) | 1: 1x res_xhigh_po/600000 | 1: 1x res_xhigh_po/600000 | yes |
| `loop_filter` | resistors (class, ohm) | 2: 1x res_xhigh_po/10000; 1x res_xhigh_po/5060 | 2: 1x res_xhigh_po/10000; 1x res_xhigh_po/5060 | yes |
| `loop_filter` | capacitors (class, F) | 3: 1x sky130_fd_pr__model__cap_mim/1.04227e-11; 1x sky130_fd_pr__model__cap_mim/2.07613e-10; 1x sky130_fd_pr__model__cap_mim/3.2304e-12 | 3: 1x sky130_fd_pr__model__cap_mim/1.04227e-11; 1x sky130_fd_pr__model__cap_mim/2.07613e-10; 1x sky130_fd_pr__model__cap_mim/3.2304e-12 | yes |
| `vco_ring5` | MOS (class, W um, L um) | 26: 6x nfet/2/0.15; 6x nfet/2/0.5; 1x nfet/8/0.15; 1x pfet/16/0.15; 6x pfet/4/0.15; 6x pfet/4/0.5 | 26: 6x nfet/2/0.15; 6x nfet/2/0.5; 1x nfet/8/0.15; 1x pfet/16/0.15; 6x pfet/4/0.15; 6x pfet/4/0.5 | yes |
| `clk_buf` | MOS (class, W um, L um) | 4: 1x nfet/1/0.15; 1x nfet/12/0.15; 1x pfet/2/0.15; 1x pfet/24/0.15 | 4: 1x nfet/1/0.15; 1x nfet/12/0.15; 1x pfet/2/0.15; 1x pfet/24/0.15 | yes |

The standard-cell block extracts as 654 transistors rather than its 42 schematic instances -- those are the library cells' own internal devices, which is what a standard-cell block's layout *is*; the instance-level check above is the one that compares like with like.

## Flow

1. `pll_layout.py` parses the schematic netlist and derives the plan (`plan.json`).
2. `klt gen mos_array` / `klt gen res_array` per matched device group.
3. `klt draw` per MiM capacitor (plate geometry -- no generator exists; see README).
4. Each divider standard cell is taken from the PDK's own library GDS.
5. `klt gen-compose` (explicit placement) per block, then once more for the top cell.
6. `klt drc` / `klt extract` / `klt cells` over the result -- the evidence in this directory.

## Provenance

- Record ID: `20261121-015858-147252b9`
- Schematic netlist: `design/top/netlist/top.spice`
- `klt` version: `klt 0.8.0` (see `layout/requirements.txt`)
- KLayout engine version: `0.30.12`
- PDK: `sky130A`, `open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`
- PDK pin cross-check: compare `version` above against `sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself enforce the pin (unlike `sim/harness/pdk.py`), so a mismatch here is a manual reproducibility note, not a hard failure.
- Repo state: `147252b9dcbf707630778d3dacfbcbed21cdf10a` on `feature/issue-548` (dirty)

## Links

The raw outputs below are in the artifact store, not in git (DR-012); they are
named by their manifest `name` (this record's directory + the path shown), see
"Stored evidence" at the end of this record.

- `plan.json` -- the schematic-derived layout plan (device set + full port/net map)
- `build.json` -- placement/composition summary
- `pll_top.gds` -- **the layout**
- `drc.json`, `extract.json`, `pll_top.spice`
- `cells.top.json` -- composed cell hierarchy
- `renders/overview.png`, `render.json`
- `report.md` -- combined `klt report --format github-summary` rendering

## Stored evidence

The raw bytes of this run are in the fleet artifact store, not in git (DR-012). Manifest: `manifests/artifacts/layout-pll-20261121-015858-147252b9.manifest.json` (124 objects, 4843657 B). Paths cited above are the manifest `name`s. Pinned harness boilerplate (`.spiceinit`, the exact `lvs.request.json` bytes in `PINNED_BOILERPLATE`) is omitted by rule (DR-014, DR-015). Check them against the store, or fetch one hash-verified, with:

```
klt artifact verify manifests/artifacts/layout-pll-20261121-015858-147252b9.manifest.json
klt artifact get manifests/artifacts/layout-pll-20261121-015858-147252b9.manifest.json#<name> -o <out>
```

| name | size (B) | sha256 |
|---|---:|---|
| `layout/pll/reports/20261121-015858-147252b9/build.json` | 2380 | `2a6b814670295090e8676513be00a5f40e04c40f1946ef78d441a44c30befe1e` |
| `layout/pll/reports/20261121-015858-147252b9/cells.divider_intN.json` | 17765 | `71d0d26fa2577ac7589ff2db8ca714d6fcc098113fbe624a5816657c51b3d300` |
| `layout/pll/reports/20261121-015858-147252b9/cells.top.json` | 45149 | `acaac4dbac72b029ff611c214d115465100814856327368970a96bb6203dae46` |
| `layout/pll/reports/20261121-015858-147252b9/clk_buf_nfet_w12_l0p15.gds` | 3324 | `0cd2614de47bda28cd3ff4208b9c934705ba3a38577e1dae9cceb535db226cb7` |
| `layout/pll/reports/20261121-015858-147252b9/clk_buf_nfet_w1_l0p15.gds` | 3324 | `615c1510dfa53548667e1dcf872893555f58ff955b273b9006f4b204dfa1ef68` |
| `layout/pll/reports/20261121-015858-147252b9/clk_buf_pfet_w24_l0p15.gds` | 3388 | `644e94d6f0143c46102066f97971b2bd0925b2ddff83fc74afad0e03e2c93f7b` |
| `layout/pll/reports/20261121-015858-147252b9/clk_buf_pfet_w2_l0p15.gds` | 3388 | `1e6350735b365b02f8313bd75ce13791a43e67dbcde6f63b734aa6f995ceaf7e` |
| `layout/pll/reports/20261121-015858-147252b9/compose.clk_buf.request.json` | 11900 | `397777443c4075fa8021e24a205926c104b1a195fa34c625c8893862cccd9dab` |
| `layout/pll/reports/20261121-015858-147252b9/compose.clk_buf.response.json` | 3322 | `c0ac07b08d84abc16528a331880699315ab3d17bdeffcef8d029214e74ca8d2c` |
| `layout/pll/reports/20261121-015858-147252b9/compose.divider_intN.request.json` | 22307 | `8210647372760024d43bd659506a2d81bb586b40302125e1c30522d0efe4fc0c` |
| `layout/pll/reports/20261121-015858-147252b9/compose.divider_intN.response.json` | 26181 | `ae8813a622408b57279657fd6857192fc71bad24061c29e498dba11ec5b62521` |
| `layout/pll/reports/20261121-015858-147252b9/compose.loop_filter.request.json` | 9435 | `ab22d854a4e2853fe48d7cce8a4878241e40d48faea44e3bb091861dfa224597` |
| `layout/pll/reports/20261121-015858-147252b9/compose.loop_filter.response.json` | 3796 | `9ba34126662a25d5cf5ebd77fd41c2cd3a3f538458183a751770afdea21711c0` |
| `layout/pll/reports/20261121-015858-147252b9/compose.pfd_cp.request.json` | 88528 | `10c6990653fb9caed7f1dc8ef82b34708df700ee8dd62970fa4f2f19152b07ca` |
| `layout/pll/reports/20261121-015858-147252b9/compose.pfd_cp.response.json` | 11423 | `c20dfa98028483317d2e4bcb0d10315be262eb1e6d804f75223e6b5b9d9f2469` |
| `layout/pll/reports/20261121-015858-147252b9/compose.top.request.json` | 2468 | `752ad57e7de280268f54d4aaef1d21275869a14b5993567b7d13271ba0e1b424` |
| `layout/pll/reports/20261121-015858-147252b9/compose.top.response.json` | 3545 | `84d7ce9cc37976802d92e2e789f9a636fc949ba5abc57393adea3d52ca285c82` |
| `layout/pll/reports/20261121-015858-147252b9/compose.vco_ring5.request.json` | 36920 | `5429bbcfab307eed6bd21ed42199d219fbd5bcfc0ef9fac327890e200fa8074e` |
| `layout/pll/reports/20261121-015858-147252b9/compose.vco_ring5.response.json` | 4699 | `20b95a44cd3be601829384b2d5171e270f03257347989eeb5cead433f94a072f` |
| `layout/pll/reports/20261121-015858-147252b9/draw.loop_filter_XC1.json` | 1056 | `6b5d91607410aac0b536084c503c1955335506bcfa9f9c2173dd205e02ee51cb` |
| `layout/pll/reports/20261121-015858-147252b9/draw.loop_filter_XC1.params.json` | 309 | `1c4f2d3c0c92fee86eaab21bf234a5251a8102d92b88e718e24cdc7033908a90` |
| `layout/pll/reports/20261121-015858-147252b9/draw.loop_filter_XC2.json` | 1024 | `a0eaf377848683572f2bd9da902a1e2191fcd71f0f1e00d91f52183acff6fd2b` |
| `layout/pll/reports/20261121-015858-147252b9/draw.loop_filter_XC2.params.json` | 305 | `f9914a5f3e0ed6e2ea20e33d1ae7017f77f991e32013384a3d758763740f5f78` |
| `layout/pll/reports/20261121-015858-147252b9/draw.loop_filter_XC3.json` | 1024 | `6fc64cbe93948172ad2f1a76b80b73f75b195a8215bbc1556180bed490cafe8d` |
| `layout/pll/reports/20261121-015858-147252b9/draw.loop_filter_XC3.params.json` | 305 | `b5644856b66a0ffd18b82842020ebd552f5cfdbc822b4de4c5825498d31c81a7` |
| `layout/pll/reports/20261121-015858-147252b9/drc.json` | 16789 | `eacf2108e75d94c5d08027b03fc9ce964c5b81bba051c95eca9c9be59c8f1247` |
| `layout/pll/reports/20261121-015858-147252b9/extract.json` | 635553 | `ffa011319c6fd1ad7618f1010743485db5f5e4e072c567104ce56878b866a861` |
| `layout/pll/reports/20261121-015858-147252b9/extract.pll_clk_buf.json` | 11161 | `ea3c3753aa4c36b3a5ae081b9058e84d586e9999565925d00c01763599d8eeb4` |
| `layout/pll/reports/20261121-015858-147252b9/extract.pll_divider_intN.json` | 418417 | `0d90e85f31c9d9e86dc9864698041288bb9697d7563c164be088e518896bef13` |
| `layout/pll/reports/20261121-015858-147252b9/extract.pll_loop_filter.json` | 9750 | `0f898096c8903a75b6871a138d8b03557170ab18c747e7594896a581dc46871b` |
| `layout/pll/reports/20261121-015858-147252b9/extract.pll_pfd_cp.json` | 90998 | `89fe1bf1aa1cb47c906a78756e6f686395359a5a928ea487debf92f86f19d26c` |
| `layout/pll/reports/20261121-015858-147252b9/extract.pll_vco_ring5.json` | 42072 | `4b9798d5fac87d66ec01f56af94e740d498517d793f55d6925b02cbc6c3d0d13` |
| `layout/pll/reports/20261121-015858-147252b9/gen.clk_buf_nfet_w12_l0p15.json` | 2208 | `897ff428f41f5a4e29b2395481b30aeb699f07198fd683c584e36d864acb6806` |
| `layout/pll/reports/20261121-015858-147252b9/gen.clk_buf_nfet_w1_l0p15.json` | 2203 | `550aa82d93ae97046edfc97cb1a13492813b36cad1b00a8d5b559feababf1250` |
| `layout/pll/reports/20261121-015858-147252b9/gen.clk_buf_pfet_w24_l0p15.json` | 2208 | `d648035617189fe13809b8c516491855c1010ff944543b92f85b8b4d4119802c` |
| `layout/pll/reports/20261121-015858-147252b9/gen.clk_buf_pfet_w2_l0p15.json` | 2187 | `8dfd74854bf3c2eddb1c79038bf98b4d16dc0e926f46cf75f63fed34cbe21d1f` |
| `layout/pll/reports/20261121-015858-147252b9/gen.loop_filter_resxhigh_w1_l2p53.json` | 1647 | `2fa985f484918ca0330196ca6c69b42771f489905c6ad65a6c93eff1d8c15932` |
| `layout/pll/reports/20261121-015858-147252b9/gen.loop_filter_resxhigh_w1_l5.json` | 1640 | `88439d3af0fd358739d85b3e6061441303f36513a0f6512214fb56d33b929f39` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_nfet_w10_l0p15.json` | 2206 | `272c04362c20bbfa04bbad1fbcbdf5ae71b6d00c9d4eded3d3b36d339e4b4cdf` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_nfet_w10_l1.json` | 1809 | `7ed50c2ee2780bdc614785388e1adc0e4e78669e3c22b46070d0cca4e723545d` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_nfet_w1_l0p15_row0.json` | 6073 | `d14cca10d13ae4d8e4f879a1188c455d361adacfb1d7e89d9d58df73b97610b3` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_nfet_w1_l0p15_row1.json` | 6073 | `4fe4c572a0d0398f4d5c0ff01871f9e2f54c1108c06b90c35145427b4ee4ce16` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_nfet_w1_l0p15_row2.json` | 6073 | `98a5323d07498985994e10d8dd7e879d48350c7974348da647a877689bcdbb28` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_nfet_w1_l0p3.json` | 5571 | `0f408f7cba865772a11bf3c8c8b3cb1a6dcd3099dcaa92af74d84aeef59f9c06` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_nfet_w1_l1.json` | 2589 | `5951992edcb4c835e6c1171971fb04752a46e4cc37133b364a03340faf04c014` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_nfet_w2_l1.json` | 2561 | `dd4f2c1ad6eedfae737a10056fd9519ffa8034512ba6ce2c4222f4bd12bf941c` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_pfet_w20_l0p15.json` | 2206 | `03a833d851daea8fbb187f6ae34f21fe1c372555d10c254980466921c4f9c4cd` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_pfet_w20_l1.json` | 1809 | `5421fb7b3879bdea42d17fd94bd0589901dc4e1faff353bc936ee47bf84e3e21` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_pfet_w2_l0p15_row0.json` | 5975 | `1ba2b93f4a751a3ad01fa4b85c529a177322dac25412b9b21508071983302e8b` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_pfet_w2_l0p15_row1.json` | 5975 | `fb3fc400eb449395cd3bd66f07693587c98d4d31186938000644603b57911735` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_pfet_w2_l0p15_row2.json` | 5975 | `e82e77e8ef5fda45276ec30d0bced63e71741e0af52287db669c5176e233e257` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_pfet_w2_l0p3.json` | 5527 | `75385f1d499967393b310b9cf30adf5d0ace54fd0ee53707ce56be9954ba764c` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_pfet_w2_l1.json` | 2559 | `73698efa5f58da31dea41b2be624f10414e18a82b30170098ea702ac91b7f262` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_pfet_w4_l1.json` | 1815 | `2ef6fdcc25ae2eb7aff5b07725f8b56f8aad636ffd97ac9cc707969096e7d393` |
| `layout/pll/reports/20261121-015858-147252b9/gen.pfd_cp_resxhigh_w1_l300.json` | 1638 | `8642d674dad838cfc187c5605e1cd4cad503f73adf747dffde73ee6cc2571325` |
| `layout/pll/reports/20261121-015858-147252b9/gen.vco_ring5_nfet_w2_l0p15.json` | 5987 | `b1a126476a8be098b83819e8f28a442158f5e8deda2faef0feab9c006f10940b` |
| `layout/pll/reports/20261121-015858-147252b9/gen.vco_ring5_nfet_w2_l0p5.json` | 5535 | `607e97d2cb79177b7358564139e94e0ed1943b4f1ee64948929c72a18eabc81f` |
| `layout/pll/reports/20261121-015858-147252b9/gen.vco_ring5_nfet_w8_l0p15.json` | 2206 | `f359b58c9ef5f199793402bc7c63464bf6ccca6ba2475460530e0202d5ea1f49` |
| `layout/pll/reports/20261121-015858-147252b9/gen.vco_ring5_pfet_w16_l0p15.json` | 2210 | `2fd4249af11708b7744d00c983a8dc6ae0ab7e2ba89aa082fc12d04955eb9e6d` |
| `layout/pll/reports/20261121-015858-147252b9/gen.vco_ring5_pfet_w4_l0p15.json` | 6125 | `865863a82f37a586aeeb4cad652dd45b2c8a33180cf0889759a87c61436ad564` |
| `layout/pll/reports/20261121-015858-147252b9/gen.vco_ring5_pfet_w4_l0p5.json` | 5673 | `f4f7a286f07ded0179c8be1946596b368087aff80c33281d484106bdd8fc6f1e` |
| `layout/pll/reports/20261121-015858-147252b9/loop_filter_XC1.gds` | 246 | `731c8bb91fde6a337fcc4be9ed3e7d67fb892b4c099f652895631924f8ac056f` |
| `layout/pll/reports/20261121-015858-147252b9/loop_filter_XC2.gds` | 246 | `2f1064f7dc8d091776b7ef428fd3109d3f58a691c6c44072b099fff6d37fa06e` |
| `layout/pll/reports/20261121-015858-147252b9/loop_filter_XC3.gds` | 246 | `d7a22ac46f7033965e16f567bd0e8f615c7c04e1d9b54ec3a2c6fca1ce43c5d1` |
| `layout/pll/reports/20261121-015858-147252b9/loop_filter_resxhigh_w1_l2p53.gds` | 2630 | `0b03b74fc2ca6a7af76f25008d2b9b64ab9ba13dc885ee53e58ea1e75b19b92b` |
| `layout/pll/reports/20261121-015858-147252b9/loop_filter_resxhigh_w1_l5.gds` | 2622 | `d9ab6738de3f216e176cc9f4ca7006e310139df454840fd1802112ae8e5f56e9` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_nfet_w10_l0p15.gds` | 3324 | `741822a191567dda16b66594900ec8142d95da284a6261447866402744dc1199` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_nfet_w10_l1.gds` | 3318 | `1eb8f8872913c58b14a8a9c36b170e0f71e6dd179a46a7d59c9e1c21dc54185b` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_nfet_w1_l0p15_row0.gds` | 7178 | `37f978101665bf3e9bd973e00e9c38322d9f3058faa3cda324aad5338c5d75d0` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_nfet_w1_l0p15_row1.gds` | 7178 | `ded7b7e9a9ce967e2823d58b025403010455e920e9b3fe779a19b331051541a9` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_nfet_w1_l0p15_row2.gds` | 7178 | `7d6f1ea364c2f916688c5adf0789e608317a9fb8491756d0cc703184daa535ab` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_nfet_w1_l0p3.gds` | 7236 | `0c874b3a304dbd2c7bef59a224dcc2bcfa45cd07ade12e576f3bfa304bf10a46` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_nfet_w1_l1.gds` | 4096 | `ece52a8953438e87036faad2f83f185233c1d9eb668bebaa2237cfa9679f04e8` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_nfet_w2_l1.gds` | 4096 | `0b83ee33b07eefece8623617a28f706ca716b01bee1d3702039a2069bd8e061e` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_pfet_w20_l0p15.gds` | 3388 | `c80a5598b24ef9c6c986c9166e887f15f34a5c93c395729ac6b6302ff81a988b` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_pfet_w20_l1.gds` | 3382 | `9aa65bdfd78eb9afd19bab5ab248e468176138e81290dd329fe779af6e6d8643` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_pfet_w2_l0p15_row0.gds` | 7242 | `bf72f67b2dfea5e800e4fbd32870969c9013636fc007f64b8f945818d4a63e77` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_pfet_w2_l0p15_row1.gds` | 7242 | `cd9b34acce96360a29720a67a8f1c309db8303ce3cb02ea87c47f2d7ce691a81` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_pfet_w2_l0p15_row2.gds` | 7242 | `d9921b8cc1c0ec5de9d29e45fc44aedfc4ff24ea4b782fd33b5a754b6a15f6ea` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_pfet_w2_l0p3.gds` | 7300 | `4be7f4df28b3533c10172e6e57c40ff712fde4a3b21e067e56cdb2036d5f2b32` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_pfet_w2_l1.gds` | 4160 | `bf38405c14b41bcc8b032587adb293784824f663b4cefb632d7128f17eb5c58e` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_pfet_w4_l1.gds` | 3382 | `047a517763ad8e8a7612ce1b0c542eb317ac11cd7572a631ec3055b1f41684f2` |
| `layout/pll/reports/20261121-015858-147252b9/pfd_cp_resxhigh_w1_l300.gds` | 2622 | `e1e387d33e9d9c2708bdaea47d029359afe74aa3bb1766d0789d2a7c95cb8f42` |
| `layout/pll/reports/20261121-015858-147252b9/plan.json` | 59540 | `60b65403c5e2b03efea03d1b11c85073c639e3b0cc4987aebfc91fe95bd1ec9c` |
| `layout/pll/reports/20261121-015858-147252b9/pll_clk_buf.extract.spice` | 597 | `70c4163365277f0aed2baf66f78fa9c46a6b744ca56affe5b1f3c051070dc60a` |
| `layout/pll/reports/20261121-015858-147252b9/pll_clk_buf.gds` | 4502 | `143b76c7c6de991073968df4042d9980ac8ca4000485ca39d962dfaa758b5a6f` |
| `layout/pll/reports/20261121-015858-147252b9/pll_divider_intN.extract.spice` | 90218 | `613c7e7a3be1628bc7d0577ad7fb1f499a55f4c0d2c50dfc681834d812488cfa` |
| `layout/pll/reports/20261121-015858-147252b9/pll_divider_intN.gds` | 358788 | `8ea52579e59987fb50a43db40949cc924de67f39c34173794324abbd705774c0` |
| `layout/pll/reports/20261121-015858-147252b9/pll_loop_filter.extract.spice` | 605 | `04898874e99ff6404630f2727c8092229f59d08a350dbbca1ce69b2a90523328` |
| `layout/pll/reports/20261121-015858-147252b9/pll_loop_filter.gds` | 2794 | `b1ba50367a37ffab4d053f4d181fbd4c8aa6e47cc56eda8377197d80264dbe83` |
| `layout/pll/reports/20261121-015858-147252b9/pll_pfd_cp.extract.spice` | 7537 | `7aa3d5297415955bef55bb739a9d4e032b9552d5788ec93ab8fcdc10a0e85f21` |
| `layout/pll/reports/20261121-015858-147252b9/pll_pfd_cp.gds` | 51728 | `364d5f3382ae55d5410eda7c698d8b15ee8eeb36c5c281cd6d18a9aee158b4ea` |
| `layout/pll/reports/20261121-015858-147252b9/pll_top.gds` | 440316 | `b551636048e258c89ca72b5f29461cf40a2f840532a9c36def27bf399311c952` |
| `layout/pll/reports/20261121-015858-147252b9/pll_top.spice` | 103807 | `6f97a2781fd57ff075c1d7c2b323a4d660674b372e959cdb70c5b5ef4d8b12ad` |
| `layout/pll/reports/20261121-015858-147252b9/pll_vco_ring5.extract.spice` | 3268 | `ed19cd467cd7e1794cf1a6c99603789e66f4616db26637844259eda04ad23feb` |
| `layout/pll/reports/20261121-015858-147252b9/pll_vco_ring5.gds` | 22348 | `a6e62f0b9491d6d43220b9cc52d38262ffcd42ba281cdb6731b93d4eb75b3856` |
| `layout/pll/reports/20261121-015858-147252b9/render.json` | 7976 | `2c489fc238fdc8b0821b08dc161e3a2d9a4a4173955456102aeb9df6f1ac09b7` |
| `layout/pll/reports/20261121-015858-147252b9/renders/overview.png` | 40761 | `df03f1720da2e601f4503ce3ee2ce4bbe1b0545ccf7461cc5fd00e0d0031eac5` |
| `layout/pll/reports/20261121-015858-147252b9/report.md` | 190 | `545b20990c0274468027781642f5cdef518b30118276d1b74162c559aa3d00d7` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/build.json` | 16271 | `b75b0f000ceea0a9fa972650bd5ed13d565ca4e66630bdd62704c64548963a1d` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.clk_buf.request.json` | 13462 | `d448596bce1ca92ba2fda4c6620b6ed4db73ba256818980e037598e9006eb835` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.clk_buf.response.json` | 9795 | `a75556a02c954d3b56413806b74f6c278a81d79c7833b5633e032d1a3d401852` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.divider_intN.request.json` | 22433 | `19a511f5917115d18cd2283bec9c23c2897ad2f93fd57c48e0e2ada00cc86ef5` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.divider_intN.response.json` | 26307 | `84b39232dcdf79c65a2358dbe62c0e4764e812b4550fd82d9913156f1beb180d` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.loop_filter.request.json` | 10735 | `a6544f7e875b5f4e7d49b89033035a98856a1b4d64b65c14c8d2bb0c04517be4` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.loop_filter.response.json` | 8068 | `1cd7590313cd85b1c12a049af5eb6e926e35afb8818165770b4ecbec118681c1` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.pfd_cp.request.json` | 112164 | `730667c435840ee0cad82639859024016ed7e7281f0cc36baeb00774f1444fa3` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.pfd_cp.response.json` | 157274 | `7826e15b58c478a4d21a47b84210290c3d96026280b2a491a20b635d589c42e5` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.top.request.json` | 2468 | `4f2d275e58c8cc5f16e73eaf8b87fa6a65f6834fd9905d51ab45b239c53a4d73` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.top.response.json` | 3545 | `a5acd2083243bc025d104a317af6c0cf54e4d2b45c0f71463384f8f90dd33f21` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.vco_ring5.request.json` | 46637 | `003f0fe43ff6018280f6128e4aa9dad79b78c07cf5aaf0004b3ce79b19a7138f` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/compose.vco_ring5.response.json` | 52556 | `ec2af2c0c1179610e0575ce58fd2444ebd256035264b8f45e32ab36a570518db` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/drc.json` | 18031 | `1b2c6b2ad2cd5b17ae2ac85252abb9a30983186f5fd3561db923bafb0b475f3e` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/extract.json` | 605714 | `31583e75d6b887ad0df49d7f8b7b96684686214a2b55151efdfb7e928c0b66c8` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/lvs.json` | 638588 | `a6816f848fb2a859c5bd0197c8fdc9ab92bf1ac0b75f32ea760f9d32fe83ec4a` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/pll_top.spice` | 103997 | `80a65e9e9419ce720b35bc1316c2c6b30f314981327a045a152b2d1607732dc9` |
| `layout/pll/reports/20261121-015858-147252b9/route-spot-check/reference.spice` | 18532 | `877f20fe2d0ac861cd2429363767482d9a50b0636113d7d690c86301be80557a` |
| `layout/pll/reports/20261121-015858-147252b9/routing-levers.json` | 12483 | `bd68012805b9f04bf7e328f01034bba8cad5959c2be22b3aca29d3bcd39b679d` |
| `layout/pll/reports/20261121-015858-147252b9/vco_ring5_nfet_w2_l0p15.gds` | 7240 | `bb479eb63b1b66a14fbb42b7f1fb379bf3cd61569eaef8a628d3c8880f7078b2` |
| `layout/pll/reports/20261121-015858-147252b9/vco_ring5_nfet_w2_l0p5.gds` | 7238 | `4e5448f22e10288138112b249cc1e76216d7e2ee07dc67864eb8ccbf5ac3ff1b` |
| `layout/pll/reports/20261121-015858-147252b9/vco_ring5_nfet_w8_l0p15.gds` | 3326 | `e99c7317abae66273695079ba4e80127cacbb2f772188dd53dae17cb52a0f4a1` |
| `layout/pll/reports/20261121-015858-147252b9/vco_ring5_pfet_w16_l0p15.gds` | 3390 | `f708344a3891a4cdb65f79048aacc61d4050c384bf7b019293eaf6546872719e` |
| `layout/pll/reports/20261121-015858-147252b9/vco_ring5_pfet_w4_l0p15.gds` | 7304 | `ae88ea3dcf7bf15ac085972adadfd4ce3dfd87f63be0edddd1456c39d7aabc38` |
| `layout/pll/reports/20261121-015858-147252b9/vco_ring5_pfet_w4_l0p5.gds` | 7302 | `f2577bd0be88933ec6c505f5a54aa7e3416a463adf7985a89fb816576b4acf1d` |
