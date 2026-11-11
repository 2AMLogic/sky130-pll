# Note 2026-11-11: the `remote` slot is retired

Supersedes the empty `remote` row in [`README.md`](README.md) (its "Status"
table). That README, like every record under `sim/`, is append-only and is left
unedited; this note is the dated supersession.

Issue #425 (operator ruling 2026-11-11) retired `--executor remote`: the
`RemoteBackend`, its `SKY130_PLL_REMOTE_*` configuration, and its silent
fallback to `local` were removed from the harness. `local` and `batch` remain.
This reverses the decision in #146 and gives up the path that waited on
2AMLogic/2am#934.

Consequences for this directory:

- The `remote` half described in `README.md` will never be produced, and the
  command it quotes (`--executor remote`) is now refused by the harness.
- The committed `local` record is unchanged and remains valid evidence.
- The `local`-vs-fleet equivalence question now concerns `--executor batch`;
  a fixture for it, if wanted, is new work with its own record.
