#!/usr/bin/env python3
"""Unit tests for signoff/item6_preconditions.py.

No PDK, ngspice, xschem or `klt` required. Three kinds of test live here:

  * **The drift check itself** -- `--check` against the committed
    `signoff/item6-preconditions.md` and this repo's real artifacts. This is the
    gate `npm run check:ci` runs, and the reason a precondition of T1 item 6
    cannot change state without CI saying so.
  * **Both directions of every verdict** -- each row is driven from synthetic
    facts in both its met and its unmet state, so the generated document is
    shown to *report* the repo rather than to hardcode "unmet". This is the
    same discipline `signoff/run-signoff.sh`'s guard 3 was verified with: a
    check that only ever says no is indistinguishable from a broken one.
  * **The refusals** -- an input artifact that is missing, is not the shape the
    script claims, or is a report with more measurements than this document
    grades must raise rather than render a document that quietly drops a fact.

    python3 -m unittest discover -s signoff/tests -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "signoff" / "item6_preconditions.py"
DOCUMENT_PATH = REPO_ROOT / "signoff" / "item6-preconditions.md"

_spec = importlib.util.spec_from_file_location("item6_preconditions", SCRIPT_PATH)
item6 = importlib.util.module_from_spec(_spec)
sys.modules["item6_preconditions"] = item6
_spec.loader.exec_module(item6)  # type: ignore[union-attr]


def facts(**overrides) -> dict:
    """A fully-met fact set, so any single override isolates one row.

    Deliberately *not* this repo's current state: a fixture that started from
    the real (mostly unmet) facts could not tell a correct `met` verdict from a
    row that never fires.
    """
    doc = {
        "source_record": "sim/pll-lock-mc/records/20260101-000000-abcdef0.md",
        "record_id": "20260101-000000-abcdef0",
        "declared_trials": 305,
        "seed_first": 1,
        "seed_last": 305,
        "seed_base": 1,
        "manifest_trials": 305,
        "process_sampling": True,
        "mismatch_sampling": True,
        "measurement_name": "period_jitter_rms_pct",
        "measurable_n": 183,
        "errored": 122,
        "failed_unmeasurable": 0,
        "negative_control": {"verdict": "detected"},
        "sample_size_verdict": "sufficient",
        "sample_size_n": 183,
        "required_n": 183,
        "report_status": "reported",
        "pvt_jitter_declared": True,
        "pvt_jitter_max_frac": 0.01,
        "pvt_records_with_jitter": ["20260101-000000-abcdef0.md"],
        "pvt_records_without_jitter": [],
        "item6_cited": True,
    }
    doc.update(overrides)
    return doc


def verdict_of(row_id: str, **overrides) -> bool:
    rows = {row["id"]: row for row in item6._verdicts(facts(**overrides))}
    return rows[row_id]["met"]


class TestCommittedDocument(unittest.TestCase):
    """The gate: the committed document still matches what the repo derives."""

    def test_check_passes_against_the_repo(self):
        self.assertEqual(item6.main(["--check"]), 0)

    def test_render_reproduces_the_committed_document(self):
        self.assertEqual(item6.render(item6.collect()), DOCUMENT_PATH.read_text())

    def test_check_fails_when_the_document_drifts(self):
        original = item6.OUTPUT
        with tempfile.TemporaryDirectory() as tmp:
            drifted = Path(tmp) / "item6-preconditions.md"
            drifted.write_text("# not what the repo derives\n")
            item6.OUTPUT = drifted
            try:
                self.assertEqual(item6.main(["--check"]), 1)
            finally:
                item6.OUTPUT = original

    def test_check_fails_when_the_document_is_absent(self):
        original = item6.OUTPUT
        with tempfile.TemporaryDirectory() as tmp:
            item6.OUTPUT = Path(tmp) / "gone.md"
            try:
                self.assertEqual(item6.main(["--check"]), 1)
            finally:
                item6.OUTPUT = original

    def test_write_then_check_round_trips(self):
        original = item6.OUTPUT
        with tempfile.TemporaryDirectory() as tmp:
            item6.OUTPUT = Path(tmp) / "item6-preconditions.md"
            try:
                self.assertEqual(item6.main(["--write"]), 0)
                self.assertEqual(item6.main(["--check"]), 0)
            finally:
                item6.OUTPUT = original


class TestCollectedFacts(unittest.TestCase):
    """What `collect()` reads is cross-consistent with the artifacts it names."""

    def setUp(self):
        self.facts = item6.collect()

    def test_source_record_is_the_one_the_sample_set_names(self):
        samples = json.loads((REPO_ROOT / item6.MC_SAMPLES).read_text())
        self.assertEqual(
            self.facts["source_record"], samples["provenance"]["source_record"]
        )
        self.assertTrue((REPO_ROOT / self.facts["source_record"]).is_file())

    def test_seed_and_trial_counts_agree_across_record_and_manifest(self):
        self.assertEqual(self.facts["seed_base"], self.facts["seed_first"])
        self.assertEqual(self.facts["manifest_trials"], self.facts["declared_trials"])
        self.assertEqual(
            self.facts["seed_last"],
            self.facts["seed_first"] + self.facts["declared_trials"] - 1,
        )

    def test_negative_control_and_sample_size_come_from_the_report(self):
        report = json.loads((REPO_ROOT / item6.MC_REPORT).read_text())
        measurement = report["measurements"][0]
        self.assertEqual(self.facts["negative_control"], measurement["negative_control"])
        self.assertEqual(
            self.facts["sample_size_verdict"], measurement["sample_size"]["verdict"]
        )

    def test_every_pvt_record_is_classified_exactly_once(self):
        directory = REPO_ROOT / item6.PVT_RECORDS
        names = sorted(path.name for path in directory.glob("*.md"))
        self.assertEqual(
            sorted(
                self.facts["pvt_records_with_jitter"]
                + self.facts["pvt_records_without_jitter"]
            ),
            names,
        )

    def test_the_document_agrees_with_the_block_manifest(self):
        manifest = json.loads((REPO_ROOT / item6.BLOCK_MANIFEST).read_text())
        cited = item6.ITEM in (manifest.get("evidence") or {})
        self.assertEqual(self.facts["item6_cited"], cited)
        # The claim that has to hold in both directions: the manifest cites item
        # 6 only if nothing is outstanding.
        outstanding = [row for row in item6._verdicts(self.facts) if not row["met"]]
        if cited:
            self.assertEqual(outstanding, [])


class TestVerdictsBothDirections(unittest.TestCase):
    def test_all_rows_met_for_a_fully_met_fact_set(self):
        rows = item6._verdicts(facts())
        self.assertTrue(all(row["met"] for row in rows), rows)

    def test_row_ids_are_the_ones_the_document_promises(self):
        self.assertEqual(
            [row["id"] for row in item6._verdicts(facts())],
            ["1", "2", "3", "4a", "4b", "5"],
        )

    def test_seed_row_unmet_when_the_record_and_manifest_disagree(self):
        self.assertFalse(verdict_of("1", seed_base=7))
        self.assertFalse(verdict_of("1", manifest_trials=304))
        self.assertFalse(verdict_of("1", seed_last=304))

    def test_sample_count_row_unmet_with_no_measurable_draw(self):
        self.assertFalse(verdict_of("2", measurable_n=0))

    def test_negative_control_row_tracks_the_reports_verdict(self):
        self.assertFalse(verdict_of("3", negative_control=None))
        self.assertFalse(verdict_of("3", negative_control={"verdict": "not_detected"}))
        self.assertFalse(verdict_of("3", negative_control="declared in prose"))
        self.assertTrue(verdict_of("3", negative_control={"verdict": "detected"}))

    def test_process_corner_row_unmet_without_process_sampling(self):
        self.assertFalse(verdict_of("4a", process_sampling=False))

    def test_deterministic_axis_row_needs_a_run_not_a_declaration(self):
        self.assertFalse(
            verdict_of(
                "4b",
                pvt_records_with_jitter=[],
                pvt_records_without_jitter=["20260101-000000-abcdef0.md"],
            )
        )
        # Declared but never run is still unmet -- the point of splitting 4.
        self.assertFalse(
            verdict_of(
                "4b",
                pvt_jitter_declared=True,
                pvt_records_with_jitter=[],
                pvt_records_without_jitter=["20260101-000000-abcdef0.md"],
            )
        )

    def test_sizing_row_tracks_the_reports_sample_size_verdict(self):
        self.assertFalse(verdict_of("5", sample_size_verdict="insufficient"))
        self.assertTrue(verdict_of("5", sample_size_verdict="sufficient"))

    def test_rendered_summary_reports_the_outstanding_ids(self):
        document = item6.render(facts(negative_control=None, item6_cited=False))
        self.assertIn("**Verdict: 1 of 6 preconditions outstanding** (3)", document)
        self.assertIn("does not cite item 6", document)

    def test_rendered_summary_flags_a_manifest_that_cites_it_anyway(self):
        document = item6.render(facts(negative_control=None, item6_cited=True))
        self.assertIn("the manifest is the one that is wrong", document)

    def test_rendered_summary_says_so_when_everything_is_met(self):
        document = item6.render(facts())
        self.assertIn("every one of the 6 preconditions is met", document)


class TestTableParsing(unittest.TestCase):
    def test_header_needs_a_separator_row_under_it(self):
        self.assertEqual(
            item6.table_headers("| A | B |\n|---|---|\n| 1 | 2 |\n"), [["A", "B"]]
        )
        self.assertEqual(item6.table_headers("| A | B |\n| 1 | 2 |\n"), [])

    def test_prose_and_indented_tables_are_handled(self):
        markdown = (
            "- **Result**:\n"
            "\n"
            "  | Corner | Verdict | Period jitter |\n"
            "  |---|---|---|\n"
            "  | tt | PASS | 1.584% |\n"
        )
        self.assertEqual(
            item6.table_headers(markdown), [["Corner", "Verdict", "Period jitter"]]
        )

    def test_jitter_column_detection_is_case_insensitive_and_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "with.md").write_text(
                "| Corner | Period Jitter |\n|---|---|\n| tt | 1.0% |\n"
            )
            (directory / "without.md").write_text(
                "| Corner | Duty |\n|---|---|\n| tt | 50% |\n"
            )
            original = item6.REPO_ROOT
            item6.REPO_ROOT = directory.parent
            try:
                carries, without = item6.records_with_a_jitter_column(directory.name)
            finally:
                item6.REPO_ROOT = original
        self.assertEqual(carries, ["with.md"])
        self.assertEqual(without, ["without.md"])

    def test_an_empty_records_directory_is_a_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            original = item6.REPO_ROOT
            item6.REPO_ROOT = directory.parent
            try:
                with self.assertRaises(item6.PreconditionError):
                    item6.records_with_a_jitter_column(directory.name)
            finally:
                item6.REPO_ROOT = original

    def test_a_missing_records_directory_is_a_refusal(self):
        with self.assertRaises(item6.PreconditionError):
            item6.records_with_a_jitter_column("no/such/directory")


class TestRefusals(unittest.TestCase):
    """Every input this script cannot read is an error, never a rendered shrug."""

    def _with_repo(self, files: dict[str, str]):
        """Run `collect()` against a synthetic repo holding only `files`."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        original = item6.REPO_ROOT
        item6.REPO_ROOT = root
        self.addCleanup(lambda: setattr(item6, "REPO_ROOT", original))
        return root

    def _repo_files(self, **overrides) -> dict[str, str]:
        report = {
            "status": "reported",
            "measurements": [
                {
                    "name": "period_jitter_rms_pct",
                    "n": 3,
                    "errored": 2,
                    "failed_unmeasurable": 0,
                    "negative_control": None,
                    "sample_size": {"verdict": "insufficient", "n": 3, "required_n": 183},
                }
            ],
        }
        files = {
            item6.MC_SAMPLES: json.dumps(
                {"provenance": {"source_record": "records/r.md"}}
            ),
            "records/r.md": "- Trials: 5 (seeds 1..5, one card per trial)\n",
            item6.MC_MANIFEST: json.dumps(
                {"monte_carlo": {"seed_base": 1, "trials": 5, "process": True,
                                 "mismatch": True}}
            ),
            item6.MC_REPORT: json.dumps(report),
            item6.PVT_MANIFEST: json.dumps({"measure": {"jitter": {"max_frac": 0.01}}}),
            f"{item6.PVT_RECORDS}/p.md": "| Corner | Duty |\n|---|---|\n| tt | 50% |\n",
            item6.BLOCK_MANIFEST: json.dumps({"evidence": {}}),
        }
        files.update(overrides)
        return files

    def test_the_synthetic_repo_is_itself_readable(self):
        self._with_repo(self._repo_files())
        collected = item6.collect()
        self.assertEqual(collected["declared_trials"], 5)
        self.assertIsNone(collected["negative_control"])
        self.assertEqual(collected["pvt_records_without_jitter"], ["p.md"])

    def test_missing_artifact(self):
        files = self._repo_files()
        del files[item6.MC_REPORT]
        self._with_repo(files)
        with self.assertRaises(item6.PreconditionError):
            item6.collect()

    def test_sample_set_with_no_provenance(self):
        self._with_repo(self._repo_files(**{item6.MC_SAMPLES: json.dumps({})}))
        with self.assertRaises(item6.PreconditionError):
            item6.collect()

    def test_provenance_naming_no_source_record(self):
        self._with_repo(
            self._repo_files(**{item6.MC_SAMPLES: json.dumps({"provenance": {}})})
        )
        with self.assertRaises(item6.PreconditionError):
            item6.collect()

    def test_record_without_a_trials_line(self):
        self._with_repo(self._repo_files(**{"records/r.md": "# a record\n"}))
        with self.assertRaises(item6.PreconditionError):
            item6.collect()

    def test_manifest_without_a_monte_carlo_block(self):
        self._with_repo(self._repo_files(**{item6.MC_MANIFEST: json.dumps({})}))
        with self.assertRaises(item6.PreconditionError):
            item6.collect()

    def test_report_with_more_than_one_measurement(self):
        measurement = {
            "name": "m",
            "n": 3,
            "negative_control": None,
            "sample_size": {"verdict": "insufficient"},
        }
        self._with_repo(
            self._repo_files(
                **{item6.MC_REPORT: json.dumps({"measurements": [measurement] * 2})}
            )
        )
        with self.assertRaises(item6.PreconditionError):
            item6.collect()

    def test_report_that_is_not_a_yield_report(self):
        self._with_repo(
            self._repo_files(
                **{item6.MC_REPORT: json.dumps({"measurements": [{"name": "m"}]})}
            )
        )
        with self.assertRaises(item6.PreconditionError):
            item6.collect()

    def test_unparseable_json(self):
        self._with_repo(self._repo_files(**{item6.BLOCK_MANIFEST: "{not json"}))
        with self.assertRaises(item6.PreconditionError):
            item6.collect()


