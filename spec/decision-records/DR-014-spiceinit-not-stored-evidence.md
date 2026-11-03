# DR-014: the boilerplate `.spiceinit` is not stored as run evidence

- **Status**: ratified (operator ruling on issue #400, 2026-11-03, option (a);
  it touches no spec row and no ratified value)
- **Date**: 2026-11-03
- **Author**: Builder agent (issue #400)
- **Ratifies against / input to**: #400, PR #398
- **Supersedes**: N/A. It narrows what DR-012 stores for runs minted after this
  record; the manifest checker and earlier records are unchanged.

## Context

The harness drops an identical `.spiceinit` (1093 B, sha256 `0f498ef7…`) into
every run directory. 72 tracked `sim/*/corners/*/.spiceinit` files from before
DR-012 have the same bytes. `scripts/check_artifact_manifests.py` rejects any
manifest entry whose bytes equal a tracked file, so every manifest listing a
`.spiceinit` fails, as the two manifests from PR #398 did.

## Decision

`evidence_store.stage_files` never stages a file named `.spiceinit`. All four
callers (`cli.py`, `fmax_cli.py`, `locktiming_cli.py`,
`layout/bin/store_pll_evidence.py`) get this through the shared function. A
stored record therefore omits that file; it is harness boilerplate, not a
result.

## Alternatives considered

- **Dedupe any file content-identical to a committed file.** Rejected: record
  completeness would depend on repo state at run time, so manifests would stop
  being self-describing.
- **Exempt pre-DR-012 legacy paths in the checker.** Rejected: it loosens a
  verification gate and needs a maintained legacy-path list.

## Consequences

- The checker and the 72 legacy copies are untouched.
- PR #398 merged before the ruling, so its two records need no supersession;
  the next run under this rule is the first clean one.
- A `.spiceinit` that differs from the boilerplate is also omitted. The
  netlist snapshot and per-point netlists remain the evidence of what ran.

## Status notes

Ratified by the operator ruling on #400. The harness tests in
`sim/tests/test_evidence_store.py` pin the behaviour.
