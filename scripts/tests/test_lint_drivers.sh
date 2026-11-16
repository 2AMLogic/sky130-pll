#!/usr/bin/env bash
# Parameterised fixture tests for the three repo-owned lint drivers
# (scripts/lint-shell-syntax.sh, scripts/lint-python-syntax.sh,
# scripts/lint-json.sh) and their shared core, scripts/lint_common.sh
# (#507).
#
# Every case runs a driver against a throwaway git repository built under
# mktemp, so discovery can be driven to its edges (vendored trees, untracked
# files, an empty listing, awkward names) without touching this checkout.
# Each driver section drives the same shared steps -- the drivers share one
# contract (#482) -- with only the fixtures, the samples and the real-repo
# assertions varying per tool. The fake repos track the driver wrapper but
# only copy lint_common.sh in untracked: the core must sit beside the wrapper
# to be sourced, but tracking it would change the coverage set under test.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
core="$here/../lint_common.sh"
real_root="$(cd "$here/../.." && pwd)"

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fails=0; n=0
ok()  { n=$((n+1)); echo "ok $n - $1"; }
bad() { n=$((n+1)); fails=$((fails+1)); echo "not ok $n - $1"; }
expect() { # desc cond-exit
  if [ "$2" -eq 0 ]; then ok "$1"; else bad "$1"; fi
}

# Per-driver configuration, set immediately before each section:
#   tool      wrapper name (lint-shell-syntax, ...)
#   noun      singular noun for descriptions ("shell script")
#   noun_pl   plural noun used in the driver's own messages ("shell scripts")
#   good      a sample that passes the per-file check
#   broken    a sample that fails it (a parse/compile error, not a runtime one)
tool= noun= noun_pl= good= broken=

setup_fake() {
  repo="$T/fake repo $tool"
  mkdir -p "$repo/scripts"
  cp "$here/../$tool.sh" "$repo/scripts/$tool.sh"
  cp "$core" "$repo/scripts/lint_common.sh"
  git -C "$repo" init -q
  git -C "$repo" config user.email loom@example.invalid
  git -C "$repo" config user.name loom
  git -C "$repo" add -- "scripts/$tool.sh"
}

add() { # relpath contents
  mkdir -p "$repo/$(dirname "$1")"
  printf '%s\n' "$2" > "$repo/$1"
  git -C "$repo" add -- "$1"
}
run() { # [args...] -> stdout+stderr in $T/out, exit status returned
  ( cd "$T" && bash "$repo/scripts/$tool.sh" "$@" ) > "$T/out" 2>&1
}
expect_list() { # expected --list output on stdin
  run --list; rc=$?
  cat > "$T/want"
  [ "$rc" -eq 0 ] && diff -u "$T/want" "$T/out" > "$T/diff"; listed=$?
  expect "$tool: --list reports exactly the repo-owned tracked $noun_pl" "$listed"
  [ "$listed" -eq 0 ] || cat "$T/diff" 2>/dev/null
}

# --- shared steps: the contract every driver must satisfy identically -------

step_failures_named() { # broken1 broken2
  add "$1" "$broken"
  run; rc=$?
  [ "$rc" -eq 1 ] && grep -qF "$1" "$T/out"
  expect "$tool: a failing $noun fails with exit 1 and names the file" $?
  add "$2" "$broken"
  run; rc=$?
  [ "$rc" -eq 1 ] && grep -qF "$1" "$T/out" && grep -qF "$2" "$T/out"
  expect "$tool: all failures are reported, not just the first" $?
  git -C "$repo" rm -q --cached -- "$1" "$2"
  rm -f "$repo/$1" "$repo/$2"
  run; expect "$tool: removing the broken $noun_pl restores a passing tree" $?
}

step_new_covered() { # path
  add "$1" "$broken"
  run; rc=$?
  [ "$rc" -ne 0 ] && grep -qF "$1" "$T/out"
  expect "$tool: a newly tracked $noun is covered with no list to update" $?
  git -C "$repo" rm -q --cached -- "$1"
  rm -f "$repo/$1"
}

step_untracked_ignored() { # relpath tree-to-remove
  mkdir -p "$repo/$(dirname "$1")"
  printf '%s\n' "$broken" > "$repo/$1"
  run; expect "$tool: untracked file with a failure is ignored" $?
  rm -rf "$repo/$2"
}

step_sparse_skipped() { # path
  add "$1" "$good"
  rm -f "$repo/$1"
  run; rc=$?
  [ "$rc" -eq 0 ] && grep -qi 'skip' "$T/out" && grep -qF "$1" "$T/out"
  expect "$tool: tracked-but-absent path is skipped with a notice, not an error" $?
  git -C "$repo" rm -q --cached -- "$1"
}

