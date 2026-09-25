#!/usr/bin/env python3
"""Unit tests for `sim/jitter-calibration`'s generator and analysis script.

No PDK, ngspice or xschem required. Four kinds of case here:

1. **The seeded schedule still reproduces.** Every committed record's own
   per-point netlist is re-generated from the variant it names and compared
   point for point. This is what makes the injected figure *reproducible*
   rather than merely *recorded*: if a Python release, a refactor of
   `gen_pwl_clock.py`, or an edit to its constants changed the stream, these
   tests fail instead of the evidence trail quietly ceasing to be derivable.
2. **Drift detection against the real evidence.** The committed calibration
   document (`sim/jitter-calibration/analysis/calibration.md`) is re-derived
   from the committed records and compared, which is the check `sim/README.md`
   requires of an `analysis/` directory -- so a record added to
   `sim/jitter-calibration/records/`, or to `sim/jitter-floor/records/`, fails
   here rather than leaving a stale derived document in the tree.
3. **The exactness the campaign claims, asserted rather than assumed.** The
   generator's normalization must make `pstdev(T_k)/mean(T_k)` exactly the
   stated RMS, and the reducer must return the injected figure unchanged for
   the variants whose edge the dump grid resolves.
4. **Refusals, driven from synthetic records built in a temp directory.** The
   analysis script's value is that it will not restate against inputs it
   cannot line up, so those refusals are asserted rather than assumed.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import importlib.util
import math
import sys
import tempfile
import unittest
from pathlib import Path
from statistics import fmean, pstdev

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = REPO_ROOT / "sim" / "jitter-calibration"
FLOOR_EXPERIMENT = REPO_ROOT / "sim" / "jitter-floor"
GENERATOR_PATH = EXPERIMENT / "testbench" / "gen_pwl_clock.py"
ANALYSIS_PATH = EXPERIMENT / "analysis" / "calibration.py"
DOCUMENT = EXPERIMENT / "analysis" / "calibration.md"


def _load(name: str, path: Path):
    """Neither directory is an importable package (hyphens in the slug), so the
    modules are loaded from their paths -- the same pattern
    `sim/tests/test_jitter_floor.py` and `sim/tests/test_yield_evidence.py` use.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


gen = _load("gen_pwl_clock", GENERATOR_PATH)
calibration = _load("calibration", ANALYSIS_PATH)


def committed_rows() -> list:
    return calibration._parse_all(EXPERIMENT, calibration.parse_calibration_record)


CALIBRATION_RECORD_TEMPLATE = """# Record {record_id}

- **Record ID**: {record_id}
- **Result**:

  | Corner | Temp (C) | Supply (V) | Verdict | f_out | Duty | Detail |
  |---|---|---|---|---|---|---|
  | tt | 27 | 1.80 | PASS | 255.3 MHz | 50.0% | f_out 255.3 MHz, duty 50.0%, \
period jitter {pct}% RMS over {cycles} cycles |
"""

CORNER_NETLIST_TEMPLATE = """** synthetic per-point netlist
R1 CLK GND 1k m=1
** GENERATED -- variant {variant}: synthetic
{card}
.temp 27
.control
tran {step} 1.2u
linearize v(CLK)
wrdata tt_27c_1.80v-point000.raw v(CLK)
.endc
.end
"""


def write_calibration_record(
    experiment: Path,
    *,
    record_id: str,
    variant: str = "J10a",
    pct: float = 2.395,
    cycles: int | None = None,
    step: str = "200p",
    card: str | None = None,
) -> None:
    """One synthetic `sim/jitter-calibration`-shaped record plus its netlist."""
    schedule = gen.variant_schedule(variant)
    if card is None:
        card = schedule["card"]
    if cycles is None:
        cycles = schedule["cycles"]
    (experiment / "records").mkdir(parents=True, exist_ok=True)
    (experiment / "corners" / record_id).mkdir(parents=True, exist_ok=True)
    (experiment / "records" / f"{record_id}.md").write_text(
        CALIBRATION_RECORD_TEMPLATE.format(
            record_id=record_id, pct=pct, cycles=cycles
        )
    )
    (experiment / "corners" / record_id / "tt_27c_1.80v.spice").write_text(
        CORNER_NETLIST_TEMPLATE.format(variant=variant, card=card, step=step)
    )
    manifest = experiment / "testbench"
    manifest.mkdir(parents=True, exist_ok=True)
    (manifest / "tb.json").write_text('{"threshold_frac": 0.5}')


