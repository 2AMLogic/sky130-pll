# measurements/ — aggregated characterization report

Stood up by the sim-harness bootstrap issue (#2) as an empty placeholder
("silicon characterization, empty until there is silicon" — see the root
`README.md`). Issue #22 (T1 item 8) adds the piece that was actually
missing before silicon exists: a **rollup report/aggregator** that walks
this repo's existing `sim/`/`layout/` evidence and presents it one row at a
time against `spec/target-spec.md`. It does not change what
`measurements/` is *for* long-term (post-silicon characterization still
lands here) — it gives that eventual data a report format to land into, and
makes the format checkable now, against the harness-plumbing evidence that
already exists.

## What this is not

- **Not a new evidence trail.** `measurements/aggregate.py` never
  simulates, extracts, measures, or invents anything — it only reads the
  append-only records already committed under `sim/*/records/*.md` and
  `layout/*/reports/*/record.md` and restates what they already say. If you
  want to add or correct evidence, add a `sim/`/`layout/` record per those
  directories' own README, then re-run the aggregator.
- **Not itself append-only.** `measurements/report.md` (the checked-in
  output of the last aggregator run) is a *derived* artifact — regenerate
  and recommit it whenever new evidence lands; there's no supersession
  chain to maintain for it the way `sim/`/`layout/` records have one for
  themselves.
- **Not a ratified PLL result.** `spec/target-spec.md` has ratified rows 0,
  1, 19 and 20 (`DR-001`/`DR-002`/`DR-003`) and **no ratified numeric
  performance row at all**. Every row a record now appears against is still
  DRAFT, so a populated row means "measured evidence bearing on this row
  exists", never "this row passes" and never "this row is settled".
  Ratification remains a separate decision-record act argued on its own
  merits (`CLAUDE.md`), and nothing the aggregator prints substitutes for
  it.

## Running it

```bash
python3 measurements/aggregate.py --out measurements/report.md   # markdown (default)
python3 measurements/aggregate.py --format json                  # JSON, to stdout
```

Standard library only (same "no extra runtime dependency" convention as
`sim/run_corners.py` / `layout/bin/render-record.py`). No PDK, ngspice,
xschem, or `klt` required — it only reads already-committed `.md` files.

## Report format

One markdown table, one row per `spec/target-spec.md` entry (`#` 0–20 as of
this writing):

| Row | Parameter | DRAFT target | Evidence | Verdict | Citation |
|---|---|---|---|---|---|

- **Row / Parameter / DRAFT target** — read straight from
  `spec/target-spec.md`'s summary table (its `#`, `Parameter`, and `DRAFT
  target (starting point)` columns).
- **Evidence / Verdict / Citation** — one line per evidence record matched
  to that row (see "How a record gets matched to a row" below); a row with
  no matched record renders literally as `No evidence` rather than being
  silently dropped from the table. The Citation cell names the record, and
  adds `-- rows via <declaration>` when the mapping came from the
  experiment's declaration rather than the record's own line (see "Records
  that predate the convention").

A second section, **"Evidence found, not mapped to a spec row,"** lists
every current evidence record that resolves to no `spec/target-spec.md` row
— harness plumbing (`sim/pdk-smoke`, `sim/pll`), the layout flows, and
anything whose citation is a typo or missing. Its **Why unmapped** column
distinguishes the healthy case ("declares it measures no spec row") from the
two gaps ("no spec-row declaration found", "malformed …"). This section
exists so the aggregator never drops a record on the floor.

A closing **"Scan summary"** states how many records were scanned, how many
are current, how many were excluded as superseded (see below), and where
each current record's citation came from — including a count of current
records with no declaration at all, which should always be zero and is
asserted so in CI.

`--format json` emits the same information as a JSON object
(`rows: [...]`, `unmapped_evidence: [...]`, `scan_summary: {...}`) for
programmatic consumption instead of the markdown tables.

## How a record gets matched to a row

A `sim/` or `layout/` evidence record appears against one or more
`spec/target-spec.md` rows by carrying a line anywhere in its body:

```markdown
- **Spec row(s)**: 8, 9
```

(comma-separated row numbers first; the leading `- ` is cosmetic — the
aggregator matches `**Spec row(s)**: ...` wherever it appears, and reads the
digits immediately after the colon, so explanatory prose may follow them but
never precede them). A record that measures no spec row says so in the same
place, explicitly:

```markdown
- **Spec row(s)**: none -- harness plumbing; measures no spec/target-spec.md parameter
```

**Both forms are emitted by construction, not written by hand.** Issue #152
found this convention documented and adopted by *zero* records — which is
what a convention that depends on an author remembering it decays to. The
citation is therefore declared once per experiment, in the one file per
experiment that is *mutable*:

| Tree | Where the declaration lives | Who stamps it into the record |
|---|---|---|
| `sim/` | `sim/<slug>/testbench/tb.json` → `"spec_rows": [6, 7]` | `sim/harness/report.py` (via `sim/harness/cli.py`) |
| `layout/` | `layout/<block>/spec-rows.json` → `{"spec_rows": []}` | `layout/bin/render_common.py` (via both `render-*.py`) |

`spec_rows` is **required**, and `sim/run_corners.py` refuses to run an
experiment whose manifest omits it — before it resolves the PDK or simulates
a single point, so a forgotten declaration costs a second, not a corner run.
`"spec_rows": []` (this experiment measures no spec row) additionally
requires a `spec_rows_note` arguing why: "measures none" is a claim, and is
never confusable here with "nobody thought about it".

### Records that predate the convention

`sim/` and `layout/` records are **append-only** — `sim/README.md` is
explicit that a record is "written once and never edited or deleted after
creation, even to fix a typo". Records minted before this convention existed
therefore cannot be retro-fitted with the line, and this repo does not try
to: for those, the aggregator resolves the citation from the owning
experiment's declaration above and says so in the report (`-- rows via
sim/<slug>/testbench/tb.json` in the citation cell, plus a count in the scan
summary). A record's own line always wins over the declaration when it has
one, so this is a shrinking legacy path rather than a second convention:
every record minted from here on carries its own line and never reaches it.

### Typos and gaps stay visible

A row number that doesn't exist in `spec/target-spec.md` is not silently
dropped — it shows up in the "not mapped" section with the rows it cited,
so a typo'd citation is visible rather than lost. So is a record whose
citation line is neither row numbers nor an explicit `none` (reported as
`malformed`), and a record with no declaration from either source (reported
as `no spec-row declaration found`). The last of those is a CI failure, not
just a report annotation — see "Testing" below.

### What a populated row does and does not mean

A record listed against a row is **evidence bearing on that row** — the
measured input a future decision record would argue the row from. It is not
a verdict on the row, and it is not ratification: per `CLAUDE.md`,
ratification is a separate decision-record act argued on its own merits, and
only rows 0, 1, 19 and 20 are ratified today. Nor is the `Verdict` column a
spec pass: it is each record's own overall pass/fail, which for several
campaigns means "the harness ran and recorded what happened", recorded
non-lock included.

## Current vs. superseded evidence

Both `sim/` and `layout/` are append-only — old records are never deleted,
so a naive scan would show every historical record for a claim, not just
the live one. The aggregator resolves "current" the same way each tree
already defines it, rather than inventing a third convention:

- **`sim/` records**: a record is superseded if some other record in the
  same experiment names it in that other record's own `**Supersedes**`
  field (`sim/README.md`'s "Status / supersession language").
- **`layout/` records**: a record is superseded if it is not the one named
  by its block's `reports/LATEST` pointer file (`layout/README.md`'s
  directory-layout convention). A block with no `LATEST` file is treated as
  having no superseded records (nothing to compare against).

Superseded records are excluded from the per-row and "not yet mapped"
tables but are still counted in the scan summary — the append-only history
under `sim/`/`layout/` itself is unaffected either way; this only changes
what the *report* highlights as current.

## Testing

```bash
python3 -m unittest discover -s measurements/tests -v
```

`test_aggregate.py` covers: `spec/target-spec.md` summary-table parsing,
sim/layout record-field extraction (record ID, claim, verdict, detail, the
spec-row citation and where it resolved from, supersession), the
current/superseded resolution rules above, row-matching (including the
"unknown row number surfaces, doesn't vanish" edge case), and markdown/JSON
rendering — plus one smoke test that runs the real aggregator against this
repo's actual checked-in evidence end to end.

`test_spec_row_citations.py` is the CI guard against this convention
decaying again (it runs in `npm run check:ci` with everything else under
`measurements/tests/`). Over the **real** tree it asserts that:

1. every `sim/*/testbench/tb.json` declares `spec_rows` (with a
   `spec_rows_note` whenever it is empty),
2. every `layout/<block>/` that has a `reports/` tree declares the same in
   `spec-rows.json`,
3. every declared row number is a real row of `spec/target-spec.md`,
4. no manifest hand-writes a `**Spec row(s)**:` line into its `claim` (or
   another prose field) — a prose copy precedes the rendered bullet and
   would shadow the declaration it duplicates, and
5. no **current** (non-superseded) evidence record resolves to no citation
   at all.

It deliberately does *not* require a non-empty row set — plumbing records
and negative controls measure no spec row, and saying so explicitly is the
right answer for them — and it never asks for an append-only record to be
edited.

## Provenance

Built for issue #22 (T1 item 8). No prior-art convention to port: gf180-pll
(this repo's sibling canary)'s own `measurements/` is likewise just a
`.gitkeep` placeholder — verified via the GitHub API during curation (see
#22's Curator enhancement) — so this format was designed from
`spec/target-spec.md`'s existing row structure and `sim/`/`layout/`'s
existing record schemas, not copied from a sister repo.
