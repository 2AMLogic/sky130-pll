# Work Plan

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#304**: layout: draw clk_buf and re-mint the top-level layout record against the buffered top (split from #303)

## Important

`loom:important`; taken before unlabelled work.

- **#244**: sim: record divider Fmax boundaries across PVT for digital T1 characterization
- **#443**: render-pll-record: the same li1.space.1 count is stated twice per record, once derived and once typed in

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#244**: sim: record divider Fmax boundaries across PVT for digital T1 characterization
- **#304**: layout: draw clk_buf and re-mint the top-level layout record against the buffered top (split from #303)
- **#440**: Remove ExecutionBackend.requested: a fallback marker left behind by #425
- **#447**: Remove two dead-on-arrival harness helpers kept alive only by their own tests (to_supplied, split_static_dynamic)
- **#448**: Dedupe the two parallel DirtyFlagTests: scripts/git_status.py is tested twice through re-export shims, and layout's real git_provenance is untested
- **#453**: Remove three dead Python symbols and the inert noqa suppressions hiding them
- **#454**: Dedupe the seven PDK stub classes in sim/tests: four shapes for one 8-field frozen dataclass, three contradicting its as_env
- **#456**: package.json: check:all silently skips three checks check:ci runs, and test:compile misses scripts/ (the two lists #446 scoped out)

## In Progress

Issues currently being built (`loom:building`).

- **#439**: docs: README and CLAUDE.md still say this repository is private
- **#443**: render-pll-record: the same li1.space.1 count is stated twice per record, once derived and once typed in
- **#446**: Replace package.json lint's hand-listed `bash -n` chain with a discovery loop (the list has already drifted)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#437**: docs: roadmap as of 2026-11-13
- **#449**: docs: state the repository is public and list every tracked top-level directory
- **#452**: build: discover shell scripts for bash -n lint instead of enumerating them

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#416**: layout: count extracted resistors from klt JSON; mint passing buffered-top record
- **#444**: fix: derive the record's li1.space.1 count from the plan, not a literal

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
- **#304**: layout: draw clk_buf and re-mint the top-level layout record against the buffered top (split from #303) *(curated)*
- **#439**: docs: README and CLAUDE.md still say this repository is private *(curated)*

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
| Very important | 1 |
| Important | 2 |
| Ready (`loom:issue`) | 8 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 3 |
| Approved PRs awaiting merge | 2 |
| Curated | 17 |
| Architect / Hermit proposals | 3 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
