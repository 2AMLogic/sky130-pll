# Work Log

Merged PRs and closed issues from the Guide’s 30-day discovery window.

### 2026-10-29

- **Issue #154** (closed): README: embed the fleet burndown chart (one line)

### 2026-10-28

- **PR #421**: sim: add klt sim wrapper for schematic closed-loop-psrr
- **Issue #4** (closed): Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers)
- **PR #418**: sim: add klt sim wrappers for closed-loop-iq and closed-loop-startup
- **Issue #411** (closed): T1 item 11 (power delivery): commit a klt erc supply spec and report for the SG13G2 bandgap_top instead of citing the SG13CMOS5L port's ERC
- **PR #417**: feat: add SG13G2 bandgap_top ERC evidence and cite it for T1 item 11

### 2026-10-27

- **Issue #408** (closed): Bump klayout-tools pin 7ee09483b748 → 0.8.0
- **PR #409**: ci: pin klayout-tools to PyPI 0.8.0 and regenerate signoff verdict
- **Issue #405** (closed): SG13CMOS5L committed netlists drift from schematics at the dev PDK pin
- **PR #406**: docs: classify archived-pin mm_ok netlist delta in drift check
- **PR #383**: chore: bump klayout-tools pin to 0.8.0 and re-render tier report
- **Issue #382** (closed): Bump klayout-tools pin 0.6.0, 0.7.0 → 0.8.0

### 2026-10-25

- **Issue #399** (closed): Remove dead helpers _interp_log and _fmt_vdd from enrich_ac_report.py
- **PR #400**: refactor(sim): remove uncalled helpers from enrich_ac_report
- **PR #398**: feat(sim): convert closed-loop-vref-pvt-boxtc to the klt sim fleet harness

### 2026-10-24

- **Issue #385** (closed): Remove dead riser 'bridge' machinery in sg13cmos5l-bandgap_top generate.py

### 2026-10-23

- **Issue #389** (closed): sim/README: list the 6 other manifest-less experiments with non-run_pvt_sweep runners
- **PR #393**: docs(sim): list all 18 experiments without run_klt_sim.sh as unconverted
- **Issue #386** (closed): Follow-on from PR #382: convert legacy corners/-writing sim runners to the artifact store
- **PR #388**: ci(sim): fail manifest-less evidence records dated on/after DR-0015
- **Issue #310** (closed): signoff: execute the deferred cold-start testbench audit for T1 item 9
- **PR #391**: fix(sim): make PEX klt-sim record step work cold; add partial item-9 audit log
- **PR #382**: feat(sim): store new klt-sim evidence in the artifact store, commit manifests
- **PR #377**: feat: route LOCK timing group bytes through the artifact store
- **PR #376**: feat: store PLL layout flow outputs in the artifact store
- **Issue #373** (closed): Route run_locktiming.py evidence bytes through the artifact store
- **Issue #371** (closed): Route layout flow reports through the artifact store (manifest in git, bytes via klt artifact)
- **PR #372**: feat: store run evidence bytes in the artifact store, commit manifest and record
- **Issue #370** (closed): Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact)

### 2026-10-22

- **PR #366**: feat(sim): route transient measure campaigns through the batch decks[] executor

### 2026-10-21

- **PR #365**: Bump Repo Skills 0.24.3 -> 0.24.7
- **Issue #374** (closed): Condense layout/README.md: resolved-blocker history and triplicated Reproducing sections
- **PR #375**: docs: condense resolved-blocker history in layout/README.md
- **Issue #366** (closed): Consolidate five near-identical sim run_klt_sim.sh runners into a shared driver
- **PR #369**: refactor(sim): share one driver across the five PEX run_klt_sim.sh runners
- **Issue #367** (closed): CI: hygiene/signoff-manifest fails building klayout wheel on Python 3.15 (red main)
- **PR #368**: ci: pin hygiene signoff-manifest Python to 3.14
- **PR #362**: Bump Repo Skills 0.24.3 -> 0.24.7
- **Issue #103** (closed, not planned): Re-run full sim/pll-lock 45-point PVT grid against widened harness defaults (depends on #102)

