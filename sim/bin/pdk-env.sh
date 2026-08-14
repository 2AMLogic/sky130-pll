# Source me: exports the sky130 PDK environment this repo's harness expects.
#
#   source sim/bin/pdk-env.sh
#   xschem --rcfile "$XSCHEM_RCFILE" sim/pdk-smoke/testbench/tb_pdk_smoke.sch
#   ngspice ...            # remember to copy sim/spiceinit to ./.spiceinit
#
# Resolution order (single source of truth is sim/run_corners.py --print-env,
# via sim/harness/pdk.py):
#   PDK_ROOT env -> `volare path` -> default_pdk_root from sim/pdk.json
#   PDK env      -> variant from sim/pdk.json
#
# Not needed to run the corner runner itself: sim/run_corners.py resolves the
# PDK on its own. This is for driving xschem/ngspice by hand.
#
# Provenance: adapted from 2AMLogic/sky130-bandgap sim/bin/pdk-env.sh (source
# commit a8c4147a6cdf7b7fad467417cbc7b83178ccc9c6) per this repo's CLAUDE.md
# harness-bootstrap rule -- the sourcing pattern is unchanged; it now shells
# out to sim/run_corners.py (this repo's harness entry point, following
# 2AMLogic/gf180-pll's naming) instead of sky130-bandgap's sim/bin/corner-run.py.

_pdk_env_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")" && pwd)"
_pdk_env_out="$(python3 "${_pdk_env_dir}/../run_corners.py" --print-env)" || {
  echo "pdk-env.sh: run_corners.py --print-env failed (is the pinned PDK installed?)" >&2
  unset _pdk_env_dir _pdk_env_out
  return 1 2>/dev/null || exit 1
}
eval "${_pdk_env_out}"
echo "PDK_ROOT=${PDK_ROOT}"
echo "PDK=${PDK}"
echo "SKY130_MODEL_LIB=${SKY130_MODEL_LIB}"
echo "XSCHEM_RCFILE=${XSCHEM_RCFILE}"
unset _pdk_env_dir _pdk_env_out
