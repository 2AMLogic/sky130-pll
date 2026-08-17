# PLL characterization report

Generated: 2026-08-17T16:43:52Z by `measurements/aggregate.py` -- this file is a **derived rollup**, not append-only evidence itself; re-run the aggregator to refresh it (see `measurements/README.md`).

Rolls up every `sim/*/records/*.md` and `layout/*/reports/*/record.md` evidence record into one table, keyed by `spec/target-spec.md` row number. **No row below is a PLL result.** `spec/target-spec.md` has no ratified numeric row yet (row 0, the supply flavor, is the only ratified row -- see `DR-001`, #1), and no evidence record in this repo currently cites a spec row (see `measurements/README.md` for the citation convention a future PLL evidence record uses to appear here). Every row therefore reads "No evidence" until that changes; the evidence this repo does have today is listed in the appendix below, to prove the rollup mechanism itself works, not to claim a PLL result.

## Per-spec-row summary

| Row | Parameter | DRAFT target (unratified except row 0 -- see spec/target-spec.md) | Evidence | Verdict | Citation |
|---|---|---|---|---|---|
| 0 | Supply flavor | 1.8 V core (`nfet_01v8`/`pfet_01v8`) — **RATIFIED 2026-08-13 (DR-001, #1)** | No evidence | -- | -- |
| 1 | Supply range | 1.8 V ±10 % (1.62–1.98 V) *if* 1.8 V core | No evidence | -- | -- |
| 2 | Output band | 10 – 200 MHz continuous, **carried from gf180-pll and NOT assumed to hold** | No evidence | -- | -- |
| 3 | Reference input | 1 – 25 MHz, CMOS square wave, rising-edge triggered, duty 30–70 % | No evidence | -- | -- |
| 4 | Multiplication ratio | N = 4 – 64, every integer, static configuration | No evidence | -- | -- |
| 5 | Kvco | ≤ a fixed-filter-compatible bound (gf180-pll used ≤ 150 MHz/V) | No evidence | -- | -- |
| 6 | Loop bandwidth | f_c well below f_ref, hard ceiling `f_c < f_ref/10` | No evidence | -- | -- |
| 7 | Phase margin | ≥ 45° everywhere in the contracted space | No evidence | -- | -- |
| 8 | Lock time | < 100 µs to a stated lock criterion | No evidence | -- | -- |
| 9 | Period jitter | ≤ 1.0 % of the output period, RMS, conditional on a stated supply-ripple limit | No evidence | -- | -- |
| 10 | Reference spur | ≤ −55 dBc (candidate) | No evidence | -- | -- |
| 11 | Integrated RMS jitter / phase noise | **not spec'd** — derived-only, deliberately visible | No evidence | -- | -- |
| 12 | Power | a budget at a stated frequency (gf180-pll used < 5 mW at 100 MHz on 3.3 V) | No evidence | -- | -- |
| 13 | Supply sensitivity | supply-ripple limit + a DC-excursion Vctrl budget | No evidence | -- | -- |
| 14 | Output duty cycle | 45 – 55 % at CLK, whole band, all corners | No evidence | -- | -- |
| 15 | Output levels and drive | rail-to-rail CMOS, V_OH ≥ 0.9·VDD / V_OL ≤ 0.1·VDD into a stated load | No evidence | -- | -- |
| 16 | Lock detector | digital `lock` output; assert window + hysteresis criteria | No evidence | -- | -- |
| 17 | Standby / power-down | no power-down mode in v1 (always-on) | No evidence | -- | -- |
| 18 | Area | a budget, not a result (no layout exists) | No evidence | -- | -- |

## Evidence found, not yet mapped to a spec row

Harness-plumbing and other non-PLL-claim evidence discovered by the scan above, listed here rather than silently dropped -- this is what currently proves the rollup mechanism reads real records correctly.

| Kind | Block | Record | Claim | Verdict | Detail | Citation |
|---|---|---|---|---|---|---|
| sim | pdk-smoke | 20260814-022011-dcd6160 | harness self-test -- proves xschem netlisting + sim/harness PVT-point substitution (process corner, supply, temperature) + ngspice execution work end-to-end ag… | PASS | 27/27 points passed | `sim/pdk-smoke/records/20260814-022011-dcd6160.md` |
| layout | trivial-cell | 20260814-020940-aa2de71 | Trivial-cell proof of the `klt`-driven DRC/LVS flow (issue #2) -- **not** PLL-block layout, which is a later issue's scope (there is no PLL schematic yet). | PASS | 6/6 checks passed | `layout/trivial-cell/reports/20260814-020940-aa2de71/record.md` |

## Scan summary

- Evidence records scanned: 2
- Current (non-superseded): 2
- Superseded (excluded from the tables above; still retained, append-only, under `sim/`/`layout/`): 0