### 2026-10-20

- **PR #345**: sim: add behavioral study of the I/Q /2 quadrature output and correct proposal
- **Issue #344** (closed): Test proposed quadrature clock timing with a bounded behavioral model (#332 / DR-010)
- **PR #299**: build: re-pin open_pdks to f6eeac7 and resolve the PDK via ciel with a SOURCES revision check
- **Issue #296** (closed): Re-pin open_pdks to f6eeac7 and move PDK install/search to ciel 2.6.1 (part of #295)
- **PR #353**: feat: add N=20 divider bench and mandatory-probe Stage A Fmax configuration
- **Issue #352** (closed): Prepare divide-by-20 bench and explicit 500 MHz screening probe for #333; no campaign execution
- **PR #351**: docs: add 0.95 V VCTRL point to proposed Stage A VCO matrix
- **PR #350**: refactor: remove dead locals and unused imports in power generators and tests
- **Issue #349** (closed): Remove dead locals and unused imports flagged by ruff F401/F841 (sim/power, signoff, sim/tests)
- **Issue #347** (closed): docs: Stage A request's added VCTRL points miss the 500 MHz crossing at 19 of 45 PVT points
- **PR #346**: docs: propose Stage A campaign request for 500 MHz screening

### 2026-10-19

- **PR #342**: docs: add DR-011 proposed bounded feasibility plan for a 500 MHz output
- **PR #341**: docs: propose quarter-cycle phase vs multiplied-clock output (DR-010)
- **Issue #339** (closed): Propose a phase-shifted or multiplied-clock output interface for v1 (follow-on to #332)

### 2026-10-18

- **Issue #360** (closed): Consolidate PEX klt-sim batch runners: zout-pex duplicates psrr-pex, three bypass pex_merge_call.sh
- **PR #361**: refactor: route remaining PEX batch runners through pex_merge_shards

### 2026-10-17

- **Issue #356** (closed): Consolidate duplicated sha256-pin validation in CI evidence checkers
- **PR #357**: refactor(ci): single-source containment and sha256 pin check
- **PR #335**: docs(spec): add DR-009 recording phase-output scope and consumer clock-gap dispositions
- **PR #330**: feat(signoff): declare partition boundary and inventory items 1, 9, 10
- **PR #328**: refactor: share test module loader, table-row and sha256 helpers
- **Issue #326** (closed): Consolidate the importlib path-loader copied across 13 test files
- **PR #325**: refactor: share injected_from_pwl and parse_floor_records via analysis_common
- **Issue #324** (closed): Share injected_from_pwl and parse_floor_records via sim/analysis_common (residual duplicates)
- **PR #322**: refactor: share parse_floor_record via sim/analysis_common
- **Issue #321** (closed): Consolidate triplicated parse_floor_record into sim/analysis_common.py
- **PR #318**: refactor(sim): share SPICE-literal and floor-netlist parsing across analysis scripts
- **Issue #316** (closed): Consolidate duplicated SPICE-literal and floor-record parsing left in sim analysis scripts
- **PR #315**: refactor(sim): share klt batch capacity-retry submit across runners
- **PR #313**: refactor(sim): share record-table helpers across analysis scripts
- **Issue #314** (closed): Consolidate triplicated klt-sim capacity-retry submit loop (fmax_klt / cp_klt / locktiming_cli)
- **Issue #312** (closed): Consolidate helpers copy-pasted across the sim/*/analysis scripts

### 2026-10-16

- **PR #306**: Bump Repo Skills 0.24.1 -> 0.24.3

### 2026-10-15

- **PR #347**: Bump Repo Skills 0.19.5 -> 0.24.1
- **PR #302**: design: add provisional buffered CLK output stage and 1 pF load contract (DR-008)
- **PR #301**: sim: shard the power campaign to fit the batch fleet job ceiling
- **PR #292**: sim: add klt sim decks[] batch route for the pfd-cp campaign
- **PR #289**: Bump Repo Skills 0.19.5 -> 0.24.1
- **PR #288**: loom: unpin verdict-staleness-guard.sh (2am#4345 Q7)

