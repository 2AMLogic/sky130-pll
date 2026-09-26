# `sim/pll-lock-mc-negative-control/` — T1 item 6's negative control

This unit is `sim/pll-lock-mc`'s campaign run against a **deliberately degraded
variant of its own DUT**. It exists because T1 item 6 (*Statistical claims carry
Monte Carlo evidence*) requires a **deterministic negative control** per Monte
Carlo campaign, and `klt yield` grades one from per-measurement
`negative_control` metadata: a seeded known-bad variant's own samples of the
*same* measurement, which the campaign's statistics must be shown to separate
from the nominal population.

**Status: testbench committed, no record yet.** Nothing in this directory is
evidence today, and `sim/pll-lock-mc/analysis/yield-evidence/` therefore still
carries `klt yield`'s own missing-negative-control warning. See
"What is still owed" at the bottom for exactly what is outstanding and what it
costs; issue #195 tracks it.

## What is degraded, and why that

`design/top/top.sch` with **`design/loop-filter`'s `C2` at a quarter of its
drawn area** — `W=L=72 µm` → `36 µm`, i.e. 10.47 pF → 2.64 pF by the
`cap_mim_m3_1` subcircuit's own capacitance expression. `R1`, `C1`, `R3`, `C3`
and every other device, net, label and property of the four-block closed loop
are unchanged.

`C2` is the shunt capacitor at the charge-pump node, and
`design/loop-filter/DESIGN.md` states its design purpose directly: it "adds the
filter's first non-zero pole" in order to "attenuate reference-frequency ripple
reaching `VCTRL`". Ripple on `VCTRL` is what frequency-modulates the ring, and
period jitter at `CLK` is what ratified spec row 9 bounds — so shrinking `C2`
degrades **exactly the mechanism the measurement under grading is taken over**,
and nothing else's design intent.

Three properties made it the right knob rather than one of the other four
passives, and the third is the one a negative control lives or dies on:

1. **It is monotone and exactly stateable.** One drawn geometry on one
   component, so the injected degradation is a factor, not a hand-tuned number.
2. **It does not degrade rows 6/7.** Per that same document's derivation the
   `C2` pole `1/(2π·R1·Ceff)` moves *further above* the loop crossover as `C2`
   shrinks, so phase margin does not fall — a control that destabilised the loop
   would be testing something else.
3. **It does not cost the lock.** A draw that never locks carries **no**
   period-jitter figure at all (row 9 is a post-lock quantity), so it is
   censored out of the control's own denominator rather than counted as a
   failing sample — which, as the sizing section below shows, is the difference
   between a control that fires and one that does not. `C2` is a few per cent of
   the `C1+C2+C3` that document identifies as the cold-start acquisition ramp's
   capacitance, so the ramp the 50 µs window pays for is essentially unchanged.

**Neither the factor nor those last two properties are asserted.**
`sim/lf-c2-jitter-sensitivity` measures this exact netlist's post-lock period
jitter against the unmodified design's, at the same sampling point and the same
device draw, and that unit's record family is where the `4` comes from.

## Why this is a *third* control, not a duplicate of the two that exist

This repo already has two committed controls for the same reducer, and neither
is the one item 6 asks for. The distinction is the point, so it is stated here
rather than left to be re-derived:

