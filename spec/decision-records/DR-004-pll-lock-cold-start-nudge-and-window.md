# DR-004: `sim/pll-lock` cold-start startup nudge and widened lock-time window

- **Status**: proposed — ratified by the operator's PR approval (per the
  mechanism the operator set out on #19 and reused for `DR-002`/`DR-003`:
  "the operator's PR approval is the ratification act").
- **Date**: 2026-09-06
- **Author**: Builder agent (drafted per #98, item 1 of #100's suggested
  scope)
- **Ratifies against / input to**: #98 (closed-loop cold-start lock
  convergence), #100 (harness-defaults follow-up this record implements)
- **Supersedes**: none

## Context

`sim/pll-lock/records/20260905-193322-0f1934d.md` — the current committed
full-45-point baseline against `design/top/top.sch` at or after #95's
loop-filter re-size — shows 42 of 45 ratified PVT points failing to lock,
split between two dominant modes: **"no oscillation"** (0 rising edges
observed at `CLK`) at most corners, and **"no lock within window"** (the
loop free-runs far from 250 MHz and never satisfies the lock criterion) at
several others. The manifest that produced it,
`sim/pll-lock/testbench/tb.json`, has two properties relevant here: its
`measure.tran_stop` is `3u`, more than 30x shorter than
`spec/target-spec.md` row 8's own DRAFT `< 100 µs` lock-time budget; and it
injects no cold-start perturbation at all — every device in
`design/vco/vco_ring5.sch`'s 5-stage ring starts from an identical (SPICE
model-typical) state.

