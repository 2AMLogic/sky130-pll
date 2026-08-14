# sim/ — evidence record format

This directory holds simulation testbenches and their results. Results are
**append-only evidence**: once a record is written, it is never edited or
deleted. A re-run — even one that corrects a mistake — mints a new record
with a new ID; a correction references the record it supersedes rather than
overwriting it in place.

This convention exists because `CLAUDE.md` commits this repo to two rules
that need a concrete schema to be enforceable:

- **Verification is the product.** No claim without a testbench.
- **`sim/` is append-only evidence.** Re-runs get new records; records are
  never edited or deleted.

## Provenance of this convention

Adapted from `2AMLogic/gf180-pll`'s `sim/README.md`
(source commit `d6115c79f9d41140341c4666256b659151a824db`), which itself
adapts the convention `2AMLogic/gf180-bandgap` ratified. Per this repo's
`CLAUDE.md` harness-bootstrap rule (copy the sister-repo pattern rather than
reinventing).

**Scoped down for issue #2.** gf180-pll's version documents an entire mature
PLL verification campaign table (lock-time, jitter, divider-ratio, ...) —
none of that exists here yet. This file keeps the schema and the
append-only/retention/no-fabricated-evidence rules gf180-pll ratified, and
drops the campaign-specific sections (closed-loop assembly paths, the PFD
internal-timestep bound, etc.) that do not apply until there is a PLL
schematic. Those return, adapted, when the campaigns that need them land.

## Directory / naming convention

Each testbench topic gets its own experiment directory:

```
sim/
  <experiment-slug>/                 # e.g. pdk-smoke
    testbench/                       # tb.json manifest + xschem schematic(s)
    netlist-snapshots/
      <record-id>.spice              # frozen DUT netlist used for this record
    corners/
      <record-id>/
        <corner-id>.spice            # patched per-point netlist
        <corner-id>.log              # raw ngspice output per PVT point
    records/
      <record-id>.md                 # append-only summary record
```

- **`<experiment-slug>`** — short, descriptive, kebab-case name for what is
  being verified. One directory per distinct claim, not per run.

  | Slug | Claim under test | Issue |
  |---|---|---|
  | `pdk-smoke` | does xschem+ngspice+sky130 run this DUT to completion across a real process/temperature/supply sweep — the harness's own plumbing self-test, not a PLL design claim | #2 |

  New campaigns add rows here as they are created; the list is descriptive,
  not a closed set. The first PLL-specific campaign lands with whichever
  issue first needs `design/`'s schematic to exist.

- **`<record-id>`** — `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` (UTC), this
  repo's `HEAD` when the run started. Re-runs mint a new `<record-id>`;
  nothing under `records/` is ever edited in place. If the tree was dirty at
  run time, the record's **Environment provenance** field says so.

- **`<corner-id>`** — `<corner>_<temp>c_<supply>v`, e.g. `ss_-40c_1.62v.log`,
  `tt_27c_1.80v.log`. Supply is written to two decimals.

- **`testbench/`** is not versioned per record — it holds the current
  testbench manifest/schematic used to generate records. A testbench change
  that could affect comparability across records is noted in the next
  record's summary.

## Default corner matrix

Unless a record states otherwise, a result is swept over the grid its own
`tb.json` manifest declares — see `sim/harness/README.md`. `sim/pdk.json`
pins the process-corner names the installed sky130 PDK actually defines
`.lib` sections for (`tt`, `ss`, `ff`, `sf`, `fs`, plus the passive-only `ll`/
`hh` axis); a manifest's `process_corners` must be a subset of that list.

