# Work Plan

<!-- guide:plan-body:start -->
_Generated: 2026-11-24T11:11:24Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#244**: sim: record divider Fmax boundaries across PVT for digital T1 characterization *(held)*

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#523**: xschem pin migration: migrate sky130-pll to the fleet 3.4.7

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#18**: Get the PLL netlist-vs-layout LVS-clean via klt (T1 item 4) *(curated)* *(held)*
- **#21**: Run post-layout (PEX) verification for the PLL netlist (T1 item 7) — blocked on klayout-tools klt pex *(curated)* *(held)*
- **#98**: Closed-loop cold-start lock convergence still broadly fails across PVT after #95's loop-filter re-size *(curated)* *(held)*
- **#159**: sim: no VCO supply-pushing or transient rail-ripple campaign exists, so spec row 13 cannot be derived *(curated)* *(held)*
- **#166**: sim: measure transient VDD/VCTRL ripple-in-lock of the assembled loop (DR-006 row 13 Budget 1, part 2) *(curated)* *(held)*
- **#182**: signoff: cite T1 item 6 once row 9's Monte Carlo campaign has a negative control and a sized population *(curated)* *(held)*
- **#215**: sim(pll-lock-mc-negative-control): draw the six-trial control campaign and grade it with klt yield *(curated)* *(held)*
- **#232**: design: CLK is the raw VCO node — add an output stage so rows 14/15 have a pin to measure *(curated)* *(held)*
- **#233**: sim: no sky130 power measurement exists, so spec row 12 cannot be re-budgeted *(curated)* *(held)*
- **#239**: Guard: recognize bounded explicit /tmp mktemp templates while preserving containment *(curated)* *(held)*
- **#244**: sim: record divider Fmax boundaries across PVT for digital T1 characterization *(curated)* *(held)*
- **#259**: design: characterize LOCK timing primitives and watchdog over PVT *(curated)*
- **#290**: sim: klt decks[] batch route for the PFD/charge-pump (cp) campaign, with one-point smoke *(curated)* *(held)*
- **#297**: Re-qualify cited sim reference records under open_pdks f6eeac7 (part of #295) *(curated)* *(held)*
- **#298**: Re-qualify cited layout reference records under open_pdks f6eeac7 (part of #295) *(curated)* *(held)*
- **#523**: xschem pin migration: migrate sky130-pll to the fleet 3.4.7 *(curated)*

## Proposed (Architect / Hermit)

- **#231**: design: add the digital lock output spec row 16 asks for (top-level has no LOCK port) *(architect)* *(held)*
- **#247**: sim: add a standalone PFD/charge-pump characterization campaign (UP/DN asymmetry, Icp, compliance) *(architect)* *(held)*
- **#434**: Collapse the layout klt pin narrative: 156 comment lines for 2 pins, with stale copies in layout/README.md and setup-venv.sh *(hermit)*
- **#554**: Remove the unused mim_cap_ff helper with the incorrect C1 example *(hermit)* *(held)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 1 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 0 |
| In Progress (`loom:building`) | 1 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 0 |
| Curated | 16 |
| Architect / Hermit proposals | 4 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
