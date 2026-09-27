# ngspice tolerance audit: do the defaults bias this repo's frequency figures?

Issue #210. This directory holds **no testbench and no record of its own** —
like `sim/executor-equivalence/`, it is a note that reads evidence living in
other campaigns' `records/` directories and states what follows from it.
Nothing here simulates, and every number below is read from a committed record
named beside it.

## The question

`sim/integrator-floor` (issue #202, PR #209) measured `design/vco`'s real ring
open loop at `sim/pll-lock-mc`'s base point, where the ring's true period
jitter is **zero by construction**, and found that ngspice's *default*
integrator tolerances are not a small perturbation on this design:

| Settings | Reported f_out | Reported period jitter |
|---|---|---|
| ngspice defaults (`reltol` 1e-3), 200 ps grid — [`20260925-201301-d8b1ab7`](../integrator-floor/records/20260925-201301-d8b1ab7.md) | 243.8 MHz | **1.543 %** |
| `.options reltol=1e-4`, 200 ps grid — [`20260925-201647-d8b1ab7`](../integrator-floor/records/20260925-201647-d8b1ab7.md) | — | 0.658 % |
| `.options reltol=1e-4`, 20 ps grid, TMAX held at 200 ps — [`20260925-203420-d8b1ab7`](../integrator-floor/records/20260925-203420-d8b1ab7.md) | 251.1 MHz | **0.005 %** |

A **~2.9 % frequency error** and a jitter figure larger than ratified row 9's
entire 1.0 % budget, on a DUT that has neither. PR #209 added the two manifest
knobs that remove it (`measure.options`, `measure.tran_max_step`) but changed
only `sim/pll-lock-mc`. Four campaigns that report frequency-shaped figures
through the same `linearize` → `wrdata` → `edge_times` path were left at the
defaults: **`sim/pll-lock`, `sim/vco`, `sim/vco-supply-pushing`,
`sim/loop-ripple`**. This audit asks, per campaign, whether that matters
*relative to that campaign's own bound or claim margin* — and re-runs only
where it does.

## Method

For the two campaigns cheap enough to measure (`sim/vco`,
`sim/vco-supply-pushing`) the audit is a **paired comparison**: the same point
set run twice on **one host, one ngspice build, one PDK**, so the only
difference between the legs is the simulator's accuracy settings.

- **Leg A** — ngspice's defaults, exactly as the campaign has always run.
- **Leg B** — `.options reltol=1e-4`, a 10× finer dump grid, and
  `measure.tran_max_step` pinning ngspice's TMAX at the step the campaign
  already integrated under, so the finer grid buys resolution without changing
  the integration's step cap.

Leg A doubles as a **cross-host reproduction check**: every standing record
cited here was measured on Darwin arm64, and these legs ran on Linux x86-64.
It reproduced the standing figures **exactly** at seven of the eight points it
re-ran — including all six `vco-supply-pushing` supply rows, where every
frequency and every derived `S_span` came back identical to three or four
significant figures — and at the eighth (`sim/vco` at VCTRL = 1.600 V) it
returned 1.034 GHz against the standing record's 1.033 GHz, a
three-significant-figure rounding difference. That is what makes the
leg-A-to-leg-B difference attributable to the settings rather than to the host,
and it is also the first cross-platform reproduction of either campaign.

None of these records supersedes anything. They are narrow, deliberately
subsetted variant records that exist to measure a *difference*; the standing
full-grid records stay exactly as written, per `sim/README.md`'s append-only
rule.

## What was measured

All legs: `tt`/`ff`/`sf` as noted, one PVT point per supply, `design/vco`'s ring
open loop. `n` is the number of dump-grid steps per output period at the
campaign's own `tran_step` (which, at the defaults, is also ngspice's internal
step cap) — the quantity the results turn out to sort by.

