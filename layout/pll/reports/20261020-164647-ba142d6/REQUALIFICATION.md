# Re-qualification under open_pdks f6eeac7 (issue #298, part of #295)

This record was minted by `layout/bin/run-pll-layout-flow.sh` at
`ba142d6` against `~/.ciel/sky130A` (`SOURCES`: `open_pdks
f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`, the pin in `sim/pdk.json`;
`klt pdk find` resolved via `search root: ~/.ciel`). `record.md` is the
flow's own output, unedited; this file is the supersession and comparison
note that `record.md` cannot carry.

**Supersedes** [`20260924-041509-c53e7c4`](../20260924-041509-c53e7c4/record.md)
(the previous `LATEST`) and, through it, every record in this directory
that names `open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b`:
`20260819-065329-33d74dd`, `20260819-082044-d3af784`,
`20260821-080803-b0c10bd`, `20260905-185809-4285e0a`,
`20260906-162756-9be24a9`, `20260906-170938-e2a91aa`,
`20260906-175702-eceaadb`, `20260906-195205-4a08c71`,
`20260923-084911-13ecfe9`. None of those was edited.

## Two things changed at once -- read the tables separately

1. **The PDK pin** (`c6d73a3` -> `f6eeac7`). Already visible in the repo
   *before* this issue: `20260924-041509-c53e7c4` records
   `open_pdks f6eeac7…` and its stream is byte-identical to the `c6d73a3`
   record `20260923-084911-13ecfe9` (sha256 `939f97e0…8d4c`). The PDK
   effect on that pre-buffer top is therefore measured by that pair
   (table A), not by this record.
2. **The design**: `main` at `ba142d6` carries the `clk_buf` block and a
   larger divider and loop filter that `c53e7c4` (a dirty
   `feature/issue-167` tree) predates. This record is the first at the
   current schematic, so its counts differ from `c53e7c4` for design
   reasons, not PDK reasons (table B).

### A. PDK effect only (same design, same GDS hash)

| Record | open_pdks | KLayout | DRC | Routed-spot-check LVS |
| --- | --- | --- | --- | --- |
| `20260923-084911-13ecfe9` | `c6d73a3` | 0.30.12 | clean, 0 | mismatch, 1179 |
| `20260924-041509-c53e7c4` | `f6eeac7` | 0.30.10 | clean, 0 | mismatch, 1179 |

A `diff` of the two `record.md` files differs only in record id, KLayout
engine, PDK line, pin-cross-check wording and repo-state line. No
PDK-attributable change.

### B. Current design under `f6eeac7` vs. the superseded `LATEST`

| Metric | `c53e7c4` (old) | `ba142d6` (this) | Cause |
| --- | --- | --- | --- |
| DRC, unrouted `pll_top` | clean, 0 | clean, 0 | unchanged |
| DRC, routed spot-check | clean, 0 | clean, 0 | unchanged (51 legs still declined for `met1.space.1`; see `signoff/README.md`) |
| Blocks in `pll_top` | 4 | 5 | `clk_buf` added |
| `divider_intN` cells | 29 | 42 | design |
| Per-block device-multiset check | all match | all match, incl. `clk_buf` | unchanged verdict |
| Declared nets | 60 | 65 | design |
| Router legs drawn / total | 57 / 980 | 61 / 990 | design |
| Spot-check LVS | mismatch, 1179 | mismatch, 1493 | design; not LVS-clean in either (issue #18) |
| `pll_top` bounding box (um) | 569.93 x 233.0 | 703.95 x 448.92 | design |

The LVS mismatch is the recorded, expected miss (almost all legs are
undrawn); it is not a PDK regression and it is not waived by this note.
Nothing moved in a way that needs a new issue or decision record.
Sequencing note: #304 (draw `clk_buf` in the top-level layout) is open and
will mint another top-level record; it must name this one as the one it
supersedes.

## Companion records

- `../../../trivial-cell/reports/20261020-164643-ba142d6/` -- trivial-cell flow.
- `../../erc-reports/20261020-165500-ba142d6/` -- `klt erc` against this
  record's `pll_top.gds`.
