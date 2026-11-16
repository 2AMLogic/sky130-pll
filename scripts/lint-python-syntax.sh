#!/usr/bin/env bash
# Byte-compile (`python3 -m py_compile`) every tracked `.py` file this
# repository owns.
#
# The coverage set is discovered from `git ls-files`, not enumerated here, so a
# Python file added to the repo is checked by construction. It replaces the
# inline `git ls-files | xargs py_compile` pipeline in package.json's
# `test:compile` target, which could pass vacuously: an empty discovered list
# -- or a `git ls-files` that failed outside a git repository, its 128
# swallowed on the left-hand side of the pipe -- left the pipeline exiting 0
# without compiling anything (#482).
#
# Usage:
#   bash scripts/lint-python-syntax.sh            check every discovered file
#   bash scripts/lint-python-syntax.sh --list     print the coverage set only
#
# Runs from any directory: the repo root is derived from this script's own
# location, not from the caller's cwd.
#
# `py_compile` writes a `__pycache__/` beside each source; that directory is
# gitignored, so the check leaves no working-tree churn.
#
# Exit codes: 0 every file compiled; 1 at least one syntax error;
# 2 usage error or a discovery failure (not a git repo, empty coverage set).
set -uo pipefail

# Installer-managed trees whose contents this repository does not own and must
# not compile: `.loom/` is provisioned by Loom, `.claude/` by the Loom and Repo
# Skills installers, `.agents/` by the agent-harness installer (see CLAUDE.md
# "repo-owned files"). These are the four exclusions `test:compile` already
# carried; upstream owns their syntax.
VENDORED_PREFIXES=(".loom/" ".claude/" ".agents/" ".github/")

usage() {
  cat <<'USAGE'
Usage: bash scripts/lint-python-syntax.sh [--list]

  (no option)  py_compile every tracked Python file this repository owns
  --list       print the discovered coverage set, one path per line, and exit
USAGE
}

list_only=0
case "${1-}" in
  "")       ;;
  --list)   list_only=1 ;;
  -h|--help) usage; exit 0 ;;
  *)        echo "lint-python-syntax: unknown option '$1'" >&2; usage >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
  echo "lint-python-syntax: too many arguments" >&2; usage >&2; exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! git -C "$root" rev-parse --git-dir >/dev/null 2>&1; then
  echo "lint-python-syntax: $root is not a git repository -- cannot discover Python files" >&2
  exit 2
fi

# -z plus `read -d ''` so a path containing a space or newline survives intact.
files=()
while IFS= read -r -d '' path; do
  vendored=0
  for prefix in "${VENDORED_PREFIXES[@]}"; do
    case "$path" in "$prefix"*) vendored=1; break ;; esac
  done
  [ "$vendored" -eq 1 ] && continue
  files+=("$path")
done < <(git -C "$root" ls-files -z -- '*.py')

# An empty coverage set means discovery broke (wrong root, over-broad
# exclusion), not that the repo is clean. Fail rather than pass vacuously.
if [ "${#files[@]}" -eq 0 ]; then
  echo "lint-python-syntax: no tracked Python files found under $root -- discovery is broken" >&2
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
  python3 -m py_compile "$root/$path" || failed+=("$path")
done

for path in "${skipped[@]}"; do
  echo "lint-python-syntax: skipped $path (tracked but absent from the working tree)" >&2
done

if [ "${#failed[@]}" -gt 0 ]; then
  echo "lint-python-syntax: ${#failed[@]} of ${#files[@]} file(s) failed py_compile:" >&2
  printf '  %s\n' "${failed[@]}" >&2
  exit 1
fi

checked=$(( ${#files[@]} - ${#skipped[@]} ))
echo "lint-python-syntax: $checked file(s) passed py_compile"
