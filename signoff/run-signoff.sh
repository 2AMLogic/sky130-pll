#!/usr/bin/env bash
# Render this block's T1 tier verdict with `klt signoff --manifest`, and
# either write it to signoff/tier-report.json or verify the committed copy
# still matches.
#
#   bash signoff/run-signoff.sh           # regenerate signoff/tier-report.json
#   bash signoff/run-signoff.sh --check   # fail if the committed report is stale
#
# The --check mode is what CI runs. It is the whole point of committing the
# report: a manifest that cites an evidence artifact which has since changed
# (a re-run DRC, an edited netlist, a moved file) re-renders differently, and
# the diff fails the build instead of the verdict quietly rotting.
#
# Run from anywhere; paths below are resolved against the repo root, and `klt`
# is invoked *from* the repo root so that relative evidence paths inside the
# manifest mean the same thing here, in CI, and on a reviewer's machine.
#
# Structure ported from the sibling canary 2AMLogic/gf180-pll
# (signoff/run-signoff.sh at commit d85287d8, 2026-09-20), per CLAUDE.md's
# "copy the proven patterns rather than reinventing" rule. Two deliberate
# differences from that source, both explained in signoff/README.md:
#   * no `--tiers-doc` override -- the pinned klt release below already
#     bundles the eleven-item checklist, so nothing needs vendoring here;
#   * the superseded-record guard below, which gf180-pll has no equivalent
#     of because it cites no evidence at all.
#
# Exit codes:
#   0  the report was written (default mode), or matches (--check)
#   1  the committed report is stale (--check), the manifest cites a
#      superseded evidence record, or the manifest/doc is bad
#   2  `klt` is not installed

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="signoff/block-manifest.json"
REPORT="signoff/tier-report.json"

# The klt release this repo grades against. CI installs exactly this version
# (see .github/workflows/ci.yml); a different one may parse a different
# checklist revision or render a different report shape, which shows up as a
# confusing `--check` diff rather than an obvious version mismatch -- hence
# the warning below.
KLT_PIN="0.6.0"

mode="write"
case "${1-}" in
  "") ;;
  --check) mode="check" ;;
  -h | --help)
    sed -n '2,31p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *)
    echo "error: unknown argument '$1' (expected --check or nothing)" >&2
    exit 1
    ;;
esac

cd "$REPO_ROOT"

if ! command -v klt >/dev/null 2>&1; then
  echo "error: klt not found on PATH -- install it with:" >&2
  echo "         pip install 'klayout-tools==${KLT_PIN}'" >&2
  echo "       (https://github.com/2AMLogic/klayout-tools)" >&2
  exit 2
fi

klt_version="$(klt --version 2>&1 || true)"
echo "klt: $(command -v klt) (${klt_version})" >&2
case "$klt_version" in
  *"$KLT_PIN"*) ;;
  *)
    echo "warning: this repo's committed report was rendered by klt ${KLT_PIN}." >&2
    echo "         A diff below may be version drift, not evidence drift." >&2
    ;;
esac

# Two guards `klt signoff` does not apply for us, run before the render.
#
# 1. Artifact re-hash. `klt signoff` does re-hash a cited envelope's input
#    artifact when it can find it, and discloses the answer as the citation's
#    `input_verified`. It cannot find this repo's: the layout flow's envelopes
#    record the *absolute* path of the machine that produced them, and the
#    grader only resolves a relative path against the evidence file's own
#    directory -- so `input_verified` is `null` and the pinned hash is
#    compared to another claim, never to a file. An edit to the committed
#    artifact would then be invisible: the envelope still claims the old hash,
#    the pin still matches it, the row stays green. This guard resolves the
#    artifact by basename beside the envelope, in its own append-only record
#    directory, and re-hashes it for real. The tool gap is tracked upstream
#    as klayout-tools#2340; this guard retires when that lands.
#
# 2. Superseded record.
#
# A pinned `content_hash` catches an evidence artifact that CHANGED. It cannot
# catch an evidence artifact that was SUPERSEDED: `layout/` records are
# append-only, so a fresh flow run mints a new `reports/<record-id>/` directory
# and leaves the cited one byte-identical forever. The manifest would keep
# citing a report that is no longer this block's latest, the hash would keep
# matching, and the row would stay green against stale evidence -- exactly the
# rot this directory exists to prevent, arriving by the one door the hash pin
# leaves open. T1 item 3 says "latest `klt drc` JSON report", so "latest" is
# what gets checked: every cited path under `layout/<dir>/reports/<record-id>/`
# must name the record `layout/<dir>/reports/LATEST` points at.
python3 - "$MANIFEST" <<'PY'
import hashlib
import json
import pathlib
import re
import sys

