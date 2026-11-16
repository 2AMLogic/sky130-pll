#!/usr/bin/env bash
# Fixture tests for scripts/lint-python-syntax.sh.
#
# Most cases run the script against a throwaway git repository built under
# mktemp, so discovery can be driven to its edges (vendored trees, untracked
# files, an empty listing, awkward names) without touching this checkout. The
# last block asserts properties against the real repository: the coverage set
# is non-empty and no vendored path is ever in it.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/../lint-python-syntax.sh"
real_root="$(cd "$here/../.." && pwd)"

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fails=0; n=0
ok()  { n=$((n+1)); echo "ok $n - $1"; }
bad() { n=$((n+1)); fails=$((fails+1)); echo "not ok $n - $1"; }
expect() { # desc cond-exit
  if [ "$2" -eq 0 ]; then ok "$1"; else bad "$1"; fi
}

# A fake repository with the script copied in, so the script's notion of its
# repo root is the fake one. Paths are staged, not committed: `git ls-files`
# reads the index, so `git add` is enough.
repo="$T/fake repo"
mkdir -p "$repo/scripts/tests"
cp "$src" "$repo/scripts/lint-python-syntax.sh"
git -C "$repo" init -q
git -C "$repo" config user.email loom@example.invalid
git -C "$repo" config user.name loom
git -C "$repo" add -- scripts/lint-python-syntax.sh

add() { # relpath contents
  mkdir -p "$repo/$(dirname "$1")"
  printf '%s\n' "$2" > "$repo/$1"
  git -C "$repo" add -- "$1"
}
run() { # [args...] -> stdout+stderr in $T/out, exit status returned
  ( cd "$T" && bash "$repo/scripts/lint-python-syntax.sh" "$@" ) > "$T/out" 2>&1
}

good='import os

print(os.name)'
broken='def f(:'   # a SyntaxError -- a py_compile failure, not a runtime one

# ---------------------------------------------------------------------------
# 1. Discovery: repo-owned Python files in, vendored installer trees out.
# ---------------------------------------------------------------------------
add 'scripts/git_status.py'      "$good"
add 'sim/model/pll.py'           "$good"
add 'README.md'                  '# not a Python file'
add '.loom/scripts/loom.py'      "$broken"
add '.claude/skills/repo/scripts/repo.py' "$broken"
add '.agents/tools/agent.py'     "$broken"
add '.github/helper/workflow.py' "$broken"

run --list; rc=$?
cat > "$T/want" <<'X'
scripts/git_status.py
sim/model/pll.py
X
[ $rc -eq 0 ] && diff -u "$T/want" "$T/out" > "$T/diff"; listed=$?
expect "--list reports exactly the repo-owned tracked Python files" "$listed"
[ "$listed" -eq 0 ] || cat "$T/diff" 2>/dev/null

run; expect "clean tree passes" $?
! grep -qE '\.(loom|claude|agents|github)/' "$T/out"
expect "vendored trees' syntax errors are not reported" $?

# ---------------------------------------------------------------------------
# 2. A broken repo-owned file fails with exit 1, and is named.
# ---------------------------------------------------------------------------
add 'signoff/run_signoff.py' "$broken"
run; rc=$?
[ $rc -eq 1 ] && grep -q 'signoff/run_signoff\.py' "$T/out"
expect "syntax error fails with exit 1 and names the file" $?

# Every file is checked, so one bad file does not mask a second.
add 'sim/selftest.py' "$broken"
run; rc=$?
[ $rc -eq 1 ] \
  && grep -q 'signoff/run_signoff\.py' "$T/out" \
  && grep -q 'sim/selftest\.py' "$T/out"
expect "all failures are reported, not just the first" $?
git -C "$repo" rm -q --cached -- signoff/run_signoff.py sim/selftest.py
rm -f "$repo/signoff/run_signoff.py" "$repo/sim/selftest.py"
run; expect "removing the broken files restores a passing tree" $?

# ---------------------------------------------------------------------------
# 3. The regression this replaces: a file added without editing any list.
# ---------------------------------------------------------------------------
add 'design/new_block/model.py' "$broken"
run; rc=$?
[ $rc -ne 0 ] && grep -q 'design/new_block/model\.py' "$T/out"
expect "a newly tracked Python file is covered with no list to update" $?
git -C "$repo" rm -q --cached -- design/new_block/model.py
rm -f "$repo/design/new_block/model.py"

