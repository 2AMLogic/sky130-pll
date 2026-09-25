# Which member of `sim/jitter-floor`'s family applies to `design/vco`'s own `CLK`

**Generated** by `sim/vco-clk-transition/analysis/bracket_floor.py` -- do not edit by hand. Re-derive with `--write`, verify with `--check`. Every figure below is read from a committed record (or from that record's own committed per-point netlist); nothing here simulates or measures.

## Inputs

- Measured transition time: `sim/vco-clk-transition/records/20260925-110645-810cd82.md` (record `20260925-110645-810cd82`) -- design/vco/vco_ring5.sch's own `CLK`, open loop, at the VCTRL that puts it near the row-9 operating point (issue #186).
- Floor family: `sim/jitter-floor/records/` (issue #178) -- 5 variant record(s), all dumped at the same 200.00 ps grid this design's own transition time is read against.

## The measured transition time, and its ratio to the dump grid

- Rise (10-90%): 62.14 ps (mean over 37 edges)
- Fall (10-90%): 53.37 ps (mean over 36 edges)
- Ratio to a 200.00 ps dump grid (`sim/jitter-floor`'s and `sim/pll-lock-mc`'s own): **0.267-0.311x** a grid step -- i.e. both edges are a fraction of one grid step, not multiple grid steps.

## The A3/B/C triple: one period, three edge/step ratios, floor measured at each

`sim/jitter-floor`'s A3, B and C variants share one pulse period (3.9170 ns, `sim/pll-lock-mc`'s own trial-5 measured period) and differ only in edge time, so at this one period the floor is a directly measured function of edge/step:

| Variant | Record | Edge/step | Floor reported |
|---|---|---|---|
| A3 | `20260925-022043-30889a3` | 0.10x | 2.371% |
| B | `20260925-022424-30889a3` | 1.00x | 0.610% |
| C | `20260925-022516-30889a3` | 5.00x | 0.000% |

Monotonically decreasing, as `sim/harness/measure.py`'s own module docstring states in prose ("the floor collapses as soon as the grid resolves the edge") -- this triple is the direct measurement of that claim.

## The bracket

Design's own edge/step ratio (0.267-0.311x) sits strictly between `A3`'s (0.10x, 2.371%) and `B`'s (1.00x, 0.610%). Because the triple above is measured monotonic in edge/step at this fixed period, the applicable floor at this design's own transition time -- **at `sim/pll-lock-mc`'s own 3.9170 ns operating period** -- is bounded:

> **0.610% < applicable floor < 2.371%**

Concretely: this design's real `CLK` sits in the family's **unresolved-edge** regime (its transition spans well under one grid step), the same regime `sim/jitter-floor`'s A-variants exemplify -- **not** variant C's fully-resolved, 0.000 % case, and not far from variant B's one-grid-step marginal case either. A reader of `sim/pll-lock-mc/records/20260924-222341-a9375a5.md`'s measured period-jitter figures should read them against this bracket, not against variant C's zero floor and not against the full 0.000-2.371 % span the family covered before this measurement existed.

## The other variants, for context

`sim/jitter-floor`'s remaining variants (A1, A2) share the A-family's edge/step ratio (0.1x, the same regime this design's own edge falls near) but run at `sim/pll-lock-mc`'s other two locked draws' own periods, showing how much the floor still varies with the *second* ratio (period/step grid-phase) even at a fixed, fully-unresolved edge:

| Variant | Period | Edge/step | Floor reported |
|---|---|---|---|
| A1 | 3.9952 ns | 0.10x | 0.381% |
| A2 | 3.9904 ns | 0.10x | 0.720% |

This design's own edge/step ratio is higher than the A-family's 0.1x (its edge is a few times longer, not a tenth of a grid step), so the true bound at any of these periods is tighter than -- not wider than -- the 0.381-2.371 % span the A-family alone covers; the A3/B/C bracket above states that tighter bound at the one period all three edge ratios were actually measured at.

## What this does and does not settle

- **It answers issue #186's question**: which end of `sim/jitter-floor`'s family applies to this design's real `CLK` is no longer a range spanning the whole family (0.000-2.371 %) -- it is the bracket stated above, derived from a real measured transition time rather than assumed.
- **It is a bound, not a new floor measurement.** No new simulation ran here; the number comes from the already-measured monotonic A3/B/C triple plus this design's own already-measured transition time. A future campaign that dumps `sim/jitter-floor` at THIS design's exact edge/step ratio (rather than bracketing it between two coarser variants) could narrow the bound further -- not attempted here.
- **It is read at `sim/pll-lock-mc`'s own operating period (3.9170 ns), not at this open-loop point's own free-running period** (`design/vco`'s ring runs slightly faster open-loop at this fixed VCTRL than the closed loop's own locked output -- see `sim/vco-clk-transition/records/`'s own claim). The transition TIME is a property of the ring's edge dynamics near this operating region and is not assumed to depend sensitively on that small period difference, but the bracket above is stated at the period the floor family was actually measured at, not re-derived at a new one.
- **It does not ratify, relax or restate ratified spec row 9** (`spec/target-spec.md`, `DR-006`). `sim/pll-lock-mc/records/20260924-222341-a9375a5.md` stands exactly as written, per `sim/README.md`'s append-only rule; this document is a derived reading of its own applicable resolution floor, not a correction to the record.

