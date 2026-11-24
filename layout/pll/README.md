# layout/pll/ — the PLL layout

Issue #16's deliverable: a **device-level layout of the closed-loop PLL
schematic**, drawn headlessly from `design/top/netlist/top.spice` by
`layout/bin/run-pll-layout-flow.sh`. Each run is an append-only evidence
record: `reports/<record-id>/record.md` and
`manifests/artifacts/layout-pll-<record-id>.manifest.json` are committed; the
raw outputs (GDS, extracts, JSON envelopes, renders) are in the fleet artifact
store (DR-012). Records minted before #371 still carry their bytes in git.

**Read the current record's `record.md` first** — it is the actual pass/fail
evidence this issue delivers, not this file. `reports/LATEST` names it.
The layout stream itself is `reports/<record-id>/pll_top.gds` in a pre-#371
record; in a newer one it is the manifest entry of that name
(`klt artifact get manifests/artifacts/layout-pll-<record-id>.manifest.json#layout/pll/reports/<record-id>/pll_top.gds -o pll_top.gds`).

**Newest record**: `20261121-015858-147252b9` — the buffered top with every
shipped routing lever requested in its routed spot-check (issue #548),
verdict **PASS**. It is *not* what `reports/LATEST` names, on purpose: its
raw evidence lives in the fleet artifact store (DR-012), and the signoff
superseded-record guard requires `LATEST` to name the record
`signoff/run-signoff.sh` item 3 cites — a clean CI checkout cannot verify a
manifest-only record yet
([klayout-tools#5591](https://github.com/2AMLogic/klayout-tools/issues/5591)).
Re-pointing `LATEST` is tracked by issue #459; until then read the newest
record directly at
[`reports/20261121-015858-147252b9/record.md`](reports/20261121-015858-147252b9/record.md).

The flow fails closed: without `$KLT_ARTIFACT_BROKER`, a `klt` with
`artifact put`, and a reachable broker it exits nonzero before drawing and
commits nothing. It never falls back to committing the bytes. It stages in the
git-ignored `layout/pll/build/<record-id>/`.

```bash
layout/bin/setup-venv.sh            # once, or after bumping requirements.txt
layout/bin/run-pll-layout-flow.sh   # ~30 s; writes a fresh record
```

A second, separately-recorded read of the same layout lives alongside it:
[`erc-supply-spec.json`](erc-supply-spec.json) and
[`erc-reports/`](erc-reports/) hold the `klt erc` **supply-spec** evidence
T1 item 11 (structural power delivery) is graded from — start at
`erc-reports/README.md`, which states in full what a clean record there does
and does not establish. Issue #147.

## What it is

Every device the schematic declares is physically drawn, at the schematic's
own W/L, and the five blocks (four PLL blocks plus the `clk_buf` output buffer, issue #232) are composed into one `pll_top` cell:

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
  GDS carries no wires. The one router available (`klt gen-compose`'s) now
  gets every shipped routing lever this generator can request (second
  plane, interior channels, per-net supply/fanout planes — issue #548, see
  the routing-lever measurement below) and still leaves most nets undrawn:
  the residual is the router's order-dependent plane/track assignment
  problem (klayout-tools#1962), not an unrequested capability. Each
  record's routing spot-check carries the per-leg evidence.
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
| ~~MOS generators cannot draw a DRC-clean device at a PDK's minimum gate length: the unit device's source/drain local-metal pads abut the gate, so their spacing equals the gate length, below the metal min-spacing rule~~ **Fixed upstream** ([klayout-tools#1201](https://github.com/2AMLogic/klayout-tools/pull/1201), merged as `bd5c7f4`) | [klayout-tools#1187](https://github.com/2AMLogic/klayout-tools/issues/1187) (closed) | Issue #17 bumped `layout/requirements.txt`'s `klt` pin past the fix (`klayout-tools==0.4.0`) and re-ran this flow: the pads no longer abut the gate, and the layout's DRC comes back clean of this rule (0 violations, first confirmed at that pin and still 0 in the current record, which #157 re-ran at `klayout-tools==0.6.0`) — no workaround needed any more |
| `connectivity[]` cannot be declared without also requesting metal — there is no "record the intended topology, draw nothing" mode | [klayout-tools#1188](https://github.com/2AMLogic/klayout-tools/issues/1188) | The unrouted request omits `connectivity[]`; the declared topology is written to the flow's own `plan.json` instead |
| `gen-compose` cannot consume a cell it did not generate — its own response is not a valid block input (no `generator`, no `ports[]`), so hierarchical composition and PDK library cells need a hand-forged `generator_report` | [klayout-tools#1189](https://github.com/2AMLogic/klayout-tools/issues/1189) | Synthesizes the inline block report for the top level and for library cells |

Filed after the `klt` pin bump (#46), by the router the bump made usable:

| Gap | Filed | How this flow copes |
| --- | --- | --- |
| ~~`gen-compose`'s route-vs-route collision check misses two same-block self-nets: both compose `routed: true` with no warning, and extraction reads them back as one node~~ **Fixed upstream** (klayout-tools PR #1216, merged as `dd41d23f`) | [klayout-tools#1197](https://github.com/2AMLogic/klayout-tools/issues/1197) (closed) | Issue #17's DRC-motivated pin bump (`klayout-tools==0.4.0`) turned out to be a strict descendant of this fix too — a re-run of this design's routing spot-check confirmed 0 shorted nodes, down from 3. The current pin (`klayout-tools==0.6.0`, #157) is a descendant of `0.4.0` in turn, and the current record's spot-check still reads 0 shorted nodes. Still ships the unrouted stream regardless (most legs remain undrawn — see the routing-channel gap below), and the routed build stays as a spot-check under `route-spot-check/` |
| ~~`mos_array` emits one opaque hierarchical cell with no internal routing channel reserved between rows/columns, and `gen-compose` treats every placed block as a solid obstacle with no notion of navigable space inside it — so a pin on any unit device not on the array's outermost reachable row/column is structurally unroutable, for any net, regardless of placement spacing~~ **Fixed upstream** (`mos_array` `interior_channel_um` + `navigable_regions`, and `gen-compose` subtracting those regions from the block's obstacle bbox) | [klayout-tools#1531](https://github.com/2AMLogic/klayout-tools/issues/1531) (closed) | The routed spot-check build now requests `interior_channel_um = 1.0` on every multi-unit matched array (routed build only — the shipped stream's geometry is unchanged); issue #548 measured the full lever ladder, see the routing-lever measurement section below and the newest record's own table. The row-channel split below stays (it is free, already shipped, and buys *placement* space the channel does not) |
| ~~No per-net track/layer allocation between nets: one routing plane per request, so crossing nets on that plane are an unresolvable short~~ **Fixed upstream** (per-net track allocation inside a plane, and per-net `connectivity[].layer_role` / `legs[].layer_role` planes) | [klayout-tools#1467](https://github.com/2AMLogic/klayout-tools/issues/1467) (closed), [klayout-tools#1655](https://github.com/2AMLogic/klayout-tools/issues/1655) (closed) | The routed spot-check build puts the supplies on their own plane (ordered ahead of every signal net) and the highest-fanout signal nets on the next one up, both derived from the plan (issue #548) |
| A leg retried on `routing.cross_block_layer_role` can silently short two declared nets — both compose `routed: true` with no warning, extraction reads one node; same family, drawn same-layer spacing violations on the fallback/per-net planes | [klayout-tools#7024](https://github.com/2AMLogic/klayout-tools/issues/7024) (closed upstream 2026-11-22 by klayout-tools PR #7138, "Reject shared-edge shorts at fallback via landings" — **not in the pinned `klayout-tools==0.8.0`**: the newest release, `v0.9.2`, predates that merge, so the gap is still live for this flow; the family's open descendant is [klayout-tools#7325](https://github.com/2AMLogic/klayout-tools/issues/7325)) | Not worked around: the second-plane lever stays on (it measurably helps), the newest record tabulates the shorted-node count and routed-build DRC per lever step, and the final configuration measures 0 shorted nodes — the supply plane removes the specific collision. Any stream cited downstream must keep that 0 |

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

What still blocks a routed stream was, through the #17-era pin, the
point-to-point router's inability to route a pin buried inside a matched
device array's own interior (263 of 917 legs at the post-pin-bump
measurement above) — routing that would need an actual channel *inside* the
array, which is a floorplan redesign, not a spacing tweak (a throwaway
experiment raising `GROUP_SPACING_UM`/`BLOCK_SPACING_UM` 2.5x barely moved
the numbers, since that spacing is between *groups*, not between an array's
own internal rows/columns). That gap was filed upstream, generically, as
[klayout-tools#1531](https://github.com/2AMLogic/klayout-tools/issues/1531)
and is **closed**: `mos_array` now reserves `interior_channel_um` gap bands
(reported as `navigable_regions`, which `gen-compose` subtracts from the
block's obstacle bbox), and issue #548's measurement (below) exercises it on
this design. With every shipped lever enabled, what still blocks a routed
stream is the router's order-dependent plane/track *assignment* problem —
[klayout-tools#1962](https://github.com/2AMLogic/klayout-tools/issues/1962):
legs are still declined one at a time as "crosses already-routed net" with no
way to ask up front which set of assignments is mutually consistent — plus
the cross-plane drawn-short defect
([klayout-tools#7024](https://github.com/2AMLogic/klayout-tools/issues/7024))
the second-plane lever exposes, and the absence of any top-level
connectivity in this flow's composition. Distinct from the long-closed
#1057/#1197 (route-vs-route shorting) and #1467 (inter-net track/layer
allocation, also closed) — those were contention *between* nets; the
residual is that no combination-level assignment exists over them.

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
the gap — a genuine per-unit interior routing channel was needed and was not
something this flow's floorplan choices alone could supply; that channel now
exists (`interior_channel_um`, klayout-tools#1531 closed) and issue #548's
measurement below exercises it. The current record's routing spot-check
tabulates the router's own reason for every leg it declined, and its LVS
(spot-check) section runs `klt lvs` against that build and records the
resulting mismatch in full.

### Issue #18's row-channel split

The three floorplan experiments above all vary *how* a single `klt gen
mos_array` call arranges its own `rows`/`cols`/`topology` — none of them
could touch #1531 directly while a single call's own interior had no channel
at all, regardless of shape (the historical situation; the channel exists
now, see above). The one lever this flow's own floorplan requests *do*
control is how many devices go into one `klt gen` call in the first place:
nothing requires an entire matched group to be one call. `pll_layout.py`
splits a near-square group into `rows` separate
one-row `mos_array` calls of `cols` devices each, composed as independent
blocks — which turns what used to be a zero-width internal row gap into
`GROUP_SPACING_UM` of real, router-visible space between them, the same kind
of gap `shelf_pack` already reserves between every other pair of groups.

This is only done when it cannot cost a device its common-centroid partner:
splitting only pays off when the per-row device count (`cols`) is itself
even, so every row keeps a valid `common_centroid` pairing on its own
(`_centroid_order`'s point-reflection still has a mirror within an
even-length row). On this design that condition holds for exactly the two
18-device groups (`factor_rows_cols(18) == (3, 6)`, an even `cols`); every
other matched group either already fits on one row (nothing to split) or has
an odd `cols` (the four 6-device groups, `factor_rows_cols(6) == (2, 3)`),
where splitting would silently drop common-centroid matching to plain
`array` order on a smaller group than the schematic's own count — the same
regression the `topology` guard above already refuses to make. When this
split was designed, reading `_mos_array_layout` directly confirmed there was
no equivalent lever *inside* one `klt gen mos_array` call — its complete
parameter surface was `w_um` / `l_um` / `rows` / `cols` / `dummy` /
`flavor` / `topology` / `gate_contact` / `finger_topology` /
`gate_pad_clearance_um` / `draw_well_tap` / `add_guard_ring` /
`ring_gap_side` / `ring_gap_um` / `ring_gap_offset_um` / `ring_padding_um`,
none of it a row/col pitch or channel-width knob — which was the concrete
basis for #1531's claim that no single call could reserve internal channel
space at all. That premise is history: the pinned `klt` now ships
`interior_channel_um` (with `pitch_x_um`/`pitch_y_um` beside it), and the
routed spot-check requests it (#548). The split stays anyway — it is free,
already measured, partner-safe, and it buys *placement* space between
independently placed blocks, which the in-call channel does not.

Measured effect (`20260906-195205-4a08c71`, same `klt` 0.4.0 / KLayout
0.30.12 / `open_pdks c6d73a35` pin as every measurement on this page): 66 of
926 legs drawn, against 62 of 917 on the unsplit near-square grid — a
four-leg gain that is noise-level, not a fix.

| | unsplit near-square grid (`20260906-175702-eceaadb`) | row-channel split (`20260906-195205-4a08c71`) |
| --- | --- | --- |
| Legs drawn | 62 / 917 | 66 / 926 |
| own-block-interior (the bucket this change targets) | 263 | 371 |
| route-vs-route collision (unrelated) | 460 | 354 |
| unrelated-block bbox (unrelated) | 119 | 127 |
| `klt lvs` mismatches | 1166 | 1164 |
| Shorted nodes | 0 | 0 |

The bucket this change specifically targets moved the *wrong* direction (263
→ 371): splitting two groups changes their own footprints, which reshuffles
`shelf_pack`'s whole-design placement and therefore which legs the router
attempts in what order — a change local to two groups redistributes bucket
membership design-wide rather than only shrinking the bucket it targets.
Read together with the `rows=1`-for-the-whole-group experiment above (which
eliminates row-interior burial by construction and *also* measured
neutral-to-worse), the router's leg-failure reasons do not appear to be
independently addressable one at a time by floorplan reshaping alone.

This result is shipped anyway — unlike the withdrawn topology/packing
experiments above — because, unlike those, it costs nothing: no device loses
its matched partner (the parity guard makes that structurally impossible),
DRC stays clean, and the device-set cross-check is unaffected. It is a real,
verified negative result on the one lever this flow's own floorplan requests
can pull directly against #1531, worth having on record precisely so the
same idea is not re-spent. Closing this issue's LVS acceptance criterion
still needs the router's assignment gap (#1962) closed upstream — not a
floorplan-request change on this side.
`layout/tests/test_pll_layout_plan.py`'s
`test_row_channel_groups_reconstruct_their_parent_near_square_grid` asserts
the parity guard and the split shape, so a future change cannot silently
widen the split to an odd-`cols` group.

### The routing-lever measurement (issue #548)

With #1531, #1467 and #1655 all closed upstream, the routed spot-check was
re-measured once per shipped lever the generator had never requested,
applied cumulatively — `routing.cross_block_layer_role` (a second plane),
`interior_channel_um` (navigable array interiors), the supplies on their own
`connectivity[].layer_role` plane ordered first, and a per-net plane for the
four highest-pin-count signal nets (derived from the plan). One full flow
run per step; the newest record's "Routing-lever measurement" section
carries the full before/after table with per-envelope sha256s. Headlines,
against the committed 60-of-993-legs / 5-of-65-nets baseline (reproduced
exactly on this host before any lever):

- every lever is accepted by the pinned tool — no rejection text to quote;
- the supplies **route in full inside every block that declares them**
  (the per-block rail result issue #156 consumes) — no design-wide rail
  exists or can, because the top-level composition declares no
  connectivity at all;
- the second-plane lever introduces a drawn short plus `met2.space.1`
  violations (klayout-tools#7024, filed with a two-net minimal repro);
  the supply plane removes that short here and the final configuration
  measures **0 shorted nodes**;
- the final configuration draws 111 legs / 14 nets in full against 60 / 5,
  at the cost of 4 routed-build `met3.space.1` violations from the
  per-net planes' via ladders — the ladder-footprint gap the #1962
  discussion records as rejections, surfacing here as drawn violations;
- `klt lvs` still reports `mismatch` (1489), so issue #18 stays parked on
  klayout-tools#1962 with this narrower, measured residual: with every
  shipped lever enabled, what remains is the combination-level
  plane/track assignment problem itself.

#### Exclusive supply plane trial (issue #575) — rejected, not adopted

One more run of the final configuration with a single variable changed:
`SUPPLY_LAYER_ROLE = "metal5"` (`met4`) instead of `"metal3"` (`met2`), so
the rails no longer share a plane with the `cross_block_layer_role` fallback.
`ROUTING_LAYER_ROLE` (`metal2`), `CROSS_BLOCK_LAYER_ROLE` (`metal3`),
`FANOUT_LAYER_ROLE` (`metal4`), net order and tool/PDK pins were unchanged;
each block's compose request carried `layer_role = "metal5"` on `VDD`/`GND`.
Row derived by `route_lever_tally.py` from the run's own envelopes
(run record id `20261124-032415-6a7a0251`, not committed), against the
control `20261121-015858-147252b9`:

| | Control (supplies `metal3`) | Trial (supplies `metal5`) |
| --- | --- | --- |
| Legs drawn / total | 111 / 365 | 114 / 377 |
| Nets full / partial / none | 14 / 12 / 39 | 15 / 13 / 37 |
| Declined: route-vs-route / same-layer spacing | 226 / 28 | 204 / 59 |
| Shorted nodes | 0 | 0 |
| Routed DRC | 4 (`met3.space.1`) | 10 (`met3.space.1` 4, `capm.enclosing.via3.1` 3, `capm.separation.via3.1` 3) |
| LVS | `mismatch` (1489) | `mismatch` (1483) |

The shipped unrouted stream stayed at 0 DRC violations. The leg-total basis
differs between rows, so the comparison is nets routed in full and decline
reasons, as the record's "Reading the ladder" warns.

**Disposition: rejected; supplies stay on `metal3`.** The trial routes one
more net in full and draws no short, but routed-build DRC rises from 4 to 10
(the `met4` supply via ladders land on MiM-cap layers and trip the
`capm.*.via3.1` rules), same-layer-spacing declines more than double (28 to
59), and the combined decline count rises (254 to 263) on a larger leg
total. LVS stays `mismatch` with no closure. Read strictly, "more nets in
full" alone could be taken as an improvement; this trial is recorded as a mixed
result whose DRC regression outweighs a single net, not as a clean win. No
record was minted, so the control remains the newest record. Envelope sha256s (fetch with `klt artifact get <sha256> --repo
2AMLogic/sky130-pll`). The row is derived from every envelope in
`route_lever_tally.py`'s evidence set, including the per-block compose
responses that carry all 65 nets (the top-level `compose.top.response.json`
declares no nets and backs no routing cell). Original run
`20261124-032415-6a7a0251`: `drc.json`
`23c8fba66c2ec5739d41fafeb2ad511b30aee8246720b96382ba544cd3bcf2c3`,
`lvs.json` `4857fb97730047c620b433e7b757cb4cf17156860430eb9b7fecddff72aa030c`,
`extract.json` `0fb37dd55a35624161ea76967dd90bc76cea2d2154e3aa728f07fb81b25ce1c0`,
`build.json` `8f599546fc7b3ab5c689a97694d0519ebfb8c26d4c0013b9ceb8f0d8649660c3`.
That run's per-block compose envelopes were not retained, so the routing
cells (legs, nets full/partial/none, declines) were re-measured by repeating
the identical trial (same single variable and pins; the flow's outputs were
not committed and no record was minted). The re-run reproduced every cell of
the table exactly (114 / 377 legs, 15 / 13 / 37 nets, 204 / 59 declines,
routed DRC 10 with the same rule split, LVS `mismatch` 1483, 0 shorted
nodes) and an identical `build.json` hash. Its full evidence set, under
`layout/pll/build/20261124-034618-4529de39/route-spot-check/`:
`build.json` `8f599546fc7b3ab5c689a97694d0519ebfb8c26d4c0013b9ceb8f0d8649660c3`,
`compose.clk_buf.response.json`
`a75556a02c954d3b56413806b74f6c278a81d79c7833b5633e032d1a3d401852`,
`compose.divider_intN.response.json`
`84b39232dcdf79c65a2358dbe62c0e4764e812b4550fd82d9913156f1beb180d`,
`compose.loop_filter.response.json`
`1cd7590313cd85b1c12a049af5eb6e926e35afb8818165770b4ecbec118681c1`,
`compose.pfd_cp.response.json`
`71b75e60ca1a6493d5378181419d1d2426002ab96d0e7dbd869a6e7d8251d03b`,
`compose.top.response.json`
`dec9ba12e829bb09a9390eb38c156b9d26855abae70231eefeb335d05faa4126`,
`compose.vco_ring5.response.json`
`d9aee20ef45eeca40292f80c4d083e62d5f27e177df1cd81026001f09f718d84`,
`drc.json` `97f248136f4470a3ec2f18ea9fe8f29dedf7be87189e4615d557e8cf0d27a011`,
`extract.json` `07a04370b0379055050824a940bff84e68ff430b4224f53abce5ebc24120c68e`,
`lvs.json` `318319c5ab07dfed6c724be6e0c413afe75db2077d19e2f3b559800a18558b65`.
`metal5` is not the top role (`metal6` = `met5` exists), so further
exclusive-plane variants remain possible but are not pursued here.

The unrouted *shipped* stream is unchanged by all of it — the interior
channel is applied to the routed spot-check build only, and the shipped
build's DRC stays clean (asserted by the record).

Two capabilities the bump makes available are deliberately **not yet adopted**,
because adopting either changes drawn geometry and needs its own evidence:
`klt gen cap_array` (#1117) in place of this flow's `klt draw` MiM plates, and
block `orientation` (#1166), which the divider's single row does not need
today.

## Directory layout

The tree below is the layout of a run's output. For a record minted after
#371 only `record.md` sits in `reports/<record-id>/`; every other file is a
manifest entry named `layout/pll/reports/<record-id>/<path>`.

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
