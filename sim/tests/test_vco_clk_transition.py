#!/usr/bin/env python3
"""Unit tests for `sim/vco-clk-transition/analysis/bracket_floor.py` (issue #186).

No PDK, ngspice or xschem required. `bracket_floor.py` never simulates -- it
reads `sim/vco-clk-transition`'s own committed record (design/vco's real
`CLK` transition time) and `sim/jitter-floor`'s committed family, and states
which member of that family applies. These tests check:

1. The committed derived document (`analysis/bracket.md`) still matches what
   the committed records re-derive -- the drift check `sim/README.md`
   requires of an `analysis/` directory.
2. The bracket the script draws from the real committed evidence is the one
   this repo's evidence trail actually supports (design's own edge/step
   ratio strictly between the A3 and B variants, in that unresolved-edge
   regime, not the fully-resolved C variant).
3. The refusals -- a missing A3/B/C triple, a non-monotonic triple, and this
   campaign's own dump grid failing to resolve its own measured edge -- are
   asserted from synthetic fixtures, not assumed.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = REPO_ROOT / "sim" / "vco-clk-transition"
FLOOR_EXPERIMENT = REPO_ROOT / "sim" / "jitter-floor"
ANALYSIS_PATH = EXPERIMENT / "analysis" / "bracket_floor.py"
DOCUMENT = EXPERIMENT / "analysis" / "bracket.md"


def _load(name: str, path: Path):
    """Neither directory is an importable package (hyphens in the slug), so
    the module is loaded from its path -- the same pattern
    `sim/tests/test_jitter_calibration.py` uses."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


bf = _load("bracket_floor", ANALYSIS_PATH)


TRANSITION_RECORD_TEMPLATE = """# Record {record_id}

- **Record ID**: {record_id}
- **Result**:

  | Corner | Temp (C) | Supply (V) | Verdict | f_out | Duty | Transition (rise/fall) | Detail |
  |---|---|---|---|---|---|---|---|
  | tt | 125 | 1.80 | PASS | 259.6 MHz | 50.4% | {rise} ps / {fall} ps | f_out 259.6 MHz, \
duty 50.4%, 10-90% transition time: rise {rise} ps (n={n_rise}), fall {fall} ps (n={n_fall}) |
"""

TRANSITION_NETLIST_TEMPLATE = """** synthetic per-point netlist
.control
tran {step} 200n uic
.endc
.end
"""

FLOOR_RECORD_TEMPLATE = """# Record {record_id}

- **Record ID**: {record_id}
- **Methodology / criteria / limitations**:
  - DUT / limitations: THIS RECORD'S VARIANT: {variant} -- synthetic fixture.
- **Result**:

  | Corner | Temp (C) | Supply (V) | Verdict | f_out | Duty | Detail |
  |---|---|---|---|---|---|---|
  | tt | 27 | 1.80 | PASS | 255.3 MHz | 50.0% | f_out 255.3 MHz, duty 50.0%, \
period jitter {pct}% RMS over 12764 cycles |
"""

FLOOR_NETLIST_TEMPLATE = """** synthetic per-point netlist
VCLK CLK GND pulse(0 1.8 0 {edge} {edge} 1.9585n {period})
.control
tran {step} 50u
.endc
.end
"""


def write_transition_record(
    experiment: Path, *, record_id: str, rise_ps: float, fall_ps: float,
    step: str = "5p", n_rise: int = 37, n_fall: int = 36,
) -> None:
    (experiment / "records").mkdir(parents=True, exist_ok=True)
    (experiment / "corners" / record_id).mkdir(parents=True, exist_ok=True)
    (experiment / "records" / f"{record_id}.md").write_text(
        TRANSITION_RECORD_TEMPLATE.format(
            record_id=record_id, rise=rise_ps, fall=fall_ps,
            n_rise=n_rise, n_fall=n_fall,
        )
    )
    (experiment / "corners" / record_id / "tt_125c_1.80v.spice").write_text(
        TRANSITION_NETLIST_TEMPLATE.format(step=step)
    )


def write_floor_record(
    experiment: Path, *, record_id: str, variant: str, pct: float,
    period: str = "3.9170n", edge: str = "20p", step: str = "200p",
) -> None:
    (experiment / "records").mkdir(parents=True, exist_ok=True)
    (experiment / "corners" / record_id).mkdir(parents=True, exist_ok=True)
    (experiment / "records" / f"{record_id}.md").write_text(
        FLOOR_RECORD_TEMPLATE.format(record_id=record_id, variant=variant, pct=pct)
    )
    (experiment / "corners" / record_id / "tt_27c_1.80v.spice").write_text(
        FLOOR_NETLIST_TEMPLATE.format(period=period, edge=edge, step=step)
    )