class GeneratorExactnessTests(unittest.TestCase):
    """The injected figure is exact by construction, not by luck of the draw."""

    def test_normalized_deviates_have_exactly_zero_mean_and_unit_spread(self):
        g = gen.normalized_normals(185010, gen.CYCLES)
        self.assertEqual(len(g), gen.CYCLES)
        self.assertAlmostEqual(fmean(g), 0.0, places=12)
        self.assertAlmostEqual(pstdev(g), 1.0, places=12)

    def test_every_variant_injects_exactly_its_stated_rms(self):
        for variant, spec in sorted(gen.VARIANTS.items()):
            with self.subTest(variant=variant):
                schedule = gen.variant_schedule(variant)
                # `measure.period_jitter`'s own estimator, applied to the
                # schedule the generator built.
                self.assertAlmostEqual(
                    schedule["injected_frac"], spec["rms_frac"], places=12
                )

    def test_the_mean_period_is_exactly_nominal_so_every_family_is_one_window(self):
        spans: dict = {}
        for variant in sorted(gen.VARIANTS):
            schedule = gen.variant_schedule(variant)
            self.assertAlmostEqual(
                fmean(schedule["periods"]),
                gen.FAMILY_PERIOD_S[schedule["family"]],
                places=21,
            )
            spans.setdefault(schedule["family"], set()).add(
                round(schedule["span_s"], 18)
            )
        self.assertEqual(sorted(spans), sorted(gen.FAMILY_PERIOD_S))
        for family, family_spans in sorted(spans.items()):
            with self.subTest(family=family):
                self.assertEqual(
                    len(family_spans),
                    1,
                    f"family {family}'s variants do not share one window length",
                )

    def test_every_variant_fits_the_manifests_transient_window(self):
        """The guard that keeps the reducer's population the schedule's own.

        Family K's 300 cycles at its longer period run past issue #185's
        original 1.2 us window; `pwl_points` refuses a schedule the manifest's
        window would truncate rather than letting a record be minted from a
        smaller population than the committed schedule holds.
        """
        for variant in sorted(gen.VARIANTS):
            with self.subTest(variant=variant):
                self.assertLess(
                    gen.variant_schedule(variant)["last_point_s"], gen.TRAN_STOP_S
                )
        rising = gen.rising_edges(gen.periods(0.01, 185010, cycles=4000))
        with self.assertRaises(gen.GeneratorError) as ctx:
            gen.pwl_points(rising, gen.periods(0.01, 185010, cycles=4000), 20e-12)
        self.assertIn("transient window", str(ctx.exception))

    def test_every_variant_emits_a_strictly_increasing_schedule(self):
        for variant in sorted(gen.VARIANTS):
            with self.subTest(variant=variant):
                # `pwl_points` raises on a non-monotonic schedule; reaching
                # here at all is the assertion.
                points = gen.variant_schedule(variant)["points"]
                times = [t for t, _ in points]
                self.assertEqual(times, sorted(times))

    def test_the_three_edge_variants_of_one_rms_share_one_edge_schedule(self):
        for family in sorted(gen.FAMILY_PERIOD_S):
            for rms in ("05", "10", "20"):
                with self.subTest(family=family, rms=rms):
                    schedules = [
                        gen.variant_schedule(f"{family}{rms}{edge}") for edge in "abc"
                    ]
                    first = schedules[0]["rising"]
                    for other in schedules[1:]:
                        self.assertEqual(first, other["rising"])

    def test_two_families_at_one_rms_share_one_normalized_draw(self):
        """What isolates the *period's* contribution (issue #197).

        The seed depends only on the injected RMS -- not on the edge, not on the
        family -- so a J/K pair is the identical normalized draw scaled to the
        two nominal periods. Asserted as an exact ratio rather than by eye: each
        drawn period must be its counterpart times the ratio of the two nominal
        periods.
        """
        ratio = gen.PERIOD_NOM_K_S / gen.PERIOD_NOM_S
        for rms in ("05", "10", "20"):
            for edge in "abc":
                with self.subTest(rms=rms, edge=edge):
                    j = gen.variant_schedule(f"J{rms}{edge}")["periods"]
                    k = gen.variant_schedule(f"K{rms}{edge}")["periods"]
                    self.assertEqual(len(j), len(k))
                    for a, b in zip(j, k):
                        self.assertAlmostEqual(b / a, ratio, places=12)

    def test_an_rms_outside_the_open_unit_interval_is_refused(self):
        for bad in (0.0, 1.0, -0.01, 1.5):
            with self.subTest(rms=bad):
                with self.assertRaises(gen.GeneratorError):
                    gen.periods(bad, 1)

    def test_retargeting_a_manifest_without_exactly_one_marker_is_refused(self):
        self.assertIn(
            "THIS RECORD'S VARIANT: J10a",
            gen.retarget_manifest("x THIS RECORD'S VARIANT: J20c y", "J10a"),
        )
        with self.assertRaises(gen.GeneratorError):
            gen.retarget_manifest("no marker here", "J10a")
        with self.assertRaises(gen.GeneratorError):
            gen.retarget_manifest(
                "THIS RECORD'S VARIANT: A THIS RECORD'S VARIANT: B", "J10a"
            )