step_awkward_name() { # path containing spaces
  add "$1" "$broken"
  run; rc=$?
  [ "$rc" -ne 0 ] && grep -qF "$1" "$T/out"
  expect "$tool: path containing spaces is checked and reported" $?
  git -C "$repo" rm -q --cached -- "$1"
  rm -rf "$repo/$(dirname "$1")"
}

step_empty_fails() { # expected fragment of the empty-coverage message
  empty="$T/empty repo $tool"; mkdir -p "$empty/scripts"
  cp "$here/../$tool.sh" "$empty/scripts/$tool.sh"
  cp "$core" "$empty/scripts/lint_common.sh"
  git -C "$empty" init -q
  ( cd "$T" && bash "$empty/scripts/$tool.sh" ) > "$T/out" 2>&1; rc=$?
  [ "$rc" -eq 2 ] && grep -qi "$1" "$T/out"
  expect "$tool: discovering zero $noun_pl fails loudly with exit 2" $?
}

step_non_git_fails() {
  bare="$T/not a repo $tool"; mkdir -p "$bare/scripts"
  cp "$here/../$tool.sh" "$bare/scripts/$tool.sh"
  cp "$core" "$bare/scripts/lint_common.sh"
  ( cd "$T" && bash "$bare/scripts/$tool.sh" ) > "$T/out" 2>&1; rc=$?
  [ "$rc" -eq 2 ]
  expect "$tool: non-git directory fails with exit 2 rather than passing vacuously" $?
}

step_usage_fails() {
  run --nonsense; rc=$?
  [ "$rc" -eq 2 ] && grep -qi 'usage' "$T/out"
  expect "$tool: unknown option fails with usage and exit 2" $?
}

# =============================================================================
# lint-shell-syntax.sh
# =============================================================================
tool=lint-shell-syntax
noun='shell script'; noun_pl='shell scripts'
good='#!/usr/bin/env bash
echo fine'
broken='#!/usr/bin/env bash
if true; then'   # unterminated `if` -- a bash -n failure, not a runtime one

setup_fake

# Discovery: repo-owned scripts in, vendored installer trees out. All four
# vendored trees carry broken samples: the shell driver once excluded only
# .loom/ and .claude/ and had drifted from the python driver's four (#507).
add 'loom.sh'                   "$good"
add 'sim/bin/pdk-env.sh'        "$good"
add 'verification/run-matrix.sh' "$good"
add 'README.md'                 '# not a shell script'
add '.loom/scripts/worktree.sh' "$broken"
add '.claude/skills/repo/scripts/repo-remote.sh' "$broken"
add '.agents/tools/agent.sh'    "$broken"
add '.github/helper/workflow.sh' "$broken"

expect_list <<'X'
loom.sh
scripts/lint-shell-syntax.sh
sim/bin/pdk-env.sh
verification/run-matrix.sh
X

run; expect "$tool: clean tree passes" $?
! grep -qE '\.loom/|\.claude/|\.agents/|\.github/' "$T/out"
expect "$tool: vendored trees' syntax errors are not reported" $?

# The driver checks itself: it is a tracked .sh file like any other. This is
# the property the enumeration in package.json structurally could not have.
run --list; grep -q "^scripts/${tool}\.sh$" "$T/out"
expect "$tool: the checker includes itself in its own coverage set" $?

step_failures_named 'signoff/run-signoff.sh' 'sim/selftest.sh'
step_new_covered 'verification/guard/new-script.sh'
step_untracked_ignored 'layout/.venv/bin/activate.sh' 'layout/.venv'
step_sparse_skipped 'sim/sparse.sh'
step_awkward_name 'sim/a dir with spaces/odd name.sh'
step_empty_fails 'no .*script'
step_non_git_fails
step_usage_fails

# The real repository: the drifted script is covered, vendored trees and the
# shared core behave, and cwd does not matter.
( cd / && bash "$real_root/scripts/lint-shell-syntax.sh" --list ) > "$T/real" 2>&1
expect "$tool: real repo: --list succeeds from an unrelated cwd" $?
grep -q '^verification/guard-mktemp-template/run-matrix\.sh$' "$T/real"
expect "$tool: real repo: run-matrix.sh (missed by the old chain) is covered" $?
! grep -qE '^(\.loom|\.claude|\.agents|\.github)/' "$T/real"
expect "$tool: real repo: no vendored installer-managed path is covered" $?
[ "$(wc -l < "$T/real")" -ge 12 ]
expect "$tool: real repo: covers at least the 12 repo-owned scripts" $?
grep -q '^scripts/lint_common\.sh$' "$T/real"
expect "$tool: real repo: the shared core is covered like any repo-owned script" $?

# =============================================================================
# lint-python-syntax.sh
# =============================================================================
tool=lint-python-syntax
noun='Python file'; noun_pl='Python files'
good='import os