def write_default_triple(experiment: Path) -> None:
    """The A3/B/C triple this script's bracket needs, at the real committed
    figures (`sim/jitter-floor/records/`'s own A3/B/C)."""
    write_floor_record(
        experiment, record_id="20260101-000000-aaaaaaa", variant="A3",
        pct=2.371, edge="20p",
    )
    write_floor_record(
        experiment, record_id="20260101-000001-aaaaaaa", variant="B",
        pct=0.610, edge="200p",
    )
    write_floor_record(
        experiment, record_id="20260101-000002-aaaaaaa", variant="C",
        pct=0.000, edge="1n",
    )


class CommittedEvidenceTests(unittest.TestCase):
    """The real committed evidence, read through the script itself."""

    def test_the_committed_document_matches_the_committed_records(self):
        self.assertTrue(DOCUMENT.is_file(), f"{DOCUMENT} is missing")
        self.assertEqual(bf.main(["--check"]), 0)

    def test_the_real_record_measures_an_unresolved_edge(self):
        transition = bf.parse_transition_record(EXPERIMENT)
        floors = bf.parse_floor_records(FLOOR_EXPERIMENT)
        step_s = floors[0]["step_s"]
        self.assertLess(transition["rise_s"], step_s)
        self.assertLess(transition["fall_s"], step_s)

    def test_the_real_bracket_sits_strictly_between_a3_and_b(self):
        transition = bf.parse_transition_record(EXPERIMENT)
        floors = bf.parse_floor_records(FLOOR_EXPERIMENT)
        d = bf.bracket(transition, floors)
        self.assertEqual(d["bracket_lo"]["variant"], "A3")
        self.assertEqual(d["bracket_hi"]["variant"], "B")
        self.assertLess(d["floor_lo"], d["floor_hi"])
        # The bracket variant's own floors, read straight off the record
        # text rather than hardcoded, so a re-run of sim/jitter-floor that
        # changes those figures fails this test instead of silently
        # invalidating the printed conclusion.
        self.assertAlmostEqual(d["floor_hi"], 0.02371, places=5)
        self.assertAlmostEqual(d["floor_lo"], 0.00610, places=5)

    def test_own_dump_grid_resolves_its_own_measured_edge(self):
        """The precondition `main()` enforces before trusting the ratio at
        all: this campaign's OWN 5 ps grid must resolve its measured ~53-62
        ps edge (tran_step <= transition_time / 2)."""
        transition = bf.parse_transition_record(EXPERIMENT)
        shortest = min(transition["rise_s"], transition["fall_s"])
        self.assertLessEqual(transition["own_step_s"], 0.5 * shortest)