class CommittedEvidenceTests(unittest.TestCase):
    """The committed evidence must still be what the generator and the records say."""

    def test_the_committed_document_matches_the_committed_records(self):
        self.assertTrue(DOCUMENT.is_file(), f"{DOCUMENT} is missing")
        self.assertEqual(calibration.main(["--check"]), 0)

    def test_every_committed_record_names_a_known_variant(self):
        rows = committed_rows()
        self.assertEqual(len(rows), len(gen.VARIANTS))
        self.assertEqual(
            sorted(r["variant"] for r in rows), sorted(gen.VARIANTS)
        )

    def test_every_committed_netlist_is_reproduced_by_the_generator(self):
        """The seeded RNG still lands on the committed edge schedule.

        This is the test that keeps the injected figure *reproducible*: the
        committed netlist is evidence, and this asserts the generator beside it
        still derives that exact evidence rather than merely something like it.
        """
        for row in committed_rows():
            with self.subTest(variant=row["variant"]):
                card = gen.variant_schedule(row["variant"])["card"]
                regenerated = calibration.pwl_points(
                    card + "\n", Path(f"<regenerated {row['variant']}>")
                )
                committed = calibration.pwl_points(
                    (REPO_ROOT / row["netlist"]).read_text(),
                    REPO_ROOT / row["netlist"],
                )
                self.assertEqual(regenerated, committed)

    def test_every_committed_record_injected_exactly_its_variants_rms(self):
        """Re-derived from the committed netlist, not from the generator.

        The tolerance is **relative**, and it is the PWL card's own 1 fs time
        quantum rather than the generator's float precision: writing each ramp
        endpoint to 6 decimals of a nanosecond perturbs every reconstructed
        crossing by up to half a femtosecond, and that perturbation's
        correlation with the drawn schedule shifts the re-derived figure by
        order `(quantum / injected jitter) / sqrt(N)` -- a few parts per
        million at the smallest variant here, four orders of magnitude below
        the ~4 % sampling error the *reported* figures carry, and invisible at
        the three-decimal precision the records print.
        """
        for row in committed_rows():
            with self.subTest(variant=row["variant"]):
                stated = gen.VARIANTS[row["variant"]]["rms_frac"]
                self.assertAlmostEqual(row["injected_frac"] / stated, 1.0, places=4)

    def test_a_resolved_edge_returns_the_injected_figure_unchanged(self):
        """The calibration's own control: at an edge the grid resolves, the
        reducer must be unbiased. This is what rules out a generator that
        injects something other than what it claims."""
        resolved = [r for r in committed_rows() if r["edge_s"] >= 2.0 * r["step_s"]]
        self.assertTrue(resolved, "no committed variant has a grid-resolved edge")
        for row in resolved:
            with self.subTest(variant=row["variant"]):
                self.assertAlmostEqual(
                    row["reported_frac"], row["injected_frac"], places=5
                )

    def test_an_unresolved_edge_inflates_the_reported_figure(self):
        """...and at an edge it cannot resolve, it must not. A regression that
        silently resolved the edge (a finer grid, a slower ramp) would make
        this campaign measure nothing, so the asymmetry is pinned."""
        unresolved = [r for r in committed_rows() if r["edge_s"] <= 0.5 * r["step_s"]]
        self.assertTrue(unresolved, "no committed variant has an unresolved edge")
        for row in unresolved:
            with self.subTest(variant=row["variant"]):
                self.assertGreater(row["reported_frac"], row["injected_frac"])

    def test_the_null_control_is_still_readable_for_comparison(self):
        """Every calibration variant's null-control pairing, stated rather than
        assumed to exist.

        `sim/jitter-floor`'s family ran all three edges at family J's period
        (A3/B/C) but only the fastest edge at family K's (A1), so the pairing is
        complete at 20 ps and absent at the two slower edges of family K. That
        asymmetry is why the rendered document has a "no null-control variant at
        this period and edge" cell at all, and pinning it here keeps a future
        `sim/jitter-floor` variant (or a renamed one) from silently changing
        which rows the #197 section can score.
        """
        floors = calibration._parse_all(
            FLOOR_EXPERIMENT, calibration.parse_floor_record
        )
        self.assertEqual(len(floors), 5)
        matched = {
            row["variant"]: (
                None
                if calibration.match_floor(row, floors) is None
                else calibration.match_floor(row, floors)["variant"]
            )
            for row in committed_rows()
        }
        self.assertEqual(
            matched,
            {
                "J05a": "A3", "J10a": "A3", "J20a": "A3",
                "J05b": "B", "J10b": "B", "J20b": "B",
                "J05c": "C", "J10c": "C", "J20c": "C",
                "K05a": "A1", "K10a": "A1", "K20a": "A1",
                "K05b": None, "K10b": None, "K20b": None,
                "K05c": None, "K10c": None, "K20c": None,
            },
        )

    def test_the_implied_floor_is_below_the_reported_figure_everywhere(self):
        """Quadrature is only meaningful while the floor is a component of the
        total, never the whole of it."""
        rows = committed_rows()
        floors = calibration._parse_all(
            FLOOR_EXPERIMENT, calibration.parse_floor_record
        )
        for row in calibration.restate(rows, floors)["rows"]:
            with self.subTest(variant=row["variant"]):
                if row["implied_floor_s"] is None:
                    continue
                self.assertLess(row["implied_floor_s"], row["reported_s"])

    def test_the_committed_records_cover_two_period_families(self):
        """The evidence issue #197 asked for exists, at the periods it named.

        3.9952 ns is trial 2's own measured post-lock period in
        `sim/pll-lock-mc/records/20260924-222341-a9375a5.md`, which is what lets
        a future restatement there cite these records instead of extrapolating
        across periods.
        """
        derived = calibration.restate(
            committed_rows(),
            calibration._parse_all(FLOOR_EXPERIMENT, calibration.parse_floor_record),
        )
        self.assertEqual([f["letter"] for f in derived["families"]], ["J", "K"])
        self.assertAlmostEqual(
            derived["families"][0]["period_s"], gen.PERIOD_NOM_S, places=13
        )
        self.assertAlmostEqual(
            derived["families"][1]["period_s"], gen.PERIOD_NOM_K_S, places=13
        )
        # Grid phases at opposite ends of the range, which is the whole point of
        # running a second family at all.
        self.assertLess(derived["families"][0]["f_phase"], 0.7)
        self.assertGreater(derived["families"][1]["f_phase"], 0.9)

    def test_the_null_controls_error_changes_sign_between_the_two_families(self):
        """Issue #197's finding, pinned to the committed evidence.

        At family J's period the null control's measured floor sits **above**
        the floor this campaign implied for a signal that genuinely jitters (so
        a correction using it over-corrects); at family K's it sits **below**
        it. Neither direction is a property of the pipeline -- which is the
        claim `analysis/calibration.md` could only argue from the walk-phase
        formula before this family ran.
        """
        derived = calibration.restate(
            committed_rows(),
            calibration._parse_all(FLOOR_EXPERIMENT, calibration.parse_floor_record),
        )
        directions = {
            fam["letter"]: calibration._direction(fam) for fam in derived["families"]
        }
        self.assertEqual(directions, {"J": "over", "K": "under"})
        for fam in derived["families"]:
            with self.subTest(family=fam["letter"]):
                self.assertTrue(fam["signed"], "no variant could be scored")
                # The same direction, read off the arithmetic bound rather than
                # the measured null control: the two must agree here, or the
                # document's rendered agreement claim is wrong.
                predicted_over = fam["walk_phase_s"] > fam["uniform_phase_s"]
                self.assertEqual(
                    predicted_over, calibration._direction(fam) == "over"
                )


