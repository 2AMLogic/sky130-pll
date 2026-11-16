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
# driver never widens past the four roots. The rest of the mechanism (option
# parsing, git-repo guard, discovery, the empty-set guard, skip handling,
# summary) lives in scripts/lint_common.sh, shared with the other lint
# drivers; this wrapper supplies only the glob, the per-file check and the
# message wording.
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
LINT_TOOL=lint-json
LINT_GLOB='*.json'
LINT_FILTER=roots
LINT_ROOTS=("sim/" "layout/" "measurements/" "signoff/")
LINT_NOUN_PLURAL='JSON files'
LINT_UNIT='file(s)'
LINT_CHECKER='json.tool'
LINT_ACTION='json.tool every tracked JSON file under sim, layout,
               measurements, signoff'

lint_check_one() {
  python3 -m json.tool "$1" > /dev/null
}

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lint_common.sh"
