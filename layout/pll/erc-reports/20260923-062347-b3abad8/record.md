# PLL ERC supply record: 20260923-062347-b3abad8

The first `klt erc` supply-spec run in this repository — the structural
power-delivery evidence T1 **item 11** (klayout-tools#2025, added to the
checklist 2026-09-17) is graded from. Issue #147.

Read `../README.md` first for what this class of record does and does not
establish. Read this file before `erc.json`; `erc.json` is the raw evidence
this file summarises.

## What was run

```bash
klt erc layout/pll/reports/20260906-195205-4a08c71/pll_top.gds \
  layout/pll/erc-supply-spec.json \
  --top pll_top --pdk sky130 --format json \
  > layout/pll/erc-reports/20260923-062347-b3abad8/erc.json
```

| Input | Value |
| --- | --- |
| Layout | `layout/pll/reports/20260906-195205-4a08c71/pll_top.gds` (the record `layout/pll/reports/LATEST` points at) |
| Layout content hash | `sha256:939f97e0…8d4c` — `erc.json`'s `provenance.input.content_hash`, and the `sha256sum` of the committed GDS |
| Spec | `layout/pll/erc-supply-spec.json` |
| Spec content hash | `sha256:ee791569…a7a2` — `erc.json`'s `provenance.spec.content_hash`, and the `sha256sum` of the committed spec |
| `klt` | `0.5.0+g2f64ab88bfcc` (`provenance.klt_version` records the release part only, `0.5.0`) |
| KLayout | `0.30.10` |
| Exit code | `0` |