| Unit | Kind | What it degrades | What it demonstrates |
| --- | --- | --- | --- |
| `sim/jitter-floor` (#178) | **null** control | nothing — an ideal source whose true period jitter is zero by construction | what the `linearize` → `wrdata` → `edge_times` → `period_jitter` pipeline *reports* for a signal that does not jitter, i.e. the dump-grid resolution floor |
| `sim/jitter-calibration` (#185, #197) | **known-bad measurement input** | the *measurement input* — an ideal source at a known nonzero injected jitter | that the reducer recovers an injected figure, and by how much it errs where the grid cannot resolve the edge |
| **this unit** (#195) | **known-bad design** | the *DUT*, by one stated loop-filter parameter | that *this campaign's statistics*, over this population, separate the real design from a worse one |

Both of the first two are load-bearing and neither is a degraded design.
Declaring either one's samples as this campaign's `negative_control` would claim
the statistics separate the population from a degraded PLL when what they
actually separate it from is an ideal pulse source; `signoff/README.md`
§ "Why every other row is `unmet`" case 4b records that decision.

## Why six draws

Six is not a round number. It is the arithmetic in
`sim/pll-lock-mc/analysis/negative-control/reachability.md`, applied to the
nominal population as it now stands.

`klt yield` reports a control `detected` on two conjuncts and nothing else: the
control's own empirical yield strictly below the nominal's, **and** the
control's 95 % interval upper bound strictly below the nominal's interval lower
bound. Against `sim/pll-lock-mc/records/20260925-224917-3a2dd6e.md` — 5 of 5
draws meeting row 9, Clopper-Pearson lower bound **0.478176** — a control in
which *no* draw meets the bound has an interval upper bound of

| Control draws | Interval upper bound | Below 0.478176? | Verdict |
| --- | --- | --- | --- |
| 5 | 0.521824 | no | `not_detected` (committed probe `p4`) |
| **6** | **0.459258** | yes | **`detected`** (committed probe `p7`) |

Both rows are *executed* `klt yield` outputs committed under
`sim/pll-lock-mc/analysis/negative-control/`, not a formula quoted here, so the
threshold is a measured property of the tool. Six is therefore the **cheapest
sufficient** control against today's nominal population — which is also the
whole reason this unit could not be run before #202 landed: while the nominal
campaign's empirical yield was exactly 0, *no* control of any size or
degradation could satisfy either conjunct, and that is what
`reachability.md` proves.

**It is only sufficient if all six draws both lock and miss.** One draw that
meets the 1.0 % bound takes the control's estimate to 1/6 and its interval upper
bound above the nominal's lower bound; one draw that never locks is censored out
of the denominator and takes the control back to five. That is the sizing
constraint the degradation had to be chosen against — large enough to clear the
bound on every draw, small enough to keep every draw locking — and it is why the
factor was measured rather than guessed.

## What is identical to the campaign, and what differs

A negative control has to be the **same experiment** or its samples are not
comparable with the population they are meant to separate from. Everything that
decides *what is measured* is `sim/pll-lock-mc/testbench/tb.json`'s own,
unchanged: the measured node (`CLK`), the 20 ps dump grid, the 200 ps
internal-step cap, `.options reltol=1e-4`, the 50 µs window, the `DR-005`
discharged-loop-filter cold start, the lock criterion, the 20-cycle post-lock
population floor, the ratified 1.0 % bound with `gate_on_bound` left **true**,
and the `(corner, temperature, supply, mismatch, process)` sampling point.

Three things differ, and only three: the DUT, the trial count (6, above), and
this manifest's own `negative_control` block naming the degradation.

That is **checked rather than asserted**, in two places:

- `sim/pll-lock-mc/analysis/yield_evidence.py` refuses to write a
  `negative_control` block at all unless ten of those fields agree between the
  two manifests — and additionally refuses if the control's draws meet the bound
  at least as often as the nominal's, since `klt yield` could not report
  `detected` for such a control however deliberate its degradation was.
- `testbench/gen_tb.py --check` re-derives this unit's testbench schematic from
  `sim/pll-lock-mc/testbench/tb_pll_lock_mc.sch`'s own body and fails on a byte
  of drift, so "same stimulus, same strapping, same reference" is a property
  rather than a claim about a careful copy. The degraded DUT it points at is
  `sim/lf-c2-jitter-sensitivity`'s committed arm — *referenced*, not copied, so
  this unit's circuit and the sizing evidence for it cannot become two different
  circuits.

**Because `gate_on_bound` is left true, every trial of this campaign is expected
to be recorded as a `FAIL`.** That per-trial verdict is the finding, not a
defect: a control whose draws passed would be the failure. (This is the one
place this unit deliberately does *not* follow `sim/integrator-floor`'s
`gate_on_bound: false` convention for a control unit — there, reporting a floor
figure is the whole result and a bound has no meaning; here, "misses the bound"
*is* the result, and having the harness itself assert it per trial is stronger
than a reading of the table.)

## Reproducing

```sh
# 0. the testbench is generated from the design and the nominal campaign --
#    verify neither has drifted
python3 sim/lf-c2-jitter-sensitivity/testbench/gen_c2_variant.py --check
python3 sim/pll-lock-mc-negative-control/testbench/gen_tb.py --check

# 1. the campaign: 6 draws, seeds 1..6, the same 50 us cold-start window
#    sim/pll-lock-mc runs. Cost is this unit's whole difficulty -- see below.
python3 sim/run_corners.py pll-lock-mc-negative-control --mc --jobs 6

# 2. wire the resulting record into the nominal campaign's sample-set documents
python3 sim/pll-lock-mc/analysis/yield_evidence.py \
    sim/pll-lock-mc/records/<nominal-record>.md \
    --negative-control sim/pll-lock-mc-negative-control/records/<this-record>.md \
    --write

# 3. re-run klt yield over them and diff against the committed outputs
bash sim/pll-lock-mc/analysis/klt-yield-env.sh --write

# 4. regenerate the precondition table from whatever step 3 actually reported
python3 signoff/item6_preconditions.py --write
```

## What is still owed

- **The campaign itself.** Six draws of a 50 µs cold-start transient at
  `reltol=1e-4`; the nominal campaign's own record puts five such draws at
  ≈ 4 h 23 m of wall-clock time at `--jobs 5` on a shared host, so this is a
  real spend and it has not been made. `sim/executor-equivalence/README.md`
  records that no host is provisioned for the batch/remote fleet yet
  (2AMLogic/2am#934), so it is a local spend or none.
- **The `klt yield` verdict.** `negative_control.verdict` must come back
  `detected` — or, if it does not, an argued record for `not_detected` at a
  stated limit with `signoff/run-signoff.sh`'s guard 3 relaxed in the same
  change to accept that limit explicitly. **No verdict is claimed here**: the
  table above says which population *would* be `detected` per the committed
  probes, which is arithmetic over the tool, not a result of this unit's own
  run. Note also that `klt yield` is not reachable from this repo's pinned wheel
  at all (klayout-tools#2466) — `sim/pll-lock-mc/analysis/klt-yield-env.sh` is
  the recipe that builds it.
- **`signoff/item6-preconditions.md` row 3**, which is generated from the
  committed report and will keep reading `unmet` until that report carries a
  fired control.

Even with a `detected` control, T1 item 6 stays `unmet`: guard 3's *other*
condition is that the cited report's estimate be **sized**, and a 5-draw nominal
population is not (`sample_size.verdict` `insufficient`). This unit closes one
of two preconditions, and says so rather than implying it turns a row green.