| Campaign / triple | Supply | grid | `n` | leg A f_out | leg B f_out | shift |
|---|---|---|---|---|---|---|
| `vco` tt/27 °C, VCTRL 0.900 V | 1.80 V | 50 ps | 63 | 318.1 MHz | 318.2 MHz | **+0.03 %** |
| `vco` tt/27 °C, VCTRL 1.600 V | 1.80 V | 50 ps | 19 | 1.034 GHz | 1.048 GHz | **+1.35 %** |
| `vco-supply-pushing` ff/125 °C, VCTRL 0.900 V | 1.62 V | 50 ps | 52 | 383.7 MHz | 383.9 MHz | +0.05 % |
| `vco-supply-pushing` ff/125 °C, VCTRL 0.900 V | 1.80 V | 50 ps | 57 | 352.0 MHz | 352.0 MHz | +0.00 % |
| `vco-supply-pushing` ff/125 °C, VCTRL 0.900 V | 1.98 V | 50 ps | 64 | 313.3 MHz | 313.3 MHz | +0.00 % |
| `vco-supply-pushing` sf/125 °C, VCTRL 1.200 V | 1.62 V | 50 ps | 30 | 677.3 MHz | 679.2 MHz | +0.28 % |
| `vco-supply-pushing` sf/125 °C, VCTRL 1.200 V | 1.80 V | 50 ps | 26 | 766.2 MHz | 771.9 MHz | +0.74 % |
| `vco-supply-pushing` sf/125 °C, VCTRL 1.200 V | 1.98 V | 50 ps | 25 | 810.9 MHz | 819.3 MHz | +1.04 % |
| `integrator-floor` tt/125 °C, VCTRL 0.86 V (for reference, #202) | 1.80 V | 200 ps | 20 | 243.8 MHz | 251.1 MHz | +2.99 % |

Records, all in their own campaign's `records/`:

| Leg | Record | Point set |
|---|---|---|
| `vco` A | [`20260927-081603-25bc597`](../vco/records/20260927-081603-25bc597.md) | tt/27 °C/1.80 V, VCTRL {0.9, 1.6} |
| `vco` B | [`20260927-093607-25bc597`](../vco/records/20260927-093607-25bc597.md) | same |
| `vco-supply-pushing` A | [`20260927-072223-25bc597`](../vco-supply-pushing/records/20260927-072223-25bc597.md) | sf/125 °C × 3 supplies, VCTRL 1.2 |
| `vco-supply-pushing` B | [`20260927-080253-25bc597`](../vco-supply-pushing/records/20260927-080253-25bc597.md) | same |
| `vco-supply-pushing` A2 | [`20260927-093811-25bc597`](../vco-supply-pushing/records/20260927-093811-25bc597.md) | ff/125 °C × 3 supplies, VCTRL 0.9 |
| `vco-supply-pushing` B2 | [`20260927-093854-25bc597`](../vco-supply-pushing/records/20260927-093854-25bc597.md) | same |

### A correction the append-only rule requires be stated here

The **first** `vco-supply-pushing` pair (legs A and B, sf/125 °C/VCTRL=1.200 V)
carries a claim in its own text that says that triple is "the single (corner,
temperature, VCTRL) triple whose standing `S_span` sits closest to DR-006's
structural `1/VDD` pushing floor … 5.7 %/V of margin … the triple whose
ABOVE/BELOW-floor classification the smallest frequency shift can flip."

**That is wrong.** Ranking all 60 triples of the standing 45-point record
[`20260923-141525-e514bb0`](../vco-supply-pushing/records/20260923-141525-e514bb0.md)
by `|S_span|`'s distance from the floor at its own rail puts sf/125/1.200
**sixth**:

| rank | triple | `S_span` | floor | margin | as % of `|S_span|` | class |
|---|---|---|---|---|---|---|
| 1 | ff/125 °C/0.900 V | −56.1 %/V | 55.6 | **0.5 %/V** | **0.9 %** | ABOVE |
| 2 | ss/27 °C/0.800 V | −53.3 %/V | 55.6 | 2.3 %/V | 4.3 % | BELOW |
| 3 | fs/27 °C/1.200 V | +58.7 %/V | 55.6 | 3.1 %/V | 5.3 % | ABOVE |
| 4 | fs/125 °C/0.900 V | −58.9 %/V | 55.6 | 3.3 %/V | 5.6 % | ABOVE |
| 5 | ff/−40 °C/0.800 V | −59.6 %/V | 55.6 | 4.0 %/V | 6.7 % | ABOVE |
| 6 | sf/125 °C/1.200 V | +49.9 %/V | 55.6 | 5.7 %/V | 11.4 % | BELOW |

Those records are **not edited** — `sim/README.md`'s append-only rule forbids
it, and a wrong framing in a record whose *numbers* are sound is exactly what a
later document is supposed to correct. Legs A2/B2 are that correction: they
re-ran the audit at rank 1, ff/125 °C/VCTRL=0.900 V, and settled the question
the first pair left open.

