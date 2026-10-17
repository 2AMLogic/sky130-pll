# Environment setup

Bootstrap steps for the open-source analog flow used by this repo: xschem
(schematic capture / netlisting) + ngspice (simulation) against the sky130
PDK (fetched/managed via [ciel](https://github.com/fossi-foundation/ciel)), plus
[klayout-tools](https://github.com/2AMLogic/klayout-tools) (`klt`) for the
layout-side DRC/LVS flow.

**Provenance.** This doc is adapted from `2AMLogic/sky130-bandgap`'s
`docs/environment-setup.md`
(source commit `7b88134ba17cd6536e389f45b3e8a512d6245b15`), per this repo's
`CLAUDE.md` harness-bootstrap rule (mirror the sky130 plumbing from that repo
rather than reinventing it). Deviations from that source: this repo's smoke
testbench lives under `sim/pdk-smoke/testbench/` rather than `design/`
(`design/` here is reserved for the PLL schematic itself — see
`sim/README.md`), the corner-runner entry point follows `2AMLogic/gf180-pll`'s
`sim/run_corners.py` naming (issue #2's own Part B instruction), and a `klt`
layout-flow section is added (sky130-bandgap's own layout bootstrap post-dates
its `docs/environment-setup.md`, so this is written fresh from
`layout/README.md`'s own quick-start rather than copied).

## Toolchain versions (recorded 2026-08-13, this sandbox)

| Tool | Version | Install path |
|---|---|---|
| xschem | `XSCHEM V3.4.7` | `/opt/homebrew/bin/xschem` (Homebrew) |
| ngspice | `ngspice-47` | `/opt/homebrew/bin/ngspice` (Homebrew) |
| ciel | `2.6.1` | `pip install ciel==2.6.1` (pinned; not the retired volare) |
| klayout-tools (`klt`) | `0.2.0` | `~/.local/bin/klt` (installed via `uv tool install klayout-tools`, or `layout/bin/setup-venv.sh` for a repo-local pin) |

Verify before reinstalling anything:

```sh
xschem -v         # expect: XSCHEM V3.4.7 ...
ngspice --version # expect: ngspice-47 ... (ngspice-46 also verified to work)
ciel --version    # expect: 2.6.1
klt --version     # expect: klt 0.2.0
```

## 1. Verify xschem works headlessly

```sh
xschem -n -q -x /opt/homebrew/share/doc/xschem/examples/nand2.sch -o /tmp/xschem_check
```

This should exit 0 and write a `.spice` netlist to `/tmp/xschem_check` with no
errors printed. It needs no PDK wiring — a bare toolchain sanity check.

## 2. Fetch + enable the sky130 PDK via ciel

```sh
ciel ls-remote --pdk-family sky130   # lists open_pdks build commits, newest first
ciel enable --pdk-family sky130 -l sky130_fd_pr f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7
```

**Recorded PDK version (pinned, not "latest"), matching `sim/pdk.json`:**

- PDK family: `sky130`
- open_pdks build commit: `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`
- Chosen because: this is the open_pdks commit the 2AM Logic sky130 canaries
  re-pinned to together (#295), after the previous pin lost its volare release
  feed. Keeping every canary on one build keeps model/PVT provenance
  consistent. Records made before the re-pin name the older revision
  (`c6d73a35f524070e85faff4a6a9eef49553ebc2b`); they are append-only and are
  not rewritten.

After `ciel enable`, confirm the variant resolved:

```sh
ls -la ~/.ciel | grep sky130
cat ~/.ciel/sky130A/SOURCES    # expect: open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7
```

This repo standardizes on the **`sky130A`** variant (same as sky130-bandgap).

## 3. Environment convention: `PDK_ROOT` / `PDK`

Export these two variables in any shell before running xschem/ngspice against
sky130 in this repo:

```sh
export PDK_ROOT="$HOME/.ciel"   # -> the ciel-managed PDK store root
export PDK=sky130A
```

Verify:

```sh
echo "$PDK_ROOT"          # e.g. /Users/<you>/.ciel
echo "$PDK_ROOT/$PDK"     # must exist and be a real (symlinked) directory
ls "$PDK_ROOT/$PDK/libs.tech/ngspice/sky130.lib.spice" 2>/dev/null \
  || ls "$PDK_ROOT/$PDK/libs.tech/combined/sky130.lib.spice"   # model include file
```

`sim/bin/pdk-env.sh` wraps this (see `sim/README.md` and
`sim/harness/README.md`) — `source sim/bin/pdk-env.sh` resolves and exports
the same two variables via `sim/run_corners.py --print-env`, so interactive
and scripted use share one resolution path.

## 4. Smoke test: xschem netlist -> ngspice run against sky130 models

`sim/pdk-smoke/testbench/tb_pdk_smoke.sch` is a throwaway circuit — a 1:1
resistor divider built from two `sky130_fd_pr__res_generic_po` primitives
across a fixed DC source — used only to prove the toolchain end-to-end. It
carries no PLL design content, spec values, or measurement data (per
`CLAUDE.md`: the supply flavor is an open question pending #1, so this
testbench does not encode any ratified supply as a design commitment — the
1.8 V source here is an arbitrary smoke-test bias, not a spec claim).

```sh
export PDK_ROOT="$HOME/.ciel"
export PDK=sky130A

# 1. Netlist the schematic with xschem (headless, no X server needed)
xschem -x -n -s -q --rcfile "$PDK_ROOT/$PDK/libs.tech/xschem/xschemrc" \
  -o /tmp/pdk-smoke sim/pdk-smoke/testbench/tb_pdk_smoke.sch

# 2. Run the netlist through ngspice (operating-point analysis)
cp sim/spiceinit /tmp/pdk-smoke/.spiceinit
(cd /tmp/pdk-smoke && ngspice -b tb_pdk_smoke.spice)
```

Expected result: the run completes with exit code 0, resolves
`.lib $::SKYWATER_MODELS/sky130.lib.spice tt` to an absolute path under
`$PDK_ROOT/$PDK/libs.tech/combined/`, and prints an operating-point node
voltage table — no `error` lines. `sim/run_corners.py pdk-smoke` runs this
same testbench through the PVT corner harness and writes the append-only
evidence record described in `sim/README.md`.

## 5. Layout flow: `klt` DRC/LVS smoke proof

```sh
layout/bin/setup-venv.sh                     # once, or after a requirements.txt bump
layout/.venv/bin/klt pdk find --pdk sky130A   # sanity-check the PDK resolves
layout/bin/run-trivial-cell-flow.sh           # gen -> drc -> extract -> lvs -> report
```

See `layout/README.md` for what this proves: a DRC-clean trivial cell, a
DRC negative control (deliberately illegal geometry) that must come back
`violations`, an LVS match against a known-good reference, and two LVS
negative controls that must each report `mismatch`. The run fails if any of
those five verdicts flips.

## Troubleshooting

- **`SKYWATER_MODELS: unable to resolve variable`** / `.lib` path is
  literally `$::SKYWATER_MODELS/...` in the emitted netlist (not expanded to
  a real path): the `code.sym` block emitting the `.lib` line needs
  `format="tcleval( @value )"` so xschem evaluates the Tcl variable at
  netlist time — see `sim/pdk-smoke/testbench/tb_pdk_smoke.sch` for the
  working pattern.
- **`Warning: PDK_ROOT environment variable is set but path not found`**
  (printed by the PDK's own `xschemrc`): `$PDK_ROOT`/`$PDK` aren't exported in
  the shell running `xschem`, or `ciel enable` hasn't been run for the
  recorded hash above.
- **xschem opens a GUI window instead of running headless**: pass `-x`
  (no X) in addition to `-n -q`.
- **`klt pdk find --pdk sky130A` fails**: same PDK pin as above — run
  `ciel enable --pdk-family sky130 -l sky130_fd_pr f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7` first.
