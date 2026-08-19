#!/usr/bin/env bash
# Source or run me: creates/refreshes layout/.venv with the pinned `klt`
# build from layout/requirements.txt.
#
#   layout/bin/setup-venv.sh          # create if missing, otherwise no-op
#   layout/bin/setup-venv.sh --force  # reinstall even if .venv/bin/klt exists
#
# Provenance: adapted from 2AMLogic/sky130-bandgap layout/bin/setup-venv.sh
# (source commit b24b40485ff2a1a53a7eeb2cd6c4beadd1ef33c6) per this repo's
# CLAUDE.md harness-bootstrap rule, including its `--force-reinstall` install
# step. That flag is load-bearing whenever requirements.txt pins `klt` by git
# commit (it has since issue #46, see that file's header): upstream has not
# bumped the package version, so two different commits both report
# `klt 0.2.0` and pip would consider an already-installed build up to date --
# silently leaving the old `klt` in place after a pin bump. It was dropped
# while this repo pinned a plain PyPI version, which does not have that
# failure mode; it is back for the same reason bandgap has it.
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
"$VENV/bin/pip" install --quiet --force-reinstall -r "$LAYOUT_DIR/requirements.txt"

echo "setup-venv.sh: installed"
"$VENV/bin/klt" --version
"$VENV/bin/klt" pdk find --pdk sky130A || {
  echo "setup-venv.sh: WARNING: no resolvable sky130A PDK install found." >&2
  echo "  See sim/pdk.json / docs/environment-setup.md for this repo's pinned install command." >&2
}