**The `klt` build is NOT this repo's pinned one, and that is a real
reproducibility gap.** `layout/requirements.txt` pins
`klayout-tools==0.4.0`; that release's `klt erc` has neither the
`stackup[0].active_layer` field (klayout-tools#1979) this spec requires for a
`poly ∩ diff` antenna denominator, nor the `provenance` block
(klayout-tools#1968/#2036) that carries the two content hashes above. So this
record could not have been produced by `layout/bin/setup-venv.sh`'s pinned
build at all. Bumping the pin re-runs both layout flows and re-checks their
records in as the non-regression proof (`layout/README.md`), which is a
separate piece of work — tracked as its own issue, cited from
`docs/t1-gap.md`.

## Verdict on item 11's own rules

Item 11 grades three things, and **not** the report's overall `status`
(`docs/design-evidence-tiers.md`, item 11; klayout-tools#1994):

| Item 11 rule | Result | Where to check it |
| --- | --- | --- |
| Every declared supply resolves to exactly **one** electrical island | **PASS** — `VPWR` → 1 island, `VGND` → 1 island | zero `erc.unconnected_net` in `erc_findings` |
| No `erc.supply_short` naming a declared supply | **PASS** | zero `erc.supply_short` in `erc_findings` |
| Zero `erc.missing_tie` | **NOT COMPUTED** — see below | no `ties[]` in the spec |

`erc_finding_count` is `0` and `status` is `"clean"`, but the first two rows
above are the ones item 11 actually reads.

### Independently corroborated

The island counts were re-derived outside `klt erc`, with a hand-written
`klayout.db.LayoutToNetlist` extraction over the same layers this spec
declares, before this record was written: `VPWR` → 1 island, `VGND` → 1
island, zero islands carrying both names. That agrees with `klt erc`'s own
zero-`erc.unconnected_net` verdict, which per `docs/cli/erc.md` means exactly
one island (the rule fires on zero matches *and* on more than one).

## `erc.missing_tie` is NOT COMPUTED — absence of evidence

The spec deliberately declares no `ties[]`. Declaring one on a real routed
standard-cell layout collapses the design into a single electrical island and
reports a **false** `erc.supply_short` — filed upstream as
**klayout-tools#2169** and reproduced four ways in `gf180-drone-fc`'s
FRICTION F-034. Per `klt erc`'s own contract ("Omitted entirely →
`erc.missing_tie` is never computed"), the zero `erc.missing_tie` count in
`erc.json` is **an absence of evidence, not evidence of absence**. Nothing in
this record may be read as "the well/substrate ties check out".

**What stands in for it here: nothing, and the true state is worse than
"unverified".**

- `tap.drawing` (65/44) has **zero shapes** in `pll_top.gds`. The
  `sky130_fd_sc_hd` logic cells draw no taps of their own (verified against
  the PDK's own `libs.ref/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds`: e.g.
  `sky130_fd_sc_hd__inv_2` carries no 65/44 geometry), and no tap cell is
  placed in the divider row. The well/substrate ties are not merely
  uncomputed — they are **demonstrably not drawn**.
- There is no `klt place-and-route` response anywhere in this repo (this is a
  `klt gen-compose` device-level flow), so there is no
  `power.tapcell_master` to cite.
- The only `klt lvs` run on record is the routing spot-check's, and it
  reports `mismatch` with 1164 mismatches
  (`layout/pll/reports/20260906-195205-4a08c71/record.md` → "LVS
  (spot-check)"). There is no `power_connectivity.status: "match"` and no
  supply-carrying `net_correspondence` to stand in. LVS closure is issue #18.
- The only body-bias evidence present is label text: 30 `VPB` on
  `nwell.label` (64/5) and 30 `VNB` on `pwell.label` (64/59), inherited from
  the standard cells. Those are pin *names* on well shapes, not contacted
  ties, and neither label layer is a conductor role in this spec.

## The much larger caveat: this reads ONE of four blocks

`VPWR`/`VGND` are the `sky130_fd_sc_hd` standard cells' own power-pin names,
and they are the **only** supply labels any geometry in this stream carries.
They come entirely from the divider's standard-cell row:

| | Value |
| --- | --- |
| `VPWR` met1 island bounding box | `(0, 232.28) … (142.6, 232.76)` µm |
| `VGND` met1 island bounding box | `(0, 229.56) … (142.6, 230.04)` µm |
| `pll_top` bounding box | `(-0.19, -0.15) … (569.93, 232.76)` µm |
| met1 area on the declared supplies | 136.9 of 156.3 µm² (87.6 %) |
| li1 area on the declared supplies | 84.6 of 432.2 µm² (19.6 %) |

Each rail is one island because the 29 standard cells are abutted in a single
row and their met1 power rails touch — which is a genuine structural pass,
but a pass over a 142.6 × 2.72 µm strip of a 569.93 × 232.76 µm block.

The other three blocks (`pfd_cp`, `vco_ring5`, `loop_filter`) are
custom-drawn and carry **no supply labels and no supply rails at all**: the
shipped layout is a device-level floorplan with no inter-device interconnect
drawn (`layout/pll/reports/20260906-195205-4a08c71/record.md` → "Not
routed"). The top-level schematic
(`design/top/netlist/top.spice`) names this block's supplies `VDD`/`GND`;
no shape anywhere in this stream carries either string. So a clean result
here says *the divider row's rails are continuous*, not *this PLL's supply
reaches what it powers*. That gap is filed as its own issue and cited from
`docs/t1-gap.md`.

## Antenna and floating-gate results (not item 11's subject)

Reported in the same run, and recorded here because the run produced them —
but an antenna verdict or a floating-gate finding is explicitly **not** item
11's subject and does not block it (klayout-tools#1994).

- `gate_count`: **213** gate nets, identified as `poly ∩ diff`
  (`stackup[0].active_layer` = `diff.drawing` 65/20), so the loop-filter and
  PFD/CP poly resistors (`poly.res` 66/13, no gate oxide) are correctly
  excluded from the denominator.
- **Zero `erc.floating_gate`** findings — every gate net has connected
  geometry above poly (the device generator draws a li1 landing pad on every
  terminal).
- Antenna: every graded level **passes**. Worst ratios are `li1` 11.64
  (limit 75), `met1`/`met2` 11.72 (limit 400).
- Every gate reports `antenna_verdict: "pass_partial"`, never plain
  `"pass"` — `met3` is declared in the stackup and sky130's own transcribed
  antenna table has no met3 limit, so that level is `"unchecked"` for every
  net. This is the documented coverage-gap roll-up
  (klayout-tools#1997), not a violation. `poly` is always `"unchecked"` by
  contract.
- These numbers are taken against an **unrouted** layout. They will change,
  probably substantially, once issue #18's routing lands; nothing here is a
  standing antenna sign-off.
