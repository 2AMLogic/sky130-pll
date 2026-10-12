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
