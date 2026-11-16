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
# The mechanism (option parsing, git-repo guard, discovery, the empty-set
# guard, skip handling, summary) lives in scripts/lint_common.sh, shared with
# the other lint drivers; this wrapper supplies only the glob, the per-file
# check and the message wording.
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
LINT_TOOL=lint-python-syntax
LINT_GLOB='*.py'
LINT_FILTER=vendored
LINT_NOUN_PLURAL='Python files'
LINT_UNIT='file(s)'
LINT_CHECKER='py_compile'
LINT_ACTION='py_compile every tracked Python file this repository owns'

lint_check_one() {
  python3 -m py_compile "$1"
}

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lint_common.sh"
