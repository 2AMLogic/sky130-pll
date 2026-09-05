# Layout DRC/LVS record: 20260905-184511-4285e0a

Trivial-cell proof of the `klt`-driven DRC/LVS flow (issue #2) -- **not** PLL-block layout, which is a later issue's scope (there is no PLL schematic yet).

## Overall verdict: PASS

- [x] DRC on trivial_mos_array is clean
- [x] DRC negative control (deliberately illegal geometry) reports violations
- [x] DRC negative control trips exactly the rules its fixture declares (li1.space.1, poly.width.1)
- [x] LVS matches the known-good reference
- [x] LVS negative control (device-parameter corruption) reports mismatch
- [x] LVS negative control (topology corruption) reports mismatch

## Flow

1. `klt gen mos_array --pdk sky130A --cell-name trivial_mos_array` -- default params (2x2 array, 1 dummy column/side, nfet, no well).
2. `klt drc trivial_mos_array.gds --deck sky130`
2b. `klt draw` the deliberately illegal fixture (`drc-negative-control.params.json`), then run the same deck against it -- it must come back flagged.
3. `klt extract trivial_mos_array.gds --deck sky130 --top trivial_mos_array`
4. `klt lvs` against `reference.spice` (known-good) and two negative-control references (`reference.broken-device.spice`, `reference.broken-topology.spice`).

## Cell

- Generator: `mos_array` (`klt gen --list` for the full params schema)
- `device_count` (extracted): 4
- `dummy_devices_dropped`: 4
- bbox (um): {'x0': -1.52, 'y0': 0.0, 'x1': 4.16, 'y1': 2.08}
- `matched_group_id`: mos_array:2x2:common_centroid

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| DRC | clean | violation_count=0 |
| DRC negative control | violations | violation_count=2, rule_counts={'li1.space.1': 1, 'poly.width.1': 1} |
| Extract | extracted | device_count=4, net_count=13, pin_count=1 |
| LVS (good reference) | match | mismatch_count=8, category_counts={'device.body_unverified': 1, 'topology': 7} |
| LVS negative control: device parameter | mismatch | mismatch_count=34 |
| LVS negative control: topology (shorted net) | mismatch | mismatch_count=32 |

The DRC negative control is a `klt draw` fixture -- geometry written verbatim with no rule checking -- carrying one deliberately illegal width and one deliberately illegal spacing, so a regression that silently disabled either check primitive would still be caught by the other. Rules the fixture declares it should trip: `li1.space.1`, `poly.width.1`; rules the deck actually reported: `li1.space.1`, `poly.width.1`.
- `li1.space.1` -- the two li1 (67/20) rectangles are separated by a 0.10 um gap, below sky130's 0.17 um minimum li1 spacing -- a SPACING-class violation
- `poly.width.1` -- the 0.10 um-tall poly (66/20) rectangle is below sky130's 0.15 um minimum poly width -- a WIDTH-class violation

The good-reference LVS run's `mismatch_count` (8) is nonzero but `status` is `"match"` -- all 8 entries are `severity: "warning"` (0 at `severity: "error"`; see `lvs.json`), documented, expected quirks for this minimal, highly symmetric cell:
- `device.body_unverified` (x1): the curated sky130 extraction deck draws no distinct NMOS substrate/tap layer, so every body terminal compares against a deck-synthesized `vsubs` net rather than a real schematic net (documented in `klt extract`'s own "Coverage" docs).
- `topology`, ambiguous net pairing (x5): the array's unit devices are electrically interchangeable (no two devices connect to a common net that would anchor a unique pairing), so `NetlistComparer` resolves the correspondence structurally rather than uniquely -- expected for a fully symmetric matched array, not a defect.
- `topology`, unused device class on both sides (x2): device classes the sky130 deck can recognise (e.g. `pfet`, `pnp`, `resistor`) but that this cell draws none of -- not a real mismatch.

## Provenance

- Record ID: `20260905-184511-4285e0a`
- `klt` version: `klt 0.4.0` (see `layout/requirements.txt`)
- KLayout engine version: `0.30.12`
- PDK: `sky130A`, `open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b`
- PDK pin cross-check: compare `version` above against `sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself enforce the pin (unlike `sim/harness/pdk.py`), so a mismatch here is a manual reproducibility note, not a hard failure.
- Repo state: `4285e0a4cc9e15cc51f52d0dc9138dc55173163d` on `feature/issue-17` (dirty)

## Links

- [`gen.json`](gen.json), [`trivial_mos_array.gds`](trivial_mos_array.gds)
- [`drc.json`](drc.json)
- [`drc-negative-control.params.json`](drc-negative-control.params.json), [`draw.negative-control.json`](draw.negative-control.json), [`drc_negative_control.gds`](drc_negative_control.gds), [`drc.negative-control.json`](drc.negative-control.json)
- [`extract.json`](extract.json), [`trivial_mos_array.extract.spice`](trivial_mos_array.extract.spice)
- [`lvs.request.json`](lvs.request.json), [`lvs.json`](lvs.json), [`reference.spice`](reference.spice)
- [`lvs.broken-device.request.json`](lvs.broken-device.request.json), [`lvs.broken-device.json`](lvs.broken-device.json), [`reference.broken-device.spice`](reference.broken-device.spice)
- [`lvs.broken-topology.request.json`](lvs.broken-topology.request.json), [`lvs.broken-topology.json`](lvs.broken-topology.json), [`reference.broken-topology.spice`](reference.broken-topology.spice)
- [`report.md`](report.md) -- combined `klt report --format github-summary` rendering

