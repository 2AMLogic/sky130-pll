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
  mint.py           klt reports -> append-only record + reduced data + snapshots
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

```sh
for b in vco divider-n4 divider-n64 pfd-cp; do
  klt sim sim/power/testbench/$b.request.json --backend batch --format json \
      -o /path/to/scratch/$b-out > /path/to/scratch/$b.report.json
done
python3 sim/power/mint.py --reports-dir /path/to/scratch [--supersedes <id>]
python3 measurements/aggregate.py --out measurements/report.md
```

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