class BracketArithmeticTests(unittest.TestCase):
    """The bracket logic, from synthetic fixtures with known-by-construction
    numbers -- checked independently of whatever the real record measures."""

    def test_a_ratio_between_a3_and_b_is_bracketed_by_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            transition_exp = Path(tmp) / "vco-clk-transition"
            floor_exp = Path(tmp) / "jitter-floor"
            # Edge/step ratio 0.3 -- strictly between A3's 0.1 and B's 1.0.
            write_transition_record(
                transition_exp, record_id="20260101-000000-aaaaaaa",
                rise_ps=60.0, fall_ps=60.0,
            )
            write_default_triple(floor_exp)

            transition = bf.parse_transition_record(transition_exp)
            floors = bf.parse_floor_records(floor_exp)
            d = bf.bracket(transition, floors)
            self.assertEqual(d["bracket_lo"]["variant"], "A3")
            self.assertEqual(d["bracket_hi"]["variant"], "B")
            self.assertAlmostEqual(d["floor_hi"], 0.02371)
            self.assertAlmostEqual(d["floor_lo"], 0.00610)

    def test_a_ratio_between_b_and_c_is_bracketed_by_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            transition_exp = Path(tmp) / "vco-clk-transition"
            floor_exp = Path(tmp) / "jitter-floor"
            # Edge/step ratio 2.0 -- strictly between B's 1.0 and C's 5.0.
            write_transition_record(
                transition_exp, record_id="20260101-000000-aaaaaaa",
                rise_ps=400.0, fall_ps=400.0, step="20p",
            )
            write_default_triple(floor_exp)

            transition = bf.parse_transition_record(transition_exp)
            floors = bf.parse_floor_records(floor_exp)
            d = bf.bracket(transition, floors)
            self.assertEqual(d["bracket_lo"]["variant"], "B")
            self.assertEqual(d["bracket_hi"]["variant"], "C")
            self.assertAlmostEqual(d["floor_hi"], 0.00610)
            self.assertAlmostEqual(d["floor_lo"], 0.0)

    def test_a_ratio_outside_the_triples_own_range_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            transition_exp = Path(tmp) / "vco-clk-transition"
            floor_exp = Path(tmp) / "jitter-floor"
            # Edge/step ratio 10 -- beyond C's 5.0.
            write_transition_record(
                transition_exp, record_id="20260101-000000-aaaaaaa",
                rise_ps=2000.0, fall_ps=2000.0, step="20p",
            )
            write_default_triple(floor_exp)

            transition = bf.parse_transition_record(transition_exp)
            floors = bf.parse_floor_records(floor_exp)
            with self.assertRaises(bf.AnalysisError) as ctx:
                bf.bracket(transition, floors)
            self.assertIn("falls outside", str(ctx.exception))

    def test_a_missing_triple_member_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            transition_exp = Path(tmp) / "vco-clk-transition"
            floor_exp = Path(tmp) / "jitter-floor"
            write_transition_record(
                transition_exp, record_id="20260101-000000-aaaaaaa",
                rise_ps=60.0, fall_ps=60.0,
            )
            write_floor_record(
                floor_exp, record_id="20260101-000000-aaaaaaa", variant="A3",
                pct=2.371, edge="20p",
            )
            write_floor_record(
                floor_exp, record_id="20260101-000001-aaaaaaa", variant="B",
                pct=0.610, edge="200p",
            )
            # C is missing.
            transition = bf.parse_transition_record(transition_exp)
            floors = bf.parse_floor_records(floor_exp)
            with self.assertRaises(bf.AnalysisError) as ctx:
                bf.bracket(transition, floors)
            self.assertIn("A3/B/C triple", str(ctx.exception))

    def test_a_non_monotonic_triple_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            transition_exp = Path(tmp) / "vco-clk-transition"
            floor_exp = Path(tmp) / "jitter-floor"
            write_transition_record(
                transition_exp, record_id="20260101-000000-aaaaaaa",
                rise_ps=60.0, fall_ps=60.0,
            )
            # B's floor stated HIGHER than A3's -- violates monotonicity.
            write_floor_record(
                floor_exp, record_id="20260101-000000-aaaaaaa", variant="A3",
                pct=0.500, edge="20p",
            )
            write_floor_record(
                floor_exp, record_id="20260101-000001-aaaaaaa", variant="B",
                pct=0.900, edge="200p",
            )
            write_floor_record(
                floor_exp, record_id="20260101-000002-aaaaaaa", variant="C",
                pct=0.000, edge="1n",
            )
            transition = bf.parse_transition_record(transition_exp)
            floors = bf.parse_floor_records(floor_exp)
            with self.assertRaises(bf.AnalysisError) as ctx:
                bf.bracket(transition, floors)
            self.assertIn("monotonically decreasing", str(ctx.exception))


class RefusalTests(unittest.TestCase):
    """`main()`'s own end-to-end refusals."""

    def test_an_own_grid_too_coarse_to_resolve_its_own_edge_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            transition_exp = Path(tmp) / "vco-clk-transition"
            floor_exp = Path(tmp) / "jitter-floor"
            # A 100 ps own dump grid cannot resolve a 60 ps measured edge.
            write_transition_record(
                transition_exp, record_id="20260101-000000-aaaaaaa",
                rise_ps=60.0, fall_ps=60.0, step="100p",
            )
            write_default_triple(floor_exp)
            rc = bf.main([
                "--experiment", str(transition_exp),
                "--floor-experiment", str(floor_exp),
            ])
            self.assertEqual(rc, 2)

    def test_more_than_one_transition_record_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            transition_exp = Path(tmp) / "vco-clk-transition"
            write_transition_record(
                transition_exp, record_id="20260101-000000-aaaaaaa",
                rise_ps=60.0, fall_ps=60.0,
            )
            write_transition_record(
                transition_exp, record_id="20260101-000001-aaaaaaa",
                rise_ps=61.0, fall_ps=61.0,
            )
            with self.assertRaises(bf.AnalysisError) as ctx:
                bf.parse_transition_record(transition_exp)
            self.assertIn("assumes exactly one", str(ctx.exception))

    def test_floor_records_spanning_two_dump_grids_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            floor_exp = Path(tmp) / "jitter-floor"
            write_floor_record(
                floor_exp, record_id="20260101-000000-aaaaaaa", variant="A3",
                pct=2.371, edge="20p", step="200p",
            )
            write_floor_record(
                floor_exp, record_id="20260101-000001-aaaaaaa", variant="B",
                pct=0.610, edge="200p", step="100p",
            )
            with self.assertRaises(bf.AnalysisError) as ctx:
                bf.parse_floor_records(floor_exp)
            self.assertIn("one dump grid", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
