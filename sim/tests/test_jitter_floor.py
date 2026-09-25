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
CALIBRATION_EXPERIMENT = REPO_ROOT / "sim" / "jitter-calibration"
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


CALIBRATION_RECORD_TEMPLATE = """# Record {record_id}

- **Record ID**: {record_id}
- **Methodology / criteria / limitations**:
  - DUT / limitations: {variant_line}
- **Result**:

  | Corner | Temp (C) | Supply (V) | Verdict | f_out | Duty | Detail |
  |---|---|---|---|---|---|---|
  | tt | 27 | 1.80 | PASS | 255.3 MHz | 50.0% | f_out 255.3 MHz, duty 50.0%, \
period jitter {pct}% RMS over {cycles} cycles |
"""


def _pwl_points(period_s: float, edge_s: float, cycles: int) -> list[tuple[float, float]]:
    """A synthetic, exactly-periodic PWL rising-edge schedule (no injected jitter).

    This test only exercises period matching, never a reported-vs-injected
    figure, so an exact period rather than a jittered one keeps the fixture
    simple; `calibration_schedule` does not care which it is handed. Requires
    `edge_s < period_s / 2` so the rising and falling edges never overlap.
    """
    v_low, v_high = 0.0, 1.8
    points: list[tuple[float, float]] = [(0.0, v_low)]
    t = 0.0
    for _ in range(cycles + 1):
        points.append((t + edge_s, v_high))  # rising edge ends
        points.append((t + period_s - edge_s, v_high))  # falling edge starts
        t += period_s
        points.append((t, v_low))  # falling edge ends / next low hold starts
    return points


def _pwl_card(points: list[tuple[float, float]]) -> str:
    lines = ["VCLK CLK GND pwl("]
    for i in range(0, len(points), 2):
        pair = points[i : i + 2]
        fields = " ".join(f"{t * 1e9:.6f}n {v:g}" for t, v in pair)
        lines.append(f"+ {fields}")
    lines.append("+ )")
    return "\n".join(lines) + "\n"


def write_calibration_record(
    experiment: Path,
    *,
    record_id: str,
    variant: str = "J05a",
    pct: float = 2.375,
    period_s: float = 3.9170e-9,
    edge_s: float = 20e-12,
    cycles: int = 5,
    step: str = "200p",
) -> None:
    """One synthetic `sim/jitter-calibration`-shaped record plus its netlist."""
    (experiment / "records").mkdir(parents=True, exist_ok=True)
    (experiment / "corners" / record_id).mkdir(parents=True, exist_ok=True)
    variant_line = f"THIS RECORD'S VARIANT: {variant} -- synthetic."
    (experiment / "records" / f"{record_id}.md").write_text(
        CALIBRATION_RECORD_TEMPLATE.format(
            record_id=record_id, variant_line=variant_line, pct=pct, cycles=cycles
        )
    )
    netlist = (
        "** synthetic per-point netlist\n"
        f"{_pwl_card(_pwl_points(period_s, edge_s, cycles))}"
        "R1 CLK GND 1k m=1\n"
        ".temp 27\n"
        ".control\n"
        f"tran {step} 1.2u\n"
        "linearize v(CLK)\n"
        "wrdata tt_27c_1.80v-point000.raw v(CLK)\n"
        ".endc\n"
        ".end\n"
    )
    (experiment / "corners" / record_id / "tt_27c_1.80v.spice").write_text(netlist)


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

    def test_calibration_covers_trials_2_and_5s_periods_today(self):
        # Committed evidence for which of issue #193's two Decline grounds
        # applies per draw. sim/jitter-calibration runs two period families:
        # 3.9170 ns (issue #185, trial 5's period) and 3.9952 ns (issue #197,
        # trial 2's). Trial 3's own 3.9904 ns is still unvisited, so the
        # cross-period-extrapolation ground still applies to it and to nothing
        # else -- which is exactly what the rendered restatement now says per
        # draw. A future family at 3.9904 ns is expected to change this test
        # (and the rendered document with it), not to be worked around.
        mc = jitter_floor.parse_mc_record(MC_RECORD)
        cal = jitter_floor.parse_calibration_records(CALIBRATION_EXPERIMENT)
        self.assertEqual(len(cal), 18)
        periods = sorted({round(c["period_s"], 15) for c in cal})
        self.assertEqual(len(periods), 2, f"expected two calibration periods, got {periods}")
        for period_s, expected_ns in zip(periods, (3.9170, 3.9952)):
            self.assertAlmostEqual(1e9 * period_s, expected_ns, places=3)
        coverage = {
            draw["trial"]: bool(
                jitter_floor.calibration_variants_at(1.0 / draw["freq_hz"], cal)
            )
            for draw in mc["draws"]
        }
        self.assertEqual(coverage, {2: True, 3: False, 5: True})


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

    def _restate(
        self, *, measured_frac: float, floor_pct: float, freq_hz: float, cal_records=None
    ):
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
            return jitter_floor.restate(mc, floors, cal_records or [])["rows"][0]

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