## What the shift sorts by: steps-per-period, not frequency

Sort the table above by `n` rather than by campaign and the audit stops looking
like four unrelated answers. The frequency error ngspice's default tolerances
introduce is negligible where the campaign's own grid and step cap resolve an
output period finely, and grows once they do not — which is a statement about
`n`, not about how fast the ring is running.

```
 n    shift
64   +0.00 %
63   +0.03 %
57   +0.00 %
52   +0.05 %
30   +0.28 %
26   +0.74 %
25   +1.04 %
21   +2.99 %   <- integrator-floor (#202), 200 ps grid
19   +1.35 %   <- sim/vco at VCTRL 1.600 V, 50 ps grid
```

Two honest limits on how far to push this. First, it is an **observed pattern
across nine measured points in three campaigns**, not a derivation. Second, it
is monotone only for `n` ≳ 25: the two lowest-`n` points are both the largest
shifts in the set, but they disagree with each other by more than 2× (+2.99 %
at `n` ≈ 21 against +1.35 % at `n` ≈ 19), and they were measured on different
absolute grids (200 ps and 50 ps). So `n` is a reliable indicator of **where**
the default tolerances stop being negligible — somewhere around `n` ≈ 30 — and
is **not** a correction factor for the magnitude once they do. Nothing here
licenses scaling a measured figure by a predicted bias; the only way to know a
point's bias is to run that point both ways, which is what this audit did.

With that said, it explains why `sim/integrator-floor`'s alarming ~2.9 % does not transfer
uniformly: that experiment ran a 250 MHz ring on a **200 ps** grid (`n` ≈ 20),
while `sim/vco` and `sim/vco-supply-pushing` run a **50 ps** grid, so at the
operating points that matter to them they sit at `n` ≈ 50–65 and the bias is in
the fourth decimal place. It is also why the two closed-loop campaigns —
which report a ~250 MHz output on a 200 ps grid, i.e. `n` ≈ 20, precisely
`integrator-floor`'s own condition — are the ones this audit changes.

## Per-campaign verdicts

### `sim/vco` — no re-run needed; manifest unchanged

The campaign backs rows 2 (output band) and 5 (Kvco), **both DRAFT**, and its
own claim says so: it is "measured design input, not a spec claim … it ratifies
nothing." There is no ratified bound here for a shift to flip, so the question
is whether the shift is large enough to change what a future decision record
would conclude from these figures. The paired legs measured:

| Quantity | leg A (defaults) | leg B (tightened) | shift |
|---|---|---|---|
| f_out at VCTRL = 0.900 V (`n` ≈ 63) | 318.1 MHz | 318.2 MHz | **+0.03 %** |
| f_out at VCTRL = 1.600 V (`n` ≈ 19) | 1.034 GHz | 1.048 GHz | **+1.35 %** |
| endpoint-to-endpoint mean slope, the row-5-shaped figure | 1022 MHz/V | 1042 MHz/V | **+1.96 %** |

Neither row's reading changes. Row 2's carried-and-explicitly-not-assumed band
is 10–200 MHz; this ring measures 318 MHz–1.05 GHz, so it is already outside
that band by a factor of ~1.6 at the bottom and ~5 at the top, and a 1.35 %
shift is nowhere near that conclusion. Row 5's only ever-floated number is
gf180-pll's ≤ 150 MHz/V, which `spec/target-spec.md` explicitly refuses to port
("do not port 150"); this ring measures ~1030 MHz/V, ~7× it, and a 1.96 % shift
does not move that either. **No re-run of the 45-point grid, and no change to
`sim/vco/testbench/tb.json`'s accuracy settings.**

Stated rather than buried, because it is the one place this campaign's figures
are soft: the shift is **not uniform across the sweep**. At the VCTRL value
that matters to the closed loop (0.900 V, nearest the 250 MHz target) it is
+0.03 % — nothing. At the top of the sweep it is +1.35 %, and the standing
record's VCTRL = 1.400 / 1.600 V rows across all 45 points run at 750 MHz–1.46
GHz, i.e. `n` ≈ 14–27, in the regime where this audit measured the bias to be
live. A future decision record that quotes a **top-of-band frequency** or a
**local** slope from the upper half of this sweep as a number, rather than as a
bound it clears by a factor of several, should re-measure those points at
`reltol=1e-4` first. That is a caveat on how the existing record is read, not a
defect in it.

