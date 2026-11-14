# Roadmap

An integer-N ring-oscillator PLL for the sky130 open PDK, designed forward from
a row-by-row ratified spec, with every claim backed by a recorded testbench.

Status as of 2026-11-13, `main` @ `37484b3`.

This file says what comes next and why. It is not a verdict: the T1 verdict is
[`signoff/tier-report.json`](../signoff/tier-report.json), the per-row rollup
is [`measurements/report.md`](../measurements/report.md), and #380 tracks the
gap to T1. Where this file and those disagree, they are right.

## Where it stands

**Spec.** Rows 0, 1, 9, 19 and 20 of
[`spec/target-spec.md`](../spec/target-spec.md) are ratified (DR-001, DR-002,
DR-003, DR-006). Rows 10 and 13 are DRAFT by explicit decision (DR-006). Every
other numeric row is DRAFT. DR-007 (lock detector), DR-008 (CLK buffer),
DR-009 and DR-010 (phase outputs) are `proposed`, not ratified.

**Design.** Schematics and netlist snapshots exist for the PFD/charge pump,
loop filter, 5-stage ring VCO, programmable divider, CLK buffer (#302) and the
closed-loop top (`design/`). An I/Q divide-by-2 cell for the DR-010 proposal
is in `design/divider-iq` (PR #423). There is no LOCK circuit.

**Evidence, by spec row** (from `measurements/report.md`):

- PASS records exist for rows 2 and 5 (`sim/vco`), 4 (`sim/divider*`, N = 4,
  5, 63, 64 and the 45-point N = 64 grid), 6 and 7 (`sim/loop-ac`) and 13's
  supply-pushing part (`sim/vco-supply-pushing`). All of those rows are DRAFT.
- Row 9 (ratified): the Monte Carlo record passes (`sim/pll-lock-mc`); the
  deterministic PVT records in `sim/pll-lock` are FAIL.
- Rows 3, 8 and 14 are FAIL in every closed-loop record, including the
  buffered-top nominal runs of 2026-11-04 (`sim/pll-lock-1mhz`,
  `sim/pll-lock-25mhz`). Cold-start lock across PVT is the open design
  problem (#98).
- Rows 10, 12, 15 and 16 have no evidence. The campaigns for them are written
  but have never produced a record: `sim/power`, `sim/clk-output`,
  `sim/vco-buffered`, `sim/pfd-cp`, `sim/loop-ripple`, `sim/divider-fmax` and
  `sim/pll-lock-mc-negative-control` each hold zero records.
- LOCK timing primitives (#259, PR #411): the watchdog passes at 45/45 PVT
  points; both phase-window chains miss the DR-007 Table 2 bands.

**T1 checklist** (`klayout-tools==0.8.0`, eleven items, two partitions): 9 of
22 rows met, `tier: null`.

| Item | State | Owner |
|---|---|---|
| 1 Design sources, 9 Testbenches, 10 Hygiene | met, both partitions (PR #405) | none |
| 3 DRC clean | met, both partitions | none |
| 8 Characterization report | met for analog; digital unmet | #244 |
| 2 Layout stream | unmet, deliberately uncited until LVS is clean | #379 |
| 4 LVS clean | unmet; the shipped layout is unrouted | #18 |
| 5 Corner verification vs ratified spec | unmet; most rows are DRAFT | none |
| 6 Monte Carlo | unmet; negative control not drawn | #215, #182 |
| 7 Post-layout verification | unmet | #21 |
| 11 Power delivery (structural) | unmet, see [`t1-gap.md`](t1-gap.md) | #156 |

## Now

Items 1 and 2 carry a stale `loom:blocked` label; items 3 and 4 have no issue yet.

1. **Re-run the one-point PFD/charge-pump batch smoke (#290).** Done when a
   `sim/pfd-cp/records/` record exists for tt / 27 C / 1.80 V and its dumps
   reduce through `cpmeasure`. The 2026-11-04 attempt failed on the batch
   runner (klayout-tools#4891, still open), but a 45-deck sky130 campaign
   completed on a newer runner on 2026-11-10 (`sim/vco-2x-iq-25mhz/records/`),
   so one retry is warranted. A stale remote branch `feature/issue-290`
   refused the last push.
2. **Run the divider Fmax campaign (#244).** Done when `sim/divider-fmax/records/`
   holds the 225-cell record and item 8's digital row can cite it. PR #418
   fixed the harness refusal that stopped the last attempt.
3. **Argue a response to the LOCK phase-window miss (no issue yet).** Done when
   a `proposed` decision record states, from the committed 45-point phase
   records, either chain lengths that would land `W_acq` and `W_rel` in the
   DR-007 Table 2 bands or a superseding set of bands, with the invariants
   re-checked. This is what #260 is waiting for.
4. **Correct the visibility statements (no issue yet).** Done when `README.md`
   and `CLAUDE.md` no longer say the repository is private, and the README
   layout list names every top-level directory.

## Next

- **Batch route for `pll-lock` and `loop-ripple` (#365)**, one-point smoke
  only. Unblocked by #290.
- **Full-grid closed-loop re-run and first `loop-ripple` record (#218).**
  Unblocked by #365. Its record is the baseline #98 needs, and it releases
  #127, #166 and the negative-control campaign #215 (then #182, item 6).
- **PFD/charge-pump 45-point campaign (#250, parent #247).** Unblocked by #290.
- **Standalone LOCK circuit (#260), then loop integration (#261, #231).**
  Unblocked by Now item 3 being decided.
- **Close the open_pdks re-pin (#295).** Layout half (#298, PR #358) waits on
  the #304 hold below; sim half (#297) waits on #365.
- **Power campaign (#233).** Done when one `sim/power` shard completes on the
  batch route and the 45-point record follows.

## Later

- **Fix cold-start lock across PVT (#98).** First: does the fresh full-grid
  record (#218) show a loop-filter problem or a VCO start-up problem?
- **Route the layout and get LVS clean (#18), then PEX (#21), the layout
  citation (#379) and the analog supply rails (#156).** First: can
  `klt gen-compose` assign layers and tracks across many crossing nets
  (klayout-tools#1962)?
- **Ratify the remaining spec rows (item 5).** First: which DRAFT rows have a
  full-grid record a decision record can stand on? Rows 2, 4, 5, 6 and 7 have
  PASS records today; rows 8 and 14 need the design fix; row 10 needs rows 2
  and 5 ratified plus a charge-pump asymmetry measurement (#250, DR-006).

## Blocked and waiting

- **Buffered-top layout record (#304, PR #416).** The new record passes, but
  `signoff/run-signoff.sh --check` fails its superseded-record guard because
  the record's `drc.json` and GDS live in the artifact store, not in git
  (DR-012 left this open). Needs a decision on how signoff cites stored
  evidence. Held for the operator.
- **DR-010 adoption (#332).** The 90-point I/Q evidence passed (PR #423); the
  adopt / more evidence / reject choice is with the operator.
- **Buffered-CLK evidence path (#232)** and the layout pin-narrative cleanup
  (#434): options are with the operator. Rows 14 and 15 wait on #232.
- **500 MHz consumer requirement (#333, DR-011).** The bench is prepared
  (`sim/divider-n20`, PR #353); running it is not authorized.
- **Upstream:** klayout-tools#4891 (batch runner), klayout-tools#1962
  (routing), and a Repo Skills release carrying the guard fix for #239.

## Not planned

- A power-down mode (row 17) or an integrated-jitter / phase-noise spec (row
  11, derived-only by design).
- Silicon measurement, or porting gf180-pll numbers in place of a sky130 campaign.