### 2026-10-14

- **PR #286**: lockdet: resumable append-only grid runner; partial wdb grid (#276)

### 2026-10-13

- **Issue #337** (closed): sim: convert the four SG13CMOS5L experiments to the klt sim harness (Part of #322)
- **Issue #342** (closed): Simplify CI checkers: hoist duplicated manifest discovery, report printing and sha256: wrapper into _ci_common
- **PR #344**: ci: hoist duplicated checker scaffolding into _ci_common
- **Issue #341** (closed): docs: add the five unindexed sim/ experiments to sim/README.md and enforce index completeness
- **PR #343**: docs(sim): index five missing experiments, enforce index completeness
- **Issue #333** (closed): sim: reject unresolved local include closures before minting snapshots
- **PR #340**: sim: reject unresolved local include closures before minting snapshots
- **Issue #332** (closed): sim: bind resumed batch reports to the exact submitted inputs
- **PR #338**: sim: bind resumed batch reports to the exact submitted inputs
- **Issue #331** (closed): sim: repair PEX batch callers missing the mandatory expected-grid arguments
- **PR #334**: sim: repair PEX batch callers missing the mandatory expected-grid arguments
- **PR #285**: design: wdb watchdog nominal, split-temp runner and incomplete-grid evidence (#276)
- **PR #284**: design: watchdog primitive, controls and partial timing handoff (#276)

### 2026-10-12

- **Issue #328** (closed): sim: enforce append-only staged publication in the evidence adapter
- **Issue #327** (closed): sim: reject incomplete and malformed batch shard grids before publishing evidence
- **PR #329**: sim: reject incomplete and malformed batch shard grids before publishing evidence
- **Issue #325** (closed): Guard blocks read-only rg search patterns in Codex
- **PR #326**: ci: detect stale inputs behind the active T1 design-source audit
- **PR #323**: docs: re-stamp SG13CMOS5L target pin to IHP-Open-PDK dev f7bca326 (Refs #322)
- **PR #281**: sim: full PVT grids for LOCK phase-window delay chains (measured miss)
- **Issue #275** (closed): design: measure acquisition and release delay-chain PVT envelopes
- **PR #280**: design: phase-window delay-chain candidates and PVT evidence (#275)
- **PR #279**: sim: add fixed-stimulus batch runner for LOCK timing primitives
- **Issue #274** (closed): sim: add fixed-stimulus batch runner for LOCK timing primitives
- **PR #277**: sim: define LOCK timing measurement schema and reducer
- **Issue #273** (closed): sim: define LOCK timing measurement schema and reducer

### 2026-10-11

- **PR #270**: docs(sim/pfd-cp): full-grid campaign still blocked on batch route (Part of #250)
- **PR #268**: sim: pfd-cp campaign testbench/manifest and nominal resolution record (Part of #250)

### 2026-10-10

- **PR #266**: sim: wire charge-pump analysis through PVT execution and records
- **Issue #249** (closed): sim: wire charge-pump analysis through PVT execution and records
- **PR #263**: sim: implement signed charge-pump analysis and synthetic reducers
- **Issue #248** (closed): sim: implement signed charge-pump analysis and synthetic reducers
- **Issue #246** (closed): sim: run and commit the divider Fmax full-grid record (follow-up to #244)

### 2026-10-09

