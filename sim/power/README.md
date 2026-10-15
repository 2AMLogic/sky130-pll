# sim/power/ -- supply-current / power campaign (issue #233)

Measures the sky130 supply current and power of the open-loop blocks over the
ratified PVT grid, so `spec/target-spec.md` row 12 (Power, DRAFT) has measured
data a future decision record can argue a budget from. It ratifies nothing and
proposes no number.

Blocks: `vco_ring5`, `divider_intN` (N = 4 and N = 64), `pfd_cp` (1 MHz and
25 MHz reference, the row 3 range extremes). The loop filter is passive and
draws no supply current. The totals are **sums of separately simulated
open-loop blocks, not a loop measurement** (the closed loop still does not
lock, #98).

## Why this is not a `tb.json` campaign

`sim/run_corners.py` has no executor for the batch fleet (`--executor remote`
falls back to a local run when the fleet is not configured, which is not
acceptable for a 4 x 45-point grid on a shared host), and its reducer
(`sim/harness/measure.py`) reduces node *voltages*. This campaign is a
`klt sim` request per block instead (the fleet-native path; `klt sim` splits
the 45 corners across the batch backend), plus a small reducer for the branch
current. It therefore has **no `testbench/tb.json`**, so `run_corners.py
--list` does not list it, and its records carry their own `**Spec row(s)**`
line (which is what `measurements/aggregate.py` reads).

## Files

```
sim/power/
  build.py          regenerates everything under testbench/ from one stage table
  reduce.py         waveform -> whole-cycle mean supply current (pure; unit-tested)
  shard.py          splits a request into batch-fleet shards that partition the 45 points
  mint.py           klt reports (or shard reports, merged) -> append-only record + reduced data + snapshots
  testbench/
    tb_power_<block>.sch     xschem testbench (generated)
    <block>.body.spice       klt circuit body (generated)
    <block>.stages.json      stage table the reducer reads (generated)
    <block>.request.json     the klt sim request: 45-point grid (generated)
  records/<id>.md            evidence records (append-only)
  reports/<id>/              klt reports (verbatim) + reduced.json
  netlist-snapshots/<id>/    the inputs that were simulated
```

`python3 sim/power/build.py --check` fails if a committed generated file is
stale (needs xschem + the PDK; no simulation).

## How a stage works

Each block's testbench runs one transient per PVT point, staged in time: an
**idle** stage (block held quiescent: VCO at VCTRL = 0 V, divider clock gated
off, PFD inputs low) followed by **active** stages at stated operating points.
`reduce.py` averages `i(V1)` over a whole number of cycles of the stage's
alignment node. **Static** power is the idle stage; **dynamic** is derived as
active minus idle (a difference, not a separate simulation).

## Running (do not hand-launch ngspice grids on the shared host)

The batch fleet kills a whole job at 3600 s and caps the fleet at 8 instances,
and `klt sim --hosts` only shards the local backends, so each 45-point request
is split client-side into shards that partition the grid (`shard.py`; measured
serial cost per point on a shared worker: vco 64 s, divider-n4 95 s, pfd-cp
86 s, divider-n64 300 s -> 5 shards per block by process corner, 15 for
divider-n64 by process x supply). The grid, stimulus and averaging windows are
unchanged; only `options.timeout_s` is lowered per shard so klt's serial bound
fits the ceiling.

```sh
S=/path/to/scratch
python3 sim/power/shard.py --out $S
# verify ONE shard end to end first, then the rest (<= 4 in flight):
klt sim $S/pfd-cp.shard00.request.json --backend batch --format json \
    -o $S/pfd-cp.shard00.out > $S/pfd-cp.shard00.report.json
# then the remaining shards, at most 4 submitted at once (fleet cap is 8 instances,
# shared with other sweeps); a refused submit is reported, never run locally:
for r in $S/*.shard*.request.json; do klt sim $r --backend batch --format json \
    -o ${r%.request.json}.out > ${r%.request.json}.report.json; done   # serial; or 4 at a time
python3 sim/power/mint.py --reports-dir $S [--supersedes <id>]
python3 measurements/aggregate.py --out measurements/report.md
```

Each shard's report must be saved as `$S/<block>.shard<NN>.report.json`;
`mint.py` merges them and refuses a duplicated PVT point. It records every
fleet job id.

The requests carry `"backend": "batch"`; `KLT_SIM_BACKEND` / the batch fleet
configuration come from the environment. The fleet refuses a client whose
`klt` version differs from the runner's; the record states which client was
used. The waveform dumps stay in the scratch directory (not committed,
`sim/README.md`'s retention policy).

## Provenance

Testbench wiring and netlisting adapt `sim/vco-supply-pushing/` and
`sim/harness/runner.py` (this repo); the edge extractor is
`sim/harness/measure.py::edge_times`; the record layout follows
`sim/README.md` / `sim/harness/report.py`.
