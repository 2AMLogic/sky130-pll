#!/usr/bin/env bash
# Source or run me: creates/refreshes layout/.venv with the pinned `klt`
# build from layout/requirements.txt.
#
#   layout/bin/setup-venv.sh          # create if missing, otherwise no-op
#   layout/bin/setup-venv.sh --force  # reinstall even if .venv/bin/klt exists
#
# Provenance: adapted from 2AMLogic/sky130-bandgap layout/bin/setup-venv.sh
# (source commit b24b40485ff2a1a53a7eeb2cd6c4beadd1ef33c6) per this repo's
# CLAUDE.md harness-bootstrap rule. Deviation: this repo's requirements.txt
# pins a plain PyPI version (klayout-tools==0.2.0), not a git commit -- see
# that file's own header -- so this script's install step is a normal
# `pip install -r`, without sky130-bandgap's `--force-reinstall` workaround
# (that workaround exists because pinning by git commit can leave pip
# thinking an already-installed same-version build is up to date; a PyPI
# version pin does not have that failure mode).
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$LAYOUT_DIR/.venv"

if [[ -x "$VENV/bin/klt" && "${1:-}" != "--force" ]]; then
  echo "setup-venv.sh: $VENV already has klt installed (pass --force to reinstall)"
  "$VENV/bin/klt" --version
  exit 0
fi

echo "setup-venv.sh: creating $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$LAYOUT_DIR/requirements.txt"

echo "setup-venv.sh: installed"
"$VENV/bin/klt" --version
"$VENV/bin/klt" pdk find --pdk sky130A || {
  echo "setup-venv.sh: WARNING: no resolvable sky130A PDK install found." >&2
  echo "  See sim/pdk.json / docs/environment-setup.md for this repo's pinned install command." >&2
}
