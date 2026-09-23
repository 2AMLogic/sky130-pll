# Gap to T1

An index of where each `klayout-tools`
[`docs/design-evidence-tiers.md`](https://github.com/2AMLogic/klayout-tools/blob/main/docs/design-evidence-tiers.md)
**T1 checklist** item's evidence and tracking issue live for this block, and
what is still missing.

**This is a hand-read index, not a graded verdict.** It deliberately does not
mint per-item PASS/FAIL tokens — the authoritative, machine-read grading is
`klt signoff --manifest` against a committed block manifest, which this repo
does not have yet (**issue #148**). When that lands, its `tier-report.json`
becomes the verdict of record and this file becomes a pointer to it. Until
then, the "Evidence on record" column is what a reader should go check for
themselves, and the "Tracking" column is where the remaining work is.

The checklist has **eleven** items. It grew its eleventh — *Power delivery
(structural)* — on **2026-09-17** (klayout-tools#2025). Any "gap to T1" read
of this block taken before that date was taken against a ten-item checklist
that no longer exists.

This block's kind for checklist purposes is **analog** (a custom-drawn,
device-level PLL; there is no RTL, no synthesis, and no `klt place-and-route`
run anywhere in this repo), so the Digital column's extra requirements —
`power.pdn`, `power.tapcell_master`, `power.straps[]`, and an LVS
`power_connectivity` verdict — do not apply. The Analog column does.

| # | T1 item | Evidence on record | Still missing | Tracking |
|---|---|---|---|---|
| 1 | Design sources | `design/` — four block schematics + `design/top/top.sch`, each with a committed SPICE netlist snapshot (`design/top/netlist/top.spice`) | — | #15 (closed) |
| 2 | Layout (GDS/OASIS) | `layout/pll/reports/LATEST` → `pll_top.gds`, a device-level floorplan of all four blocks | **Not routed** — no inter-device interconnect is drawn | #16 (closed) |
| 3 | DRC clean | Same record's `drc.json`: `status: "clean"`, `violation_count: 0`, deck `sky130` | Deck-coverage disclosure not stated in a claim yet | #17 (closed) |
| 4 | LVS clean | Same record's routing spot-check `klt lvs` run (`layout/pll/reports/LATEST` → `route-spot-check/lvs.json`): `mismatch`, 1179 mismatches, 0/90 reference nets matched (474 nets in the layout) | A matching LVS compare; blocked behind routing | **#18 (open)** |
| 5 | Full corner verification vs. a ratified spec | `sim/` PVT campaigns (`sim/divider-*`, `sim/pll-lock`, `sim/vco`) on the DR-003 corner set | Most `spec/target-spec.md` rows are still unratified, so most claims have no bound target (DR-002) | **#151 (open)**, #19 (closed) |
| 6 | Monte Carlo / yield | none | The whole methodology | **#20 (open)** |
| 7 | Post-layout (PEX) | none | Blocked on `klt pex` upstream | **#21 (open)** |
| 8 | Characterization report | `measurements/` aggregator (#22's tooling) | Zero evidence records carry the **Spec row(s)** citation the aggregator matches on, so the report is empty by construction | **#22 (open)**, **#152 (open)** |
| 9 | Testbenches shipped | `sim/` testbenches + `sim/README.md`'s cold-start invocation; PDK pinned in `sim/pdk.json` (`open_pdks` `c6d73a3`) | — | #23 (closed) |
| 10 | Repo hygiene | `README.md`, `spec/target-spec.md`, `LICENSE` (Apache-2.0), `.github/workflows/ci.yml` | `README.md`'s status section is stale — it still describes the repo as pre-layout | — |
| 11 | **Power delivery (structural)** | `layout/pll/erc-supply-spec.json` + `layout/pll/erc-reports/LATEST`: one electrical island per declared supply, no supply short — produced by this repo's pinned `klt` since #157 | Three separate gaps — see below | **#147**, **#156 (open)**, #18, #157 (closed) |

## Item 11 in detail

Added to the checklist 2026-09-17 (klayout-tools#2025). It is the
**structural** power-delivery question — *is the supply connected to what it
powers* — graded from a `klt erc` supply-spec run. IR drop and
electromigration (`klt power`) are the *analysis* question and stay
deliberately outside it.

**What is on record** (issue #147):

- [`layout/pll/erc-supply-spec.json`](../layout/pll/erc-supply-spec.json) —
  the supply spec, with every layer/datatype resolved from the sky130A PDK's
  own `sky130A.lyp` **and** cross-checked against klayout-tools' curated
  sky130 deck layer table, and an inline justification for each `stackup`
  entry and each `label_layer`.
- [`layout/pll/erc-reports/`](../layout/pll/erc-reports/) — the committed
  `klt erc --format json` report, content-hash-pinned to both the layout and
  the spec it was run against.

**What that run establishes**: `VPWR` → exactly one electrical island,
`VGND` → exactly one, zero `erc.unconnected_net`, zero `erc.supply_short`.
Two of item 11's three rules.

**What is still missing, and why item 11 is NOT met:**

1. **`erc.missing_tie` is NOT COMPUTED.** The spec declares no `ties[]`,
   because declaring one collapses a real standard-cell layout into a single
   island and reports a false `erc.supply_short` (klayout-tools#2169;
   reproduced in `gf180-drone-fc`'s FRICTION F-034). Per `klt erc`'s own
   contract, omitting `ties[]` means the rule never runs — the zero count in
   the committed report is an **absence of evidence, not evidence of
   absence**. Nothing stands in for it here: `tap.drawing` (65/44) has zero
   shapes in the layout, there is no `power.tapcell_master` (no
   `klt place-and-route` run exists), and the only `klt lvs` result is a
   `mismatch`.
2. **The Analog column also requires item 4's LVS report to have carried the
   supply nets in its `net_correspondence`.** That is issue #18, and this
   repo's only LVS result is a `mismatch`.
3. **The declared supplies cover one of four blocks.** `VPWR`/`VGND` are the
   `sky130_fd_sc_hd` standard cells' own power-pin names and come entirely
   from the divider's abutted cell row — a 142.6 × 2.72 µm strip of a
   569.93 × 232.76 µm block. The three custom-drawn analog blocks carry no
   supply labels and no supply rails at all, because the layout is unrouted.
   Filed as **#156**.

A fourth gap — reproducibility rather than evidence — is **closed** (issue
#157, 2026-09-23). The first committed report was produced with a `klt` newer
than `layout/requirements.txt`'s pin of the day (`klayout-tools==0.4.0`),
whose `klt erc` predated both `stackup[0].active_layer` and the `provenance`
block, so it could not be regenerated from the pin. The pin is now
`klayout-tools==0.6.0`, both layout flows were re-run at it, and the current
`erc-reports/LATEST` record was produced by the pinned build. The superseded
record is kept unedited; the current one records the measured
`0.4.0`-vs-`0.6.0` difference (216 "gates" vs 213 — the old pin counted this
block's three poly resistors as gates and understated every antenna ratio by
~2.9×).

## Keeping this file honest

- The checklist upstream is versioned and **has changed item count before**.
  Re-read `klayout-tools`' `docs/design-evidence-tiers.md` before trusting
  any row here, and update the item count in this file's intro if it moved
  again.
- A row is "evidence on record" only when the artifact's own content says so.
  Artifact presence is not a verdict — a report generated against an older
  netlist or layout revision than current `main` is stale, not passing.
- Never relax a row to make it read better. A miss is recorded as a miss
  (root `CLAUDE.md`).
