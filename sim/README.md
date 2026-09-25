# sim/ — evidence record format

This directory holds simulation testbenches and their results. Results are
**append-only evidence**: once a record is written, it is never edited or
deleted. A re-run — even one that corrects a mistake — mints a new record
with a new ID; a correction references the record it supersedes rather than
overwriting it in place.

This convention exists because `CLAUDE.md` commits this repo to two rules
that need a concrete schema to be enforceable:

- **Verification is the product.** No claim without a testbench.
- **`sim/` is append-only evidence.** Re-runs get new records; records are
  never edited or deleted.

## Provenance of this convention

Adapted from `2AMLogic/gf180-pll`'s `sim/README.md`
(source commit `d6115c79f9d41140341c4666256b659151a824db`), which itself
adapts the convention `2AMLogic/gf180-bandgap` ratified. Per this repo's
`CLAUDE.md` harness-bootstrap rule (copy the sister-repo pattern rather than
reinventing).

**Scoped down for issue #2.** gf180-pll's version documents an entire mature
PLL verification campaign table (lock-time, jitter, divider-ratio, ...) —
none of that exists here yet. This file keeps the schema and the
append-only/retention/no-fabricated-evidence rules gf180-pll ratified, and
drops the campaign-specific sections (closed-loop assembly paths, the PFD
internal-timestep bound, etc.) that do not apply until there is a PLL
schematic. Those return, adapted, when the campaigns that need them land.

## Directory / naming convention

Each testbench topic gets its own experiment directory:

```
sim/
  <experiment-slug>/                 # e.g. pdk-smoke
    testbench/                       # tb.json manifest + xschem schematic(s)
    netlist-snapshots/
      <record-id>.spice              # frozen DUT netlist used for this record
    corners/
      <record-id>/
        <corner-id>.spice            # patched per-point netlist
        <corner-id>.log              # raw ngspice output per PVT point
    records/
      <record-id>.md                 # append-only summary record
    analysis/                        # optional, mutable -- see below
```

