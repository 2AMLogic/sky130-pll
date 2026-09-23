# DR-006: ratify target-spec row 9 (period jitter); rows 10 and 13 stay DRAFT

- **Status**: proposed — ratified by the operator's PR approval (per the
  mechanism the operator set out on #19 and reused for `DR-002`/`DR-003`/
  `DR-004`/`DR-005`: "the operator's PR approval is the ratification act").
  This record is not marked `ratified` by its author; only the merge of the
  PR that ships it performs that act.
- **Date**: 2026-09-23
- **Author**: Builder agent (drafted per #151)
- **Ratifies against / input to**: #151 ("spec: ratify target-spec rows
  9/10/13 — #20 and #22 are blocked on this and nothing targets it"), and
  through it #20 (Monte Carlo / `klt yield` methodology, T1 item 6) and #22
  (aggregated characterization report, T1 item 8)
- **Supersedes**: none. This record extends the row-by-row ratification pass
  `DR-002` began (row 1 ratified, rows 2/3/4/6/7/8 left DRAFT with cited
  gaps) to the three statistical-shaped rows `DR-002` did not reach. It does
  not change any disposition `DR-001`, `DR-002`, `DR-003`, `DR-004` or
  `DR-005` made.

## Context

### What is asked, and by whom

`spec/target-spec.md`'s status header lists rows 0, 1, 19 and 20 as
RATIFIED. Rows **9** (period jitter), **10** (reference spur) and **13**
(supply sensitivity) — the three statistical-shaped rows — remain DRAFT, and
until #151 was filed no issue or PR targeted their ratification. Two T1
items are blocked behind that:

- **#20** (T1 item 6, Monte Carlo / yield methodology). Its harness
  deliverable already shipped (`sim/harness/montecarlo.py`, PR #33, `Part of
  #20`). Its second acceptance-criteria bullet needs a *binding* statistical
  row to grade a draw population against. `sim/README.md` says so in its own
  words: "`spec/target-spec.md`'s statistical-shaped rows (period jitter row
  9, reference spur row 10, supply sensitivity row 13) are DRAFT/unratified
  … an `--mc` record produced today … is a harness plumbing check, not a
  statistical-spec measurement."
- **#22** (T1 item 8, aggregated characterization report). Its aggregator
  shipped (`measurements/aggregate.py`, PR #32, `Part of #22`). Its second
  bullet needs at least one ratified row for an evidence record to cite.

#151's own scope statement is explicit that partial ratification is the
preferred outcome over a false one, and that a row staying DRAFT is a
legitimate outcome **provided it is a decision rather than a default**. This
record makes all three calls explicitly.

### The shape this record's dispositions turn on

Three facts about these rows, established below, drive every disposition
here:

1. **Row 9's bound is dimensionless; rows 10's and 13's are not.** Row 9 is
   stated as a *percentage of the output period*. That form carries no volts
   and no hertz, so it is the one part of gf180-pll's corresponding row that
   is unaffected by the 3.3 V → 1.8 V supply-flavor change `DR-001` ratified.
   Row 10's bound is in dBc *at a stated output frequency*, and row 13's two
   budgets are in millivolts and in volts-of-control-window — all three of
   which move with rows that are still DRAFT.
2. **gf180-pll's row 12 constrains a rail this design does not have.**
   gf180-pll writes its AC supply-ripple budget against a dedicated
   `vdd_vco` rail (its own rail table: "`vdd_vco` / `gnd_vco` — constant-gm
   bias, band mirrors, V→I converter, 5-stage ring, output buffer"). This
   repo's **row 1 is already ratified to the contrary**: "1.8 V ± 10 %
   (1.62 – 1.98 V), a single supply domain — no separate ring / PFD-CP /
   digital domain split," confirmed by inspection of
   `design/top/netlist/top.spice`. There is no `vdd_vco` here to write a
   limit against.
3. **Rows 10 and 13 are both downstream of row 5 (Kvco), which is DRAFT and
   which this design misses by a wide margin.** `design/vco/DESIGN.md`'s own
   update section states it plainly: the measured tuning slope is
   692 – 1751 MHz/V against a DRAFT row-5 bound of ≤ 150 MHz/V, and "it is
   not designed to already meet the ≤ 150 MHz/V DRAFT bound." Both a spur
   target in dBc and a DC control-window budget scale directly with that
   number.

### What evidence exists in this repo today, and what does not

Stated so that no disposition below can be mistaken for a value fitted to a
result already in hand — #151's own scope warns against exactly that
("writing the target to match what was measured is the same failure wearing
a different hat").

| Quantity these rows need | Status in this repo |
|---|---|
| Period jitter (any corner, any operating point) | **No measurement of any kind.** `sim/harness/measure.py` derives mean frequency, duty cycle and lock time; it has no period-jitter metric at all. No record under `sim/*/records/` reports a jitter number. |
| Reference spur (dBc) | **No measurement.** No spectral/sideband campaign exists. |
| VCO supply pushing (%/V) | **No measurement.** `sim/vco` characterizes frequency vs. `VCTRL`, not vs. `VDD`. |
| `VCTRL` ripple in lock | **No measurement.** `design/loop-filter/DESIGN.md` says so in its own row-13 headroom section: "`sim/loop-ac` is a small-signal AC campaign and measures nothing about ripple … A transient testbench still owes the verified number." |
| Charge-pump `UP`/`DN` charge asymmetry | **No measurement.** `design/pfd-cp/DESIGN.md`: "no DC operating-point simulation exists for this block." |
| Kvco | Measured, 692 – 1751 MHz/V over a 45-point PVT grid (`sim/vco/records/20260904-163130-f3ae976.md`, read via `design/loop-filter/DESIGN.md`'s design-point table). Row 5 itself is **not** ratified. |
| `Icp` | Design point 10 µA; measured 7.05 µA typical, 4.91 – 7.50 µA across PVT (`design/loop-filter/DESIGN.md`, issue #98 section) — i.e. ~30 % below the design point. Not a ratified value. |

The two measured quantities in that table are used **only** to demonstrate
that rows 10 and 13 are not ratifiable today. No value ratified by this
record is derived from any of them.

## Decision

**One row is ratified; two are left DRAFT, explicitly.**

### 1. Row 9 — Period jitter: RATIFY, with the supply condition re-derived rather than ported

**Ratified bound.** Period jitter at `CLK`, in lock:

> **≤ 1.0 % of the output period, RMS.**

**The quantity, stated unambiguously.** "Period jitter" here is the standard
deviation of the measured period `T_k` over a population of consecutive
output cycles taken after lock, divided by the mean period of that same
population, expressed as a percentage. The **percentage form is normative**;
any absolute picosecond figure (100 ps RMS at 100 MHz, 50 ps at 200 MHz) is
a derived restatement of it, never the spec'd quantity. This follows
gf180-pll's own resolution of exactly this ambiguity in its row 5, and is
stated here so the same 10× drafting inconsistency cannot recur in this
repo.

**The condition this bound is stated under.** gf180-pll makes its 1 % line
conditional on a `vdd_vco` ripple limit, and its spec says the line is not
ratifiable without one. That condition **is not ported**, because the rail
it names does not exist under this repo's ratified row 1 (see *Context* fact
2). In its place, this record binds row 9 to a condition that is both
well-defined and verifiable with what exists today:

> The bound holds with the supply modelled as an **ideal DC source at any
> point in row 1's ratified range** (1.62 / 1.80 / 1.98 V), with **no
> externally applied AC ripple**, over the full PVT grid rows 19 × 20 × 1
> define (`tt`/`ff`/`ss`/`sf`/`fs` × −40 / 27 / 125 °C × 1.62 / 1.80 /
> 1.98 V), and over a local-mismatch Monte Carlo population at the nominal
> point (`sim/run_corners.py <slug> --mc`).

This narrows the row's validity domain relative to gf180-pll's; it does not
loosen the number. The ripple-inclusive form of the row — a jitter target
that survives a stated rail disturbance — is **explicitly owed at row 13**
and is named in *Consequences* below as unfinished business, not quietly
dropped.

**Why 1.0 %, and why this is not a rubber stamp of the DRAFT value.** Three
independent reasons, in the order they carry weight:

- **It is the one clause in gf180-pll's row 5 that survives the supply
  change.** `DR-002` established the pattern this record follows: when
  porting from gf180-pll, separate the part of a row that carries a supply
  dependence from the part that does not, port only the latter, and say
  which is which. `DR-002` ported the **± 10 %** tolerance (dimensionless)
  while refusing the **3.3 V** it was attached to. The same cut applies
  here: "1.0 % of the output period" carries no volts, so it crosses the
  1.8 V boundary intact, while gf180-pll's "≤ 20 mV pp on `vdd_vco`" does
  not — and is refused below at row 13 for that reason. Porting the
  percentage while refusing the millivolts is the consistent application of
  the rule, not a convenient half-port.
- **It is a demanding target for *this* design, not a freebie.** A target
  worth ratifying must be capable of failing. With this ring's measured
  tuning slope, `Kvco / f_out` is 4.3 – 10.9 per volt (692 – 1751 MHz/V
  against `design/loop-filter/DESIGN.md`'s own `f_out` = 160 MHz design
  point), so **≈ 1 mV of ripple on `VCTRL` alone produces 0.4 – 1.1 %
  peak fractional frequency deviation** — at or beyond the whole budget
  before any device-noise or mismatch contribution is counted. Against
  that, `design/loop-filter/DESIGN.md`'s own design-time estimate of the
  single-pulse charge-pump excursion at the `CP` node is ≈ 52 mV
  (`Icp · R1` = 10 µA × 5.23 kΩ), attenuated by `C2`/`C3` before reaching
  `VCTRL` by a factor nobody has measured. Ratifying 1.0 % therefore
  creates real design pressure — in the direction row 5 (Kvco) already
  owes — rather than blessing a number the design cannot miss.
- **The alternative directions are both worse.** *Loosening* it to
  accommodate the 1.8 V rail's tighter headroom would be precisely the
  "relax the spec so results pass" move `CLAUDE.md` forbids, applied
  pre-emptively and without a single measurement to justify it. *Tightening*
  it has no evidentiary basis either. 1.0 % is retained on its merits, with
  the < 0.5 % figure kept as an **uncommitted stretch** (no evidence either
  way, not binding, not a second ratified number) exactly as gf180-pll keeps
  it.

**This ratifies a target, not a compliance claim.** No period-jitter
measurement exists in this repo (see *Context*). Following the precedent of
`2AMLogic/sky130-comparator`'s DR-002 — which ratified its kickback bound
while recording that the design missed it by ~29× — ratifying row 9 commits
this repo to the number; it asserts nothing about whether the present
schematic meets it. The first campaign to measure it may well record a miss,
and that miss is recorded as a miss.

### 2. Row 10 — Reference spur: stays DRAFT, explicitly

**Disposition: not ratified. The ≤ −55 dBc candidate stays a candidate**,
with the reason recorded here rather than left as a bare DRAFT marker.

**Reason 1 — the target has no binding frequency, because row 2 is DRAFT.**
A spur in dBc is a *ratio*, and for a given control-voltage disturbance it
scales as `20·log₁₀(f_out)` through `θ = 2π·f_out·TIE`. gf180-pll's own
experience shows this is not a rounding concern: its measured spur passes
−55 dBc at all five measured corners at 150 MHz and **fails at two of them
once scaled to its 200 MHz binding point** (−54.5 and −54.9 dBc), a
pass/fail flip caused by 2.5 dB of frequency scaling alone. Row 2 (output
band) is DRAFT and its sky130 band edges are explicitly owed a re-derivation
("a 130 nm ring on 1.8 V core may reach *higher* or trade range for Kvco").
Ratifying a dBc number before the frequency it binds at exists would be
ratifying an expression with a free variable in it.

**Reason 2 — porting −55 dBc would covertly ratify a Kvco requirement row 5
has never argued.** For a fixed `VCTRL` ripple waveform and a fixed `f_out`,
the spur's phase deviation scales linearly with `Kvco`; the fair
cross-design comparison is therefore the dimensionless-per-volt ratio
`Kvco / f_out`. gf180-pll's own supply-sensitivity derivation states its
figure directly: `Kvco/f_out` spans **0.31 … 0.84 per volt** across its bands
and corners. This design's measured 692 – 1751 MHz/V against its documented
160 MHz design point gives **4.3 … 10.9 per volt** — **5× to 35× higher,
i.e. 14 – 31 dB more spur for the same `VCTRL` ripple at the same output
frequency.** Part of that gap is structural and already-accepted: `DR-001`
ratified the 1.8 V core knowing it leaves "roughly a third of gf180-pll's
3.3 V control-voltage window," and covering a comparable fractional tuning
range across a ~2.2× narrower window *requires* a ~2.2× larger `Kvco/f_out`.
The remainder is this ring's own sizing, which is exactly what row 5 owes
and has not delivered. Ratifying −55 dBc today would smuggle a
one-to-1.5-orders-of-magnitude `Kvco` reduction into the spec as an
unstated precondition.

**Reason 3 — the mechanism the number would have to be derived from is
unmeasured, and this design's topology is structurally worse at it than the
one the ported number came from.** gf180-pll derives its −61 dBc prediction
from charge-pump per-event charge asymmetry against a measured `C2`. Here
the corresponding inputs do not exist: `design/pfd-cp/DESIGN.md` records
that "no DC operating-point simulation exists for this block," and the same
document states that its charge pump is deliberately **single-stage, not
cascoded**, precisely because of the 1.8 V rail's headroom — "it is not the
topology this design would choose under gf180-pll's 3.3 V rail" — with the
accepted cost named as "lower output impedance than a cascode would give,
meaning more `UP`/`DN` current mismatch as `CP` swings across `VCTRL`'s
range." The spur number cannot be ported from a design whose charge pump has
structurally better matching, and cannot be derived here because the
matching has not been measured. (`DR-003` reached the same conclusion from
the other direction, and ratified the `sf`/`fs` mixed-skew corners
specifically so that this mechanism would be exercised when it *is*
measured.)

**What would ratify row 10**, stated so this DRAFT is closeable rather than
open-ended:

1. Row 2 (output band) ratified, fixing the frequency the dBc figure binds
   at; and
2. Row 5 (Kvco) ratified, or a recorded decision that the current tuning
   slope stands; and
3. A sky130 charge-pump `UP`/`DN` charge-asymmetry measurement plus a
   `VCTRL`-ripple-in-lock measurement, from which a spur bound can be
   *derived* for this design — or a direct closed-loop sideband measurement
   — rather than ported.

### 3. Row 13 — Supply sensitivity: stays DRAFT, explicitly, both budgets

**Disposition: not ratified.** Row 13 carries two independent budgets in
gf180-pll's structure; they fail ratification for different reasons, so they
are disposed separately rather than as a block.

#### Budget 1 (AC) — a supply-ripple limit: **not ratifiable, because the constrained quantity does not exist here**

gf180-pll's budget is "`vdd_vco` ripple ≤ 20 mV pp, 100 kHz – 100 MHz" — a
contract a system integrator designs a **dedicated VCO rail** against.
**Row 1 of this spec is already ratified to the contrary**: a single supply
domain, no ring / PFD-CP / digital split, confirmed against
`design/top/netlist/top.spice`. There is no `vdd_vco` node in this design to
place a limit on. The nearest available quantity is ripple on the one shared
`VDD` — but on a shared rail the PLL's own divider and PFD switching
currents are themselves a ripple source, so a `VDD`-ripple limit is partly a
constraint the block imposes on *itself*, and whether any candidate number
is even self-consistent cannot be answered without a transient measurement
of the block's own self-generated rail disturbance. No such measurement
exists; `design/loop-filter/DESIGN.md` says so explicitly in its own row-13
section.

**What this record does record — the device/topology anchor a future
derivation starts from.** `DR-001`'s ratified *Consequences* already state
that "gf180-pll's ripple limit must be re-derived **smaller, not larger**"
on this rail. That statement has never been quantified. It can be, from
topology algebra and the ratified row-1 supply alone, with no measurement:

- A current-starved ring runs at `f ≈ I_stage / (n · C_stage · V_swing)`,
  and in a single-ended CMOS ring `V_swing` **is** the supply. So even a
  perfectly supply-independent starving current carries a `−1/VDD` term:
  the fractional-frequency pushing magnitude has a **structural floor of
  `1/VDD`** — **55.6 %/V at 1.8 V**, against **30.3 %/V at 3.3 V**. This
  design's ring is exactly that topology (`design/vco/DESIGN.md`:
  "single-ended current-starved," chosen over differential). **Per absolute
  volt of rail disturbance, this rail is structurally ≥ 1.83× more
  frequency-sensitive than gf180-pll's** — which is `DR-001`'s qualitative
  "smaller, not larger" made numeric for the first time.
- That floor bounds any future limit from above. For sinusoidal ripple of
  amplitude `A = Vpp/2` at a frequency above the loop bandwidth (where the
  loop does not correct it), the fractional period deviation is
  `S · A · sin(·)`, so its RMS is `S · Vpp / (2√2)`. Allocating half of the
  now-ratified row-9 budget (0.5 % RMS) to this deterministic mechanism —
  gf180-pll's own allocation convention, which leaves the other half for the
  unmeasured random contribution — and evaluating at the structural floor
  `S = 0.556/V` gives **Vpp ≤ 25.4 mV**. Realized pushing strictly exceeds
  the floor (gf180-pll measured 1.67× its own floor at the worst corner,
  and its measured ripple-jitter ran a further ~1.4× above this
  sinusoidal-FM algebra), so the eventual sky130 limit is **strictly below
  25 mV pp** and, if those two ratios carried over, would land near 10 mV
  pp. **Neither ratio is a sky130 measurement, which is why no number is
  ratified here** — a limit a system integrator must design a rail against
  should not rest on two borrowed correction factors.

#### Budget 2 (DC) — a rail-excursion `VCTRL` budget: **not ratifiable, because it is denominated in a window row 5 governs**

gf180-pll's budget is "a full-range rail excursion must consume ≤ 0.6 V of
the `VCTRL` window." Both the numerator and the denominator are unavailable
here:

- **Numerator.** The required `VCTRL` re-positioning is
  `(Δf/f) / (Kvco/f_out)`. Row 5 (Kvco) is DRAFT, and — unlike row 9's
  dimensionless bound — this budget's value moves by more than an order of
  magnitude across the gap between the measured slope and the DRAFT bound.
  At the measured 692 – 1751 MHz/V the required shift is tens of millivolts;
  at a ratified ≤ 150 MHz/V it would be hundreds. A budget that swings 10×
  on an unratified input is not a budget.
- **Denominator.** The usable `VCTRL` window is itself a VCO property
  (`design/vco/DESIGN.md`'s informal 0.8 – 1.6 V free-running span, and
  `design/pfd-cp/DESIGN.md`'s compliance range, which that document states
  is "a design-time qualitative note, not a verified operating-point claim"
  with no numeric `VOV` behind it). Ratifying a fraction-of-window budget
  before the window has a ratified or even measured value would be
  arithmetic on two unknowns.

**What this record does record**, from ratified inputs only: at the
structural `1/VDD` floor, a full-range row-1 excursion (1.62 → 1.98 V) moves
the open-loop frequency by **≥ 22 %** — and because row 1's tolerance is
*relative* (± 10 %), that fractional figure is the **same** as gf180-pll's,
even though the per-volt sensitivity is 1.83× worse. The 1.8 V rail's
penalty is concentrated in the **AC** budget (denominated in absolute
millivolts), not in the DC one (denominated in a relative excursion). That
distinction is not in `DR-001`'s prose and is recorded here so a future
ratification does not apply the 1.83× factor to the wrong budget.

**What would ratify row 13**:

1. **Budget 1**: a VCO supply-pushing campaign on sky130 (frequency vs.
   `VDD` at fixed `VCTRL`, across the ratified PVT grid) to replace the
   borrowed 1.67× ratio, **plus** a transient `VDD`/`VCTRL` ripple
   measurement of the assembled loop that quantifies the block's own
   self-generated rail disturbance — the measurement
   `design/loop-filter/DESIGN.md` already names as owed. Together these say
   whether a shared-rail ripple limit is a meaningful contract or whether
   row 1's single-domain decision needs revisiting first.
2. **Budget 2**: row 5 (Kvco) ratified, plus a measured usable `VCTRL`
   window (a charge-pump compliance-range DC measurement, which
   `design/pfd-cp/DESIGN.md` explicitly does not have).

## Alternatives considered

- **Ratify all three rows.** Rejected. Rows 10 and 13 each have a named,
  cited structural gap — a free frequency variable, an unratified `Kvco`, a
  rail that does not exist, an unmeasured control window. Ratifying them
  would produce bounds that cannot be evaluated and would silently commit
  the repo to preconditions (a much smaller `Kvco`; a dedicated VCO rail)
  that no record argues. #151's own scope prefers partial ratification over
  a false one, and `sky130-comparator`'s DR-002 is the precedent it cites:
  three rows ratified, two left open "explicitly, not silently."
- **Ratify none of the three.** Considered seriously, and rejected for row 9
  specifically. The argument for it is consistency ("no statistical row has
  a single measurement behind it in this repo, so ratify nothing"). But that
  conflates *ratifying a target* with *claiming compliance*. `DR-002` already
  ratified row 1 with no measurement behind it, on the strength of an
  argument about which part of a ported value survives a supply change —
  the identical argument that carries row 9's percentage form here. Leaving
  row 9 DRAFT would also leave #20 and #22 blocked for no evidentiary
  reason, since neither needs a *measured* row, only a *binding* one.
- **Ratify row 9 by porting gf180-pll's ripple condition verbatim (≤ 20 mV
  pp on the VCO supply), so the row keeps its original conditional shape.**
  Rejected on two independent grounds. It contradicts ratified row 1 (there
  is no VCO supply to apply it to). And `DR-001`'s ratified *Consequences*
  already commit this repo to re-deriving that limit **smaller**; porting
  20 mV unchanged would be a ratified record contradicting a ratified
  record.
- **Ratify row 9 with a ripple condition derived from the numbers in Budget
  1's discussion above (≈ 10 mV pp, or the ≤ 25 mV pp structural ceiling).**
  Rejected — this is the most tempting option in this record and the easiest
  to get wrong. The 25 mV ceiling is sound but useless as a contract (it is
  the value at a *floor* of sensitivity no real circuit sits at). The ~10 mV
  figure requires importing two gf180-pll measurement ratios (realized/floor
  pushing, and measured/algebraic ripple jitter) across a PDK and a supply
  change, which is exactly the "carried from gf180-pll … a candidate to be
  tested, not a commitment" pattern `target-spec.md`'s cardinal rule
  forbids. A ripple limit is a contract a system integrator designs a rail
  against; it must not rest on two borrowed correction factors. The
  arithmetic is recorded in full so the next pass starts from it rather than
  redoing it — recorded, not ratified.
- **Loosen row 9's 1.0 % to reflect the 1.8 V rail's tighter headroom before
  any measurement exists.** Rejected — pre-emptive relaxation, forbidden by
  `CLAUDE.md` and by `spec/README.md`'s own restatement of it, and with no
  evidence on either side it would be a guess in the one direction the rules
  name.
- **Tighten row 9 below 1.0 %, since the percentage form makes a tighter
  number "free" to write.** Rejected — no evidentiary or requirement-side
  basis. < 0.5 % is retained as an uncommitted stretch, matching
  gf180-pll's own treatment, and is explicitly **not** a second ratified
  bound.
- **Ratify row 13's Budget 2 alone (the DC budget), on the argument that the
  ± 10 % relative excursion makes the fractional frequency shift identical
  to gf180-pll's.** Rejected. The *frequency shift* ports; the *budget* does
  not, because the budget is denominated in `VCTRL` volts and therefore
  divides by `Kvco/f_out` (row 5, DRAFT, missed by 5 – 12×) and by the
  usable control window (unmeasured). The shared half of the derivation is
  recorded above so a future pass can reuse it.
- **Restate rows 10 and 13 as "not spec'd — derived-only,"** the disposition
  row 11 (integrated RMS jitter / phase noise) carries. Rejected — that is a
  deliberate permanent omission for a quantity this flow cannot substantiate
  at all, which is a different claim from "this row needs inputs that are
  not ratified yet." Both rows here are expected to become ratifiable once
  their named prerequisites land; marking them derived-only would
  mis-describe them and discard the closure conditions listed above.

## Consequences

**What this record settles:**

- **Row 9 becomes binding.** `spec/target-spec.md`'s status header moves to
  RATIFIED (rows 0, 1, 9, 19, 20). The PLL has, for the first time, a
  numeric *performance* target — rows 0/1/19/20 bind the verification
  environment; row 9 binds an output quality.
- **#20 is unblocked, and its Monte Carlo scope is now definable.** Row 9 is
  a statistical row in exactly the sense T1 item 6 means: its value is a
  standard deviation over a population, and mismatch-driven stage asymmetry
  makes that population corner-*and*-draw dependent. The grading procedure
  is now stated: the ratified PVT grid (rows 19 × 20 × 1) for the
  deterministic axis, and `sim/run_corners.py <slug> --mc` local-mismatch
  draws at the nominal point for the statistical axis.
- **#22 is unblocked** the moment one evidence record measuring row 9 adopts
  `measurements/README.md`'s `**Spec row(s)**:` citation convention (the
  separate gap #152 tracks). Until then `measurements/report.md` will render
  row 9 as "No evidence," which is the correct rendering.
- **Rows 10 and 13 are now DRAFT by decision, with dated closure
  conditions**, instead of DRAFT by omission with no owner. The
  "no open issue or PR targets their ratification" state #151 was filed
  against does not recur: each row's section names what must exist first.

**What this record costs, constrains, or hands forward:**

- **Row 9 is ratified under a narrower condition than gf180-pll's, and the
  gap is real.** A quiet-supply jitter target says nothing about behaviour
  under rail disturbance — which, on a single shared domain, is the case
  that matters most. This is the largest known weakness of this
  ratification, and it is row 13 Budget 1's job to close it. Nothing here
  should be read as evidence that the ripple case is fine.
- **The ratified condition is schematic-level by construction.** An ideal DC
  source has no rail impedance, so the block's own switching currents
  generate no rail disturbance in the modelled system. A post-layout or
  rail-network campaign may find the as-built shared rail violates the
  premise the bound is stated under. Flagged now rather than discovered
  later.
- **Row 9 re-arms the VCO topology question `design/vco/DESIGN.md` parked.**
  That document chose the single-ended current-starved ring over a
  differential one partly because "there is no numeric target yet that
  specifically demands differential's better noise rejection over
  single-ended's simplicity," and set its own escalation condition: "If a
  future PVT/jitter campaign shows single-ended's supply sensitivity is the
  binding constraint on row 9 … a differential ring is the natural
  escalation." That condition is now live and checkable. Ratifying row 9
  does **not** by itself force a redesign — the ratified condition is a
  quiet supply, and the supply-sensitivity half stays open at row 13 — but
  the premise the topology choice rested on has partly expired, and a future
  campaign that misses row 9 must weigh that escalation rather than treat
  the topology as settled.
- **Row 9 creates design pressure on row 5 (Kvco), which is DRAFT.** At
  `Kvco/f_out` = 4.3 – 10.9 per volt, roughly a millivolt of `VCTRL` ripple
  consumes the entire jitter budget. Row 9 does not ratify a `Kvco` bound —
  it has no standing to, and row 5 is not in this record's scope — but it
  does make the consequences of the present tuning slope quantitative for
  the first time.
- **No harness can measure the row this record ratifies, yet.**
  `sim/harness/measure.py` derives mean frequency, duty cycle and lock time;
  it has **no period-jitter metric**. Filed as **#158**. Filing it rather
  than writing it here is deliberate: #151 is scoped to the ratification
  step, and harness code is out of scope.
- **The row-13 evidence gap now has an owner too.** Filed as **#159**: the
  sky130 VCO supply-pushing measurement (frequency vs. `VDD` at fixed
  `VCTRL`) and the transient rail/control ripple measurement of the
  assembled loop that Budget 1 needs — the measurement
  `design/loop-filter/DESIGN.md` already names as owed and that no issue
  tracked before this record. The "no open issue or PR targets this" state
  #151 was filed against does not recur for either row.
- **Nothing in `sim/`, `design/` or `measurements/` is edited by this
  record.** No manifest is re-pointed, no evidence record is annotated, no
  design document is revised — those are the follow-ups' work. The two
  design documents whose premises this record touches
  (`design/vco/DESIGN.md`'s topology rationale, `design/loop-filter/
  DESIGN.md`'s row-13 first pass) are cited, not amended, per the repo's
  append-only conventions.
- **#20 and #22 are not edited by this PR.** Consistent with the convention
  `DR-002` and `DR-003` followed for tracker issues, a Curator pass updates
  those threads after this merges.

## Status notes

This record stays `proposed` until the PR that ships it merges. Per the
mechanism the operator set out on #19 and reused for `DR-002` through
`DR-005` — "the operator's PR approval is the ratification act" — there is
no separate operator-only ratification issue; #151 plus this PR is the
ratification mechanism, which is also the two-key path (#151's scope
bullet 2: Judge review plus Champion/operator merge) that issue asks for.

Review feedback that disagrees with any of the three dispositions —
including a judgement that row 9 should also stay DRAFT, or that one of rows
10/13 can be ratified on evidence this record did not weigh — is resolved as
PR review feedback on this record **before** merge, not by a post-merge
supersession. Nothing here is binding as this note is written.

`spec/target-spec.md` is edited in the same PR that ships this record, so
the table and this record cannot disagree: row 9's table cell and section
carry the ratified bound and its condition; rows 10 and 13 carry an explicit
"DRAFT by decision, see `DR-006`" note naming what would ratify them,
rather than a bare DRAFT marker.
