# LOCK-detector timing handoff (issue #276, part of #259 within #231)

Combined circuit-timing evidence for the provisional LOCK detector. DR-007
stays **proposed**, spec row 16 stays **DRAFT**, and the behavioral reference
(`lockdet_ref.py`) is unchanged. Q/R/K logic, CDC, reset-to-LOCK latency and
clock-loss transitions belong to #260/#261; nothing here establishes them.

## Verdict

**The handoff is NOT ready, and #260 remains blocked.** Two independent
reasons, neither a spec relaxation:

1. Phase windows (#275, complete 45/45 physical records): no candidate meets the
   DR-007 Table 2 `W_acq` / `W_rel` bands (see `sim/lockdet-timing/phase/README.md`).
2. Watchdog (this issue): **no complete 45-point watchdog grid exists.** Only
   nominal (tt, 27 C, 1.8 V) and negative-control points were obtained. The
   full grid could not be completed for the two candidates tried (below). This
   is missing evidence (`INCONCLUSIVE`), not a measured band miss, and it is not
   full-grid completion. Resolving it needs a tool change or a re-scoped
   candidate; a superseding decision record is only relevant if a *complete*
   grid later shows a miss.

Mechanical grade (reducer `handoff`, `design/lock-detector/timing/grade_combined.py`;
nearest rising phase candidate `s25-rising`, record `lt-20261012-220148-142698`,
with the watchdog nominal record): scope FULL, `handoff_ready: false`;
`phase-acq` MISS (`w_acq`), `phase-rel` MISS (`w_rel`; hysteresis and 12 ns
ceiling PASS), `watchdog` INCONCLUSIVE (`tick`, incomplete).

## Watchdog primitive (candidate `wd`, dlygate ring) - MEASURED nominal only

Independent of REF, FBCLK and CLK: its only inputs are `EN`, `RSTB` and the
supply.

| item | value |
|---|---|
| enable gate | 1 x `sky130_fd_sc_hd__nand2_1` (EN, feedback) |
| ring delay | 5 x `sky130_fd_sc_hd__dlygate4sd3_1`, drive 1, in series (the NAND is the only inverting stage) |
| divider | 6 x `sky130_fd_sc_hd__dfrbp_1` ripple toggle (D = Q_N, CLK = previous Q), ratio /64, `RESET_B` = `RSTB` |
| taps | `RAW` = last ring buffer output (also feeds the NAND); `TICK` = Q of flop 6 |
| loading | 10 fF on `RAW` and on `TICK`, plus the first flop clock pin on `RAW` |
| thresholds | 0.9 V absolute, all supplies |
| stimulus | `EN` and `RSTB` step 0 -> VDD at 20 ns (100 ps edge); VDD fixed per group |
| settling / window | enable 20 ns + settle 60 ns; window 100 ns - 1.5 us; output step 50 ps; timeout 3600 s |
| startup aid | none: no `.ic`, no ideal forcing. With `EN` low the NAND holds the ring at a DC state; raising `EN` starts it from that state. `RSTB` low holds the divider cleared. |
| area (liberty, placement-free) | 3.754 + 5 x 10.010 + 6 x 28.778 = 226.5 um^2 |

Measured at tt / 27 C / 1.8 V (batch record `lt-20261013-061032-937960`, job
`klt-sim-2a1f494dbbd4`, status OK, 50 ps output step):

| quantity | value | note |
|---|---|---|
| raw-ring period | 4.105 ns | diagnostic, not banded |
| divided tick | 262.75 ns | in the 125-500 ns band (one point only) |
| startup latency | 4.138 ns | EN release to first RAW rising crossing |

The divided tick equals 64 x raw period, as expected for a /64 ripple chain.
Independent local single-corner cross-checks (one `ngspice -b` each, same deck,
tt / 27 C / 1.8 V; local traces inspected for `RAW` and `TICK` separately):

* 25 ps step: raw period 4.075 ns, tick 260.8 ns. 5 ps reference trend: 4.08 -> 4.07 ns. The 50 ps batch value is about 0.8 % slow; 100 ps was 3.9 % slow (a 100 ps precursor smoke, uncommitted, read 4.233 ns / 271 ns), so the step was tightened.
* First `TICK` rising edge at 25.4 ns: the first RAW edge ripples through all six flops because each toggles from its cleared state. It lies before the window and does not affect the period.
* Disable / re-enable (local): EN low at 300 ns holds `RAW` high with no oscillation; EN back high at 500 ns restarts with a 4.075 ns period immediately.
* Reset (local): `RSTB` low 600-650 ns clears `TICK`; the ring keeps running; `TICK` rises again 2.9 ns after release.

## Why there is no complete grid

* **Candidate `wd` (dlygate ring), 1.62 V group, 15 corners, batch job 3016 s.**
  Reduced values were not produced (the client was stopped, see below), but the
  fleet report is committed (`sim/lockdet-timing/watchdog/rejected-dlygate/report.json`):
  * `ss` at all three temperatures: ngspice aborts the transient with
    `Fatal error ... BSIM4v5 parameter checking ... model phighvt_model.46`
    (`Dsub`/`Pclm` negative) for a `dlygate4sd3_1` pfet. The run reports status
    `pass` yet the waveform is empty. The cell is therefore **not simulable at
    ss** with this PDK pin; `ss_27C_ngspice.log` is kept.
  * `nonconvergence` at tt/125 C, fs/27 C, fs/125 C and sf/125 C.
  * Remaining corners ran 450-2190 s each against 130 s at nominal; the 1.62 V
    group used 3016 s of the fleet's 3600 s whole-job ceiling.
  This candidate is rejected for the grid; its decks, manifests and generator
  are preserved under `rejected-dlygate/` (the committed records `lt-...061032`,
  `...061245`, `...061534` reference its `candidates/*.json`, now there).
* **Candidate `wdb` (29 x `buf_1` ring, same divider)** is the current
  generator output (`gen_watchdog.py`, `candidates/wdb.*`). Its nominal smoke
  could not be collected: `klt sim` writes `save all` ASCII raw plus a JSON copy
  (1.84 GB + 1.67 GB for one corner), the client reached 3.9 GB RSS and was
  killed (twice) with no record. Filed generically as
  `2AMLogic/klayout-tools#3211`. A finer output step is also needed for accuracy
  (the buffer ring read 3.45 ns at 10 ps, 3.58 ns at 25 ps and 4.00 ns at 50 ps;
  `.options trtol=1` brought the 50 ps value to 3.48 ns), which the artifact
  size forbids. No `wdb` timing is claimed.
* The 1.8 V and 1.98 V groups of `wd` were never run (the batch run was stopped
  after the ss defect was found). No complete watchdog record exists.

## Negative controls (actual classification, before any grid)

* `wd-ctl-en` (`wd`, EN held low): `ABSENT_CROSSING`, no values (`lt-20261013-061534-163034`). The same control on `wdb`: `ABSENT_CROSSING` (`lt-20261013-085627-989271`).
* `wd-ctl` (AND2 enable gate: non-inverting loop): `SIM_FAILED`, klt exit 4 with `nonconvergence` on the bistable DC point (`lt-20261013-061245-358912`, `incomplete-not-physical`). It is a failure, not an oscillation classification; kept as evidence.

## Switching current and shared supply

Not measured. Estimate (not measured): a free-running ring plus six toggling
flops draws continuous supply current while enabled and injects supply noise at
the ring frequency and its harmonics; whether that disturbs a shared VCO or
charge-pump supply is a #260/#231 integration question. Gate `EN` when the
watchdog is not needed and give it its own supply branch if the loop shares VDD.

## Backend / client / runner

Backend `klt sim --backend batch` accepted both the smoke and the 15-corner
group. Runner klt 0.7.0 vs client 0.7.1.dev (`version_skew: true`), exit 4
accepted as waveform-only by `locktiming_cli.waveform_only_exit`. Capability
gaps found: artifact size/memory (klayout-tools#3211), and no resume or
per-supply selection in the runner for a partial rerun.

## Reproduction

```
python3 design/lock-detector/timing/gen_watchdog.py        # regenerate wdb files (no PDK write)
W=sim/lockdet-timing/watchdog
python3 sim/run_locktiming.py --candidate $W/candidates/wdb.json=$W/candidates/wdb.spice --points nominal --required-products phase-acq,phase-rel,watchdog --records-dir $W/records   # blocked by klayout-tools#3211
python3 design/lock-detector/timing/grade_combined.py sim/lockdet-timing/phase/records/lt-20261012-220148-142698.json $W/records/lt-20261013-061032-937960.json
```

Local cross-checks: append the inlined deck with `.lib <PDK>/libs.tech/combined/sky130.lib.spice tt`,
`.temp 27`, `.tran 25p 1.5u` and `.meas` TRIG/TARG at 0.9 V on `RAW`/`TICK`.
Phase evidence: `sim/lockdet-timing/phase/README.md`.

## Open items

* Complete 45-point watchdog grid (needs the artifact-size fix or a decks with fewer saved nodes; avoid `dlygate4sd3_1` at ss; choose a step that is accurate for the ring).
* Re-satisfy the phase bands (separate design work) before #260 can start.
