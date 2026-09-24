# PLL characterization report

Generated: 2026-09-24T23:43:05Z by `measurements/aggregate.py` -- this file is a **derived rollup**, not append-only evidence itself; re-run the aggregator to refresh it (see `measurements/README.md`).

Rolls up every `sim/*/records/*.md` and `layout/*/reports/*/record.md` evidence record into one table, keyed by `spec/target-spec.md` row number. **A populated row is not a passing row.** Rows 0, 1, 9, 19 and 20 of `spec/target-spec.md` are ratified (`DR-001`/`DR-002`/`DR-003`/`DR-006`); every other numeric row an evidence record appears against is still DRAFT. For a DRAFT row, a record listed against it is *evidence bearing on that row* -- the measured input a future decision record would argue the row from -- never a verdict on it, and never a substitute for the ratification act itself. For a **ratified** row the record's verdict does grade against a binding bound, and a FAIL there is a recorded miss against the spec (never a reason to relax it -- see `CLAUDE.md`). Read each record before quoting it either way: its own `Verdict` column here is the record's overall pass/fail, which for several campaigns means "the harness ran and recorded what happened", including recorded non-lock.

## Per-spec-row summary

| Row | Parameter | DRAFT target (unratified except rows 0/1/9/19/20 -- see spec/target-spec.md) | Evidence | Verdict | Citation |
|---|---|---|---|---|---|
| 0 | Supply flavor | 1.8 V core (`nfet_01v8`/`pfet_01v8`) — **RATIFIED 2026-08-13 (DR-001, #1)** | No evidence | -- | -- |
| 1 | Supply range | 1.8 V ±10 % (1.62–1.98 V) — **RATIFIED 2026-08-19 (DR-002, #19)** | No evidence | -- | -- |
| 2 | Output band | 10 – 200 MHz continuous, **carried from gf180-pll and NOT assumed to hold** | sim/vco (20260819-131741-fe0e6df) | PASS | `sim/vco/records/20260819-131741-fe0e6df.md` -- rows via `sim/vco/testbench/tb.json` |
|  |  |  | sim/vco (20260904-163130-f3ae976) | PASS | `sim/vco/records/20260904-163130-f3ae976.md` -- rows via `sim/vco/testbench/tb.json` |
| 3 | Reference input | 1 – 25 MHz, CMOS square wave, rising-edge triggered, duty 30–70 % | sim/pll-lock-1mhz (20260904-152129-f00ce3e) | FAIL | `sim/pll-lock-1mhz/records/20260904-152129-f00ce3e.md` -- rows via `sim/pll-lock-1mhz/testbench/tb.json` |
|  |  |  | sim/pll-lock-25mhz (20260904-152213-f00ce3e) | FAIL | `sim/pll-lock-25mhz/records/20260904-152213-f00ce3e.md` -- rows via `sim/pll-lock-25mhz/testbench/tb.json` |
| 4 | Multiplication ratio | N = 4 – 64, every integer, static configuration | sim/divider (20260910-234943-ec91425) | PASS | `sim/divider/records/20260910-234943-ec91425.md` |
|  |  |  | sim/divider-n4 (20260911-091838-7d2f839) | PASS | `sim/divider-n4/records/20260911-091838-7d2f839.md` |
|  |  |  | sim/divider-n5 (20260911-095824-7d2f839) | PASS | `sim/divider-n5/records/20260911-095824-7d2f839.md` |
|  |  |  | sim/divider-n5 (20260911-100824-7d2f839) | PASS | `sim/divider-n5/records/20260911-100824-7d2f839.md` |
|  |  |  | sim/divider-n5 (20260919-023351-32f268f) | PASS | `sim/divider-n5/records/20260919-023351-32f268f.md` |
|  |  |  | sim/divider-n63 (20260911-101042-7d2f839) | PASS | `sim/divider-n63/records/20260911-101042-7d2f839.md` |
|  |  |  | sim/divider-n63 (20260911-104153-7d2f839) | PASS | `sim/divider-n63/records/20260911-104153-7d2f839.md` |
|  |  |  | sim/divider-n64 (20260911-074438-073b241) | PASS | `sim/divider-n64/records/20260911-074438-073b241.md` |
|  |  |  | sim/divider-n64 (20260911-101305-7d2f839) | PASS | `sim/divider-n64/records/20260911-101305-7d2f839.md` |
|  |  |  | sim/divider-n64 (20260911-104400-7d2f839) | PASS | `sim/divider-n64/records/20260911-104400-7d2f839.md` |
|  |  |  | sim/divider-n64 (20260911-125347-aa4478c) | PASS | `sim/divider-n64/records/20260911-125347-aa4478c.md` |
|  |  |  | sim/divider-n64 (20260911-160518-3b65794) | PASS | `sim/divider-n64/records/20260911-160518-3b65794.md` |
|  |  |  | sim/divider-n64 (20260911-171337-fbf217b) | PASS | `sim/divider-n64/records/20260911-171337-fbf217b.md` |
|  |  |  | sim/divider-n64 (20260911-180406-071a336) | PASS | `sim/divider-n64/records/20260911-180406-071a336.md` |
| 5 | Kvco | ≤ a fixed-filter-compatible bound (gf180-pll used ≤ 150 MHz/V) | sim/vco (20260819-131741-fe0e6df) | PASS | `sim/vco/records/20260819-131741-fe0e6df.md` -- rows via `sim/vco/testbench/tb.json` |
|  |  |  | sim/vco (20260904-163130-f3ae976) | PASS | `sim/vco/records/20260904-163130-f3ae976.md` -- rows via `sim/vco/testbench/tb.json` |
| 6 | Loop bandwidth | f_c well below f_ref, hard ceiling `f_c < f_ref/10` | sim/loop-ac (20260904-204534-3fcd920) | PASS | `sim/loop-ac/records/20260904-204534-3fcd920.md` -- rows via `sim/loop-ac/testbench/tb.json` |
| 7 | Phase margin | ≥ 45° everywhere in the contracted space | sim/loop-ac (20260904-204534-3fcd920) | PASS | `sim/loop-ac/records/20260904-204534-3fcd920.md` -- rows via `sim/loop-ac/testbench/tb.json` |
| 8 | Lock time | < 100 µs to a stated lock criterion | sim/pll-lock (20260904-165409-f3ae976) | FAIL | `sim/pll-lock/records/20260904-165409-f3ae976.md` -- rows via `sim/pll-lock/testbench/tb.json` |
|  |  |  | sim/pll-lock (20260905-193322-0f1934d) | FAIL | `sim/pll-lock/records/20260905-193322-0f1934d.md` -- rows via `sim/pll-lock/testbench/tb.json` |
|  |  |  | sim/pll-lock-1mhz (20260904-152129-f00ce3e) | FAIL | `sim/pll-lock-1mhz/records/20260904-152129-f00ce3e.md` -- rows via `sim/pll-lock-1mhz/testbench/tb.json` |
|  |  |  | sim/pll-lock-25mhz (20260904-152213-f00ce3e) | FAIL | `sim/pll-lock-25mhz/records/20260904-152213-f00ce3e.md` -- rows via `sim/pll-lock-25mhz/testbench/tb.json` |
| 9 | Period jitter | ≤ 1.0 % of the output period, RMS, at `CLK` in lock, under a **DC-quiet supply** within row 1's ran… | sim/pll-lock-mc (20260924-222341-a9375a5) | FAIL | `sim/pll-lock-mc/records/20260924-222341-a9375a5.md` |
| 10 | Reference spur | ≤ −55 dBc (candidate) — **DRAFT by explicit decision (DR-006, #151)**, not by omission | No evidence | -- | -- |
| 11 | Integrated RMS jitter / phase noise | **not spec'd** — derived-only, deliberately visible | No evidence | -- | -- |
| 12 | Power | a budget at a stated frequency (gf180-pll used < 5 mW at 100 MHz on 3.3 V) | No evidence | -- | -- |
| 13 | Supply sensitivity | supply-ripple limit + a DC-excursion Vctrl budget — **DRAFT by explicit decision (DR-006, #151)**,… | sim/vco-supply-pushing (20260923-141525-e514bb0) | PASS | `sim/vco-supply-pushing/records/20260923-141525-e514bb0.md` |
| 14 | Output duty cycle | 45 – 55 % at CLK, whole band, all corners | sim/pll-lock (20260904-165409-f3ae976) | FAIL | `sim/pll-lock/records/20260904-165409-f3ae976.md` -- rows via `sim/pll-lock/testbench/tb.json` |
|  |  |  | sim/pll-lock (20260905-193322-0f1934d) | FAIL | `sim/pll-lock/records/20260905-193322-0f1934d.md` -- rows via `sim/pll-lock/testbench/tb.json` |
|  |  |  | sim/pll-lock-1mhz (20260904-152129-f00ce3e) | FAIL | `sim/pll-lock-1mhz/records/20260904-152129-f00ce3e.md` -- rows via `sim/pll-lock-1mhz/testbench/tb.json` |
|  |  |  | sim/pll-lock-25mhz (20260904-152213-f00ce3e) | FAIL | `sim/pll-lock-25mhz/records/20260904-152213-f00ce3e.md` -- rows via `sim/pll-lock-25mhz/testbench/tb.json` |
| 15 | Output levels and drive | rail-to-rail CMOS, V_OH ≥ 0.9·VDD / V_OL ≤ 0.1·VDD into a stated load | No evidence | -- | -- |
| 16 | Lock detector | digital `lock` output; assert window + hysteresis criteria | No evidence | -- | -- |
| 17 | Standby / power-down | no power-down mode in v1 (always-on) | No evidence | -- | -- |
| 18 | Area | a budget, not a result (no layout exists) | No evidence | -- | -- |
| 19 | Process corners | sky130's five standard MOS/BJT process corners: `tt`, `ff`, `ss`, `sf`, `fs` — **RATIFIED 2026-08-2… | No evidence | -- | -- |
| 20 | Operating temperature range | −40 °C to 125 °C, sampled at −40 / 27 / 125 °C — **RATIFIED 2026-08-27 (DR-003, #77)** | No evidence | -- | -- |

## Evidence found, not mapped to a spec row

Harness-plumbing evidence, negative controls, and anything whose citation does not resolve to a row of `spec/target-spec.md` -- listed here rather than silently dropped. The **Why unmapped** column says which: a record that *declares* it measures no spec row is doing the right thing, while `no spec-row declaration found` or `malformed ...` is a gap to close (see `measurements/README.md`).

| Kind | Block | Record | Claim | Verdict | Detail | Why unmapped | Citation |
|---|---|---|---|---|---|---|---|
| sim | pdk-smoke | 20260814-022011-dcd6160 | harness self-test -- proves xschem netlisting + sim/harness PVT-point substitution (process corner, supply, temperature) + ngspice execution work end-to-end ag… | PASS | 27/27 points passed | declares it measures no spec row (declared by `sim/pdk-smoke/testbench/tb.json`; the record itself predates the citation convention and is append-only) | `sim/pdk-smoke/records/20260814-022011-dcd6160.md` |
| sim | pdk-smoke | 20260817-171010-7823a49 | harness self-test -- proves sim/harness's Monte Carlo trial generation + sky130 MC_MM_SWITCH/MC_PR_SWITCH statistical-sampling patching + ngspice execution wor… | PASS | 10/10 trials passed | declares it measures no spec row (declared by `sim/pdk-smoke/testbench/tb.json`; the record itself predates the citation convention and is append-only) | `sim/pdk-smoke/records/20260817-171010-7823a49.md` |
| sim | pll | 20260819-123508-fe0e6df | first PLL-specific harness campaign -- proves xschem netlisting + sim/harness PVT-point substitution (process corner, supply, temperature) + ngspice execution… | FAIL | 17/27 points passed | declares it measures no spec row (declared by `sim/pll/testbench/tb.json`; the record itself predates the citation convention and is append-only) | `sim/pll/records/20260819-123508-fe0e6df.md` |
| layout | pll | 20260924-041509-c53e7c4 | Device-level layout of the closed-loop PLL schematic (`design/top/netlist/top.spice`), drawn by `layout/bin/run-pll-layout-flow.sh` (issue #16). Read this file… | PASS | 8/8 checks passed | declares it measures no spec row (cited by the record itself) | `layout/pll/reports/20260924-041509-c53e7c4/record.md` |
| layout | trivial-cell | 20260924-041449-c53e7c4 | Trivial-cell proof of the `klt`-driven DRC/LVS flow (issue #2) -- **not** PLL-block layout, which is a later issue's scope (there is no PLL schematic yet). - *… | PASS | 6/6 checks passed | declares it measures no spec row (cited by the record itself) | `layout/trivial-cell/reports/20260924-041449-c53e7c4/record.md` |

## Scan summary

- Evidence records scanned: 45
- Current (non-superseded): 28
- Superseded (excluded from the tables above; still retained, append-only, under `sim/`/`layout/`): 17
- Spec-row citation stated by the record itself: 18
- Spec-row citation resolved from the experiment's own declaration (`sim/<slug>/testbench/tb.json` / `layout/<block>/spec-rows.json`) because the record predates the convention and is append-only: 10
- **Current records with no spec-row declaration at all: 0**
