# signoff/ — this block's gap to T1, graded rather than hand-read

`signoff/tier-report.json` is **this block's T1 verdict of record**. It is
machine-rendered by `klt signoff --manifest` from `signoff/block-manifest.json`
and re-checked in CI. Nothing in this repository hand-maintains a parallel
met/unmet checklist; if a sentence anywhere claims this block does or does not
clear a T1 item, the report is what settles it.

Today the verdict is **2 of 22 T1 rows met** — item 3 (DRC clean), once per
partition — and `tier: null`. Every other row is `unmet` with `reason:
"no_evidence"`. That is the correct, expected result for a block at this
repo's stated maturity (see the root `README.md`'s status section), and an
almost-entirely-`unmet` report is an honest machine-readable statement of the
gap. It is worth more than a prose checklist nobody re-reads, and it is the
reason this directory exists before the evidence does rather than after.

## Files

| File | What it is |
| --- | --- |
| `block-manifest.json` | The block manifest: this block's `block` name, its `kind`, and the evidence envelope cited per T1 item. Hand-edited; the only file here a human writes. |
| `tier-report.json` | `klt signoff --manifest … --format json` output. **Generated — do not edit.** Re-render with `bash signoff/run-signoff.sh`. |
| `run-signoff.sh` | Renders the report (`bash signoff/run-signoff.sh`) or verifies the committed one (`--check`, which is what CI runs), after two guards `klt signoff` does not apply itself (see "Two guards this repo adds"). |

## Reproducing

```sh
pip install 'klayout-tools==0.6.0'
bash signoff/run-signoff.sh --check    # verify the committed report
bash signoff/run-signoff.sh            # re-render it after changing the manifest
```

No PDK, no KLayout binary, and no layout input are needed: the grader only
reads committed JSON plus its own bundled checklist. The CI `checks` job runs
`--check` on every push and pull request. That is what stops this verdict from
rotting — see "Negative controls" below for the four ways it is demonstrated to
fail rather than rot.

Note the version skew this pin deliberately leaves visible: the **grader** is
`klt` 0.6.0, while the DRC envelope it grades was produced by `klt` 0.4.0 (the
pin in `layout/requirements.txt`, which moves on the layout flow's own
schedule). Both versions are recorded in the report — the grader's as `build`,
the envelope's inside the citation's own provenance — so the two pins never
have to be inferred.

## Block kind: `mixed-signal`, and the partition boundary

`kind: "mixed-signal"`, confirmed against this block rather than assumed: the
loop contains both a transistor-level analog signal path and a logic block
built entirely from PDK standard cells. The checklist requires a mixed-signal
claim to state its partition boundary explicitly, so a reviewer can tell which
evidence covers which silicon. The boundary is exactly the standard-cell
boundary, and it is machine-visible in the netlists (`grep -l sky130_fd_sc_hd
design/*/netlist/*.spice` returns the divider and the top-level integration
netlist that instantiates it, and no other block):

- **Digital partition** — the programmable integer-N feedback divider,
  `design/divider/divider_intN.sch` (netlist
  `design/divider/netlist/divider_intN.spice`), whose every gate is an
  instance of a `sky130_fd_sc_hd` standard cell.
- **Analog partition** — everything else: the ring-oscillator VCO
  (`design/vco/vco_ring5.sch`), the tri-state PFD and charge pump
  (`design/pfd-cp/pfd_cp.sch`, which draws its own logic at transistor level
  rather than from the cell library), and the passive loop filter
  (`design/loop-filter/loop_filter.sch`).

The digital partition is **not an RTL flow**: there is no RTL source, no
synthesis step, and no place-and-route — the divider is hand-captured as an
xschem schematic that instantiates library cells, and its layout is those
cells abutted in one row by `layout/bin/pll_layout.py`. The checklist's
"full-custom digital sub-case" is written for the case where no compatible
open standard-cell library exists; here one does exist and is used, and only
the RTL/synthesis/P&R half is absent. The consequence for grading is the same
either way — items 1, 2, 5 and 11 for this partition will be satisfied by the
Analog column's artifacts (schematic + netlist, drawn GDS, SPICE PVT sweeps),
not by `klt sta`/`klt functional-verification`/`klt place-and-route` outputs
this repo has no flow to produce — but the *reason* differs from the sub-case
as written, so it is stated here rather than borrowed.

