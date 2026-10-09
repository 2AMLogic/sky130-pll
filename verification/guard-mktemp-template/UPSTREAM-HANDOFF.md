# Upstream handoff: bounded `mktemp -d /tmp/<prefix>.XXXXXX` in the write-confinement resolver

Text for a Repo Skills issue or PR against `hooks/repo/guard-destructive.sh`
(not filed from this repository). Written to stand alone.

## Problem

The Bash-tool write-confinement check resolves a same-command assignment such
as `S=$(mktemp -d)` as a fresh scratch directory, so a later
`printf x > "$S/result.txt"` is allowed. The equally bounded explicit-template
form is denied:

    S=$(mktemp -d /tmp/probe.XXXXXX); printf probe > "$S/result.txt"

Decision observed: `permissionDecision: deny`, reason "write target
'$S/result.txt' is an unexpanded shell variable from the path root down".
Bare `S=$(mktemp -d)` and literal `S=/tmp/probe` both allow, so the guard is
inconsistent about two equally safe scratch idioms. Observed on a Loom
install 0.19.966 vendored copy of the guard at source revision
`1ee7fb07c7ffe7253ebdab2f62cf4ea7abef1b28` of the consuming repository;
`wt_write_mktemp_same_command_safe()` accepts only bare forms.

## Proposed grammar (deliberately minimal)

Treat `VAR=$(mktemp -d TEMPLATE)` as a proven-safe scratch root only when
TEMPLATE is exactly, as one unquoted or fully quoted word:

    /tmp/<prefix>.XXXXXX

- `<prefix>`: non-empty, characters `[A-Za-z0-9_-]` only (no `/`, `.`, `$`,
  backtick, glob, brace, tilde, whitespace, or expansion of any kind).
- Suffix: exactly the literal `.XXXXXX` (six X).
- No other `mktemp` options (`-p`, `--tmpdir`, `-t`, `-u`, `--suffix`) and no
  additional words.
- Root is the literal `/tmp`; never `$TMPDIR`, `~`, relative paths, or any
  other directory.

Out of scope: arbitrary command substitution, report-ID or date expressions,
other roots, templates built from variables.

Required semantics: a write is allowed only if the resolved path stays inside
the allocated directory. The variable keeps its existing poisoning rules: any
later reassignment, `unset`, `export` rebinding, `eval`, or use in a position
the resolver cannot track invalidates the proof.

## Negative containment cases (must remain deny/ask as today)

| Case | Why |
| --- | --- |
| `printf x > "$UNKNOWN/result.txt"` | unresolved root |
| `S=$(mktemp -d /tmp/p.XXXXXX); S=<checkout>; printf x > "$S/r"` | reassignment poisons proof |
| `S=$(mktemp -d /tmp/p.XXXXXX); printf x > "$S/../escape.txt"` | parent traversal out of allocated dir |
| `S=$(mktemp -d /tmp/p.XXXXXX); printf x > "$S/a/../../escape"` | nested traversal |
| `S=$(mktemp -d <checkout>/p.XXXXXX); printf x > "$S/r"` | template root is a protected checkout |
| `S=$(mktemp -d /tmp/../<checkout>/p.XXXXXX); ...` | template root traverses out of `/tmp` |
| `S=$(mktemp -d /tmp/$X.XXXXXX); ...`, `/tmp/$(cmd).XXXXXX`, `` /tmp/`cmd`.XXXXXX `` | expansion in template |
| `S=$(mktemp -d /tmp/p.XXXXXX -p <checkout>); ...` | extra options/words |
| `S=$(mktemp -d /tmp/p.XXXXXX/sub.XXXXXX); ...` | multi-component template |
| `S=$(mktemp -d /tmp/p.XXXX); ...`, `/tmp/p.*`, `/tmp/p.{a,b}` | non-literal or short suffix |
| `S=$(mktemp -d /tmp/p.XXXXXX) && S=$OTHER; ...` | rebinding via a second assignment |
| symlink case: `/tmp/p.XXXXXX` allocated, then `ln -s <checkout> "$S/l"; printf x > "$S/l/r"` | symlink escape; if the guard cannot rule it out it must stay fail-closed |
| quoted variants: `"$S/r"`, `'$S/r'` (literal, not a variable), `${S}/r` | each judged on its real resolved path |

The symlink case needs a decision upstream: either the guard already treats a
write through a path component created in the same command as unresolved, or
the proof must be scoped to writes that do not traverse same-command links.

## Acceptance for the upstream change

1. Positive: the proposed literal template allows in quoted and unquoted forms.
2. Every row above keeps today's decision, in the canonical regression suite.
3. Dispatcher probes in consumer repos (version, write-confinement, search/jq
   masking, `--body @path`) still pass on the new release so the canonical
   guard remains selectable.
4. Release notes name the grammar so consumers can resync deliberately.

## Consumer re-validation

After a release carrying the change is consumed through the supported
resync, run
`bash verification/guard-mktemp-template/run-matrix.sh` from the primary
checkout of the consuming repository. Expect exit 0: row R0 allows and every
control row keeps its decision. Preserve the output as a new, append-only
record.
