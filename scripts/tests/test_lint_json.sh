#!/usr/bin/env bash
# Fixture tests for scripts/lint-json.sh.
#
# Most cases run the script against a throwaway git repository built under
# mktemp, so discovery can be driven to its edges (the four repo-owned roots,
# files outside them, untracked files, an empty listing, awkward names)
# without touching this checkout. The last block asserts properties against
# the real repository: the coverage set is non-empty, confined to the roots,
# and cwd does not matter.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/../lint-json.sh"
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
cp "$src" "$repo/scripts/lint-json.sh"
git -C "$repo" init -q
git -C "$repo" config user.email loom@example.invalid
git -C "$repo" config user.name loom
git -C "$repo" add -- scripts/lint-json.sh

add() { # relpath contents
  mkdir -p "$repo/$(dirname "$1")"
  printf '%s\n' "$2" > "$repo/$1"
  git -C "$repo" add -- "$1"
}
run() { # [args...] -> stdout+stderr in $T/out, exit status returned
  ( cd "$T" && bash "$repo/scripts/lint-json.sh" "$@" ) > "$T/out" 2>&1
}

good='{"ok": true}'
broken='{"broken":'   # malformed JSON -- a json.tool parse failure

# ---------------------------------------------------------------------------
# 1. Discovery: tracked JSON under the four repo-owned roots in; everything
#    else -- top-level files, vendored trees, non-JSON -- out.
# ---------------------------------------------------------------------------
add 'sim/config.json'         "$good"
add 'layout/cells.json'       "$good"
add 'measurements/sweep.json' "$good"
add 'signoff/record.json'     "$good"
add 'package.json'            "$broken"
add 'docs/data.json'          "$good"
add '.loom/config.json'       "$broken"
add '.claude/settings.json'   "$broken"
add 'sim/netlist.spice'       '* not json'

run --list; rc=$?
cat > "$T/want" <<'X'
layout/cells.json
measurements/sweep.json
signoff/record.json
sim/config.json
X
[ $rc -eq 0 ] && diff -u "$T/want" "$T/out" > "$T/diff"; listed=$?
expect "--list reports exactly the tracked JSON under the four roots" "$listed"
[ "$listed" -eq 0 ] || cat "$T/diff" 2>/dev/null

run; expect "clean tree passes" $?
! grep -qE 'package\.json|docs/data\.json|\.loom/|\.claude/' "$T/out"
expect "malformed JSON outside the roots is not reported" $?

# ---------------------------------------------------------------------------
# 2. A broken file under a root fails with exit 1, and is named.
# ---------------------------------------------------------------------------
add 'sim/measurements/bad.json' "$broken"
run; rc=$?
[ $rc -eq 1 ] && grep -q 'sim/measurements/bad\.json' "$T/out"
expect "malformed JSON fails with exit 1 and names the file" $?

# Every file is checked, so one bad file does not mask a second.
add 'signoff/bad.json' "$broken"
run; rc=$?
[ $rc -eq 1 ] \
  && grep -q 'sim/measurements/bad\.json' "$T/out" \
  && grep -q 'signoff/bad\.json' "$T/out"
expect "all failures are reported, not just the first" $?
git -C "$repo" rm -q --cached -- sim/measurements/bad.json signoff/bad.json
rm -f "$repo/sim/measurements/bad.json" "$repo/signoff/bad.json"
run; expect "removing the broken files restores a passing tree" $?

# ---------------------------------------------------------------------------
# 3. The regression this replaces: a file added under a root with no list to
#    update.
# ---------------------------------------------------------------------------
add 'sim/new/dir/data.json' "$broken"
run; rc=$?
[ $rc -ne 0 ] && grep -q 'sim/new/dir/data\.json' "$T/out"
expect "a newly tracked JSON file under a root is covered with no list to update" $?
git -C "$repo" rm -q --cached -- sim/new/dir/data.json
rm -f "$repo/sim/new/dir/data.json"

# ---------------------------------------------------------------------------
# 4. Untracked files are out of scope -- the reason the old find pipeline's
#    layout/.venv exclusion could go away entirely.
# ---------------------------------------------------------------------------
mkdir -p "$repo/layout/.venv"
printf '%s\n' "$broken" > "$repo/layout/.venv/config.json"
run; expect "untracked file with malformed JSON is ignored" $?
rm -rf "$repo/layout/.venv"

