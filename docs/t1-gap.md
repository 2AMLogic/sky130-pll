# Gap to T1

**This file is a pointer, not a verdict.** This block's T1 verdict of record
is [`signoff/tier-report.json`](../signoff/tier-report.json), rendered by
`klt signoff --manifest` from the committed block manifest
[`signoff/block-manifest.json`](../signoff/block-manifest.json) and re-checked
in CI by `bash signoff/run-signoff.sh --check`.
[`signoff/README.md`](../signoff/README.md) explains every row: what each met
row does and does not say, why each unmet row is unmet, and what would change
it. Read those, not a hand-maintained table here.

As rendered today: the manifest declares `kind: "mixed-signal"` (the
programmable divider, built from `sky130_fd_sc_hd` standard cells, is the
digital partition; everything else is analog; see `signoff/README.md`'s "Block
kind" section for the boundary). The report reads **3 of 22 T1 rows met** —
item 3 (DRC clean) once per partition, and item 8 (characterization report)
for the analog partition only — and `tier: null`. Item 8's row means only
that `measurements/report.md` is the artifact the item names. It does not
mean any spec row is met. That report itself records FAIL rows (lock time,
row 8, among them) and rows with no evidence. `python3
signoff/readme-manifest-consistency.py` (in `npm run check:ci`) fails if the
count or the kind stated in this paragraph stops matching the report and the
manifest.

The checklist is `klayout-tools`'
[`docs/design-evidence-tiers.md`](https://github.com/2AMLogic/klayout-tools/blob/main/docs/design-evidence-tiers.md),
graded at the version this repo pins (`klayout-tools==0.6.0`, eleven items).
The report records which copy of the checklist it graded against
(`source_doc`, `source_doc_content_hash`).

What remains below is the one per-item read too detailed for the report's
rows: item 11, which `signoff/README.md` §4 declines to cite and points here
for.

## Item 11 in detail

Added to the checklist 2026-09-17 (klayout-tools#2025). It is the
**structural** power-delivery question — *is the supply connected to what it
powers* — graded from a `klt erc` supply-spec run. IR drop and
electromigration (`klt power`) are the *analysis* question and stay
deliberately outside it.

**What is on record** (issue #147):

- [`layout/pll/erc-supply-spec.json`](../layout/pll/erc-supply-spec.json) —
  the supply spec, with every layer/datatype resolved from the sky130A PDK's
  own `sky130A.lyp` **and** cross-checked against klayout-tools' curated
  sky130 deck layer table, and an inline justification for each `stackup`
  entry and each `label_layer`.
- [`layout/pll/erc-reports/`](../layout/pll/erc-reports/) — the committed
  `klt erc --format json` report, content-hash-pinned to both the layout and
  the spec it was run against.

**What that run establishes**: `VPWR` → exactly one electrical island,
`VGND` → exactly one, zero `erc.unconnected_net`, zero `erc.supply_short`.
Two of item 11's three rules.

**What is still missing, and why item 11 is NOT met:**

1. **`erc.missing_tie` is NOT COMPUTED.** The spec declares no `ties[]`,
   because declaring one collapses a real standard-cell layout into a single
   island and reports a false `erc.supply_short` (klayout-tools#2169;
   reproduced in `gf180-drone-fc`'s FRICTION F-034). Per `klt erc`'s own
   contract, omitting `ties[]` means the rule never runs — the zero count in
   the committed report is an **absence of evidence, not evidence of
   absence**. Nothing stands in for it here: `tap.drawing` (65/44) has zero
   shapes in the layout, there is no `power.tapcell_master` (no
   `klt place-and-route` run exists), and the only `klt lvs` result is a
   `mismatch`.
2. **The Analog column also requires item 4's LVS report to have carried the
   supply nets in its `net_correspondence`.** That is issue #18, and this
   repo's only LVS result is a `mismatch`.
3. **The declared supplies cover one of four blocks.** `VPWR`/`VGND` are the
   `sky130_fd_sc_hd` standard cells' own power-pin names and come entirely
   from the divider's abutted cell row — a 142.6 × 2.72 µm strip of a
   569.93 × 232.76 µm block. The three custom-drawn analog blocks carry no
   supply labels and no supply rails at all, because the layout is unrouted.
   Filed as **#156**.

A fourth gap — reproducibility rather than evidence — is **closed** (issue
#157, 2026-09-23). The first committed report was produced with a `klt` newer
than `layout/requirements.txt`'s pin of the day (`klayout-tools==0.4.0`),
whose `klt erc` predated both `stackup[0].active_layer` and the `provenance`
block, so it could not be regenerated from the pin. The pin is now
`klayout-tools==0.6.0`, both layout flows were re-run at it, and the
`erc-reports/LATEST` record of that day was produced by the pinned build. The
superseded record is kept unedited; the record it superseded records the
measured `0.4.0`-vs-`0.6.0` difference (216 "gates" vs 213 — the old pin
counted this block's three poly resistors as gates and understated every
antenna ratio by ~2.9×).

That fix left one reproducibility gap of its own: `layout/requirements.txt`
pinned `klayout-tools` but not the `klayout` engine it runs on, so a cold
install of that pin could resolve whatever `klayout` engine PyPI had current
that day — a bare `pip install 'klayout-tools==0.6.0'` resolves
`klayout==0.30.12`, not the `0.30.10` that build's own engine-mismatch
warning names as tested against — and made `klt` warn on every
`drc`/`extract`/`lvs`/`erc` call. Closed by **issue #167**:
`layout/requirements.txt` now also pins `klayout==0.30.10`, both layout flows
and the ERC run were re-run at it, and `erc-reports/LATEST` is the current
record. The per-gate antenna attribution moved (131 of 213 gates), but every
aggregate figure and the verdict on item 11's rules did not.

## Keeping this file honest

- The verdict lives in `signoff/`. If this file and `signoff/tier-report.json`
  disagree, the report is right and this file is stale.
- The checklist upstream is versioned and **has changed item count before**
  (it grew item 11, *Power delivery (structural)*, on 2026-09-17,
  klayout-tools#2025). A `klt` pin bump re-renders the report against the new
  checklist; re-read the section above when that happens.
- Never relax a row to make it read better. A miss is recorded as a miss
  (root `CLAUDE.md`).