class RefusalTests(unittest.TestCase):
    """The analysis script refuses inputs it cannot line up, rather than guessing."""

    def test_a_netlist_with_no_pwl_card_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-calibration"
            write_calibration_record(experiment, record_id="20260101-000000-aaaaaaa")
            netlist = (
                experiment / "corners" / "20260101-000000-aaaaaaa" / "tt_27c_1.80v.spice"
            )
            netlist.write_text(netlist.read_text().replace("pwl(", "pulse("))
            with self.assertRaises(calibration.AnalysisError) as ctx:
                calibration._parse_all(experiment, calibration.parse_calibration_record)
            self.assertIn("pwl(", str(ctx.exception))

    def test_a_population_mismatch_between_record_and_schedule_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-calibration"
            write_calibration_record(
                experiment, record_id="20260101-000000-aaaaaaa", cycles=42
            )
            with self.assertRaises(calibration.AnalysisError) as ctx:
                calibration._parse_all(experiment, calibration.parse_calibration_record)
            self.assertIn("same population", str(ctx.exception))

    def test_records_spanning_two_dump_grids_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-calibration"
            write_calibration_record(experiment, record_id="20260101-000000-aaaaaaa")
            write_calibration_record(
                experiment,
                record_id="20260101-000001-aaaaaaa",
                variant="J10b",
                step="100p",
            )
            rows = calibration._parse_all(
                experiment, calibration.parse_calibration_record
            )
            with self.assertRaises(calibration.AnalysisError) as ctx:
                calibration.restate(rows, [])
            self.assertIn("one dump grid", str(ctx.exception))

    def test_records_whose_names_and_periods_disagree_are_refused(self):
        """A variant's family letter *is* its nominal period (issue #197).

        Two records naming the same family letter but carrying schedules at two
        different periods mean the committed names no longer describe the
        committed evidence, which would silently mis-group the per-period
        restatement. Refused rather than grouped by period and renamed.
        """
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-calibration"
            write_calibration_record(
                experiment, record_id="20260101-000000-aaaaaaa", variant="J20a"
            )
            write_calibration_record(
                experiment,
                record_id="20260101-000001-aaaaaaa",
                variant="J10a",
                # ...but at family K's period, which its name does not say.
                card=gen.variant_schedule("K10a")["card"],
            )
            rows = calibration._parse_all(
                experiment, calibration.parse_calibration_record
            )
            with self.assertRaises(calibration.AnalysisError) as ctx:
                calibration.restate(rows, [])
            self.assertIn("two different nominal periods", str(ctx.exception))

    def test_records_at_two_periods_restate_as_two_families(self):
        """The two-period case the committed evidence exercises, on synthetic
        records: `restate` groups rather than refusing, and keeps each family's
        own grid phase."""
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-calibration"
            write_calibration_record(
                experiment, record_id="20260101-000000-aaaaaaa", variant="J10a"
            )
            write_calibration_record(
                experiment,
                record_id="20260101-000001-aaaaaaa",
                variant="K10a",
                card=gen.variant_schedule("K10a")["card"],
            )
            derived = calibration.restate(
                calibration._parse_all(
                    experiment, calibration.parse_calibration_record
                ),
                [],
            )
            self.assertEqual([f["letter"] for f in derived["families"]], ["J", "K"])
            self.assertEqual([len(f["rows"]) for f in derived["families"]], [1, 1])
            # No null-control records were handed in, so no family can state a
            # measured direction -- and the restatement must not invent one.
            self.assertEqual(
                [calibration._direction(f) for f in derived["families"]], [None, None]
            )

    def test_a_non_monotonic_schedule_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-calibration"
            write_calibration_record(
                experiment,
                record_id="20260101-000000-aaaaaaa",
                card="VCLK CLK GND pwl(\n+ 0n 0 3n 0 2n 1.8 4n 1.8\n+ )",
            )
            with self.assertRaises(calibration.AnalysisError) as ctx:
                calibration._parse_all(experiment, calibration.parse_calibration_record)
            self.assertIn("strictly increasing", str(ctx.exception))

    def test_an_unclosed_pwl_card_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-calibration"
            write_calibration_record(
                experiment,
                record_id="20260101-000000-aaaaaaa",
                card="VCLK CLK GND pwl(\n+ 0n 0 1n 0 2n 1.8 3n 1.8",
            )
            with self.assertRaises(calibration.AnalysisError):
                calibration._parse_all(experiment, calibration.parse_calibration_record)

    def test_a_drifted_threshold_fraction_is_refused(self):
        """`injected_from_pwl` reads the crossing off as the ramp midpoint,
        which is only the measured instant at a 0.5 threshold fraction."""
        with self.assertRaises(calibration.AnalysisError) as ctx:
            calibration._assert_threshold('{"threshold_frac": 0.4}')
        self.assertIn("threshold_frac", str(ctx.exception))
        calibration._assert_threshold('{"threshold_frac": 0.5}')

    def test_an_empty_experiment_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "jitter-calibration"
            (experiment / "records").mkdir(parents=True)
            with self.assertRaises(calibration.AnalysisError):
                calibration._parse_all(experiment, calibration.parse_calibration_record)


