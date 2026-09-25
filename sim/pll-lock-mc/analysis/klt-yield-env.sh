#!/usr/bin/env bash
# Build a `klt yield` that actually runs, and regenerate every `klt yield`
# output committed under sim/pll-lock-mc/analysis/.
#
# WHY THIS EXISTS
# ---------------
# `layout/requirements.txt` pins `klayout-tools==0.6.0`, and `klt yield --help`
# works at that pin -- but running the verb does not: its statistics live in a
# Rust extension (`klt_yield_native`) that upstream does not publish as a
# wheel. `klt yield` at the pin exits with
#
#   the klt_yield_native extension is not installed -- from a repo checkout,
#   run `maturin develop --release` inside native/yield/
#
# which is the documented behaviour of the pin, not a broken install (filed
# generically as 2AMLogic/klayout-tools#2466). Until that lands, every
# `klt yield` report this repo commits rests on an extension somebody built by
# hand, and "built by hand" is not a reproduction recipe. This script is.
#
# It does not touch the host's tools. It builds into a throwaway virtualenv
# (default `$TMPDIR`), from an upstream checkout at the exact tag that
# published the pinned wheel, so the Rust core and the Python side are the same
# revision. Nothing it creates is committed; the artifacts it verifies are.
#
# USAGE
# -----
#   bash sim/pll-lock-mc/analysis/klt-yield-env.sh            # build + verify
#   bash sim/pll-lock-mc/analysis/klt-yield-env.sh --write    # build + regenerate
#
# `--write` overwrites the committed reports with freshly generated ones; the
# default mode regenerates into a scratch directory and diffs, so a clean run
# is proof the committed artifacts are reproducible rather than a claim.
#
# Requires: python3 with venv, a Rust toolchain (cargo), maturin, git, network.
# Requires NO PDK, ngspice or xschem.

set -euo pipefail

TAG="v0.6.0"
EXPECT_COMMIT="c622e8addb362491664d44ba4d717f354ca88bbd"
WHEEL_PIN="klayout-tools==0.6.0"

MODE="verify"
[[ "${1:-}" == "--write" ]] && MODE="write"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
WORK="${KLT_YIELD_WORKDIR:-$(mktemp -d "${TMPDIR:-/tmp}/klt-yield-env.XXXXXX")}"
SRC="$WORK/klayout-tools"
VENV="$WORK/venv"

echo "==> work dir: $WORK"

# 1. upstream source at the tag that published the pinned wheel
if [[ ! -d "$SRC" ]]; then
  git clone --quiet --depth 1 --branch "$TAG" \
    https://github.com/2AMLogic/klayout-tools.git "$SRC"
fi
GOT="$(git -C "$SRC" rev-parse HEAD)"
if [[ "$GOT" != "$EXPECT_COMMIT" ]]; then
  echo "FATAL: tag $TAG resolved to $GOT, expected $EXPECT_COMMIT" >&2
  echo "       (a moved tag changes what the committed reports mean -- stop and investigate)" >&2
  exit 1
fi
echo "==> klayout-tools $TAG @ $GOT"

# 2. the pinned wheel, then the extension built from that same revision
if [[ ! -x "$VENV/bin/klt" ]]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet "$WHEEL_PIN"
fi
echo "==> $("$VENV/bin/klt" --version)"

if ! "$VENV/bin/python" -c "import klt_yield_native" 2>/dev/null; then
  ( cd "$SRC/native/yield" \
    && VIRTUAL_ENV="$VENV" CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-2}" \
       CARGO_TARGET_DIR="$WORK/target" maturin develop --release )
fi
KLT="$VENV/bin/klt"
echo "==> klt_yield_native built"

# 3. regenerate every committed klt yield output
A="sim/pll-lock-mc/analysis"
E="$A/yield-evidence"
N="$A/negative-control"
OUT="$WORK/out"
[[ "$MODE" == "write" ]] && OUT="$REPO"
mkdir -p "$OUT/$E" "$OUT/$N/reports"

cd "$REPO"
"$KLT" yield "$E/mc-samples.json" --limits "$E/spec-limits.json" --format json \
  > "$OUT/$E/klt-yield-report.json"
"$KLT" yield "$E/mc-samples.json" --limits "$E/spec-limits.json" --format text \
  > "$OUT/$E/klt-yield-report.txt"
"$KLT" yield "$E/mc-samples-censored-as-failures.json" --limits "$E/spec-limits.json" \
  --format json > "$OUT/$E/klt-yield-report-censored-as-failures.json"
"$KLT" yield "$E/mc-samples-censored-as-failures.json" --limits "$E/spec-limits.json" \
  --format text > "$OUT/$E/klt-yield-report-censored-as-failures.txt"

# The probes carry their limits inline, so they take no --limits file.
for p in "$N"/probes/*.json; do
  "$KLT" yield "$p" --format json > "$OUT/$N/reports/$(basename "$p")"
done

if [[ "$MODE" == "write" ]]; then
  echo "==> regenerated in place under $A/"
  exit 0
fi

rc=0
while IFS= read -r rel; do
  if diff -q "$REPO/$rel" "$OUT/$rel" >/dev/null 2>&1; then
    echo "    ok   $rel"
  else
    echo "    DRIFT $rel" >&2
    rc=1
  fi
done < <(cd "$OUT" && find "$E" "$N" -type f -name '*.json' -o -type f -name '*.txt' | sort)

if [[ $rc -eq 0 ]]; then
  echo "==> every committed klt yield output reproduces from $TAG @ $EXPECT_COMMIT"
else
  echo "==> at least one committed output does not reproduce" >&2
fi
exit $rc