### `sim/vco-supply-pushing` — no re-run needed; manifest unchanged

The campaign's own bound is DR-006's structural `1/VDD` pushing floor
(55.6 %/V at 1.80 V), and what it claims per triple is an ABOVE/BELOW-floor
classification. Both pairs were run, and the decisive one is at the tightest
margin in the whole 45-point record:

| Triple | leg | `S_span` | `|S_span|` vs floor | margin | class |
|---|---|---|---|---|---|
| ff/125 °C/0.900 V (rank 1, 0.5 %/V) | A2 | −56.1 %/V | 56.1 vs 55.6 | +0.5 %/V | ABOVE |
| ff/125 °C/0.900 V | B2 | **−56.3 %/V** | 56.3 vs 55.6 | **+0.7 %/V** | **ABOVE** |
| sf/125 °C/1.200 V (rank 6, 5.7 %/V) | A | +49.9 %/V | 49.9 vs 55.6 | −5.7 %/V | BELOW |
| sf/125 °C/1.200 V | B | **+51.9 %/V** | 51.9 vs 55.6 | **−3.7 %/V** | **BELOW** |

**Neither classification flips**, and at the tightest triple in the campaign
the tightened settings move `S_span` by 0.2 %/V — they *widen* its margin
rather than threatening it. The rank-6 triple moves more (+2.0 %/V, +4.0 % of
itself, consuming 35 % of its margin) because its 677–811 MHz frequencies sit
at `n` ≈ 25–30 where the bias is live; it still does not flip. Since the
campaign's tightest-margin triple is also one of its *best*-resolved ones
(VCTRL = 0.900 V is near the bottom of the tuning range, so its period is long
relative to the 50 ps grid), the two effects work against each other rather
than compounding, and the representative-subset comparison is sufficient
evidence. **No full 45-point re-run, and no change to
`sim/vco-supply-pushing/testbench/tb.json`'s accuracy settings.**

One caveat stated rather than buried: the triples at VCTRL = 1.200 V and
1.500 V run at 650 MHz–1.46 GHz, i.e. `n` ≈ 14–28, where this audit measured
shifts up to +1.04 %. Their `S_span` figures carry that uncertainty. None of
them is within 3 %/V of the floor, so no classification in the standing record
turns on it — but a future decision record that quotes a VCTRL ≥ 1.2 V pushing
*magnitude* as a budget number, rather than as a classification, should
re-measure at `reltol=1e-4` first.

### `sim/pll-lock` — manifest re-tuned; full-grid re-run owed and not done here

This is the campaign where the audit bites, and it needed no new simulation to
establish it — only the arithmetic of reading two committed records together:

- `sim/pll-lock` **gates** its verdict column on **ratified** row 9
  (`measure.jitter.gate_on_bound` is `true`, bound 1.0 % RMS). It is the only
  one of the four that gates on a ratified row.
- Its dump grid was **200 ps** and its target output **250 MHz** — `n` ≈ 20,
  which is *exactly* `sim/integrator-floor`'s condition.
- At that condition `integrator-floor` measured **1.543 % RMS** apparent period
  jitter on this design's own ring through this campaign's own reducer, for a
  DUT whose true jitter is zero. That is **1.5× row 9's entire budget**.

So a gated row-9 verdict from `sim/pll-lock` at the old settings was not a
verdict about the circuit, and the ~2.9 % frequency error applies to the
final-window mean frequencies the standing record reports for its ~32
non-locking points (a free-running-ring figure by construction). The *locked*
output frequency is the one figure structurally protected — in lock the loop
pins `f_out` to `N·F_ref` and absorbs a VCO-side bias into `VCTRL` — but lock
*time*, duty and jitter are not.

The manifest therefore now declares `tran_step` 20 ps, `tran_max_step` 200 ps
and `.options reltol=1e-4`, with `timeout_s` raised 43200 → 172800. This is
**convergence on an existing convention, not a novel setting**: the identical
four-block DUT already runs under exactly this triple in `sim/pll-lock-mc`,
`sim/lf-c1-jitter-sensitivity` and `sim/lf-c2-jitter-sensitivity`, so until now
the deterministic and statistical axes of one ratified row were being measured
at different accuracies. On the closed loop the same change flipped
`pll-lock-mc` from 3 locked draws all *missing* row 9 (1.584 / 1.851 /
3.073 %) to 5 locked draws all *meeting* it (0.554–0.717 %) —
[`20260924-222341-a9375a5`](../pll-lock-mc/records/20260924-222341-a9375a5.md)
versus
[`20260925-224917-3a2dd6e`](../pll-lock-mc/records/20260925-224917-3a2dd6e.md).

