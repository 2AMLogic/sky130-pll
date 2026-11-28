#!/usr/bin/env python3
"""The reader pointers must name the newest PLL layout record.

Issue #304: `layout/pll/reports/LATEST` is deliberately pinned to a pre-buffer
record (the newest PASS record's raw evidence lives in the artifact store,
DR-012, and the signoff superseded-record guard requires `LATEST` to name the
record `signoff/run-signoff.sh` item 3 cites — a clean CI checkout cannot
verify a manifest-only record yet, 2AMLogic/klayout-tools#5591; the re-point is
tracked by issue #459). Because the pointer is held back on purpose, the
READMEs carry an explicit "newest record" note naming the buffered-top record
so a reader following the `LATEST` sentence cannot come away believing the
design still has four blocks.

This test fails if that note is missing or silently goes stale — i.e. names
anything other than the newest record directory under `layout/pll/reports/` —
the same way `test_trivial_cell_references.py` checks README references
against the tree.

    python3 -m unittest layout.tests.test_newest_record_reference -v
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parents[1]
PLL_DIR = LAYOUT_DIR / "pll"
REPORTS_DIR = PLL_DIR / "reports"

#: A record id's sha leg is whatever `git rev-parse --short HEAD` printed at
#: mint time; git picks that length adaptively (7 hex chars for most of this
#: repo's history, 8 once the object count grew), so 7-or-more, never a
#: fixed 7.
RECORD_ID_RE = re.compile(r"\d{8}-\d{6}-[0-9a-f]{7,}")
NOTE_ANCHOR = "**Newest record**"


def newest_record_id() -> str:
    record_dirs = sorted(
        p.name
        for p in REPORTS_DIR.iterdir()
        if p.is_dir() and RECORD_ID_RE.fullmatch(p.name)
    )
    assert record_dirs, f"no record directories under {REPORTS_DIR}"
    return record_dirs[-1]


def note_record_id(readme: Path) -> str:
    """Return the record id the "newest record" note names.

    The note starts at the `**Newest record**` anchor and runs to the next
    blank line; its first record id is the one a reader is pointed at.
    """
    text = readme.read_text()
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if NOTE_ANCHOR in line]
    assert len(starts) == 1, (
        f"expected exactly one '{NOTE_ANCHOR}' note in {readme}, "
        f"found {len(starts)}"
    )
    block = "\n".join(lines[starts[0]:])
    block = block.split("\n\n", 1)[0]
    ids = RECORD_ID_RE.findall(block)
    assert ids, f"'{NOTE_ANCHOR}' note in {readme} names no record id"
    return ids[0]


class NewestRecordReferenceTests(unittest.TestCase):
    def test_newest_record_is_the_lever_measurement_pass_record(self):
        # Guard the fixture itself: the newest record directory must be the
        # PASS routing-lever measurement record this note exists to surface
        # (issue #548). If a newer record lands, this note (and the pointer
        # checks below) must be updated in the same change.
        self.assertEqual(newest_record_id(), "20261121-015858-147252b9")

    def test_pll_readme_note_names_newest_record(self):
        self.assertEqual(
            note_record_id(PLL_DIR / "README.md"), newest_record_id()
        )

    def test_layout_readme_carries_same_pointer(self):
        self.assertEqual(
            note_record_id(LAYOUT_DIR / "README.md"), newest_record_id()
        )

    def test_pll_readme_note_states_why_it_is_not_latest(self):
        block_lines = (PLL_DIR / "README.md").read_text().splitlines()
        start = next(
            i for i, line in enumerate(block_lines) if NOTE_ANCHOR in line
        )
        block = "\n".join(block_lines[start:]).split("\n\n", 1)[0]
        self.assertIn("LATEST", block)
        self.assertIn("artifact store", block)
        self.assertIn("klayout-tools#5591", block)
        self.assertIn("#459", block)


if __name__ == "__main__":
    unittest.main()
