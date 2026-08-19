# Decision: move `layout/requirements.txt` off the PyPI `klt` pin

**Status**: decided, 2026-08-19 (issue #46).
**Decision**: move from `klayout-tools==0.2.0` (PyPI) to a git-commit pin,
`klayout-tools @ git+https://github.com/2AMLogic/klayout-tools@66f73d0`.

This is a **tooling** decision, not a spec change — nothing in `spec/` moves,
no ratified number changes, so it is recorded here rather than as a
`spec/decision-records/DR-NNN`. It is written down at all because the pin's own
header argued for the PyPI version on reproducibility grounds, and reversing
that argument without stating why would leave the next reader unable to tell
whether the trade was considered.

## The question

Issue #16 drew the PLL layout against `klayout-tools==0.2.0` and hit eight
`klt` gaps ([`pll/README.md` → Friction](pll/README.md#friction-klt-gaps-found-drawing-this)).
Five were already fixed on the tool's `main` and reached this repo only because
the pin is the PyPI release. The release is far behind `main`
([klayout-tools#953](https://github.com/2AMLogic/klayout-tools/issues/953)
tracks that cadence gap), and one of the five —
[#1057](https://github.com/2AMLogic/klayout-tools/issues/1057), a router that
never checked one route against another — is the single reason the shipped
layout is unrouted, which is what blocks #17 (DRC-clean) and #18 (LVS-clean).

So: stay on a PyPI version pin (simple, artifact-immutable, hash-checkable) or
move to a git-commit pin (picks up the fixes, loses the PyPI artifact story)?

## What was verified, not assumed

Every claim below was measured at `66f73d0` in this repo's own worktree, not
read off an issue's closed status.

| Claim | How it was checked | Result |
| --- | --- | --- |
| A newer PyPI release exists | PyPI JSON API: releases are `0.1.0`, `0.2.0` | **No.** `0.2.0` (2026-08-04) is still the latest; the fixes sit under "Unreleased" in the tool's CHANGELOG. "Wait for a release" is not an option with a date on it |
| #1057 (route-vs-route) fixed | Ran the PLL flow's own router spot-check on both pins | **Yes, largely.** On `0.2.0` all 7 drawn routes came back merged onto 2 nodes. At this pin the router draws 51 legs and rejects 302 with `legs[].reason: "crosses already-routed net '<net>'"`. One residual short remains — see below |
| #1073 (bundle nets) fixed | Same spot-check; 53 of 60 declared nets are >2-pin | **Yes.** Bundle nets route as spanning trees of two-pin legs, with per-leg `reason` and a per-net `status` (`routed`/`partial`/`unrouted`). On `0.2.0` every bundle was unroutable by construction |
| #1059 (`klt draw` composes) fixed | `klt draw` response envelope | **Yes.** It carries `generator: "draw"`; the hand-forged block report is no longer required for drawn geometry |
| #1117 (MiM generator) fixed | `klt gen --list` | **Yes.** `cap_array` exists (sky130 capm/met3 unit row, top-plate via + landing pad). Available, not yet adopted here — see "What this does not do" |
| #1166 (block orientation) fixed | CHANGELOG + request schema | **Yes.** `blocks[].orientation` takes `mirror_x`/`mirror_y`/`rotate_180`. Available, not yet adopted (the divider is a single row) |
| #1155 (`layout-plan`) usable as a CLI verb | `klt --help` and the installed package | **No CLI verb.** `layout_plan.py`/`layout_plan_execute.py` ship as *library* modules; `docs/cli/layout-plan-execute.md` states plainly that there is deliberately no `klt layout-plan` subcommand. See "Does `layout-plan` supersede `pll_layout.py`?" |

## The decision, and the argument for it

**Move to the git-commit pin.**

1. **The reproducibility cost is smaller than the pin's old header implies.**
   That header's claim was "a version pin, re-fetched, is byte-identical". A
   git *commit* pin is content-addressed too: the sha names one immutable tree,
   and `pip` records it in `direct_url.json`, so a re-fetch installs the same
   source. What is genuinely lost is PyPI's artifact immutability and a
   hash-checkable wheel — real, but second-order against a tool whose behaviour
   this repo re-derives from checked-in records on every run.
2. **There is no "wait for the release" option.** PyPI has published nothing
   since `0.2.0`, and the fixes are in the CHANGELOG's "Unreleased" section.
   Staying put is not "wait a week"; it is "keep working around five fixed bugs
   indefinitely".
3. **The capability is not hypothetical.** Two of the five (#1057, #1073) are
   exactly the two that made routing impossible, and both were measured working
   on this design. Routing is the gate on #17 and #18.
4. **It restores the sibling repo's discipline.** `2AMLogic/sky130-bandgap`'s
   `layout/requirements.txt` has pinned by commit through eight deliberate
   bumps, each with its own "what this picks up / what it changes /
   non-regression proof" note. This repo's `CLAUDE.md` says to mirror that
   plumbing rather than reinvent it; the version pin was the deviation.
5. **The correctness changes ride along.** The bump also brings `klt extract`'s
   MiM perimeter/fringe term and sky130 dummy-device suppression. Both make the
   extracted netlist *more* faithful, and both are absorbed by making this
   repo's own predictions match the better model — not by loosening a
   comparison (see "What changed in the checked-in evidence").

### What this does *not* do

It does not produce a routed layout. Re-running the router at this pin, on this
floorplan, still leaves most nets undrawn, for reasons the record now tabulates
from the router's own per-leg `reason` strings:

| Why a leg was not drawn | Legs |
| --- | --- |
| would cross an already-drawn route (the #1057 check, now present) | 302 |
| backbone would plough through its own pin's block (no channel inside a matched array) | 277 |
| backbone would plough through an unrelated block's bbox (no channel between abutted groups) | 141 |
| terminates on a bare-poly gate with no contacted landing pad | 129 |

The last two are this design's own doing, not the tool's: the floorplan
shelf-packs groups with no routing channels, and the flow does not opt into
`mos_array`'s `params.gate_contact`
([klayout-tools#492](https://github.com/2AMLogic/klayout-tools/issues/492)).
Both are #17/#18's work. And one **residual short survives** the route-vs-route
check (`DN|GND` in the spot-check's extraction): reduced to a minimal,
design-free reproduction — two 2-pin self-nets on one default-shaped
`klt gen mos_array`, both certified `routed: true`, extracting as one node —
and filed upstream as
[klayout-tools#1197](https://github.com/2AMLogic/klayout-tools/issues/1197) per
the friction protocol. So the shipped stream stays unrouted, for a smaller and
better-understood reason than before.

`cap_array` (#1117) and block `orientation` (#1166) are likewise *available*
rather than *adopted*: adopting either changes drawn geometry and needs its own
evidence, which is layout work, not a pin bump.

## What changed in the checked-in evidence

Both flows were re-run at the new pin and their records are checked in.

- **Trivial cell** (`layout/bin/run-trivial-cell-flow.sh`): PASS, same six-way
  verdict. `klt extract` now suppresses the generator's 4 dummy-column units
  (`device_count` 8 → 4, `dummy_devices_dropped` 0 → 4), so
  `trivial-cell/reference*.spice` are re-stated at 4 M-cards. That is the
  topologically correct reference — a dummy unit has no schematic counterpart —
  and is the same shape sky130-bandgap settled on when it took the same fix. It
  is not a relaxation: the 8-card version was itself compensating for a `klt`
  recognition gap.
- **PLL layout** (`layout/bin/run-pll-layout-flow.sh`): PASS, same eight-way
  verdict, same device sets, same DRC signature (52 × `li1.space.1`, one per
  minimum-gate-length device). One prediction changed: `klt extract` now
  includes a MiM capacitor's perimeter/fringe term, so the record's
  schematic-vs-extracted capacitor cross-check predicts the same two-term value
  (`MIM_PERIM_CAP_F_UM`, taken from the curated deck like the area term already
  was) and still compares **exactly** — the tolerance was not widened.
- The record's routing narrative was rewritten, because the old one asserted
  "every route drawn is a short", which is no longer true.

## Does `klt layout-plan` supersede `layout/bin/pll_layout.py`?

Partly in principle, not in practice today.

`klayout_tools.layout_plan` (Phase B, #1131) validates a plan document, and
`klayout_tools.layout_plan_execute` (Phase C,
[#1155](https://github.com/2AMLogic/klayout-tools/issues/1155)) compiles one
onto `klt gen` + `gen-compose`, including netlist-derived sizing and derived
`connectivity[]` — genuinely the first-class version of what `pll_layout.py`
does by hand. But:

- **There is no `klt layout-plan` CLI verb.** Confirmed against `klt --help` at
  this pin and stated outright in the tool's own
  `docs/cli/layout-plan-execute.md` ("There is no `klt layout-plan execute`
  verb… this ships as a library-level module"). This flow shells out to `klt`;
  adopting Phase C means importing the library, i.e. a different integration
  shape.
- **The plan contract is netlist-digest-driven**, so the parts of
  `pll_layout.py` that are this design's own judgement (grouping by
  `(flavor, W, L)`, the standard-cell row, the MiM plate drawing, the
  core-device-flavor assertion for DR-001) would have to be re-expressed as a
  plan document, not deleted.

So: a real follow-up candidate, worth revisiting when either the flow needs
`layout_plan_execute`'s row/abutment/connectivity compilation or the verb
appears — recorded here rather than attempted inside this decision.

## How to bump this pin again

Same discipline sky130-bandgap uses, and what this bump followed:

1. Pin an exact commit, never floating `main`.
2. Say in `requirements.txt`'s header what the bump picks up and what it
   changes.
3. Re-run **both** `layout/bin/run-trivial-cell-flow.sh` and
   `layout/bin/run-pll-layout-flow.sh`, and check the refreshed records in as
   the non-regression proof.
4. If a record's numbers move, explain the movement — or fix this repo's
   prediction to match a better model. Never loosen a comparison to absorb it.
