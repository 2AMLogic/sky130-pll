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
# The mechanism (option parsing, git-repo guard, discovery, the empty-set
# guard, skip handling, summary) lives in scripts/lint_common.sh, shared with
# the other lint drivers; this wrapper supplies only the glob, the per-file
# check and the message wording.
#
# `bash -n` parses without executing, so this has no side effects and needs
# neither the PDK nor a virtualenv.
#
# Usage:
#   bash scripts/lint-shell-syntax.sh            check every discovered script
#   bash scripts/lint-shell-syntax.sh --list     print the coverage set only
#
# Runs from any directory: the repo root is derived from this script's own
# location, not from the caller's cwd.
#
# Exit codes: 0 every script parsed; 1 at least one syntax error;
# 2 usage error or a discovery failure (not a git repo, empty coverage set).
LINT_TOOL=lint-shell-syntax
LINT_GLOB='*.sh'
LINT_FILTER=vendored
LINT_NOUN_PLURAL='shell scripts'
LINT_UNIT='script(s)'
LINT_CHECKER='bash -n'
LINT_ACTION='bash -n every tracked shell script this repository owns'

lint_check_one() {
  bash -n "$1"
}

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lint_common.sh"