**This repo has no ratified supply flavor yet (#1, `DR-001` — `proposed`).**
A testbench manifest's `supply_nominal`/`supply_tolerance` are that
testbench's own bias, not a spec claim, until #1 ratifies row 0/1 of
`spec/target-spec.md`. Nothing in this harness reads a spec value or gates
pass/fail on one: the corner matrix comes from each manifest, and the
per-point criterion is "did the simulator complete this point". Once #1
ratifies, PLL campaigns state their corner matrix against the ratified
supply range the same way gf180-pll states its 3.3 V ±10 % grid, and cite
the ratifying `DR-NNN` in their records.

Any subset of a manifest's default grid (fewer temperatures, one supply, a
single process corner) is allowed **only** with an in-record justification —
`sim/run_corners.py`'s `--subset-reason` flag is mandatory whenever a
`--corners`/`--temps`/`--supply-tol` override is combined with `--write`, and
its text becomes part of the record. "The sim was slow" is not a
justification; "fast selftest pass proving the harness runs, not a design
claim — see sim/pdk-smoke/records/<id>.md for the full grid" is.

## Summary record format

Each run produces one `records/<record-id>.md` file (see `sim/harness/
report.py`) with these mandatory fields:

- **Record ID** — matches the filename and the corresponding
  `netlist-snapshots/`/`corners/` subdirectory.
- **Claim** — what this record substantiates, taken from the manifest's own
  `claim` field. Until #1 ratifies the spec, no record here can state a
  `spec/target-spec.md` claim (there is nothing ratified to check against
  yet) — every record's claim is a plumbing or design-input claim.
- **Netlist provenance** — schematic path plus the SHA-256 of the frozen
  `netlist-snapshots/<record-id>.spice`.
- **Environment provenance** — PDK variant + pinned open_pdks hash, model
  library file, ngspice/xschem versions, this repo's git commit and whether
  the tree was dirty, host OS/arch. "Dirty" means *the code that produced
  this evidence differed from the named commit*: the record's own outputs
  (its corner logs, its netlist snapshot, the record file itself) are
  excluded from that check, since a run always creates them and counting
  them would mark every record dirty. An uncommitted edit to the harness or
  to the testbench does still mark it dirty.
- **Corner matrix run** — the explicit (process corner, temperature, supply)
  points actually executed, and whether it is a declared subset of the
  manifest's default grid.
- **Methodology / criteria / limitations** — the pass/fail criterion applied
  per point, and any known gap in what the record can support.
- **Result** — per-point pass/fail table plus an overall verdict.
- **Links** — testbench, netlist snapshot, raw per-point logs.
- **Timestamp / author** — UTC creation time and who (human or agent) ran it.
- **Supersedes** (optional) — the prior `<record-id>` this record supersedes.

### Status / supersession language

A record's standing is **`current`** or **`superseded by <record-id>`**,
derived rather than stored: `Status` is not itself a record field. The
superseding record carries **Supersedes**; the superseded record is never
edited to add a back-reference — read forward to find what superseded it.

## Append-only rule

`records/*.md`, `netlist-snapshots/*.spice`, and `corners/<record-id>/*` are
written once and never edited or deleted after creation, even to fix a typo.
A correction is a new record naming the one it supersedes. Only `testbench/`
and this README are mutable.

## Retention policy

| Artifact | Retained? | Why |
|---|---|---|
| Summary record (`records/<id>.md`) | **Always, committed** | the citable evidence object |
| Frozen netlist snapshot (`netlist-snapshots/<id>.spice`) | **Always, committed** | the record's claim is meaningless without the exact DUT |
| Raw per-point ngspice logs (`corners/<id>/*.log`) | **Always, committed** | the primary evidence the pass/fail table was read from |
| Per-point patched netlists (`corners/<id>/*.spice`) | **Always, committed** | reproduces exactly what ngspice ran at that point |
| Full waveform rawfiles (`.raw`) | **No, not committed** | regenerable from the frozen netlist + logged environment |

Root `.gitignore` ignores `*.raw` and `*.log` tree-wide; a scoped negation
un-ignores exactly the evidence path:

```gitignore
*.raw
*.log
!sim/*/corners/**/*.log
```

**Nothing is pruned.** Old records stay after they are superseded.

## No fabricated evidence

Files under `sim/<experiment-slug>/` may only be created by an actual run of
an actual testbench. Do not commit an example, a template, or a
plausible-looking record into evidence position.

The first real testbench is `pdk-smoke` (#2) — see
`sim/pdk-smoke/records/` for the current evidence. Every campaign added
after it follows this same convention.
