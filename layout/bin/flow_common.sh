#!/usr/bin/env bash
# layout/bin/flow_common.sh -- shared setup/teardown boilerplate for the
# layout/bin/run-*-flow.sh scripts (run-trivial-cell-flow.sh,
# run-pll-layout-flow.sh).
#
# Sourced, not executed: it provides functions that operate on the caller's
# own $KLT / $PDK_VARIANT / $REPO_ROOT variables (already assigned by the
# caller before sourcing this file) and, as a side effect, set $RECORD_ID /
# $OUT_DIR for the caller to use. This mirrors the analogous factoring PR #63
# did for the two record-rendering Python scripts
# (layout/bin/render_common.py) -- the same duplicated shape here is the
# shell flow scripts that drive those renderers.
#
# Usage (from a run-*-flow.sh script, after its own `set -euo pipefail` and
# LAYOUT_DIR/REPO_ROOT/KLT/PDK_VARIANT assignments):
#
#   source "$LAYOUT_DIR/bin/flow_common.sh"
#   SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
#
#   flow_require_klt "$SCRIPT_NAME"
#   flow_require_pdk "$SCRIPT_NAME"
#
#   flow_new_record_id            # sets RECORD_ID
#   flow_setup_out_dir "$SCRIPT_NAME" "$SOME_BASE_DIR"   # sets OUT_DIR, mkdir -p's it, echoes the "record ... -> ..." line
#   ...
#   flow_write_latest "$SOME_BASE_DIR"   # writes reports/LATEST under the base dir

# Exit 1 with an error message if $KLT is not an executable file.
flow_require_klt() {
  local script_name="$1"
  if [[ ! -x "$KLT" ]]; then
    echo "$script_name: $KLT not found -- run layout/bin/setup-venv.sh first" >&2
    exit 1
  fi
}

# Exit 1 with an error message if $PDK_VARIANT does not resolve via `klt pdk find`.
flow_require_pdk() {
  local script_name="$1"
  if ! "$KLT" pdk find --pdk "$PDK_VARIANT" >/dev/null; then
    echo "$script_name: no resolvable $PDK_VARIANT PDK -- see sim/pdk.json for the pin" >&2
    exit 1
  fi
}

# Set RECORD_ID from the current UTC timestamp and $REPO_ROOT's short SHA.
flow_new_record_id() {
  local ts_utc short_sha
  ts_utc="$(date -u +%Y%m%d-%H%M%S)"
  short_sha="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
  RECORD_ID="${ts_utc}-${short_sha}"
}

# Set OUT_DIR to "$2/reports/$RECORD_ID", create it, and echo the
# "record $RECORD_ID -> $OUT_DIR" progress line. Requires RECORD_ID to
# already be set (see flow_new_record_id).
flow_setup_out_dir() {
  local script_name="$1" base_dir="$2"
  OUT_DIR="$base_dir/reports/$RECORD_ID"
  mkdir -p "$OUT_DIR"
  echo "$script_name: record $RECORD_ID -> $OUT_DIR"
}

# Write the "latest record" pointer under "$1/reports/LATEST". Requires
# RECORD_ID to already be set.
flow_write_latest() {
  local base_dir="$1"
  echo "$RECORD_ID" > "$base_dir/reports/LATEST"
}
