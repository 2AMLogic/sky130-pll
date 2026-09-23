#!/usr/bin/env python3
"""Repo-wide guard: every evidence record resolves to a spec-row citation.

Issue #152. `measurements/aggregate.py` rolls `sim/`/`layout/` evidence up
against `spec/target-spec.md` by matching a `**Spec row(s)**:` line, and for
a long time that convention was documented but adopted by nothing -- so the
rollup was structurally empty regardless of how much real evidence landed. A
convention that depends on an author remembering it decays exactly that way,
so it is checked here rather than merely written down.

What this asserts, over the real checked-in tree:

1. Every `sim/<slug>/testbench/tb.json` declares `spec_rows` (and, when it is
   empty, a `spec_rows_note` arguing why the experiment measures no row).
2. Every `layout/<block>/` with a `reports/` tree declares the same in
   `spec-rows.json`.
3. Every declared row number is a real row of `spec/target-spec.md` -- a typo
   citing row 99 must not quietly vanish from the report.
4. No manifest hand-writes a `**Spec row(s)**:` line into its prose fields,
   where it would precede (and therefore shadow) the bullet the renderer
   emits from the declaration.
5. No **current** (non-superseded) evidence record is left with no spec-row
   declaration at all, from either source.

It deliberately does *not* require a record to cite a *non-empty* row set:
harness plumbing and negative controls measure no spec row, and saying so
explicitly is the correct outcome for them. Nor does it require a record
minted before the convention to have been edited to add the line --
`sim/README.md`'s append-only rule forbids editing a record at all, so those
resolve via their experiment's own (mutable) declaration instead.

No PDK, ngspice, xschem, or klt required.

    python3 -m unittest discover -s measurements/tests -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

MEASUREMENTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MEASUREMENTS_DIR))

import aggregate  # noqa: E402

REPO_ROOT = MEASUREMENTS_DIR.parent


def _declaration(path: Path) -> dict:
    return json.loads(path.read_text())


def _assert_valid(test: unittest.TestCase, decl: dict, where: str) -> list[int]:
    rows = decl.get("spec_rows")
    test.assertIsInstance(
        rows,
        list,
        f"{where}: no `spec_rows` list -- state which spec/target-spec.md "
        "row(s) this measures, or declare [] with a `spec_rows_note` saying "
        "why it measures none",
    )
    for entry in rows:
        test.assertIsInstance(entry, int, f"{where}: `spec_rows` entry {entry!r}")
        test.assertNotIsInstance(entry, bool, f"{where}: `spec_rows` entry {entry!r}")
        test.assertGreaterEqual(entry, 0, f"{where}: `spec_rows` entry {entry!r}")
    if not rows:
        note = str(decl.get("spec_rows_note", "") or "").strip()
        test.assertTrue(
            note,
            f"{where}: `\"spec_rows\": []` is an explicit 'measures no spec "
            "row' claim and needs a `spec_rows_note` arguing it",
        )
    return rows


class DeclarationTests(unittest.TestCase):
    def test_every_sim_experiment_declares_spec_rows(self):
        manifests = sorted(REPO_ROOT.glob("sim/*/testbench/tb.json"))
        self.assertTrue(manifests, "no sim experiment manifests found")
        for path in manifests:
            with self.subTest(manifest=path.relative_to(REPO_ROOT).as_posix()):
                _assert_valid(
                    self,
                    _declaration(path),
                    path.relative_to(REPO_ROOT).as_posix(),
                )

    def test_no_manifest_hand_writes_the_citation_into_its_prose(self):
        # The divider manifests originally carried "**Spec row(s)**: 4 ..."
        # inside their `claim` sentence. Once the renderer stamps the line
        # from `spec_rows`, a surviving prose copy is worse than redundant:
        # it precedes the real bullet in the rendered record, so the
        # aggregator reads the prose and a later change to `spec_rows` would
        # silently not take effect (issue #152).
        for path in sorted(REPO_ROOT.glob("sim/*/testbench/tb.json")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            with self.subTest(manifest=rel):
                decl = _declaration(path)
                for field in ("claim", "methodology_note", "analysis"):
                    self.assertNotIn(
                        "**Spec row(s)**",
                        str(decl.get(field, "")),
                        f"{rel}: `{field}` hand-writes the citation the "
                        "renderer already emits from `spec_rows` -- delete the "
                        "prose copy, it shadows the declaration",
                    )

    def test_every_layout_block_declares_spec_rows(self):
        blocks = sorted(p.parent for p in REPO_ROOT.glob("layout/*/reports"))
        self.assertTrue(blocks, "no layout blocks with a reports/ tree found")
        for block in blocks:
            rel = (block / "spec-rows.json").relative_to(REPO_ROOT).as_posix()
            with self.subTest(block=block.name):
                self.assertTrue(
                    (block / "spec-rows.json").is_file(),
                    f"{rel} does not exist -- every layout block must declare "
                    "which spec/target-spec.md row(s) its records measure",
                )
                _assert_valid(self, _declaration(block / "spec-rows.json"), rel)

    def test_every_declared_row_number_exists_in_the_spec(self):
        known = {
            row.number
            for row in aggregate.parse_spec_rows(REPO_ROOT / "spec" / "target-spec.md")
        }
        self.assertTrue(known, "spec/target-spec.md summary table parsed as empty")
        declarations = [
            (p, _declaration(p)) for p in sorted(REPO_ROOT.glob("sim/*/testbench/tb.json"))
        ] + [
            (p, _declaration(p)) for p in sorted(REPO_ROOT.glob("layout/*/spec-rows.json"))
        ]
        for path, decl in declarations:
            rel = path.relative_to(REPO_ROOT).as_posix()
            for row in decl.get("spec_rows") or []:
                with self.subTest(declaration=rel, row=row):
                    self.assertIn(
                        row,
                        known,
                        f"{rel} cites spec/target-spec.md row {row}, which that "
                        "file has no such row for",
                    )


class ResolvedCitationTests(unittest.TestCase):
    """The end-to-end property: nothing current is left uncited."""

    def _report(self):
        spec_rows = aggregate.parse_spec_rows(REPO_ROOT / "spec" / "target-spec.md")
        records = aggregate.discover_evidence(REPO_ROOT)
        return aggregate.build_report(spec_rows, records, repo_root=REPO_ROOT)

    def test_no_current_record_is_left_without_a_declaration(self):
        data = self._report()
        offenders = [
            rec.path.as_posix()
            for rec in aggregate._all_current(data)
            if rec.spec_rows_source
            in (aggregate.SOURCE_UNDECLARED, aggregate.SOURCE_MALFORMED)
        ]
        self.assertEqual(
            offenders,
            [],
            "these current evidence records resolve to no spec-row citation -- "
            "declare `spec_rows` in the owning sim/<slug>/testbench/tb.json or "
            "layout/<block>/spec-rows.json (records themselves are append-only "
            "and must not be edited)",
        )

    def test_the_rollup_is_not_structurally_empty(self):
        # The regression issue #152 exists to close: the aggregator working
        # while zero evidence feeds it. If this ever fails, real evidence has
        # stopped reaching the report.
        data = self._report()
        populated = [n for n, recs in data.rows.items() if recs]
        self.assertTrue(
            populated,
            "no spec row has any evidence mapped to it -- the characterization "
            "report is structurally empty again (issue #152)",
        )


if __name__ == "__main__":
    unittest.main()
