# DR-005: `sim/pll-lock` starts every point from a discharged loop filter

- **Status**: proposed — ratified by the operator's PR approval (per the
  mechanism the operator set out on #19 and reused for `DR-002`/`DR-003`/
  `DR-004`: "the operator's PR approval is the ratification act").
- **Date**: 2026-09-06
- **Author**: Builder agent (drafted per #98)
- **Ratifies against / input to**: #98 (closed-loop cold-start lock
  convergence), #103 (the full-grid re-run this record's defaults must be
  run against)
- **Supersedes**: none — this record *extends* `DR-004`'s cold-start
  initialization from the VCO ring to the loop filter. `DR-004`'s two
  decisions (the `v(ring0)=0` startup nudge, the 100 µs window) stand
  unchanged.

## Context

`DR-004` established that `sim/pll-lock`'s manifest needed an explicit
cold-start initial condition on the VCO ring, because a noiseless,
perfectly-matched SPICE ring can sit on a degenerate DC fixed point real
silicon never sits on. That record fixed **one** node's initial state
(`v(xxxtop.xxvco.ring0)=0`) and left every other node to whatever ngspice's
operating-point solver produces.

That turns out to be the larger half of the problem. `sim/harness/measure.py`
emits `tran <step> <stop>` **without** `uic` (see `build_control_block`), so
every point computes a transient operating point first and starts the
transient from it. For this closed loop that operating point is not a cold
start and is not even a stable answer:

- In DC the ring sits at its metastable all-stages-at-midrail equilibrium,
  so `CLK` is a static level, the divider's `FBCLK` never toggles, and the
  PFD's `UP`/`DN` outputs are static.
- The charge pump's output node therefore settles wherever the static
  `UP`/`DN` leakage balance puts it, with only the loop filter's (DC-open)
  capacitors attached.
- Where that lands is **corner-dependent and arbitrary** — it is a property
  of the solver's chosen operating point, not of the circuit's power-on
  behavior.