print(os.name)'
broken='def f(:'   # a SyntaxError -- a py_compile failure, not a runtime one

setup_fake

add 'scripts/git_status.py'      "$good"
add 'sim/model/pll.py'           "$good"
add 'README.md'                  '# not a Python file'
add '.loom/scripts/loom.py'      "$broken"
add '.claude/skills/repo/scripts/repo.py' "$broken"
add '.agents/tools/agent.py'     "$broken"
add '.github/helper/workflow.py' "$broken"

expect_list <<'X'
scripts/git_status.py
sim/model/pll.py
X

run; expect "$tool: clean tree passes" $?
! grep -qE '\.(loom|claude|agents|github)/' "$T/out"
expect "$tool: vendored trees' syntax errors are not reported" $?

step_failures_named 'signoff/run_signoff.py' 'sim/selftest.py'
step_new_covered 'design/new_block/model.py'
step_untracked_ignored 'layout/.venv/lib/site.py' 'layout/.venv'
step_sparse_skipped 'sim/sparse.py'
step_awkward_name 'sim/a dir with spaces/odd name.py'
step_empty_fails 'no tracked Python'
step_non_git_fails
step_usage_fails

( cd / && bash "$real_root/scripts/lint-python-syntax.sh" --list ) > "$T/real" 2>&1
expect "$tool: real repo: --list succeeds from an unrelated cwd" $?
! grep -qE '^(\.loom|\.claude|\.agents|\.github)/' "$T/real"
expect "$tool: real repo: no vendored installer-managed path is covered" $?
[ "$(wc -l < "$T/real")" -gt 0 ]
expect "$tool: real repo: covers a non-empty set of tracked Python files" $?
grep -qE '\.py$' "$T/real"
expect "$tool: real repo: every covered path is a Python file" $?
# py_compile writes __pycache__ beside sources; it must leave no git churn.
git -C "$real_root" status --porcelain -- '**/__pycache__' > "$T/dirty"
[ ! -s "$T/dirty" ]; expect "$tool: real repo: py_compile leaves no tracked-tree churn" $?

# =============================================================================
# lint-json.sh
# =============================================================================
tool=lint-json
noun='JSON file'; noun_pl='JSON files'
good='{"ok": true}'
broken='{"broken":'   # malformed JSON -- a json.tool parse failure

setup_fake

# Discovery: tracked JSON under the four repo-owned roots in; everything
# else -- top-level files, vendored trees, non-JSON -- out.
add 'sim/config.json'         "$good"
add 'layout/cells.json'       "$good"
add 'measurements/sweep.json' "$good"
add 'signoff/record.json'     "$good"
add 'package.json'            "$broken"
add 'docs/data.json'          "$good"
add '.loom/config.json'       "$broken"
add '.claude/settings.json'   "$broken"
add 'sim/netlist.spice'       '* not json'

expect_list <<'X'
layout/cells.json
measurements/sweep.json
signoff/record.json
sim/config.json
X

run; expect "$tool: clean tree passes" $?
! grep -qE 'package\.json|docs/data\.json|\.loom/|\.claude/' "$T/out"
expect "$tool: malformed JSON outside the roots is not reported" $?

step_failures_named 'sim/measurements/bad.json' 'signoff/bad.json'
step_new_covered 'sim/new/dir/data.json'
step_untracked_ignored 'layout/.venv/config.json' 'layout/.venv'
step_sparse_skipped 'sim/sparse.json'
step_awkward_name 'sim/a dir with spaces/odd name.json'
step_empty_fails 'no tracked JSON'

# JSON present but only outside the four roots: the roots moved, and that is
# a discovery failure, not a clean pass.
mkdir -p "$empty/docs"
printf '%s\n' "$good" > "$empty/docs/data.json"
git -C "$empty" add -- docs/data.json
( cd "$T" && bash "$empty/scripts/lint-json.sh" ) > "$T/out" 2>&1; rc=$?
[ "$rc" -eq 2 ] && grep -qi 'no tracked JSON' "$T/out"
expect "$tool: JSON only outside the roots fails loudly rather than passing vacuously" $?

step_non_git_fails
step_usage_fails

( cd / && bash "$real_root/scripts/lint-json.sh" --list ) > "$T/real" 2>&1
expect "$tool: real repo: --list succeeds from an unrelated cwd" $?
! grep -qvE '^(sim|layout|measurements|signoff)/[^/].*\.json$' "$T/real"
expect "$tool: real repo: every covered path is JSON under a repo-owned root" $?
! grep -qE '^(\.loom|\.claude|\.agents)/' "$T/real"
expect "$tool: real repo: no vendored installer-managed path is covered" $?
[ "$(wc -l < "$T/real")" -gt 0 ]
expect "$tool: real repo: covers a non-empty set of tracked JSON files" $?

echo "1..$n"; [ "$fails" -eq 0 ]
