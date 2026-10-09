# design/lock-detector/ — behavioral reference (no circuit yet)

This directory holds the **executable behavioral reference** for the
proposed `LOCK` contract in
[`spec/decision-records/DR-007-lock-detector-provisional-contract.md`](../../spec/decision-records/DR-007-lock-detector-provisional-contract.md)
(status: proposed; spec row 16 stays DRAFT). It does not yet hold a
schematic, symbol or netlist. Those come from #231, and when they arrive they
follow the `design/README.md` file shape alongside this reference.

| File | What it is |
|---|---|
| `lockdet_ref.py` | Deterministic, event-driven model of `LOCK` from `REF`/`FBCLK`/`RESETB` edge streams plus an independent watchdog tick. Integer-picosecond time. Stdlib only. |
| `tests/test_lockdet_ref.py` | Literal expected `LOCK` transitions for every case DR-007 lists, plus the two negative controls (frequency qualification removed, watchdog removed). |
| `tests/test_harness_comparison.py` | Runs `sim/harness/measure.py::lock_time` with `sim/pll-lock/testbench/tb.json`'s lock block (both read-only) on the same synthetic streams. Shows where harness frequency-lock and hardware `LOCK` agree and where they differ. |

Run:

```sh
python3 -m unittest discover -s design/lock-detector/tests -p 'test_*.py'
```

`npm run test:unit` runs these tests too.

**Evidential scope.** These are behavioral-reference results on ideal edges.
They are not circuit, PVT or silicon evidence, and they are not row 16
evidence for `measurements/report.md`. The model runs at the nominal values in
DR-007 Table 1. The PVT bands a circuit must meet (Table 2) are checked here
only as arithmetic invariants.