The manifest's own former justification for *not* refining the grid — that
`tran_step` also caps ngspice's internal timestep, so a finer grid multiplies
the integration cost — has been retired by measurement: `tran_max_step`
decouples the two, and on this ring `tran 20p 6u 0 200p` takes 109,986 internal
steps against 109,989 for `tran 200p 6u`. The finer grid costs a larger
(uncommitted) dump and nothing else.

**What is owed and not delivered here**: the full 45-point re-run at these
settings. One point is a 100 µs cold-start transient on the four-block loop;
issue #103 records ~6.8 wall-clock hours per point at 8-way concurrency on the
reference host, and the sibling campaigns declare a 172800 s per-point hang
guard for a *50* µs window. That is a fleet-scale campaign, not a session-scale
one, and this host is a shared 8-vCPU dispatch worker with no provisioned
remote executor (`sim/executor-equivalence/README.md`,
2AMLogic/2am#934). The standing record
[`20260905-193322-0f1934d`](../pll-lock/records/20260905-193322-0f1934d.md) is
**not edited and not superseded** — only a fresh record can supersede it — and
it should be read with this note beside it until one exists.

### `sim/loop-ripple` — nothing to audit; manifest re-tuned before its first record

`sim/loop-ripple` has **no record at all**: `sim/loop-ripple/` contains only
`testbench/`. The issue's premise that this campaign "reports frequency-shaped
figures … at ngspice's default tolerances" is therefore not yet true of any
committed evidence — there was no default-tolerance figure on file to compare
against, and nothing to supersede. Being empty is what made it the cheapest of
the four to fix.

It is `sim/pll-lock`'s DUT, cold start, window, lock criterion and (formerly)
grid, and `sim/tests/test_harness.py` pins that correspondence so the two
campaigns' lock columns stay comparable. It therefore takes the identical
change: `tran_step` 20 ps, `tran_max_step` 200 ps, `.options reltol=1e-4`,
`timeout_s` 172800. A campaign whose entire output is the *size* of a small
self-generated disturbance must not run at a tolerance that manufactures
disturbance of its own.

One consequence is recorded in the manifest rather than left to be discovered:
the finer grid **widens** the reported `v(VDD)` peak-to-peak, because less of
the ring's per-edge crowbar content is attenuated by the resampling. Both the
20 ps and the 200 ps figure bound DR-006's 100 kHz–100 MHz Budget 1 band from
above; 20 ps is the looser bound. Nobody should read the difference between a
future record and an informal 200 ps probe as a change in the circuit.

## Summary

| Campaign | Gated on a ratified row? | `n` at its own operating point | Measured/derived shift | Re-run needed? | Manifest changed? |
|---|---|---|---|---|---|
| `sim/vco` | no (rows 2, 5 both DRAFT) | 19–63 over its sweep | +0.03 % f at VCTRL 0.9 V, +1.35 % at 1.6 V, +1.96 % on the mean slope | **no** | no |
| `sim/vco-supply-pushing` | no (row 13 DRAFT) | 14–64 over its grid | ≤ +1.04 % f; `S_span` +0.2 %/V at the tightest triple, no class flip | **no** | no |
| `sim/pll-lock` | **yes** — row 9, 1.0 % RMS | ≈ 20 | 1.543 % RMS of pure simulator error = 1.5× the whole budget (derived from `integrator-floor`) | **yes — owed, not done** | yes |
| `sim/loop-ripple` | no (row 13 DRAFT) | ≈ 20 | no record exists to shift | n/a — nothing on file | yes (before first record) |

Two of four campaigns are cleared by measurement, and the two that are not are
the two whose `n` ≈ 20 puts them in `integrator-floor`'s own regime. The
audit's one-line answer: **ngspice's default tolerances bias this repo's
frequency figures by an amount set by how finely each campaign's grid resolves
its own output period, and only the two 200 ps closed-loop campaigns were
coarse enough for it to matter.**
