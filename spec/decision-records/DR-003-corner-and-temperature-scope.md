# DR-003: sky130 process-corner set and operating temperature range for PLL PVT verification

- **Status**: proposed — ratified by the operator's PR approval (per the
  mechanism the operator set out on #19, reused here: "the operator's PR
  approval is the ratification act"). This record is not marked `ratified`
  by its author; only the merge of the PR that ships it performs that act.
- **Date**: 2026-08-27
- **Author**: Builder agent (drafted per #77)
- **Ratifies against / input to**: #77 ("no target-spec row binds the PVT
  process-corner set or temperature range, so 'all corners' is undefined")
- **Supersedes**: none

## Context

`spec/target-spec.md` rows 0 and 1 bind the supply axis of "PVT" — supply
flavor (`DR-001`, 1.8 V core) and supply range (`DR-002`, 1.8 V ± 10 %,
1.62–1.98 V). Neither record, nor any other row, binds the other two PVT
axes: the **process-corner set** and the **operating temperature range**.
Row 14 ("Output duty cycle") already quantifies its target over "all
corners," and every future per-corner row (2, 6, 7, 8, 9, 10, 13, 14, 16)
will do the same — but "all corners" is not defined anywhere in the ratified
spec. `grep -Ei 'temperatur|-40|125|corner' spec/target-spec.md` on `main` @
`693e3f2` returned only prose (line 33's forward reference to future "corner
bindings," and row 14's own "all corners" text) — no spec row.

The corner set exists today only as an **unratified harness convention**,
copied between manifests without argument:

- `sim/pll/testbench/tb.json`: `"process_corners": ["tt","ss","ff"]`,
  `"temps_c": [-40, 27, 125]`.
- `sim/pdk-smoke`'s recorded runs use the same 3×3×3 grid.
- `sim/pdk.json` (this repo's PDK reproducibility pin) separately lists a
  broader set — `["tt", "ss", "ff", "sf", "fs", "ll", "hh"]` — as "the basic
  N/P device sections that actually exist in the PDK ngspice library," with
  a note that `hl`/`lh`/the `*_mm` sections also exist but are not pinned
  until a manifest actually uses them. `sim/pdk.json` documents what the PDK
  *offers*; it does not decide what this PLL's verification *needs*, which
  is exactly the gap this record closes.

**What the installed PDK actually defines** (verified against
`sky130A/libs.tech/ngspice/sky130.lib.spice` and its `corners/*.spice`
includes in this sandbox, `open_pdks` commit `c6d73a35f524070e85faff4a6a9eef49553ebc2b`
— the same pin `sim/pdk.json` records):

- Five named `.lib` sections carrying distinct `nfet_01v8`/`pfet_01v8`
  device models: `tt` (`.pm3.spice` typical for both), `ff` (fast NMOS, fast
  PMOS), `ss` (slow NMOS, slow PMOS), `sf` (slow NMOS / fast PMOS — verified
  by grep: `sf.spice` includes `..nfet_01v8__sf.pm3.spice` and
  `..pfet_01v8__sf.corner.spice`), and `fs` (fast NMOS / slow PMOS, the
  mirror image). These are the standard 5-corner MOS process-corner set —
  the same corner topology `2AMLogic/gf180-pll`'s own (independently
  numbered) sibling spec verifies against on its own 3.3 V PDK, though this
  record does not port gf180-pll's numbers or its 7-bundle convention (see
  *Alternatives considered*).
- Twenty additional `.lib` sections (`ll`, `hh`, `hl`, `lh`, and their
  `sf_*`/`ff_*`/`ss_*`/`fs_*`/`*_mm` compounds) that keep the MOS corner at
  `tt` and instead vary the resistor/capacitor corner (`res_*__cap_*`
  includes) or toggle the `mc_mm_switch`/`mc_pr_switch` mismatch-Monte-Carlo
  parameters. These are genuinely separate axes from MOS process skew.
- No hard temperature-validity boundary is encoded in the BSIM4 model files
  themselves (`sky130_fd_pr__nfet_01v8__tt.pm3.spice` etc.) — they carry
  real temperature-dependence coefficients (`kt1`, `ub1`, `ua`, `uc`, and a
  `tnom = 30.0` nominal-temperature reference) rather than a fixed
  single-temperature characterization, but the PDK does not itself enumerate
  a discrete "these are the temperatures" set the way it enumerates named
  process corners. The temperature axis is therefore a verification-scope
  choice this record makes explicitly, not a PDK-provided enumeration.

`design/pfd-cp/DESIGN.md`'s own "Reference-spur note" (qualitative, no
numeric claim) names the charge pump's un-cascoded `MPCP`/`MNCP` current
mirror as the dominant source of `UP`/`DN` current mismatch: "the
single-stage (non-cascoded) mirror topology ... has lower output impedance
than a cascode would, so `MPCP`'s and `MNCP`'s currents vary more with `CP`'s
instantaneous voltage ... any residual `UP`-vs-`DN` current mismatch shows up
as a net charge injected into the loop filter once per reference cycle." This
is a specific, structural reason a mixed-skew corner might matter for this
particular design — it is not evaluated at all by `sim/pll/testbench/tb.json`'s
prior `tt`/`ss`/`ff` set, which never separates NMOS and PMOS speed.