# ---------------------------------------------------------------------------
# 5. A path tracked but absent from the working tree is skipped, not fatal
#    (sparse checkout), and is reported as skipped.
# ---------------------------------------------------------------------------
add 'sim/sparse.json' "$good"
rm -f "$repo/sim/sparse.json"
run; rc=$?
[ $rc -eq 0 ] && grep -qi 'skip' "$T/out" && grep -q 'sim/sparse\.json' "$T/out"
expect "tracked-but-absent path is skipped with a notice, not an error" $?
git -C "$repo" rm -q --cached -- sim/sparse.json

# ---------------------------------------------------------------------------
# 6. Awkward names survive the discovery pipeline.
# ---------------------------------------------------------------------------
add 'sim/a dir with spaces/odd name.json' "$broken"
run; rc=$?
[ $rc -ne 0 ] && grep -q 'odd name\.json' "$T/out"
expect "path containing spaces is checked and reported" $?
git -C "$repo" rm -q --cached -- 'sim/a dir with spaces/odd name.json'
rm -rf "$repo/sim/a dir with spaces"

# ---------------------------------------------------------------------------
# 7. An empty coverage set is a failure, not a pass. A root set that silently
#    matches nothing -- including JSON that exists only outside the roots --
#    is the failure mode this script exists to prevent.
# ---------------------------------------------------------------------------
empty="$T/empty repo"; mkdir -p "$empty/scripts"
cp "$src" "$empty/scripts/lint-json.sh"
git -C "$empty" init -q
git -C "$empty" add -- scripts/lint-json.sh
( cd "$T" && bash "$empty/scripts/lint-json.sh" ) > "$T/out" 2>&1; rc=$?
[ $rc -eq 2 ] && grep -qi 'no tracked JSON' "$T/out"
expect "discovering zero files fails loudly with exit 2" $?

# JSON present but only outside the four roots: the roots moved, and that is
# a discovery failure, not a clean pass.
add_outside() { # repo relpath contents
  mkdir -p "$1/$(dirname "$2")"
  printf '%s\n' "$3" > "$1/$2"
  git -C "$1" add -- "$2"
}
add_outside "$empty" 'docs/data.json' "$good"
( cd "$T" && bash "$empty/scripts/lint-json.sh" ) > "$T/out" 2>&1; rc=$?
[ $rc -eq 2 ] && grep -qi 'no tracked JSON' "$T/out"
expect "JSON only outside the roots fails loudly rather than passing vacuously" $?

# Outside a git repository at all: fail, never silently pass.
bare="$T/not a repo"; mkdir -p "$bare/scripts"
cp "$src" "$bare/scripts/lint-json.sh"
( cd "$T" && bash "$bare/scripts/lint-json.sh" ) > "$T/out" 2>&1; rc=$?
[ $rc -eq 2 ]; expect "non-git directory fails with exit 2 rather than passing vacuously" $?

# ---------------------------------------------------------------------------
# 8. Usage.
# ---------------------------------------------------------------------------
run --nonsense; rc=$?
[ $rc -eq 2 ] && grep -qi 'usage' "$T/out"
expect "unknown option fails with usage and exit 2" $?

# ---------------------------------------------------------------------------
# 9. The real repository: coverage is non-empty and confined to the four
#    roots, and cwd does not matter.
# ---------------------------------------------------------------------------
( cd / && bash "$real_root/scripts/lint-json.sh" --list ) > "$T/real" 2>&1
expect "real repo: --list succeeds from an unrelated cwd" $?
! grep -qvE '^(sim|layout|measurements|signoff)/[^/].*\.json$' "$T/real"
expect "real repo: every covered path is JSON under a repo-owned root" $?
! grep -qE '^(\.loom|\.claude|\.agents)/' "$T/real"
expect "real repo: no vendored installer-managed path is covered" $?
[ "$(wc -l < "$T/real")" -gt 0 ]
expect "real repo: covers a non-empty set of tracked JSON files" $?

echo "1..$n"; [ $fails -eq 0 ]
