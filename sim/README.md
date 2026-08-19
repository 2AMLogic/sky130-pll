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
  | `pdk-smoke` (`--mc`) | does the sky130 `MC_MM_SWITCH`/`MC_PR_SWITCH` statistical-sampling mechanism run this DUT to completion, seed by seed — the Monte Carlo harness's own plumbing self-test, not a PLL statistical-spec claim | #20 |
  | `pll` | does the four-block closed-loop PLL netlist (`design/top/top.sch` — VCO + PFD/charge pump + loop filter + divider) netlist and simulate to completion across a real process/temperature/supply sweep — the first PLL-specific campaign, still a plumbing claim (no `spec/target-spec.md` row is ratified yet, and the transient window is far short of the loop's cold-start lock time), not a lock-time, frequency, or jitter claim | #23 |
  | `pll-lock` | does the closed-loop PLL, driven cold-start from `design/top/top.sch`'s own power-on reset, lock its output to `N * Fref` within a real (multi-microsecond, not 200 ns) transient window — a measurement claim (output frequency, duty cycle, time-to-lock, or explicit no-lock), extracted via `sim/harness/measure.py` | #52 |
  | `vco` | frequency-vs-`VCTRL` characterization of `design/vco/vco_ring5.sch` alone (open loop, no PFD/charge pump/loop filter/divider), replacing the informal single-corner sanity check `design/vco/DESIGN.md` disclaims with real committed `sim/` evidence across the full PVT matrix | #52 |

  New campaigns add rows here as they are created; the list is descriptive,
  not a closed set.

- **`<record-id>`** — `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` (UTC), this
  repo's `HEAD` when the run started. Re-runs mint a new `<record-id>`;
  nothing under `records/` is ever edited in place. If the tree was dirty at
  run time, the record's **Environment provenance** field says so.

- **`<corner-id>`** — the naming convention depends on what mode produced the
  record, but both share the same `corners/<record-id>/` directory:
  - **PVT points**: `<corner>_<temp>c_<supply>v`, e.g. `ss_-40c_1.62v.log`,
    `tt_27c_1.80v.log`. Supply is written to two decimals.
  - **Monte Carlo trials** (`--mc`, see `sim/harness/README.md`'s Monte Carlo
    section): `mc<trial>_seed<seed>_<lib-corner>_<temp>c_<supply>v`, e.g.
    `mc001_seed1_tt_mm_27c_1.80v.log`. `<lib-corner>` is the `.lib` section
    actually netlisted against (the corner, with `_mm` appended when
    mismatch sampling is enabled).

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

## Monte Carlo evidence

`sim/run_corners.py <slug> --mc` (issue #20) runs a statistical-variation
campaign instead of a PVT sweep: many trials at one fixed PVT point, each
sampling sky130's own `MC_MM_SWITCH`/`MC_PR_SWITCH`-gated device variation
with a distinct ngspice RNG seed — see `sim/harness/README.md`'s Monte Carlo
section for the manifest schema and sampling mechanism. Records land in the
same `records/<record-id>.md` / `netlist-snapshots/<record-id>.spice` /
`corners/<record-id>/` tree a PVT record uses (same append-only/retention
rules apply); `sim/harness/report.render_mc` renders a trial table (trial,
seed, verdict, detail) and the campaign's sampling configuration (base
corner, temperature, supply, which switches were on, trial count and seed
range) in place of the PVT per-point matrix.

**This capability is scoped to the harness/methodology, not a PLL claim.**
`spec/target-spec.md`'s statistical-shaped rows (period jitter row 9,
reference spur row 10, supply sensitivity row 13) are DRAFT/unratified, and
there is no PLL netlist yet — an `--mc` record produced today (e.g.
`pdk-smoke`'s) is a harness plumbing check ("does the sky130 statistical-
sampling mechanism run this DUT to completion, seed by seed, with each seed
producing a distinct draw?"), not a statistical-spec measurement. The first
real PLL statistical-row record is a follow-up issue, once #14 (the PLL
design) exists and a targeted row is ratified.

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

  The recorded commit is the branch commit the run happened at, and a rebase
  or a squash-merge rewrites that hash — so a record written before its PR
  merged names a commit that no longer exists on `main`. Regenerate the
  record when that is cheap; otherwise read the recorded hash as "the tree
  this ran against", and rely on the fields that survive history rewriting
  for exact reproduction: the pinned PDK build, the tool versions, and the
  netlist snapshot's SHA-256.
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
