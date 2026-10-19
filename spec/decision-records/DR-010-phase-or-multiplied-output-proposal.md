# DR-010: proposal for a quarter-cycle phase output (2x VCO + I/Q ÷2) versus a multiplied-clock output

- **Status**: proposed. This record does **not** ratify or edit any spec row;
  rows 2, 14 and 15 stay **DRAFT**. See "Status notes".
- **Date**: 2026-10-19
- **Author**: Builder agent (issue #339)
- **Ratifies against / input to**: #339; input to the operator's ruling on
  #332 and to the eventual ratification of row 2 (output band)
- **Supersedes**: none (`DR-009` is preserved as history; see "Context")

One decision per record. The decision here is **which interface, if any, v1
should add for a clock at a quarter-cycle offset from `CLK`**: a direct
quarter-cycle phase output, or a multiplied-clock output. The full analysis is
in `docs/phase-output-proposal.md`.

## Context

`DR-009` proposed keeping a single `CLK` and left that scope decision
proposed until the operator answered #332. On 2026-10-19 the operator
selected the option that requests a proposal for an additional phase or
multiplied-clock output instead of accepting `DR-009`'s single-output
default. `DR-009` is not edited to say otherwise: its default is the option
the operator declined to accept, and it remains the record of the original
reasoning. This record is the follow-on `DR-009` called for.

This record does not select a topology on the operator's behalf, ratify a
numeric target, approve implementation, authorize simulation spend, or fold in
#333 (the 500 MHz consumer request, which is a separate decision). The buffered
output and its validation remain owned by `DR-008`, #232, #303 and #304.

## Decision

**Recommended (proposed):** add a quarter-cycle phase interface, `CLK` plus
`CLK90`, produced by running the existing 5-stage ring at 2x the output
frequency and deriving both outputs from a reset-defined I/Q ÷2, with the
feedback counter taking its input from `CLK`. No multiplied clock is exported
in v1.

This record is `proposed`; it takes effect only if the operator accepts it,
and even then it authorizes only the separately scoped issues listed in
`docs/phase-output-proposal.md` §6.

## Alternatives considered

- **Direct taps from the 5-stage ring.** Rejected: the ring offers 36° phase
  steps, so no tap is at 90° (nearest error 18°).
- **Even-stage or differential ring with native quadrature.** Rejected for v1:
  it replaces the VCO and orphans the committed VCO, jitter and lock
  evidence. Would need to be true to revisit: a row-9 or row-13 campaign that
  already motivates a differential ring (`design/vco/DESIGN.md`).
- **Export a 2x or 4x clock.** Rejected as the recommendation: 2x leaves the
  quarter-cycle derivation with the consumer; 4x moves the fast clock and its
  distribution to the consumer and raises the exported frequency to 800 MHz at
  the band edge. Revisit on a ratified consumer requirement for a fast clock.
- **Keep the `DR-009` single-output default.** Not rejected on its merits here;
  it is the operator's call, and it is the cheapest option. It leaves the
  consumer's delay-element derivation and its PVT drift in place.

## Consequences

- If accepted: the VCO must cover 2x the output band, so the row-2 tuning-range
  campaign scope doubles at the top; a `CLK90` output, a matched buffer and an
  I/Q ÷2 cell are added; every `design/top`-dependent record from before the
  change describes a different circuit and any new record must say so.
- Costs not yet known: the `CLK`-to-`CLK90` skew from mismatch, the effect of
  the ÷2 stage on the recorded row-9 miss, power at 2x, and startup ordering.
- Nothing in this record changes a ratified row, the rows 14/15 bounds, or the
  evidence `DR-008` owes.

## Status notes

Stays `proposed` until the operator rules on #332 after reviewing the
proposal PR for #339. Merging this record is not an approval of the interface
or of any implementation. No `sim/` record, schematic, netlist or layout is
added or changed by it.
