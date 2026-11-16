#!/usr/bin/env bash
# Parse-check (`python3 -m json.tool`) every tracked `.json` file under the
# four repo-owned data roots: sim, layout, measurements, signoff.
#
# The coverage set is discovered from `git ls-files`, not enumerated here, so a
# JSON file added under the roots is checked by construction. It replaces the
# inline `find | xargs json.tool` pipeline in package.json's `lint` target,
# which could pass vacuously: an empty discovered list -- or a `find` that
# failed on a missing root, its non-zero status swallowed on the left-hand
# side of the pipe -- left the pipeline exiting 0 without parsing anything
# (#482).
#
# The roots are an include filter by construction: a repo-wide
# `git ls-files -- '*.json'` would also reach vendored installer trees
# (`.loom/`, `.claude/`, `.agents/`) this repository does not own, so this
# script never widens past the four roots.
#
# Usage:
#   bash scripts/lint-json.sh            check every discovered file
#   bash scripts/lint-json.sh --list     print the coverage set only
#
# Runs from any directory: the repo root is derived from this script's own
# location, not from the caller's cwd.
#
# Output goes to /dev/null; the check is pass/fail per file, not a formatter.
#
# Exit codes: 0 every file parsed; 1 at least one malformed file;
# 2 usage error or a discovery failure (not a git repo, empty coverage set).
set -uo pipefail

# The only trees whose JSON this repository owns. Everything else -- including
# the vendored installer trees -- is out of scope here.
ROOT_PREFIXES=("sim/" "layout/" "measurements/" "signoff/")

usage() {
  cat <<'USAGE'
Usage: bash scripts/lint-json.sh [--list]

  (no option)  json.tool every tracked JSON file under sim, layout,
               measurements, signoff
  --list       print the discovered coverage set, one path per line, and exit
USAGE
}

list_only=0
case "${1-}" in
  "")       ;;
  --list)   list_only=1 ;;
  -h|--help) usage; exit 0 ;;
  *)        echo "lint-json: unknown option '$1'" >&2; usage >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
  echo "lint-json: too many arguments" >&2; usage >&2; exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! git -C "$root" rev-parse --git-dir >/dev/null 2>&1; then
  echo "lint-json: $root is not a git repository -- cannot discover JSON files" >&2
  exit 2
fi

# -z plus `read -d ''` so a path containing a space or newline survives intact.
files=()
while IFS= read -r -d '' path; do
  owned=0
  for prefix in "${ROOT_PREFIXES[@]}"; do
    case "$path" in "$prefix"*) owned=1; break ;; esac
  done
  [ "$owned" -eq 0 ] && continue
  files+=("$path")
done < <(git -C "$root" ls-files -z -- '*.json')

# An empty coverage set means discovery broke (wrong root, roots renamed),
# not that the repo is clean. Fail rather than pass vacuously.
if [ "${#files[@]}" -eq 0 ]; then
  echo "lint-json: no tracked JSON files found under the repo-owned roots in $root -- discovery is broken" >&2
  exit 2
fi

if [ "$list_only" -eq 1 ]; then
  printf '%s\n' "${files[@]}"
  exit 0
fi

failed=()
skipped=()
for path in "${files[@]}"; do
  # Tracked but absent from the working tree: a sparse or partial checkout.
  # Report it so the gap is visible, but do not fail the check over it.
  if [ ! -f "$root/$path" ]; then
    skipped+=("$path")
    continue
  fi
  python3 -m json.tool "$root/$path" > /dev/null || failed+=("$path")
done

for path in "${skipped[@]}"; do
  echo "lint-json: skipped $path (tracked but absent from the working tree)" >&2
done

if [ "${#failed[@]}" -gt 0 ]; then
  echo "lint-json: ${#failed[@]} of ${#files[@]} file(s) failed json.tool:" >&2
  printf '  %s\n' "${failed[@]}" >&2
  exit 1
fi

checked=$(( ${#files[@]} - ${#skipped[@]} ))
echo "lint-json: $checked file(s) passed json.tool"
