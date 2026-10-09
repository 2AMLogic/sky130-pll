#!/usr/bin/env bash
# run-matrix.sh - inert regression fixture for the Bash-tool write-confinement
# resolver and explicit `mktemp -d /tmp/<prefix>.XXXXXX` templates (issue #239).
#
# INERT BY CONSTRUCTION. Every command string below is passed to the hook as a
# JSON *data* field on stdin. This script never evaluates, sources or executes
# a command string, never creates the temp directory the strings mention, never
# runs a simulator, and writes nothing (all output goes to stdout/stderr).
#
# Usage:   bash verification/guard-mktemp-template/run-matrix.sh [PRIMARY_ROOT]
#          PRIMARY_ROOT defaults to the primary checkout of the enclosing repo.
# Needs:   bash, jq, git.
#
# Exit status (inspect the printed JSON-derived decisions, not just this):
#   0  every row matched its expectation (template row allows: defect resolved)
#   1  a CONTROL row diverged (guard inactive or containment regression)
#   2  INCONCLUSIVE: a prerequisite is missing or the hook output was unusable
#   3  all controls held, but the bounded-template row still denies
#      (the known blocked-upstream state recorded in the issue)
set -uo pipefail

inconclusive() { echo "INCONCLUSIVE: $*" >&2; exit 2; }

command -v jq  >/dev/null 2>&1 || inconclusive "jq not found"
command -v git >/dev/null 2>&1 || inconclusive "git not found"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# -ge 1 ]]; then
  root="$1"
else
  common="$(git -C "$here" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" \
    || inconclusive "not inside a git checkout"
  root="$(dirname "$common")"
fi
root="$(cd "$root" 2>/dev/null && pwd)" || inconclusive "primary root not accessible"
dispatcher="$root/.loom/hooks/guard-destructive.sh"

# ---- confinement prerequisites (missing context is inconclusive, never pass)
[[ -r "$dispatcher" ]] || inconclusive "dispatcher not readable: $dispatcher"
[[ -d "$root/.git" ]] || inconclusive "$root is not a primary checkout (.git is not a directory)"
nwt="$(git -C "$root" worktree list --porcelain | grep -c '^worktree ' || true)"
[[ "${nwt:-0}" -ge 2 ]] || inconclusive "no linked worktree exists; confinement is only active with one"
ls -d "$root"/.loom/worktrees/*/ >/dev/null 2>&1 \
  || inconclusive "no Loom-managed worktree under .loom/worktrees"
[[ "${LOOM_GUARD_WORKTREE_ISOLATION:-1}" != "0" ]] || inconclusive "LOOM_GUARD_WORKTREE_ISOLATION=0 in environment"
if [[ -r "$root/.loom/config.json" ]] \
   && [[ "$(jq -r '.guards.worktreeIsolation // true' "$root/.loom/config.json" 2>/dev/null)" == "false" ]]; then
  inconclusive "guards.worktreeIsolation=false in .loom/config.json"
fi

# ---- record: selected implementation and revisions
# The dispatcher is run under `bash -x` with an empty-command JSON input; the
# trace line `exec bash <path>` names the implementation it hands off to.
selected="$(printf '%s' "$(jq -n --arg cwd "$root" '{tool_name:"Bash",cwd:$cwd,tool_input:{command:"true"}}')" \
  | bash -x "$dispatcher" 2>&1 >/dev/null | sed -n 's/^+* *exec bash //p' | head -1)"
[[ -n "$selected" ]] || inconclusive "could not determine selected implementation"
sha() { sha256sum "$1" 2>/dev/null | cut -c1-16; }
echo "# source_revision:      $(git -C "$root" rev-parse HEAD)"
echo "# selected_impl:        ${selected#"$root"/}"
echo "# selected_impl_sha256: $(sha "$selected")"
echo "# dispatcher_sha256:    $(sha "$dispatcher")"
echo "# vendored_sha256:      $(sha "$root/.loom/hooks/guard-destructive-generic.sh")"
echo "# loom_version:         $(jq -r '.loom_version // "unknown"' "$root/.loom/install-metadata.json" 2>/dev/null)"
echo "# primary_root:         <PRIMARY_ROOT>  (placeholder; real path elided)"
echo "# linked_worktrees:     $((nwt - 1))"

# decide <command-text> -> prints allow|deny|ask|ERROR:<why>
decide() {
  local out rc dec
  out="$(jq -n --arg cwd "$root" --arg c "$1" \
        '{tool_name:"Bash",cwd:$cwd,tool_input:{command:$c}}' | bash "$dispatcher" 2>/dev/null)"
  rc=$?
  [[ $rc -eq 0 ]] || { echo "ERROR:hook-exit-$rc"; return; }
  [[ -z "$out" ]] && { echo allow; return; }
  dec="$(jq -r 'select(.hookSpecificOutput.hookEventName=="PreToolUse") | .hookSpecificOutput.permissionDecision // empty' <<<"$out" 2>/dev/null)"
  [[ -n "$dec" ]] && echo "$dec" || echo "ERROR:unparseable-output"
}

P='/PRIMARY_ROOT'                    # replaced with the real root at call time
T='mktemp -d /tmp/loom-guard-probe.XXXXXX'
# id | role | expected | command-text (single-quoted: never expanded here)
rows=(
 'R1|control|allow|S=$(mktemp -d); printf probe > "$S/result.txt"'
 'R2|control|allow|S=/tmp/loom-guard-probe; printf probe > "$S/result.txt"'
 'R3|control|deny|printf probe > "$UNKNOWN/result.txt"'
 'R4|control|deny|S=@P@; printf probe > "$S/result.txt"'
 'R5|control|deny|S=$('"$T"'); S=@P@; printf probe > "$S/result.txt"'
 'R6|control|deny|S=$('"$T"'); printf probe > "$S/../escape.txt"'
 'R7|control|deny|S=$(mktemp -d @P@/probe.XXXXXX); printf probe > "$S/result.txt"'
 'R0|target|allow|S=$('"$T"'); printf probe > "$S/result.txt"'
)

bad=0 target_state=""
printf '%-3s %-7s %-8s %-8s %s\n' ROW ROLE EXPECTED ACTUAL RESULT
for r in "${rows[@]}"; do
  IFS='|' read -r id role want cmd <<<"$r"
  cmd="${cmd//@P@/$root}"
  got="$(decide "$cmd")"
  [[ "$got" == ERROR:* ]] && inconclusive "row $id: $got"
  if [[ "$got" == "$want" ]]; then res=ok; else res=MISMATCH; fi
  printf '%-3s %-7s %-8s %-8s %s\n' "$id" "$role" "$want" "$got" "$res"
  if [[ $res == MISMATCH ]]; then
    [[ $role == target ]] && target_state="$got" || bad=1
  fi
done

# R3/R4 denying proves the guard is active (a dead guard would allow them);
# R1/R2 allowing proves it is not a blanket deny.
if [[ $bad -ne 0 ]]; then echo "RESULT: CONTROL MISMATCH (guard inactive or containment regression)"; exit 1; fi
if [[ -n "$target_state" ]]; then
  echo "RESULT: controls hold; bounded /tmp template row R0 = $target_state (expected allow): BLOCKED-UPSTREAM"
  exit 3
fi
echo "RESULT: all rows match; bounded template allows and every negative control denies"
exit 0
