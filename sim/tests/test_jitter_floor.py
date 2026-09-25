#!/usr/bin/env python3
"""Unit tests for sim/pll-lock-mc/analysis/jitter_floor.py.

No PDK, ngspice or xschem required. Two kinds of case here:

1. **Drift detection against the real evidence.** The committed restatement
   (`sim/pll-lock-mc/analysis/jitter-floor/restatement.md`) is re-derived from
   the committed records and compared, which is the check `sim/README.md`
   requires of an `analysis/` directory -- so a record added to
   `sim/jitter-floor/records/`, or a drift in the Monte Carlo record's figures,
   fails here rather than leaving a stale derived document in the tree.
2. **Refusals, driven from synthetic records built in a temp directory.** The
   script's value is that it will not restate against inputs it cannot line up
   (a floor record that does not say which variant it is, a draw with no floor
   variant at its own period, a floor record set spanning two dump grids), so
   those refusals are asserted rather than assumed.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "sim" / "pll-lock-mc" / "analysis" / "jitter_floor.py"
MC_RECORD = REPO_ROOT / "sim" / "pll-lock-mc" / "records" / "20260924-222341-a9375a5.md"
FLOOR_EXPERIMENT = REPO_ROOT / "sim" / "jitter-floor"
RESTATEMENT = (
    REPO_ROOT / "sim" / "pll-lock-mc" / "analysis" / "jitter-floor" / "restatement.md"
)

# sim/pll-lock-mc/analysis/ is not an importable package (hyphens in the slug),
# so the module is loaded from its path -- the same pattern
# sim/tests/test_yield_evidence.py and sim/tests/test_pushing.py use.
_spec = importlib.util.spec_from_file_location("jitter_floor", SCRIPT_PATH)
jitter_floor = importlib.util.module_from_spec(_spec)
sys.modules["jitter_floor"] = jitter_floor
_spec.loader.exec_module(jitter_floor)  # type: ignore[union-attr]


FLOOR_RECORD_TEMPLATE = """# Record {record_id}

- **Record ID**: {record_id}
- **Methodology / criteria / limitations**:
  - DUT / limitations: {variant_line}
- **Result**:

  | Corner | Temp (C) | Supply (V) | Verdict | f_out | Duty | Detail |
  |---|---|---|---|---|---|---|
  | tt | 27 | 1.80 | PASS | 255.3 MHz | 50.0% | f_out 255.3 MHz, duty 50.0%, \
