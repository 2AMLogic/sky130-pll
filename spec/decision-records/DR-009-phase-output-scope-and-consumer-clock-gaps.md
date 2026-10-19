# DR-009: scope disposition of a phase-shifted / multiplied clock output, and two related consumer clock-interface gaps

- **Status**: proposed. This record does **not** ratify or edit any spec row;
  row 2 stays **DRAFT**. See "Status notes".
- **Date**: 2026-10-17
- **Author**: Builder agent (issue #332)
- **Ratifies against / input to**: #332; input to the eventual ratification of
  row 2 (output band)
- **Supersedes**: none

One decision per record. The decision here is **whether v1 of this PLL gains an
additional clock output at a fixed phase offset (90°) or at a multiple (2x / 4x)
of `CLK`**. Two related gaps raised in the same filing are recorded as
dispositions that point at existing work.

## Context

A downstream consumer of this block's clock output reported three
clock-interface gaps against `spec/target-spec.md`. The report was explicitly
not a request for new scope on this repo's schedule, so the deliverable is a
recorded disposition of each gap. The consumer's context is described only as
far as needed: it uses `CLK` as a system clock and derives a quarter-period
clock from it.

1. **No phase / multiplied output.** The spec defines a single `CLK` and no
   output at 90° or at 2x / 4x the output frequency. A consumer that needs one
   must derive it from `CLK`, for example with a delay element. No open issue
   covers this.
2. **`CLK` was the raw VCO node, so rows 14 and 15 were unmeasurable.** Already
   addressed: #232 (output stage) led to PR #302, which merged the
   `design/clk-buf` two-inverter stage, and to `DR-008`
   (`DR-008-clk-output-load-and-buffer-scope.md`, proposed, 1 pF
   characterization load, rows 14/15 stay DRAFT). The remaining evidence
   campaigns are tracked in #303 and #304.
3. **Row 2 band is DRAFT.** Row 2 (10 – 200 MHz) is carried from the sibling
   port and is stated as "NOT assumed to hold" pending a sky130 tuning-range
   campaign. The consumer needs 25 MHz and 50 MHz output, with 100 MHz as a
   stretch point. All three lie inside the draft numbers, but a draft number is
   not evidence that the tuning range reaches them.

## Decision

**Gap 1 — not in v1 (recommended; proposed).** v1 keeps a single `CLK`. No
phase-shifted or multiplied output is added. The consumer continues to derive
its 90° clock from `CLK` with a delay element. Revisit on a ratified downstream
need, as a follow-on issue with its own decision record.

**Gap 2 — covered; no new design.** Dispositioned by #232, PR #302, `DR-008`,
#303 and #304. This record adds nothing to that scope.

**Gap 3 — input to row 2 ratification.** The consumer's 25 MHz, 50 MHz and
100 MHz (stretch) output frequencies are recorded as **required in-band
operating points** for the future tuning-range campaign that ratifies row 2.
Row 2 stays DRAFT and no number in it is changed.

This record is `proposed`; it takes effect only if the operator accepts it.

## Alternatives considered

- **Add a quadrature / 2x / 4x output now.** Rejected for v1: it needs a new
  VCO tap, divider or phase-generation topology, has no ratified requirement
  behind it, and would reopen `DR-008`'s buffered-output regression scope.
  Would need to be true to revisit: a ratified downstream requirement that
  cannot be met by a delay element on `CLK`, plus an operator-approved
  schedule.
- **One issue per gap.** Rejected: gaps 2 and 3 are one-line pointers to
  existing work and do not merit separate issues.
- **Widen or tighten row 2 to cover the consumer's points.** Rejected: that
  would edit a spec row without evidence. Row 2 changes only through its own
  ratification record after the tuning-range campaign.

## Consequences

- No design, simulation, or ratified spec row changes.
- The tuning-range campaign that ratifies row 2 must include 25 MHz, 50 MHz and
  100 MHz as explicit operating points across the PVT set, and report each as a
  pass or a recorded miss.
- If the operator rejects the gap 1 default, a follow-on issue and decision
  record are needed; this record then becomes the pointer to that work.
- Row 2's open-question cell carries a one-line pointer to this record. No
  other spec text changes.

## Status notes

Stays `proposed` until the operator accepts or rejects it on #332. Accepting it
does not ratify row 2, 14 or 15; those close through their own records.

**Follow-on (2026-10-19).** The operator's response on #332 requested a
proposal for an additional phase or multiplied-clock output rather than
accepting the single-output default above. That proposal is `DR-010`
(`DR-010-phase-or-multiplied-output-proposal.md`, proposed). The gap 1 default
in this record is not accepted by that response and is kept here as history.
