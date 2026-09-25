# Can this campaign's negative control ever be `detected`?

**Generated** by `sim/pll-lock-mc/analysis/negative_control_reachability.py` -- do not edit. `python3 sim/pll-lock-mc/analysis/negative_control_reachability.py --check` re-derives every figure below from the committed artifact that carries it and fails on any drift; it runs in `npm run check:ci`.

T1 item 6 requires a deterministic negative control, and `signoff/run-signoff.sh`'s guard 3 will only accept a citation whose `negative_control.verdict` is `detected`. #195 was filed to build that control as a seeded, degraded variant of the DUT re-drawn through this campaign, and its own open question 3 asks whether `detected` is reachable at all before that simulator time is spent. This document answers it.

**Verdict: `detected` is UNREACHABLE over this campaign.**

## The rule

`klt yield` decides the verdict with two comparisons and nothing else (`native/yield/src/estimate.rs:1193-1199`, upstream tag `v0.6.0` / commit `c622e8ad` -- the revision that built every `klt yield` output committed in this directory):

```rust
let degradation_detected = empirical.estimate < nominal_empirical.estimate
    && empirical.confidence_interval.high < nominal_empirical.confidence_interval.low;
```

`empirical` is the control's own Clopper-Pearson yield, `nominal_empirical` the nominal measurement's. Both of the control's quantities are proportions of a draw count, so both are **>= 0 by construction**.

## The two fields that settle it

| Mapping of the two censored draws | `yield.empirical.estimate` | interval lower bound | reachability |
| --- | --- | --- | --- |
| `errored` (primary) -- `sim/pll-lock-mc/analysis/yield-evidence/klt-yield-report.json` | 0.000000 | 0.000000 | **unreachable** -- no control can be below both |
| `failed_unmeasurable` (sensitivity check) -- `sim/pll-lock-mc/analysis/yield-evidence/klt-yield-report-censored-as-failures.json` | 0.000000 | 0.000000 | **unreachable** -- no control can be below both |

Both mappings put the nominal estimate and its interval's lower bound at zero: not one of the draws that produced a measurement met ratified row 9's 1.0 % bound. Substituting those zeros leaves `(something >= 0) < 0` on both sides of the `&&`, which no control can satisfy.

## The probes