- **`analysis/`** is optional and, like `testbench/`, **mutable**: stdlib-only
  scripts that *read a committed record and restate what it already says*, for
  a derived quantity the record's own generated tables cannot express. It is
  not an evidence directory — nothing under it simulates, measures, or
  introduces a number that is not already in the record it was handed, and a
  record stays readable without it. The case that introduced it
  (`sim/vco-supply-pushing`, issue #165) is a quantity that is **cross-point**:
  supply pushing lives across the three PVT rows sharing a (corner,
  temperature, `VCTRL`) triple, and `sim/harness/report.py` renders one row per
  point. A script there must offer a `--check` mode that re-derives its output
  and fails on any drift, so a reader can re-verify the derivation against the
  record long after the run. The second user (`sim/pll-lock-mc/analysis/`,
  issue #179) is a different shape of the same rule: it restates a Monte Carlo
  record's per-trial table as the sample-set document `klt yield` consumes, so
  that campaign's yield estimate, confidence interval, Cpk and sample-size
  verdict become machine-readable — quantities a per-trial table cannot
  express, derived entirely from figures that table already carries. The third
  (`sim/pll-lock-mc/analysis/jitter_floor.py`, issue #178) is the first to read
  **two** campaigns' records: it restates this campaign's measured period jitter
  against the measurement floor `sim/jitter-floor`'s records report, which is a
  quantity neither campaign's own table can express because it is a relation
  between them. The fourth (`sim/jitter-calibration/analysis/calibration.py`,
  issue #185) pushes the "read from the record's own netlist" allowance to its
  limit, and states why that is still inside the rule: the quantity it needs is
  the jitter its campaign *injected*, and that quantity is not a number written
  in prose anywhere — it is the committed per-point netlist's own PWL edge
  schedule, from which the script re-derives it with the same estimator
  `measure.period_jitter` applies to the reduced edges. Reading it there is what
  makes the injected figure checkable evidence rather than a claim about a
  generator script. The fifth (`sim/vco-clk-transition/analysis/bracket_floor.py`,
  issue #186) reads **two** campaigns' records again, the same shape as the
  third: it locates this design's own measured transition-time figure among
  `sim/jitter-floor`'s own edge/grid-step ratios and states the bracket that
  follows from the fact that the family's A3/B/C variants are a *measured*,
  monotonically decreasing function of that ratio at one shared period —
  turning a family spanning the whole floor range (0.000–2.371 %) into the
  specific two-variant bracket this design's real `CLK` actually falls in. The
  rule is otherwise unchanged — it simulates nothing, and every figure it
  prints is read from a committed record (or from that record's own committed
  per-point netlist, for the numbers that define a floor variant, an injected
  schedule, or a measured transition time), with the same mandatory `--check`
  mode.

- **`<experiment-slug>`** — short, descriptive, kebab-case name for what is
  being verified. One directory per distinct claim, not per run.

  | Slug | Claim under test | Issue |
  |---|---|---|
  | `pdk-smoke` | does xschem+ngspice+sky130 run this DUT to completion across a real process/temperature/supply sweep — the harness's own plumbing self-test, not a PLL design claim | #2 |
  | `pdk-smoke` (`--mc`) | does the sky130 `MC_MM_SWITCH`/`MC_PR_SWITCH` statistical-sampling mechanism run this DUT to completion, seed by seed — the Monte Carlo harness's own plumbing self-test, not a PLL statistical-spec claim | #20 |
  | `pll` | does the four-block closed-loop PLL netlist (`design/top/top.sch` — VCO + PFD/charge pump + loop filter + divider) netlist and simulate to completion across a real process/temperature/supply sweep — the first PLL-specific campaign, still a plumbing claim (no `spec/target-spec.md` row is ratified yet, and the transient window is far short of the loop's cold-start lock time), not a lock-time, frequency, or jitter claim | #23 |
  | `pll-lock` | does the closed-loop PLL, driven cold-start from `design/top/top.sch`'s own power-on reset, lock its output to `N * Fref` within a real (multi-microsecond, not 200 ns) transient window — a measurement claim (output frequency, duty cycle, time-to-lock, or explicit no-lock), extracted via `sim/harness/measure.py`. Drives a 10 MHz reference, `NSEL[5:0]`=`N`=25 (target 250 MHz) | #52 |
  | `pll-lock-1mhz` | sibling of `pll-lock`, same DUT and measurement layer, driven at spec row 3's DRAFT low reference-frequency band edge (1 MHz) instead of 10 MHz — `NSEL[5:0]`=`N`=64 (the divider's maximum representable ratio, target 64 MHz), the closest achievable target to `sim/vco/records/`'s characterized VCO tuning floor (~145.1 MHz) given the divider's `N<=64` ceiling; exercises spec row 3's frequency-range claim at more than the single 10 MHz point `pll-lock` drives | #55 |
  | `pll-lock-25mhz` | sibling of `pll-lock`, same DUT and measurement layer, driven at spec row 3's DRAFT high reference-frequency band edge (25 MHz) instead of 10 MHz — `NSEL[5:0]`=`N`=10 (target 250 MHz, deliberately the same target `pll-lock` uses, isolating the effect of reference frequency alone) | #55 |
  | `pll-lock-mc` | Monte Carlo statistical companion to `pll-lock`: same DUT, same `DR-005` cold start and same lock criterion, but run as a `--mc` campaign — many trials at ONE fixed PVT point (`tt`/125 °C/1.80 V), each trial resampling sky130's `MC_MM_SWITCH` (within-die mismatch) + `MC_PR_SWITCH` (die-to-die process) draws from its own RNG seed — reduced by `sim/harness/measure.py`'s `period_jitter` once a trial locks. This is the statistical half of the verification `DR-006` names for **ratified** spec row 9 (period jitter ≤ 1.0 % of the output period, RMS, at `CLK` in lock); `pll-lock`'s own grid is the deterministic half. The window is 50 µs, not `pll-lock`'s 100 µs, because this campaign buys post-lock population for a post-lock quantity rather than the full row-8 cold-start budget — see the manifest's `monte_carlo.methodology_note` for that trade, for why the base point is `tt`/125 °C (the one point with a documented cold-start lock under this nudge convention) and for the 200 ps dump-grid resolution floor a reader of a jitter number is owed. **Run and recorded**: `sim/pll-lock-mc/records/20260924-222341-a9375a5.md` (2/5 trials PASS — 3 of 5 draws lock, and **all three measure period jitter above row 9's ratified 1.0 % bound**: 1.584 %, 1.851 %, 3.073 %. A recorded miss against a ratified row, per `CLAUDE.md`, read together with the resolution-floor caveat the record states). **Graded**: `sim/pll-lock-mc/analysis/` restates that record as a `klt yield` sample set and commits the resulting report — 0 % empirical yield, 95 % CI [0, 0.7076], `cpk` −0.491, and the tool's own `sample_size.verdict: insufficient` (`n` = 3, `required_n` = 183). That report is deliberately **not** cited for T1 item 6; `signoff/README.md` § "Why every other row is `unmet`" records why | #20, #179 |
  | `jitter-floor` | the **measurement-resolution floor** `sim/harness/measure.py`'s own period-jitter reducer carries at a stated dump grid — a harness negative control (a *null* control), not a PLL design claim. The DUT is an ideal pulse voltage source and a load resistor, no sky130 device at all, so `v(CLK)` is a trapezoid of exactly constant period whose true period jitter is **zero by construction**; it is pushed through the identical `linearize` → `wrdata` → `edge_times` → `period_jitter` path a `pll-lock-mc` trial is reduced by, at the same 200 ps grid and 50 µs window, so whatever jitter the reducer reports for it is the floor. Run as a family of variants (each record names its own, and its committed `corners/<record-id>/*.spice` pins it): the floor is **0.000 %** for an edge spanning five grid steps, 0.610 % at one step, and 0.381–2.371 % for an edge a tenth of a step, at the three periods `pll-lock-mc`'s locked draws measured. **Run and recorded**: `sim/jitter-floor/records/20260925-022153-30889a3.md` (A1), `20260925-022310-30889a3.md` (A2), `20260925-022043-30889a3.md` (A3), `20260925-022424-30889a3.md` (B), `20260925-022516-30889a3.md` (C) — 1/1 PASS each. Read with `sim/pll-lock-mc/analysis/jitter-floor/restatement.md`, which restates that campaign's three measured figures against these floors | #178 |
  | `jitter-calibration` | the **transfer** of a known period-jitter figure through the same reducer — the sibling of `jitter-floor` one step on, and a *known-bad* control rather than a null one. Same shape of DUT (an ideal source and a load resistor, no sky130 device), same `linearize` → `wrdata` → `edge_times` → `period_jitter` path, same 200 ps grid and 3.9170 ns nominal period; the difference is that this source's rising-edge schedule is drawn from a seeded RNG at an **exactly specified nonzero** RMS period jitter and written edge by edge into the netlist, so the injected figure is a re-derivable property of the committed evidence rather than a claim about a generator. Reported-against-injected over the family is a **calibration curve**: a measured figure can be read back toward a true one, where a floor only bounds it from below. Run as 3 injected values (0.5 %, 1.0 %, 2.0 % RMS) × 3 transition times (20 ps / 200 ps / 1 ns, the same edge family `jitter-floor` uses), 300 cycles each. **Run and recorded**, 1/1 PASS each: `20260925-103212-518b31f` (J05a), `20260925-103238-518b31f` (J05b), `20260925-103303-518b31f` (J05c), `20260925-103326-518b31f` (J10a), `20260925-103348-518b31f` (J10b), `20260925-103409-518b31f` (J10c), `20260925-103435-518b31f` (J20a), `20260925-103459-518b31f` (J20b), `20260925-103526-518b31f` (J20c). The headline: at an edge the grid resolves the reducer returns the injected figure **exactly** (0.500 / 1.000 / 2.000 %), and at one it cannot the reported figure is inflated 1.4×–4.8×. Read with `sim/jitter-calibration/analysis/calibration.md`, which tabulates the curve and shows the floor a *jittering* signal carries moving away from the constant-period walk-phase figure `jitter-floor` measures and toward the uniformly-spread-phase one as the source's jitter grows — i.e. the null control's floor is a different quantity from this one, not a conservative version of it | #185 |
  | `vco-clk-transition` | the **measured 10–90 % rise/fall transition time** of `design/vco/vco_ring5.sch`'s own `CLK`, open loop, at the fixed VCTRL (0.865 V) that puts the ring near the row-9 operating point — the missing input that makes `jitter-floor`'s edge/grid-step family readable against this design's real clock rather than only against an assumed one. A single fixed-VCTRL point (`tt`/125 °C/1.80 V, `sim/pll-lock-mc`'s own base corner), dumped at a fine 5 ps grid (well under the ~50–60 ps edge it resolves) over a 200 ns window, reduced by `sim/harness/measure.py`'s new `measure.transition` block (`transition_times`, issue #186) rather than a one-off script. **Run and recorded**: `sim/vco-clk-transition/records/20260925-110645-810cd82.md` (1/1 PASS — 259.6 MHz, rise 62.14 ps (37 edges), fall 53.37 ps (36 edges)). Read with `sim/vco-clk-transition/analysis/bracket.md`, which reads that figure against `jitter-floor`'s own measured, monotonic A3/B/C triple (one shared period, three edge/grid-step ratios) and states the bracket it implies: this design's own edge/step ratio (0.267–0.311×) sits strictly between A3's (0.1×, 2.371 %) and B's (1.0×, 0.610 %) — the family's **unresolved-edge** regime, not variant C's fully-resolved 0.000 % — so a reader of `sim/pll-lock-mc`'s measured period-jitter figures has a real bound (0.610 %–2.371 %) rather than the whole family's span | #186 |
  | `loop-ripple` | how large is the closed-loop PLL's own self-generated disturbance, in lock, on its shared `VDD` rail and on `VCTRL` — `DR-006`'s row 13 Budget 1 transient ripple measurement. Same DUT (`design/top/top.sch`), `DR-005` cold start, 100 µs window and lock criterion as `pll-lock`, but the ideal supply feeds the block's `VDD` through a 1 Ω resistive power-delivery stand-in (`RPDN`, a testbench assumption — without it `v(VDD)` ripple is zero by construction); reports `v(VDD)` and `v(VCTRL)` peak-to-peak over the final 5 µs via `sim/harness/measure.py`'s `ripple_pp`, labelled with whether that window was in lock. **Testbench only, no record yet** — see the manifest's `methodology_note` for the supply model, bandwidth and cost caveats (inherits `pll-lock`'s per-point cost, issue #103) | #166 |
  | `vco` | frequency-vs-`VCTRL` characterization of `design/vco/vco_ring5.sch` alone (open loop, no PFD/charge pump/loop filter/divider), replacing the informal single-corner sanity check `design/vco/DESIGN.md` disclaims with real committed `sim/` evidence across the full PVT matrix | #52 |
  | `vco-supply-pushing` | sibling of `vco`, same DUT and open-loop harness, opposite independent variable: `VCTRL` is held FIXED at four operating points (0.8, 0.9, 1.2, 1.5 V) while `VDD` is the swept quantity, supplied by the corner runner's own 1.62/1.80/1.98 V axis — frequency-vs-`VDD` supply-pushing characterization (fractional `%/V`), the first of the two prerequisites `DR-006` names for a future ratification of spec row 13 Budget 1 (the AC supply-ripple limit), replacing the 1.67x realized-over-floor ratio borrowed from gf180-pll. The cross-point `%/V` derivation (`sim/vco-supply-pushing/analysis/pushing.py`) is appended to the record, not rendered by `sim/harness/report.py` itself. **Run and recorded**: `sim/vco-supply-pushing/records/20260923-141525-e514bb0.md` (45/45 PASS). | #165 |

  | `loop-ac` | linearized open-loop AC characterization of the loop dynamics — unity-gain crossover frequency (row 6, loop bandwidth) and phase margin (row 7), from a real ngspice `ac` sweep of `design/loop-filter/loop_filter.sch`'s own sky130 R/C network, with the charge pump / VCO / divider applied as a swept scalar loop gain `A = Icp*Kvco/N`. Replaces `design/loop-filter/DESIGN.md`'s explicitly hand-calculated, single-design-point, no-stated-corner `f_c` and phase-margin figures with committed `sim/` evidence. It is the AC/linearized-model testbench `sim/harness/measure.py`'s own docstring defers these two rows to | #52 |
  | `divider` | does the standalone programmable integer-N feedback divider (`design/divider/divider_intN.sch`, retimed to a dual-modulus /2-/3 prescaler front-end by issue #114) divide a fixed ~1.10 GHz ideal CLK — at or above the VCO's own characterized top free-running frequency — by N=25 (`NSEL[5:0]`=`011000`, the same modulus `sim/pll-lock` straps) cleanly across the full PVT corner matrix, turning `design/divider/DESIGN.md`'s informal, uncommitted "Issue #114" diagnostic table into a committed `sim/` evidence record. **Run and recorded**: `sim/divider/records/20260910-234943-ec91425.md` (45/45 PASS). | #129 |
  | `divider-n4` | sibling of `divider`, same DUT and open-loop method, straps N=4 (`NSEL[5:0]`=`000011`) at 250 MHz — the DRAFT modulus range's floor (spec/target-spec.md row 4) and the smallest modulus on the divider's even decode path. **Run and recorded**: `sim/divider-n4/records/20260911-091838-7d2f839.md` (full DR-003 45-point grid, 45/45 PASS). | #129, #131 |
  | `divider-n64` | sibling of `divider`, same DUT and open-loop method, straps N=64 (`NSEL[5:0]`=`111111`) at 250 MHz — the DRAFT modulus range's ceiling and the largest modulus on the even decode path; N=64's long output period makes a full 45-point grid impractical in one pass (see the manifest's own `methodology_note`), so this campaign accumulated its coverage one process-corner row at a time. **Run and recorded — the full DR-003 45-point grid is now complete, 45/45 PASS, across seven append-only records**: `sim/divider-n64/records/20260911-074438-073b241.md` (issue #130 — the full `tt` process-corner row, 3 temps x 3 supplies, 9/9 PASS), `sim/divider-n64/records/20260911-101305-7d2f839.md` (issue #131 — tt/27 °C/1.80 V, 1/1 PASS; **adds no distinct point** — it independently reproduces a point the `tt` row already covers, and is retained under the append-only rule rather than counted as coverage), `sim/divider-n64/records/20260911-104400-7d2f839.md` (issue #131 — ss/125 °C, full local supply axis, 3/3 PASS; the first `ss` evidence here), `sim/divider-n64/records/20260911-125347-aa4478c.md` (issue #130 — the full `ff` process-corner row, 3 temps x 3 supplies, 9/9 PASS), `sim/divider-n64/records/20260911-160518-3b65794.md` (issue #130 — the `ss` row's remaining -40 °C/27 °C temperatures, 3 supplies each, 6/6 PASS, completing the `ss` row), `sim/divider-n64/records/20260911-171337-fbf217b.md` (issue #130 — the full `sf` process-corner row, 3 temps x 3 supplies, 9/9 PASS) and `sim/divider-n64/records/20260911-180406-071a336.md` (issue #130 — the full `fs` process-corner row, 3 temps x 3 supplies, 9/9 PASS, completing the grid). Their union is exactly the 45 distinct (corner, temperature, supply) points of the DR-003 grid, with no point missing and no FAIL row. No consolidating record supersedes them: each is a real run of a real subset, and the append-only rule keeps all seven as written. See `design/divider/DESIGN.md`'s "The `sim/divider-n64` overlap" subsection for how the two campaigns' coverage is reconciled. | #129, #130, #131 |
  | `divider-n5` | sibling of `divider`, same DUT and open-loop method, straps N=5 (`NSEL[5:0]`=`000100`) at 250 MHz — the smallest *odd* modulus in the DRAFT range, exercising the divider's odd (one-/3-period) decode path the N=4/N=64 records do not. **Run and recorded**: `sim/divider-n5/records/20260911-095824-7d2f839.md` (tt/27 °C/1.80 V, 1/1 PASS) and `sim/divider-n5/records/20260911-100824-7d2f839.md` (ss/125 °C, default supply tolerance, 3/3 PASS) — together covering issue #129's two named corners. | #129, #131 |
  | `divider-n63` | sibling of `divider`, same DUT and open-loop method, straps N=63 (`NSEL[5:0]`=`111110`) at 250 MHz — the largest odd modulus in the DRAFT range; like `divider-n64`, its long output period makes a full grid impractical in one pass. **Run and recorded**: `sim/divider-n63/records/20260911-101042-7d2f839.md` (tt/27 °C/1.80 V, 1/1 PASS) and `sim/divider-n63/records/20260911-104153-7d2f839.md` (ss/125 °C, default supply tolerance, 3/3 PASS) — together covering issue #129's two named corners as a documented subset. Widening this campaign to the full 45-point grid was the *optional* half of issue #130 ("if convenient while touched") and has not been attempted — `divider-n64`, the other long-output-period sibling, absorbed that issue's whole compute budget and is now complete at 45/45. | #129, #130, #131 |

  New campaigns add rows here as they are created; the list is descriptive,
  not a closed set.

- **`<record-id>`** — `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` (UTC), this
  repo's `HEAD` when the run started. Re-runs mint a new `<record-id>`;
  nothing under `records/` is ever edited in place. If the tree was dirty at
  run time, the record's **Environment provenance** field says so.

- **`<corner-id>`** — the naming convention depends on what mode produced the
  record, but both share the same `corners/<record-id>/` directory:
  - **PVT points**: `<corner>_<temp>c_<supply>v`, e.g. `ss_-40c_1.62v.log`,
    `tt_27c_1.80v.log`. Supply is written to two decimals.
  - **Monte Carlo trials** (`--mc`, see `sim/harness/README.md`'s Monte Carlo
    section): `mc<trial>_seed<seed>_<lib-corner>_<temp>c_<supply>v`, e.g.
    `mc001_seed1_tt_mm_27c_1.80v.log`. `<lib-corner>` is the `.lib` section
    actually netlisted against (the corner, with `_mm` appended when
    mismatch sampling is enabled).

- **`testbench/`** is not versioned per record — it holds the current
  testbench manifest/schematic used to generate records. A testbench change
  that could affect comparability across records is noted in the next
  record's summary.

## Default corner matrix

Unless a record states otherwise, a result is swept over the grid its own
`tb.json` manifest declares — see `sim/harness/README.md`. `sim/pdk.json`
pins the process-corner names the installed sky130 PDK actually defines
`.lib` sections for (`tt`, `ss`, `ff`, `sf`, `fs`, plus the passive-only `ll`/
`hh` axis); a manifest's `process_corners` must be a subset of that list.

**This repo has no ratified supply flavor yet (#1, `DR-001` — `proposed`).**
A testbench manifest's `supply_nominal`/`supply_tolerance` are that
testbench's own bias, not a spec claim, until #1 ratifies row 0/1 of
`spec/target-spec.md`. Nothing in this harness reads a spec value or gates
pass/fail on one: the corner matrix comes from each manifest, and the
per-point criterion is "did the simulator complete this point". Once #1
ratifies, PLL campaigns state their corner matrix against the ratified
supply range the same way gf180-pll states its 3.3 V ±10 % grid, and cite
the ratifying `DR-NNN` in their records.

Any subset of a manifest's default grid (fewer temperatures, one supply, a
single process corner) is allowed **only** with an in-record justification —
`sim/run_corners.py`'s `--subset-reason` flag is mandatory whenever a
`--corners`/`--temps`/`--supply-tol` override is combined with `--write`, and
its text becomes part of the record. "The sim was slow" is not a
justification; "fast selftest pass proving the harness runs, not a design
claim — see sim/pdk-smoke/records/<id>.md for the full grid" is.

## Interrupted and parallel runs

A campaign's cost is set by its manifest, and some are large: a single
`sim/pll-lock` point runs a 100 us transient with a 3 h `timeout_s`, so its
45-point grid is days of wall clock (issue #133). Two execution-model flags
make such a campaign tractable. Neither changes what a point measures — the
same manifest, the same netlist, the same per-point criterion, the same
record schema — they change only *when* points run and *what survives* an
interruption.

```sh
# Run 8 points at a time instead of one (one ngspice process each).
python3 sim/run_corners.py pll-lock --jobs 8

# ...that run was killed at point 31/45. Finish it, don't restart it:
python3 sim/run_corners.py pll-lock --jobs 8 --resume 20260911-071500-730c24b
```

- **`--jobs N` / `-j N`** (default `1`, i.e. today's serial behaviour) runs
  `N` points (or Monte Carlo trials) concurrently. Points are independent:
  each patches its own copy of the netlisted DUT and runs its own `ngspice
  -b` process, writing only files named after its own `<corner-id>`. The
  record's rows stay in the manifest's point order regardless of which point
  finishes first.

  `N` shares one host. Keep it at or below the free core count: a point
  already close to its manifest's `timeout_s` budget can be pushed past it by
  contention, and that is recorded as a failed point exactly as in a serial
  run. The default stays `1` so no existing invocation changes behaviour.

- **`--resume <record-id>`** finishes an interrupted run instead of
  restarting it. Every completed point is persisted, the instant it
  completes, to `corners/<record-id>/checkpoint.json`; a resume reloads those
  and runs only the points that are missing. The run prints its record id at
  the start (`record id ... -- an interrupted run can be resumed with
  --resume ...`) so it is available before the run finishes.

  A resume is **refused** — loudly, with no record written — if the testbench
  manifest, the netlisted DUT, the resolved PDK build, the run mode or the
  requested point list differ from what the checkpoint was written against.
  Splicing two different campaigns into one record is exactly what the
  append-only rule below exists to prevent, so the harness will not do it
  even when asked.

- **`--executor {local,remote}`** (default `local`, i.e. today's behaviour)
  selects *where* each point's `ngspice -b` process runs: on this host, or
  on klayout-tools' Spot fleet (`--jobs N` becomes the shard count). Like
  the two flags above it is execution-model only — the netlist, the
  per-point criterion, the measurement reducer and the record schema are the
  same code either way, and a `local` record is byte-for-byte the record it
  would have been before the seam existed.

  A remote request that this host cannot honour (no cloud credentials, a
  quota or cost-gate refusal, a lost shard) **falls back to local** with one
  logged line and a `fallback_reason` recorded in the evidence, rather than
  failing the campaign. Full contract, configuration and the reasoning:
  `sim/harness/README.md` → "Where a unit runs"; the committed side-by-side
  local/remote comparison lives in `sim/executor-equivalence/`.

The checkpoint is **run state, not evidence**: it is deleted the moment the
record is written, and it is gitignored (`sim/*/corners/**/checkpoint.json`)
so it can never land in the committed record trail. A checkpoint that still
exists therefore means exactly one thing: *that record id's run was
interrupted and has no record*. Either resume it, or delete it to run that
record id from scratch.

This preserves the append-only contract in both directions: a run produces
**one complete record with every requested point, or no record at all** —
never a record silently missing points, and never one counting a point twice.

## Monte Carlo evidence

`sim/run_corners.py <slug> --mc` (issue #20) runs a statistical-variation
campaign instead of a PVT sweep: many trials at one fixed PVT point, each
sampling sky130's own `MC_MM_SWITCH`/`MC_PR_SWITCH`-gated device variation
with a distinct ngspice RNG seed — see `sim/harness/README.md`'s Monte Carlo
section for the manifest schema and sampling mechanism. Records land in the
same `records/<record-id>.md` / `netlist-snapshots/<record-id>.spice` /
`corners/<record-id>/` tree a PVT record uses (same append-only/retention
rules apply); `sim/harness/report.render_mc` renders a trial table and the
campaign's sampling configuration (base corner, temperature, supply, which
switches were on, trial count and seed range) in place of the PVT per-point
matrix.

**What an `--mc` record supports depends on its manifest, not on the run
mode.** There are exactly two kinds:

- A manifest that **measures nothing** (e.g. `pdk-smoke`'s) yields a harness
  plumbing check — "does the sky130 statistical-sampling mechanism run this
  DUT to completion, seed by seed, with each seed producing a distinct draw?"
  — and nothing more. Its table is `Trial | Seed | Verdict | Detail`.
- A manifest that also declares a `measure` block (e.g. `pll-lock-mc`'s) is
  reduced per trial by exactly the extractor a PVT point of that manifest
  would use, so each trial reports the measured quantities (frequency, duty
  cycle, time-to-lock, period jitter) and a manifest-stated bound a draw
  misses fails that trial. See `sim/harness/README.md`'s Monte Carlo section
  → "Per-trial criterion".

Of `spec/target-spec.md`'s statistical-shaped rows, **row 9 (period jitter) is
now RATIFIED** (`DR-006`, #151) — ≤ 1.0 % of the output period, RMS, at `CLK`
in lock — while reference spur (row 10) and supply sensitivity (row 13) remain
DRAFT. Row 9's extractor landed with #158 (`measure.period_jitter`, wired in
through the manifest's `measure.jitter` block) and the first campaign to use it
is **`pll-lock-mc`** (#20) — the statistical half of the verification `DR-006`
names for that row, a local-mismatch + process draw population at one fixed PVT
point.

`sim/pll-lock-mc/records/20260924-222341-a9375a5.md` is that first record, and
**it records a miss**: of 5 draws at `tt`/125 °C/1.80 V, 3 lock (at 26.32,
38.68 and 48.88 µs) and all 3 measure period jitter *above* the ratified
1.0 % bound — 1.584 %, 1.851 % and 3.073 % RMS. Per `CLAUDE.md` a result that
misses the spec is recorded as a miss; the bound is not relaxed to make it
pass, and `DR-006` stands as written.

Two limits of that record a reader is owed, both argued in the manifest's own
`monte_carlo.methodology_note` rather than left implicit:

- Its **50 µs window** is shorter than row 8's 100 µs cold-start budget, so a
  draw that would lock later is recorded as "no lock within 50 µs" — a limit of
  the window, not a row-8 verdict. Two of the five draws land there.
- The **200 ps dump grid** puts a quantization floor under any jitter figure.
  `measure.py` `linearize`s `v(CLK)` onto the transient's own `tran_step` grid
  before dumping, so each interpolated edge carries a grid error and each
  period inherits it from both ends, against a bound that is 1.0 % of a 4 ns
  period (40 ps). That error is independent per edge and adds in quadrature, so
  it can only *inflate* the measured number: a measured pass is conservative,
  and a measured miss has to be read against the floor's size.

  **That floor is now measured** (`sim/jitter-floor`, issue #178) rather than
  left unquantified, and it did not need a finer-grid re-run of the campaign to
  get at: a null control — an ideal source of exactly constant period, pushed
  through the identical reducer at the identical grid — puts a number on it for
  the price of a 60-second run. It is not one number but a family, and its two
  ends bracket the question:
  **0.000 %** for an edge the grid resolves (five grid steps), and
  **0.381 % / 0.720 % / 2.371 %** for an edge it cannot (a tenth of a step) at
  the three periods this record's locked draws measured.
  `sim/pll-lock-mc/analysis/jitter-floor/restatement.md` restates the three
  measured figures against that family: all three still miss the 1.0 % bound
  with the floor removed in quadrature, and trial 5 still misses it under the
  most pessimistic floor arithmetic allows at this grid (`tran_step/2`, 100 ps).
  **So the recorded miss is not an artefact of the dump grid.** What the null
  control cannot settle is stated there too, and tracked: the floor a signal
  with *real* jitter carries is a different-phase quantity (#185), and
  which end of the family the DUT's own `CLK` sits at needs its transition time
  measured (#186).

  **The first of those two is now measured as well** (`sim/jitter-calibration`,
  issue #185): the same shape of control with a *known, exactly specified,
  nonzero* injected jitter instead of zero, so what comes back out is a
  calibration curve rather than a floor. Its finding is that the difference is
  real and its sign is not what a reader would assume — at this period the null
  control's walk-phase floor (2.371 %, 92.9 ps) is the **larger** of the two
  bounds, and the floor a signal carries moves *down* toward the
  uniformly-spread-phase figure (81.6 ps) as its own jitter grows relative to
  the grid step, so correcting a jittering signal with a null-control floor
  over-corrects it. **The restatement above reads that campaign's records, but
  only for period coverage, and declines to apply its curve** (issue #193): the
  calibration family ran at one nominal period, trial 5's, and the two draws
  (trials 2, 3) that still carry a residual ambiguity after the null-control
  floor ran at different periods it has never visited, so applying it there
  would extrapolate across periods on a quantity the calibration document
  itself says does not transfer by assumption. Issue #197 tracks the run that
  would close that gap. `sim/harness/measure.py`'s jitter docstring records
  what grid a defensible row-9 figure requires, so a future campaign does not
  re-derive it: resolve the edge (`tran_step` ≤ half the measured node's
  transition time), or bound the floor unconditionally at `0.5 * tran_step` —
  20 ps for a floor inside a quarter of row 9's 40 ps budget, against the
  100 ps a 200 ps grid allows.

Row 9's **deterministic** axis — a jitter column across the ratified
rows 19 × 20 × 1 PVT grid — is still owed; `pll-lock`'s manifest does not yet
declare a `measure.jitter` block.

## Summary record format

Each run produces one `records/<record-id>.md` file (see `sim/harness/
report.py`) with these mandatory fields:

- **Record ID** — matches the filename and the corresponding
  `netlist-snapshots/`/`corners/` subdirectory.
- **Claim** — what this record substantiates, taken from the manifest's own
  `claim` field. Until #1 ratifies the spec, no record here can state a
  `spec/target-spec.md` claim (there is nothing ratified to check against
  yet) — every record's claim is a plumbing or design-input claim.
- **Spec row(s)** — which `spec/target-spec.md` row(s) this record supplies
  evidence *toward*, taken from the manifest's own **required** `spec_rows`
  field, or the literal `none -- <why>` when the experiment measures no spec
  row (its `spec_rows_note`). This is the citation `measurements/aggregate.py`
  rolls the characterization report up on; making it a manifest field rather
  than something an author remembers per record is why it is now present on
  every record by construction (issue #152 — see `measurements/README.md`).
  `sim/run_corners.py` refuses to run an experiment whose manifest omits it,
  before resolving the PDK or simulating a point. **Citing a row is not
  claiming it**: rows stay DRAFT until a decision record ratifies them, and
  no record here may state a verdict on a spec row.
- **Netlist provenance** — schematic path plus the SHA-256 of the frozen
  `netlist-snapshots/<record-id>.spice`.
- **Environment provenance** — PDK variant + pinned open_pdks hash, model
  library file, ngspice/xschem versions, this repo's git commit and whether
  the tree was dirty, host OS/arch. "Dirty" means *the code that produced
  this evidence differed from the named commit*: the record's own outputs
  (its corner logs, its netlist snapshot, the record file itself) are
  excluded from that check, since a run always creates them and counting
  them would mark every record dirty. An uncommitted edit to the harness or
  to the testbench does still mark it dirty.

  The recorded commit is the branch commit the run happened at, and a rebase
  or a squash-merge rewrites that hash — so a record written before its PR
  merged names a commit that no longer exists on `main`. Regenerate the
  record when that is cheap; otherwise read the recorded hash as "the tree
  this ran against", and rely on the fields that survive history rewriting
  for exact reproduction: the pinned PDK build, the tool versions, and the
  netlist snapshot's SHA-256.
- **Corner matrix run** — the explicit (process corner, temperature, supply)
  points actually executed, and whether it is a declared subset of the
  manifest's default grid.
- **Methodology / criteria / limitations** — the pass/fail criterion applied
  per point, and any known gap in what the record can support.
- **Result** — per-point pass/fail table plus an overall verdict.
- **Links** — testbench, netlist snapshot, raw per-point logs.
- **Timestamp / author** — UTC creation time and who (human or agent) ran it.
- **Supersedes** (optional) — the prior `<record-id>` this record supersedes.

### Status / supersession language

A record's standing is **`current`** or **`superseded by <record-id>`**,
derived rather than stored: `Status` is not itself a record field. The
superseding record carries **Supersedes**; the superseded record is never
edited to add a back-reference — read forward to find what superseded it.

## Append-only rule

`records/*.md`, `netlist-snapshots/*.spice`, and `corners/<record-id>/*` are
written once and never edited or deleted after creation, even to fix a typo.
A correction is a new record naming the one it supersedes. Only `testbench/`
and this README are mutable.

This is why a record minted before the **Spec row(s)** field existed was not
retro-fitted with one when issue #152 introduced it: back-filling the
citation into 20-odd committed records would have been exactly the in-place
edit this rule forbids. Those records' spec-row mapping lives in their
experiment's `testbench/tb.json` instead — mutable by the sentence above —
and `measurements/aggregate.py` resolves it from there, saying so in the
report. Every record minted from here on carries the field itself.

One deliberate non-exception: `corners/<record-id>/checkpoint.json` (see
"Interrupted and parallel runs" above) is transient run state that is
rewritten as a run progresses and deleted when the record is written. It is
gitignored and is never part of the committed evidence trail, so the rule
above — which governs committed evidence — is unaffected.

## Retention policy

| Artifact | Retained? | Why |
|---|---|---|
| Summary record (`records/<id>.md`) | **Always, committed** | the citable evidence object |
| Frozen netlist snapshot (`netlist-snapshots/<id>.spice`) | **Always, committed** | the record's claim is meaningless without the exact DUT |
| Raw per-point ngspice logs (`corners/<id>/*.log`) | **Always, committed** | the primary evidence the pass/fail table was read from |
| Per-point patched netlists (`corners/<id>/*.spice`) | **Always, committed** | reproduces exactly what ngspice ran at that point |
| Full waveform rawfiles (`.raw`) | **No, not committed** | regenerable from the frozen netlist + logged environment |

Root `.gitignore` ignores `*.raw` and `*.log` tree-wide; a scoped negation
un-ignores exactly the evidence path:

```gitignore
*.raw
*.log
!sim/*/corners/**/*.log
sim/*/corners/**/checkpoint.json
```

(The last line keeps the transient resume checkpoint out of the committed
trail — see "Interrupted and parallel runs" above.)

**Nothing is pruned.** Old records stay after they are superseded.

## No fabricated evidence

Files under `sim/<experiment-slug>/` may only be created by an actual run of
an actual testbench. Do not commit an example, a template, or a
plausible-looking record into evidence position.

The first real testbench is `pdk-smoke` (#2) — see
`sim/pdk-smoke/records/` for the current evidence. Every campaign added
after it follows this same convention.