class ArithmeticTests(unittest.TestCase):
    """The two grid bounds the document prints, checked against their formulas."""

    def test_the_uniform_phase_bound_is_sqrt2_over_sqrt12_of_the_step(self):
        rows = committed_rows()
        floors = calibration._parse_all(
            FLOOR_EXPERIMENT, calibration.parse_floor_record
        )
        derived = calibration.restate(rows, floors)
        step = derived["step_s"]
        self.assertAlmostEqual(
            derived["uniform_phase_s"],
            math.sqrt(2.0) * step / math.sqrt(12.0),
            places=18,
        )
        # The walk-phase bound is period-specific, so it is checked per family
        # against that family's own `f` -- the uniform-phase one is not, and
        # every family must report the same figure for it.
        for fam in derived["families"]:
            with self.subTest(period_ns=1e9 * fam["period_s"]):
                f = fam["f_phase"]
                self.assertTrue(0.0 <= f < 1.0)
                self.assertAlmostEqual(
                    fam["walk_phase_s"], step * math.sqrt(f * (1.0 - f)), places=18
                )
                self.assertAlmostEqual(
                    fam["uniform_phase_s"], derived["uniform_phase_s"], places=18
                )
        self.assertEqual(
            len({round(fam["f_phase"], 12) for fam in derived["families"]}),
            len(derived["families"]),
            "two period families report the same grid phase",
        )

    def test_spice_literals_parse_the_suffixes_this_evidence_uses(self):
        self.assertAlmostEqual(calibration.spice_literal("200p"), 200e-12)
        self.assertAlmostEqual(calibration.spice_literal("3.9170n"), 3.9170e-9)
        self.assertAlmostEqual(calibration.spice_literal("1.2u"), 1.2e-6)
        self.assertAlmostEqual(calibration.spice_literal("1.8"), 1.8)
        self.assertAlmostEqual(calibration.spice_literal("0"), 0.0)
        with self.assertRaises(calibration.AnalysisError):
            calibration.spice_literal("not-a-number")


if __name__ == "__main__":
    unittest.main()