manifest_path = pathlib.Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text())

cited = []
for item, entry in (manifest.get("evidence") or {}).items():
    if isinstance(entry, str):
        cited.append((item, entry, None))
    elif isinstance(entry, dict) and isinstance(entry.get("file"), str):
        cited.append((item, entry["file"], entry.get("content_hash")))

# Guard 1: re-hash the artifact each cited envelope names.
mismatched = []
for item, path, pinned in cited:
    if pinned is None:
        mismatched.append(f"item {item}: {path} pins no content_hash -- freshness is unverifiable")
        continue
    envelope_path = pathlib.Path(path)
    try:
        envelope = json.loads(envelope_path.read_text())
    except (OSError, ValueError) as exc:
        mismatched.append(f"item {item}: {path} is unreadable ({exc})")
        continue
    named = envelope.get("file")
    if not isinstance(named, str) or not named:
        print(
            f"warning: item {item}: {path} names no input artifact -- "
            "its pinned content_hash could not be re-hashed",
            file=sys.stderr,
        )
        continue
    # The envelope records the absolute path of the machine that produced it;
    # the artifact itself is committed beside the envelope, in the same
    # append-only record directory.
    artifact = envelope_path.parent / pathlib.PurePosixPath(named.replace("\\", "/")).name
    if not artifact.is_file():
        mismatched.append(
            f"item {item}: {artifact} is missing -- {path}'s pinned content_hash "
            "cannot be re-verified because the cited artifact is gone, not merely "
            "changed"
        )
        continue
    actual = "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
    if actual != pinned:
        mismatched.append(
            f"item {item}: {artifact} hashes to {actual}, but the manifest pins {pinned}"
        )

if mismatched:
    print("error: a cited artifact does not match its pinned content_hash:", file=sys.stderr)
    for line in mismatched:
        print(f"  {line}", file=sys.stderr)
    print(
        "       The evidence moved under the claim. Re-run the flow that "
        "produces it, cite the new record, and re-render with "
        "`bash signoff/run-signoff.sh`.",
        file=sys.stderr,
    )
    sys.exit(1)

# Guard 2: every cited layout record must be the one LATEST names.
pattern = re.compile(r"^(layout/[^/]+/reports)/([^/]+)/")
stale = []
for item, path, _pinned in cited:
    match = pattern.match(path)
    if not match:
        continue
    reports_dir, record_id = match.group(1), match.group(2)
    latest_file = pathlib.Path(reports_dir) / "LATEST"
    if not latest_file.is_file():
        stale.append(f"item {item}: {path} -- {latest_file} does not exist")
        continue
    latest = latest_file.read_text().strip()
    if latest != record_id:
        stale.append(
            f"item {item}: cites record {record_id}, but {latest_file} names {latest}"
        )

if stale:
    print("error: the manifest cites a superseded evidence record:", file=sys.stderr)
    for line in stale:
        print(f"  {line}", file=sys.stderr)
    print(
        "       T1 item 3 asks for the LATEST report. Re-point "
        f"{manifest_path} at the current record (and re-pin its content_hash), "
        "then re-render with `bash signoff/run-signoff.sh`.",
        file=sys.stderr,
    )
    sys.exit(1)
PY

# `klt signoff --manifest` exits 3 when the block is not yet T1 -- which is
# the expected, honest state of this block today (see signoff/README.md). Only
# 0 (T1 reached) and 3 (not yet T1) are verdicts; anything else is a tool or
# input error and must not be written out as if it were a report.
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
status=0
klt signoff \
  --manifest "$MANIFEST" \
  --format json >"$tmp" || status=$?

case "$status" in
  0 | 3) ;;
  *)
    echo "error: klt signoff exited $status -- not a tier verdict" >&2
    cat "$tmp" >&2
    exit 1
    ;;
esac

if [ "$mode" = "check" ]; then
  if ! diff -u "$REPORT" "$tmp"; then
    echo >&2
    echo "error: $REPORT is stale -- re-render it with:" >&2
    echo "         bash signoff/run-signoff.sh" >&2
    echo "       and read signoff/README.md before updating any claim it backs." >&2
    exit 1
  fi
  echo "$REPORT is current." >&2
  exit 0
fi

cp "$tmp" "$REPORT"
echo "wrote $REPORT" >&2
