# Work Log

Merged PRs and closed issues from the Guide’s 30-day discovery window.

### 2026-10-08

- **PR #234**: signoff: bump grader to klayout-tools 0.7.0 and narrow guard 3 (#200)
- **Issue #200** (closed): signoff: klayout-tools#2467 has landed — bump the grader pin and decide what guard 3 becomes
- **PR #229**: README: dated, pointer-based status summary (fix stale claims)
- **PR #226**: signoff: cite the characterization report for T1 item 8 (analog partition)
- **Issue #227** (closed): README status section is stale: claims no PLL sim or layout evidence
- **Issue #224** (closed): T1 item 8: decide and record the characterization-report citation now that #22 has closed

### 2026-10-07

- **PR #222**: ci: run on GitHub-hosted runners; the shared self-hosted runner is retired

### 2026-10-04

- **PR #221**: Consolidate duplicated C1/C2 variant generator mechanics
- **Issue #220** (closed): Consolidate duplicated C1/C2 variant generator mechanics

### 2026-10-02

- **Issue #195** (closed): sim(pll-lock-mc): T1 item 6's negative control needs a degraded *design* variant, which this repo has none of

### 2026-10-01

- **Issue #173** (closed): Sweep host cannot load ngspice/xschem: Homebrew dylibs fail code-signature validation (mig callout failed)
- **Issue #172** (closed): CI runs stuck in queued status for 3.5+ hours (self-hosted runner likely offline)

### 2026-09-30

- **PR #82**: fix(ratification): remove unwrapped private-repo reference from market-key/SKILL.md

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
