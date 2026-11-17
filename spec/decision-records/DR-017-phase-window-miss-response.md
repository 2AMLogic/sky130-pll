# DR-017: phase-window band miss — no tap count of the measured delay chains fits; proposed response

- **Status**: proposed. This record ratifies nothing: DR-007 stays `proposed`,
  spec row 16 stays DRAFT, and every band value below is unchanged. See
  "Status notes" for what ratifies it.
- **Date**: 2026-11-15
- **Author**: Builder agent (issue #438)
- **Ratifies against / input to**: responds to the measured phase-window miss
  of #275 (`sim/lockdet-timing/phase/README.md`); input to #260 (standalone
  LOCK circuit), #261 and #231
- **Supersedes**: none

## Context

DR-007's Table 2 bands the hardware phase windows: `W_acq` 1.5–4.0 ns and
`W_rel` 4.5–10.0 ns, with the strict invariants `W_acq,max < W_rel,min` and
`W_rel,max < 12 ns` (`sim/harness/locktiming.py` lines 36–40; DR-007 Table 2,
lines 112–122). The 45-point PVT characterization of the two delay-chain
candidates (#275) is complete — four records, one per candidate × edge
polarity, each 45/45 `OK` — and **no candidate meets the bands**. Every
extreme sits at the same corners (fastest ff/−40 °C/1.98 V, slowest
ss/−40 °C/1.62 V), and the spread is dominated by process and supply (about
2.4×), not temperature.

Because the phase products miss their bands, `handoff_ready` is false and the
lock-detector line (#260, #261, #231; spec row 16, still DRAFT) is blocked:
`design/lock-detector/DESIGN.md` (Verdict) records that #260 stays blocked
"pending a separately argued superseding decision record". This record is
that argument. It tabulates the committed measurements, shows the miss is
structural rather than a wrong tap count, weighs the response options, and
recommends one — without running anything (no new simulation; every figure
below is lifted from committed records, cited by record id).

### Measured envelope (all four 45/45 records)

From the `### Full PVT grid` table of `sim/lockdet-timing/phase/README.md`.
Per-stage values are the committed chain totals divided by the stage counts of
the same README's Candidates table (`s50`: 7 acquisition / 18 release stages
of `sky130_fd_sc_hd__clkdlybuf4s50_1`; `s25`: 14 / 39 stages of
`sky130_fd_sc_hd__clkdlybuf4s25_1`); the cells in each chain are identical, so
the division is the committed average stage delay, tap load included.

| record | candidate · polarity | `W_acq` measured (ns) | `W_rel` measured (ns) | per-stage acq (ns) | per-stage rel (ns) |
|---|---|---|---|---|---|
| `lt-20261012-215440-502985` | `s50` rising | 1.885 – 4.584 | 4.745 – 11.573 | 0.269 – 0.655 | 0.264 – 0.643 |
| `lt-20261012-215409-824834` | `s50` falling | 1.583 – 3.633 | 4.001 – 9.205 | 0.226 – 0.519 | 0.222 – 0.511 |
| `lt-20261012-220148-142698` | `s25` rising | 1.748 – 4.064 | 4.748 – 11.064 | 0.125 – 0.290 | 0.122 – 0.284 |
| `lt-20261012-220219-074618` | `s25` falling | 1.677 – 3.776 | 4.591 – 10.376 | 0.120 – 0.270 | 0.118 – 0.266 |

Both Table 2 invariants pass in all four records (the reducer's cross-window
checks): max(`W_acq`) < min(`W_rel`) strict, and max(`W_rel`) < 12 ns strict.
The misses are band misses only. The overall per-stage spread across PVT is
2.46× for the `s25` cell (0.118–0.290 ns) and 2.95× for the `s50` cell
(0.222–0.655 ns).

### Band-fit arithmetic

A chain of k identical stages realizes `W = k · d`, where `d` is the
per-stage delay spanning `[d_min, d_max]` over the grid. The band `[L, U]`
contains the whole envelope iff `k ≥ L/d_min` and `k ≤ U/d_max`; an integer k
exists iff `d_max/d_min ≤ U/L`, i.e. the band's own ratio must be at least
the per-stage PVT spread ratio.

The release band's ratio is 10.0/4.5 = **2.222**. The measured release
per-stage spread ratio is 2.44 (`s50` rising), 2.30 (`s50` falling), 2.33
(`s25` rising) and 2.26 (`s25` falling) — **larger than 2.222 in every
polarity**. The integer windows are empty:

| candidate · polarity | release: k must satisfy | result | acquisition: k must satisfy | result |
|---|---|---|---|---|
| `s50` rising | k ≥ 18 and k ≤ 15 | no k | k = 6 | k = 6 would fit |
| `s50` falling | k ≥ 21 and k ≤ 19 | no k | k = 7 | k = 7 fits (the built chain) |
| `s25` rising | k ≥ 37 and k ≤ 35 | no k | k = 13 | k = 13 would fit |
| `s25` falling | k ≥ 39 and k ≤ 37 | no k | k = 13 or 14 | k = 13–14 would fit |

**No stage count of the existing `clkdlybuf4s50_1` / `clkdlybuf4s25_1` chains
fits both bands across the whole grid.** The release band alone is
unreachable at any tap count, in either polarity: scaling the tap count
scales the whole envelope, so it cannot narrow a spread ratio that already
exceeds the band ratio. The acquisition band (ratio 4.0/1.5 = 2.667) is wide
enough and could be re-centered by a shorter chain — which is exactly why the
release band, not the acquisition band, is the structural blocker. This is a
fully measured miss: the crossing extremes all sit at ff and ss corners of
the same 45-point grid.

## Decision

**Proposed, not ratified:** the response to the phase-window miss is to
abandon absolute delay chains as the window realization and direct the
follow-up design (#260/#231) at a **PVT-tracking window**: a structure whose
window width is set by a ratio or difference of matched standard-cell delays,
so process and supply variation cancels first-order instead of appearing as a
2.3–2.4× envelope spread. The DR-007 contract (Tables 1 and 2, the bands, the
invariants) is unchanged by this record; the realization inside it changes.
No tap is selected from #275's candidates, and none can be — the arithmetic
above closes that door on committed evidence. Until a tracking structure (or
an alternative below) passes its own 45-point grid, #260/#261 stay blocked
and row 16 stays DRAFT. A cheaper variant of the same requirement — swapping
in a different fixed delay primitive — is acceptable only if a cell is first
shown to spread less than 2.222× over this exact grid, which committed
evidence today does not provide for any measured cell.

## Alternatives considered

### A. A different fixed delay primitive (swap the cell, keep the chain)

Replace `clkdlybuf4s50_1`/`clkdlybuf4s25_1` with another standard cell whose
per-stage PVT spread ratio is below 2.222 over the same grid.

- **Cost**: no committed evidence shows such a cell. Measured spreads over
  this grid: `clkdlybuf4s50_1` 2.95×, `clkdlybuf4s25_1` 2.46×, and the
  `buf_1` watchdog ring 2.30× (tick 161.4–371.2 ns, 45/45 record
  `lt-20261105-202135-163927`) — every standard-cell delay measured in this
  repository so far spreads ≥ 2.26×. `dlygate4sd3_1` is additionally **not
  simulable at ss** with this PDK pin (BSIM4 model abort; the watchdog
  predecessor was rejected for it, `design/lock-detector/DESIGN.md` §
  "Rejected predecessor"). Finding a candidate means characterizing further
  cells with the full campaign before any LOCK design starts, and it may find
  nothing: the library may simply not contain a cell this flat.
- **Invariant re-check**: unchanged bands mean the invariants are unchanged —
  `W_acq,max ≤ 4.0 < 4.5 ≤ W_rel,min` and `W_rel,max ≤ 10.0 < 12 ns` hold by
  construction for any primitive that meets both bands. The invariants
  themselves never bound this swap (they already pass in all four records);
  the release *band* is what no cell demonstrably fits.

### B. A PVT-tracking window realization (recommended)

Set the window width from a ratio or difference of matched delays rather than
one absolute chain delay, so the dominant process/supply variation cancels;
stay all standard-cell (DR-007's architecture constraint).

- **Cost**: a new realization — new schematics, generator and decks, more
  cells than a plain chain, and design work this record explicitly does not
  do. It must also validate, in the assembled circuit (#260), the assumptions
  the phase campaign declared but never validated: chain delay = window
  half-width, and flop setup/hold and clock-to-Q offsets cancelling between
  the compared arms, at the declared 10 fF / 100 ps load and slew.
- **Invariant re-check**: bands unchanged, so both invariants still apply to
  the realized windows: `W_acq,max < W_rel,min` strict and `W_rel,max < 12 ns`
  strict. Tracking helps rather than hurts — the two windows co-vary with PVT
  instead of spanning independently, so if they are sized correctly at
  nominal (e.g. 2.5 and 6.0 ns, DR-007 Table 1) their envelopes shrink toward
  the nominal values and both invariants gain margin. The record nevertheless
  requires the same 45-point evidence of the realized windows before #260
  unblocks (see "Consequences").

### C. Superseding band values (re-center or widen Table 2)

Rewrite the bands to cover a measured envelope, e.g. `W_rel` [4.7, 11.1] ns
for `s25` rising.

- **Cost**: the bands protect derived contract needs, not preferences.
  `W_rel,max < 12 ns` is the hard ceiling 0.3 × `T_ref,min` (25 MHz, 30 %
  duty; DR-007 §2) that keeps a jittering `FBCLK` edge inside the pairing
  interval `I_k` — and the measured envelopes reach 11.573 ns, under 4 %
  from it. Accepting `s50` falling's floor (4.001 ns) would drop `W_rel,min`
  to ≈4.0 and collide with the `W_acq` ceiling head-on (invariant becomes
  4.0 < 4.0 — false) unless `W_acq`'s band were narrowed in the same stroke.
  Worse, the contract's purpose — hysteresis sized to the loop's actual
  locked jitter and static offset — is unmeasured (#231 owns that
  measurement), so there is no evidence the wider window is safe *for its
  purpose*; the edit would launder a measured miss into the spec without a
  use-case argument. It would also require a superseding DR ratified by an
  operator. **Not recommended now**; revisit only with #231's measured
  jitter/offset in hand and margins argued on their own merits.
- **Invariant re-check**: numerically satisfiable per polarity, with the
  margins collapsing. Least-bad case `s25` rising: bands [1.7, 4.1] and
  [4.7, 11.1] keep `W_acq,max < W_rel,min` by 0.6 ns and `W_rel,max < 12 ns`
  by 0.9 ns. `s50` rising: [1.8, 4.6] and [4.75, 11.6] keep them by ≈0.1 ns
  and ≈0.4 ns. `s50` falling cannot be accepted at all without also moving
  the `W_acq` band (invariant collision above). The invariants survive only
  by evaporating the margins they exist to provide.

### Confirming measurement (named, not run)

For the recommended alternative B: a 45-point phase-window campaign on the
tracking structure, executed exactly as #275's was — generate the
structure's chains, run the complete tt/ff/ss/fs/sf × −40/27/125 °C ×
1.62/1.8/1.98 V grid in both edge polarities through the batch backend, and
reduce with `sim/harness/locktiming.py`'s **unchanged** bands and invariants.
The confirmation passes iff the record is `physical`, `complete: true` (45/45
`OK`), with `W_acq` and `W_rel` inside 1.5–4.0 ns and 4.5–10.0 ns at every
rising point (the DR-007 selection basis; falling recorded alongside) and
both invariants strict-pass. A nominal single-corner smoke precedes the grid,
as in #275. Assembled-circuit validation of the flop-offset assumption then
belongs to #260 and is a separate gate. This record does not run any of it.

## Consequences

- **Unblocks the route, not the line**: on ratification, #260's phase-window
  blocker lifts conditional on the evidence gate above; #261 and #231 get a
  direction to design against. Until then, `design/lock-detector/DESIGN.md`'s
  verdict stands and row 16 stays DRAFT.
- **#275's products are not selected, and cannot be**: the s50/s25 chains
  remain committed evidence of the structural miss; no candidate, tap count
  or polarity is carried forward as the window realization. The measurement
  cost is sunk but not wasted — it is what makes this argument a measured
  one.
- **DR-007 is untouched**: Tables 1 and 2, the band constants and the
  executable reference stay as they are; `ContractValues`
  (`design/lock-detector/tests/test_lockdet_ref.py`) keeps pinning them. A
  tracking realization lives inside the existing contract; only alternative
  C would require a superseding DR and an operator-ratified band edit.
- **Costs accepted**: the recommended route delays the LOCK circuit by one
  design-and-measure cycle (new structure, new 45-point campaign) and adds
  realization complexity (more cells, matched structures) against the
  alternative of shipping a detector whose release window is unreachable
  over PVT — which is no option at all.

## Status notes

This record stays `proposed` until a **separate operator-only issue**
ratifies it; agents do not self-ratify. Ratifying this record is the action
`design/lock-detector/DESIGN.md` (Verdict) names as #260's unblock condition.
Until ratification *and* a 45/45 phase record for the recommended structure
exist, #260 and #261 remain blocked and spec row 16 remains DRAFT. Nothing
here changes DR-007's status, any band, threshold or spec row, and no
simulation was run for it; the confirming measurement above is named, not
performed.
