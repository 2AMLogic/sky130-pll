# DR-015: pinned boilerplate files are not stored as run evidence

- **Status**: proposed (an operator ratifies it; agents do not self-ratify)
- **Date**: 2026-11-06
- **Author**: Builder agent (issue #414)
- **Ratifies against / input to**: #414, PR #412
- **Supersedes**: N/A. It extends DR-014 with a narrower, content-pinned rule.

## Context

`scripts/check_artifact_manifests.py` rejects any manifest entry whose bytes
equal a tracked blob. The layout flow's `route-spot-check/lvs.request.json`
(sha256 `2a9e80c7cc57a8ffe78770839ebd37f9ca630947758b8ff8d04eb8143d54f7ad`,
306 B) is already tracked in older records, so the manifest added by PR #412
fails `check:ci`. The file is a templated heredoc, so other top cells or decks
produce different bytes (for example `d9ee37ba...`), which are real evidence.

## Decision

`evidence_store.stage_files` also drops a file when both its basename and its
sha256 match an entry of `PINNED_BOILERPLATE` (initially `lvs.request.json` with
the sha256 above). `.spiceinit` handling under DR-014 is unchanged. A record
minted under this rule says in its "Stored evidence" section that pinned
boilerplate is omitted by rule. Proposed until an operator ratifies it.

## Alternatives considered

- **Dedupe any file content-identical to a committed file.** Rejected: DR-014
  already rejected it, since record completeness would depend on repo state.
- **Drop `lvs.request.json` by name.** Rejected: it would lose variants whose
  bytes differ, which are evidence.
- **Exempt legacy paths in the checker.** Rejected: loosens a gate (DR-014).

## Consequences

- Completeness stays independent of repo state: the rule depends only on the
  file's own name and bytes.
- Adding a pin needs a new decision record.
- The existing record and manifest for `20261106-053933-0772a9d` are
  append-only and untouched. A fresh buffered-top record naming it as
  superseded needs the layout flow and is a follow-up outside this change.

## Status notes

Stays `proposed` until the operator ratifies it on the PR or on #414.
