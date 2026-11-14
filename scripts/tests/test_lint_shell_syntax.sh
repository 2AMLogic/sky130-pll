#!/usr/bin/env bash
# Fixture tests for scripts/lint-shell-syntax.sh.
#
# Most cases run the script against a throwaway git repository built under
# mktemp, so discovery can be driven to its edges (vendored trees, untracked
# files, an empty listing, awkward names) without touching this checkout. The
# last block asserts two properties against the real repository: the script
# that the superseded hand-written chain in package.json forgot is discovered,
# and no vendored path ever is.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/../lint-shell-syntax.sh"
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
cp "$src" "$repo/scripts/lint-shell-syntax.sh"
git -C "$repo" init -q
git -C "$repo" config user.email loom@example.invalid
git -C "$repo" config user.name loom
git -C "$repo" add -- scripts/lint-shell-syntax.sh

add() { # relpath contents
  mkdir -p "$repo/$(dirname "$1")"
  printf '%s\n' "$2" > "$repo/$1"
  git -C "$repo" add -- "$1"
}
run() { # [args...] -> stdout+stderr in $T/out, exit status returned
  ( cd "$T" && bash "$repo/scripts/lint-shell-syntax.sh" "$@" ) > "$T/out" 2>&1
}

good='#!/usr/bin/env bash
echo fine'
broken='#!/usr/bin/env bash
if true; then'   # unterminated `if` -- a bash -n failure, not a runtime one

# ---------------------------------------------------------------------------
# 1. Discovery: repo-owned scripts in, vendored installer trees out.
# ---------------------------------------------------------------------------
add 'loom.sh'                   "$good"
add 'sim/bin/pdk-env.sh'        "$good"
add 'verification/run-matrix.sh' "$good"
add 'README.md'                 '# not a shell script'
add '.loom/scripts/worktree.sh' "$broken"
add '.claude/skills/repo/scripts/repo-remote.sh' "$broken"

run --list; rc=$?
cat > "$T/want" <<'X'
loom.sh
scripts/lint-shell-syntax.sh
sim/bin/pdk-env.sh
verification/run-matrix.sh
X
[ $rc -eq 0 ] && diff -u "$T/want" "$T/out" > "$T/diff"; listed=$?
expect "--list reports exactly the repo-owned tracked shell scripts" "$listed"
[ "$listed" -eq 0 ] || cat "$T/diff" 2>/dev/null

run; expect "clean tree passes" $?
! grep -q '\.loom/' "$T/out"
expect "vendored .loom/ syntax error is not reported" $?

# The script checks itself: it is a tracked .sh file like any other. This is
# the property the enumeration in package.json structurally could not have.
run --list; grep -q '^scripts/lint-shell-syntax\.sh$' "$T/out"
expect "the checker includes itself in its own coverage set" $?

# ---------------------------------------------------------------------------
# 2. A broken repo-owned script fails, and is named.
# ---------------------------------------------------------------------------
add 'signoff/run-signoff.sh' "$broken"
run; rc=$?
[ $rc -ne 0 ] && grep -q 'signoff/run-signoff\.sh' "$T/out"
expect "syntax error fails non-zero and names the file" $?

# Every file is checked, so one bad script does not mask a second.
add 'sim/selftest.sh' "$broken"
run; rc=$?
[ $rc -ne 0 ] \
  && grep -q 'signoff/run-signoff\.sh' "$T/out" \
  && grep -q 'sim/selftest\.sh' "$T/out"
expect "all failures are reported, not just the first" $?
git -C "$repo" rm -q --cached -- signoff/run-signoff.sh sim/selftest.sh
rm -f "$repo/signoff/run-signoff.sh" "$repo/sim/selftest.sh"
run; expect "removing the broken scripts restores a passing tree" $?

