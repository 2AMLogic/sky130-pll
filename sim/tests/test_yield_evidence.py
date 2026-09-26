#!/usr/bin/env python3
"""Unit tests for sim/pll-lock-mc/analysis/yield_evidence.py.

No PDK, ngspice, xschem or `klt` required: every test drives the parsing and
derivation functions from a synthetic Monte Carlo record body and a synthetic
`tb.json` manifest it builds itself, so what the derivation produces is checked
against inputs whose correct output is known by construction rather than read
back out of the one committed record.

The failure paths matter as much as the happy one here: this script's whole
value is that it refuses to grade a drifted record (a manifest whose jitter
bound no longer matches the ratified spec row, a locked trial with no jitter
figure, a seed list that disagrees with the manifest), so those refusals are
asserted rather than assumed.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "sim" / "pll-lock-mc" / "analysis" / "yield_evidence.py"
RECORD_PATH = (
    REPO_ROOT / "sim" / "pll-lock-mc" / "records" / "20260924-222341-a9375a5.md"
)
MANIFEST_PATH = REPO_ROOT / "sim" / "pll-lock-mc" / "testbench" / "tb.json"
EVIDENCE_DIR = REPO_ROOT / "sim" / "pll-lock-mc" / "analysis" / "yield-evidence"

# sim/pll-lock-mc/analysis/ is not an importable package (the slug directory
# name has hyphens, which are not valid in a Python package path), so the
# module is loaded directly from its file path -- the same pattern
# sim/tests/test_pushing.py uses for the sibling analysis script.
_spec = importlib.util.spec_from_file_location("yield_evidence", SCRIPT_PATH)
yield_evidence = importlib.util.module_from_spec(_spec)
sys.modules["yield_evidence"] = yield_evidence
_spec.loader.exec_module(yield_evidence)  # type: ignore[union-attr]


def manifest(**overrides) -> dict:
    """A minimal tb.json carrying only the fields `parse_manifest` reads."""
    doc = {
        "measure": {
            "node": "CLK",
            "tran_step": "200p",
            "tran_stop": "50u",
            "jitter": {"max_frac": 0.01, "min_cycles": 20},
        },
        "monte_carlo": {
            "corner": "tt",
            "temp_c": 125,
            "supply_v": 1.8,
            "mismatch": True,
            "process": True,
            "trials": 3,
            "seed_base": 1,
        },
    }
    for dotted, value in overrides.items():
        outer, _, inner = dotted.partition(".")
        if inner:
            target = doc[outer]
            if inner == "jitter.max_frac":
                target["jitter"]["max_frac"] = value
            elif inner == "jitter.min_cycles":
                target["jitter"]["min_cycles"] = value
            else:
                target[inner] = value
        else:
            doc[outer] = value
    return doc


def record(rows: list[tuple], *, trials: int = 3, seed_base: int = 1) -> str:
    """Build a record body carrying just what `parse_record` reads.

    Each row is `(trial, seed, verdict, locked, jitter_cell)`.
    """
    passed = sum(1 for row in rows if row[2] == "PASS")
    lines = [
        "# Record 20260101-000000-abcdef0",
        "",
        "- **Record ID**: 20260101-000000-abcdef0",
        "- **Statistical sampling point**:",
        f"  - Trials: {trials} (seeds {seed_base}..{seed_base + trials - 1}, "
        "one ngspice `.options seed=<N>` per trial)",
        "- **Result**:",
        "",
        "  | Trial | Seed | Verdict | Locked | Time-to-lock | f_out (post-lock) "
        "| Duty | Period jitter | Detail |",
        "  |---|---|---|---|---|---|---|---|---|",
    ]
    for trial, seed, verdict, locked, jitter in rows:
        locked_cell = "yes" if locked else "**no**"
        lines.append(
            f"  | {trial} | {seed} | {verdict} | {locked_cell} | 26.32 us | "
            f"250.3 MHz | 49.5% | {jitter} | detail text |"
        )
    lines += [
        "",
        f"  - **Overall: {'PASS' if passed == len(rows) else 'FAIL'}** "
        f"({passed}/{len(rows)} trials passed)",
        "",
    ]
    return "\n".join(lines) + "\n"


THREE_ROWS = [
    (1, 1, "PASS", False, "-"),
    (2, 2, "FAIL", True, "1.500% (5000 cycles)"),
    (3, 3, "FAIL", True, "2.500% (2500 cycles)"),
]


class ParseRecordTests(unittest.TestCase):
    def test_reads_trials_seeds_and_rows(self):
        parsed = yield_evidence.parse_record(record(THREE_ROWS))
        self.assertEqual(parsed["record_id"], "20260101-000000-abcdef0")
        self.assertEqual(parsed["declared_trials"], 3)
        self.assertEqual((parsed["seed_first"], parsed["seed_last"]), (1, 3))
        self.assertEqual([row["seed"] for row in parsed["rows"]], [1, 2, 3])
        self.assertEqual(
            [row["locked"] for row in parsed["rows"]], ["no", "yes", "yes"]
        )
        self.assertEqual(parsed["overall"], "FAIL")
        self.assertEqual(parsed["passed"], 1)

    def test_missing_table_raises(self):
        body = record(THREE_ROWS).split("- **Result**")[0]
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.parse_record(body)

    def test_missing_trials_line_raises(self):
        body = "\n".join(
            line for line in record(THREE_ROWS).splitlines() if "Trials:" not in line
        )
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.parse_record(body)

    def test_missing_overall_line_raises(self):
        body = "\n".join(
            line for line in record(THREE_ROWS).splitlines() if "Overall:" not in line
        )
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.parse_record(body)


class ParseManifestTests(unittest.TestCase):
    def test_reads_bound_and_sampling_point(self):
        parsed = yield_evidence.parse_manifest(manifest())
        self.assertEqual(parsed["max_frac"], 0.01)
        self.assertEqual(parsed["min_cycles"], 20)
        self.assertEqual(yield_evidence.corner_id(parsed), "tt_mm_125c_1.80v")

    def test_bound_that_drifted_from_the_ratified_row_raises(self):
        # CLAUDE.md: a ratified row is never relaxed to make a result pass. A
        # manifest that no longer gates at row 9's 1.0 % must stop the
        # derivation, not silently grade against the drifted number.
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.parse_manifest(manifest(**{"measure.jitter.max_frac": 0.02}))

    def test_mismatch_off_drops_the_mm_suffix(self):
        parsed = yield_evidence.parse_manifest(
            manifest(**{"monte_carlo.mismatch": False})
        )
        self.assertEqual(yield_evidence.corner_id(parsed), "tt_125c_1.80v")

    def test_malformed_manifest_raises(self):
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.parse_manifest({"measure": {}})


class DeriveTests(unittest.TestCase):
    def setUp(self):
        self.manifest = yield_evidence.parse_manifest(manifest())

    def test_splits_measured_from_censored_draws(self):
        derived = yield_evidence.derive(
            yield_evidence.parse_record(record(THREE_ROWS)), self.manifest
        )
        self.assertEqual(derived["samples"], [1.5, 2.5])
        self.assertEqual(derived["sample_seeds"], [2, 3])
        self.assertEqual(derived["censored_seeds"], [1])

    def test_locked_trial_without_a_jitter_figure_raises(self):
        rows = [
            (1, 1, "FAIL", True, "-"),
            (2, 2, "FAIL", True, "1.500% (5000 cycles)"),
            (3, 3, "FAIL", True, "2.500% (2500 cycles)"),
        ]
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.derive(
                yield_evidence.parse_record(record(rows)), self.manifest
            )

    def test_no_lock_trial_with_a_jitter_figure_raises(self):
        # Row 9's population is post-lock: a non-converged draw cannot carry a
        # jitter figure, and a record that says otherwise is not gradeable.
        rows = [
            (1, 1, "PASS", False, "1.100% (30 cycles)"),
            (2, 2, "FAIL", True, "1.500% (5000 cycles)"),
            (3, 3, "FAIL", True, "2.500% (2500 cycles)"),
        ]
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.derive(
                yield_evidence.parse_record(record(rows)), self.manifest
            )

    def test_post_lock_population_below_min_cycles_raises(self):
        rows = [
            (1, 1, "PASS", False, "-"),
            (2, 2, "FAIL", True, "1.500% (5000 cycles)"),
            (3, 3, "FAIL", True, "2.500% (19 cycles)"),
        ]
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.derive(
                yield_evidence.parse_record(record(rows)), self.manifest
            )

    def test_seed_list_disagreeing_with_the_manifest_raises(self):
        rows = [
            (1, 7, "PASS", False, "-"),
            (2, 8, "FAIL", True, "1.500% (5000 cycles)"),
            (3, 9, "FAIL", True, "2.500% (2500 cycles)"),
        ]
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.derive(
                yield_evidence.parse_record(record(rows, seed_base=7)), self.manifest
            )

    def test_trial_count_disagreeing_with_the_manifest_raises(self):
        rows = THREE_ROWS[:2]
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.derive(
                yield_evidence.parse_record(record(rows, trials=2)), self.manifest
            )

    def test_fewer_than_two_measurable_draws_raises(self):
        # `klt yield`'s hard floor is 2 usable samples -- below it no
        # confidence interval exists, so there is nothing to write out.
        rows = [
            (1, 1, "PASS", False, "-"),
            (2, 2, "PASS", False, "-"),
            (3, 3, "FAIL", True, "2.500% (2500 cycles)"),
        ]
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.derive(
                yield_evidence.parse_record(record(rows)), self.manifest
            )


def control_manifest(**overrides) -> dict:
    """A minimal negative-control tb.json: the nominal one plus its own
    `negative_control` block, six draws instead of three.
    """
    doc = manifest(**overrides)
    doc["monte_carlo"]["trials"] = overrides.get("monte_carlo.trials", 6)
    doc.setdefault(
        "negative_control",
        {
            "of": "sim/pll-lock-mc",
            "degradation": "loop filter C2 area / 9 (W=L=72 um -> 24 um)",
        },
    )
    return doc


#: Three draws that all lock and all meet the 1.0 % bound -- the shape of the
#: nominal population a control has to separate from.
THREE_PASSING_ROWS = [
    (1, 1, "PASS", True, "0.554% (6426 cycles)"),
    (2, 2, "PASS", True, "0.669% (5949 cycles)"),
    (3, 3, "PASS", True, "0.717% (5077 cycles)"),
]

#: Six draws that all lock and all miss the 1.0 % bound -- what a deliberately
#: degraded variant of the DUT is expected to produce.
SIX_DEGRADED_ROWS = [
    (index, index, "FAIL", True, f"{1.4 + index / 10:.3f}% (5000 cycles)")
    for index in range(1, 7)
]


class NegativeControlTests(unittest.TestCase):
    """The `negative_control` block, and the four refusals that guard it."""

    def setUp(self):
        self.nominal_manifest = yield_evidence.parse_manifest(manifest())
        self.nominal = yield_evidence.parse_record(record(THREE_PASSING_ROWS))
        self.nominal_derived = yield_evidence.derive(self.nominal, self.nominal_manifest)
        self.control_manifest = yield_evidence.parse_control_manifest(control_manifest())
        self.control = yield_evidence.parse_record(record(SIX_DEGRADED_ROWS, trials=6))
        self.control_derived = yield_evidence.derive_control(
            self.control,
            self.control_manifest,
            self.nominal_manifest,
            self.nominal_derived,
        )

    def test_control_block_carries_the_control_draws(self):
        doc = yield_evidence.samples_doc(
            self.nominal,
            self.nominal_manifest,
            self.nominal_derived,
            as_failures=False,
            control=self.control_derived,
        )
        control = doc["measurements"][0]["negative_control"]
        self.assertEqual(len(control["samples"]), 6)
        self.assertEqual(control["errored"], 0)
        self.assertEqual(control["failed_unmeasurable"], 0)
        self.assertIn("C2 area / 9", control["description"])

    def test_no_control_argument_leaves_the_block_out(self):
        doc = yield_evidence.samples_doc(
            self.nominal, self.nominal_manifest, self.nominal_derived, as_failures=False
        )
        self.assertNotIn("negative_control", doc["measurements"][0])

    def test_provenance_names_the_control_record_and_its_degradation(self):
        doc = yield_evidence.samples_doc(
            self.nominal,
            self.nominal_manifest,
            self.nominal_derived,
            as_failures=False,
            control=self.control_derived,
        )
        control = doc["provenance"]["negative_control"]
        self.assertEqual(
            control["source_record"],
            "sim/pll-lock-mc-negative-control/records/20260101-000000-abcdef0.md",
        )
        self.assertEqual(control["degradation"], control_manifest()["negative_control"]["degradation"])
        self.assertEqual(control["seeds_with_a_measurement"], [1, 2, 3, 4, 5, 6])

    def test_manifest_without_a_negative_control_block_raises(self):
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.parse_control_manifest(manifest())

    def test_control_at_a_different_sampling_point_raises(self):
        # A control drawn at another PVT point is not this campaign's control.
        drifted = yield_evidence.parse_control_manifest(
            control_manifest(**{"monte_carlo.temp_c": 27})
        )
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.derive_control(
                self.control, drifted, self.nominal_manifest, self.nominal_derived
            )

    def test_control_run_in_a_different_window_raises(self):
        # "Same testbench, same reducer" is checked, not claimed: a control
        # measured over another window is not comparable with the nominal.
        drifted = yield_evidence.parse_control_manifest(
            control_manifest(**{"measure.tran_stop": "20u"})
        )
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.derive_control(
                self.control, drifted, self.nominal_manifest, self.nominal_derived
            )

    def test_control_that_does_not_separate_from_the_nominal_raises(self):
        # `klt yield` needs the control's own pass rate strictly below the
        # nominal's; a variant whose draws pass as often demonstrates nothing,
        # so the document is refused rather than written and graded.
        passing = [
            (index, index, "PASS", True, "0.600% (5000 cycles)") for index in range(1, 7)
        ]
        with self.assertRaises(yield_evidence.AnalysisError):
            yield_evidence.derive_control(
                yield_evidence.parse_record(record(passing, trials=6)),
                self.control_manifest,
                self.nominal_manifest,
                self.nominal_derived,
            )


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.manifest = yield_evidence.parse_manifest(manifest())
        self.record = yield_evidence.parse_record(record(THREE_ROWS))
        self.derived = yield_evidence.derive(self.record, self.manifest)

    def test_primary_document_excludes_censored_draws(self):
        doc = yield_evidence.samples_doc(
            self.record, self.manifest, self.derived, as_failures=False
        )
        measurement = doc["measurements"][0]
        self.assertEqual(measurement["errored"], 1)
        self.assertEqual(measurement["failed_unmeasurable"], 0)
        self.assertEqual(measurement["limits"], {"max": 1.0})
        self.assertEqual(measurement["source_corners"], ["tt_mm_125c_1.80v"])
        self.assertEqual(measurement["samples"], [1.5, 2.5])
        # No target_yield may be invented: row 9 states a bound, not a target.
        self.assertNotIn("target_yield", measurement["limits"])

    def test_variant_document_charges_censored_draws(self):
        doc = yield_evidence.samples_doc(
            self.record, self.manifest, self.derived, as_failures=True
        )
        measurement = doc["measurements"][0]
        self.assertEqual(measurement["errored"], 0)
        self.assertEqual(measurement["failed_unmeasurable"], 1)
        self.assertEqual(measurement["samples"], [1.5, 2.5])

    def test_spec_limits_carry_the_manifest_bound_and_no_target(self):
        doc = yield_evidence.spec_limits_doc(self.manifest)
        self.assertEqual(doc["confidence"], 0.95)
        self.assertEqual(doc["target_ci_halfwidth"], 0.01)
        limits = doc["measurements"][yield_evidence.MEASUREMENT_NAME]
        self.assertEqual(limits, {"max": 1.0})

    def test_provenance_names_the_record_it_restates(self):
        doc = yield_evidence.samples_doc(
            self.record, self.manifest, self.derived, as_failures=False
        )
        provenance = doc["provenance"]
        self.assertEqual(
            provenance["source_record"],
            "sim/pll-lock-mc/records/20260101-000000-abcdef0.md",
        )
        self.assertEqual(provenance["spec_row"], 9)
        self.assertEqual(provenance["censored_draw_mapping"], "errored")
        self.assertEqual(provenance["seeds_censored_no_lock"], [1])


class CommittedEvidenceTests(unittest.TestCase):
    """The committed documents must still be what the committed record derives.

    This is the same property `yield_evidence.py --check` asserts, run here so
    the repo's own unit suite catches drift without anyone remembering to run
    the script -- the `analysis/` convention's re-verifiability rule, enforced.
    """

    def test_check_mode_passes_against_the_committed_documents(self):
        exit_code = yield_evidence.main([str(RECORD_PATH), "--check"])
        self.assertEqual(exit_code, 0)

    def test_committed_primary_document_matches_the_record(self):
        parsed = yield_evidence.parse_record(RECORD_PATH.read_text())
        manifest_doc = yield_evidence.parse_manifest(
            json.loads(MANIFEST_PATH.read_text())
        )
        derived = yield_evidence.derive(parsed, manifest_doc)
        committed = json.loads((EVIDENCE_DIR / "mc-samples.json").read_text())
        self.assertEqual(
            committed["measurements"][0]["samples"], derived["samples"]
        )
        self.assertEqual(
            committed["measurements"][0]["errored"], len(derived["censored_seeds"])
        )

    def test_check_mode_fails_on_a_drifted_record(self):
        drifted = RECORD_PATH.read_text().replace("1.584%", "1.234%", 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260101-000000-abcdef0.md"
            path.write_text(drifted)
            self.assertEqual(yield_evidence.main([str(path), "--check"]), 1)


class WriteModeTests(unittest.TestCase):
    def test_write_then_check_round_trips(self):
        original = {
            name: (yield_evidence.OUTPUT_DIR / name).read_text()
            for name in (
                "mc-samples.json",
                "mc-samples-censored-as-failures.json",
                "spec-limits.json",
            )
        }
        try:
            self.assertEqual(yield_evidence.main([str(RECORD_PATH), "--write"]), 0)
            self.assertEqual(yield_evidence.main([str(RECORD_PATH), "--check"]), 0)
        finally:
            for name, text in original.items():
                (yield_evidence.OUTPUT_DIR / name).write_text(text)
        for name, text in original.items():
            self.assertEqual((yield_evidence.OUTPUT_DIR / name).read_text(), text)


if __name__ == "__main__":
    unittest.main()
