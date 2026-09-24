# `layout/pll/erc-reports/` — `klt erc` supply-spec evidence (T1 item 11)

Append-only records of `klt erc` runs against this repo's PLL layout, driven
by [`../erc-supply-spec.json`](../erc-supply-spec.json). They are the
**structural power-delivery** evidence T1 **item 11** is graded from — added
to `klayout-tools`' `docs/design-evidence-tiers.md` on 2026-09-17
(klayout-tools#2025). Stood up by issue #147.

`LATEST` names the current record. Read that record's `record.md` **first**;
its `erc.json` is the raw evidence the record summarises.

Same rules as `../reports/`: a record, once written, is never edited or
deleted. A re-run mints a new record that names the one it supersedes.

## Reproducing a record

```bash
klt erc layout/pll/reports/<layout-record-id>/pll_top.gds \
  layout/pll/erc-supply-spec.json \
  --top pll_top --pdk sky130 --format json \
  > layout/pll/erc-reports/<record-id>/erc.json
```

Each record's `record.md` states the exact layout record it was run against,
both content hashes (`provenance.input` / `provenance.spec`), and the `klt`
build used. **Check the hashes before trusting a record**: `klt erc`'s verdict
depends on two inputs, not one, and a report pinned to only the layout cannot
be re-verified against the declarations it was actually run with.

The current record **is** produced with this repo's pinned `klt`
(`layout/requirements.txt` → `klayout-tools==0.6.0`) **and** its pinned
`klayout` engine (`layout/requirements.txt` → `klayout==0.30.10`, added by
issue #167). Before #167, `klayout` was an unpinned transitive dependency of
`klayout-tools`, so a cold `layout/bin/setup-venv.sh` install resolved
whatever engine build PyPI had current that day — confirmed still live at
the time of the #167 fix: a bare `pip install 'klayout-tools==0.6.0'` (no
`klayout` pin) resolves `klayout==0.30.12`, not the `0.30.10` that build's
own engine-mismatch warning names as tested against. Every record this repo
committed at the `0.6.0` pin before #167 — including this record's immediate
predecessor — was produced by exactly that unpinned resolution, `klt`'s
engine-mismatch warning included. See the current record's "What was run"
and "What the engine pin actually changed" sections — the per-gate antenna
attribution moves across the engine pin (131 of 213 gates), but every
aggregate figure (sum, max, worst ratio per layer, verdict) and
`erc_finding_count` land on the exact same numbers either way.

Its immediate predecessor (`20260923-085051-13ecfe9`) was produced with the
`klayout-tools==0.6.0` pin but no `klayout` pin (issue #157's bump), and
happened to resolve `klayout==0.30.12` that day. The first record
(`20260923-062347-b3abad8`) predates both: it was made with a `0.5.0+g…`
`klayout-tools` build that is not resolvable upstream, and the pin of its day
(`==0.4.0`) had neither `stackup[0].active_layer` nor the `provenance` block.
Both predecessors are kept, unedited, as records the current one supersedes.
See `20260923-085051-13ecfe9/record.md`'s own "What the pin bump actually
changed" section for the measured `0.4.0`-vs-`0.6.0` `klayout-tools` antenna
difference, which is a separate change from the engine-pin difference this
record documents.

## What a clean record here does and does not establish

**Does**: every supply declared in `../erc-supply-spec.json` resolves to
exactly one electrical island across the declared stackup — no
`erc.unconnected_net`, no `erc.supply_short`. That is two of item 11's three
rules.

**Does not**:

1. **`erc.missing_tie` is NOT COMPUTED.** The spec declares no `ties[]`,
   because declaring one collapses a real standard-cell layout into a single
   island and reports a false `erc.supply_short` (klayout-tools#2169;
   `gf180-drone-fc` FRICTION F-034). Per `klt erc`'s contract, omitting
   `ties[]` means the rule never runs — the zero count in `erc.json` is an
   **absence of evidence, not evidence of absence**. In this block the honest
   state is worse than "unverified": `tap.drawing` (65/44) has zero shapes,
   so the well/substrate ties are not drawn at all. No
   `power.tapcell_master`, no LVS `power_connectivity.status: "match"`, and
   no supply-carrying `net_correspondence` exists here to stand in for it.
2. **Item 11 is not met by this evidence alone.** For an analog block, item
   11 also requires item 4's own LVS report to have carried the supply nets
   in its `net_correspondence` — i.e. issue #18. This repo's only `klt lvs`
   result is a `mismatch`.
3. **The declared supplies are the standard cells' `VPWR`/`VGND` and cover
   only the divider row.** The shipped layout is an unrouted device-level
   floorplan; the three custom-drawn analog blocks carry no supply labels and
   no supply rails. A clean record here is a statement about a
   142.6 × 2.72 µm strip of a 569.93 × 232.76 µm block.
4. **Nothing about IR drop or electromigration.** Those are `klt power`'s
   *analysis* question and are deliberately outside item 11, which asks only
   the *structural* one: is the supply connected to what it powers.

## Records

Newest first. `LATEST` names the current one.

| Record | Layout record | `klt` | KLayout engine | Verdict on item 11's rules |
| --- | --- | --- | --- | --- |
| [`20260924-041753-c53e7c4`](20260924-041753-c53e7c4/record.md) | `20260924-041509-c53e7c4` | `0.6.0` (**the pin**) | `0.30.10` (**the pin**, issue #167) | one island per declared supply (PASS); no supply short (PASS); `erc.missing_tie` NOT COMPUTED |
| [`20260923-085051-13ecfe9`](20260923-085051-13ecfe9/record.md) — superseded | `20260923-084911-13ecfe9` (byte-identical stream) | `0.6.0` | `0.30.12` (not the pin — engine was unpinned at the time) | same verdict; kept unedited as a record the current one supersedes |
| [`20260923-062347-b3abad8`](20260923-062347-b3abad8/record.md) — superseded | `20260906-195205-4a08c71` (byte-identical stream) | `0.5.0+g2f64ab88bfcc` (not the pin, not resolvable upstream) | `0.30.10` | same verdict; kept unedited as the record it was superseded by supersedes |
