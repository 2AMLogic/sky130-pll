# What this pipeline reports when the signal really jitters

**Generated** by `sim/jitter-calibration/analysis/calibration.py` -- do not edit by hand. Re-derive with `--write`, verify with `--check`. Every figure below is read from a committed record (or from that record's own committed per-point netlist); nothing here simulates or measures.

## Inputs

- Calibration: `sim/jitter-calibration/records/` -- 9 variant record(s). Each one's source is a PWL clock whose rising-edge schedule was drawn from a seeded RNG at an exactly specified RMS period jitter and written edge by edge into the netlist, so the **injected** column below is re-derived from the committed netlist rather than taken on trust: it is `pstdev(T_k)/mean(T_k)` over the card's own 50 % crossings, the same estimator `sim/harness/measure.period_jitter` applies to the reduced edges.
- Null control, for comparison: `sim/jitter-floor/records/` -- 5 variant record(s) of an ideal pulse source of exactly constant period (true period jitter zero by construction).
- Both at a 200 ps dump grid and a 3.9170 ns nominal period, so every figure below is one operating point's.

## The calibration curve

`Injected` is what the source carried; `Reported` is what the reducer said; `Implied floor` is `sqrt(reported^2 - injected^2)`, the measurement error this pipeline actually added to a signal that jitters. `Null-control floor` is what `sim/jitter-floor` measured at the *same* period and transition time, for a signal that does not.

| Variant | Record | Edge (TR=TF) | Edge / grid step | Injected | Reported | Reported / injected | Implied floor | Null-control floor (variant) |
|---|---|---|---|---|---|---|---|---|
| J05a | `20260925-103212-518b31f` | 20 ps | 0.10 | 0.500% (19.6 ps) | 2.375% (93.0 ps) | 4.75x | 2.322% (90.9 ps) | 2.371% (92.9 ps, A3) |
| J10a | `20260925-103326-518b31f` | 20 ps | 0.10 | 1.000% (39.2 ps) | 2.395% (93.8 ps) | 2.40x | 2.176% (85.2 ps) | 2.371% (92.9 ps, A3) |
| J20a | `20260925-103435-518b31f` | 20 ps | 0.10 | 2.000% (78.3 ps) | 2.878% (112.7 ps) | 1.44x | 2.070% (81.1 ps) | 2.371% (92.9 ps, A3) |
| J05b | `20260925-103238-518b31f` | 200 ps | 1.00 | 0.500% (19.6 ps) | 0.760% (29.8 ps) | 1.52x | 0.572% (22.4 ps) | 0.610% (23.9 ps, B) |
| J10b | `20260925-103348-518b31f` | 200 ps | 1.00 | 1.000% (39.2 ps) | 1.178% (46.1 ps) | 1.18x | 0.623% (24.4 ps) | 0.610% (23.9 ps, B) |
| J20b | `20260925-103459-518b31f` | 200 ps | 1.00 | 2.000% (78.3 ps) | 2.071% (81.1 ps) | 1.04x | 0.538% (21.1 ps) | 0.610% (23.9 ps, B) |
| J05c | `20260925-103303-518b31f` | 1000 ps | 5.00 | 0.500% (19.6 ps) | 0.500% (19.6 ps) | 1.00x | - (-) | 0.000% (0.0 ps, C) |
| J10c | `20260925-103409-518b31f` | 1000 ps | 5.00 | 1.000% (39.2 ps) | 1.000% (39.2 ps) | 1.00x | 0.001% (0.0 ps) | 0.000% (0.0 ps, C) |
| J20c | `20260925-103526-518b31f` | 1000 ps | 5.00 | 2.000% (78.3 ps) | 2.000% (78.3 ps) | 1.00x | 0.001% (0.0 ps) | 0.000% (0.0 ps, C) |

## Reading it

- **An edge the grid resolves costs nothing.** For the 3 variant(s) whose transition spans two or more grid samples, the reported figure matches the injected one to within 0.000 pp -- the two samples that bracket the 50 % crossing both sit on the (straight) ramp, so `measure.edge_times._interpolate_back` recovers the crossing exactly and the reducer is unbiased. This is also the check that the injected figure is what this campaign says it is: the generator, the netlist, the reducer and this script agree on a number none of them could fake independently.
- **An edge it cannot resolve costs a floor that does not vanish as the injected figure shrinks.** For the 6 variant(s) below two grid samples, the reported figure is inflated by 1.04x to 4.75x. Read the `Implied floor` column rather than the inflation factor: the floor is roughly constant in absolute time while the injected figure is not, which is exactly why a small true jitter is inflated most.

## The null control's floor is not this floor -- which is the point of #185

A jitter-free source's edges walk through grid phase deterministically, by `frac(period/step)` = 0.585 of a step per period and by nothing else. A source that genuinely jitters spreads them further, and the two distributions have different spreads -- so the null control's floor is a different quantity from the floor a real signal carries, not a conservative version of it. Neither of the two bounds below is measured; both are arithmetic on this 200 ps grid, printed with their formulas:

- `step * sqrt(f*(1-f))` at `f = 0.585` = **98.5 ps** -- the walk-phase case, i.e. what an unresolved edge on a *perfectly periodic* clock carries at this period. This is the regime `sim/jitter-floor` measures.
- `sqrt(2)*step/sqrt(12)` = `0.41*step` = **81.6 ps** -- independent, uniformly-spread grid phases, the case a signal whose jitter is large compared with the grid approaches.

Against those two, the floors this campaign actually implied. Only the **fully unresolved** variants are listed -- an edge shorter than half a grid step, where the bracketing sample pair straddles the whole transition and the arithmetic above is the applicable model. The one-grid-step variants sit in an intermediate regime (the pair sometimes lands on the ramp), so neither bound describes them and they are deliberately not scored against either.

| Variant | Injected | Injected / grid step | Implied floor | vs. walk-phase | vs. uniform-phase |
|---|---|---|---|---|---|
| J05a | 0.500% (19.6 ps) | 0.10 | 90.9 ps | 0.92x | 1.11x |
| J10a | 1.000% (39.2 ps) | 0.20 | 85.2 ps | 0.87x | 1.04x |
| J20a | 2.000% (78.3 ps) | 0.39 | 81.1 ps | 0.82x | 0.99x |

The trend across that table is the finding, and it is read off the table rather than asserted: going from the smallest injected figure (J05a, 0.500%, implied floor 90.9 ps = 1.11x the uniformly-spread-phase bound) to the largest (J20a, 2.000%, 81.1 ps = 0.99x), the floor a jittering signal carries moves **toward** the uniformly-spread-phase figure and away from the walk-phase figure the null control measures. That is the crossover issue #185 predicted must exist: a source whose jitter is small compared with the grid step still presents the constant-period walk, and one whose jitter is comparable to it does not.

So a floor read off `sim/jitter-floor` and applied to a signal that really jitters is an approximation, and **its sign is not guaranteed**. At this period the walk-phase floor (98.5 ps) is the *larger* of the two bounds, so the null control over-states the floor for a strongly jittering signal and over-corrects it; at a period whose `frac(period/step)` is nearer 0 or 1 the walk-phase floor is the smaller one and the error runs the other way. Neither direction is conservative by construction, which is why the correction wanted a measurement rather than an argument.

## Using this to read a measured figure

For a measured figure `m` at this grid and period, with an unresolved edge, the true figure is `sqrt(m^2 - floor^2)` with `floor` taken from the `Implied floor` column at a comparable injected magnitude (the floor is mildly magnitude-dependent, per the table above) -- and **no value at all** when `m <= floor`, which is the honest statement of "this measurement cannot separate the signal from its own measurement". For a resolved edge no correction is needed. For scale: ratified spec row 9's bound is 1.0 % of the output period, 39.2 ps at this period, against a grid step of 200.0 ps.

## What this does and does not settle

- **It calibrates the reducer, not the PLL.** This campaign's DUT is a voltage source and a resistor. It measures no `spec/target-spec.md` row, states no verdict on one, and ratifies nothing -- see its manifest's `spec_rows_note`.
- **Its injected jitter is white.** Independent Gaussian period to period: no correlation, no wander, no deterministic or spur component. A correlated source presents a different grid-phase distribution again, and this campaign says nothing about it.
- **One period and one grid.** 3.9170 ns at 200 ps. The grid-phase arithmetic is period-specific (`f = frac(period/step)`), so these numbers transfer to another period only through that arithmetic, never by assumption.
- **Sampling error is not zero.** Each figure is over a 300-cycle population, so the *reported* column carries roughly `1/sqrt(2N)` = 4.1 % relative error. The *injected* column carries none: it is exact by construction (the generator normalizes its draw to the stated RMS) and re-derived here from the committed schedule.
- **It does not establish which variant the real DUT is in.** Nothing committed here states `design/vco`'s `CLK` transition time at the row-9 operating point (issue #186), so the applicable row of the table above cannot be read off without that measurement -- the same gap `sim/jitter-floor`'s records name.