## The one met row: item 3, and what it does and does not say

Item 3 cites
`layout/pll/reports/20260906-195205-4a08c71/drc.json` — the DRC envelope of
the record `layout/pll/reports/LATEST` currently names — with its input pinned
to `sha256:939f97e05b9e4a2a0f866a44bb6f758c030cfd611eaa0a567d5dc3002fa68d4c`,
which is the SHA-256 of `pll_top.gds` committed in that same record directory
(re-hashed on every run, see "Two guards this repo adds"). It is cited once,
with a kind-independent `"3"` key, so it grades both partitions' rows: the
stream it ran on is the composed `pll_top` cell, which contains both
partitions' devices.

Item 3 requires the deck's coverage gaps to be **enumerated in the claim** —
`klt signoff` reports them beside the row but explicitly does not grade them,
so a `met` verdict is not evidence that they were disclosed. Quoted verbatim
from the cited envelope's own `coverage` block:

- **`deck_scope`** (17) — the chapters of the sky130 DRM this deck transcribes
  at all: `cap2m`, `capm`, `ct`, `difftap`, `li`, `licon`, `m1`, `m2`, `m3`,
  `m4`, `m5`, `nwell`, `poly`, `via`, `via2`, `via3`, `via4`. Everything else
  in the DRM — density, antenna, latch-up, ESD, seal ring, and the rest — is
  outside what "clean" was measured inside.
- **`layers_in_stream_without_rules`** (17) — layers this stream draws that
  the deck has no rule for: `64/5`, `64/16`, `64/59`, `66/13`, `67/5`,
  `67/16`, `68/5`, `68/16`, `78/44`, `79/20`, `81/4`, `83/44`, `93/44`,
  `94/20`, `95/20`, `122/16`, `236/0`.
- **`rules_skipped`** (29) — rules the deck carries that this run did not
  evaluate, because a layer they read is absent from this stream:
  `capm.enclosing.via3.1`, `capm.separation.via3.1`, `capm2.enclosing.via4.1`,
  `capm2.separation.via4.1`, `capm2.space.1`, `capm2.width.1`,
  `met1.enclosing.via.1`, `met2.enclosing.via.1`, `met2.enclosing.via2.1`,
  `met2.space.1`, `met2.width.1`, `met3.enclosing.via2.1`,
  `met3.enclosing.via3.1`, `met4.enclosing.capm2.1`, `met4.enclosing.via3.1`,
  `met4.enclosing.via4.1`, `met4.space.1`, `met4.width.1`,
  `met5.enclosing.via4.1`, `met5.space.1`, `met5.width.1`, `via.space.1`,
  `via.width.1`, `via2.space.1`, `via2.width.1`, `via3.space.1`,
  `via3.width.1`, `via4.space.1`, `via4.width.1`.

**Read that third list against `layout/pll/README.md`'s "Not routed"**: every
skipped rule is a via or upper-metal (or MiM-capacitor) rule, and those layers
are absent precisely because the shipped stream carries no inter-device
routing. Only 9 of the deck's 17 layers were checked at all. So the honest
reading of this row is: *the composed PLL stream is clean of every rule this
deck could evaluate on an unrouted layout* — not "this block's finished layout
is DRC clean". Drawing the routing will re-open 29 rules that have never run
against this design, and the row can legitimately go red when it does. That is
the expected direction of travel, not a regression to be argued away.

Two further disclosures that belong with the claim:

- The deck is `klt`'s own curated `sky130` deck, pinned by content hash
  (`sha256:5afac7ab8561545859f5e2e74f4621c6ffc052756dc8fe344ea263398e96b240`),
  and the envelope records `released: false` for it — `klt`'s deck-history
  lookup did not confirm that this deck revision ships in any released
  `klayout-tools` version. It is not a foundry signoff runset, and this row
  is not a foundry signoff result.
- `coverage.voltage_domain_warnings` is empty, which is the expected result
  for a 1.8 V core-device-only design (DR-001).

## Why every other row is `unmet`

All 20 remaining T1 rows render `reason: "no_evidence"` — the manifest cites
nothing for them. That single machine code covers five materially different
situations, and the difference is the point of this section.

**1. The artifact exists, but not as a `klt` JSON envelope.** The `sim/`
campaigns under `sim/*/records/*.md` are this repo's own Markdown-plus-raw-log
record format, produced by `sim/run_corners.py`, not by `klt sim`. `klt
signoff` grades envelopes, so none of that evidence is citable as it stands.
This bears most directly on item 5.

