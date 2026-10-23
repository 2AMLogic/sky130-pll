# DR-013: the LOCK timing runner stores its group bytes in the artifact store

- **Status**: ratified (a change to evidence handling, authorized by issue #373;
  it touches no spec row and no ratified value)
- **Date**: 2026-10-23
- **Author**: Builder agent (issue #373)
- **Ratifies against / input to**: #373
- **Supersedes**: the one sentence in DR-012 § Consequences saying that
  `run_locktiming.py` "is not routed through the store by this record". DR-012
  itself is not edited and its decision stands.

## Context

DR-012 routed `run_corners.py` and `run_fmax.py` through
`sim/harness/evidence_store.py` and left `run_locktiming.py`
(`sim/harness/locktiming_cli.py`) as it was. That runner still copied each
group's `request.json`, `body.spice`, `report.json` and `stderr.log` into git,
once beside the group record and once more under `records/<record-id>/`. Of the
tracked files under `sim/lockdet-timing/` (131 at the time of writing) most are
those copies, so the repo kept growing from this runner and the evidence rule
had an unexplained exception. `signoff/` pins nothing under this tree
(`signoff/block-manifest.json` pins a DRC report and the characterization
report), so changing the layout touches no signoff pin. No spec row is involved.

## Decision

For a run minted after this record, each finished group's four files are
stored with `klt artifact put`. Git keeps, per group, a manifest
`manifests/artifacts/lockdet-timing-<group-record-stem>.manifest.json`, and the
small JSON group record (resume state), whose `job` gains `evidence_manifest`.
The combined record `records/lt-<stamp>.json` keeps every existing field; each
entry of its `jobs` carries the same `evidence_manifest`, so a reader finds the
bytes of every group from the record. No byte file is written under
`sim/lockdet-timing/**/records/` any more. The manifest is per group, not per
combined record, because bounded and resumed runs finish groups in different
invocations, before any combined record exists.

The runner fails closed as DR-012 does: it runs `evidence_store.preflight`
before submitting any job, and a failed or hash-mismatched put exits nonzero,
writes no group record, and leaves the staged bytes in the git-ignored
`sim/build/lockdet-timing/`. There is no fallback that commits the bytes.
`--dry-run` still needs no broker.

## Alternatives considered

- **One manifest per combined record.** Rejected: group records are written as
  each group finishes and a bounded run has no combined record, so a resumed
  group would have no manifest to cite.
- **Keep committing bytes.** Rejected for the reason in DR-012.
- **Rewrite or move the tracked history.** Rejected: records are append-only,
  and this runner's earlier records and their byte copies stay as written.

## Consequences

- Minting a record needs the broker (a fleet worker), as for the other
  runners. `--dry-run` and the PDK-free tests do not.
- Old records keep their `records/<record-id>/<group>/` byte trees; new ones
  have none. Both shapes of `jobs` entry load (`evidence_manifest` is optional).
- A zero-byte `stderr.log` is not stored (the store's minimum object is one
  byte); its content is known to be empty.
- Waveforms were never kept and still are not.

## Status notes

Ratified on merge of the PR for #373.
