#!/usr/bin/env bash
# layout/bin/run-pll-layout-flow.sh -- draw the PLL layout from the authored
# schematic (issue #16) and record the evidence: the raw outputs go to the
# artifact store (DR-012, issue #371); git keeps only
# manifests/artifacts/layout-pll-<record-id>.manifest.json and
# layout/pll/reports/<record-id>/record.md.
#
# Usage:
#   layout/bin/setup-venv.sh            # once, or after bumping requirements.txt
#   layout/bin/run-pll-layout-flow.sh
#
# Requires: layout/.venv (see setup-venv.sh), a resolvable sky130A PDK
# install (same pin as sim/pdk.json; `ciel enable --pdk-family sky130 -l sky130_fd_pr <sha>`),
# and a configured artifact store ($KLT_ARTIFACT_BROKER, a klt with
# `artifact put`). Fails closed (nonzero, nothing committed) without them;
# the raw bytes are never committed as a fallback.
#
# Shape and conventions follow run-trivial-cell-flow.sh (same record-id
# scheme, same "record.md is the deliverable" rule, same LATEST pointer), but
# the content is different work: that flow proves the DRC/LVS *round trip* on
# a fixture, this one draws the actual PLL device set from
# design/top/netlist/top.spice.
#
# Two builds are produced per record:
#   * the shipped, unrouted build in the record root; and
#   * route-spot-check/, the same build with `klt gen-compose`'s
#     point-to-point router enabled -- evidence for why the shipped stream is
#     unrouted (the router introduces shorts). Its GDS streams are deleted
#     after the DRC/extract/LVS run; the JSON envelopes are the evidence.
#     `klt lvs` is run only against this routed build (issue #18) -- the
#     shipped build has no routing at all, so comparing it would only ever
#     report a foregone mismatch with no information in it.
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
PLL_DIR="$LAYOUT_DIR/pll"
KLT="$LAYOUT_DIR/.venv/bin/klt"
NETLIST="$REPO_ROOT/design/top/netlist/top.spice"
PDK_VARIANT=sky130A
DECK=sky130
TOP_CELL=pll_top

# shellcheck source=layout/bin/flow_common.sh
source "$LAYOUT_DIR/bin/flow_common.sh"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"

flow_require_klt "$SCRIPT_NAME"

if [[ ! -f "$NETLIST" ]]; then
  echo "$SCRIPT_NAME: no schematic netlist at $NETLIST" >&2
  exit 1
fi

# The top snapshot's embedded blocks must agree with the standalone block
# snapshots before any record is minted (issue #240). PDK-free; this checks
# snapshot-to-snapshot consistency only, not equivalence with the .sch files.
if ! python3 "$REPO_ROOT/signoff/design-snapshot-consistency.py" \
    --repo-root "$REPO_ROOT"; then
  echo "$SCRIPT_NAME: top snapshot is stale relative to its block snapshots;" \
    "regenerate parents per design/README.md before minting a layout record" >&2
  exit 1
fi

flow_require_pdk "$SCRIPT_NAME"

# Refuse before spending any drawing time if the evidence could not be stored.
if ! python3 "$LAYOUT_DIR/bin/store_pll_evidence.py" preflight --klt "$KLT"; then
  echo "$SCRIPT_NAME: artifact store unavailable; refusing to run (nothing committed)" >&2
  exit 1
fi

flow_new_record_id
# Raw outputs are staged in a git-ignored scratch dir (layout/pll/build/), then
# stored in step 8. flow_setup_out_dir would put them under reports/ (in git),
# so the scratch dir is set up here instead.
OUT_DIR="$PLL_DIR/build/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "$SCRIPT_NAME: record $RECORD_ID -> $OUT_DIR (staging; stored in the artifact store)"

# --- 1. Draw + compose the schematic's device set (shipped, unrouted) ------
python3 "$LAYOUT_DIR/bin/pll_layout.py" \
  --netlist "$NETLIST" --out-dir "$OUT_DIR" \
  --klt "$KLT" --pdk "$PDK_VARIANT" --no-route

# --- 2. DRC the composed top cell ------------------------------------------
# Not expected clean -- see the record's own DRC verdict for what is asserted.
"$KLT" drc "$OUT_DIR/$TOP_CELL.gds" --deck "$DECK" --format json \
  > "$OUT_DIR/drc.json" || true

# --- 3. Extract the top cell and every block cell ---------------------------
"$KLT" extract "$OUT_DIR/$TOP_CELL.gds" --deck "$DECK" --top "$TOP_CELL" \
  -o "$OUT_DIR/$TOP_CELL.spice" --format json > "$OUT_DIR/extract.json"

# `<name> <cell_name> <has-standard-cells>` per block, straight from the plan.
BLOCK_ROWS="$(python3 "$LAYOUT_DIR/bin/pll_layout.py" --netlist "$NETLIST" \
  --out-dir "$OUT_DIR" --plan-only --print-blocks)"

while read -r name cell stdcell; do
  [[ -n "$cell" ]] || continue
  "$KLT" extract "$OUT_DIR/$cell.gds" --deck "$DECK" --top "$cell" \
    -o "$OUT_DIR/$cell.extract.spice" --format json > "$OUT_DIR/extract.$cell.json"
  # --- 4. Cell hierarchy, for the standard-cell block's instance-level check
  if [[ "$stdcell" == "stdcell" ]]; then
    "$KLT" cells "$OUT_DIR/$cell.gds" --format json > "$OUT_DIR/cells.$name.json"
  fi
