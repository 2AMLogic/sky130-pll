# `sim/pll-lock-mc/analysis/` — the Monte Carlo record, graded and floor-corrected

Three derived readings of one record live here: its **grading** by `klt yield`
(yield, confidence interval, Cpk, sample-size verdict — the sections from
"Reproducing" down), its **restatement against the measurement-resolution
floor** `sim/jitter-floor` measures (issue #178 — see "The measurement floor,
quantified"), and the **reachability of item 6's negative control** over this
population (issue #182 — see "Can a negative control fire here at all?"). None
of them simulates; all three only restate committed artifacts.


`sim/pll-lock-mc/records/20260924-222341-a9375a5.md` is this repo's Monte Carlo
population for **ratified** spec row 9 (period jitter ≤ 1.0 % of the output
period, RMS, at `CLK` in lock — `DR-006`). The record states its per-trial
result; it does not state a *yield*, a confidence interval, a Cpk, or whether
five draws are enough draws to say anything at all.

This directory answers those four questions with `klt yield`, the verb
`klayout-tools`' own T1 checklist names as the machine-checkable evidence for
item 6 ("Statistical claims carry Monte Carlo evidence"). It is an `analysis/`
directory in the sense `sim/README.md` defines — mutable, stdlib-only, reads a
committed record and restates what the record already says. **Nothing here
simulates, and nothing here introduces a number the record or its testbench
manifest does not already carry.**

| File | What it is |
| --- | --- |
| `yield_evidence.py` | Reads the record's per-trial table + `../testbench/tb.json` and writes the two input documents below. `--check` re-derives them and fails on any drift, per `sim/README.md`'s rule for this directory. |
| `yield-evidence/mc-samples.json` | The `klt yield` sample-set document (generated). |
| `yield-evidence/mc-samples-censored-as-failures.json` | The same draw under the alternative mapping of the two no-lock trials (generated) — see "The two no-lock draws" below. |
| `yield-evidence/spec-limits.json` | Row 9's ratified bound as a spec-limits file (generated). |
| `yield-evidence/klt-yield-report.json` / `.txt` | `klt yield`'s report over `mc-samples.json` — **the artifact this directory exists to produce**. |
| `yield-evidence/klt-yield-report-censored-as-failures.json` / `.txt` | The same, over the alternative mapping. Committed so "the mapping does not change the verdict" is checkable rather than asserted. |
| `jitter_floor.py` | Reads the record's per-trial table **and** `sim/jitter-floor`'s records, and restates the three measured period-jitter figures against the measurement-resolution floor those records put a number on (issue #178). Same `--check` contract. |
| `jitter-floor/restatement.md` | That restatement (generated) — **the artifact that says whether this campaign's recorded miss is the circuit's or the dump grid's.** See "The measurement floor, quantified" below. |
| `negative_control_reachability.py` | Reads the two committed reports above plus the committed probe reports, and derives whether `klt yield` can report a negative control `detected` over this campaign **at all** — and, for the populations nobody has run, which ones would. Same `--check` contract; the derived half additionally re-derives every committed probe's interval bounds, verdict and sample-size state and refuses to render if any disagrees with the tool. |
| `negative-control/probes/*.json` | Eleven synthetic `klt yield` sample-set documents (generated) that probe the tool's negative-control detection rule — evidence about `klt yield`, not about the PLL. |
| `negative-control/reports/*.json` | `klt yield`'s own outputs over those probes. Committed so the rule is checkable rather than quoted. |
| `negative-control/reachability.md` | The reachability verdict (generated) — **the artifact that says item 6's negative control is gated on the design rather than on simulator time, and prices what closing it costs.** See "Can a negative control fire here at all?" below. |
| `klt-yield-env.sh` | Builds `klt_yield_native` in a throwaway virtualenv from the upstream tag that published the pinned wheel, then regenerates and diffs **every** `klt yield` output in this directory. The reproduction recipe for artifacts this repo's own pin cannot produce. |

## Reproducing

```sh
# 1. the two input documents, from the record
python3 sim/pll-lock-mc/analysis/yield_evidence.py \
    sim/pll-lock-mc/records/20260924-222341-a9375a5.md --check   # verify
python3 sim/pll-lock-mc/analysis/yield_evidence.py \
    sim/pll-lock-mc/records/20260924-222341-a9375a5.md --write   # re-derive

# 2. every klt yield output in this directory, from a build of the pinned
#    extension -- verifies the committed ones reproduce byte for byte
bash sim/pll-lock-mc/analysis/klt-yield-env.sh            # verify
bash sim/pll-lock-mc/analysis/klt-yield-env.sh --write    # re-derive

# 3. the measurement-floor restatement (no klt, no PDK -- reads records only)
python3 sim/pll-lock-mc/analysis/jitter_floor.py --check   # verify
python3 sim/pll-lock-mc/analysis/jitter_floor.py --write   # re-derive

# 4. the negative-control probes and the reachability verdict
#    (--write-probes needs no klt; re-run step 2 after changing a probe)
python3 sim/pll-lock-mc/analysis/negative_control_reachability.py --check
python3 sim/pll-lock-mc/analysis/negative_control_reachability.py --write-probes
python3 sim/pll-lock-mc/analysis/negative_control_reachability.py --write
```

Step 2 needs more than this repo's pinned `klt` — see the next section; it is
the only step here that needs a network and a Rust toolchain. Steps 3 and 4
need nothing but Python, and `sim/tests/test_jitter_floor.py` and
`sim/tests/test_negative_control_reachability.py` run their `--check` modes in
`npm run check:ci`, so neither committed document can go stale against the
artifacts it is derived from.

## `klt yield` is not reachable from this repo's pin (verified, not assumed)

`layout/requirements.txt` pins `klayout-tools==0.6.0`, and `signoff/README.md`'s
"Reproducing" section installs exactly that. `klt yield --help` works at that
pin and documents the verb fully. **Running it does not**: the statistics live
in a Rust extension (`klt_yield_native`) that upstream does not publish as a
wheel. Confirmed in a clean virtualenv at the exact pin before any of the work
here was built on it:

```
$ python3 -m venv .venv && .venv/bin/pip install 'klayout-tools==0.6.0'
$ .venv/bin/klt yield <samples> --limits <limits>
{"schema_version": 1, "error": {"command": "yield", "message":
  "the klt_yield_native extension is not installed -- from a repo checkout, run
   `maturin develop --release` inside native/yield/ ..."}}
```

`klt yield --help`'s own text says so ("NOT published as a prebuilt wheel and is
therefore unreachable from a single-package `pip install`/`uv tool install`
(including its git-pinned `@git+...` form) — it needs a full repo checkout plus
a Rust toolchain"), so this is the documented behaviour of the pin, not a
broken install.

**What the verb accepts** (the premise this work had to check before building on
it, `klt yield --help` at `0.6.0`): a `klt sim --format json` Monte Carlo
report, **or** a plain sample-set document
(`{"measurements": [{"name", "unit", "samples", "errored",
"failed_unmeasurable", "limits", "source_corners", "negative_control",
"analytic_cross_check", "sampling"}, …]}`), with spec limits either inline or in
a `--limits` file (`min`/`max`/`target_yield`, plus run-level `confidence` /
`target_ci_halfwidth` / `min_samples`). This repo's campaigns are run by
`sim/run_corners.py`, not `klt sim`, so the second shape is the one that
applies — and **it fits this record with nothing invented**: a numeric sample
per locked draw, the ratified bound as `limits.max`, the single sampling point
as `source_corners`, and a declared count for the draws that produced no value.
There is no schema gap to report; the gap is reaching the verb at all.

**How the reports here were produced**, stated so a reader knows exactly what
they are trusting: the pinned wheel (`pip install 'klayout-tools==0.6.0'`,
`klt --version` → `klt 0.6.0`) plus `klt_yield_native` built once by the
documented remediation — `maturin develop --release` inside `native/yield/` of
an upstream checkout at **tag `v0.6.0`** (commit `c622e8ad`), the tag that
published this wheel, so the Rust core and the Python side are the same
revision. The report carries no `provenance` block of
its own (`klt yield`'s JSON has none at this version), which is why that build
identity is recorded here instead.

**That build is now a script, and the reports are now shown to reproduce from
it** (issue #182). `klt-yield-env.sh` performs exactly the sequence above —
`git clone --branch v0.6.0`, assert the tag still resolves to `c622e8ad`, the
pinned wheel into a throwaway virtualenv, `maturin develop --release` into that
same virtualenv — and then regenerates every `klt yield` output in this
directory and diffs it against the committed one. Run on this tree, all ten
committed outputs (the four `yield-evidence/` reports and the six
`negative-control/reports/` probes) reproduce **byte for byte**. Nothing it
creates is committed and it never touches the host's tools.

That does not close klayout-tools#2466, and this section still stands as
written: the extension remains unreachable from a plain `pip install` of the
pin, so CI cannot regenerate these artifacts and a citation resting on them is
still resting on something CI cannot check. What changed is that "built by
hand" is no longer the recipe — any reviewer with a Rust toolchain and a
network can now re-derive every number in this directory from upstream source
and be told, by exit status, whether it matched.

Filed upstream per `CLAUDE.md`'s friction protocol, described generically:

- [klayout-tools#2466](https://github.com/2AMLogic/klayout-tools/issues/2466) —
  the extension is unreachable from every published release, while `klt
  signoff` kind-restricts T1 item 6 to this verb's envelope, so that item is
  ungradeable for a consumer that pins a release (and a report built from a
  hand-built extension is not reproducible under that pin). Successor to
  upstream #1061, which closed the *discoverability* half of the same gap.
- [klayout-tools#2467](https://github.com/2AMLogic/klayout-tools/issues/2467) —
  `klt signoff` grades a yield citation on `status` alone, consulting neither
  the report's own `sample_size.verdict` nor its missing-negative-control
  warning. This is the gap behind the citation decision below.
- [klayout-tools#2468](https://github.com/2AMLogic/klayout-tools/issues/2468) —
  no category for a draw censored by a conditioning event, which is what forced
  the two mappings below.

## The two no-lock draws

Three of the five draws locked and carry a period-jitter figure; two never
locked inside the 50 µs window and therefore carry none, because row 9 is a
*post-lock* quantity. The record is explicit that such a trial "contributes no
period-jitter figure … it is not charged as a jitter failure, because a design
that has not converged has no post-lock population to measure jitter over."

`klt yield` offers two ways to declare a draw with no value, and neither
describes a censored one: `errored` (a tooling failure — excluded from every
statistic *including* the denominator, with a warning that the estimate is
conditional) and `failed_unmeasurable` (a design failure whose failure mode
*is* the absence of a value — counted as a failing draw). A draw that never
locked is neither: the simulator exited 0 and the harness reduced it exactly as
it reduced the others, and row 9 is *undefined* for it rather than violated by
it (the row that bounds reaching lock at all is row 8, DRAFT).

So both readings are published:

| Mapping | Empirical yield | `yield.empirical.n` | 95 % CI | `sample_size.verdict` |
| --- | --- | --- | --- | --- |
| `errored: 2` (**primary** — matches the record's own treatment) | 0.000000 | 3 | [0, 0.7076] | `insufficient` (`required_n` 183) |
| `failed_unmeasurable: 2` (sensitivity check) | 0.000000 | 5 | [0, 0.5218] | `insufficient` (`required_n` 183) |

The mapping moves the sample size and the interval width. It does not move the
verdict: **no draw in this campaign met row 9 under either reading**, and the
distribution fit (`mean` 2.169 %, `stddev` 0.794 %, `cpk` −0.491,
`sigma_to_spec` −1.473, limiting side `upper`) is identical, since both
mappings exclude valueless draws from the fit.

## The sample-size question, answered

`klt yield`'s own verdict is **`insufficient`**, and this directory records that
rather than presenting a five-draw campaign as a sized yield estimate:

- `n` = 3 numeric samples (5 draws, 2 censored).
- `observed_ci_halfwidth` = **±0.354** in absolute yield, against the requested
  `target_ci_halfwidth` of ±0.01.
- `required_n` = **183** samples for that precision at the observed pass rate.
  Read that figure with its branch attached: `method` is
  `clopper-pearson-zero-failures`, so 183 is the size of a campaign in which
  **no** draw passes. It stops being the right number the moment one does — see
  "How well the design has to do, and what that costs" below, where the same
  183-draw campaign at 9 passing draws reports `required_n` = 1797.
- `required_n_for_target` = `null` — no `target_yield` is declared, and none can
  be: row 9 states a jitter bound, `DR-006` states no yield target, and
  inventing one here would be a spec change without a decision record
  (`CLAUDE.md`). `klt yield` therefore reports `status: "reported"`, a
  measurement that "can never fail".

**The campaign was not widened, and that is a cost decision stated rather than
hidden.** 183 *measurable* samples at this campaign's observed 3-of-5 lock rate
is ≈ 305 draws; at the ~1 h 20 m per trial the record's own execution notes
give, that is ≈ 400 h of simulator time — real money on the batch fleet, and
~60× the ≈ 6.7 h the five draws already recorded cost. Three reasons it is not
the next thing to spend it on:

1. **It would sharpen an interval, not change a verdict.** The point estimate is
   already 0 % with a *negative* Cpk: the fitted mean (2.169 %) sits outside the
   1.0 % bound by 1.47 sample standard deviations, so the question 183 samples
   answers is "how far below the bound is the yield", not "is the row met".
2. **The binding uncertainty is not sampling noise.** Each sample carries the
   200 ps dump-grid resolution floor the record states, against a 40 ps budget.
   That floor is **no longer unquantified** — `sim/jitter-floor` measured it
   (#178) and `jitter-floor/restatement.md` below restates these figures against
   it — and the answer is that it does not explain the miss. The residual
   uncertainty it leaves is still not sampling noise, though: it is the floor a
   *jittering* signal carries — which the null control cannot reach, and which
   `sim/jitter-calibration` has since measured directly (#185, see below) — and
   which draw sits at which end of the floor family (#186). Buying 300 more
   draws sharpens none of those.
3. **A sized campaign also needs a negative control**, and — measured since,
   see "Can a negative control fire here at all?" below — **sizing does not
   supply one**. Probe `p2` of `negative-control/` is precisely this campaign
   widened to 183 measurable draws with row 9 still missed on every one, checked
   against the strongest control `klt yield`'s schema can express, and it still
   reports `not_detected`. Widening therefore buys 305 draws of a campaign that
   still could not close item 6, and it does not get closer to closing it either.

The condition under which widening *is* the right call is now sharper than
"once #178 has put a number on the resolution floor" — #178 has, and the floor
does not explain the miss. What is left is the design work on row 9 (**#202**),
and the threshold it has to clear is now a number rather than a direction:
widening pays once the design meets row 9 on essentially every draw, which is
both when a 183-draw campaign is sized again and when a negative control can
fire. Anywhere in between costs more, not less — the derivation is in "How well
the design has to do, and what that costs" below. Until then the honest
statement is the one the committed report makes — 0 % yield over 3 measurable
draws of 5, interval [0, 0.71], sample size insufficient.

## The measurement floor, quantified

`jitter-floor/restatement.md` is the second artifact this directory exists to
produce, and it answers the question the record itself had to leave open: **is
the 1.584 % / 1.851 % / 3.073 % miss the circuit's, or the 200 ps dump grid's?**

`sim/jitter-floor` (#178) measures the floor directly, with no PLL transient at
all — an ideal source of exactly constant period (true jitter zero) through the
identical reducer at the identical grid. Its family, and this campaign's figures
restated against it:

| Trial | Measured | Floor at that draw's period | Floor-removed | Still misses row 9? |
| --- | --- | --- | --- | --- |
| 2 | 1.584 % (63.3 ps) | 0.381 % (15.2 ps) | 1.537 % | yes |
| 3 | 1.851 % (73.9 ps) | 0.720 % (28.7 ps) | 1.705 % | yes |
| 5 | 3.073 % (120.4 ps) | 2.371 % (92.9 ps) | 1.955 % | yes |

At the other end of the family — an edge the grid resolves rather than one it
cannot — the measured floor is **0.000 %** and the figures stand unchanged. So
under both regimes the control covers, the recorded miss is attributable to the
circuit, and trial 5 misses even under the most pessimistic floor the arithmetic
allows at this grid (`tran_step/2` = 100 ps). The generated document states the
one gap that remains — an *intermediate* floor, for edges the grid only partly
resolves at grid phases spread by a draw's own jitter, could still put trials 2
and 3 inside the bound, and only a source of known **nonzero** injected jitter
(#185) settles that.

**That source now exists**: `sim/jitter-calibration` (#185) is the same kind of
harness control one step further on — a PWL clock whose rising-edge schedule is
drawn from a seeded RNG at an exactly specified nonzero RMS period jitter, run
through the identical reducer at the identical 200 ps grid, so
*reported*-against-*injected* is a calibration curve rather than a floor. Its
`analysis/calibration.md` measures what the null control cannot: the floor a
signal that genuinely jitters carries, and how that floor moves from the
constant-period walk-phase regime toward the uniformly-spread-phase one as the
source's own jitter grows relative to the grid step. Read it before applying a
`sim/jitter-floor` figure to a jittering signal: **which way** that correction
errs depends on the period. Measured at the campaign's two nominal periods
(#197), the null control's floor is the *larger* of the two grid bounds at
`frac(period/step)` = 0.585 and over-corrects, and the *smaller* one at 0.976
and under-corrects — so a null-control floor is neither a conservative bound
nor a consistently optimistic one. One of those two periods is trial 2's own;
what that coverage should change in the restatement below, if anything, is
**#205**, not this directory's to assume.

None of this moves the record: it stands exactly as written, per
`sim/README.md`'s append-only rule. The restatement is a derived reading of it,
and `jitter-floor/restatement.md` is deliberately **not** re-derived against the
calibration curve here — restating a Monte Carlo draw against a floor measured at
a *different* source's jitter magnitude is a further step, and it is not taken
silently inside this README.

## The negative control: coordinated with #178, not built twice

T1 item 6 requires a **deterministic negative control** per campaign, and `klt
yield` supports one directly (`negative_control`: a seeded known-bad variant's
own samples, checked for a statistically distinguishable degradation). This
campaign declares none, so both committed reports carry the tool's own run-level
warning:

> no measurement declared a `negative_control` — this campaign has no seeded,
> known-bad variant demonstrating that the statistics above can actually detect
> a degraded design

**#178 built that control, and it is `sim/jitter-floor`** — five committed
records of an ideal source of exactly known period through the same `linearize` →
`wrdata` → `edge_times` → `period_jitter` pipeline (see the section above).
Nothing here built a second one, and `yield_evidence.py` still needs no change to
carry one: `negative_control` is per-measurement metadata in the same sample-set
document.

**It is not, however, item 6's control, and this directory does not pretend
otherwise.** The two are different *kinds*: `sim/jitter-floor` is a **null**
control (a signal whose true jitter is zero, which measures the pipeline's
floor), while item 6 / `klt yield` want a **known-bad** variant whose degradation
the statistics must detect. The null control proves the reducer does not invent
jitter out of nothing at a grid that resolves the edge, and puts a number on what
it does invent at one that does not — genuinely load-bearing, but it demonstrates
nothing about detecting a *degraded design*.

**The known-bad control now exists** — `sim/jitter-calibration` (#185, extended
by #197), eighteen committed records of a source at a known **nonzero** injected
jitter (0.5 %, 1.0 % and 2.0 % RMS at three transition times, at each of two
nominal periods) through the same pipeline. It is
the *kind* of control item 6 and `klt yield`'s `negative_control` ask for: a
seeded, known-bad input whose degradation the statistics must detect, and which
they do detect — the reducer returns the injected figure exactly where the grid
resolves the edge, and its departure elsewhere is quantified rather than
asserted.

**Three things that still does not do, stated so nobody reads more into it.**
(a) It degrades the *measurement input*, not the *design*: its DUT is a voltage
source and a resistor, so it demonstrates that the reducer detects a degraded
signal, not that this campaign's statistics detect a degraded PLL. (b) Nothing
here wires it into either committed `klt yield` report — `negative_control` is
per-measurement metadata in the sample-set document `yield_evidence.py` renders,
and populating it is a separate, deliberate act. (c) Whether item 6's citation
may lean on it at all is **#182's** decision, not this directory's. Both
committed reports therefore still carry the missing-negative-control warning
above, and the citation decision below is unchanged.

**That decision has since been made** (`signoff/README.md` § "Why every other
row is `unmet`", case 4b): neither `sim/jitter-floor` nor
`sim/jitter-calibration` is item 6's control, because neither degrades the
*design*. The control item 6 still lacks is a seeded, deliberately degraded
variant of the DUT re-drawn through this campaign, filed as **#195** — and the
next section is the reason #195 should not be run yet.

## Can a negative control fire here at all?

`negative-control/reachability.md` is the third artifact this directory exists
to produce, and it answers a question that was assumed rather than checked for
as long as item 6's negative control has been outstanding: **could `klt yield`
report a control `detected` over this population, if one existed?**

It cannot. `klt yield` decides that verdict with two comparisons and nothing
else — the control's own empirical yield strictly below the nominal's, *and* the
control's interval upper bound strictly below the nominal's interval lower bound
(`native/yield/src/estimate.rs:1193-1199` at tag `v0.6.0`, the revision that
built every report here). This campaign's committed report puts the nominal
estimate at **0.0** and its interval's lower bound at **0.0**, under both
censored-draw mappings. A control's own estimate and interval upper bound are
proportions of a draw count, so neither can be negative: both conjuncts are
unsatisfiable. **No negative control — at any population size, at any
degradation — can be `detected` over a campaign whose empirical yield is zero.**
A floor-bounded yield has nothing below it to degrade toward.

Eleven executed `klt yield` probes are committed under `negative-control/` so
that is checkable rather than quoted, with the strongest control the schema can
express (every draw `failed_unmeasurable`) on the other side. The three that
matter for what to spend next:

- **This campaign as committed, against a 1000-draw control**: `not_detected`.
- **This campaign widened to `required_n` = 183, still missing row 9 on every
  draw**: `not_detected`. The ≈ 400 h does not unlock the negative-control
  precondition as a side effect.
- **183 measurable draws in which *every* one meets row 9, against a 2-draw
  control**: `detected` — and `sample_size.verdict` `sufficient`. It is the only
  committed population where both of guard 3's conditions hold at once, i.e. the
  cheapest campaign the guard would actually accept.

The other eight straddle three thresholds one draw apart each (8 vs 9 passing at
a 183-draw control; 20 vs 21 at a 50-draw one; a 5-of-5 nominal against a 5- vs
a 6-draw control), which is what makes the `not_detected` rows a property of the
populations under test rather than of a broken probe.

### How well the design has to do, and what that costs

The rule is a comparison of two Clopper-Pearson intervals, so the *forward*
question — which populations would work — is arithmetic rather than opinion, and
`reachability.md` now derives it. It checks that arithmetic against all eleven
committed `klt yield` outputs first (each probe's interval bounds,
`negative_control.verdict`, `required_n` and `sample_size.verdict` must come
back out of the formulas) and refuses to render on a single disagreement. Three
readings come out of it that the probes alone did not give:

1. **"Five draws a side is too few" was about the diagonal, not the size.** The
   same 5-of-5 nominal that is `not_detected` against a 5-draw control is
   `detected` against a **6**-draw one. The control is the cheap half of this
   precondition; against a nominal that is also *sized*, `klt yield`'s own
   2-draw minimum is enough. **#195** is therefore smaller than its own estimate
   assumed — and still not buyable first, because it buys nothing while row 9 is
   missed on every draw.
2. **Guard 3's two conditions pull against each other.** `required_n` uses an
   exact zero-failures interval at a pass rate of exactly 0 or exactly 1 and a
   normal approximation in between, so it *peaks in the middle*. This campaign is
   "sized" at 183 today only because **no** draw passes; the first draws that
   pass make it unsized (`required_n` 209 at 182 of 183, 1797 at 9 of 183).
3. **So the target is a pass rate, and it is essentially 100 %.** The cheapest
   citable campaign is 183 measurable draws with every one meeting row 9, plus a
   2-draw control: ≈ 307 drawn trials, ≈ 409 h — roughly the ≈ 400 h quoted
   above, but conditional on a pass rate nobody had stated. A design meeting
   row 9 half the time costs ≈ 21,000 h, about 50× as much. **Part-way is the
   expensive place to stop.**

**What this changes:** item 6's negative control is not gated on simulator time.
It is gated on the nominal campaign having a yield interval that clears the
control's, which is to say on **the design meeting ratified row 9 on
essentially every draw** — a design precondition, not a sampling or tooling one.
That design gap is **#202**, filed against the table above because until it was
derived there was no target to file it against. `#195` should be sized against
`negative-control/reachability.md` before any of its time is bought, and
`signoff/item6-preconditions.md` row 3 says so from the report's own fields
rather than in prose here.

## Why `signoff/block-manifest.json` does not cite this report

It would turn T1 item 6 green. `klt signoff` grades a yield citation as passing
when `status` is `"pass"` or `"reported"` — and `"reported"` is exactly what a
measurement with no `target_yield` produces — while consulting neither
`sample_size.verdict` nor the missing-negative-control warning
(klayout-tools#2467). Citing this report today would therefore render item 6
`met` on a campaign whose own artifact says its yield estimate is unsized, whose
measured yield is 0 %, and which has no self-check demonstrating the statistics
can detect a bad design.

That is the trade `signoff/README.md` declines twice already — for the four
items with no `klt` verb behind them, and for item 11's real, clean `klt erc`
envelope that answers two of three rules. The same answer is given here, with
the same reasoning, and it is recorded in `signoff/README.md` § "Why every other
row is `unmet`" rather than only here. The report is committed regardless: the
gap it documents is worth more as a measured artifact than as a sentence.

**The decline is enforced, not merely argued (issue #182).**
`signoff/run-signoff.sh`'s guard 3 refuses to render a manifest that cites a
`klt yield` report whose measurements are not sized (`sample_size.verdict` ≠
`sufficient`) or declare no negative control that fired (`negative_control` →
`verdict` ≠ `detected`). Citing this report today therefore fails the signoff
run with both conditions named, rather than producing a green row and a README
that has to be re-read to notice. Measured, not assumed: without the guard the
same manifest entry takes `t1_met_count` from 2 to 4, and with a scratch copy
of this report patched to `sufficient` + `detected` it passes cleanly — so the
guard blocks exactly this campaign's citation and not the sized one that
replaces it. The guard retires when
[klayout-tools#2467](https://github.com/2AMLogic/klayout-tools/issues/2467)
lands and `klt signoff` applies the same two checks itself.

What that leaves as the remaining work on item 6 has **changed**, and not in the
direction this section used to point. It named two things: a known-bad control
and a sized population. Both are still outstanding, and neither is a re-reading
of this report — but "Can a negative control fire here at all?" above shows that
*buying either one first would not close the item*. The guard's `detected`
condition is unreachable over a campaign whose empirical yield is zero, and
sizing the population does not lift it. The first thing item 6 now needs is
design work on ratified row 9 (**#202**) — and the bar is not "enough draws",
it is **essentially every draw**: the cheapest population that is both sized and
`detected` is 183 measurable draws with none of them missing the 1.0 % bound
(≈ 409 h, plus a 2-draw control), while a campaign passing half the time costs
≈ 50× that. After that the control (#195) and the sized campaign are worth their
simulator time, and are cheaper than previously estimated. `klt yield`'s own
unreachability from this repo's pin (klayout-tools#2466) gates the re-run on top
of all of that.

## Provenance

The bundle layout (a deterministic, re-runnable script that reformats a
committed campaign's own numbers into `klt yield`'s input shape, beside the
committed `mc-samples.json` / `spec-limits.json` / report outputs) follows the
precedent `klayout-tools`' own `docs/cli/yield.md` § "Real canary evidence"
records for the sibling canary `2AMLogic/gf180-sar-adc`
(`sim/mc-cdac-mismatch/yield-evidence/`, that repo's PR #149), per `CLAUDE.md`'s
rule to copy the proven pattern and record provenance where we do. Two
deliberate differences: the script lives under this repo's own `analysis/`
convention (`sim/README.md`) with the `--check` mode that convention requires,
and the inputs are derived from a committed **record**'s table rather than from
raw CSVs, because this campaign's per-trial reduction is not committed (the
record's table is the repo's source of truth for these figures, at the three
decimals it prints — ±0.0005 pp, immaterial against a 0.58–2.07 pp miss).