# ---------------------------------------------------------------------------
# 4. Untracked files are out of scope (e.g. an untracked virtualenv).
# ---------------------------------------------------------------------------
mkdir -p "$repo/layout/.venv/lib"
printf '%s\n' "$broken" > "$repo/layout/.venv/lib/site.py"
run; expect "untracked file with a syntax error is ignored" $?
rm -rf "$repo/layout/.venv"

# ---------------------------------------------------------------------------
# 5. A path tracked but absent from the working tree is skipped, not fatal
#    (sparse checkout), and is reported as skipped.
# ---------------------------------------------------------------------------
add 'sim/sparse.py' "$good"
rm -f "$repo/sim/sparse.py"
run; rc=$?
[ $rc -eq 0 ] && grep -qi 'skip' "$T/out" && grep -q 'sim/sparse\.py' "$T/out"
expect "tracked-but-absent path is skipped with a notice, not an error" $?
git -C "$repo" rm -q --cached -- sim/sparse.py

# ---------------------------------------------------------------------------
# 6. Awkward names survive the discovery pipeline.
# ---------------------------------------------------------------------------
add 'sim/a dir with spaces/odd name.py' "$broken"
run; rc=$?
[ $rc -ne 0 ] && grep -q 'odd name\.py' "$T/out"
expect "path containing spaces is checked and reported" $?
git -C "$repo" rm -q --cached -- 'sim/a dir with spaces/odd name.py'
rm -rf "$repo/sim/a dir with spaces"

# ---------------------------------------------------------------------------
# 7. An empty coverage set is a failure, not a pass. A filter that silently
#    matches nothing is the failure mode this script exists to prevent.
# ---------------------------------------------------------------------------
empty="$T/empty repo"; mkdir -p "$empty/scripts"
cp "$src" "$empty/scripts/lint-python-syntax.sh"
git -C "$empty" init -q
git -C "$empty" add -- scripts/lint-python-syntax.sh
( cd "$T" && bash "$empty/scripts/lint-python-syntax.sh" ) > "$T/out" 2>&1; rc=$?
[ $rc -eq 2 ] && grep -qi 'no tracked Python' "$T/out"
expect "discovering zero files fails loudly with exit 2" $?

# Outside a git repository at all: fail, never silently pass.
bare="$T/not a repo"; mkdir -p "$bare/scripts"
cp "$src" "$bare/scripts/lint-python-syntax.sh"
( cd "$T" && bash "$bare/scripts/lint-python-syntax.sh" ) > "$T/out" 2>&1; rc=$?
[ $rc -eq 2 ]; expect "non-git directory fails with exit 2 rather than passing vacuously" $?

# ---------------------------------------------------------------------------
# 8. Usage.
# ---------------------------------------------------------------------------
run --nonsense; rc=$?
[ $rc -eq 2 ] && grep -qi 'usage' "$T/out"
expect "unknown option fails with usage and exit 2" $?

# ---------------------------------------------------------------------------
# 9. The real repository: coverage is non-empty, vendored trees are not, and
#    cwd does not matter.
# ---------------------------------------------------------------------------
( cd / && bash "$real_root/scripts/lint-python-syntax.sh" --list ) > "$T/real" 2>&1
expect "real repo: --list succeeds from an unrelated cwd" $?
! grep -qE '^(\.loom|\.claude|\.agents|\.github)/' "$T/real"
expect "real repo: no vendored installer-managed path is covered" $?
[ "$(wc -l < "$T/real")" -gt 0 ]
expect "real repo: covers a non-empty set of tracked Python files" $?
grep -qE '\.py$' "$T/real"
expect "real repo: every covered path is a Python file" $?
# py_compile writes __pycache__ beside sources; it must leave no git churn.
git -C "$real_root" status --porcelain -- '**/__pycache__' > "$T/dirty"
[ ! -s "$T/dirty" ]; expect "real repo: py_compile leaves no tracked-tree churn" $?

echo "1..$n"; [ $fails -eq 0 ]
