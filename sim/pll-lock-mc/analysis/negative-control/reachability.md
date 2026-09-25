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

Three things those rows establish that prose could not:

1. **Probe 1**: the campaign as committed cannot produce `detected`, and the control it is checked against is not a weak one -- it is 1000 draws, every one of them outside the measurable regime. There is no stronger control to build.
2. **Probes 2 and 3**: neither widening the population to `required_n` = 183 nor landing a single passing draw changes that. The threshold is on the nominal interval's *lower* bound, which a near-zero yield does not lift past even a 1000-draw control's upper bound.
3. **Probe 4**: a control the size #195 costs at 5 draws, checked against a 5-draw nominal in which *every* draw passes, is still `not_detected`. At these population sizes the pairing is unreachable no matter how good the design or how bad the control: a 5-draw control's own 95 % interval still reaches 0.521824, while the best lower bound a 5-draw nominal can reach -- at 5 of 5 passing -- is 0.478176. Five draws a side is simply too few for two exact binomial intervals to separate.

Probes 5 and 6 are the positive control for the set: one passing draw apart, at 183 draws a side, they straddle the threshold and probe 6 reports `detected`. The harness can produce both verdicts, so probes 1-4 report their populations rather than a broken probe.

## What this changes

Item 6's negative control is **not gated on simulator time**, and buying it first would buy a control that cannot fire. It is gated on the nominal campaign having a yield whose interval clears the control's -- which is to say on **the design meeting ratified row 9 in enough draws**, a design precondition rather than a sampling or tooling one. Both halves of this issue's remaining spend are affected:

- **#195** (the degraded-design control, ~6.7 h at 5 draws) cannot close item 6's negative-control precondition while row 9 is missed by every draw, and at 5 draws a side cannot close it even if row 9 were met by all of them. Probe 4 is the number to read before sizing it.
- **The sized campaign** (~400 h for `required_n` = 183) does not help either: probe 2 is that campaign, and it is still `not_detected`. `sim/pll-lock-mc/analysis/README.md` already argued that spend sharpens an interval rather than changing a verdict; this adds that it does not unlock the negative-control precondition as a side effect.

The escape hatch `signoff/run-signoff.sh`'s guard 3 names -- an argued record of why `not_detected` is honest for the limit it is checked against -- is therefore the *only* outcome this campaign can currently reach, and this document is the argument it would rest on. It is not enough on its own to cite item 6: guard 3 still requires a sized population (`signoff/item6-preconditions.md` row 5), and `klt yield` still cannot be reached from this repo's own pin (klayout-tools#2466), so no report *declaring* a control can be produced under it. What this settles is the ordering question #195 asked, and it settles it against spending the simulator time first.