**2. The artifact does not exist yet.** No LVS-clean result exists for the
shipped stream (item 4 — the stream is unrouted, so no `klt lvs` run is
attempted against it; the routed spot-check under the same record's
`route-spot-check/` reports a large, honest mismatch, and it is a *different*
build from the one item 3 cites, so citing it here would be citing the wrong
artifact for the claim as well as a failing one; closure is issue #18). There
is no Monte Carlo campaign (item 6, issue #20), no `klt pex` run (item 7,
issue #21), no aggregated PLL characterization report (item 8, issue #22 —
`measurements/report.md` exists but rolls up harness-plumbing evidence only,
not per-spec-row PLL performance, so a `generic` envelope asserting `pass` over
it would be a false claim). Item 5 additionally needs a
ratified spec: `spec/target-spec.md` is DRAFT with only row 0 ratified
(DR-001), so a corner verdict against it is provisional by construction.

**3. The tool cannot check what the item claims, and we decline to game it.**
Items **1** (design sources), **2** (layout), **9** (testbenches shipped) and
**10** (repo hygiene) have no `klt` verb behind them. `klt signoff` grades them
on whether *some* passing envelope was cited at all, not on whether the cited
evidence has anything to do with the claim — the one clean DRC report this repo
owns, cited four more times, would render four more `met` rows and the tool
would have no basis to object. This repo cites nothing for them. All four have
real artifacts behind them (committed schematics and netlist snapshots under
`design/`; a committed, reproducibly-generated `pll_top.gds`; a testbench per
`sim/*/testbench/`; this repo's READMEs, spec table, license and CI), and
turning those into green rows would still mean citing evidence that does not
support them. A row that goes green for the wrong reason is worse than a red
one.

**4. A real, clean `klt` envelope exists — and still does not answer the whole
item.** Item **11** (power delivery, structural) is the one row where a
citable envelope already sits in this repo: `layout/pll/erc-supply-spec.json`
and the `klt erc --format json` report under `layout/pll/erc-reports/LATEST`,
which reports `status: "clean"`, `erc_finding_count: 0`, pinned by content hash
to the same `pll_top.gds` item 3 cites. It establishes **two of item 11's three
rules** — one electrical island per declared supply, and no supply short. The
third, `erc.missing_tie`, is **not computed**: the spec declares no `ties[]`,
because declaring one collapses a standard-cell layout into a single island and
reports a false supply short
([klayout-tools#2169](https://github.com/2AMLogic/klayout-tools/issues/2169)),
and `klt erc`'s own contract is that an omitted `ties[]` means the rule never
runs — so the zero in that report is an absence of evidence, not evidence of
absence. The declared supplies also cover one block of four: `VPWR`/`VGND` are
the `sky130_fd_sc_hd` cells' own power pins and come entirely from the
divider's abutted cell row, while the three custom-drawn analog blocks carry no
supply labels and no rails at all because the layout is unrouted (issue #156,
open). Citing that envelope would render item 11 green on two thirds of a
claim — the same trade §3 declines, so it is declined here too. The full read
is `docs/t1-gap.md` § "Item 11 in detail"; #147, which asked for the spec and
the report, is closed because they now exist.

When #156 closes and the tie rule can actually run, item 11 is the next row to
cite — and citing it is not a one-line manifest edit. Guard 2 below matches
`layout/<dir>/reports/<record-id>/…` literally; a citation under the sibling
`layout/pll/erc-reports/…` tree does not match that pattern and would be
silently skipped, leaving the new citation with no superseded-record check at
all. Extending the pattern is part of the work of citing item 11, not a
follow-up to it.

**5. The item is a per-partition row whose column this repo cannot produce
yet.** The digital partition's items 1, 2, 5 and 11 will be answered by the
Analog column's artifacts (see "Block kind" above), which do not exist as
envelopes either — not by RTL-flow artifacts. Nothing is being withheld here
that a synthesis flow would have produced.

T2, T3 and T4 render as single ladder rows, always `unmet` with `reason:
"tier_not_supported"`: they need commercial signoff tools, fab access, or
production data, none of which this repo has a mechanism to check.

## Two guards this repo adds

`run-signoff.sh` runs two checks before rendering, because the grader's
freshness model leaves two doors open that matter for an append-only evidence
repo. Both are demonstrated below.

1. **The cited artifact is re-hashed.** `klt signoff` does re-hash a citation's
   input artifact when it can find it, and discloses the answer as the
   citation's `input_verified`. It cannot find this repo's: the layout flow's
   envelopes record the absolute path of the machine that produced them
   (`/Users/…/pll_top.gds`), and the grader resolves a path against the
   evidence file's own directory only when that path is *relative* — so this
   citation reports `input_verified: null` and `input: not re-hashed`, and the
   pinned hash is only ever compared to another claim. An edit to the committed
   `pll_top.gds` would then leave the envelope claiming the old hash, the pin
   matching it, and the row green. The guard resolves the artifact by basename
   beside the envelope in its own record directory and hashes it for real. The
   tool gap is tracked upstream as
   [klayout-tools#2340](https://github.com/2AMLogic/klayout-tools/issues/2340)
   (cross-confirmed from this repo, per `CLAUDE.md`'s friction protocol); this
   guard retires when that lands.
2. **The cited record must be the one `LATEST` names.** A pinned hash catches
   an artifact that *changed*; it cannot catch one that was *superseded*.
   `layout/` records are append-only, so a fresh flow run mints a new
   `reports/<record-id>/` and leaves the cited one byte-identical forever —
   the manifest would keep citing a report that is no longer the latest, the
   hash would keep matching, and item 3 (which asks for the **latest** `klt
   drc` report) would stay green against superseded evidence. The guard
   compares every cited `layout/<dir>/reports/<record-id>/…` path against
   `layout/<dir>/reports/LATEST`. That path shape is matched literally, and a
   cited path that does not match it is skipped rather than rejected — so a
   future citation under a differently-named sibling record tree (the live
   example is `layout/pll/erc-reports/`, item 11's, see §4 above) gets no
   superseded-record check until the pattern is widened to cover it.

## Negative controls

A gate that cannot fail is not a gate — the same discipline
`layout/trivial-cell/`'s injected-defect fixtures apply to the DRC/LVS flow.
All four properties were demonstrated against a scratch copy of the cited
record before this directory was committed:

| Injected fault | Result |
| --- | --- |
| A byte appended to `pll_top.gds` (the artifact moves under the pin) | guard 1 fails: `hashes to sha256:d563871e… but the manifest pins sha256:939f97e0…`, exit 1 |
| `layout/pll/reports/LATEST` re-pointed at a newer record (the citation is superseded) | guard 2 fails: `cites record 20260906-195205-4a08c71, but … LATEST names 20260907-000000-deadbee`, exit 1 |
| The envelope's own `provenance.input.content_hash` changed (it ran against a different revision than the claim) | `klt signoff` re-grades item 3 `unmet` / `stale_evidence`, `t1_met_count` 2 → 0, the committed report no longer matches, `--check` exits 1 |
| One field of the committed `tier-report.json` hand-edited | `--check` prints the diff (`"t1_met_count": 99` → `2`) and exits 1 |

## Why the checklist is not vendored here

The sibling canary `2AMLogic/gf180-pll` vendors a pinned copy of
`design-evidence-tiers.md` and passes `--tiers-doc`, because the `klt` release
available when it was written (0.5.0) bundled a **ten**-item checklist and T1
item 11 had landed upstream days earlier. That bridge is unnecessary here:
`klayout-tools` 0.6.0 bundles the eleven-item checklist, so this repo grades
against the copy inside the pinned wheel and vendors nothing. The report
records which document it used and pins its content
(`source_doc` plus `source_doc_content_hash`), so a checklist that changes
under a fixed `klt` pin is visible in the diff rather than silent.

Bump discipline, mirrored from `layout/requirements.txt`: pin an exact version,
never a floating release; state what the bump picks up; re-render the report
and **read the diff** — a row that changes colour across a `klt` bump is a
finding about the grader, not about this block.

## Provenance

Structure and much of the wording of `run-signoff.sh` and this README are
ported from the sibling canary `2AMLogic/gf180-pll`
(`signoff/run-signoff.sh`, `signoff/README.md` at commit `d85287d8`,
2026-09-20), per `CLAUDE.md`'s instruction to copy the proven patterns rather
than reinvent them and to record provenance where we do. The evidence, the
verdict, the partition boundary, the item-3 disclosure and the two guards are
this block's own.
