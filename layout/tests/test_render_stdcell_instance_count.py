#!/usr/bin/env python3
"""The record's standard-cell instance count must be derived from the plan.

Issue #451: the device-set sentence stated the divider's instance count
twice -- once derived from `plan.json` (`_stdcell_device_count` for the
transistor half) and once as a typed-in `29` in the same sentence. They
agreed only while the netlist carried 29 divider instances; it now carries
42, and the record's own coverage row (`divider_intN: 29 -> 29` at mint
time) moves with the plan while the typed-in copy does not. Third instance
of the class in this file (#304's "four blocks", #443's `52`), so this
mirrors those tests' pair: behaviour, plus a source grep that keeps the
literal from coming back.

PDK- and `klt`-free.

    python3 -m unittest layout.tests.test_render_stdcell_instance_count -v
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
    "render_pll_record_scic", LAYOUT_BIN / "render-pll-record.py", register=False
)

#: The committed record whose sentence the fix must re-render byte-identically
#: (issue #451 AC 4): its plan's stdcell groups sum to 29 and its
#: `extract.pll_divider_intN.json` carries `device_count: 454`, so the
#: derived value equals the typed-in one *on this record* -- proving the fix
#: changes nothing for already-minted evidence while moving with the plan
#: for the next mint. `layout/pll/reports/` is append-only; this test only
#: reads it.
_COMMITTED_RECORD = REPO_ROOT / "layout/pll/reports/20260924-041509-c53e7c4"

#: A `"..."` / newline / `"..."` implicit-concatenation seam, as the renderer's
#: prose is written (same collapse as `test_render_derived_drc_count.py`).
#: Collapsing these is what lets the source grep below see a count and its
#: `schematic instances` subject as the adjacent tokens they render as, even
#: when the author split them across source lines.
_CONCAT_SEAM = re.compile(r"\"\s*\n\s*f?\"")

#: An integer literal standing immediately before `schematic instances` (the
#: rendered sentence) or `standard-cell instances` (the module docstring and
#: the `_check_stdcell` check label -- derived there, so both must stay
#: literal-free). A derived count renders from an f-string expression, so the
#: character before it is `}` (or the digits are part of an identifier) --
#: excluded here.
_TYPED_IN_COUNT = re.compile(
    r"(?<![\w.}])\d+\s+(?:schematic|standard-cell)\s+instances"
)


def _render(fn, *args) -> str:
    lines: list[str] = []
    fn(lines.append, *args)
    return "\n".join(lines)


def _stdcell_plan(
    *counts: int, name: str = "divider_intN", cell_name: str = "pll_divider_intN"
) -> dict:
    """A plan whose one stdcell block's groups sum to `sum(counts)`.

    `count > 1` groups are deliberate: the sentence follows
    `sum(group["count"])` -- the same expression `_check_coverage`'s `drawn`
    tally uses -- not `len(groups)` and not the block's `device_count`
    (those coincide only while every stdcell group has `count == 1`).
    Groups carry the committed plan's own `id` / `params.cell` shape.
    """
    groups = [
        {
            "kind": "stdcell",
            "id": f"g{i}",
            "params": {"cell": f"cell_{i}"},
            "count": n,
        }
        for i, n in enumerate(counts)
    ]
    block = {
        "name": name,
        "cell_name": cell_name,
        "device_count": len(groups),
        "group_count": len(groups),
        "size_um": [1, 1],
        "declared_nets": 0,
        "groups": groups,
    }
    return {"top_cell_name": "pll_top", "blocks": [block]}


class StdcellInstanceCount(unittest.TestCase):
    def test_count_is_sum_of_group_counts(self) -> None:
        self.assertEqual(render._stdcell_instance_count(_stdcell_plan(29)), 29)
        self.assertEqual(render._stdcell_instance_count(_stdcell_plan(20, 22)), 42)
        self.assertEqual(render._stdcell_instance_count(_stdcell_plan()), 0)

    def test_count_ignores_non_stdcell_groups_and_blocks(self) -> None:
        plan = _stdcell_plan(7)
        plan["blocks"][0]["groups"].append(
            {"kind": "mos_array", "params": {"l_um": 0.15}, "count": 99}
        )
        plan["blocks"].append(
            {
                "name": "vco",
                "cell_name": "c",
                "device_count": 26,
                "group_count": 1,
                "size_um": [1, 1],
                "declared_nets": 0,
                "groups": [{"kind": "mos_array", "params": {}, "count": 26}],
            }
        )
        self.assertEqual(render._stdcell_instance_count(plan), 7)

    def test_sentence_states_the_derived_count(self) -> None:
        """Across plans -- the mint-time 29, the current-netlist 42, and a
        multi-group sum (issue #451 AC 2)."""
        for counts in ((29,), (42,), (1, 2, 3)):
            expected = sum(counts)
            text = _render(
                render._render_device_set, [], Path("/nonexistent"), _stdcell_plan(*counts)
            )
            self.assertIn(f"rather than its {expected} schematic instances", text)
            for other in (0, 6, 29, 42):
                if other != expected:
                    self.assertNotIn(
                        f"rather than its {other} schematic instances", text
                    )

    def test_no_stdcell_block_renders_zero_not_a_crash(self) -> None:
        plan = {
            "top_cell_name": "pll_top",
            "blocks": [
                {
                    "name": "vco",
                    "cell_name": "c",
                    "device_count": 26,
                    "group_count": 1,
                    "size_um": [1, 1],
                    "declared_nets": 0,
                    "groups": [{"kind": "mos_array", "params": {}, "count": 26}],
                }
            ],
        }
        self.assertEqual(render._stdcell_instance_count(plan), 0)
        text = _render(render._render_device_set, [], Path("/nonexistent"), plan)
        self.assertIn("rather than its 0 schematic instances", text)

    def test_missing_extract_json_still_states_derived_instances(self) -> None:
        """A stdcell block with no `extract.<cell>.json` renders `0
        transistors` today; the instance half must still derive, not raise."""
        text = _render(
            render._render_device_set, [], Path("/nonexistent"), _stdcell_plan(29)
        )
        self.assertIn("0 transistors rather than its 29 schematic instances", text)

    def test_sentence_and_coverage_row_agree_in_one_record(self) -> None:
        """The two statements of the count must move together: the coverage
        row's `drawn` tally and the sentence's instance count are the same
        `sum(group["count"])` expression over the same plan (issue #451 AC 6,
        mirroring `test_render_derived_drc_count`'s DRC twin)."""
        for counts in ((29,), (20, 22), (41, 1)):
            plan = _stdcell_plan(*counts)
            expected = sum(counts)
            cards = {plan["blocks"][0]["name"]: [{}] * expected}
            _label, _ok, detail = render._check_coverage(plan, cards)
            sentence = _render(
                render._render_device_set, [], Path("/nonexistent"), plan
            )
            rows = re.findall(r"divider_intN: (\d+) -> (\d+)", detail)
            self.assertEqual(rows, [(str(expected), str(expected))])
            (stated,) = re.findall(r"(\d+) schematic instances", sentence)
            self.assertEqual(stated, rows[0][1])

    def test_committed_record_sentence_re_renders_byte_identically(self) -> None:
        """Driving `_render_device_set` over the committed record's own
        envelopes must reproduce its sentence unchanged: the plan derives the
        same 29 the typed-in literal held at mint time, and the extract JSON
        the same 454 (issue #451 AC 4)."""
        plan = render._load(_COMMITTED_RECORD / "plan.json")
        text = _render(render._render_device_set, [], _COMMITTED_RECORD, plan)
        committed = (_COMMITTED_RECORD / "record.md").read_text()
        sentence = next(
            line
            for line in committed.splitlines()
            if line.startswith("The standard-cell block extracts as")
        )
        self.assertIn("454 transistors rather than its 29 schematic instances", sentence)
        self.assertIn(sentence, text)

    def test_no_typed_in_instance_count_in_renderer_source(self) -> None:
        """Guard the `N schematic instances` shape (issue #451 AC 3).

        The fully-broad shape the issue considered -- any integer literal
        adjacent to a lowercase noun in this renderer's prose strings -- was
        measured (2026-11-15, over origin/main @ 96d72e0 with PR #444's
        seam-collapsing) to hit ~26 matches, overwhelmingly false positives:
        issue numbers (`17 bumped`, `1187 workaround`), ordinary code
        (`+= 1`, `1 else`), quoted deck excerpts (`2 vsubs`, `0 extracted`,
        `3 drawn`) and a dimension (`300 um`). A guard that fires on those
        gets silenced by the next author, so this stays phrase-specific --
        the third such grep in this suite, one per defect (#304 `blocks`,
        #443 `` `li1.space.1` ``, #451 `schematic instances`) -- while also
        covering `standard-cell instances`, the module docstring's own
        (since-removed) literal, which any broader shape would have flagged.
        """
        src = _CONCAT_SEAM.sub("", (LAYOUT_BIN / "render-pll-record.py").read_text())
        self.assertEqual(
            _TYPED_IN_COUNT.findall(src),
            [],
            "the standard-cell instance count must be derived from plan.json, "
            "not typed into the renderer's prose or docstring (issue #451)",
        )

    def test_guard_catches_a_re_introduced_literal(self) -> None:
        """Negative control: split across a concat seam, as the original
        defect could be re-introduced."""
        src = (
            'a("... rather than its "\n'
            '     "29 schematic instances -- ...")'
        )
        collapsed = _CONCAT_SEAM.sub("", src)
        self.assertEqual(_TYPED_IN_COUNT.findall(collapsed), ["29 schematic instances"])


if __name__ == "__main__":
    unittest.main()
