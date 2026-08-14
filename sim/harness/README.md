# sim/harness/ — testbench manifest format

`sim/run_corners.py <slug>` runs the experiment declared at
`sim/<slug>/testbench/tb.json` across a PVT (process/voltage/temperature)
point matrix and writes an append-only evidence record — see `sim/README.md`
for the record schema and directory conventions this package writes into.

Stdlib only, no virtualenv. Package layout:

```
sim/harness/
  pdk.py       resolve the sky130 PDK install (PDK_ROOT/PDK, volare, sim/pdk.json)
  corners.py   build the PVT point matrix from a manifest + CLI overrides
  runner.py    xschem-netlist once, patch per point, run ngspice, judge pass/fail
  report.py    render the append-only records/<record-id>.md evidence record
  cli.py       argparse glue: --check-env / --print-env / --list / <slug>
```

This is deliberately scoped down from `2AMLogic/gf180-pll`'s own
`sim/harness/` (source commit `3e3814c11ce6f0781ecfbefb0d109981c4e5eb21`,
which this package's shape is adapted from per this repo's `CLAUDE.md`
harness-bootstrap rule): gf180-pll's package carries PLL-specific
derived-measurement modules (lock detection, jitter reduction, divider-ratio
checks, ...) because it has a real PLL schematic to measure. sky130-pll does
not yet — issue #2 stands up the harness plumbing only, unblocked of spec
ratification (#1). Measurement-specific reduction modules are added by later
issues once there is a PLL netlist.

## `tb.json` manifest schema

```json
{
  "schema": "sky130-pll.harness.tb/1",
  "claim": "one-sentence statement of what this experiment substantiates",
  "schematic": "tb_foo.sch",
  "corner_pattern": "regex, one capture group ending right before the corner token",
  "supply_pattern": "regex, one capture group ending right before the supply value",
  "process_corners": ["tt", "ss", "ff"],
  "temps_c": [-40, 27, 125],
  "supply_nominal": 1.8,
  "supply_tolerance": 0.1
}
```

- **`schematic`** — path relative to the manifest's own `testbench/`
  directory. Netlisted once per run via `xschem -x -n -s -q --rcfile
  sim/xschemrc`; the corner/temperature/supply axes are then applied by
  regex-patching the netlisted text, not by re-netlisting per point (the DUT
  topology does not change across a PVT sweep).
- **`corner_pattern` / `supply_pattern`** — each a Python regex with exactly
  one capturing group: the text immediately *before* the value the harness
  overwrites. `runner.patch_netlist` replaces `group(1) + <new value>` for
  every match. This keeps the harness generic — it never needs to understand
  the DUT's topology, only where in its own netlisted text the process
  corner (a `.lib ... <corner>` line) and the supply (a voltage source's DC
  value) live. Temperature is not pattern-based: a `.temp <T>` card is always
  inserted immediately before the netlist's final, standalone `.end` line.
- **`process_corners`** — must be a subset of `sim/pdk.json`'s
  `process_corners` list (the corners the installed sky130 PDK's combined
  ngspice library actually defines `.lib` sections for).
- **`temps_c`** / **`supply_nominal`** / **`supply_tolerance`** — the default
  PVT grid for this experiment. Supply points are
  `nominal*(1-tol), nominal, nominal*(1+tol)` (tolerance `0` collapses to a
  single nominal point). A CLI override (`--corners`/`--temps`/
  `--supply-tol`) narrows this for a fast pass, and requires
  `--subset-reason` to be recorded when writing evidence — see
  `sim/README.md`'s subset-justification rule.

## Running

```sh
python3 sim/run_corners.py --check-env        # PDK + ngspice + xschem availability
python3 sim/run_corners.py --print-env        # `export PDK_ROOT=... PDK=...` for eval
python3 sim/run_corners.py --list             # known experiment slugs
python3 sim/run_corners.py pdk-smoke          # full manifest grid, writes a record
python3 sim/run_corners.py pdk-smoke --no-write   # run, print pass/fail, write nothing
python3 sim/run_corners.py pdk-smoke \
  --corners tt --temps 27 --supply-tol 0 \
  --subset-reason "fast selftest pass, not a design claim"
```

Per-point pass/fail is a **plumbing** criterion, not a design measurement:
ngspice must exit 0, print its analysis-completion marker, and emit no
`Error:` line for that PVT point's patched netlist. A campaign that measures
an actual circuit quantity (once a PLL schematic exists) extends `runner.py`
/ `report.py` with its own reduction — this harness's job is to guarantee the
netlist-patch-run-record loop itself is trustworthy underneath that.
