# layout/ — the klayout-tools (`klt`) DRC/LVS flow

Issue #2's layout deliverable: a headless, repeatable DRC/LVS flow driven by
[`klayout-tools`](https://github.com/2AMLogic/klayout-tools) (`klt`),
**proven on a trivial known-good cell**. There is no PLL layout yet — that
starts with a later issue, once a PLL schematic exists (`design/` is still
empty). This directory's whole scope for #2 is the trivial-cell proof below.

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
```

The last command writes a fresh, timestamped record under
`trivial-cell/reports/<record-id>/` and updates
`trivial-cell/reports/LATEST` to point at it. Read the current checked-in
record's `record.md` **first** — it is the actual pass/fail evidence this
issue delivers, not this README (see `trivial-cell/reports/LATEST` for its
id).

## Why `klt`, and why a plain PyPI version pin

`layout/requirements.txt` pins `klayout-tools==0.2.0` from PyPI. Earlier
sibling repos (`sky130-bandgap`) had to pin an exact git commit because at
the time PyPI's release (v0.1.0) shipped only five verbs
(`layers`/`stats`/`cells`/`drc`/`pdk`) — `gen`, `extract`, and `lvs` (all
required by this flow) were `main`-only. That gap is closed: PyPI's `0.2.0`
release ships all three, verified directly in this repo's own
`layout/bin/run-trivial-cell-flow.sh` run. See `requirements.txt`'s own
header for the fuller history and how to bump the pin.

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
match `mos_array`'s pinned-default topology at this repo's pinned `klt`
version: **8** independent unit NMOS devices (4 "real" + 4 dummy-column,
all physically drawn and none suppressed at this `klt` version — see
`reference.spice`'s own header for why this differs from sky130-bandgap's
current 4-device reference), each with its own isolated source/drain/gate
net, bodies tied to one shared `vsubs` pin. `klt lvs`/`NetlistComparer`
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
  requirements.txt           # pinned `klt` install (PyPI version)
  bin/
    setup-venv.sh             # create/refresh layout/.venv from requirements.txt
    run-trivial-cell-flow.sh  # the repeatable driver: gen -> drc -> extract -> lvs -> report
    render-record.py          # renders + verdict-checks a record's record.md
  tests/                      # PDK-free unit coverage
  .venv/                      # gitignored -- `klt` install, created by setup-venv.sh
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
first try with the pinned PyPI `0.2.0` release, and the trivial-cell
five-way verdict (DRC clean, DRC negative control `violations`, LVS match,
two LVS negative controls both `mismatch`) reproduced on repeat runs. The
DRC negative control needed no workaround either — `klt draw` is documented
as existing for precisely this case (a known-bad fixture produced with `klt`
alone), it errors cleanly on a malformed shape description rather than
silently emitting an empty cell, and `klt drc` distinguishes the
violations case with its own exit code, so a shell driver can tell "deck
found violations" from "the deck failed to run".
`2AMLogic/sky130-bandgap`'s own layout bootstrap had already
found and filed the two gaps a resistor-array-based trivial cell would hit
([klayout-tools#369](https://github.com/2AMLogic/klayout-tools/issues/369),
the reason this flow (like bandgap's) uses `mos_array` rather than
`res_array`) and the PyPI-lag gap
([klayout-tools#342](https://github.com/2AMLogic/klayout-tools/issues/342),
now closed as of the `0.2.0` release this repo pins) — nothing new to file.

If a *new* gap turns up in follow-on layout issues (once a PLL schematic
exists to draw), file it at `2AMLogic/klayout-tools` per the root
`CLAUDE.md` — tool-gap description only, no spec values or design content
from this repo.

## Known klt-deck limitations relevant to later, PLL-specific layout issues

Not gaps to file (documented, deliberate scope limits of the curated
`sky130` deck, carried over from sky130-bandgap's own note) but worth
flagging now for whichever later issue takes on PLL-block layout, since this
issue's own scope stops at the trivial-cell proof:

- **No NMOS substrate-tap extraction.** The curated deck ties every NMOS
  body to a single global `vsubs` net rather than a real drawn tap
  (`docs/cli/extract.md` → "Coverage"). A future PLL-block LVS reference
  netlist should tie NMOS bodies to a single net for the same reason.
- **No voltage-flavor distinction on MOS devices.** `klt extract`'s `nfet`/
  `pfet` classes are flavor-agnostic — relevant once #1 ratifies this repo's
  supply flavor and a real device mix exists to extract.