# ---------------------------------------------------------------------------
# 3. The regression this replaces: a script added without editing any list.
# ---------------------------------------------------------------------------
add 'verification/guard/new-script.sh' "$broken"
run; rc=$?
[ $rc -ne 0 ] && grep -q 'verification/guard/new-script\.sh' "$T/out"
expect "a newly tracked script is covered with no list to update" $?
git -C "$repo" rm -q --cached -- verification/guard/new-script.sh
rm -f "$repo/verification/guard/new-script.sh"

# ---------------------------------------------------------------------------
# 4. Untracked files are out of scope (e.g. the untracked layout virtualenv).
# ---------------------------------------------------------------------------
mkdir -p "$repo/layout/.venv/bin"
printf '%s\n' "$broken" > "$repo/layout/.venv/bin/activate.sh"
run; expect "untracked file with a syntax error is ignored" $?
rm -rf "$repo/layout/.venv"

# ---------------------------------------------------------------------------
# 5. A path tracked but absent from the working tree is skipped, not fatal
#    (sparse checkout), and is reported as skipped.
# ---------------------------------------------------------------------------
add 'sim/sparse.sh' "$good"
rm -f "$repo/sim/sparse.sh"
run; rc=$?
[ $rc -eq 0 ] && grep -qi 'skip' "$T/out" && grep -q 'sim/sparse\.sh' "$T/out"
expect "tracked-but-absent path is skipped with a notice, not an error" $?
git -C "$repo" rm -q --cached -- sim/sparse.sh

# ---------------------------------------------------------------------------
# 6. Awkward names survive the discovery pipeline.
# ---------------------------------------------------------------------------
add 'sim/a dir with spaces/odd name.sh' "$broken"
run; rc=$?
[ $rc -ne 0 ] && grep -q 'odd name\.sh' "$T/out"
expect "path containing spaces is checked and reported" $?
git -C "$repo" rm -q --cached -- 'sim/a dir with spaces/odd name.sh'
rm -rf "$repo/sim/a dir with spaces"

# ---------------------------------------------------------------------------
# 7. An empty coverage set is a failure, not a pass. A filter that silently
#    matches nothing is the failure mode this script exists to prevent.
# ---------------------------------------------------------------------------
empty="$T/empty repo"; mkdir -p "$empty/scripts"
cp "$src" "$empty/scripts/lint-shell-syntax.sh"
git -C "$empty" init -q
( cd "$T" && bash "$empty/scripts/lint-shell-syntax.sh" ) > "$T/out" 2>&1; rc=$?
[ $rc -ne 0 ] && grep -qi 'no .*script' "$T/out"
expect "discovering zero scripts fails loudly" $?

# Outside a git repository at all: fail, never silently pass.
bare="$T/not a repo"; mkdir -p "$bare/scripts"
cp "$src" "$bare/scripts/lint-shell-syntax.sh"
( cd "$T" && bash "$bare/scripts/lint-shell-syntax.sh" ) > "$T/out" 2>&1; rc=$?
[ $rc -ne 0 ]; expect "non-git directory fails rather than passing vacuously" $?

# ---------------------------------------------------------------------------
# 8. Usage.
# ---------------------------------------------------------------------------
run --nonsense; rc=$?
[ $rc -ne 0 ] && grep -qi 'usage' "$T/out"
expect "unknown option fails with usage" $?

# ---------------------------------------------------------------------------
# 9. The real repository: the drifted script is covered, vendored trees are
#    not, and cwd does not matter.
# ---------------------------------------------------------------------------
( cd / && bash "$real_root/scripts/lint-shell-syntax.sh" --list ) > "$T/real" 2>&1
expect "real repo: --list succeeds from an unrelated cwd" $?
grep -q '^verification/guard-mktemp-template/run-matrix\.sh$' "$T/real"
expect "real repo: run-matrix.sh (missed by the old chain) is covered" $?
! grep -qE '^(\.loom|\.claude)/' "$T/real"
expect "real repo: no vendored installer-managed path is covered" $?
[ "$(wc -l < "$T/real")" -ge 12 ]
expect "real repo: covers at least the 12 repo-owned scripts" $?

echo "1..$n"; [ $fails -eq 0 ]