- **Issue #315** (closed): ci: detect dependency drift in the active characterization summary
- **PR #316**: ci: detect dependency drift in the active characterization report (#315)
- **PR #314**: design: opt-in netlist drift check (#312)
- **Issue #309** (closed): sim: bind PEX simulation records to their consumed extraction hashes
- **PR #311**: sim: bind PEX simulation records to their consumed extraction hashes
- **PR #257**: sim: klt batch route for the divider Fmax campaign with capacity retry (part of #244)
- **PR #256**: Add opt-in headless audit bootstrap wrapper
- **Issue #253** (closed): Auditor Capability Request: Python 3 unavailable for headless repository checks
- **PR #254**: spec: propose the provisional LOCK detector contract with an executable reference (#237)
- **Issue #237** (closed): Specify and test the provisional LOCK detector contract before hardware integration
- **PR #252**: docs: refresh stale status prose in design/ and sim/ READMEs
- **Issue #230** (closed): Refresh stale status statements in design/README.md and sim/README.md
- **PR #245**: sim: divider Fmax characterization campaign (part of #244)
- **PR #243**: verification: inert guard reproduction for /tmp mktemp templates (part of #239)
- **PR #241**: design: regenerate stale top snapshot and guard hierarchical consistency
- **Issue #240** (closed): design: regenerate the stale top-level loop-filter snapshot and guard hierarchical consistency
- **PR #238**: sim: supply-current/power campaign harness (part of #233)

### 2026-10-08

- **Issue #300** (closed): measurements: refresh the aggregated characterization report against the current spec and trim-bearing core, and wrap it for T1 item 8
- **PR #307**: measurements: October characterization report bound to T1 item 8 (#300)
- **Issue #265** (closed): Trimmed-line disposition: DR-0011's +/-0.5% does not hold on #229's aids-free trim-domain MC evidence
- **PR #305**: docs(readme): Trim-row disposition now tracked in #303
- **Issue #297** (closed): Run the loop-gain solve-quality test in hygiene CI and add harness self-tests
- **Issue #295** (closed): Orphan helper .loom/scripts/tracker-state-comment.sh: upstream it or pin it
- **PR #296**: chore: pin tracker-state-comment helper as repo-owned (#295)
- **PR #234**: signoff: bump grader to klayout-tools 0.7.0 and narrow guard 3 (#200)
- **Issue #200** (closed): signoff: klayout-tools#2467 has landed — bump the grader pin and decide what guard 3 becomes
- **PR #229**: README: dated, pointer-based status summary (fix stale claims)
- **PR #226**: signoff: cite the characterization report for T1 item 8 (analog partition)
- **Issue #227** (closed): README status section is stale: claims no PLL sim or layout evidence
- **Issue #224** (closed): T1 item 8: decide and record the characterization-report citation now that #22 has closed

### 2026-10-07

- **PR #222**: ci: run on GitHub-hosted runners; the shared self-hosted runner is retired

### 2026-10-04

- **PR #293**: sim(pex): re-run three of the five PEX grids through the klt-sim batch bridge (part of #278)
- **PR #221**: Consolidate duplicated C1/C2 variant generator mechanics
- **Issue #220** (closed): Consolidate duplicated C1/C2 variant generator mechanics

### 2026-10-03

- **Issue #289** (closed): loop-gain bench: a single AC sweep can return a numerically corrupted solve that PASSes (36.3 deg / 43.9 deg were artifacts); add a solve-quality guard
- **PR #291**: sim(loop-gain): solve-quality gate and guarded 45-point record (#289)
- **Issue #271** (closed): Trim ladder costs real loop phase margin at wcs/125C/2.97V (36.3 deg vs 88.5 deg pre-trim)
- **PR #290**: sim(loop-gain): trim-code axis of phase margin; 36.3 deg is a corrupted AC solve, accept and disclose (#271)
- **Issue #285** (closed): Trim row: should the ratified 1-point 27 °C trim become 2-point (room+hot) with the CTAT knob? It is the only measured path to ±0.5%

### 2026-10-02

