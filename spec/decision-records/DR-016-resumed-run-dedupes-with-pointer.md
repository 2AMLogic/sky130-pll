# DR-016: a resumed run deduplicates at stage time, with a `supplied_by` pointer

- **Status**: proposed (the operator ratifies it on PR #411; agents do not self-ratify)
- **Date**: 2026-11-06
- **Author**: Doctor agent (PR #411, issue #276), implementing operator ruling r7-q21
- **Ratifies against / input to**: PR #411, #276
- **Supersedes**: N/A. It narrows, and does not reverse, DR-014's rejection of content dedupe.

## Context

`scripts/check_artifact_manifests.py` rejects a manifest entry whose bytes equal a
tracked file (DR-012: stored bytes live in exactly one place). The resumed
watchdog run on PR #411 regenerated netlists (`body.spice`) and requests
(`request.json`) byte-identical to those already committed under the superseded
October records, so 8 new manifests collided with them (12 problems). The October
records are append-only, and re-running the corners reproduces the same bytes.
DR-014 rejected content-dedupe in the harness ("record completeness would depend
on repo state at run time") and a checker exemption ("loosens a verification gate").

## Decision

1. `evidence_store.split_resumed` omits a staged file only when the run is a
   **resume of a named prior record** and the file's (sha256, size) equals a file
   committed **under that lineage**: the record named by `--supersedes` and the
   group records already present under the matrix's `groups/` directory when the
   resume started (the ones `--resume` reads). The lineage is declared by the run
   (`--resume`, `--supersedes`), so completeness depends on the run's own
   declared ancestry and not on whatever else is in the repo. Without a resume the
   lineage is empty and nothing is omitted. Open-ended content dedupe stays rejected.
2. The manifest entry for such a file has no `uri`. It carries the same `sha256`,
   `size`, `kind`, `producer` and `name`, plus `supplied_by: <committed path>`.
3. `check_artifact_manifests.py` stays strict for ordinary entries. For a
   `supplied_by` entry it requires a canonical repo-relative path outside
   `manifests/artifacts/` that exists in the checked tree with the entry's sha256
   and size. A missing or mismatched pointer fails. Such an entry is not counted
   as stored bytes, so it cannot collide with its own pointer.
4. PR #411's 8 `lockdet-timing-watchdog.wdb_*` manifests are rewritten under the
   rule (13 entries converted, bytes already in the store, no new upload). The
   October records are untouched.

## Alternatives considered

- **Content-dedupe against any committed file.** Rejected: DR-014 reason.
- **Checker accepts a digest match when the entry declares `committed_at`.**
  Rejected: loosens the gate for every entry rather than verifying a pointer.
- **Drop the colliding entries by hand.** Rejected: same omission with no rule or
  pointer.

## Consequences

- The "bytes in exactly one place" invariant holds; the manifest names where.
- `klt artifact verify` / `get` do not know `supplied_by` entries (no `uri`). For
  those entries read the pointed-to committed file instead; a tool gap to raise
  generically with klayout-tools if verify rejects them.
- The reducer grade (phase MISS, watchdog PASS) is unchanged.

## Status notes

Stays `proposed` until the operator ratifies it on PR #411.
