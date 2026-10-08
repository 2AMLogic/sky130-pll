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
PLL is designed forward from a target specification (ratified row by row), and the whole
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

## Status (as of 2026-10-08)

This repository is a work in progress, and this section is deliberately a
pointer rather than a scoreboard: it says what kinds of evidence exist and
where the verdicts live, so it does not have to be re-edited after every
campaign. For current state, read the linked files, not this prose.

- **Spec** — [`spec/target-spec.md`](spec/target-spec.md) is **partially
  ratified**. Some rows are bound by decision records in
  [`spec/decision-records/`](spec/decision-records/); the remaining rows are
  still DRAFT starting points and are not binding. The spec file itself lists
  which rows are which.
- **Design** — forward-designed xschem schematics and SPICE netlist snapshots
  for the PLL blocks and a top-level closed-loop integration live in
  [`design/`](design/). Design values there are design-time targets or
  estimates; a result only counts once a `sim/` record backs it.
- **Simulation** — `sim/` holds PLL block and closed-loop testbenches, PVT
  corner sweeps, Monte Carlo campaigns, and the append-only records they
  produced, alongside the harness's own self-checks.
- **Layout** — `layout/` holds the `klt` DRC/LVS flow, a trivial proving cell,
  and a PLL layout record with its checking reports.
- **Rollup** — [`measurements/report.md`](measurements/report.md) is the
  machine-rendered per-spec-row rollup of the `sim/` and `layout/` evidence.
  It **records misses** (FAIL rows) as well as passes; the existence of
  evidence for a row is not the same as that row being ratified or met.
- **Silicon** — none. Nothing here has been fabricated or measured on
  silicon.

Evidence existing, a spec row being ratified, and a requirement being met are
three different things, and none of them means verification is complete.

**Where the block stands against the T1 evidence checklist is not settled by
this prose.** [`signoff/tier-report.json`](signoff/tier-report.json) is this
block's T1 verdict of record: machine-rendered by `klt signoff --manifest` from
`signoff/block-manifest.json` and re-checked in CI on every push, so it cannot
go stale silently. [`signoff/README.md`](signoff/README.md) states what each
met row does and does not say. No file in this repository hand-maintains a
parallel met/unmet checklist; if a sentence here or anywhere else claims this
block does or does not clear a T1 item, that report settles it. In particular,
a met row for the characterization report means only that
`measurements/report.md` is the artifact that item names; it does not mean any
spec row is met.

## Private for now

This repository is **private**. It is a design canary that binds under the 2AM
Logic invention firewall; whether and when it goes public is an **operator**
decision, not an agent one — the visibility flip is an operator action. Even so,
write every commit message, issue, and document here as if a stranger will read
it, because one day one may. Nothing about business positioning, commercial
terms, or the contents of other 2AM Logic repositories belongs in this one.

## Repository layout

```
spec/          target spec (partially ratified) + numbered decision records (DR-NNN)
design/        xschem schematics/symbols + SPICE netlist snapshots (PLL blocks + top-level integration)
sim/           PVT corner harness, PLL block and closed-loop testbenches, append-only evidence records
layout/        klt-driven DRC/LVS flow, a trivial proving cell, and a PLL layout record with checking reports
measurements/  per-spec-row report aggregator and its rendered report (rolls up sim/+layout/ evidence); silicon characterization slot, empty until there is silicon
docs/          environment setup, plus docs/t1-gap.md — a pointer to signoff/ (the graded T1 verdict) and the detailed read of T1 item 11
signoff/       block manifest + machine-rendered T1 tier verdict (`klt signoff --manifest`), re-checked in CI
```

Start with `spec/target-spec.md` for *what is being targeted, which rows are
ratified, and which are still DRAFT*, and `sim/README.md` / `layout/README.md`
for *how results are recorded and how to reproduce them*.

## How verification works here

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
