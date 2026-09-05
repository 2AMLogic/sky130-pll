# layout/ — the klayout-tools (`klt`) layout flows

Two flows live here, both headless and repeatable, both driven by
[`klayout-tools`](https://github.com/2AMLogic/klayout-tools) (`klt`):

| Directory | What it is | Issue |
| --- | --- | --- |
| [`pll/`](pll/) | **The PLL layout.** A device-level layout of the closed-loop PLL schematic, drawn from `design/top/netlist/top.spice` — start at `pll/README.md`, then the current record's `record.md` (`pll/reports/LATEST`) | #16 |
| `trivial-cell/` | The DRC/LVS flow's own gating proof on a trivial known-good cell, plus its negative controls | #2 |

The PLL layout is a **device-level floorplan**: every device the schematic
declares is physically drawn at its own W/L, and the extracted device set is
checked back against the schematic. It is **DRC-clean** (issue #17, since
2026-09-05) but still **not routed and not LVS-compared**. `pll/README.md`'s
"What it is not" section states the remaining gaps in full; LVS-clean closure
is #18.

The trivial-cell proof below is unchanged and still the flow's own regression
gate: it is what establishes that a DRC/LVS "pass" from this directory can
also come back "fail".

Two rules from the root `CLAUDE.md` shape this directory:

- **Verification is the product.** A DRC/LVS "pass" claim ships with the
  actual reports it came from, plus a negative control proving the flow can
  also report failure.
- **Friction protocol.** Every `klt` gap/awkwardness hit while standing this
  up gets checked against the public
  [`2AMLogic/klayout-tools`](https://github.com/2AMLogic/klayout-tools)
  tracker and filed (or cross-confirmed if already tracked) there —
  tool-gap description only, never this repo's design/spec content.

## Provenance

Adapted from `2AMLogic/sky130-bandgap`'s `layout/` DRC/LVS bootstrap
(`layout/bin/run-trivial-cell-flow.sh`, source commit
`7f2314c338b1356112e244577c03c288a617fbb4`; `layout/bin/setup-venv.sh`,
`b24b40485ff2a1a53a7eeb2cd6c4beadd1ef33c6`; `layout/bin/render-record.py`,
`7d1ce05168777f6615e1e26adf5eedd6213df318`), per this repo's `CLAUDE.md`
harness-bootstrap rule. Same flow shape and reasoning; this file only covers
the trivial-cell bootstrap, not sky130-bandgap's later block-specific layout
sections (floorplan/routed flows), which are out of scope until this repo has
a PLL schematic to draw.

Deviation from that source: a **DRC** negative control is added here (the
source flow proves only that DRC comes back clean, and relies on the two LVS
controls for the "can it report failure?" half). Issue #2's definition of
done calls for a deliberately-injected DRC violation as well as an injected
LVS mismatch, so step 2b below exists in this repo and not in bandgap's.

## Quick start (cold machine)

```bash
# 1. install the pinned klt build (~10s; see requirements.txt for the pin)
layout/bin/setup-venv.sh

# 2. sanity-check the sky130A PDK resolves (same pin as sim/pdk.json)
layout/.venv/bin/klt pdk find --pdk sky130A

# 3. run the trivial-cell DRC/LVS proof (~5s)
layout/bin/run-trivial-cell-flow.sh

# 4. draw the PLL layout from the schematic netlist (~30s)
layout/bin/run-pll-layout-flow.sh
```

The last command writes a fresh, timestamped record under
`trivial-cell/reports/<record-id>/` and updates
`trivial-cell/reports/LATEST` to point at it. Read the current checked-in
record's `record.md` **first** — it is the actual pass/fail evidence this
issue delivers, not this README (see `trivial-cell/reports/LATEST` for its
id).

## Why `klt`, and why the pin is a git commit

`layout/requirements.txt` pins `klt` by **exact git commit**. It pinned the
PyPI release (`klayout-tools==0.2.0`) from issue #2 through issue #16, and
moved back to a commit pin in issue #46.

**Read [`klt-pin-decision.md`](klt-pin-decision.md) for that decision** — what
the version pin bought, what it cost, what was measured on each side, and the
bump discipline that follows from it. In short: PyPI has published nothing
since `0.2.0`, five of the eight `klt` gaps the PLL layout hit are fixed only
on the tool's `main`, and two of those five are what made the layout
unroutable. `requirements.txt`'s own header lists exactly what the current pin
picks up.

A pin bump is never just a version edit here: it re-runs **both** flows below
and checks the refreshed records in as the non-regression proof.

## The flow

```
klt gen mos_array --pdk sky130A         (1) build the trivial known-good cell
        |
        v
klt drc <cell>.gds --deck sky130        (2) DRC against the sky130 deck
        |                                   -> must report "clean"
        v
klt draw <illegal fixture> + klt drc    (2b) DRC negative control
        |                                    -> must report "violations"
        v
klt extract <cell>.gds --deck sky130    (3) layout -> schematic-equivalent netlist
        |
        v
klt lvs (extracted vs. hand-written      (4) LVS: topology compare, once against
         reference netlist)                  a known-good reference and once
                                             against each of two corrupted ones
```

**The trivial cell**: `klt gen mos_array`'s documented defaults (a 2x2 array
of unit NMOS devices with a one-column dummy guard on each side, `nfet`
flavor, no well) are chosen because the project's own docs guarantee every
generator's default `params` pass `klt drc --deck sky130` clean — exactly
the "trivial known-good cell" this issue's acceptance criteria call for.

**The reference netlist** (`trivial-cell/reference.spice`) is hand-written to
match `mos_array`'s pinned-default topology at this repo's pinned `klt` build:
**4** independent unit NMOS devices — the "real" ones. The generator also draws
4 dummy-column units, which the curated deck's `dummy` marker layer lets
`klt extract` suppress (`dummy_devices_dropped: 4`); it reported all 8 while
this repo pinned `klayout-tools==0.2.0`, which predates that fix. See
`reference.spice`'s own header for why 4 is the topologically correct
reference. Each unit has its own isolated source/drain/gate net, bodies tied to
one shared `vsubs` pin. `klt lvs`/`NetlistComparer`
compares topology, not net *names* (see
[`docs/cli/lvs.md`](https://github.com/2AMLogic/klayout-tools/blob/main/docs/cli/lvs.md)
in the `klayout-tools` repo), so the reference's arbitrary net names do not
need to match the extracted netlist's own arbitrary `$N`-style names.

**The DRC negative control** (`trivial-cell/drc-negative-control.json`) is a
`klt draw` fixture: geometry written verbatim with no PDK awareness and no
rule checking (`klt draw` exists for exactly this — producing a known-bad
fixture a DRC flow must come back flagged on). It carries one deliberately
sub-minimum poly width and one deliberately sub-minimum `li1` spacing, so a
regression that silently disabled either KLayout check primitive is still
caught by the other. A DRC "clean" verdict on the trivial cell only proves
the flow *runs*; this proves it can still say "violations". Two things keep
it honest: `layout/tests/test_drc_negative_control.py` re-derives both
violations from the fixture's own rectangles (PDK-free, so `npm run check:ci`
catches a fixture that drifts back to legal), and `render-record.py` fails
the run unless the deck reports **exactly** the rules the fixture's
`_expected_rules` block declares.

**Two LVS negative controls** (`reference.broken-device.spice`,
`reference.broken-topology.spice`) prove the flow actually *fails* on a real
defect, not just that it produces a report — per `klt lvs`'s own documented
guidance, a device-parameter-only corruption and an independent topology
(shorted-net) corruption, since a single corruption class can pass by
accident on a compare that ignores the other axis. Both must (and do) report
`status: "mismatch"`.

## Directory layout

```
layout/
  README.md                  # this file
  klt-pin-decision.md        # why the `klt` pin is a git commit (issue #46)
  requirements.txt           # pinned `klt` install (git commit; see above)
  bin/
    setup-venv.sh             # create/refresh layout/.venv from requirements.txt
    run-trivial-cell-flow.sh  # the repeatable driver: gen -> drc -> extract -> lvs -> report
    render-record.py          # renders + verdict-checks a trivial-cell record's record.md
    pll_layout.py             # schematic -> layout plan -> `klt gen`/`draw`/`gen-compose`
    run-pll-layout-flow.sh    # the PLL layout driver: plan -> draw -> compose -> drc/extract -> report
    render-pll-record.py      # renders + verdict-checks a PLL record's record.md
  tests/                      # PDK-free unit coverage
  .venv/                      # gitignored -- `klt` install, created by setup-venv.sh
  pll/                        # the PLL layout + its records (see pll/README.md)
  trivial-cell/
    reference.spice                    # known-good LVS reference netlist
    reference.broken-device.spice      # LVS negative control 1: device.property corruption
    reference.broken-topology.spice    # LVS negative control 2: net.merged corruption
    drc-negative-control.json          # DRC negative control: `klt draw` illegal-geometry fixture
    reports/
      LATEST                    # plain-text pointer to the newest record id
      <record-id>/              # <YYYYMMDD-HHMMSS>-<short-git-sha>, one per run
        gen.json, trivial_mos_array.gds
        drc.json
        drc-negative-control.params.json, draw.negative-control.json
        drc_negative_control.gds, drc.negative-control.json
        extract.json, trivial_mos_array.extract.spice
        lvs.request.json, lvs.json
        lvs.broken-device.request.json, lvs.broken-device.json
        lvs.broken-topology.request.json, lvs.broken-topology.json
        reference*.spice           # snapshot of the reference(s) used for this record
        report.md                  # `klt report --format github-summary` rendering
        record.md                  # human-readable pass/fail summary (read this first)
```

`<record-id>` mirrors `sim/`'s `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` (UTC)
convention (see `sim/README.md`) so the two evidence trails read the same
way — including the `dirty` flag's meaning: *the flow that produced this
evidence differed from the named commit*, with the record's own report
directory excluded from that check (a run always creates it). Unlike `sim/`, this flow does not itself enforce a PDK-version pin the
way `sim/harness/pdk.py` does — `record.md` surfaces the resolved PDK version
as a manual cross-check against `sim/pdk.json` instead.

## Friction protocol: what was found

Standing this flow up in this sandbox surfaced no new `klt` gap: `gen`,
`drc`, `draw`, `extract`, and `lvs` all ran cleanly against sky130 on the
first try (originally on the PyPI `0.2.0` release, and again unchanged at the
git-commit pin issue #46 moved to), and the trivial-cell
five-way verdict (DRC clean, DRC negative control `violations`, LVS match,
two LVS negative controls both `mismatch`) reproduced on repeat runs. The
DRC negative control needed no workaround either — `klt draw` is documented
as existing for precisely this case (a known-bad fixture produced with `klt`
alone), it errors cleanly on a malformed shape description rather than
silently emitting an empty cell, and `klt drc` distinguishes the
violations case with its own exit code, so a shell driver can tell "deck
found violations" from "the deck failed to run".

One smaller gap was filed:
[klayout-tools#950](https://github.com/2AMLogic/klayout-tools/issues/950) —
`klt draw`'s request contract does not state whether unrecognized JSON keys
are ignored. `drc-negative-control.json` carries `_purpose`/`_expected_rules`
/`_rule` sidecar keys (JSON has no comments, and a negative-control fixture
that cannot explain which rule each rectangle trips is one careless edit away
from being silently legal). Today `klt draw` accepts and ignores them, but
nothing promises it will keep doing so. If that issue resolves as "unknown
keys are rejected", this fixture moves its notes to whichever escape hatch
the resolution names.
`2AMLogic/sky130-bandgap`'s own layout bootstrap had already
found and filed the two gaps a resistor-array-based trivial cell would hit
([klayout-tools#369](https://github.com/2AMLogic/klayout-tools/issues/369),
the reason this flow (like bandgap's) uses `mos_array` rather than
`res_array`) and the PyPI-lag gap
([klayout-tools#342](https://github.com/2AMLogic/klayout-tools/issues/342),
now closed as of the `0.2.0` release this repo pins) — nothing new to file.

That was the trivial cell's own experience. **Drawing the actual PLL layout
(#16) found considerably more** — eight gaps, of which five were already fixed
on the tool's `main` and reached this repo only through the PyPI pin. Issue
#46's pin bump cleared those five (see
[`klt-pin-decision.md`](klt-pin-decision.md)); what remains open, plus the
one new gap the bumped router surfaced, is tabulated with the workaround each
one forces in
[`pll/README.md`](pll/README.md#friction-klt-gaps-found-drawing-this).
File any further gap the same way, at `2AMLogic/klayout-tools` per the root
`CLAUDE.md` — tool-gap description only, no spec values or design content
from this repo.

## Known klt-deck limitations relevant to PLL-specific layout issues

Not gaps to file (documented, deliberate scope limits of the curated
`sky130` deck, carried over from sky130-bandgap's own note) but load-bearing
for the PLL layout in `pll/` and for the DRC/LVS closure issues (#17/#18)
that follow it:

- **No NMOS substrate-tap extraction.** The curated deck ties every NMOS
  body to a single global `vsubs` net rather than a real drawn tap
  (`docs/cli/extract.md` → "Coverage"). A PLL-block LVS reference netlist
  should tie NMOS bodies to a single net for the same reason. Confirmed in
  the PLL layout's own extraction: every drawn MOS device's body terminal
  comes back on one `vsubs` net.
- **No voltage-flavor distinction on MOS devices.** `klt extract`'s `nfet`/
  `pfet` classes are flavor-agnostic, so extraction cannot itself confirm
  the ratified 1.8 V core flavor (DR-001). The PLL flow closes that gap on
  the schematic side instead: `layout/bin/pll_layout.py` refuses any device
  model it has no primitive for, and both the record and
  `layout/tests/test_pll_layout_plan.py` assert every MOS model in the
  schematic is an `_01v8` core device.
