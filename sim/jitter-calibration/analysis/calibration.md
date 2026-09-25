# What this pipeline reports when the signal really jitters

**Generated** by `sim/jitter-calibration/analysis/calibration.py` -- do not edit by hand. Re-derive with `--write`, verify with `--check`. Every figure below is read from a committed record (or from that record's own committed per-point netlist); nothing here simulates or measures.

## Inputs

- Calibration: `sim/jitter-calibration/records/` -- 18 variant record(s). Each one's source is a PWL clock whose rising-edge schedule was drawn from a seeded RNG at an exactly specified RMS period jitter and written edge by edge into the netlist, so the **injected** column below is re-derived from the committed netlist rather than taken on trust: it is `pstdev(T_k)/mean(T_k)` over the card's own 50 % crossings, the same estimator `sim/harness/measure.period_jitter` applies to the reduced edges.
- Null control, for comparison: `sim/jitter-floor/records/` -- 5 variant record(s) of an ideal pulse source of exactly constant period (true period jitter zero by construction).
- All at a 200 ps dump grid, at two nominal periods: 3.9170 ns (`frac` = 0.585, family J); 3.9952 ns (`frac` = 0.976, family K). A jitter-free clock's edges walk through grid phase by `frac(period/step)` per period and by nothing else, so the floor this campaign measures is **period-specific** -- every figure below is stated per period, and nothing is pooled across periods.

## The calibration curve

`Injected` is what the source carried; `Reported` is what the reducer said; `Implied floor` is `sqrt(reported^2 - injected^2)`, the measurement error this pipeline actually added to a signal that jitters. `Null-control floor` is what `sim/jitter-floor` measured at the *same* period and transition time, for a signal that does not.

| Variant | Record | Nominal period | Edge (TR=TF) | Edge / grid step | Injected | Reported | Reported / injected | Implied floor | Null-control floor (variant) |
|---|---|---|---|---|---|---|---|---|---|
| J05a | `20260925-103212-518b31f` | 3.9170 ns | 20 ps | 0.10 | 0.500% (19.6 ps) | 2.375% (93.0 ps) | 4.75x | 2.322% (90.9 ps) | 2.371% (92.9 ps, A3) |
| J10a | `20260925-103326-518b31f` | 3.9170 ns | 20 ps | 0.10 | 1.000% (39.2 ps) | 2.395% (93.8 ps) | 2.40x | 2.176% (85.2 ps) | 2.371% (92.9 ps, A3) |
| J20a | `20260925-103435-518b31f` | 3.9170 ns | 20 ps | 0.10 | 2.000% (78.3 ps) | 2.878% (112.7 ps) | 1.44x | 2.070% (81.1 ps) | 2.371% (92.9 ps, A3) |
| J05b | `20260925-103238-518b31f` | 3.9170 ns | 200 ps | 1.00 | 0.500% (19.6 ps) | 0.760% (29.8 ps) | 1.52x | 0.572% (22.4 ps) | 0.610% (23.9 ps, B) |
| J10b | `20260925-103348-518b31f` | 3.9170 ns | 200 ps | 1.00 | 1.000% (39.2 ps) | 1.178% (46.1 ps) | 1.18x | 0.623% (24.4 ps) | 0.610% (23.9 ps, B) |
| J20b | `20260925-103459-518b31f` | 3.9170 ns | 200 ps | 1.00 | 2.000% (78.3 ps) | 2.071% (81.1 ps) | 1.04x | 0.538% (21.1 ps) | 0.610% (23.9 ps, B) |
| J05c | `20260925-103303-518b31f` | 3.9170 ns | 1000 ps | 5.00 | 0.500% (19.6 ps) | 0.500% (19.6 ps) | 1.00x | - (-) | 0.000% (0.0 ps, C) |
| J10c | `20260925-103409-518b31f` | 3.9170 ns | 1000 ps | 5.00 | 1.000% (39.2 ps) | 1.000% (39.2 ps) | 1.00x | 0.001% (0.0 ps) | 0.000% (0.0 ps, C) |
| J20c | `20260925-103526-518b31f` | 3.9170 ns | 1000 ps | 5.00 | 2.000% (78.3 ps) | 2.000% (78.3 ps) | 1.00x | 0.001% (0.0 ps) | 0.000% (0.0 ps, C) |
| K05a | `20260925-160214-ed585e4` | 3.9952 ns | 20 ps | 0.10 | 0.500% (20.0 ps) | 1.191% (47.6 ps) | 2.38x | 1.081% (43.2 ps) | 0.381% (15.2 ps, A1) |
| K10a | `20260925-160342-ed585e4` | 3.9952 ns | 20 ps | 0.10 | 1.000% (40.0 ps) | 1.922% (76.8 ps) | 1.92x | 1.641% (65.6 ps) | 0.381% (15.2 ps, A1) |
| K20a | `20260925-160453-ed585e4` | 3.9952 ns | 20 ps | 0.10 | 2.000% (79.9 ps) | 2.779% (111.0 ps) | 1.39x | 1.929% (77.1 ps) | 0.381% (15.2 ps, A1) |
| K05b | `20260925-160252-ed585e4` | 3.9952 ns | 200 ps | 1.00 | 0.500% (20.0 ps) | 0.545% (21.8 ps) | 1.09x | 0.217% (8.7 ps) | -- (no null-control variant at this period and edge) |
| K10b | `20260925-160403-ed585e4` | 3.9952 ns | 200 ps | 1.00 | 1.000% (40.0 ps) | 1.097% (43.8 ps) | 1.10x | 0.451% (18.0 ps) | -- (no null-control variant at this period and edge) |
| K20b | `20260925-160517-ed585e4` | 3.9952 ns | 200 ps | 1.00 | 2.000% (79.9 ps) | 2.068% (82.6 ps) | 1.03x | 0.526% (21.0 ps) | -- (no null-control variant at this period and edge) |
| K05c | `20260925-160316-ed585e4` | 3.9952 ns | 1000 ps | 5.00 | 0.500% (20.0 ps) | 0.500% (20.0 ps) | 1.00x | 0.000% (0.0 ps) | -- (no null-control variant at this period and edge) |
| K10c | `20260925-160426-ed585e4` | 3.9952 ns | 1000 ps | 5.00 | 1.000% (40.0 ps) | 1.000% (40.0 ps) | 1.00x | - (-) | -- (no null-control variant at this period and edge) |
| K20c | `20260925-160541-ed585e4` | 3.9952 ns | 1000 ps | 5.00 | 2.000% (79.9 ps) | 2.000% (79.9 ps) | 1.00x | - (-) | -- (no null-control variant at this period and edge) |

## Reading it

- **An edge the grid resolves costs nothing, at any period here.** For the 6 variant(s) whose transition spans two or more grid samples, the reported figure matches the injected one to within 0.000 pp -- the two samples that bracket the 50 % crossing both sit on the (straight) ramp, so `measure.edge_times._interpolate_back` recovers the crossing exactly and the reducer is unbiased. This is also the check that the injected figure is what this campaign says it is: the generator, the netlist, the reducer and this script agree on a number none of them could fake independently.
- **An edge it cannot resolve costs a floor that does not vanish as the injected figure shrinks.** For the 12 variant(s) below two grid samples, the reported figure is inflated by 1.03x to 4.75x. Read the `Implied floor` column rather than the inflation factor: the floor is roughly constant in absolute time while the injected figure is not, which is exactly why a small true jitter is inflated most.
- **One edge schedule, two periods.** A variant's seed depends only on its injected RMS, so the 6 (magnitude, edge) group(s) that appear at more than one period are built from the identical normalized draw and differ in the nominal period alone. Their implied floors spread by up to 47.8 ps -- the period's own contribution, isolated from the magnitude's and the edge's.

## The null control's floor is not this floor -- which is the point of #185

A jitter-free source's edges walk through grid phase deterministically, by `frac(period/step)` of a step per period and by nothing else. A source that genuinely jitters spreads them further, and the two distributions have different spreads -- so the null control's floor is a different quantity from the floor a real signal carries, not a conservative version of it. Neither of the two bounds below is measured; both are arithmetic on this 200 ps grid, printed with their formulas:

| Nominal period | `frac(period/step)` | `step * sqrt(f*(1-f))` (walk-phase) | `sqrt(2)*step/sqrt(12)` (uniform-phase) | Larger bound |
|---|---|---|---|---|
| 3.9170 ns | 0.585 | 98.5 ps | 81.6 ps | walk-phase |
| 3.9952 ns | 0.976 | 30.6 ps | 81.6 ps | uniform-phase |

The walk-phase case is what an unresolved edge on a *perfectly periodic* clock carries at that period -- the regime `sim/jitter-floor` measures. The uniform-phase case is independent, uniformly-spread grid phases: the case a signal whose jitter is large compared with the grid approaches, and it does not depend on the period at all. Note that which of the two is larger is a property of the period, not of the pipeline.

Against those two, the floors this campaign actually implied. Only the **fully unresolved** variants are listed -- an edge shorter than half a grid step, where the bracketing sample pair straddles the whole transition and the arithmetic above is the applicable model. The one-grid-step variants sit in an intermediate regime (the pair sometimes lands on the ramp), so neither bound describes them and they are deliberately not scored against either.

| Variant | Nominal period | Injected | Injected / grid step | Implied floor | vs. walk-phase | vs. uniform-phase |
|---|---|---|---|---|---|---|
| J05a | 3.9170 ns | 0.500% (19.6 ps) | 0.10 | 90.9 ps | 0.92x | 1.11x |
| J10a | 3.9170 ns | 1.000% (39.2 ps) | 0.20 | 85.2 ps | 0.87x | 1.04x |
| J20a | 3.9170 ns | 2.000% (78.3 ps) | 0.39 | 81.1 ps | 0.82x | 0.99x |
| K05a | 3.9952 ns | 0.500% (20.0 ps) | 0.10 | 43.2 ps | 1.41x | 0.53x |
| K10a | 3.9952 ns | 1.000% (40.0 ps) | 0.20 | 65.6 ps | 2.14x | 0.80x |
| K20a | 3.9952 ns | 2.000% (79.9 ps) | 0.40 | 77.1 ps | 2.52x | 0.94x |

At 3.9170 ns (`frac` = 0.585, family J), the trend across that table is read off it rather than asserted: going from the smallest injected figure (J05a, 0.500%, implied floor 90.9 ps = 1.11x the uniformly-spread-phase bound) to the largest (J20a, 2.000%, 81.1 ps = 0.99x), the floor a jittering signal carries moves **toward** the uniformly-spread-phase figure and away from the walk-phase figure a perfectly periodic clock would carry here. At the small-jitter end the floor sits at 0.92x that walk-phase figure, i.e. essentially at the constant-period walk -- which is the crossover issue #185 predicted must exist: a source whose jitter is small compared with the grid step still presents that walk, and one whose jitter is comparable to the grid step does not.

At 3.9952 ns (`frac` = 0.976, family K), the trend across that table is read off it rather than asserted: going from the smallest injected figure (K05a, 0.500%, implied floor 43.2 ps = 0.53x the uniformly-spread-phase bound) to the largest (K20a, 2.000%, 77.1 ps = 0.94x), the floor a jittering signal carries moves **toward** the uniformly-spread-phase figure and away from the walk-phase figure a perfectly periodic clock would carry here. At the small-jitter end the floor sits at 1.41x that walk-phase figure -- so at this period even the smallest magnitude run here does not sit at the constant-period walk, and the crossover issue #185 predicted is not visible from inside this family's magnitude range.

## Which way the null control's error runs, measured -- the point of #197

So a floor read off `sim/jitter-floor` and applied to a signal that really jitters is an approximation, and **its sign is not guaranteed**. Issue #185's family ran at one period and argued the sign's period dependence from the walk-phase formula alone; the table below measures it instead. For every fully-unresolved variant that has a null-control variant at its *own* period and edge, it is that measured null-control floor against the floor this campaign implied -- above it means the null control **over**-states the floor a jittering signal carries and a correction using it over-corrects; below it means it under-states it and under-corrects.

| Variant | Nominal period | `frac(period/step)` | Implied floor (measured here) | Null-control floor (variant) | Null / implied | Null control ... |
|---|---|---|---|---|---|---|
| J05a | 3.9170 ns | 0.585 | 90.9 ps | 92.9 ps (A3) | 1.02x | **over**-states it |
| J10a | 3.9170 ns | 0.585 | 85.2 ps | 92.9 ps (A3) | 1.09x | **over**-states it |
| J20a | 3.9170 ns | 0.585 | 81.1 ps | 92.9 ps (A3) | 1.15x | **over**-states it |
| K05a | 3.9952 ns | 0.976 | 43.2 ps | 15.2 ps (A1) | 0.35x | **under**-states it |
| K10a | 3.9952 ns | 0.976 | 65.6 ps | 15.2 ps (A1) | 0.23x | **under**-states it |
| K20a | 3.9952 ns | 0.976 | 77.1 ps | 15.2 ps (A1) | 0.20x | **under**-states it |

- At 3.9170 ns (`frac` = 0.585, family J) the null control **over**-states the floor in 3 of 3 scored variant(s): its measured floor is 1.02x to 1.15x the floor this campaign implied for a signal that genuinely jitters. The walk-phase arithmetic here (98.5 ps at `f` = 0.585) is the larger of the two bounds, so that arithmetic predicts **over**-statement -- and the measured column above agrees.
- At 3.9952 ns (`frac` = 0.976, family K) the null control **under**-states the floor in 3 of 3 scored variant(s): its measured floor is 0.20x to 0.35x the floor this campaign implied for a signal that genuinely jitters. The walk-phase arithmetic here (30.6 ps at `f` = 0.976) is the smaller of the two bounds, so that arithmetic predicts **under**-statement -- and the measured column above agrees.

**The sign flips across the periods measured here.** It is therefore not a property of this pipeline that can be quoted once and applied everywhere: a null-control floor is neither a conservative bound nor a consistently optimistic one, and which it is depends on `frac(period/step)` at the period being corrected. That is the confirmation issue #197 asked for, and it is measured rather than argued from the formula.

Neither direction is conservative by construction, which is why the correction wanted a measurement rather than an argument -- and a correction applied at a period this campaign has not visited is still an extrapolation, in whichever direction that period's own `frac(period/step)` puts it.

## Using this to read a measured figure

For a measured figure `m` at this grid, with an unresolved edge, the true figure is `sqrt(m^2 - floor^2)` with `floor` taken from the `Implied floor` column **at the row matching that figure's own nominal period** and at a comparable injected magnitude (the floor is mildly magnitude-dependent, per the tables above) -- and **no value at all** when `m <= floor`, which is the honest statement of "this measurement cannot separate the signal from its own measurement". For a resolved edge no correction is needed. For scale: ratified spec row 9's bound is 1.0 % of the output period, against a grid step of 200.0 ps -- 39.2 ps at 3.9170 ns, 40.0 ps at 3.9952 ns.

## What this does and does not settle

- **It calibrates the reducer, not the PLL.** This campaign's DUT is a voltage source and a resistor. It measures no `spec/target-spec.md` row, states no verdict on one, and ratifies nothing -- see its manifest's `spec_rows_note`.
- **Its injected jitter is white.** Independent Gaussian period to period: no correlation, no wander, no deterministic or spur component. A correlated source presents a different grid-phase distribution again, and this campaign says nothing about it.
- **Two nominal periods, one grid.** 3.9170 ns (`frac` = 0.585, family J), 3.9952 ns (`frac` = 0.976, family K) at 200 ps. The grid-phase arithmetic is period-specific (`f = frac(period/step)`), so these numbers transfer to a period not listed here only through that arithmetic, never by assumption -- including the sign of the null control's error, which the section above shows is itself period-dependent.
- **Sampling error is not zero.** Each figure is over a 300-cycle population, so the *reported* column carries roughly `1/sqrt(2N)` = 4.1 % relative error. The *injected* column carries none: it is exact by construction (the generator normalizes its draw to the stated RMS) and re-derived here from the committed schedule.
- **It does not establish which variant the real DUT is in.** Nothing committed here states `design/vco`'s `CLK` transition time at the row-9 operating point (issue #186), so the applicable row of the table above cannot be read off without that measurement -- the same gap `sim/jitter-floor`'s records name.
- **It states no verdict on any `sim/pll-lock-mc` draw.** Where a period here matches a Monte Carlo draw's own measured post-lock period, that match is coverage, not a correction: applying it is `sim/pll-lock-mc/analysis/jitter_floor.py`'s own decision to make, on its own record, and this document neither makes it nor presumes its outcome.

