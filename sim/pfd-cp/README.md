# sim/pfd-cp -- standalone PFD + charge-pump campaign (issue #250, part of #247)

Characterizes the **unchanged** `design/pfd-cp/pfd_cp.sch` in isolation, through
its actual ports `VDD GND REF DIV CP`. There is no VCO, loop filter or divider,
and no internal node is forced. It is mechanism evidence only: it cites spec
row 10 (the UP/DN charge-asymmetry half; the ripple-in-lock half is #166) and
gives row 12 prerequisite context (bias/Icp). It measures no assembled-loop
power and ratifies nothing; both rows stay DRAFT.

- `testbench/tb_pfd_cp.sch` -- DUT + supply `V1` + stimulus `VREF`/`VDIV` +
  ideal clamp `VCLAMP` from CP to ground. Positive `i(VCLAMP)` is charge
  delivered into CP (UP); negative is DN.
- `testbench/tb.json` -- the whole campaign contract (the `cp` block, see
  `sim/harness/README.md` "Charge-pump current/charge analysis"): 10 MHz, 50 %
  duty, 100 ps edges, first REF edge at 100 ns, positive offset = DIV later
  than REF, VCTRL/VDD = 0.1..0.9, 15 phase offsets from -25 ns to +25 ns,
  20 settle + 10 integrated periods, 5 ps dump/max step, and the
  operating-point vectors (NB, PB and the RBIAS reference-branch current,
  `@r.xx1.xrbias.rend1[i]`, reported with ngspice's sign). Gate nodes
  `xx1.up` (active high, drives the PMOS switch through `UPB`) and `xx1.dn`
  (active high, gates the NMOS switch) select exclusive-pulse samples.
- `../pfd-cp-resolution/` -- the separately identified **nominal finer-grid
  diagnostic** (tt, 27 degC, 1.8 V; zero and +/-0.1 ns at midrail, 2.5 ps vs
  5 ps). It is its own slug so its record cannot be mistaken for the grid.

The 45-point grid is tt/ff/ss/fs/sf x -40/27/125 degC x 1.62/1.80/1.98 V.
The compliance rule (both plateau magnitudes within 10 % of midrail, expected
signs, contiguous sampled VCTRL interval around 0.5 VDD) is provisional
characterization methodology, not a spec pass; unsampled boundaries are never
interpolated.

## Reproduction

```sh
python3 sim/run_corners.py pfd-cp                     # full 45-point grid, writes a record
python3 sim/run_corners.py pfd-cp-resolution          # nominal 2.5 ps vs 5 ps diagnostic
```

Each point is 135 transients of ~3.1 us at 5 ps, so the full grid is long
enough that it belongs on a fleet, not on a shared dispatch host.

### Execution backend: the batch route and its status (issue #290)

`--executor remote` needs the klayout-tools SSH fleet and **silently degrades
to `local`** on a host that is not provisioned for it (`sim/harness/README.md`,
"Fallback contract"), and `klt sim` corner requests cannot express this
campaign's per-coordinate PULSE stimulus. The harness therefore has a
dedicated route, `--executor batch` (`sim/harness/cp_klt.py`): one `klt sim`
`decks[]` entry per PVT point, run on the Spot batch fleet, with the returned
dumps reduced by the unchanged `cpmeasure` reducer. On a host that exports
`KLT_SIM_BACKEND=batch` it is chosen automatically for this manifest, and
`--executor remote` is refused. A refused or failed submit is reported and
the run exits nonzero; it never falls back to a local run of the grid. See
`sim/harness/README.md`, "Batch-fleet route for `cp`".

**Status as of 2026-10-15: the route is built and unit-tested but has no
successful end-to-end run.** A one-deck probe through the real fleet reached a
spot instance and failed in 25 s because the fleet runner's `klt` does not
accept `decks[]` (`request is missing required field: netlist`; job
`klt-sim-b1f40d6f9ddc`, installed client `klt 0.7.1.dev500+g247e3c89b14b`),
tracked as 2AMLogic/klayout-tools#3303. The nominal-point smoke (tt/27 C/1.80 V)
has therefore **not** been run; no record was minted and nothing ran locally.
Do not run the 45-point grid until a one-point batch smoke has passed.

## Evidence discipline

Records under `records/` are append-only. A rerun mints a new record that
names the one it supersedes (`--supersedes`); an existing record is never
edited or deleted. A coordinate that has not settled is recorded as such and
answered with a new record with a longer manifest window, not an edit.

## Status of the evidence (issue #250)

- `pfd-cp` (45-point grid): **not run.** One nominal point's 135-transient
  sweep costs on the order of 9 hours of CPU (about 4 minutes per 5 ps
  transient), so the grid is roughly 400 CPU-hours and has no working end-to-end route to
  a batch fleet (see above).
- `pfd-cp-resolution`: run once locally (a single nominal unit), record
  `sim/pfd-cp-resolution/records/20261011-011743-f9ceac9.md`. It **failed**:
  ngspice aborted the 2.5 ps diagnostic transients at the +/-0.1 ns offsets
  ("Timestep too small" at `xx1.rstpre`, ~2.05-2.1 us), and the harness marks
  the whole point incomplete, so that record carries no operating-point,
  plateau or charge values. A follow-up needs simulator-option control in the
  `cp` block (none exists today) or a different diagnostic step; a rerun must
  name this record in `--supersedes`.
