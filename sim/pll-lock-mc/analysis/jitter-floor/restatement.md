# `sim/pll-lock-mc`'s measured period jitter, restated against the measured floor

**Generated** by `sim/pll-lock-mc/analysis/jitter_floor.py` -- do not edit by hand. Re-derive with `--write`, verify with `--check`. Every figure below is read from a committed record (or from that record's own committed per-point netlist); nothing here simulates or measures.

## Inputs

- Measured: `sim/pll-lock-mc/records/20260924-222341-a9375a5.md` (record `20260924-222341-a9375a5`) -- 3 locked draw(s) carrying a period-jitter figure.
- Floor: `sim/jitter-floor/records/` -- 5 variant record(s) of the null control (an ideal pulse source of exactly constant period, true period jitter zero by construction), all at the same 200 ps dump grid as the measured record.

## The floor family, as measured

| Variant | Record | Pulse period | Edge (TR=TF) | Edge / grid step | frac(period / step) | Floor reported | Population |
|---|---|---|---|---|---|---|---|
| A1 | `20260925-022153-30889a3` | 3.9952 ns | 20.0 ps | 0.10 | 0.976 | 0.381% | 12515 cycles |
| A2 | `20260925-022310-30889a3` | 3.9904 ns | 20.0 ps | 0.10 | 0.952 | 0.720% | 12530 cycles |
| A3 | `20260925-022043-30889a3` | 3.9170 ns | 20.0 ps | 0.10 | 0.585 | 2.371% | 12764 cycles |
| B | `20260925-022424-30889a3` | 3.9170 ns | 200.0 ps | 1.00 | 0.585 | 0.610% | 12764 cycles |
| C | `20260925-022516-30889a3` | 3.9170 ns | 1000.0 ps | 5.00 | 0.585 | 0.000% | 12764 cycles |

Read this as the two dependences `sim/jitter-floor/testbench/tb.json` states: the floor collapses once the clock's transition spans two or more grid samples (the interpolation then happens across a bracketing pair that both sit on the ramp), and, for an edge the grid cannot resolve, it is set by how far the grid phase of successive edges walks -- the fractional part of period/step.

## The restatement

Quadrature removal, `sqrt(measured^2 - floor^2)`, at each draw's own measured post-lock period, against the worst-case (fastest-edge) floor variant measured at that period. Row 9's bound is 1.0 % of the output period; the `Budget` column is that bound in absolute time, for scale against the 200 ps grid.

| Trial | Verdict in record | f_out | Budget (1.0 %) | Measured | Floor (variant) | Floor-removed | Floor-removed % | Still misses row 9 at this floor? |
|---|---|---|---|---|---|---|---|---|
| 2 | FAIL | 250.3 MHz | 40.0 ps | 1.584% (63.3 ps) | 0.381% (15.2 ps, A1) | 61.4 ps | 1.537% | **yes** |
| 3 | FAIL | 250.6 MHz | 39.9 ps | 1.851% (73.9 ps) | 0.720% (28.7 ps, A2) | 68.0 ps | 1.705% | **yes** |
| 5 | FAIL | 255.3 MHz | 39.2 ps | 3.073% (120.4 ps) | 2.371% (92.9 ps, A3) | 76.6 ps | 1.955% | **yes** |

## The regime the null control does not reproduce

The null control's period is exactly constant, so its edges walk through grid phase deterministically. A signal with real jitter comparable to the grid step does not: its edges land at grid phases spread by that jitter, which is a wider distribution and therefore a different floor. Neither figure below is measured here (`sim/jitter-calibration`, issue #185, is the control that measures the second -- see its `analysis/calibration.md`, which finds that at this period the walk-phase figure is the *larger* of the two, so a null-control floor over-corrects a strongly jittering signal); both are arithmetic on this 200 ps grid, printed with their formulas:

- `step * sqrt(f*(1-f))`, maximized at `f = 0.5`, i.e. `step/2` = **100.0 ps** -- the worst case over grid phases for a perfectly periodic clock, which is the largest floor any unresolved edge with adjacent-interval quantization can carry.
- `sqrt(2)*step/sqrt(12)` = `0.41*step` = **81.6 ps** -- edges at independent, uniformly-spread grid phases, the case a really-jittering signal approaches.

Applying the larger of the two (100.0 ps) to each draw, as a test of whether the conclusion above survives the most pessimistic floor arithmetic allows:

- Trial 2: measured 63.3 ps RMS, which is **below** 100.0 ps. A quadrature-additive error cannot exceed the total it contributes to, so this draw's own magnitude rules that pessimistic floor out for it -- whatever floor applies to this draw is smaller than its measured figure, which is what the restatement above already assumes.
- Trial 3: measured 73.9 ps RMS, which is **below** 100.0 ps. A quadrature-additive error cannot exceed the total it contributes to, so this draw's own magnitude rules that pessimistic floor out for it -- whatever floor applies to this draw is smaller than its measured figure, which is what the restatement above already assumes.
- Trial 5: measured 120.4 ps RMS. Even if the whole 100.0 ps applied, 67.0 ps (1.710% of its period) would remain -- still outside row 9's bound.

## What this does and does not settle

- **3 of 3 locked draws still miss ratified row 9's 1.0 % bound once the measured floor is removed in quadrature** -- the floor this null control measures at each draw's own period, with the fastest edge (largest floor) the family ran. At the *other* end of the family, an edge the grid resolves, the measured floor is 0.000 % and the draws' figures stand unchanged. So under both regimes the control itself covers, the recorded miss is the circuit's, not the grid's.
- **1 of 3 miss it even under the most pessimistic floor arithmetic allows at this grid** (100.0 ps per period): trial 5. That miss is not readable as a measurement artefact under any floor model considered here.
- **The remaining trials 2 and 3 keep a residual ambiguity, and it is named rather than argued away.** Their own magnitude rules out the fully-unresolved, uniformly-spread-phase floor (81.6 ps, which exceeds what they measured), but an *intermediate* floor -- edges the grid only partly resolves, at grid phases spread by the draw's own jitter rather than by a constant period's walk -- sits between the null control's figure and their measured one, and a large enough one would put them inside the bound. That regime is exactly what a source of known, nonzero injected jitter settles, and `sim/jitter-calibration` (issue #185) now measures it; the null control cannot, by construction. Applying that campaign's curve to these draws is a further step this restatement does not take on its own -- its floors were measured at *its* injected magnitudes, not at these draws'.
- **It does not ratify, relax or restate row 9**, and it does not turn the recorded miss into a pass or a failure verdict of its own. `sim/pll-lock-mc/records/20260924-222341-a9375a5.md` stands exactly as written, per `sim/README.md`'s append-only rule; this document is a derived reading of it, not a correction to it.
- **It does not establish which floor variant the real DUT sits at.** Nothing committed here states `design/vco`'s `CLK` transition time at the row-9 operating point (issue #186), so the applicable floor is bounded by this family rather than read off it. The first bullet is stated over both ends of the family so it does not depend on that answer; the ambiguity bullet is what that measurement, read together with `sim/jitter-calibration`'s curve, would close.

