# sky130-pll — agent instructions

Design canary: an integer-N ring-oscillator PLL on the sky130 open PDK,
designed and verified by AI agents. A sky130 port of the sibling canary
`2AMLogic/gf180-pll` — same block, a second PDK, as a portability proof.
Apache-2.0.

- **PDK**: sky130 (open PDK). Open-source flow: xschem + ngspice for
  design/sim, klayout-tools (`klt`) for layout work. Install the PDK with
  `volare` and mirror the sky130 plumbing (`xschemrc`, `spiceinit`, the sky130
  `klt` decks) from `2AMLogic/sky130-bandgap` rather than reinventing it. The
  sky130 device menu is **not** gf180's: gf180-pll is built on 3.3 V I/O
  devices (`nfet_03v3`/`pfet_03v3`); the sky130 supply flavor — 1.8 V core
  (`nfet_01v8`/`pfet_01v8`) vs. a medium-voltage arrangement — is an **open
  question the spec must settle first** (see `spec/target-spec.md` and #1). Do
  not assume gf180's flavor or supply carries over.
- **Reverse-engineering-free.** This is a forward design from a ratified spec,
  not a part recovered from silicon or another netlist. Nothing here originates
  in reverse engineering, and nothing should.
- **Friction protocol (the canary's job)**: every time klayout-tools is
  awkward, missing a capability, or wrong for what you need, file an issue at
  `2AMLogic/klayout-tools` describing the tool gap **generically** — that
  tracker is scoped to the tool, so keep design-specific detail (this repo's
  spec values, its topology, its content) out of it and describe the gap, not
  the design. A tool issue that only makes sense to someone who has read this
  repo's spec is a bad tool issue.
- **Verification is the product**: no claim without a testbench. PVT corners on
  every recorded result. `sim/` results are append-only evidence — a re-run
  mints a new record that names the one it supersedes; records are never edited
  or deleted.
- **Spec changes go through `spec/` with a decision record.** Copy
  `spec/decision-records/TEMPLATE.md` to `DR-NNN-<slug>.md`, one decision per
  record. Agents **never relax a ratified spec to make results pass** — a
  result that misses the spec is recorded as a miss, and the spec is changed
  only by a decision record that argues the change on its own merits, not to
  launder a failing number.
- **Visibility / firewall**: this repo is **private for now** and binds under
  the 2AM Logic invention firewall. The flip to public is an **operator**
  action, never an agent one. Write every commit message, issue, and document
  as if a stranger will read it. Nothing about business positioning, commercial
  terms, or the contents of other 2AM Logic repositories belongs here.
- **Harness bootstrap**: seed the sim harness (PVT corner runner + testbench
  structure) from `2AMLogic/gf180-pll`, and the sky130 open-PDK flow (PDK
  install, `xschemrc`, `spiceinit`, sky130 `klt` DRC/LVS decks) from
  `2AMLogic/sky130-bandgap`. Copy the proven patterns rather than reinventing;
  record provenance (source repo, file, commit) where you do.

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.
<!-- END LOOM ORCHESTRATION -->
<!-- BEGIN REPO-SKILLS -->
This repository has [Repo Skills](https://github.com/rjwalters/repo) installed —
general repository hygiene and environment commands invoked as `/repo:<command>`. Run
`/repo:help` for the command list, or see `.claude/skills/repo/SKILL.md` for the full
guide. Hygiene commands apply safe, reversible fixes by default and report each
change; run with `--ask` to review first, and `--prune` to allow irreversible
removals. Managed by `install.sh` — edit outside the markers only.
<!-- END REPO-SKILLS -->