class CalibrationCoverageTests(unittest.TestCase):
    """The Decline resolution (issue #193): period coverage is checked, never
    used to correct a residual -- so `restate` must carry the coverage flag
    per draw, and the quadrature residual must not change with it."""

    def test_calibration_schedule_reads_back_the_synthetic_period_and_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-calibration"
            write_calibration_record(
                experiment,
                record_id="20260101-000000-abcdef0",
                period_s=3.9170e-9,
                edge_s=20e-12,
                cycles=5,
            )
            cal = jitter_floor.parse_calibration_records(experiment)
            self.assertEqual(len(cal), 1)
            self.assertAlmostEqual(cal[0]["period_s"], 3.9170e-9, places=12)
            self.assertAlmostEqual(cal[0]["edge_s"], 20e-12, places=15)
            self.assertEqual(cal[0]["cycles"], 5)
            self.assertEqual(cal[0]["variant"], "J05a")

    def test_calibration_variants_at_matches_only_the_shared_period(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-calibration"
            write_calibration_record(
                experiment, record_id="20260101-000000-abcdef0", period_s=3.9170e-9
            )
            cal = jitter_floor.parse_calibration_records(experiment)
            # Trial 5's own period (3.9170 ns): a match.
            self.assertEqual(len(jitter_floor.calibration_variants_at(3.9170e-9, cal)), 1)
            # Trial 2's own period (3.9952 ns): no calibration variant there --
            # an empty list, not a refusal, per this script's Decline decision.
            self.assertEqual(jitter_floor.calibration_variants_at(3.9952e-9, cal), [])

    def test_restate_flags_calibration_coverage_without_changing_the_residual(self):
        with tempfile.TemporaryDirectory() as tmp:
            floor_experiment = Path(tmp) / "jitter-floor"
            cal_experiment = Path(tmp) / "jitter-calibration"
            write_floor_record(
                floor_experiment,
                record_id="20260101-000000-abcdef0",
                pct=0.5,
                period="3.9170n",
            )
            write_calibration_record(
                cal_experiment, record_id="20260101-000001-abcdef0", period_s=3.9170e-9
            )
            floors = jitter_floor.parse_floor_records(floor_experiment)
            cal = jitter_floor.parse_calibration_records(cal_experiment)
            mc = {
                "record_id": "synthetic",
                "path": Path("sim/pll-lock-mc/records/synthetic.md"),
                "draws": [
                    {
                        "trial": 1,
                        "seed": 1,
                        "verdict": "FAIL",
                        "freq_hz": 1.0 / 3.9170e-9,
                        "jitter_frac": 0.02,
                        "cycles": 500,
                    },
                    {
                        "trial": 2,
                        "seed": 2,
                        "verdict": "FAIL",
                        # A period the synthetic calibration family never ran.
                        "freq_hz": 1.0 / 5.0e-9,
                        "jitter_frac": 0.02,
                        "cycles": 500,
                    },
                ],
            }
            # Both draws need a floor variant of their own too -- give trial 2
            # one at its period so only the calibration coverage differs.
            write_floor_record(
                floor_experiment,
                record_id="20260101-000002-abcdef0",
                variant="D",
                pct=0.5,
                period="5.0000n",
            )
            floors = jitter_floor.parse_floor_records(floor_experiment)
            derived = jitter_floor.restate(mc, floors, cal)
            covered, uncovered = derived["rows"]
            self.assertTrue(covered["has_calibration_at_period"])
            self.assertFalse(uncovered["has_calibration_at_period"])
            # The quadrature residual is identical arithmetic either way --
            # this script declines to let calibration coverage touch it.
            self.assertAlmostEqual(
                covered["residual_frac"], uncovered["residual_frac"], places=9
            )


if __name__ == "__main__":
    unittest.main()
