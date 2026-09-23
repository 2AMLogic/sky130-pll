#!/usr/bin/env python3
"""Unit tests for `layout/bin/render_common.spec_rows_line`.

A layout block declares which `spec/target-spec.md` row(s) its records
measure in `layout/<block>/spec-rows.json` -- the layout-tree counterpart of
a `sim/<slug>/testbench/tb.json` manifest's `spec_rows` key. The block
directory is mutable; the records under `reports/<record-id>/` are
append-only evidence, so this is where the declaration can live and still be
stamped into every record the flow mints (issue #152).

No `klt`, no PDK, no venv required.

    python3 -m unittest discover -s layout/tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
if str(BIN_DIR) not in sys.path:
    sys.path.insert(0, str(BIN_DIR))

LAYOUT_DIR = Path(__file__).resolve().parents[1]

import render_common  # noqa: E402


class SpecRowsLineTests(unittest.TestCase):
    def _block(self, tmp: str, decl) -> Path:
        """Build a `<block>/reports/<record-id>/` tree and return the out_dir."""
        block = Path(tmp) / "some-block"
        out_dir = block / "reports" / "20260101-000000-abc1234"
        out_dir.mkdir(parents=True)
        if decl is not None:
            (block / "spec-rows.json").write_text(json.dumps(decl))
        return out_dir

    def test_missing_declaration_is_an_error_not_a_silent_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = self._block(tmp, None)
            with self.assertRaises(render_common.SpecRowsError) as ctx:
                render_common.spec_rows_line(out_dir)
            self.assertIn("spec-rows.json", str(ctx.exception))

    def test_rows_lead_the_line_so_the_aggregator_can_read_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = self._block(tmp, {"spec_rows": [18], "spec_rows_note": "area"})
            self.assertEqual(render_common.spec_rows_line(out_dir), "18 -- area")

    def test_explicit_none_needs_a_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = self._block(tmp, {"spec_rows": []})
            with self.assertRaises(render_common.SpecRowsError):
                render_common.spec_rows_line(out_dir)

    def test_explicit_none_with_a_note_renders_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = self._block(tmp, {"spec_rows": [], "spec_rows_note": "plumbing"})
            self.assertEqual(render_common.spec_rows_line(out_dir), "none -- plumbing")

    def test_non_row_number_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = self._block(tmp, {"spec_rows": ["eighteen"]})
            with self.assertRaises(render_common.SpecRowsError):
                render_common.spec_rows_line(out_dir)

    def test_every_checked_in_layout_block_declares_spec_rows(self):
        blocks = sorted(p.parent for p in LAYOUT_DIR.glob("*/reports"))
        self.assertTrue(blocks, "no layout block with a reports/ tree was found")
        for block in blocks:
            with self.subTest(block=block.name):
                out_dir = block / "reports" / "20260101-000000-abc1234"
                # spec_rows_line() only reads <block>/spec-rows.json; out_dir
                # needs to name the right block, not to exist.
                render_common.spec_rows_line(out_dir)  # raises if undeclared


if __name__ == "__main__":
    unittest.main()
