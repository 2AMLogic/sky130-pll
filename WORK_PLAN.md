# Work Plan

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#244**: sim: record divider Fmax boundaries across PVT for digital T1 characterization

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#476**: signoff: README item 8 quotes a stale pin literal, one re-pin behind the manifest
- **#487**: ci: every Loom label write re-runs the full headless check suite, and races post-verdict.sh's exact-head CI gate
- **#491**: docs(signoff): adding a decision-record index row requires the item 10 re-attestation chain — undocumented
- **#503**: sim/harness: PVT/Fmax record writer accepts a re-run with no --supersedes; the lock-timing lane already guards it
- **#504**: Derived-list lint suites do not independently pin the non-git guard (empty-set guard masks its removal)

## In Progress

Issues currently being built (`loom:building`).

- **#244**: sim: record divider Fmax boundaries across PVT for digital T1 characterization
- **#462**: sim/executor-equivalence/README.md still documents the retired --executor remote path as live
- **#495**: sim/tests: two duck-typed PDK stand-ins remain outside #472's scope

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#513**: docs: link the executor-equivalence retirement note from its README and correct three stale inbound citations
- **#514**: test: convert the last two duck-typed PDK stand-ins to make_resolved_pdk

## Proposed

Issues carrying `loom:curated`.

- **#18**: Get the PLL netlist-vs-layout LVS-clean via klt (T1 item 4) *(curated)*
- **#21**: Run post-layout (PEX) verification for the PLL netlist (T1 item 7) — blocked on klayout-tools klt pex *(curated)*
- **#98**: Closed-loop cold-start lock convergence still broadly fails across PVT after #95's loop-filter re-size *(curated)*
- **#159**: sim: no VCO supply-pushing or transient rail-ripple campaign exists, so spec row 13 cannot be derived *(curated)*
- **#166**: sim: measure transient VDD/VCTRL ripple-in-lock of the assembled loop (DR-006 row 13 Budget 1, part 2) *(curated)*
- **#182**: signoff: cite T1 item 6 once row 9's Monte Carlo campaign has a negative control and a sized population *(curated)*
- **#215**: sim(pll-lock-mc-negative-control): draw the six-trial control campaign and grade it with klt yield *(curated)*
- **#232**: design: CLK is the raw VCO node — add an output stage so rows 14/15 have a pin to measure *(curated)*
- **#233**: sim: no sky130 power measurement exists, so spec row 12 cannot be re-budgeted *(curated)*
- **#239**: Guard: recognize bounded explicit /tmp mktemp templates while preserving containment *(curated)*
- **#244**: sim: record divider Fmax boundaries across PVT for digital T1 characterization *(curated)*
- **#259**: design: characterize LOCK timing primitives and watchdog over PVT *(curated)*
- **#290**: sim: klt decks[] batch route for the PFD/charge-pump (cp) campaign, with one-point smoke *(curated)*
- **#297**: Re-qualify cited sim reference records under open_pdks f6eeac7 (part of #295) *(curated)*
- **#298**: Re-qualify cited layout reference records under open_pdks f6eeac7 (part of #295) *(curated)*
- **#462**: sim/executor-equivalence/README.md still documents the retired --executor remote path as live *(curated)*
- **#476**: signoff: README item 8 quotes a stale pin literal, one re-pin behind the manifest *(curated)*
- **#487**: ci: every Loom label write re-runs the full headless check suite, and races post-verdict.sh's exact-head CI gate *(curated)*
- **#491**: docs(signoff): adding a decision-record index row requires the item 10 re-attestation chain — undocumented *(curated)*
- **#495**: sim/tests: two duck-typed PDK stand-ins remain outside #472's scope *(curated)*
- **#503**: sim/harness: PVT/Fmax record writer accepts a re-run with no --supersedes; the lock-timing lane already guards it *(curated)*
- **#504**: Derived-list lint suites do not independently pin the non-git guard (empty-set guard masks its removal) *(curated)*

## Proposed (Architect / Hermit)

- **#231**: design: add the digital lock output spec row 16 asks for (top-level has no LOCK port) *(architect)*
- **#247**: sim: add a standalone PFD/charge-pump characterization campaign (UP/DN asymmetry, Icp, compliance) *(architect)*
- **#434**: Collapse the layout klt pin narrative: 156 comment lines for 2 pins, with stale copies in layout/README.md and setup-venv.sh *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 1 |
| Ready (`loom:issue`) | 5 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 2 |
| Curated | 22 |
| Architect / Hermit proposals | 3 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
