# Work Plan

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#299**: build: re-pin open_pdks to f6eeac7 and resolve the PDK via ciel with a SOURCES revision check

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#304**: layout: draw clk_buf and re-mint the top-level layout record against the buffered top (split from #303)

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#304**: layout: draw clk_buf and re-mint the top-level layout record against the buffered top (split from #303)

## In Progress

Issues currently being built (`loom:building`).

- **#296**: Re-pin open_pdks to f6eeac7 and move PDK install/search to ciel 2.6.1 (part of #295)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#299**: build: re-pin open_pdks to f6eeac7 and resolve the PDK via ciel with a SOURCES revision check

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
- **#244**: sim: record divider Fmax boundaries across PVT for digital T1 characterization *(curated)*
- **#259**: design: characterize LOCK timing primitives and watchdog over PVT *(curated)*
- **#276**: design: measure independent watchdog and publish LOCK timing handoff *(curated)*
- **#290**: sim: klt decks[] batch route for the PFD/charge-pump (cp) campaign, with one-point smoke *(curated)*
- **#296**: Re-pin open_pdks to f6eeac7 and move PDK install/search to ciel 2.6.1 (part of #295) *(curated)*
- **#303**: sim: paired buffered-CLK closed-loop runs and layout/LVS for clk_buffer (follow-up to #232) *(curated)*

## Proposed (Architect / Hermit)

- **#231**: design: add the digital lock output spec row 16 asks for (top-level has no LOCK port) *(architect)*
- **#247**: sim: add a standalone PFD/charge-pump characterization campaign (UP/DN asymmetry, Icp, compliance) *(architect)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 0 |
| Important | 1 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 1 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 1 |
| Curated | 16 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
