# sky130-pll

An integer-N, ring-oscillator phase-locked loop for the
[SkyWater sky130](https://github.com/google/skywater-pdk) open PDK, designed
entirely in the open-source analog flow: **xschem** for schematic capture,
**ngspice** for simulation, and
[klayout-tools](https://github.com/2AMLogic/klayout-tools) (`klt`) for layout
work. It is a sky130 **port** of the sibling canary
[gf180-pll](https://github.com/2AMLogic/gf180-pll) — same block class, a second
PDK — so that "one PLL, two open PDKs" becomes the portability proof.

This block is built by AI agents. Not "AI-assisted" — agents do the schematic
capture, write the testbenches, run the PVT corner sweeps, argue the design
decisions out in written decision records, and open the pull requests. The
verification evidence in `sim/` is the point of the repository: every claim this
project makes is meant to be backed by a testbench and a recorded corner sweep,
in a format designed so you can check that yourself.

## What this is — a reverse-engineering-free DESIGN canary

This is a **design** canary, not a reverse-engineering one. Nothing here is
recovered from an existing part, a competitor's netlist, or a decapped die. The
PLL is designed forward from a ratified target specification, and the whole
record — spec, decision records, evidence, dead ends — is original work. That
distinction matters for what the repo is *for*:

- **Dogfood for [klayout-tools](https://github.com/2AMLogic/klayout-tools).**
  A real block drawn against the sky130 open-PDK decks is the forcing function
  on the tool. Every time `klt` is awkward, missing a capability, or the wrong
  shape for the job, that friction is filed as a generic issue against
  klayout-tools (see the friction protocol in `CLAUDE.md`). The fix benefits
  everyone using sky130, not just this repo.
- **Catalog inventory.** This is one entry in the 2AM Logic canary catalog —
  one block, one PDK — building out the inventory of open-PDK analog/mixed-signal
  blocks the agent fleet can design end to end.

## Status: schematic entry landed (unverified). Pre-spec-ratification, pre-simulation, pre-layout, pre-silicon.

Being honest about where this actually is: this repository holds the map — a
DRAFT target spec, the canary rules, a working sim harness and layout DRC/LVS
flow proven on trivial, PLL-content-free DUTs (issue #2), and, as of issue
#28, a full PLL schematic + netlist. There is still no PLL verification
evidence and no PLL layout.

- **Not done** — the target spec is **DRAFT and unratified** (see
  `spec/target-spec.md` and issue #1). No number in it is binding, and every
  value is explicitly a starting point carried over from gf180-pll or a
  published sky130 reference, not a settled sky130 result.
- **Done (plumbing only)** — the sim harness (`sim/run_corners.py`, an xschem
  + ngspice PVT corner runner) and the `klt` layout DRC/LVS flow are stood up
  and proven end to end: `sim/pdk-smoke` runs a trivial resistor-divider DUT
  across a real process/temperature/supply sweep, and
  `layout/bin/run-trivial-cell-flow.sh` DRC/LVS-cleans a trivial cell and
  demonstrably catches an injected DRC/LVS defect (see `sim/README.md` and
  `layout/README.md` for the checked-in evidence). Seeded from gf180-pll (the
  PLL testbench/corner-runner structure) and
  [sky130-bandgap](https://github.com/2AMLogic/sky130-bandgap) (the sky130
  open-PDK plumbing: `volare` PDK install, `xschemrc`, `spiceinit`, and the
  sky130 `klt` decks) per issue #2. Neither harness has run against any PLL
  content yet — that starts once a testbench exists (#23) and the DRAFT spec
  rows each block targets are ratified.
- **Done (schematic entry, unverified) — issues #24/#25/#26/#27/#28.** All
  four PLL blocks (ring-oscillator VCO, tri-state PFD + charge pump, passive
  loop filter, programmable integer-N feedback divider) are authored as
  forward-designed xschem schematics against sky130's 1.8 V core devices
  (`DR-001`) and wired into a single top-level closed-loop schematic
  (`design/top/top.sch`), each with a connectivity-only SPICE netlist
  snapshot checked into `design/`. Every design value in these schematics
  (device sizing, `Icp`, `Kvco`, filter component values, divider bit width)
  is a documented design-time target or estimate, **not** a simulated or
  verified result — see each block's own `design/<block>/DESIGN.md` and
  `design/top/DESIGN.md` (which also documents one known, unresolved
  coordination gap: the loop filter's `Icp` design point predates, and does
  not yet match, the charge pump's landed value).
- **Not started** — PLL verification campaigns (closed-loop testbench, #23,
  and the PVT campaign that follows) and PLL-block layout. `measurements/`
  has a per-spec-row rollup report/aggregator (issue #22) that reads
  `sim/`/`layout/` evidence, but no PLL evidence exists yet for it to report
  — real silicon characterization still waits on silicon.

The maturity ladder being climbed: spec-ratified → simulation-complete → layout
DRC/LVS-clean → shuttle seat → measured silicon over temperature. This repo is
at the bottom of it.

## Private for now

This repository is **private**. It is a design canary that binds under the 2AM
Logic invention firewall; whether and when it goes public is an **operator**
decision, not an agent one — the visibility flip is an operator action. Even so,
write every commit message, issue, and document here as if a stranger will read
it, because one day one may. Nothing about business positioning, commercial
terms, or the contents of other 2AM Logic repositories belongs in this one.

## Repository layout

```
spec/          DRAFT target spec + numbered decision records (DR-NNN)
design/        xschem schematics/symbols + SPICE netlist snapshots (4 blocks + top-level integration, unverified)
sim/           PVT corner harness (stood up) + append-only evidence records; no PLL testbench yet
layout/        klt-driven DRC/LVS flow (stood up, proven on a trivial cell); PLL-block GDS not yet drawn
measurements/  per-spec-row report aggregator (rolls up sim/+layout/ evidence) + silicon characterization (the latter empty until there is silicon)
```

Start with `spec/target-spec.md` for *what is being targeted and why nothing is
settled yet*, and `sim/README.md` / `layout/README.md` for *how results are
recorded and how to reproduce them*.

## How verification will work here

Two rules govern the repository, and most of its structure follows from them:

1. **No claim without a testbench.** A statement about the design is only
   admissible if there is a testbench that produces it, run across the PVT
   corner matrix (temperature, supply, and sky130 process corners), with the
   raw per-corner simulator logs committed alongside the summary.
2. **`sim/` is append-only evidence.** A record, once written, is never edited
   or deleted. Re-running — even to correct a mistake — mints a *new* record
   that names the record it supersedes. So the repository keeps its own
   mistakes, in order, with the corrections attached.

## License

Apache License 2.0 — see [LICENSE](LICENSE). Copyright 2026 2AM Logic.
