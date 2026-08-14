# spec/

This directory holds the target specification (`target-spec.md`) and its
decision history (`decision-records/`).

A decision record is required whenever a spec value or approach in
`target-spec.md`'s summary table is set, changed, or scoped — not for
routine design/sim work that merely targets the existing spec. To write one:
copy `decision-records/TEMPLATE.md` to `decision-records/DR-NNN-<slug>.md`
(next unused `NNN`, one decision per record), fill it in, and commit it
alongside the spec change it justifies. Never edit a ratified record after
the fact — if a decision changes, supersede it with a new `DR-NNN` that says
so.

Agents never relax a ratified spec to make a `sim/` result pass: a result
that misses the spec is recorded as a miss in its own evidence record (see
`sim/README.md`), and the spec itself is changed only through a decision
record that argues the change on its own merits.

## Decision-record conventions

`decision-records/TEMPLATE.md` carries the section structure; these three
rules govern how records are numbered and amended, and they are the same
never-rewrite semantics `sim/README.md` applies to evidence records — a
decision and the evidence that exercises it should be traceable to each
other through stable IDs, never through an edited-in-place history.

- **Numbering is resolved at merge time, not at drafting time.** `NNN` is
  zero-padded to three digits and is the next unused number *when the record
  merges*. Two records racing for the same number is a real failure mode, so
  re-check `decision-records/` for the current highest `NNN` immediately
  before opening a PR and again after any rebase onto a moved `main`.
  Reviewers reject a PR that introduces a duplicate `NNN`.
- **`DR-NNN` is a permanent, stable ID.** Cite it from issues and from `sim/`
  evidence records exactly as `DR-NNN` (e.g. "see DR-003", "invalidated by
  DR-007") so the reference survives any later rewording of the record's
  title or slug.
- **Ratified records are append-only.** Do not delete or rewrite a ratified
  record, even to correct it. Write a new record instead, and mark the old
  one `superseded by DR-NNN` — the pointer runs forward from the old record
  to the new one, and the new record's Context says what it revises. A
  `proposed` record may still be edited freely until it is ratified.

## Provenance

Adapted from `2AMLogic/sky130-bandgap`'s `spec/README.md` (source commit
`7d1ce05168777f6615e1e26adf5eedd6213df318`), per this repo's `CLAUDE.md`
harness-bootstrap rule. `2AMLogic/gf180-pll` has no `spec/README.md` of its
own to copy — its `spec/` directory holds only `pll.md` and
`decision-records/` — so this file is seeded from sky130-bandgap instead,
noted here for anyone tracing where each piece of `spec/` came from.

The **Decision-record conventions** section above is adapted from
`2AMLogic/gf180-pll`'s `spec/decision-records/TEMPLATE.md` (source commit
`267180ec620f082d1b8dfdd772f3830d989ff358`), which carries those rules in
its own header comment. They live here rather than in this repo's
`decision-records/TEMPLATE.md` because that template already exists — it
landed with `DR-001` — and rewriting a template another change deliberately
authored would be the wrong way to import a convention. Issue #2's
"copy the template from gf180-pll" instruction is therefore satisfied by
importing gf180-pll's *rules* into a file that had no owner yet, and leaving
the template itself alone.