Measured directly (informal single-point ngspice probes against the
committed netlist snapshot `sim/pll-lock/netlist-snapshots/
20260905-193322-0f1934d.spice`, not a `sim/` evidence record — same
convention as `design/vco/DESIGN.md`'s own informal sanity-check table and
`PR #101`/`PR #109`'s diagnostics), the operating-point `VCTRL` this
campaign has been starting every transient from is:

| PVT point | operating-point `VCTRL` |
|---|---|
| `ff`/−40 °C/1.80 V | 1.9 µV |
| `ff`/27 °C/1.62 V | 180 µV |
| `ff`/125 °C/1.98 V | 16.8 mV |
| `tt`/27 °C/1.80 V | 12.3 µV |
| `tt`/−40 °C/1.62 V | 0.827 V |
| `tt`/−40 °C/1.80 V | 0.925 V |
| `ss`/−40 °C/1.62 V | 0.810 V |
| `ss`/−40 °C/1.80 V | 0.900 V |
| `ss`/27 °C/1.62 V | 1.327 V |
| `ss`/27 °C/1.98 V | 1.601 V |
| `sf`/−40 °C/1.80 V | 0.901 V |
| `sf`/125 °C/1.80 V | 1.790 V |
| `fs`/−40 °C/1.62 V | 0.957 V |
| `fs`/−40 °C/1.80 V | 1.086 V |
| `fs`/125 °C/1.80 V | 1.800 V |

The spread is the entire supply rail. Cross-referencing each of those
starting voltages against the **committed** open-loop VCO record
(`sim/vco/records/20260904-163130-f3ae976.md`, the same 45-point PVT grid)
explains essentially every verdict in the current committed closed-loop
baseline `sim/pll-lock/records/20260905-193322-0f1934d.md`:

| PVT point | op-point `VCTRL` | free-running `f` at that `VCTRL` (committed VCO record) | baseline record's verdict |
|---|---|---|---|
| `tt`/27 °C/1.80 V | 12.3 µV | below the swept range — ring off | no oscillation |
| `ff`/27 °C/1.62 V | 180 µV | below the swept range — ring off | no oscillation |
| `ff`/125 °C/1.98 V | 16.8 mV | below the swept range — ring off | no oscillation |
| `ss`/−40 °C/1.62 V | 0.810 V | 94 MHz | no lock, final-window 184.2 MHz |
| `tt`/−40 °C/1.62 V | 0.827 V | 149 MHz | no lock, final-window 266.5 MHz |
| `ss`/−40 °C/1.80 V | 0.900 V | 240 MHz | **locked** 248 MHz at 1.711 µs |
| `sf`/−40 °C/1.80 V | 0.901 V | 369 MHz | **locked** 244 MHz at 1.601 µs |
| `fs`/−40 °C/1.62 V | 0.957 V | 324 MHz | **locked** 245.4 MHz at 1.38 µs |
| `fs`/−40 °C/1.80 V | 1.086 V | 579 MHz | no lock, final-window 315.1 MHz |
| `ss`/27 °C/1.62 V | 1.327 V | 635 MHz | no lock, final-window 665.2 MHz |
| `ss`/27 °C/1.98 V | 1.601 V | 1083 MHz | no lock, final-window 1.123 GHz |
| `sf`/125 °C/1.80 V | 1.790 V | 1053 MHz | no lock, final-window 1.003 GHz |
| `fs`/125 °C/1.80 V | 1.800 V | 1000 MHz | no lock, final-window 939.1 MHz |

Three things follow, and none of them are about the PLL's design:

1. **Every "no oscillation" verdict is a point whose operating point put
   `VCTRL` at ~0 V** — a genuine cold start, but paired with `DR-004`'s
   then-3 µs window. The cold-start charge-pump ramp is separately measured
   at 22–34 mV/µs (see `design/top/DESIGN.md`'s cold-start settling-time
   analysis), so 3 µs of transient moves `VCTRL` by under 0.1 V, an order of
   magnitude short of the ~0.6 V where this ring begins to free-run at all.
   Those points could not have oscillated for reasons that have nothing to
   do with device symmetry.
2. **Every high free-running "no lock" verdict is a point whose operating
   point put `VCTRL` far above the lock point**, and the reported
   final-window frequency matches, to within a few percent, the frequency
   the committed open-loop VCO record says the ring free-runs at *at that
   very control voltage*. The loop was initialized past the divider's
   measured 800 MHz clean ceiling (`design/divider/DESIGN.md`, #109) with
   its feedback path already dead.
3. **All three "locks" are points whose operating point placed `VCTRL`
   within the loop's pull-in range of that corner's own 250 MHz control
   voltage** — i.e. the loop was initialized approximately locked. Their
   reported 1.38–1.71 µs "time-to-lock" is the lock detector's own
   settle-plus-hold latency, not an acquisition transient. They are not
   evidence that this PLL acquires lock from a cold start.

This also explains the pattern issue #98 flagged as suspicious — that the
set of "locking" corners changed almost completely between two records
rather than growing outward. It is not the loop's cold-start trajectory that
is fragile to small parameter shifts; it is the DC operating-point solution,
which has no physical meaning here and which a loop-filter re-size (or, as
measured, merely adding `DR-004`'s ring nudge — which moves `fs`/125 °C/
1.80 V's starting `VCTRL` from 1.800 V to 4.7 mV) can move anywhere on the
rail.

## Decision

Add the loop filter's three storage nodes to `sim/pll-lock/testbench/
tb.json`'s `measure.ic`, so every PVT point's transient begins from a
discharged loop filter — the physical power-on state:

```json
"ic": [
  "v(xxxtop.xxvco.ring0)=0",
  "v(xxxtop.vctrl)=0",
  "v(xxxtop.cp)=0",
  "v(xxxtop.xxlf.z1)=0"
]
```

All three nodes are needed, not just `VCTRL`: `design/loop-filter/
loop_filter.sch` stores charge on `C1` (across its internal node `Z1`),
on `C2` (at `CP`) and on `C3` (at `VCTRL`). Initializing only the output
node would leave `C1` — the dominant 207.6 pF capacitor — holding an
arbitrary charge, which is the same defect with a smaller coefficient.

Verified directly: with these cards in place the transient operating point's
t = 0 `VCTRL` is exactly 0.000 V at every probed corner (`sf`/125 °C/1.80 V,
`fs`/125 °C/1.80 V, `ss`/27 °C/1.98 V, `ss`/−40 °C/1.80 V, `sf`/−40 °C/
1.80 V, `fs`/−40 °C/1.62 V) — the same six corners that previously started
anywhere from 0.900 V to 1.800 V.

This is a measurement-methodology change only. It does **not** ratify
`spec/target-spec.md` row 8 (still DRAFT), and it changes no design file.

## Alternatives considered

- **Set `measure.uic: true` instead** (`sim/vco/testbench/tb.json`'s own
  convention for the open-loop VCO campaign). Rejected for this manifest:
  `uic` skips the operating-point solve entirely and starts every node not
  named in an `.ic` card at 0 V. For the open-loop VCO that is harmless —
  the DUT is one ring plus a DC supply. For the closed loop it would also
  zero the `sky130_fd_sc_hd` divider's internal nodes and the PFD's latch
  nodes, discarding the consistent bias solution the rest of the circuit
  needs, and would make the digital blocks' first microsecond a
  simulation-startup artifact layered on top of the acquisition transient
  this campaign is trying to measure. `.ic` without `uic` gets the property
  actually wanted — the loop filter starts discharged, everything else
  starts from a consistent DC solution given that.
- **Initialize `VCTRL` only.** Rejected: `C1` (207.6 pF, 20x `C2` and 64x
  `C3`) holds its charge on the internal node `Z1`, so the dominant energy
  store would still start arbitrarily charged.
- **Accept the operating point as "a" cold start** and treat the resulting
  numbers as evidence. Rejected: it is not a physical power-on state (a
  fabricated part powers up with its filter capacitors discharged, not with
  them pre-charged to a solver-chosen voltage), and it is not even a
  consistent one — the table above shows it varying across the entire supply
  rail as a function of PVT corner, and shifting when an unrelated node's
  `.ic` card is added.
- **Add an explicit initial-condition device to `design/loop-filter/
  loop_filter.sch`** (e.g. a reset switch across `C1`). Rejected for this
  record: that is a design change — arguably a good one for a real product,
  and a legitimate candidate for a future issue — but it would put a
  simulation-driven artifact into the committed design netlist to fix what
  is squarely a testbench initialization defect. A power-on-reset path for
  the analog loop should be argued on its own merits, not adopted as a
  measurement workaround.
- **Do nothing until the redesign work in #98 concludes.** Rejected:
  #103's full 45-point re-run is already queued against these defaults, and
  running a multi-hour campaign against an initialization that demonstrably
  measures the operating-point solver instead of the PLL would waste it and
  produce a fourth record that cannot be interpreted.

## Consequences

**What this fixes.** `sim/pll-lock` will, for the first time, measure what
its own claim string says it measures: acquisition from a power-on cold
start. The next full-grid record's per-point verdicts become comparable to
each other (every point starts from the same physical state) and to
`spec/target-spec.md` row 8's DRAFT lock-time budget.

**What this invalidates.** Every committed `sim/pll-lock` record to date —
`20260819-122135-fe0e6df.md`, `20260904-163254-f00ce3e.md`,
`20260904-165409-f3ae976.md`, `20260905-193322-0f1934d.md` — was produced
under the defective initialization described above. Per `CLAUDE.md`'s
append-only rule they are **not** edited or deleted, and this record does
not supersede them (a manifest-default change is not a new PVT-grid result);
but their per-point verdicts must not be read as cold-start lock evidence,
and in particular **the three "locks" in `20260905-193322-0f1934d.md` are
not evidence that this PLL acquires lock**. The 1-of-45 and 3-of-45 lock
counts that issue #98 and `docs/chipalooza/challenge-4-proposal.md` § 6 both
cite should be read as artifacts of the operating-point solver until #103's
re-run against these defaults lands.

**What this costs.** From a true cold start, every point must ramp `VCTRL`
from 0 V to its own ~0.85–0.93 V lock voltage at the charge pump's measured
4.9–7.5 µA into the filter's 221 pF, i.e. 26–41 µs of acquisition ramp
before the lock criterion can possibly be satisfied. Points that previously
started near the lock point and "locked" in 1.4 µs will now run the full
window. `DR-004`'s 100 µs window and 10800 s timeout are therefore
*necessary*, not generous — and the per-point wall-clock cost of #103's
re-run should be budgeted at the pessimistic end of `design/top/DESIGN.md`'s
measured estimate.

**What this does not fix.** The genuine design question #98 exists for is
untouched: whether the loop captures during the acquisition ramp before
`VCTRL` transits into the band where the VCO free-runs above the divider's
measured ~800 MHz ceiling and the feedback path dies. The capture-margin
analysis in `design/top/DESIGN.md` shows that window is as narrow as 0.222 V
of `VCTRL` (6.5 µs of ramp) at `ff`/−40 °C/1.98 V. This record makes that
question measurable; it does not answer it.

## Status notes

Stays `proposed` until the PR that ships it merges, per the `DR-002`/
`DR-003`/`DR-004` precedent. The concrete next step it hands off is **#103**
— a fresh full 45-point `sim/pll-lock` re-run against these defaults, naming
`20260905-193322-0f1934d.md` as the record it supersedes. That re-run, not
this record, is what a future `Icp`/loop-filter/VCO-bias redesign argued
under #98 must be argued against.
