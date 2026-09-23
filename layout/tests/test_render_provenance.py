#!/usr/bin/env python3
"""Pin the `## Provenance` section both layout-record renderers emit.

`render-record.py` (trivial-cell flow) and `render-pll-record.py` (PLL layout
flow) both render provenance through `render_common.render_provenance`. The
PLL flow passes `netlist_display`, which adds a `Schematic netlist:` line; the
trivial-cell flow does not. These tests load each script by path (a hyphenated
filename is not an importable module name -- same pattern as
`test_record_dirty_flag.py`) and assert the exact rendered section, so a
change to the shared function that breaks either call site fails here without
needing `klt` or a PDK install.

    python3 -m unittest discover -s layout/tests -v
"""

from __future__ import annotations

import argparse
import importlib.util
import unittest
from pathlib import Path

LAYOUT_BIN = Path(__file__).resolve().parents[1] / "bin"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, LAYOUT_BIN / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render_record = _load("render_record", "render-record.py")
render_pll_record = _load("render_pll_record", "render-pll-record.py")

ARGS = argparse.Namespace(record_id="20260101-000000-abc1234")
KLT_VERSION = "klt 1.2.3"
PDK_INFO = {"variant": "sky130A", "version": "0123456789abcdef"}
DRC = {"provenance": {"klayout_version": "0.29.0"}}
NETLIST = "design/top/netlist/top.spice"

PIN_CROSS_CHECK = (
    "- PDK pin cross-check: compare `version` above against "
    "`sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself "
    "enforce the pin, so a mismatch is a manual reproducibility note."
)


def _expected(*, netlist: str | None, dirty: bool) -> list[str]:
    lines = [
        "## Provenance",
        "",
        "- Record ID: `20260101-000000-abc1234`",
    ]
    if netlist is not None:
        lines.append(f"- Schematic netlist: `{netlist}`")
    lines += [
        "- `klt` version: `klt 1.2.3` (see `layout/requirements.txt`)",
        "- KLayout engine version: `0.29.0`",
        "- PDK: `sky130A`, `0123456789abcdef`",
        PIN_CROSS_CHECK,
        "- Repo state: `deadbeef` on `main`" + (" (dirty)" if dirty else ""),
        "",
    ]
    return lines


def _render(module, dirty: bool, **kwargs) -> list[str]:
    lines: list[str] = []
    module.render_provenance(
        lines.append, ARGS, KLT_VERSION, PDK_INFO, DRC, "deadbeef", "main", dirty, **kwargs
    )
    return lines


class RenderProvenanceTests(unittest.TestCase):
    def test_both_renderers_use_the_shared_function(self):
        # Guards against a local copy being reintroduced in either script.
        import render_common

        self.assertIs(render_record.render_provenance, render_common.render_provenance)
        self.assertIs(render_pll_record.render_provenance, render_common.render_provenance)
        self.assertFalse(hasattr(render_record, "_render_provenance"))
        self.assertFalse(hasattr(render_pll_record, "_render_provenance"))

    def test_trivial_cell_record_has_no_schematic_netlist_line(self):
        for dirty in (False, True):
            with self.subTest(dirty=dirty):
                self.assertEqual(
                    _render(render_record, dirty), _expected(netlist=None, dirty=dirty)
                )

    def test_pll_record_includes_schematic_netlist_line(self):
        for dirty in (False, True):
            with self.subTest(dirty=dirty):
                self.assertEqual(
                    _render(render_pll_record, dirty, netlist_display=NETLIST),
                    _expected(netlist=NETLIST, dirty=dirty),
                )

    def test_missing_klayout_version_renders_none_rather_than_raising(self):
        lines: list[str] = []
        render_pll_record.render_provenance(
            lines.append, ARGS, KLT_VERSION, PDK_INFO, {}, "deadbeef", "main", False,
            netlist_display=NETLIST,
        )
        self.assertIn("- KLayout engine version: `None`", lines)


if __name__ == "__main__":
    unittest.main()
