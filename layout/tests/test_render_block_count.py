#!/usr/bin/env python3
"""The PLL record prose must state the plan's block count, not a typed-in one.

Issue #304: the renderer hard-coded "four blocks" after `clk_buf` made it five.
PDK- and `klt`-free.

    python3 -m unittest layout.tests.test_render_block_count -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.test_support import load_module  # noqa: E402

LAYOUT_BIN = Path(__file__).resolve().parents[1] / "bin"
render = load_module("render_pll_record_bc", LAYOUT_BIN / "render-pll-record.py", register=False)

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def _render(fn, *args) -> str:
    lines: list[str] = []
    fn(lines.append, *args)
    return "\n".join(lines)


def _blocks(n: int) -> list[dict]:
    return [
        {"name": f"b{i}", "cell_name": f"c{i}", "device_count": 1, "group_count": 1,
         "size_um": [1, 1], "declared_nets": 2}
        for i in range(n)
    ]


class BlockCountProse(unittest.TestCase):
    def test_prose_follows_block_count(self) -> None:
        for n in (4, 5, 6):
            plan = {"top_cell_name": "pll_top", "blocks": _blocks(n)}
            build = {"blocks": _blocks(n), "top": {"cell_name": "t", "size_um": [1, 1]}}
            is_text = _render(render._render_layout_is, plan, build, Path("/nonexistent"))
            not_text = _render(render._render_layout_is_not, build, {"status": "clean"})
            for text in (is_text, not_text):
                self.assertIn(f"the {WORDS[n]} blocks", text)
                for other in (4, 5, 6):
                    if other != n:
                        self.assertNotIn(f"the {WORDS[other]} blocks", text)

    def test_no_hardcoded_block_count_in_renderer_source(self) -> None:
        src = (LAYOUT_BIN / "render-pll-record.py").read_text()
        self.assertNotIn("the four blocks", src)


if __name__ == "__main__":
    unittest.main()