- **Issue #277** (closed): Infra: the EDA batch fleet image carries no ihp-sg13g2 PDK (and no OSDI build step), so klt sim cannot run this repo's corner grids
- **PR #287**: feat: run the klt sim probe on the batch fleet (--batch)
- **Issue #267** (closed): Second trim degree of freedom: the 1-point R1 trim converts offset into TC at a measured 0.058%/code, which is what sets the trimmed line
- **Issue #269** (closed): TC row: the trim-bearing, aids-free core reads 20.2-45.7 ppm/C box TC - target still met, <20 ppm/C stretch is not
- **Issue #282** (closed): sim/closed-loop-vref-boxtc-trim/README.md attributes the ±0.5% budget to DR-0010 in one line and DR-0011 in another
- **PR #283**: docs: attribute the ±0.5% trimmed budget to DR-0011 in boxtc-trim README
- **Issue #280** (closed): sim/harness: the klt sim path records one fewer significant figure than run_pvt_sweep.sh, undisclosed
- **Issue #195** (closed): sim(pll-lock-mc): T1 item 6's negative control needs a degraded *design* variant, which this repo has none of

### 2026-10-01

- **Issue #272** (closed): Re-layout and re-extract the block against the trim-bearing core, then refresh the 5 PEX experiments
- **PR #276**: layout: re-draw the summing resistor as #229's trim ladder, re-run DRC/LVS/PEX
- **Issue #264** (closed): Refresh sim/ evidence against the trim-bearing core netlist (post-#229)
- **PR #274**: test(sim): refresh 9 schematic-DUT experiments against the trim-bearing core
- **Issue #229** (closed): Design the trim network obligated by the re-cast Output-reference row (DR-0009: range >= +/-15%, <= 0.25%/step, 1-point @ 27C)
- **Issue #173** (closed): Sweep host cannot load ngspice/xschem: Homebrew dylibs fail code-signature validation (mig callout failed)
- **Issue #172** (closed): CI runs stuck in queued status for 3.5+ hours (self-hosted runner likely offline)

### 2026-09-30

- **Issue #262** (closed): spec: duplicate decision-record number 0010 on main (hygiene CI failing since PR #230 merge)
- **Issue #231** (closed): Apply the two ratification keys to PR #230 (DR-0009, Output-reference re-cast) — non-author
- **Issue #221** (closed): Output-reference row: decide its disposition (re-target vs. defend ±1% untrimmed) — both ratification keys escalated it
- **PR #230**: ratification: re-cast the Output-reference row (DR-0010)
- **PR #82**: fix(ratification): remove unwrapped private-repo reference from market-key/SKILL.md

### 2026-09-29

- **Issue #260** (closed): Remove duplicated Report/sha256_file scaffolding across .github/scripts CI checkers
- **PR #261**: Remove duplicated Report/sha256_file scaffolding across .github/scripts CI checkers
- **PR #259**: chore: resync installed Loom surfaces (--force past obsolete local edits)

### 2026-09-27

- **PR #217**: measurements: regenerate the stale characterization report and guard against a repeat
- **PR #219**: sim: audit whether ngspice's default tolerances bias four campaigns' frequency figures
- **Issue #210** (closed): sim: audit whether default ngspice tolerances bias frequency figures in pll-lock/vco/vco-supply-pushing/loop-ripple
- **Issue #22** (closed): Produce an aggregated PLL characterization report across ratified spec rows (T1 item 8)

### 2026-09-26

- **PR #209**: sim: row 9's Monte Carlo misses are ngspice integrator error, not the circuit -- measure it, tighten it, re-run (#202)
- **PR #211**: sim(pll-lock-mc): superseding row-9 Monte Carlo record at accurate integrator settings -- 5/5 draws meet the bound (#202)
- **PR #213**: design: test #202's named jitter suspect against committed evidence, and state row 9's realized margin
- **PR #214**: sim/harness: stage a campaign's work outside a reapable checkout
- **PR #216**: sim: size T1 item 6's negative control by measurement -- C2 is not the knob, C1 area/12 is (#195)
- **Issue #212** (closed): sim/harness: a campaign reaped with its worktree is lost irrecoverably, including its resume checkpoint
- **Issue #202** (closed): sim/design: ratified spec row 9 is missed on every Monte Carlo draw, and that gates T1 item 6's negative control

### 2026-09-25

