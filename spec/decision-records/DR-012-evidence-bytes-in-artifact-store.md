# DR-012: raw run evidence goes to the artifact store; git keeps manifest and summary

- **Status**: ratified (a change to evidence handling, authorized by issue #370;
  it touches no spec row and no ratified value)
- **Date**: 2026-10-23
- **Author**: Builder agent (issue #370)
- **Ratifies against / input to**: #370
- **Supersedes**: the "Retention policy" table and the `.gitignore` negation of
  `*.log` for `sim/*/corners/` in `sim/README.md`, for runs minted after this
  record. No earlier decision record is superseded.

## Context

`sim/` and `layout/` commit raw run output, about 78 MB at the time of writing.
`sim/README.md` § "Retention policy" says per-point logs and patched netlists
are "Always, committed", § "Append-only rule" covers `corners/<record-id>/*`
and `netlist-snapshots/*.spice`, and the root `.gitignore` un-ignores
`sim/*/corners/**/*.log`. The fleet now has a common artifact store reached
through `klt artifact`: a repo commits a small manifest that names each object
by sha256, and the bytes live behind a broker. Using it means changing those
three statements, which is why this is a decision record. No spec row, limit
or ratified number is involved.

## Decision

For a run minted after this record, the raw bytes (per-point logs, patched
netlists, the frozen netlist snapshot, probe logs) are stored with
`klt artifact put`. Git keeps only `manifests/artifacts/<bench>-<run-id>.manifest.json`
and the Markdown record `sim/<bench>/records/<run-id>.md`, which ends with a
table of every stored object. Those two files are the committed evidence; the
record keeps citing the logical `sim/<slug>/...` paths, which are the manifest
`name`s. History is not rewritten and every existing record, snapshot and
`corners/<id>/` tree stays in git exactly as written.

The writer (`sim/harness/evidence_store.py`) fails closed. If the broker is
unset or unreachable, `klt` is missing or lacks `artifact put`, or a put fails
or disagrees with the local hash, the run exits nonzero, commits nothing and
leaves the staged bytes in the git-ignored scratch tree `sim/build/`. There is
no fallback that commits the bytes.

## Alternatives considered

- **Keep committing bytes.** Rejected: the repo only grows, and the store
  exists for this.
- **Rewrite history or move the existing ~78 MB out.** Rejected: it would edit
  append-only evidence and break the `content_hash` pins that
  `signoff/run-signoff.sh --check` re-grades. Out of scope here.
- **A size budget file.** Rejected: this repo has no ceiling today, so there is
  nothing to rebase; manifests are small.
- **Fall back to committing when the store is down.** Rejected: it is the
  failure mode this record exists to remove, and it would make the committed
  evidence depend on broker availability.

## Consequences

- A run can only be minted where the broker is reachable (a fleet worker).
  A host without it can still run with `--no-write`.
- The raw bytes of a new run are private to callers the broker admits; the
  manifest and record are public-safe. A manifest names no storage location
  (`artifact:<key>` only), enforced by `scripts/check_artifact_manifests.py`.
- `layout/` output uses a different write path and is not changed here.
- `run_locktiming.py` writes JSON records and group directories itself and is
  not routed through the store by this record.
- The layout of `manifests/` is documented in `manifests/README.md`.

## Status notes

Ratified on merge of the PR for #370. Whether the signoff graders read any
`corners/<id>/*` file for a *new* record is checked on that PR.
