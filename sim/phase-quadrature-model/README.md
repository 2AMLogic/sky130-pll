# sim/phase-quadrature-model — behavioral study of the proposed I/Q ÷2

Issue #344 (operator-selected follow-up for #332). A small, deterministic,
**PDK-free and SPICE-free** event/timing model of the two-flip-flop I/Q ÷2
that `DR-010` (Proposed) and `docs/phase-output-proposal.md` rely on for a
quarter-cycle `CLK90`. It qualifies assumptions; it selects nothing and
ratifies nothing (rows 2/14/15 stay DRAFT, row 9 and its recorded misses are
unchanged).

## Topology modelled

- FF_I: rising-edge flop on the 2x clock, `D = NOT Q_Q`, output `CLK`.
- FF_Q: falling-edge flop on the 2x clock, `D = Q_I`, output `CLK90`.
- Feedback counter input is `CLK`. `RESETB` is asynchronous, active low, forces
  both flops to 0; the first clock edge at/after release is the first captured
  edge (whether an edge *exactly at* release counts is a model parameter).
- Ideal relation (closed form, not from the model): 2x period `T2`, high
  fraction `D` → output period `2·T2`; `CLK90` lags `CLK` by `D·T2`, i.e.
  `180·D` degrees of the output period (`D=0.5` → 90°, 45 % → 81°, 55 % → 99°).

## Files

| File | Role |
|---|---|
| `model.py` | event model, measurement, closed-form helpers, the "assumed perfect quarter-cycle" defeating-control generator |
| `run_cases.py` | declared case matrix, run caps, report renderer, `--check` |
| `test_model.py` | analytical-control, startup/reset, clock-absence and defeating-control tests |
| `records/<id>.md` | append-only executed reports |

## Commands

```
python3 sim/phase-quadrature-model/run_cases.py                       # print report
python3 sim/phase-quadrature-model/run_cases.py --record-id ID --out sim/phase-quadrature-model/records/ID.md
python3 sim/phase-quadrature-model/run_cases.py --check sim/phase-quadrature-model/records/ID.md
python3 -m unittest discover -s sim/phase-quadrature-model -p 'test_*.py'   # also part of `npm run test`
```

`--check` re-renders from the record's own ID and fails on any drift. A record
names the `model.py`/`run_cases.py` hashes it was produced by, so editing
either later makes `--check` of an older record fail **by design**: mint a new
record naming the one it supersedes (never edit or delete a record).

## Not modelled

Metastability, transistor behaviour, PVT, loading, supply coupling and silicon
jitter. Setup/recovery windows are *flagged*, with parameters that are unknown
for this design, and resolved deterministically; a flag is not a physical
prediction. The 45/55 % duty cases are analytical controls, not characterized
VCO distributions or ratified bounds. No SPICE, PDK job or remote compute is
used.