period jitter {pct}% RMS over 12764 cycles |
"""

CORNER_NETLIST_TEMPLATE = """** synthetic per-point netlist
VCLK CLK GND pulse(0 1.8 0 {edge} {edge} 1.9385n {period})
R1 CLK GND 1k m=1
.temp 27
.control
tran {step} 50u
linearize v(CLK)
wrdata tt_27c_1.80v-point000.raw v(CLK)
.endc
.end
"""


def write_floor_record(
    experiment: Path,
    *,
    record_id: str,
    variant: str = "A3",
    pct: float = 2.371,
    period: str = "3.9170n",
    edge: str = "20p",
    step: str = "200p",
    variant_line: str | None = None,
) -> None:
    """One synthetic `sim/jitter-floor`-shaped record plus its corner netlist."""
    (experiment / "records").mkdir(parents=True, exist_ok=True)
    (experiment / "corners" / record_id).mkdir(parents=True, exist_ok=True)
    if variant_line is None:
        variant_line = f"THIS RECORD'S VARIANT: {variant} -- synthetic."
    (experiment / "records" / f"{record_id}.md").write_text(
        FLOOR_RECORD_TEMPLATE.format(
            record_id=record_id, variant_line=variant_line, pct=pct
        )
    )
    (experiment / "corners" / record_id / "tt_27c_1.80v.spice").write_text(
        CORNER_NETLIST_TEMPLATE.format(edge=edge, period=period, step=step)
    )


class CommittedEvidenceTests(unittest.TestCase):
    """The committed restatement must still be what the committed records say."""

    def test_the_committed_restatement_matches_the_committed_records(self):
        self.assertTrue(RESTATEMENT.is_file(), f"{RESTATEMENT} is missing")
        self.assertEqual(jitter_floor.main(["--check"]), 0)

    def test_the_monte_carlo_record_still_parses_into_locked_draws(self):
        mc = jitter_floor.parse_mc_record(MC_RECORD)
        self.assertEqual(mc["record_id"], "20260924-222341-a9375a5")
        # Three of five draws locked and carry a jitter figure; the two that
        # never locked carry none, per row 9 being a post-lock quantity.
        self.assertEqual([d["trial"] for d in mc["draws"]], [2, 3, 5])
        for draw in mc["draws"]:
            self.assertGreater(draw["jitter_frac"], 0.01)
            self.assertGreater(draw["cycles"], 20)

    def test_every_committed_floor_record_shares_one_dump_grid(self):
        floors = jitter_floor.parse_floor_records(FLOOR_EXPERIMENT)
        self.assertEqual(len(floors), 5)
        self.assertEqual({f["step_s"] for f in floors}, {200e-12})
        self.assertEqual(
            sorted(f["variant"] for f in floors), ["A1", "A2", "A3", "B", "C"]
        )
        # The variant whose edge the grid resolves reports no floor at all.
        resolved = [f for f in floors if f["edge_s"] >= 2 * f["step_s"]]
        self.assertTrue(resolved)
        for f in resolved:
            self.assertEqual(f["floor_frac"], 0.0)


class SpiceLiteralTests(unittest.TestCase):
    def test_parses_the_literals_the_committed_netlists_use(self):
        self.assertAlmostEqual(jitter_floor.spice_time("200p"), 200e-12)
        self.assertAlmostEqual(jitter_floor.spice_time("3.9170n"), 3.9170e-9)
        self.assertAlmostEqual(jitter_floor.spice_time("50u"), 50e-6)
        self.assertAlmostEqual(jitter_floor.spice_time("1n"), 1e-9)
        self.assertAlmostEqual(jitter_floor.spice_time("4e-9"), 4e-9)

    def test_rejects_a_literal_it_cannot_read(self):
        for text in ("", "later", "3.9n7", "p200"):
            with self.subTest(text=text):
                with self.assertRaises(jitter_floor.AnalysisError):
                    jitter_floor.spice_time(text)


class RefusalTests(unittest.TestCase):
    def test_a_floor_record_without_a_variant_line_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-floor"
            write_floor_record(
                experiment,
                record_id="20260101-000000-abcdef0",
                variant_line="DUT: an ideal pulse source. (no variant declared)",
            )
            with self.assertRaises(jitter_floor.AnalysisError) as ctx:
                jitter_floor.parse_floor_records(experiment)
            self.assertIn("VARIANT", str(ctx.exception))

    def test_floor_records_at_two_different_grids_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-floor"
            write_floor_record(experiment, record_id="20260101-000000-abcdef0", step="200p")
            write_floor_record(
                experiment, record_id="20260101-000001-abcdef0", variant="D", step="20p"
            )
            with self.assertRaises(jitter_floor.AnalysisError) as ctx:
                jitter_floor.parse_floor_records(experiment)
            self.assertIn("one dump grid", str(ctx.exception))

    def test_a_draw_with_no_floor_variant_at_its_period_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-floor"
            # The only variant runs at 3.9170 ns; the draw below ran at 4.9 ns.
            write_floor_record(experiment, record_id="20260101-000000-abcdef0")
            floors = jitter_floor.parse_floor_records(experiment)
            draw = {"trial": 1, "freq_hz": 204.08e6, "jitter_frac": 0.02}
            with self.assertRaises(jitter_floor.AnalysisError) as ctx:
                jitter_floor.match_floor(draw, floors)
            self.assertIn("too far", str(ctx.exception))

    def test_a_floor_record_with_no_committed_netlist_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-floor"
            write_floor_record(experiment, record_id="20260101-000000-abcdef0")
            (experiment / "corners" / "20260101-000000-abcdef0" / "tt_27c_1.80v.spice").unlink()
            with self.assertRaises(jitter_floor.AnalysisError) as ctx:
                jitter_floor.parse_floor_records(experiment)
            self.assertIn("per-point netlist", str(ctx.exception))


class QuadratureTests(unittest.TestCase):
    """The restatement arithmetic itself, on synthetic inputs."""

    def _restate(self, *, measured_frac: float, floor_pct: float, freq_hz: float):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-floor"
            write_floor_record(
                experiment,
                record_id="20260101-000000-abcdef0",
                pct=floor_pct,
                period=f"{1e9 / (freq_hz / 1e9) / 1e9:.4f}n",
            )
            floors = jitter_floor.parse_floor_records(experiment)
            mc = {
                "record_id": "synthetic",
                "path": Path("sim/pll-lock-mc/records/synthetic.md"),
                "draws": [
                    {
                        "trial": 1,
                        "seed": 1,
                        "verdict": "FAIL",
                        "freq_hz": freq_hz,
                        "jitter_frac": measured_frac,
                        "cycles": 500,
                    }
                ],
            }
            return jitter_floor.restate(mc, floors)["rows"][0]

    def test_a_floor_well_below_the_measurement_barely_moves_it(self):
        # 2.0 % measured against a 0.2 % floor: sqrt(2.0^2 - 0.2^2) = 1.99 %.
        row = self._restate(measured_frac=0.02, floor_pct=0.2, freq_hz=250e6)
        self.assertAlmostEqual(row["residual_frac"], 0.0199, places=4)

    def test_a_floor_at_the_measurement_reports_no_separable_figure(self):
        # Never "zero jitter": a measurement at or below its own floor has
        # nothing separable in it, and that is what must be reported.
        row = self._restate(measured_frac=0.02, floor_pct=2.0, freq_hz=250e6)
        self.assertIsNone(row["residual_s"])
        self.assertIsNone(row["residual_frac"])

    def test_the_budget_column_is_row_9s_bound_in_absolute_time(self):
        row = self._restate(measured_frac=0.02, floor_pct=0.2, freq_hz=250e6)
        self.assertAlmostEqual(row["budget_s"], 40e-12, places=15)


if __name__ == "__main__":
    unittest.main()
