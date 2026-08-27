# DR-002: ratify target-spec row 1 (supply range); rows 2/3/4/6/7/8 stay DRAFT

- **Status**: proposed — ratified by the operator's PR approval (see
  "Status notes"; this record's ratification mechanism is `#19`'s own
  operator ruling, quoted there: "the operator's PR approval is the
  ratification act").
- **Date**: 2026-08-19
- **Author**: Builder agent (drafted per #19)
- **Ratifies against / input to**: #19 ("OPERATOR QUESTION: ratify numeric
  target-spec rows so PLL corner verification has bound targets (T1 item
  5)"), itself scoped by the operator's 2026-08-19 ruling on that issue.
- **Supersedes**: none

## Context

`spec/target-spec.md` row 0 (supply flavor) ratified via `DR-001`/#1 on
2026-08-13: the ring, PFD, charge pump, and dividers are built on sky130's
1.8 V core (`nfet_01v8`/`pfet_01v8`). Ratifying row 0 did **not** ratify any
numeric row — each remaining row's "what must be settled on sky130" column
became a committed obligation (re-derive / confirm / port-and-verify)
instead of a draft intention (`target-spec.md`'s own status line).

Issue #19 asks the operator-decision question this record answers: with the
PLL design now substantively complete (#14 closed — sub-blocks #24–#27 and
top-level integration #28/PR #43 merged, `design/top/netlist/top.spice` on
`main`), which numeric rows can actually be ratified today, on the merits of
what evidence exists, versus which must stay DRAFT because no evidence
exists yet? The operator's ruling on #19 (2026-08-19T03:56:09Z) authorized a
builder to propose bound values via exactly this kind of decision record,
with an explicit release valve: "Rows with no evidentiary basis yet may stay
DRAFT — ratify the subset PVT verification actually needs, per this issue's
own framing."

This record is that proposal. It ratifies **one** row (row 1, supply range)
and documents, row by row, why the rest of the candidate list #19 named
(rows 2, 3, 4, 6, 7, 8) is **not** ratified here — each for a specific,
cited evidentiary gap, not by omission.

## Decision

**Ratify row 1 (Supply range)** as: **1.8 V ± 10 % (1.62 – 1.98 V), a single
supply domain** — no separate ring / PFD-CP / digital domain split.

This is a direct, mechanical consequence of the already-ratified row 0, not
a new measured result:

- **The ± 10 % tolerance ports from gf180-pll's own row 1 with rationale,
  not as a bare number.** gf180-pll's row 1 target-spec used 3.3 V ± 10 %.
  The *absolute voltage* does not port across the row-0 supply-flavor change
  (that is exactly why row 0 exists and why every other row below stays
  DRAFT) — but the **± 10 % figure is a generic supply-tolerance assumption**
  independent of the nominal voltage it is applied to, the same convention
  `DR-001`'s own sibling repo (`sky130-bandgap`) and this repo's own harness
  already use. It is not a PLL-performance claim needing PVT evidence to
  ratify; it is an input-tolerance convention this record adopts explicitly,
  with the derivation stated rather than silently ported.
- **The single-supply-domain answer is confirmed by the merged design, not
  assumed.** `design/top/netlist/top.spice` (`.subckt top VDD GND REF
  RESETB NSEL0 NSEL1 NSEL2 NSEL3 NSEL4 NSEL5 CLK`, merged via #28/PR #43)
  instantiates all three active sub-blocks — `pfd_cp`, `vco_ring5`,
  `divider_intN` — against the **same single `VDD`/`GND`** pair
  (`design/top/DESIGN.md`'s pin-mapping table: "top-level supply pins ...
  `pfd_cp`, `vco_ring5`, `divider_intN` (all three; `loop_filter` has no
  `VDD` pin — purely passive)"). There is no domain-split structure in the
  merged design to verify against — the open question ("confirm ... the
  domain split (ring / PFD-CP / digital) on sky130") is answered by
  inspection of the netlist that already exists on `main`: there is one
  domain.
- **This is already the convention every other artifact on `main` uses.**
  `sim/pll/testbench/tb.json` (`supply_nominal: 1.8`, `supply_tolerance:
  0.1`) and the resulting corner-matrix run
  (`sim/pll/records/20260819-061455-f61b6d4.md`, "Supplies (V): 1.62, 1.80,
  1.98") already sweep exactly this range. Ratifying row 1 to match makes
  the spec state what the harness has been assuming since #45, rather than
  leaving that assumption spec-less.

This is the "confirm" obligation row 1's own open-question column names
("confirm the tolerance band and the domain split ... on sky130") —
answered here by direct derivation from the ratified row 0 plus inspection
of the merged design and harness, with no PVT sweep needed because nothing
about this row is a measured circuit result.

**Rows 2, 3, 4, 6, 7, 8 (and every other numeric row) stay DRAFT.** #19's
candidate list named these six specifically as the rows `sim/run_corners.py`
might need a target for; each is examined below and left unratified because
its own open question is not yet answered by any evidence on `main` —
ratifying any of them today would be exactly the "relax a spec to make
results pass" move `CLAUDE.md` and #19's own operator ruling rule out.

### Row 2 — Output band: stays DRAFT

Open question: "re-derive the band and stage count on sky130." No `sim/`
evidence exists for the VCO block at all. `design/vco/DESIGN.md`'s own
"Tuning range / Kvco" section is explicit that its frequency-vs-`VCTRL`
table is "a single, informal, uncommitted ngspice sanity check ... one
process corner (`tt`), one temperature (27 °C) ... not written as a `sim/`
record, and not a claim against any `spec/target-spec.md` row." A
one-corner, one-temperature, uncommitted check is not evidence a decision
record can ratify against — it is explicitly disclaimed by its own author as
such. **Re-derive obligation, not discharged.**

### Row 3 — Reference input: stays DRAFT

Open question: "confirm input levels for the ratified supply flavor." The
CMOS rail-to-rail level claim is trivially true by construction (`REF` is a
plain digital input on the same ratified `VDD`/`GND` rail as everything
else in `design/pfd-cp/`) — but row 3's DRAFT target is not just levels, it
bundles a **frequency range** (1–25 MHz), **duty cycle** (30–70 %), and
**edge-trigger** contract as one target. The only PLL-level exercise of
`REF` on `main` is `sim/pll/testbench/tb_pll.sch`, which drives a single
fixed 10 MHz point — nowhere near the band edges (1 MHz, 25 MHz) — and that
run's own record (`sim/pll/records/20260819-061455-f61b6d4.md`) is an
**0/27 FAIL** (every corner point failed at ngspice execution, a plumbing
defect since fixed by #47, but no new corner run has been recorded since).
There is no evidence the PFD/charge-pump chain (`design/pfd-cp/DESIGN.md`'s
dead-zone-avoidance delay element in particular — a fixed propagation delay
that bounds *some* maximum operating frequency, unquantified in that
document) actually operates correctly across the full 1–25 MHz claimed
range. Ratifying the whole row on the strength of one untested-to-completion
10 MHz point would be a bare port of the frequency band, not a confirmation.
**Confirm obligation, not discharged** (only its narrow "levels" sub-question
is; the row is not decomposed by this spec's structure, so the row as a
whole stays DRAFT).

### Row 4 — Multiplication ratio: stays DRAFT

Open question: "confirm divider retiming closes at the sky130 top
frequency." `design/divider/DESIGN.md`'s "Retiming / top-frequency target"
section answers this explicitly and in the negative-pending-evidence: "No
`sim/` evidence exists for this block; no timing analysis (STA or
transient) was run ... This is exactly the kind of claim `CLAUDE.md` rules
out without a testbench." The divider's *representable* range (`NSEL[5:0]`
= 6 bits, N = 1–64, a strict superset of the DRAFT N = 4–64 floor) is
structurally confirmed by the merged netlist, but the open question is
specifically about **timing closure**, not representable range, and that
half is explicitly unverified. **Confirm obligation, not discharged.**

### Rows 6, 7, 8 — Loop bandwidth, phase margin, lock time: stay DRAFT

All three depend on **closed-loop PLL dynamics** — a locked transient, a
measured loop-bandwidth/phase-margin from a linearized loop model or an
AC/transient sweep, a measured time-to-lock. The only PLL-closed-loop
testbench that exists (`sim/pll/`, #45) has never produced a passing run:
its sole record is 0/27 FAIL, and even a hypothetical passing run today
would only be a **harness plumbing check** — `sim/harness/report.py`'s own
per-point criterion is "ngspice exits 0 ... not a design measurement." The
harness does not yet extract or compare a frequency, a bandwidth, a phase
margin, or a lock time against anything; it only confirms the netlist runs
to completion. There is no path from "ratify these rows" to "T1 item 5
passes" today — that requires **harness measurement capability that does
not exist yet**, layered on top of a **closed-loop transient long enough to
observe lock** (the current `tb_pll.sch` window is 200 ns / two reference
periods, "far short of a cold-start lock transient" per its own `tb.json`
claim). **Re-derive obligations, not discharged** — filed as a follow-up
(see "Consequences").

## Alternatives considered

- **Ratify all six candidate rows on gf180-pll-ported values, noting them as
  provisional.** Rejected: this is precisely the "relax a ratified spec to
  make results pass" move `CLAUDE.md` forbids, and the operator's own ruling
  on #19 quoted that constraint as "the review bar." A "provisional
  ratification" is not a real status this spec's structure has (`RATIFIED`
  or `DRAFT`, no third state) — inventing one would be scope creep on this
  record's own decision, not a faithful reading of the ask.
- **Ratify nothing, leave every row DRAFT, close #19 as answered-in-full by
  citing the evidence gaps.** Considered, but row 1 genuinely has no
  evidentiary gap — its answer is a mechanical consequence of row 0 plus the
  merged design's own structure, already assumed by the harness since #45.
  Declining to ratify a row with a real, cited answer just because its
  siblings lack one would leave the spec understating what is actually known
  today.
- **Wait for the VCO/PFD/loop-filter PVT characterization campaign before
  ratifying anything.** Rejected as the wrong ordering: row 1 does not
  depend on that campaign (it depends only on row 0, already ratified, and
  the merged netlist's supply topology, already fixed), so gating it behind
  unrelated future work would be a needless delay with no evidentiary
  benefit.

## Consequences

**What this record ratifies and unblocks:**

- `spec/target-spec.md` row 1 moves from DRAFT to **RATIFIED**: 1.8 V ± 10 %
  (1.62 – 1.98 V), single supply domain. `sim/pll/testbench/tb.json` and
  every future PVT-corner manifest for this PLL now have a ratified
  citation for their `supply_nominal`/`supply_tolerance` fields instead of
  an unratified assumption.
- Per the operator's ruling on #19 ("the operator's PR approval is the
  ratification act" ... "#20 and #22 unblock when the ratification PR
  merges"), this PR merging is the event #20/#22's Curator dependency checks
  were waiting on.

**What this record does not fix, and hands to a follow-up issue:**

- **T1 item 5 ("full corner verification vs a ratified spec") remains
  blocked** — not on spec-writing, but on two pieces of unbuilt work this
  record makes newly explicit and separable:
  1. A **measurement-capable extension to `sim/harness`**: today
     `report.py`'s per-point criterion is "did ngspice complete," with no
     frequency/lock/bandwidth/phase-margin extraction or comparison against
     a bound target. Rows 2/6/7/8 cannot be ratified — and T1 item 5 cannot
     pass — until the harness can measure these things.
  2. A **sky130 VCO/PFD/loop-filter PVT characterization campaign** feeding
     real values into that harness once it exists — the actual
     re-derivation rows 2/4/6/7/8 owe, run at a closed-loop transient long
     enough to observe lock (unlike the current 200 ns plumbing testbench).
  This record files that as an explicit follow-up issue (see the PR this
  record ships in) rather than leaving it implicit in six DRAFT rows with
  no forward pointer.
- Row 3's frequency-range/duty-cycle claim is now flagged with a specific,
  narrower gap (untested band edges, unquantified PFD max-frequency bound)
  rather than a generic "DRAFT." The follow-up campaign above is the natural
  place to close it alongside rows 2/6/7/8, since it needs the same
  closed-loop transient infrastructure.

## Status notes

This record stays `proposed` until the PR that ships it merges. Per the
operator's ruling on #19 (quoted in "Context" above), **the operator's PR
approval is the ratification act** for this decision — there is no separate
operator-only ratification issue the way `DR-001` had `#1`; #19 itself, plus
this PR, is the ratification mechanism the operator specified. If the
operator's review disagrees with the row-1-only scope (e.g. finds
evidentiary basis this record missed for one of rows 2/3/4/6/7/8), the
resolution is PR review feedback on this record before merge, not a
post-merge supersession — this record has not yet been ratified as this
note is written.