- **PR #181**: sim: run row 9's first Monte Carlo campaign — and let an MC trial measure at all (#20)
- **PR #184**: signoff: grade row 9's Monte Carlo campaign with `klt yield`, and record why T1 item 6 still is not cited
- **PR #187**: sim(jitter-floor): measure the period-jitter reducer's own resolution floor, and restate row 9's recorded miss against it
- **PR #188**: fix: make check:ci provably headless on any PDK-equipped host
- **PR #189**: sim(pll-lock): declare a gated measure.jitter block for ratified row 9
- **PR #191**: sim(harness): reject a gated jitter bound that outruns the lock criterion
- **PR #192**: signoff(guards): refuse a klt yield citation its own statistics do not support
- **PR #194**: sim(jitter-calibration): calibrate the period-jitter reducer against a known injected figure
- **PR #196**: signoff: re-derive T1 item 6's preconditions from the repo instead of asserting them
- **PR #198**: sim(vco-clk-transition): measure design/vco's real CLK transition time
- **PR #199**: sim(jitter-floor/pll-lock-mc): decline the calibration-informed floor, and name the run that would change it
- **PR #201**: sim(pll-lock-mc): measure whether T1 item 6's negative control can fire here at all
- **PR #204**: sim(pll-lock-mc): derive what would make T1 item 6's negative control fire, and what it costs
- **PR #206**: sim(jitter-calibration): measure the null control's error sign at a near-integer period
- **PR #207**: signoff: fix stale layout record IDs and add drift-detection check
- **PR #208**: sim(pll-lock-mc): apply trial 2's period-matched calibration bracket, decline further for trial 3
- **Issue #205** (closed): sim(pll-lock-mc): decide whether trial 2's now period-matched calibration family should bracket its residual
- **Issue #203** (closed): signoff/README.md's item-3 section names a superseded layout record the manifest no longer cites
- **Issue #197** (closed): sim(jitter-calibration): run the calibration family at a period near an integer multiple of the grid step
- **Issue #193** (closed): sim(jitter-floor/pll-lock-mc): the Monte Carlo restatement still uses the null-control floor, not the calibrated one
- **Issue #190** (closed): sim(harness): a gated jitter bound can mint artefact FAILs when measure.jitter.min_cycles exceeds lock.min_hold_cycles
- **Issue #186** (closed): sim: design/vco's CLK transition time is unmeasured, so the applicable period-jitter measurement floor cannot be read off sim/jitter-floor's family
- **Issue #185** (closed): sim(jitter-floor): the measurement floor is only characterized for a jitter-free source, not for one that actually jitters
- **Issue #183** (closed): check:ci is documented as headless but runs the full 45-point pdk-smoke grid on any PDK-equipped host
- **Issue #180** (closed): sim(pll-lock): row 9's deterministic PVT axis is unmeasured — no manifest declares measure.jitter
- **Issue #179** (closed): signoff: T1 item 6 is still ungraded — the "klt has no yield verb" premise is stale, and a Monte Carlo sample set now exists
- **Issue #178** (closed): sim(pll-lock-mc): the measured period jitter cannot be separated from the 200 ps dump-grid resolution floor
- **Issue #20** (closed): Stand up Monte Carlo / klt yield verification methodology for the PLL's statistical spec rows (T1 item 6)

### 2026-09-24

- **PR #176**: layout: pin the klayout engine, not just klayout-tools
- **PR #177**: fix: fail closed when signoff's artifact re-hash guard finds no artifact
- **Issue #167** (closed): layout/requirements.txt pins klayout-tools but not the klayout engine, so klt warns on every run that report counts may not reproduce
- **Issue #163** (closed): signoff: the artifact re-hash guard fails open when the cited artifact is missing

### 2026-09-23

