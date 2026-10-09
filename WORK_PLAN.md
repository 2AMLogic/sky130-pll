# Work Plan

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs stuck under a `loom:operator` merge-risk hold — implementation work is done, only a human merge decision is missing.

_None._

## Operator Priority

Issues the operator starred (`loom:operator-priority`); land these first.

_None._

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

_None._

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#18**: Get the PLL netlist-vs-layout LVS-clean via klt (T1 item 4) *(curated)*
- **#21**: Run post-layout (PEX) verification for the PLL netlist (T1 item 7) — blocked on klayout-tools klt pex *(curated)*
- **#98**: Closed-loop cold-start lock convergence still broadly fails across PVT after #95's loop-filter re-size *(curated)*
- **#103**: Re-run full sim/pll-lock 45-point PVT grid against widened harness defaults (depends on #102) *(curated)*
- **#159**: sim: no VCO supply-pushing or transient rail-ripple campaign exists, so spec row 13 cannot be derived *(curated)*
- **#166**: sim: measure transient VDD/VCTRL ripple-in-lock of the assembled loop (DR-006 row 13 Budget 1, part 2) *(curated)*
- **#182**: signoff: cite T1 item 6 once row 9's Monte Carlo campaign has a negative control and a sized population *(curated)*
- **#215**: sim(pll-lock-mc-negative-control): draw the six-trial control campaign and grade it with klt yield *(curated)*
- **#233**: sim: no sky130 power measurement exists, so spec row 12 cannot be re-budgeted *(curated)*
- **#239**: Guard: recognize bounded explicit /tmp mktemp templates while preserving containment *(curated)*

## Proposed (Architect / Hermit)

- **#231**: design: add the digital lock output spec row 16 asks for (top-level has no LOCK port) *(architect)*
- **#232**: design: CLK is the raw VCO node — add an output stage so rows 14/15 have a pin to measure *(architect)*

## Epics

_None._

## Backlog Balance

| Tier | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Operator priority | 0 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 0 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 0 |
| Curated | 10 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
