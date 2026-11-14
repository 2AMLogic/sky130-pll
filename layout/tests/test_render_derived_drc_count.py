#!/usr/bin/env python3
"""The record's `li1.space.1` count must be derived from the plan, not typed in.

Issue #443: the renderer stated the same historical count twice per record --
once derived from `plan.json` by `_check_drc`, once as a typed-in `52` in the
"What this layout is not" DRC-clean bullet. They agreed only by coincidence,
and the next block drawn at the 1.8 V core minimum gate length would have made
the typed-in copy wrong while the derived one moved. Same defect class as
issue #304's hard-coded "four blocks", in the same file, so this mirrors
`test_render_block_count.py`'s pair: behaviour, plus a source grep that keeps
the literal from coming back.

PDK- and `klt`-free.

    python3 -m unittest layout.tests.test_render_derived_drc_count -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.test_support import load_module  # noqa: E402

LAYOUT_BIN = Path(__file__).resolve().parents[1] / "bin"
render = load_module(
    "render_pll_record_drc", LAYOUT_BIN / "render-pll-record.py", register=False
)

#: A `"..."` / newline / `"..."` implicit-concatenation seam, as the renderer's
#: prose is written. Collapsing these is what lets the source grep below see a
#: count and its `li1.space.1` subject as the adjacent tokens they render as,
#: even when the author split them across source lines.
_CONCAT_SEAM = re.compile(r"\"\s*\n\s*f?\"")

#: An integer literal standing immediately before the rule name in collapsed
#: prose. A derived count renders from an f-string expression, so the character
#: before it is `}` (or the digits are part of an identifier) -- excluded here.
_TYPED_IN_COUNT = re.compile(r"(?<![\w.}])\d+\s+`li1\.space\.1`")


def _render(fn, *args) -> str:
    lines: list[str] = []
    fn(lines.append, *args)
    return "\n".join(lines)


def _plan(min_length_counts: tuple[int, ...]) -> dict:
    """A plan whose `mos_array` groups sum to `sum(min_length_counts)` devices
    below the deck's minimum li1 spacing, plus decoys that must not be counted.
    """
    groups = [
        {"kind": "mos_array", "params": {"l_um": 0.15}, "count": n}
        for n in min_length_counts
    ]
    groups += [
        # At/above the spacing: never fired the rule.
        {"kind": "mos_array", "params": {"l_um": 0.5}, "count": 99},
        # Not a MOS array at all.
        {"kind": "std_cell_row", "params": {"l_um": 0.15}, "count": 77},
    ]
    return {"top_cell_name": "pll_top", "blocks": [{"name": "b0", "groups": groups}]}


def _build() -> dict:
    blocks = [
        {
            "name": "b0",
            "cell_name": "c0",
            "device_count": 1,
            "group_count": 1,
            "size_um": [1, 1],
            "declared_nets": 2,
        }
    ]
    return {"blocks": blocks, "top": {"cell_name": "t", "size_um": [1, 1]}}


class DerivedCount(unittest.TestCase):
    def test_counts_only_sub_spacing_mos_devices(self) -> None:
        self.assertEqual(render._min_length_device_count(_plan((6, 6, 1))), 13)
        self.assertEqual(render._min_length_device_count(_plan(())), 0)

    def test_drc_clean_bullet_states_the_derived_count(self) -> None:
        for counts in ((6, 6, 1), (52,), (6, 1, 6, 1)):
            expected = sum(counts)
            text = _render(
                render._render_layout_is_not,
                _plan(counts),
                _build(),
                {"status": "clean"},
            )
            self.assertIn(f"{expected} `li1.space.1` violations", text)

    def test_drc_check_and_bullet_agree_in_one_record(self) -> None:
        """The two statements of the count must move together (issue #443)."""
        for counts in ((6, 6, 1), (52,), (31,)):
            plan = _plan(counts)
            drc = {"status": "clean", "violation_count": 0, "rule_counts": {}}
            check_label, _ok, _detail = render._check_drc(plan, drc)
            bullet = _render(render._render_layout_is_not, plan, _build(), drc)
            subject = "`li1.space.1` violations"
            self.assertIn(subject, check_label)
            self.assertIn(subject, bullet)
            self.assertEqual(
                re.findall(r"(\d+) " + re.escape(subject), check_label),
                re.findall(r"(\d+) " + re.escape(subject), bullet),
            )

    def test_no_typed_in_li1_count_in_renderer_source(self) -> None:
        src = _CONCAT_SEAM.sub("", (LAYOUT_BIN / "render-pll-record.py").read_text())
        self.assertEqual(
            _TYPED_IN_COUNT.findall(src),
            [],
            "the `li1.space.1` count must be derived from plan.json, not typed "
            "into the renderer's prose (issue #443)",
        )


if __name__ == "__main__":
    unittest.main()
