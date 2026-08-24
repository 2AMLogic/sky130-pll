#!/usr/bin/env bash
# layout/bin/run-trivial-cell-flow.sh -- the DRC/LVS flow's gating proof
# (issue #2): generate a trivial known-good cell, run it through
# `klt drc`/`klt extract`/`klt lvs` headlessly, and check the reports into
# layout/trivial-cell/reports/<record-id>/.
#
# Usage:
#   layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
#   layout/bin/run-trivial-cell-flow.sh
#
# Requires: layout/.venv (see setup-venv.sh) and a resolvable sky130A PDK
# install (same pin as sim/pdk.json; `volare enable --pdk sky130 <sha>`).
#
# Provenance: adapted from 2AMLogic/sky130-bandgap
# layout/bin/run-trivial-cell-flow.sh (source commit
# 7f2314c338b1356112e244577c03c288a617fbb4) per this repo's CLAUDE.md
# harness-bootstrap rule -- same flow shape (gen -> drc -> extract -> lvs,
# plus two LVS negative controls).
#
# Deviation 1: a DRC negative control (step 2b) is added, which the source
# flow does not have -- issue #2's definition of done requires proof that the
# flow catches a deliberately-injected DRC violation, not only an injected
# LVS mismatch. The fixture is drawn by `klt draw` from
# layout/trivial-cell/drc-negative-control.json.
#
# Deviation 2 (historical): while this repo pinned `klayout-tools==0.2.0`
# from PyPI, that release predated the dummy-device-suppression fix
# (2AMLogic/klayout-tools#490/#491), so `klt extract` reported all 8
# physically-drawn `mos_array` units (4 "real" + 4 dummy-column) rather than
# 4, and layout/trivial-cell/reference*.spice were written to match (8
# M-cards). Issue #46 moved layout/requirements.txt to a git-commit pin that
# carries that fix, so `klt extract` now reports device_count=4,
# dummy_devices_dropped=4, matching sky130-bandgap's own reference shape --
# see layout/trivial-cell/reference.spice's own header and
# layout/klt-pin-decision.md for the full history.
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
CELL_DIR="$LAYOUT_DIR/trivial-cell"
KLT="$LAYOUT_DIR/.venv/bin/klt"
CELL=trivial_mos_array
NC_CELL=drc_negative_control
PDK_VARIANT=sky130A

# shellcheck source=layout/bin/flow_common.sh
source "$LAYOUT_DIR/bin/flow_common.sh"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"

flow_require_klt "$SCRIPT_NAME"
flow_require_pdk "$SCRIPT_NAME"

flow_new_record_id
flow_setup_out_dir "$SCRIPT_NAME" "$CELL_DIR"

# --- 1. Generate the trivial known-good cell -------------------------------
"$KLT" gen mos_array --pdk "$PDK_VARIANT" --cell-name "$CELL" \
  -o "$OUT_DIR/$CELL.gds" --format json > "$OUT_DIR/gen.json"

# --- 2. DRC against the sky130 deck -----------------------------------------
"$KLT" drc "$OUT_DIR/$CELL.gds" --deck sky130 --format json > "$OUT_DIR/drc.json" || true

# --- 2b. DRC negative control: a deliberately illegal fixture --------------
# `klt drc` reporting "clean" on step 2 only proves the flow runs; it does not
# prove the flow can still say "violations". `klt draw` writes geometry
# verbatim with no rule checking (that is its documented purpose: producing a
# known-bad fixture for exactly this check), so the same deck is re-run
# against a cell that must come back flagged.
cp "$CELL_DIR/drc-negative-control.json" "$OUT_DIR/drc-negative-control.params.json"
"$KLT" draw --params "$OUT_DIR/drc-negative-control.params.json" \
  --cell-name "$NC_CELL" -o "$OUT_DIR/$NC_CELL.gds" --format json \
  > "$OUT_DIR/draw.negative-control.json"
"$KLT" drc "$OUT_DIR/$NC_CELL.gds" --deck sky130 --format json \
  > "$OUT_DIR/drc.negative-control.json" || true

# --- 3. Extract a schematic-equivalent netlist ------------------------------
"$KLT" extract "$OUT_DIR/$CELL.gds" --deck sky130 --top "$CELL" \
  -o "$OUT_DIR/$CELL.extract.spice" --format json > "$OUT_DIR/extract.json"

# --- 4. LVS: known-good reference (must report "match") --------------------
cp "$CELL_DIR/reference.spice" "$OUT_DIR/reference.spice"
cat > "$OUT_DIR/lvs.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "file": "$CELL.gds", "deck": "sky130", "top": "$CELL" },
  "reference": { "netlist": "reference.spice", "top": "$CELL" }
}
EOF
"$KLT" lvs "$OUT_DIR/lvs.request.json" --format json > "$OUT_DIR/lvs.json" || true

# --- 5. Negative control 1/2: device-parameter-only corruption -------------
cp "$CELL_DIR/reference.broken-device.spice" "$OUT_DIR/reference.broken-device.spice"
cat > "$OUT_DIR/lvs.broken-device.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "file": "$CELL.gds", "deck": "sky130", "top": "$CELL" },
  "reference": { "netlist": "reference.broken-device.spice", "top": "$CELL" }
}
EOF
"$KLT" lvs "$OUT_DIR/lvs.broken-device.request.json" --format json \
  > "$OUT_DIR/lvs.broken-device.json" || true

# --- 6. Negative control 2/2: topology-only corruption (shorted net) -------
cp "$CELL_DIR/reference.broken-topology.spice" "$OUT_DIR/reference.broken-topology.spice"
cat > "$OUT_DIR/lvs.broken-topology.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "file": "$CELL.gds", "deck": "sky130", "top": "$CELL" },
  "reference": { "netlist": "reference.broken-topology.spice", "top": "$CELL" }
}
EOF
"$KLT" lvs "$OUT_DIR/lvs.broken-topology.request.json" --format json \
  > "$OUT_DIR/lvs.broken-topology.json" || true

# --- 7. Combined human-readable report --------------------------------------
"$KLT" report "$OUT_DIR/drc.json" "$OUT_DIR/lvs.json" --format github-summary \
  > "$OUT_DIR/report.md"

# --- 8. Record summary (pass/fail verdicts, evidence-record style) ---------
python3 "$LAYOUT_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" \
  > "$OUT_DIR/record.md"

# Keep a "latest" pointer so the README's quick-start doesn't need a
# hardcoded record id. This is a plain text file, not a symlink, so it
# survives a shallow checkout / non-symlink-preserving copy unchanged.
flow_write_latest "$CELL_DIR"

echo "$SCRIPT_NAME: done. See $OUT_DIR/record.md"
