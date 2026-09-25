#!/usr/bin/env bash
#
# Harness acceptance test.
#
#   sim/selftest.sh                unit tests ONLY -- headless, launches no ngspice/xschem
#                                   process, whatever PDK the host has installed. This is
#                                   the intentional default (see "Default is headless" below)
#                                   and is what `npm run check:ci` runs.
#   sim/selftest.sh --require-pdk  ALSO opts into the end-to-end PVT smoke + Monte Carlo
#                                   smoke stages (stages 3/4 below), simulating for real via
#                                   ngspice/xschem; fails (instead of skipping) if the PDK is
#                                   not resolvable. This is what `npm run check:all` and the
#                                   nightly/opt-in `pdk-smoke` CI job run.
#   sim/selftest.sh --record       (only takes effect together with --require-pdk) also mint
#                                   evidence records under sim/pdk-smoke/
#   sim/selftest.sh --quick        (only takes effect together with --require-pdk) a single
#                                   typical/27C/nominal PVT point + 2 MC trials instead of the
#                                   full grid
#
# Default is headless: a plain invocation (no flags) NEVER simulates, even on a host
# that has the pinned sky130 PDK installed -- it only runs stage 1's PDK-free unit
# tests and exits. Simulating at all is an explicit opt-in via --require-pdk. This
# is the inverse of this script's original behavior (auto-detect the PDK and simulate
# whenever one happened to be resolvable, skipping only when it was not) -- see
# issue #183: that auto-detect default silently ran the full 45-point pdk-smoke grid
# under a `check:ci` target documented and CI-wired as "headless, no PDK needed",
# on every PDK-equipped dev/agent host, contradicting the documented contract and this
# fleet's own host rule against hand-launched local ngspice grids.
#
# Exit codes: 0 pass (or skipped sim stage), 1 something failed.
#
# Provenance: adapted from 2AMLogic/gf180-pll sim/selftest.sh (source commit
# 3e3814c11ce6f0781ecfbefb0d109981c4e5eb21) per this repo's CLAUDE.md
# harness-bootstrap rule. Deviation: this repo's target experiment is
# `pdk-smoke` (sim/pdk.json's process corners), not gf180-pll's
# `harness-selftest`; gf180-pll's `--corners typical` becomes `--corners tt`
# here (sky130's own corner naming, see sim/pdk.json). The Monte Carlo stage
# (issue #20) has no gf180-pll analogue and is added fresh. The headless-by-
# default inversion (issue #183) has no gf180-pll analogue either.

set -uo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RECORD=0
QUICK=0
REQUIRE_PDK=0
for arg in "$@"; do
  case "${arg}" in
    --record) RECORD=1 ;;
    --quick) QUICK=1 ;;
    --require-pdk) REQUIRE_PDK=1 ;;
    -h|--help) sed -n '2,28p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: ${arg}" >&2; exit 1 ;;
  esac
done

echo "== 1/4 harness unit tests (no PDK required) =="
if ! python3 -m unittest discover -s "${SIM_DIR}/tests" -t "${SIM_DIR}/tests"; then
  echo "FAIL: harness unit tests"
  exit 1
fi

if [ "${REQUIRE_PDK}" -ne 1 ]; then
  echo
  echo "SKIP: simulation stages (2-4/4) -- sim/selftest.sh only simulates when passed"
  echo "      --require-pdk (see --help), regardless of whether this host has the PDK"
  echo "      installed. This keeps a plain invocation -- e.g. 'npm run check:ci' --"
  echo "      headless and free of any ngspice/xschem process on every host."
  echo "      Unit tests passed. Run 'sim/selftest.sh --require-pdk' (or 'npm run"
  echo "      check:all') to exercise the harness end to end."
  exit 0
fi

echo
echo "== 2/4 environment =="
if ! python3 "${SIM_DIR}/run_corners.py" --check-env; then
  echo "FAIL: ngspice/xschem and/or the sky130 PDK are not available"
  exit 1
fi

echo
echo "== 3/4 end-to-end PVT smoke run =="
args=(pdk-smoke)
[ "${QUICK}" -eq 1 ] && args+=(--corners tt --temps 27 --supply-tol 0)
[ "${RECORD}" -eq 1 ] || args+=(--no-write)
# --quick is deliberately a PVT subset; sim/README.md demands a written reason
# before a subset run may be recorded as evidence.
if [ "${QUICK}" -eq 1 ] && [ "${RECORD}" -eq 1 ]; then
  args+=(--subset-reason "sim/selftest.sh --quick: single-point harness smoke test, not a design claim")
fi

if ! python3 "${SIM_DIR}/run_corners.py" "${args[@]}"; then
  echo "FAIL: PVT smoke run"
  exit 1
fi

echo
echo "== 4/4 end-to-end Monte Carlo smoke run =="
mc_args=(pdk-smoke --mc)
[ "${QUICK}" -eq 1 ] && mc_args+=(--mc-trials 2)
[ "${RECORD}" -eq 1 ] || mc_args+=(--no-write)
# --quick is deliberately a trial-count subset of the manifest's monte_carlo
# config; sim/README.md demands a written reason before a subset run may be
# recorded as evidence.
if [ "${QUICK}" -eq 1 ] && [ "${RECORD}" -eq 1 ]; then
  mc_args+=(--subset-reason "sim/selftest.sh --quick: 2-trial harness smoke test, not a design claim")
fi

if ! python3 "${SIM_DIR}/run_corners.py" "${mc_args[@]}"; then
  echo "FAIL: Monte Carlo smoke run"
  exit 1
fi

echo
echo "PASS: harness is functional end to end."
