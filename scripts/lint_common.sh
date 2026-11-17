# Shared core for the repo-owned lint drivers: lint-shell-syntax.sh,
# lint-python-syntax.sh and lint-json.sh source this file -- it is never
# executed directly. One driver is three variable parts (the coverage glob,
# the per-file check command, the scope filter) around this fixed mechanism:
# option parsing, the git-repo guard, `ls-files -z` discovery, the
# empty-coverage-set guard (#482), skip handling and the summary line.
#
# A wrapper defines, before sourcing this file:
#   LINT_TOOL        program name, the prefix of every message and the usage
#                    line (e.g. "lint-shell-syntax")
#   LINT_GLOB        the git ls-files pathspec glob (e.g. '*.sh')
#   LINT_FILTER      "vendored" -- cover everything except VENDORED_PREFIXES,
#                    or "roots" -- cover only LINT_ROOTS
#   LINT_ROOTS       (roots mode only) array of include prefixes
#   LINT_NOUN_PLURAL what a covered path is called in messages ("shell
#                    scripts", "Python files", "JSON files")
#   LINT_UNIT        the counting noun in failure/summary lines ("script(s)")
#   LINT_CHECKER     the checker named in failure/summary lines ("bash -n")
#   LINT_ACTION      the "(no option)" line of the usage text (may span lines)
#   lint_check_one   a function taking one absolute path, returning non-zero
#                    when the file fails the check
#
# Contract, identical for every driver (#482):
#   Exit codes: 0 every file passed; 1 at least one failure;
#   2 usage error or a discovery failure (not a git repo, empty coverage set).
#   --list prints the discovered coverage set, one path per line, and exits 0.
set -uo pipefail

if [ -z "${LINT_TOOL:-}" ] || [ -z "${LINT_GLOB:-}" ] || [ -z "${LINT_FILTER:-}" ] \
  || ! declare -F lint_check_one >/dev/null; then
  echo "lint_common: sourced without a driver's configuration --" \
    "define LINT_TOOL, LINT_GLOB, LINT_FILTER and lint_check_one first" >&2
  exit 2
fi
if [ "$LINT_FILTER" != "vendored" ] && [ "$LINT_FILTER" != "roots" ]; then
  echo "lint_common: LINT_FILTER must be 'vendored' or 'roots', got '$LINT_FILTER'" >&2
  exit 2
fi
if [ "$LINT_FILTER" = "roots" ]; then
  if [ "${LINT_ROOTS+x}" != x ] || [ "${#LINT_ROOTS[@]}" -eq 0 ]; then
    echo "lint_common: LINT_FILTER=roots requires a non-empty LINT_ROOTS array" >&2
    exit 2
  fi
fi

# Installer-managed trees whose contents this repository does not own and must
# not lint: `.loom/` is provisioned by Loom, `.claude/` by the Loom and Repo
# Skills installers, `.agents/` by the agent-harness installer, `.github/` by
# the CI-workflow installer (see CLAUDE.md "repo-owned files"). Upstream owns
# their syntax; a failure there would be unfixable in this repo. Defined once
# here so the drivers cannot drift apart again (#507).
VENDORED_PREFIXES=(".loom/" ".claude/" ".agents/" ".github/")

usage() {
  cat <<USAGE
Usage: bash scripts/${LINT_TOOL}.sh [--list]

  (no option)  ${LINT_ACTION}
  --list       print the discovered coverage set, one path per line, and exit
USAGE
}

list_only=0
case "${1-}" in
  "")       ;;
  --list)   list_only=1 ;;
  -h|--help) usage; exit 0 ;;
  *)        echo "$LINT_TOOL: unknown option '$1'" >&2; usage >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
  echo "$LINT_TOOL: too many arguments" >&2; usage >&2; exit 2
fi

# The core lives beside its wrappers, so the repo root is one level above the
# directory holding this file -- derived from the script's own location, not
# from the caller's cwd.
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! git -C "$root" rev-parse --git-dir >/dev/null 2>&1; then
  echo "$LINT_TOOL: $root is not a git repository -- cannot discover $LINT_NOUN_PLURAL" >&2
  exit 2
fi

# -z plus `read -d ''` so a path containing a space or newline survives intact.
files=()
while IFS= read -r -d '' path; do
  keep=0
  case "$LINT_FILTER" in
    vendored)
      keep=1
      for prefix in "${VENDORED_PREFIXES[@]}"; do
        case "$path" in "$prefix"*) keep=0; break ;; esac
      done
      ;;
    roots)
      for prefix in "${LINT_ROOTS[@]}"; do
        case "$path" in "$prefix"*) keep=1; break ;; esac
      done
      ;;
  esac
  [ "$keep" -eq 1 ] || continue
  files+=("$path")
done < <(git -C "$root" ls-files -z -- "$LINT_GLOB")

# An empty coverage set means discovery broke (wrong root, over-broad
# exclusion, roots renamed), not that the repo is clean. Fail rather than
# pass vacuously (#482).
if [ "${#files[@]}" -eq 0 ]; then
  case "$LINT_FILTER" in
    vendored) where="under $root" ;;
    roots)    where="under the repo-owned roots in $root" ;;
  esac
  echo "$LINT_TOOL: no tracked $LINT_NOUN_PLURAL found $where -- discovery is broken" >&2
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
  lint_check_one "$root/$path" || failed+=("$path")
done

for path in "${skipped[@]}"; do
  echo "$LINT_TOOL: skipped $path (tracked but absent from the working tree)" >&2
done

if [ "${#failed[@]}" -gt 0 ]; then
  echo "$LINT_TOOL: ${#failed[@]} of ${#files[@]} $LINT_UNIT failed $LINT_CHECKER:" >&2
  printf '  %s\n' "${failed[@]}" >&2
  exit 1
fi

checked=$(( ${#files[@]} - ${#skipped[@]} ))
echo "$LINT_TOOL: $checked $LINT_UNIT passed $LINT_CHECKER"