## Decision

**Ratify `spec/target-spec.md` rows 19 (Process corners) and 20 (Operating
temperature range)** as:

- **Row 19 — Process corners**: sky130's five standard MOS/BJT process
  corners — `tt`, `ff`, `ss`, `sf`, `fs`.
- **Row 20 — Operating temperature range**: −40 °C to 125 °C, sampled at
  three points: −40 °C, 27 °C, 125 °C.

Crossed with the already-ratified row 1 (supply range: 1.8 V ± 10 %,
1.62–1.98 V), these two rows define the PVT grid every future per-corner
target-spec row is verified against once that row is itself ratified — the
same role row 1 plays for the supply axis.

### Why all five MOS corners, not a subset

`tt`/`ss`/`ff` alone (the prior harness convention) only ever moves NMOS and
PMOS device speed **together** — both slow, both fast, or both typical. That
set structurally cannot exercise an NMOS-vs-PMOS speed differential. This
design's charge pump has a specific, named reason such a differential
matters: the un-cascoded `UP`/`DN` current mirror `design/pfd-cp/DESIGN.md`
already flags as this block's dominant spur mechanism is exactly the
circuit a mixed-skew corner (`sf` or `fs`) stresses hardest, because it is
where realized NMOS and PMOS currents diverge most from each other at a
given bias. Leaving `sf`/`fs` out of the ratified set would leave "all
corners" (row 14, and every future per-corner row) blind to precisely the
condition this block's own design documentation identifies as its most
mismatch-sensitive one. Ratifying all five is therefore not generic
thoroughness — it closes a specific, cited gap in the prior convention.

### Why −40…125 °C, sampled at three points

The PDK gives no discrete temperature set to choose from (see *Context*), so
this is a verification-scope decision rather than a PDK-provided
enumeration. −40 °C to 125 °C is the conventional industrial temperature
range, and the choice is corroborated by two independent, non-circular
sources:

1. **A sibling sky130 canary's own ratified spec.** `2AMLogic/sky130-bandgap`
   — built on the same sky130 PDK, same `open_pdks` family — independently
   ratified the identical −40…125 °C range in its own target-spec ratification
   record (`DR-005-ratify-target-spec.md`: "Temp coefficient (−40…125 °C)
   ... measured across 45 PVT corners"). This is not this repo copying
   `tb.json`'s own convention back on itself — it is a second, separately
   argued sky130 project reaching the same range for the same PDK, which is
   the kind of corroboration a bare self-citation would not provide.
2. **The device model's own temperature-dependence structure.** The BSIM4
   model files carry real, non-trivial temperature-dependence coefficients
   (`kt1`, `ub1`, `ua`, `uc`) around a 30 °C nominal (`tnom`), meaning the
   models are built to be exercised meaningfully away from room temperature
   — an industrial range is a reasonable scope to exercise that structure
   at, not an arbitrary pick.

The three sample points (−40, 27, 125) are the conventional cold / room /
hot triple: they are not a fine-grained temperature sweep (that remains a
future campaign's choice, e.g. denser sampling if a specific row's
derivative-vs-temperature behavior needs it), but they bound the range and
include a value close to `tnom` (27 °C, adjacent to the model's own 30 °C
reference) as the nominal operating point.

## Alternatives considered

- **Port gf180-pll's own corner/temperature convention verbatim.** Rejected
  — out of scope per #77 and `CLAUDE.md`'s cardinal rule for this file
  ("[n]o number below is presented as final ... [w]here a value is carried
  from gf180-pll ... it is a candidate to be tested, not a commitment").
  gf180-pll's own spec (`spec/pll.md`) additionally uses a differently
  shaped convention — "7 corner bundles" including `all-fast`/`all-slow`
  combined transistor-and-passive skew bundles, on top of the basic 5 MOS
  corners — built around its own 3.3 V/180 nm device menu and extraction
  flow. sky130's discrete named corners are not the same set, and this
  record is grounded in what `sky130.lib.spice` itself defines, not in what
  gf180-pll happened to define for a different PDK.
- **Silently ratify `tb.json`'s existing `tt`/`ss`/`ff`, −40/27/125 °C
  convention as-is, without examining it.** Rejected — this is precisely the
  "relax a ratified spec to make results pass" pattern `CLAUDE.md` and #77
  both rule out. The temperature range survives scrutiny (see "Why
  −40…125 °C" above) and is kept; the process-corner subset does **not**
  survive scrutiny once `design/pfd-cp/DESIGN.md`'s own UP/DN-mismatch note
  is read against it, and is expanded rather than rubber-stamped.
- **3-corner set (`tt`/`ss`/`ff` only), treating `sf`/`fs` as optional future
  work.** Considered and rejected — see "Why all five MOS corners" above.
  The gap is not generic thoroughness; it is a specific, structural
  under-coverage of this design's own most-cited mismatch mechanism.
- **Include the interconnect R/C skew corners (`ll`/`hh`) in the ratified
  process-corner set.** Deferred, not rejected. `sim/pdk.json`'s own
  provenance note already distinguishes these: they hold the MOS corner at
  `tt` and instead vary resistor/capacitor parasitics, which matters most
  for precision ratio-based analog blocks (the kind `sky130-bandgap` is
  built from) rather than for a ring-oscillator/PFD/charge-pump PLL whose
  loop-filter R/C sizing is not itself ratified yet (rows 6/7 stay DRAFT per
  `DR-002`). Revisit once the loop filter's own row is ratified, if a future
  campaign shows R/C skew is a first-order sensitivity for that specific
  filter — nothing in the design record today argues it is.
- **Include statistical mismatch (`mc_mm_switch`/Monte Carlo `_mm`
  sections).** Out of scope for this record. Process-corner *skew* (this
  record's subject) and *local mismatch* (a Monte Carlo methodology
  question) are different axes; the latter is already tracked separately
  (per the Curator's duplicate-check note on #77, related to #20's
  Monte Carlo/yield methodology work), not something this row's binding
  should fold in.
- **Narrow the temperature range** (e.g. a commercial 0–70 °C range).
  Rejected — gives up margin against automotive/industrial deployment
  scenarios with no stated benefit, and departs from the sky130 ecosystem
  precedent (`sky130-bandgap`'s own ratified range) without a reason to be
  narrower.
- **Widen the range beyond −40…125 °C** (e.g. an additional wafer-level
  extreme corner). No evidentiary basis is offered to go beyond the
  conventional industrial range for this design class; deferred rather than
  rejected — revisit if a downstream integration requirement calls for a
  wider qualification range.

## Consequences

**What this record ratifies and unblocks:**

- `spec/target-spec.md` rows 19 (Process corners) and 20 (Operating
  temperature range) move from undefined to **RATIFIED**: the five sky130
  MOS/BJT process corners `tt`/`ff`/`ss`/`sf`/`fs`, and −40/27/125 °C.
  Together with the already-ratified row 1, every future per-corner row now
  has a bound PVT grid to cite instead of restating an unratified
  convention.
- Row 14's "all corners" language (and every future row that uses the same
  phrase) now resolves to a concrete, ratified set rather than an undefined
  quantifier.

**What this record does not fix, and hands to a follow-up:**

- `sim/pll/testbench/tb.json` and `sim/pdk-smoke`'s manifest(s) still declare
  `"process_corners": ["tt","ss","ff"]` — narrower than the now-ratified
  5-corner set (missing `sf`/`fs`) — and their `temps_c` happens to already
  match the ratified temperature range. Updating those manifests to cite
  this ratified row (and to widen `process_corners` to include `sf`/`fs`) is
  **explicitly out of scope for this record and the issue it closes** (#77's
  own Non-goals: "No harness code changes"). This record does not leave that
  gap silent — a follow-up issue is filed alongside this PR so a future
  Builder closes it deliberately rather than the manifests silently
  continuing to under-cover the ratified corner set.
- No new sim campaign is run by this record. Rows that depend on an actual
  PVT sweep (2, 6, 7, 8, 9, 10, 13, 14, 16, etc.) remain DRAFT until their
  own evidentiary gap (documented per-row in `DR-002`) is closed by a real
  campaign against the grid this record now defines — that campaign work is
  #52/#54's scope, not this record's.

## Status notes

This record stays `proposed` until the PR that ships it merges. Per the
mechanism the operator set out on #19 and reused for `DR-002` — "the
operator's PR approval is the ratification act" — there is no separate
operator-only ratification issue the way `DR-001` had `#1`; #77 itself, plus
this PR, is the ratification mechanism. If the operator's review disagrees
with the corner set or temperature range this record proposes (e.g. finds a
reason to include the R/C skew corners, or to narrow/widen the temperature
range), the resolution is PR review feedback on this record before merge,
not a post-merge supersession — this record has not yet been ratified as
this note is written.
