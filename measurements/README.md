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
- **Not a PLL result yet.** No PLL schematic, testbench, or layout exists
  in this repo yet (see #14), and `spec/target-spec.md` has no ratified
  numeric row (row 0, the supply flavor, is the only ratified row — see
  `DR-001`, #1). The current `measurements/report.md` rolls up only the
  harness-plumbing evidence from issue #2 (`sim/pdk-smoke`,
  `layout/trivial-cell`) — real per-spec-row PLL evidence is a follow-on,
  once #14/#19 give it something to report against.

## Running it

```bash
python3 measurements/aggregate.py --out measurements/report.md   # markdown (default)
python3 measurements/aggregate.py --format json                  # JSON, to stdout
```

Standard library only (same "no extra runtime dependency" convention as
`sim/run_corners.py` / `layout/bin/render-record.py`). No PDK, ngspice,
xschem, or `klt` required — it only reads already-committed `.md` files.

## Report format

One markdown table, one row per `spec/target-spec.md` entry (`#` 0–18 as of
this writing):

| Row | Parameter | DRAFT target | Evidence | Verdict | Citation |
|---|---|---|---|---|---|

- **Row / Parameter / DRAFT target** — read straight from
  `spec/target-spec.md`'s summary table (its `#`, `Parameter`, and `DRAFT
  target (starting point)` columns).
- **Evidence / Verdict / Citation** — one line per evidence record matched
  to that row (see "How a record gets matched to a row" below); a row with
  no matched record renders literally as `No evidence` rather than being
  silently dropped from the table.

A second section, **"Evidence found, not yet mapped to a spec row,"** lists
every current evidence record that *doesn't* cite a row — this is where
today's harness-plumbing records (`sim/pdk-smoke`, `layout/trivial-cell`)
show up, since neither makes a PLL spec claim. This section exists so the
aggregator never drops a record on the floor just because it predates the
citation convention below; it's also how you can see the rollup mechanism
actually found and parsed real evidence even before any record cites a row.

A closing **"Scan summary"** states how many records were scanned, how many
are current, and how many were excluded as superseded (see below) —
totals only, no per-record detail (that's the two tables above).

`--format json` emits the same information as a JSON object
(`rows: [...]`, `unmapped_evidence: [...]`, `scan_summary: {...}`) for
programmatic consumption instead of the markdown tables.

## How a record gets matched to a row

A `sim/` or `layout/` evidence record opts into appearing against one or
more `spec/target-spec.md` rows by adding a line anywhere in its body:

```markdown
- **Spec row(s)**: 8, 9
```

(comma-separated row numbers; the leading `- ` is cosmetic — the aggregator
matches `**Spec row(s)**: ...` wherever it appears). Neither
`render-record.py` (layout) nor `sim/harness/report.py` (sim) emits this
field today, and no record in this repo currently carries it — that's
deliberate: `spec/target-spec.md` has no ratified numeric row to cite yet,
and inventing a citation now would be exactly the "no fabricated evidence"
violation `sim/README.md` and `layout/README.md` both rule out. This is a
**forward-declared convention**: the first real PLL evidence record that
does cite a row is picked up automatically, with no aggregator change
required. A row number that doesn't exist in `spec/target-spec.md` is not
silently dropped either — it shows up in the "not yet mapped" section
instead of vanishing, so a typo'd citation is visible rather than lost.

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

Covers: `spec/target-spec.md` summary-table parsing, sim/layout
record-field extraction (record ID, claim, verdict, detail, the optional
spec-row citation, supersession), the current/superseded resolution rules
above, row-matching (including the "unknown row number surfaces, doesn't
vanish" edge case), and markdown/JSON rendering — plus one smoke test that
runs the real aggregator against this repo's actual checked-in
harness-plumbing evidence (`sim/pdk-smoke/records/`,
`layout/trivial-cell/reports/`) end to end.

## Provenance

Built for issue #22 (T1 item 8). No prior-art convention to port: gf180-pll
(this repo's sibling canary)'s own `measurements/` is likewise just a
`.gitkeep` placeholder — verified via the GitHub API during curation (see
#22's Curator enhancement) — so this format was designed from
`spec/target-spec.md`'s existing row structure and `sim/`/`layout/`'s
existing record schemas, not copied from a sister repo.