Issue #98 asked, before any `Icp`/loop-filter/VCO-bias redesign is
attempted, whether these failures are a real cold-start convergence defect,
a `tran_stop` measurement-window artifact, or both. Two narrow, informal,
uncommitted single-point diagnostics run against this question (not `sim/`
evidence records — see `design/top/DESIGN.md`'s "Known gap: closed-loop
cold-start convergence (issue #98)" section for the full writeup, landed via
PR #101) found:

1. At `tt`/27 °C/1.80 V, re-running the exact committed manifest reproduces
   "no oscillation" in ~2 minutes of wall time — a fast, clean convergence
   to a non-oscillating DC fixed point, not a slow simulation that might
   resolve given more time. This is consistent with SPICE's
   exact-device-symmetry idealization: an odd-stage ring oscillator built
   from perfectly identical devices, with no explicit asymmetry and no
   noise source, can settle at (and never depart from) a degenerate fixed
   point that real, mismatched, noisy silicon would not sit at indefinitely
   on every power-up.
2. Forcing `sim/harness/measure.py`'s already-supported `measure.ic` field
   with `v(xxxtop.xxvco.ring0)=0` (the same node/nudge shape
   `sim/vco/testbench/tb.json` already uses for the open-loop VCO
   characterization campaign) breaks that degeneracy: the VCO free-runs
   immediately from the start of the transient in every diagnostic run
   against it.
3. At `tt`/125 °C/1.80 V, nudged + `tran_stop` widened to `30u`: locks at
   26.32 µs (251.5 MHz, 50.1% duty) — inside row 8's DRAFT budget. This
   corner's baseline "no oscillation" verdict was fully explained by (1)
   plus the 3 µs window being too short to see the eventual lock; no design
   change was needed for it.
4. At `tt`/27 °C/1.80 V, nudged + a direct 5 µs transient: a different,
   un-window-fixable failure — the VCO free-runs near the top of its own
   tuning range and the divider's `FBCLK` output stops toggling after its
   first post-reset pulse, breaking the loop's only feedback path. No
   amount of additional simulated time fixes this corner as currently
   designed (tracked separately as #100 item 3, the `divider_intN` `FBCLK`
   dropout root-cause).

Point 4 matters for this record's scope: the nudge does not manufacture
locks that would not otherwise happen — it can also expose a corner that,
once actually oscillating, still fails to lock for an unrelated, real
reason. That is the intended behavior of a fair test, not a risk this
record needs to guard against.

## Decision

Adopt, as `sim/pll-lock/testbench/tb.json`'s **permanent manifest
defaults** (not a one-off diagnostic overridden per-run):

1. **`measure.ic`**: `["v(xxxtop.xxvco.ring0)=0"]` — force the VCO ring's
   first stage low at `t=0` for every corner, breaking the SPICE
   exact-symmetry degeneracy identified above. This is representative of
   real silicon precisely *because* real devices are never perfectly
   matched and are never noise-free — every real power-up of this ring
   sees some asymmetry breaking the same idealized fixed point that a
   noiseless, mismatch-free SPICE model can sit on indefinitely. The nudge
   does not force a lock, or force oscillation at any particular frequency
   — it only removes an idealization the real circuit does not have, and
   points 3/4 above show it can just as easily unmask a genuine failure (a
   dead feedback path) as an artifact (a too-short window).
2. **`measure.tran_stop`**: `3u` → `100u`, matching `spec/target-spec.md`
   row 8's own DRAFT `< 100 µs` candidate lock-time budget, rather than an
   arbitrarily chosen multiple. A manifest whose window is 30x shorter than
   the very budget it is meant to test that budget against cannot
   distinguish "this corner is too slow" from "this corner would lock, just
   not within an unrelated 3 µs cutoff."
3. **`measure.timeout_s`**: `1800` → `10800` (3 hours), to accommodate the
   larger per-point wall-clock cost a 33x-wider transient window requires —
   the 30 µs diagnostic in point 3 above already took 25–40 minutes of wall
   time per point at the same `200p` step size; three of the 45 points in
   the existing baseline record already hit the prior 1800 s timeout at the
   much shorter 3 µs window.

This is a measurement-methodology change only. It does **not** ratify
`spec/target-spec.md` row 8 (which stays DRAFT — 100 µs is used here only
because it is the number row 8 already carries as a candidate, giving the
manifest something concrete to test against) and does **not** change
`design/top/top.sch`, `design/loop-filter/*`, or `design/vco/*`.

## Alternatives considered

- **Leave the manifest unperturbed and treat every "no oscillation" verdict
  as a confirmed real design defect.** Rejected — the diagnostic evidence
  above shows at least one such verdict is a SPICE-exact-symmetry
  idealization with no real-silicon analog, not a defect that would
  manifest on fabricated devices. Treating it as real would send a future
  VCO-bias redesign chasing a problem that does not actually exist in
  silicon.
- **Continue running ad hoc, per-corner informal diagnostics (as PR #101
  did) instead of changing the committed defaults.** Rejected as the
  permanent methodology — appropriate for a two-corner scouting pass, but
  this repo's evidence convention (`CLAUDE.md`: "no claim without a
  testbench," append-only `sim/` records) calls for a repeatable,
  defaults-driven grid re-run, not hand-tuned per-point settings decided
  case by case.
- **A smaller, non-zero perturbation** (e.g. a tiny voltage offset on one
  stage, or explicit device-size asymmetry) instead of a hard
  `v(ring0)=0` initial condition. Deferred, not rejected — `v(ring0)=0` is
  already the precedent `sim/vco/testbench/tb.json` established for this
  repo's open-loop VCO characterization campaign; reusing it keeps the
  closed-loop nudge consistent with the existing open-loop one instead of
  introducing a second, unexplained perturbation convention. A
  smaller-magnitude nudge might be a closer proxy for real mismatch
  magnitude, but no measured mismatch/noise model for this PDK's ring
  stages backs a specific epsilon value, and the binary "does it start"
  question this campaign needs answered does not depend on getting that
  magnitude right.
- **Full Monte Carlo (`mc_mm_switch`) mismatch+noise sampling** in place of
  a fixed `.ic` nudge. Deferred — more rigorous as a stand-in for "real
  silicon breaks the ring's degeneracy," but layering MC trials on top of
  all 45 PVT points multiplies an already multi-hour campaign, and
  `sim/harness/cli.py --mc`'s trial-matrix support is not designed to
  combine with a full PVT sweep in one manifest today. Revisit if this
  fixed-nudge campaign's results are disputed as insufficiently
  representative.
- **Widen `tran_stop` only, without the nudge.** Rejected — a wider window
  cannot start an oscillation that never departs from a symmetric DC fixed
  point; it would leave every "no oscillation" corner unexplained.
- **Add the nudge only, without widening `tran_stop`.** Rejected — point 3
  above (`tt`/125 °C/1.80 V) already shows a real lock time (26.32 µs) past
  the current 3 µs window regardless of the nudge; keeping the short window
  would still misreport that class of corner as "no lock within window" for
  a reason unrelated to startup symmetry.
- **Pick a `tran_stop` wider than row 8's own budget** (e.g. 200 µs or
  500 µs) for extra margin. Rejected for now — 100 µs already sits at
  >3.5x the one confirmed real lock time observed so far (26.32 µs) and
  matches row 8's own stated candidate number without needing to be padded
  to be a fair test of it; a materially longer window mainly multiplies the
  per-point wall-clock cost of the next full-grid re-run (#100 item 2)
  without a stated justification for the extra margin. If that re-run's own
  results show points locking just past 100 µs, that is itself evidence to
  argue a wider window in a follow-up record, not something to pre-guess
  here.

## Consequences

**What this fixes:** `sim/pll-lock`'s default manifest can now distinguish,
for most corners, "would lock given a fair, silicon-representative chance
at cold start" from "genuinely does not start or does not lock" — instead
of conflating both into a single "no oscillation" / "no lock within window"
bucket the way `20260905-193322-0f1934d.md` does today.

**What this does not fix:** the `divider_intN` `FBCLK` dropout PR #101
found once a nudged VCO free-runs well above 250 MHz (#100 item 3) is a
real defect this record does not paper over — the nudge starts the
oscillation; it does not repair the feedback path. A corner where the
nudge produces a clean start but the loop still runs away will correctly
continue to report "no lock within window" under these new defaults, not a
false pass. This record makes no design change to `design/top/top.sch`,
`design/loop-filter/*`, or `design/vco/*`.

**What this costs:** every future `sim/pll-lock` run is substantially
slower per point — the 30 µs diagnostic already took 25–40 minutes per
point at the same step size, so a 100 µs window is expected to cost
correspondingly more; `timeout_s` is raised to `10800` s to accommodate it.
A fresh full 45-point re-run against these new defaults is **deliberately
not run in this record** — that is `#100`'s item 2, a separate, multi-hour
campaign this record's diagnostics do not attempt to substitute for. Until
that re-run lands, `20260905-193322-0f1934d.md` remains the most recent
committed `sim/pll-lock` evidence and is **not** superseded by this record
(a manifest-default change is not itself a new PVT-grid result).

**What this does not ratify:** `spec/target-spec.md` row 8 stays DRAFT.
100 µs is used here only because it is the number row 8 already carries as
a candidate budget, giving this manifest something concrete to test
against — a future ratification of row 8 (or a decision that the two
constraints trade off unavoidably, per #98's own acceptance criteria) is a
separate act this record does not perform.

## Status notes

This record stays `proposed` until the PR that ships it merges, per the
`DR-002`/`DR-003` precedent (the operator's PR approval is the ratification
act; there is no separate operator-only ratification issue). The next
concrete step this record hands off is `#100`'s item 2 (a fresh full
45-point `sim/pll-lock` re-run against the defaults this record sets,
naming `20260905-193322-0f1934d.md` as the record it supersedes) and item 3
(root-causing the `divider_intN` `FBCLK` dropout), neither of which this
record itself performs.
