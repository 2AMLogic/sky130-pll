# LOCK timing measurement contract

Pure-arithmetic contract for LOCK-detector timing feasibility (issue #273,
part of #259). Implemented by `sim/harness/locktiming.py`, tested by
`sim/tests/test_locktiming.py`. There is no simulator execution, circuit or
physical evidence here: a later runner produces the inputs described below,
and physical campaigns select candidates. DR-007 stays proposed (row 16
DRAFT); the bands are constants in the module and are never relaxed.

## Manifest (`sky130-pll.lockdet-timing.manifest/1`)

`validate_manifest(m)` raises `LockTimingError` on any violation.

| field | content |
| --- | --- |
| `product_id`, `candidate_id` | non-empty strings |
| `units` | exactly `{time: s, voltage: V, temperature: C, capacitance: F}` |
| `inventory` | non-empty `cells` (`name`, `drive`, `stage`), unique `taps`, `dividers` |
| `measurement.load_f`, `slew_s` | load capacitance (>= 0), input slew (> 0) |
| `measurement.acq`, `.rel` | `{input, tap, threshold_v, input_edge, tap_edge}`; delay = first in-window input crossing to the next tap crossing |
| `measurement.tick`, `.raw`, `.startup` | `{signal, threshold_v, edge}` (`rising`/`falling`) |
| `windows` | `enable_s`, `settle_s`, `window_start_s`, `window_stop_s`, `step_s`, `timeout_s`; `window_start_s >= enable_s + settle_s` |
| `grid` | exactly the 45 coordinates: tt/ff/ss/fs/sf x -40/27/125 C x 1.62/1.8/1.98 V, as `{process, temp_c, vdd_v}` |

## Waveform input

Per coordinate, the runner supplies
`{"coord": {...}, "sim_ok": bool, "waveforms": {name: {"t": [s], "v": [V]}}}`.
Timestamps must be finite and strictly increasing with >= 2 samples; values
finite. Crossings are linearly interpolated; rising means
`v[i-1] < thr <= v[i]`, falling `v[i-1] > thr >= v[i]` (a sample exactly on the
threshold crosses once, at that sample).

## Reduced point (`reduce_point`)

Row keys: `coord`, `status`, `error`, `w_acq_s`, `w_rel_s`, `tick_s`
(divided watchdog period), `raw_period_s` (diagnostic only), `startup_latency_s`
(first crossing after `enable_s`, measured from it). Periods are
(last - first)/(n - 1) over same-edge crossings inside the window.

| status | meaning |
| --- | --- |
| `OK` | all quantities valid |
| `ABSENT_CROSSING` | a required crossing (or a second one for a period) is missing, e.g. no oscillation |
| `INSUFFICIENT_SETTLING` | waveform does not cover the window, or the window starts before enable + settle |
| `SIM_FAILED` | `sim_ok` is not `true` |
| `MALFORMED` | rejected waveform/coordinate/missing signal; message in `error` |

Non-`OK` rows carry no measured values.

## Candidate grading (`grade_candidate`)

`complete` is true only if all 45 coordinates appear exactly once with `OK`.
Otherwise `missing`, `duplicates` (excluded from aggregates), `unexpected`
and `failed` list what is wrong. Per-check verdicts are `PASS`, `MISS`
(a measured value is outside) or `INCONCLUSIVE` (evidence missing); a measured
`MISS` is reported even when incomplete, but `PASS` requires completeness.

* `w_acq` in [1.5, 4.0] ns, `w_rel` in [4.5, 10.0] ns, `tick` in [125, 500] ns (inclusive)
* `hysteresis_max_acq_lt_min_rel`: max(W_acq) < min(W_rel) (strict)
* `rel_ceiling_lt_12ns`: max(W_rel) < 12 ns (strict)

`diagnostic_raw_period_s` and `startup_latency_s` are (min, max) ranges, not graded.

## Handoff (`handoff(results, required_products)`)

Requires exactly three distinct product ids. Returns `scope` (`FULL` or
`SUBSET`), `products_present`, `products_absent`, `handoff_ready`. A subset
is never ready; a full set is ready only if each product has one candidate
result with verdict `PASS`.

## Fixtures

The synthetic builders in `sim/tests/test_locktiming.py` (`manifest`,
`waves`, `point`, `rows`) are the representative fixtures for the runner
and both physical campaigns.

## Runner (`sim/run_locktiming.py`, issue #274)

Infrastructure only: no circuit and no physical evidence ships with it.
Implemented by `sim/harness/locktiming_cli.py`, tested PDK-free by
`sim/tests/test_locktiming_cli.py` (fake `klt`, captured-report style fixtures).

A candidate is `MANIFEST.json=NETLIST.spice`. The netlist carries the fixed
stimulus, the DUT and one `@VDD@` placeholder for the supply value; it must not
hold `.control`, `.end` or a process `.lib` card (any `.lib`/`.end` line is
stripped; klt owns the process axis, `.control` and capture). The runner adds
`.save` for the manifest's traces. Grouping is explicit: one `klt sim` request
per (product, candidate) x supply, process x temperature as klt corners; the
group key `<product>.<candidate>_<vdd>v` names its work and evidence directory.

```
# plan only: no job, no PDK, no klt needed (nominal = tt/27C/1.8V, a labelled SUBSET_POINTS)
python3 sim/run_locktiming.py --candidate m1.json=n1.spice --candidate m2.json=n2.spice --dry-run
python3 sim/run_locktiming.py --candidate m1.json=n1.spice --points all --dry-run   # 45 coords

# physical smoke (later circuit children; needs klt, KLT_BATCH_PROVISION_SCRIPT, fleet)
python3 sim/run_locktiming.py --candidate m1.json=n1.spice --points nominal \
    --required-products pA,pB,pC
```

`--required-products` must name exactly three distinct ids; a wrong count is
refused before anything is submitted.

Rules the runner enforces:

* Failed submission, capacity exhaustion, a non-usable klt exit code (not 0
  or 3, recorded as `exit_code`), version refusal, missing report,
  missing corner/trace and truncated or non-uniform waveforms become explicit
  `SIM_FAILED`/`MALFORMED`/`INSUFFICIENT_SETTLING` rows with a `reason`; the
  candidate stays `INCONCLUSIVE`. No local simulation fallback, no ngspice loop.
  Exit 4 ("nothing checked") is usable only when the report says the sole
  reason is `no_requested_measurements` and every corner passed: the request
  deliberately declares no klt measurements, so a real batch run returns 4
  (found by the first physical smoke, `phase/records/lt-20261012-154414-443931`).
* Records are JSON (`sky130-pll.lockdet-timing.record/1`) in
  `sim/lockdet-timing/records/`, append-only; the request, body netlist and
  report of every group are kept under `records/<record-id>/<group>/`. Each
  carries input/netlist hashes, PDK pin, job ids, engine and runner/client klt
  versions (`version_skew: true` when they differ), `points_scope` and the
  `handoff` scope. A rerun of the same matrix
  must pass `--supersedes <record-id>`; an existing file is never overwritten.
* `evidence_class` is `physical` only if every group has a batch job id and no
  group failure. `--fixture` forces `fixture` and requires an explicit
  `--records-dir`, so test output cannot enter the real records.
* The request reuses `fmax_klt.build_request` (runner_version_check `warn`).
  Whether the fleet runner supports this campaign (per-coordinate transient
  sweeps, runner/client skew: klayout-tools #3097, #2948, #2851) is **not**
  established here; the physical children must verify it with a real run.