done <<< "$BLOCK_ROWS"

"$KLT" cells "$OUT_DIR/$TOP_CELL.gds" --format json > "$OUT_DIR/cells.top.json"

# --- 4b. Visual overview ----------------------------------------------------
# `klt render` writes one PNG per layer plus a combined `overview.png`; only
# the overview is kept (it is what a reviewer actually looks at, and 26
# per-layer images per record is not evidence anyone reads).
"$KLT" render "$OUT_DIR/$TOP_CELL.gds" -o "$OUT_DIR/renders" \
  --width 1600 --height 800 --format json > "$OUT_DIR/render.json"
find "$OUT_DIR/renders" -name '*.png' ! -name 'overview.png' -delete

# --- 5. Routing spot-check --------------------------------------------------
SPOT_DIR="$OUT_DIR/route-spot-check"
mkdir -p "$SPOT_DIR"
python3 "$LAYOUT_DIR/bin/pll_layout.py" \
  --netlist "$NETLIST" --out-dir "$SPOT_DIR" \
  --klt "$KLT" --pdk "$PDK_VARIANT" --emit-lvs-reference
"$KLT" drc "$SPOT_DIR/$TOP_CELL.gds" --deck "$DECK" --format json \
  > "$SPOT_DIR/drc.json" || true
"$KLT" extract "$SPOT_DIR/$TOP_CELL.gds" --deck "$DECK" --top "$TOP_CELL" \
  -o "$SPOT_DIR/$TOP_CELL.spice" --format json > "$SPOT_DIR/extract.json"

# --- 5b. LVS: the spot-check's routed layout against the authored schematic -
# The shipped (unrouted) stream is not compared -- with no inter-device
# routing at all its mismatch would carry no information beyond "nothing is
# wired," already documented by the coverage checks above. The routed
# spot-check is a genuine (if heavily partial -- issue #18) topology to
# compare: `klt lvs`'s SPICE reader needs the schematic's "top" as a real
# `.subckt`/`.ends` pair, hence reference.spice (`--emit-lvs-reference`
# above) rather than `$NETLIST` itself, and `options.flatten_*` puts both
# sides on the same footing -- the schematic's subcircuit-call hierarchy
# names its blocks `pfd_cp`/`loop_filter`/... while this flow's own composed
# cells are `pll_pfd_cp`/`pll_loop_filter`/...  (see layout/pll/README.md),
# a naming difference `klt lvs` does not resolve across un-flattened circuit
# boundaries.
#
# `reference.deck` is required here as of `klayout-tools==0.6.0` (issue #157's
# pin bump). The emitted reference netlist writes MOS lengths/widths as bare
# numbers (`L=0.3`), and `klt lvs`'s `subckt-call` -> plain-element conversion
# now refuses to guess whether a unit-less literal is SI metres or already
# micrometres under an ambient `.option scale=1.0u` -- it errors out and names
# `reference.deck` as the way to resolve the convention. Naming the same deck
# the layout side uses is the correct answer, not a workaround: both sides are
# then read under one stated unit convention instead of two assumed ones. At
# the previous pin (`0.4.0`) the field was absent and the converter guessed;
# the refreshed record is what shows whether that guess matched.
cat > "$SPOT_DIR/lvs.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "file": "$TOP_CELL.gds", "deck": "$DECK", "top": "$TOP_CELL" },
  "reference": { "netlist": "reference.spice", "top": "top", "form": "subckt-call", "deck": "$DECK" },
  "options": { "flatten_reference": true, "flatten_layout": true }
}
EOF
"$KLT" lvs "$SPOT_DIR/lvs.request.json" --format json > "$SPOT_DIR/lvs.json" || true

find "$SPOT_DIR" -name '*.gds' -delete
# The spot-check's per-group generator envelopes and its plan are
# byte-identical to the shipped build's (same plan, same `klt gen` calls --
# only the composition requests differ), so only the differing evidence is
# kept.
find "$SPOT_DIR" \( -name 'gen.*.json' -o -name 'draw.*.json' \
  -o -name 'draw.*.params.json' -o -name 'plan.json' \) -delete

# --- 6. Combined human-readable report --------------------------------------
# Only the DRC envelope: `klt report` renders violation/mismatch-shaped
# envelopes, and rejects an `extract` envelope as an unrecognized shape.
"$KLT" report "$OUT_DIR/drc.json" --format github-summary > "$OUT_DIR/report.md"

# --- 7. Record summary (verdicts, evidence-record style) --------------------
# The renderer exits nonzero after writing the record if a verdict it asserts
# fails; the record is still stored (it is the evidence of the miss), and the
# flow exits with that status afterwards.
RENDER_RC=0
python3 "$LAYOUT_DIR/bin/render-pll-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" --netlist "$NETLIST" \
  > "$OUT_DIR/record.md" || RENDER_RC=$?

# --- 8. Store the raw outputs; commit only the manifest and record.md --------
python3 "$LAYOUT_DIR/bin/store_pll_evidence.py" store \
  --stage-dir "$OUT_DIR" --record-id "$RECORD_ID" --klt "$KLT"

# A record whose verdicts failed is stored but not made LATEST (as before).
if [[ "$RENDER_RC" -eq 0 ]]; then
  flow_write_latest "$PLL_DIR"
fi

echo "$SCRIPT_NAME: done. See $PLL_DIR/reports/$RECORD_ID/record.md"
exit "$RENDER_RC"
