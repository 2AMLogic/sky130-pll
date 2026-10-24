# PLL ERC supply record: 20261020-165500-ba142d6

**Supersedes [`20260924-041753-c53e7c4`](../20260924-041753-c53e7c4/record.md)**
(and, through it, `20260923-085051-13ecfe9` and `20260923-062347-b3abad8`).
Issue #298, part of the open_pdks re-pin #295: re-run against the layout
record minted under `open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`.
Read `../README.md` first; everything it says about what a record of this
class does and does not establish still applies, including that
`erc.missing_tie` is NOT COMPUTED.

## What was run

```bash
layout/.venv/bin/klt erc layout/pll/reports/20261020-164647-ba142d6/pll_top.gds \
  layout/pll/erc-supply-spec.json \
  --top pll_top --pdk sky130 --format json \
  > layout/pll/erc-reports/20261020-165500-ba142d6/erc.json
```

| Input | Value |
| --- | --- |
| Layout | `layout/pll/reports/20261020-164647-ba142d6/pll_top.gds` (what `layout/pll/reports/LATEST` names) |
| Layout content hash | `sha256:5133a0ac…beb4` (`provenance.input.content_hash`) |
| Spec | `layout/pll/erc-supply-spec.json`, `sha256:171a58e5…3b48` (`provenance.spec.content_hash`; differs from the superseded record's `229d452a…` because the spec file changed on `main` since, not because of this run) |
| `klt` / KLayout | `0.6.0` / `0.30.10`, the `layout/requirements.txt` pins; exit code 0, empty stderr |

## Verdict on item 11's own rules

| Rule | Result |
| --- | --- |
| Every declared supply resolves to exactly one island | PASS -- `erc_findings` is empty (no `erc.unconnected_net`) |
| No `erc.supply_short` on a declared supply | PASS |
| Zero `erc.missing_tie` | NOT COMPUTED (`no_ties_declared`), unchanged |

## Old-vs-new

| | `c53e7c4` (old) | this | Cause |
| --- | --- | --- | --- |
| `erc_finding_count` / `erc_status` / `status` | 0 / clean / clean_partial | 0 / clean / clean_partial | unchanged |
| `gate_count` | 213 | 264 | design (`clk_buf`, larger divider and loop filter) |
| Sum of `gate_area_um2` | 131.489 | 158.774 | design |
| Largest single `gate_area_um2` | 20.0 | 20.0 | unchanged |
| Worst antenna ratio `li1` (limit 75) | 11.640 | 11.640 | unchanged |
| Worst antenna ratio `met1` / `met2` (limit 400) | 11.717 | 11.717 | unchanged |
| Every gate's `antenna_verdict` | `pass_partial` | `pass_partial` | unchanged |

The layout is not byte-identical to the superseded record's, so the
gate-count rows are design effects, not PDK effects. `klt erc` here runs
with the built-in `--pdk sky130` antenna table (`provenance.pdk.source:
built-in`), so this record does not itself isolate a PDK-tree effect; the
verdict and every worst-case ratio are unchanged.

## Still true, unchanged

- Antenna numbers are against an **unrouted** layout and will change once
  routing lands.
- `VPWR`/`VGND` still come from the divider's standard-cell row only; the
  analog blocks carry no supply rails (issue #156). Item 11 is not met by
  this evidence alone.
