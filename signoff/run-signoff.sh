#!/usr/bin/env bash
# Render this block's T1 tier verdict with `klt signoff --manifest`, and
# either write it to signoff/tier-report.json or verify the committed copy
# still matches.
#
#   bash signoff/run-signoff.sh           # regenerate signoff/tier-report.json
#   bash signoff/run-signoff.sh --check   # fail if the committed report is stale
#
# Both modes run the three guards in "Three guards this repo adds" below
# first, so a manifest edit that would have rendered a row green against
# evidence that contradicts it fails here rather than in review.
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
#      superseded evidence record, the manifest cites a `klt yield` report
#      whose own statistics do not support the row it would grade, or the
#      manifest/doc is bad
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

# Three guards `klt signoff` does not apply for us, run before the render.
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
#    Which key names that artifact depends on the verb: `klt drc`/`lvs`/`erc`
#    envelopes name it `file`, while a `klt yield` report names its sample-set
#    document `samples`. Both are read here, so a yield citation's pin is
#    re-hashed rather than skipped with a "names no input artifact" warning.
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
#
# 3. A cited `klt yield` report must be one its own statistics stand behind.
#
# `klt signoff` grades a yield citation on the report's `status` alone, and
# `status` is `"reported"` -- which it grades as passing -- for any measurement
# that declares no `target_yield`, i.e. for a measurement that *can never fail*.
# It consults neither the report's own `sample_size.verdict` nor its
# missing-negative-control warning (filed generically as
# klayout-tools#2467). So a report that says, in its own body, "this estimate
# is unsized" and "nothing here demonstrates these statistics can detect a
# degraded design" still renders T1 item 6 `met`. That is a green row over an
# artifact that contradicts it, and it is the exact false pass issue #182
# exists to keep out of this manifest.
#
# T1 item 6's checklist text asks for a recorded seed, a sample count, a
# *deterministic negative control*, and results combined with process corners.
# Two of those are machine-readable in the report the manifest would cite, so
# they are checked here rather than trusted to a reviewer:
#
#   * every measurement's `sample_size.verdict` must be `sufficient` (the verb
#     reports only `sufficient`/`insufficient`, and an absent verdict is not a
#     pass either);
#   * every measurement must declare a `negative_control` whose `verdict` is
#     `detected`.
#
# If a campaign's honest outcome is a `not_detected` negative control -- a real
# possibility, and one issue #182's acceptance criteria explicitly allow -- the
# argument for that belongs in a committed record beside the report, and
# relaxing this guard is part of making it, not a workaround for it. This guard
# retires when klayout-tools#2467 lands and `klt signoff` applies the same two
# checks itself.
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
envelopes = {}
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
    envelopes[item] = (path, envelope)
    # `klt drc`/`lvs`/`erc` name their input artifact `file`; a `klt yield`
    # report names its sample-set document `samples`. Either is the artifact
    # whose content the manifest's pin claims to fix.
    named = envelope.get("file")
    if not isinstance(named, str) or not named:
        named = envelope.get("samples")
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

# Guard 3: a cited `klt yield` report must be one its own statistics stand
# behind -- sized, and self-checked by a negative control that fired.
def yield_measurements(envelope):
    """The measurements of a `klt yield` report, or None if not one.

    A yield report is identified by shape rather than by a `command` field,
    which `klt yield`'s JSON does not carry at this version: its measurements
    each own a `sample_size` verdict block, which no other envelope this repo
    cites produces.
    """
    measurements = envelope.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        return None
    if not all(isinstance(m, dict) for m in measurements):
        return None
    if not any("sample_size" in m for m in measurements):
        return None
    return measurements


unsupported = []
for item, (path, envelope) in envelopes.items():
    measurements = yield_measurements(envelope)
    if measurements is None:
        continue
    for index, measurement in enumerate(measurements):
        name = measurement.get("name") or f"#{index}"
        sample_size = measurement.get("sample_size")
        verdict = sample_size.get("verdict") if isinstance(sample_size, dict) else None
        if verdict != "sufficient":
            detail = f"sample_size.verdict is {verdict!r}"
            if isinstance(sample_size, dict) and sample_size.get("required_n") is not None:
                detail += (
                    f" (n = {sample_size.get('n')}, "
                    f"required_n = {sample_size['required_n']})"
                )
            unsupported.append(f"item {item}: {path}: measurement '{name}': {detail}")
        control = measurement.get("negative_control")
        if not isinstance(control, dict):
            unsupported.append(
                f"item {item}: {path}: measurement '{name}': no negative_control is "
                "declared -- nothing demonstrates these statistics can detect a "
                "degraded design"
            )
        elif control.get("verdict") != "detected":
            unsupported.append(
                f"item {item}: {path}: measurement '{name}': negative_control.verdict "
                f"is {control.get('verdict')!r}, not 'detected'"
            )

if unsupported:
    print(
        "error: a cited klt yield report does not support the row it would grade:",
        file=sys.stderr,
    )
    for line in unsupported:
        print(f"  {line}", file=sys.stderr)
    print(
        "       `klt signoff` grades a yield citation on the report's `status` "
        "alone -- and `reported` (a measurement with no target_yield, which can "
        "never fail) passes -- so citing this would render T1 item 6 `met` over "
        "an artifact that contradicts it (klayout-tools#2467). Size the campaign "
        "and declare a negative control that fires, or cite nothing. If "
        "`not_detected` is the honest outcome, argue it in a committed record "
        "beside the report and relax this guard in the same change.",
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
