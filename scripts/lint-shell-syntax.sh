#!/usr/bin/env bash
# Syntax-check (`bash -n`) every shell script this repository owns.
#
# The coverage set is discovered from `git ls-files`, not enumerated here, so a
# script added to the repo is checked by construction -- including this script
# itself. It replaces a hand-maintained chain of `bash -n <path>` terms in
# package.json's `lint` target, which had silently stopped covering
# verification/guard-mktemp-template/run-matrix.sh after that file was added
# without the matching package.json edit (#446).
#
# Usage:
#   bash scripts/lint-shell-syntax.sh            check every discovered script
#   bash scripts/lint-shell-syntax.sh --list     print the coverage set only
#
# Runs from any directory: the repo root is derived from this script's own
# location, not from the caller's cwd.
#
# `bash -n` parses without executing, so this has no side effects and needs
# neither the PDK nor a virtualenv.
#
# Exit codes: 0 every script parsed; 1 at least one syntax error;
# 2 usage error or a discovery failure (not a git repo, empty coverage set).
set -uo pipefail

# Installer-managed trees whose contents this repository does not own and must
# not lint: `.loom/` is provisioned by Loom, `.claude/` by the Loom and Repo
# Skills installers (see CLAUDE.md "repo-owned files"). Upstream owns their
# syntax; a failure here would be unfixable in this repo -- and upstream Loom
# already guards its own installed surfaces with
# .loom/scripts/check-shell-syntax.sh, which scans exactly the two trees
# excluded here. The two checks are complementary, not overlapping.
VENDORED_PREFIXES=(".loom/" ".claude/")

usage() {
  cat <<'USAGE'
Usage: bash scripts/lint-shell-syntax.sh [--list]

  (no option)  bash -n every tracked shell script this repository owns
  --list       print the discovered coverage set, one path per line, and exit
USAGE
}

list_only=0
case "${1-}" in
  "")       ;;
  --list)   list_only=1 ;;
  -h|--help) usage; exit 0 ;;
  *)        echo "lint-shell-syntax: unknown option '$1'" >&2; usage >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
  echo "lint-shell-syntax: too many arguments" >&2; usage >&2; exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! git -C "$root" rev-parse --git-dir >/dev/null 2>&1; then
  echo "lint-shell-syntax: $root is not a git repository -- cannot discover scripts" >&2
  exit 2
fi

# -z plus `read -d ''` so a path containing a space or newline survives intact.
scripts=()
while IFS= read -r -d '' path; do
  vendored=0
  for prefix in "${VENDORED_PREFIXES[@]}"; do
    case "$path" in "$prefix"*) vendored=1; break ;; esac
  done
  [ "$vendored" -eq 1 ] && continue
  scripts+=("$path")
done < <(git -C "$root" ls-files -z -- '*.sh')

# An empty coverage set means discovery broke (wrong root, over-broad
# exclusion), not that the repo is clean. Fail rather than pass vacuously.
if [ "${#scripts[@]}" -eq 0 ]; then
  echo "lint-shell-syntax: no tracked shell scripts found under $root -- discovery is broken" >&2
  exit 2
fi

if [ "$list_only" -eq 1 ]; then
  printf '%s\n' "${scripts[@]}"
  exit 0
fi

failed=()
skipped=()
for path in "${scripts[@]}"; do
  # Tracked but absent from the working tree: a sparse or partial checkout.
  # Report it so the gap is visible, but do not fail the lint over it.
  if [ ! -f "$root/$path" ]; then
    skipped+=("$path")
    continue
  fi
  bash -n "$root/$path" || failed+=("$path")
done

for path in "${skipped[@]}"; do
  echo "lint-shell-syntax: skipped $path (tracked but absent from the working tree)" >&2
done

if [ "${#failed[@]}" -gt 0 ]; then
  echo "lint-shell-syntax: ${#failed[@]} of ${#scripts[@]} script(s) failed bash -n:" >&2
  printf '  %s\n' "${failed[@]}" >&2
  exit 1
fi

checked=$(( ${#scripts[@]} - ${#skipped[@]} ))
echo "lint-shell-syntax: $checked script(s) passed bash -n"