- **PR #155**: fix: purge stale unit artifacts before the remote executor's pull
- **PR #160**: spec: ratify target-spec row 9 (period jitter) via DR-006; rows 10 and 13 stay DRAFT explicitly
- **PR #161**: feat(signoff): commit a klt block manifest so this block's T1 state is graded, not hand-read
- **PR #162**: feat(layout): add klt erc supply spec and first power-delivery record
- **PR #164**: feat(measurements): emit the spec-row citation by construction
- **PR #168**: layout: bump the klt pin to 0.6.0 and refresh every record it grades
- **PR #169**: feat(measure): extract period jitter for the ratified spec row 9
- **PR #171**: layout/bin: dedupe _render_provenance into render_common (#170)
- **PR #174**: sim: add ripple_pp reducer and a sim/loop-ripple VDD/VCTRL ripple testbench
- **PR #175**: sim: measure VCO frequency-vs-VDD supply pushing at fixed VCTRL
- **Issue #170** (closed): Dedupe _render_provenance between render-record.py and render-pll-record.py (re-file of #140)
- **Issue #165** (closed): sim: measure VCO frequency-vs-VDD supply pushing at fixed VCTRL (DR-006 row 13 Budget 1, part 1)
- **Issue #158** (closed): sim/harness: no period-jitter metric exists, so the newly ratified spec row 9 cannot be measured
- **Issue #157** (closed): layout/requirements.txt's klt pin (0.4.0) cannot reproduce the committed klt erc supply record
- **Issue #152** (closed): Zero evidence records carry the **Spec row(s)** citation the aggregator matches on — T1 item 8's report is empty by construction
- **Issue #151** (closed): spec: ratify target-spec rows 9/10/13 — #20 and #22 are blocked on this and nothing targets it
- **Issue #150** (closed): sim/harness: purge_unit_artifacts is local-path-only, so the remote executor can read a stale waveform dump
- **Issue #148** (closed): Commit a klt signoff block manifest so this block's T1 state is graded, not hand-read
- **Issue #147** (closed): T1 item 11 (power delivery, structural): no klt erc supply spec or report in this repo

### 2026-09-20

- **PR #149**: sim/harness: add an `--executor {local,remote}` seam so ngspice units can run on klt's Spot fleet (#146)
- **Issue #146** (closed): sim/harness: `--executor remote` — route ngspice units through klt's Spot backend (fleet adoption pilot)

### 2026-09-14

- **Issue #140** (closed): Dedupe _render_provenance between render-record.py and render-pll-record.py

### 2026-09-12

- **PR #145**: sim(pll-lock): raise per-point timeout_s 10800 -> 43200; amend DR-004 (#103)

### 2026-09-11

- **PR #132**: Ship sim/divider standalone PVT testbench, mint N=25 evidence record
- **PR #135**: refactor(sim/harness): dedupe SPICE-literal parsing between measure.py and acmeasure.py
- **PR #136**: sim/harness: per-point parallelism (--jobs) and checkpointed resume (--resume)
- **PR #138**: sim/divider-n64: run the tt process-corner row (9/45), partial progress toward issue #130's full grid
- **PR #139**: sim/divider: mint first evidence records for -n4/-n5/-n63/-n64 siblings
- **PR #141**: sim/divider-n64: run the ff process-corner row (row 2/5), 21/45 points toward issue #130's full grid
- **PR #142**: sim/divider-n64: complete the ss process-corner row (issue #130, partial)
- **PR #143**: sim/divider-n64: complete the full DR-003 45-point PVT grid (sf + fs rows, 45/45 PASS)
- **Issue #137** (closed): Retry the sim/divider-n64 full-grid PVT campaign (issue #130) once host contention clears
- **Issue #134** (closed): Deduplicate SPICE-literal parsing: parse_spice_time/parse_spice_freq share an identical regex and suffix table
- **Issue #133** (closed): sim/harness: per-point parallelism or checkpointed resume needed to make sim/pll-lock's 45-point campaign tractable
- **Issue #131** (closed): Run the sim/divider-n4/-n5/-n63/-n64 PVT campaigns and mint their first sim/ evidence records (deferred by #129)
- **Issue #130** (closed): Complete the full DR-003 45-point PVT grid for sim/divider-n64 and sim/divider-n63 (deferred by #129)
- **Issue #129** (closed): Ship a standalone `sim/divider` PVT testbench and mint the first `sim/` evidence record for divider_intN (turn #114's informal top-frequency and modulus diagnostics into committed 45-point evidence; spec row 4)

