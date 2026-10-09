# guard-mktemp-template

Inert regression fixture for issue #239: does the Bash-tool write-confinement
guard allow `S=$(mktemp -d /tmp/<prefix>.XXXXXX); ... > "$S/file"` while keeping
fail-closed containment?

- `run-matrix.sh` - feeds eight command strings as JSON data to
  `.loom/hooks/guard-destructive.sh` and compares each `permissionDecision` to
  its expectation. Nothing is executed or written. Needs bash, jq, git, and a
  primary checkout with at least one linked Loom worktree (otherwise the result
  is inconclusive, exit 2). See the script header for exit codes.
- `RECORD-*.md` - append-only dated results. Never edit; add a new one that
  names what it supersedes.
- `UPSTREAM-HANDOFF.md` - proposed generic fix for Repo Skills, with negative
  containment cases. The vendored hooks in this repository are not edited.