class TestChecklistDrift(unittest.TestCase):
    """`--tiers-doc` guards the one input that is not in this repo at all."""

    ITEM_6 = (
        "6. **Statistical claims carry Monte Carlo evidence** -- where it\n"
        "   applies, MC runs need a recorded seed, sample count, a deterministic\n"
        "   negative control, and results combined with (not instead of) process\n"
        "   corners (#344).\n"
        "7. **Post-layout verification**\n"
    )

    def _doc(self, body: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "design-evidence-tiers.md"
        path.write_text(body)
        return path

    def test_all_four_phrases_present(self):
        self.assertEqual(item6.assert_checklist_unchanged(self._doc(self.ITEM_6)), [])

    def test_a_dropped_phrase_is_reported(self):
        body = self.ITEM_6.replace("a deterministic\n   negative control, ", "")
        self.assertEqual(
            item6.assert_checklist_unchanged(self._doc(body)),
            ["a deterministic negative control"],
        )

    def test_a_doc_without_item_6_is_a_refusal(self):
        with self.assertRaises(item6.PreconditionError):
            item6.assert_checklist_unchanged(self._doc("7. **Post-layout**\n"))

    def test_main_exits_1_on_checklist_drift(self):
        body = self.ITEM_6.replace("sample count, ", "")
        self.assertEqual(item6.main(["--tiers-doc", str(self._doc(body))]), 1)


if __name__ == "__main__":
    unittest.main()
