# `sim/pll-lock-mc`'s measured period jitter, restated against the measured floor

**Generated** by `sim/pll-lock-mc/analysis/jitter_floor.py` -- do not edit by hand. Re-derive with `--write`, verify with `--check`. Every figure below is read from a committed record (or from that record's own committed per-point netlist); nothing here simulates or measures.

## Inputs

- Measured: `sim/pll-lock-mc/records/20260924-222341-a9375a5.md` (record `20260924-222341-a9375a5`) -- 3 locked draw(s) carrying a period-jitter figure.
- Floor: `sim/jitter-floor/records/` -- 5 variant record(s) of the null control (an ideal pulse source of exactly constant period, true period jitter zero by construction), all at the same 200 ps dump grid as the measured record.
- Calibration, read for period coverage only (see "Why this restatement declines..." below -- its calibrated floor is not applied as a correction here): `sim/jitter-calibration/records/` -- 18 variant record(s) of a source with known, nonzero injected jitter (issue #185), spanning 2 distinct nominal period(s).

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

The null control's period is exactly constant, so its edges walk through grid phase deterministically. A signal with real jitter comparable to the grid step does not: its edges land at grid phases spread by that jitter, which is a wider distribution and therefore a different floor. Neither figure below is measured here (`sim/jitter-calibration`, issue #185, is the control that measures the second -- see its `analysis/calibration.md`, which finds that *which way* the null control's floor differs from the floor a jittering signal carries is itself a property of the period being corrected); both are arithmetic on this 200 ps grid, printed with their formulas:

- `step * sqrt(f*(1-f))`, maximized at `f = 0.5`, i.e. `step/2` = **100.0 ps** -- the worst case over grid phases for a perfectly periodic clock, which is the largest floor any unresolved edge with adjacent-interval quantization can carry.
- `sqrt(2)*step/sqrt(12)` = `0.41*step` = **81.6 ps** -- edges at independent, uniformly-spread grid phases, the case a really-jittering signal approaches.

Applying the larger of the two (100.0 ps) to each draw, as a test of whether the conclusion above survives the most pessimistic floor arithmetic allows:

- Trial 2: measured 63.3 ps RMS, which is **below** 100.0 ps. A quadrature-additive error cannot exceed the total it contributes to, so this draw's own magnitude rules that pessimistic floor out for it -- whatever floor applies to this draw is smaller than its measured figure, which is what the restatement above already assumes.
- Trial 3: measured 73.9 ps RMS, which is **below** 100.0 ps. A quadrature-additive error cannot exceed the total it contributes to, so this draw's own magnitude rules that pessimistic floor out for it -- whatever floor applies to this draw is smaller than its measured figure, which is what the restatement above already assumes.
- Trial 5: measured 120.4 ps RMS. Even if the whole 100.0 ps applied, 67.0 ps (1.710% of its period) would remain -- still outside row 9's bound.

## Why this restatement declines to apply the calibration-informed floor

`sim/jitter-calibration` (issue #185) measures the regime above directly, with a known, nonzero injected jitter, instead of arguing it from grid arithmetic. Its `analysis/calibration.md` finds that the two floors are different quantities -- not one a conservative bound on the other -- and that the null-control floor's error **changes sign** with `frac(period/step)`: where the walk-phase figure `step*sqrt(f*(1-f))` is the larger of the two grid bounds above, the null control *over*-states the floor a strongly jittering signal carries and a correction using it over-corrects; where it is the smaller one, the error runs the other way.

That campaign's 18 committed variant record(s) span 2 distinct nominal period(s) -- 3.9170 ns, 3.9952 ns -- so the sign's period dependence is measured there rather than argued from the formula (issue #197). Checked against each locked draw's own measured period:

| Trial | f_out | Period | frac(period / step) | Calibration variant at this period? |
|---|---|---|---|---|
| 2 | 250.3 MHz | 3.9952 ns | 0.976 | **yes** -- K05a, K05b, K05c, K10a, K10b, K10c, K20a, K20b, K20c |
| 3 | 250.6 MHz | 3.9904 ns | 0.952 | **no** |
| 5 | 255.3 MHz | 3.9170 ns | 0.585 | **yes** -- J05a, J05b, J05c, J10a, J10b, J10c, J20a, J20b, J20c |

Trial 5 already has a calibration family at its own period, but is resolved without it -- it is one of the 1 draw(s) that miss row 9 even under the null control's own most pessimistic floor arithmetic (the bullet above), so nothing about its verdict depends on the calibration curve.

Of the draws with a residual ambiguity left to resolve (trials 2 and 3), trial 2 now has a calibration family at its own period (3.9952 ns -- K05a, K05b, K05c, K10a, K10b, K10c, K20a, K20b, K20c), and trial 3 still has none (3.9904 ns, a period the calibration family has never visited).

**Decision: decline**, rather than interpolate or bracket -- unchanged from the resolution argued when this section was written (issue #193), and on grounds this document now states per draw rather than collectively. Interpolating the calibration's magnitude-dependent implied floor at a draw's own measured magnitude is mildly circular **even when the period matches**: a draw's measured figure already contains the floor being looked up, so using it to pick the floor assumes what it is trying to bound. That ground applies to every draw here and is not weakened by any calibration run. For trial 3 a second ground still applies on top of it: with no calibration variant at that period, interpolating **or** bracketing would compound the circularity with an unmeasured cross-period extrapolation, on a quantity `calibration.md` itself says does not transfer across periods by assumption. Declining costs nothing this restatement was going to use: no draw's verdict above depends on a calibration floor.

**What the calibration run since changed, and what it did not.** Trial 2 now has a period-matched calibration family (issue #197 ran it at that draw's own period, which is also the sign-flip test `analysis/calibration.md` could previously only argue from the formula). So the second ground above -- cross-period extrapolation -- no longer applies to it, and a **bracket** at its own period, reporting the residual under the null-control floor and under the measured implied-floor range of the family at that period, is now constructible from committed evidence rather than being the extrapolation bracketing was supposed to avoid. Whether to apply that bracket -- and what it would mean for a draw the record above already marks FAIL -- is a decision about this campaign's own reading of ratified row 9, and is **deliberately not made here**: this document states the coverage and stops. Issue #205 tracks it.

**The run that would close the remaining gap**: a `sim/jitter-calibration` variant family (the same 3 injected magnitudes x 3 edges that campaign runs) at 3.9904 ns -- trial 3's own measured period, which the calibration family has not visited. Until then this restatement has nothing period-matched to read there, in either direction.

## What this does and does not settle

- **3 of 3 locked draws still miss ratified row 9's 1.0 % bound once the measured floor is removed in quadrature** -- the floor this null control measures at each draw's own period, with the fastest edge (largest floor) the family ran. At the *other* end of the family, an edge the grid resolves, the measured floor is 0.000 % and the draws' figures stand unchanged. So under both regimes the control itself covers, the recorded miss is the circuit's, not the grid's.
- **1 of 3 miss it even under the most pessimistic floor arithmetic allows at this grid** (100.0 ps per period): trial 5. That miss is not readable as a measurement artefact under any floor model considered here.
- **The remaining trials 2 and 3 keep a residual ambiguity, and this restatement declines to resolve it rather than argue it away.** Their own magnitude rules out the fully-unresolved, uniformly-spread-phase floor (81.6 ps, which exceeds what they measured), but an *intermediate* floor -- edges the grid only partly resolves, at grid phases spread by the draw's own jitter rather than by a constant period's walk -- sits between the null control's figure and their measured one, and a large enough one would put them inside the bound. `sim/jitter-calibration` (issue #185) measures exactly that regime, at 2 nominal period(s) so far; trial 2 now has a family at its own period and trial 3 does not -- see "Why this restatement declines..." above for the argued decision, which stands on grounds a period match does not remove, and for what remains unrun.
- **It does not ratify, relax or restate row 9**, and it does not turn the recorded miss into a pass or a failure verdict of its own. `sim/pll-lock-mc/records/20260924-222341-a9375a5.md` stands exactly as written, per `sim/README.md`'s append-only rule; this document is a derived reading of it, not a correction to it.
- **It does not establish which floor variant the real DUT sits at.** Nothing committed here states `design/vco`'s `CLK` transition time at the row-9 operating point (issue #186), so the applicable floor is bounded by this family rather than read off it. The first bullet is stated over both ends of the family so it does not depend on that answer; the ambiguity bullet is what that measurement, read together with a period-matched `sim/jitter-calibration` variant (issue #197), would close.