Reading a rule out of the tool's source is a claim about the tool, so it is checked rather than asserted. Each row is an executed `klt yield` run whose input and output are both committed under `negative-control/`. The populations are **synthetic** -- these are evidence about `klt yield`, not about the PLL -- and use exactly two sample values: 0.500 % (inside row 9's bound) and 2.169 % (outside it, the campaign's own fitted mean). Every control is the strongest degradation the schema can express: every draw `failed_unmeasurable`, i.e. 0 passes out of N.

| Probe | Nominal | Control | Verdict | What it settles |
| --- | --- | --- | --- | --- |
| `p1-campaign-as-is` | 0/3 passing, 2 errored<br>est 0.000000, CI low 0.000000 | 1000 draws, none measurable<br>est 0.000000, CI high 0.003682 | **`not_detected`** | the committed campaign itself (3 measurable draws, none passing, 2 censored as `errored`) against the strongest control the schema can express |
| `p2-campaign-sized-all-missing` | 0/183 passing<br>est 0.000000, CI low 0.000000 | 1000 draws, none measurable<br>est 0.000000, CI high 0.003682 | **`not_detected`** | the same campaign widened to `required_n` = 183 measurable draws, still missing row 9 on every one -- does sizing the population make the control fire? |
| `p3-campaign-sized-one-passing` | 1/183 passing<br>est 0.005464, CI low 0.000138 | 1000 draws, none measurable<br>est 0.000000, CI high 0.003682 | **`not_detected`** | 183 draws of which exactly one meets row 9 -- is 'some draw passed' enough, or is the threshold on the nominal interval's lower bound? |
| `p4-control-same-size-best-case` | 5/5 passing<br>est 1.000000, CI low 0.478176 | 5 draws, none measurable<br>est 0.000000, CI high 0.521824 | **`not_detected`** | a 5-draw control against a 5-draw nominal in which **every** draw passes -- the best a campaign of this size can possibly do, against the control size #195 costs at 5 draws |
| `p5-sized-threshold-below` | 8/183 passing<br>est 0.043716, CI low 0.019060 | 183 draws, none measurable<br>est 0.000000, CI high 0.019956 | **`not_detected`** | 183 nominal draws, 8 passing, against a same-size 183-draw control -- one draw below the threshold probe 6 finds |
| `p6-sized-threshold-at` | 9/183 passing<br>est 0.049180, CI low 0.022732 | 183 draws, none measurable<br>est 0.000000, CI high 0.019956 | **`detected`** | 183 nominal draws, 9 passing, against the same 183-draw control -- the smallest passing count at which this pairing is `detected`, and the positive control for the whole probe set |
| `p7-small-nominal-asymmetric-control` | 5/5 passing<br>est 1.000000, CI low 0.478176 | 6 draws, none measurable<br>est 0.000000, CI high 0.459258 | **`detected`** | the same 5-of-5 nominal as probe 4, against a **6**-draw control -- is probe 4's `not_detected` a property of the population size, or only of the `n_control = n_nominal` diagonal it sits on? |
| `p8-sized-cheap-control-below` | 20/183 passing<br>est 0.109290, CI low 0.068048 | 50 draws, none measurable<br>est 0.000000, CI high 0.071122 | **`not_detected`** | 183 nominal draws, 20 passing, against a 50-draw control -- one draw below the threshold probe 9 finds, off the diagonal probes 5 and 6 straddle |
| `p9-sized-cheap-control-at` | 21/183 passing<br>est 0.114754, CI low 0.072455 | 50 draws, none measurable<br>est 0.000000, CI high 0.071122 | **`detected`** | 183 nominal draws, 21 passing, against the same 50-draw control -- a control less than a third the size of probe 6's, bought with 12 more passing nominal draws |
| `p10-both-guard-3-conditions` | 183/183 passing<br>est 1.000000, CI low 0.980044 | 2 draws, none measurable<br>est 0.000000, CI high 0.841886 | **`detected`** | 183 nominal draws, **every one** passing, against a control at `klt yield`'s own 2-draw floor -- the only population probed here that is `detected` **and** whose `sample_size.verdict` is `sufficient`, i.e. the cheapest campaign guard 3 would actually accept |
| `p11-one-failing-draw` | 182/183 passing<br>est 0.994536, CI low 0.969931 | 2 draws, none measurable<br>est 0.000000, CI high 0.841886 | **`detected`** | the same campaign with a single draw missing row 9 -- still `detected`, but no longer sized: one failure moves `required_n` off the exact zero-failures branch, which is what makes the two guard-3 conditions pull against each other |

Three things those rows establish that prose could not:

1. **Probe 1**: the campaign as committed cannot produce `detected`, and the control it is checked against is not a weak one -- it is 1000 draws, every one of them outside the measurable regime. There is no stronger control to build.
2. **Probes 2 and 3**: neither widening the population to `required_n` = 183 nor landing a single passing draw changes that. The threshold is on the nominal interval's *lower* bound, which a near-zero yield does not lift past even a 1000-draw control's upper bound.
3. **Probe 4**: a control the size #195 costs at 5 draws, checked against a 5-draw nominal in which *every* draw passes, is still `not_detected` -- a 5-draw control's own 95 % interval still reaches 0.521824, while the best lower bound a 5-draw nominal can reach, at 5 of 5 passing, is 0.478176. This is a statement about a control **sized to match its nominal**, and the next section shows it is not a statement about small populations: probe 7 is the identical 5-of-5 nominal against a 6-draw control, and it is `detected`.

Probes 5 and 6 are the positive control for the set: one passing draw apart, at 183 draws a side, they straddle the threshold and probe 6 reports `detected`. Probes 8 and 9 straddle a second threshold off that diagonal, and probes 10 and 11 a third at the top of the range -- so the `not_detected` rows report their populations rather than a broken probe.

## What would make it reachable

The rule is a comparison of two Clopper-Pearson intervals and nothing else, so the answer for populations nobody has run is arithmetic rather than opinion. This script derives it -- and checks its own arithmetic against **every** committed `klt yield` output above before rendering: each probe's two nominal interval bounds, its control's interval upper bound, its `negative_control.verdict`, its `required_n` and its `sample_size.verdict` all have to come back out of the formulas. They do, on all 11 of them; a single disagreement makes this document refuse to render.

Each cell is the **fewest nominal draws that must meet row 9** for an all-failing control of that size to be reported `detected`. `--` means no passing count works at that pairing, even if every draw passes.

| nominal measurable draws | control = 2 | control = 5 | control = 6 | control = 20 | control = 50 | control = 183 | control = 1000 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | -- | -- | -- | 3 (100 %) | 2 (67 %) | 2 (67 %) | 1 (33 %) |
| 5 | -- | -- | 5 (100 %) | 4 (80 %) | 3 (60 %) | 2 (40 %) | 1 (20 %) |
| 10 | -- | 9 (90 %) | 9 (90 %) | 5 (50 %) | 4 (40 %) | 2 (20 %) | 2 (20 %) |
| 20 | -- | 16 (80 %) | 15 (75 %) | 8 (40 %) | 5 (25 %) | 3 (15 %) | 2 (10 %) |
| 50 | 48 (96 %) | 34 (68 %) | 31 (62 %) | 15 (30 %) | 8 (16 %) | 4 (8 %) | 2 (4 %) |
| 100 | 92 (92 %) | 63 (63 %) | 57 (57 %) | 25 (25 %) | 14 (14 %) | 6 (6 %) | 3 (3 %) |
| 183 | 164 (90 %) | 110 (60 %) | 98 (54 %) | 42 (23 %) | 21 (11 %) | 9 (5 %) | 4 (2 %) |

**Probe 4 measures the diagonal, not a floor.** Its 5-draw control against a 5-of-5 nominal is `not_detected`, which reads like "five draws is too few" -- and the row above says it is not. The same 5-of-5 nominal against a **6**-draw control is `detected`, and probe 7 is that run: one extra control draw, opposite verdict. What probe 4 settles is that a control sized to match its nominal cannot separate from it at these counts, which is a statement about the pairing `#195` was about to buy, not about small populations in general.

The table also prices the trade the other way. Probe 6 needs a 183-draw control and 9 passing nominal draws; probe 9 gets the same `detected` from a control less than a third that size, bought with 12 more passing draws (21 of 183). Probe 8 is the same pairing one passing draw lower, so that threshold is straddled too rather than asserted.

## Both of guard 3's conditions at once

`signoff/run-signoff.sh`'s guard 3 wants two things of a cited report, and the reachability question above is only the second of them: every measurement's `sample_size.verdict` must be `sufficient`, **and** its `negative_control.verdict` must be `detected`. Those two conditions are not independent, and the direction they pull in is the opposite of the obvious one.

`klt yield` sizes an estimate against the 0.01 absolute interval halfwidth `sim/pll-lock-mc/analysis/yield-evidence/spec-limits.json` declares. At an observed pass rate of exactly 0 or exactly 1 it uses the exact zero-failures interval, whose halfwidth depends only on the draw count -- hence `required_n` = 183, the figure every document here quotes. At any rate in between it switches to the normal approximation, where `required_n` scales with `p(1-p)` and therefore **peaks in the middle**. Measured across the committed probes rather than argued:

| Probe | Nominal | `required_n` | `sample_size.verdict` | `negative_control.verdict` | both? |
| --- | --- | --- | --- | --- | --- |
| `p1-campaign-as-is` | 0/3 passing | 183 | `insufficient` | `not_detected` | no |
| `p2-campaign-sized-all-missing` | 0/183 passing | 183 | `sufficient` | `not_detected` | no |
| `p3-campaign-sized-one-passing` | 1/183 passing | 209 | `insufficient` | `not_detected` | no |
| `p4-control-same-size-best-case` | 5/5 passing | 183 | `insufficient` | `not_detected` | no |
| `p5-sized-threshold-below` | 8/183 passing | 1606 | `insufficient` | `not_detected` | no |
| `p6-sized-threshold-at` | 9/183 passing | 1797 | `insufficient` | `detected` | no |
| `p7-small-nominal-asymmetric-control` | 5/5 passing | 183 | `insufficient` | `detected` | no |
| `p8-sized-cheap-control-below` | 20/183 passing | 3740 | `insufficient` | `not_detected` | no |
| `p9-sized-cheap-control-at` | 21/183 passing | 3903 | `insufficient` | `detected` | no |
| `p10-both-guard-3-conditions` | 183/183 passing | 183 | `sufficient` | `detected` | **yes** |
| `p11-one-failing-draw` | 182/183 passing | 209 | `insufficient` | `detected` | no |

Probe 10 is the only row with a **yes**, and it is the cheapest one there is: 183 measurable draws with *every* draw meeting row 9, against a control at `klt yield`'s own 2-draw minimum. Probe 11 is that same campaign with a single draw missing the bound -- still `detected`, no longer sized, because one failure moves it off the zero-failures branch and `required_n` goes to 209.

So the cost of a citable item 6 is a function of how well the design does, and it is **not monotone**. Each row below is the smallest campaign that is sized at that pass rate, the smallest control that is then `detected`, and what the pair costs at the 3-of-5 lock rate this campaign observed and the ~1 h 20 m per trial its record's execution notes give:

| Nominal pass rate | measurable draws needed | control draws | total drawn trials | simulator time |
| --- | --- | --- | --- | --- |
| 100.00 % (183/183) | 183 (`required_n` 183) | 2 | ~307 | ~409 h |
| 99.49 % (195/196) | 196 (`required_n` 195) | 2 | ~329 | ~439 h |
| 98.97 % (386/390) | 390 (`required_n` 390) | 2 | ~652 | ~869 h |
| 97.69 % (847/867) | 867 (`required_n` 866) | 2 | ~1447 | ~1,929 h |
| 50.00 % (4802/9604) | 9604 (`required_n` 9604) | 6 | ~16013 | ~21,351 h |
| 24.99 % (1800/7202) | 7202 (`required_n` 7202) | 14 | ~12018 | ~16,024 h |
| 9.99 % (345/3454) | 3454 (`required_n` 3454) | 40 | ~5797 | ~7,729 h |

The cheapest row is 183/183 -- every draw passing -- at ~409 h, roughly the ~400 h this directory has been quoting all along. The dearest is 4802/9604 at ~21,351 h, about 52x as much, and it is *in the middle* rather than at the bad end: the bottom row, a design meeting row 9 one time in ten, is cheaper than the one above it. **Part-way is the expensive place to stop.** That is the opposite of the intuition that any improvement in row 9 brings the citation nearer, and it is the single fact worth carrying out of this document into the design work.

## What this changes

Item 6's negative control is **not gated on simulator time**, and buying it first would buy a control that cannot fire. It is gated on the nominal campaign having a yield whose interval clears the control's -- which is to say on **the design meeting ratified row 9**, a design precondition rather than a sampling or tooling one. What the two derived sections above add is *how well* it has to do, and what that costs:

- **The target is a pass rate, and it is ~100 %.** The cheapest campaign guard 3 would accept is probe 10's: 183 measurable draws, every one meeting row 9, against a 2-draw control -- roughly the ~400 h this directory has quoted all along, but conditional on a pass rate nobody had stated. Stopping part-way is not a partial saving, it is the expensive region: `required_n` peaks in the middle, so a design meeting row 9 half the time costs ~50x the campaign of one that meets it always. The design gap itself is **#202**, filed from this document because until this derivation there was no target to file it against.
- **#195** (the degraded-design control) is cheaper than its own estimate said, and still cannot be bought first. At the 5-draw nominal it was sized against it needs 6 control draws rather than 5 (probe 7); against a nominal that is also *sized*, `klt yield`'s 2-draw minimum is enough (probe 10). Either way it buys nothing while row 9 is missed by every draw: the control is the cheap half of this precondition, and the nominal is the whole cost.
- **The sized campaign** (~400 h for `required_n` = 183) does not unlock the control as a side effect: probe 2 is exactly that campaign with row 9 still missed on every draw, and it is `not_detected`. Worse, the `required_n` = 183 that figure rests on is the *zero-failures* branch -- it is the size of a campaign that fails everywhere, and it stops being the right size the moment the design starts passing.

The escape hatch `signoff/run-signoff.sh`'s guard 3 names -- an argued record of why `not_detected` is honest for the limit it is checked against -- is therefore the *only* outcome this campaign can currently reach, and this document is the argument it would rest on. It is not enough on its own to cite item 6: guard 3 still requires a sized population (`signoff/item6-preconditions.md` row 5), and `klt yield` still cannot be reached from this repo's own pin (klayout-tools#2466), so no report *declaring* a control can be produced under it. What this settles is the ordering question #195 asked, and it settles it against spending the simulator time first.
