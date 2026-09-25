#!/usr/bin/env python3
"""Unit tests for sim/pll-lock-mc/analysis/negative_control_reachability.py.

No PDK, ngspice, xschem or `klt` required -- every `klt yield` output the script
reads is committed evidence, exactly like the campaign's own report.

Three kinds of case here:

1. **Drift detection against the committed evidence.** The generated document
   and the six probe input documents are re-derived and compared, which is the
   check `sim/README.md` requires of an `analysis/` directory.
2. **The committed probe reports still say what the document claims they say.**
   A regenerated `klt yield` output that changed a verdict would otherwise turn
   the document into a confident restatement of a different experiment.
3. **The reachability rule reports the repo rather than hardcoding a verdict.**
   The same objection `signoff/item6_preconditions.py` had to answer: the
   predicate is driven from both sides, so a future campaign that actually
   meets row 9 flips it to reachable instead of silently reading `unreachable`
   forever.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS = REPO_ROOT / "sim" / "pll-lock-mc" / "analysis"
SCRIPT_PATH = ANALYSIS / "negative_control_reachability.py"
OUTPUT = ANALYSIS / "negative-control" / "reachability.md"
PROBE_DIR = ANALYSIS / "negative-control" / "probes"
PROBE_REPORT_DIR = ANALYSIS / "negative-control" / "reports"
ENV_SCRIPT = ANALYSIS / "klt-yield-env.sh"

# sim/pll-lock-mc/analysis/ is not an importable package (hyphens in the slug),
# so the module is loaded from its path -- the same pattern
# sim/tests/test_jitter_floor.py and sim/tests/test_yield_evidence.py use.
_spec = importlib.util.spec_from_file_location("negative_control_reachability", SCRIPT_PATH)
ncr = importlib.util.module_from_spec(_spec)
sys.modules["negative_control_reachability"] = ncr
_spec.loader.exec_module(ncr)  # type: ignore[union-attr]


class CommittedEvidenceTests(unittest.TestCase):
    def test_the_committed_document_and_probes_are_current(self):
        self.assertTrue(OUTPUT.is_file(), f"{OUTPUT} is missing")
        self.assertEqual(ncr.main(["--check"]), 0)

    def test_every_probe_has_a_committed_input_and_a_committed_klt_output(self):
        for probe in ncr.PROBES:
            with self.subTest(probe=probe[0]):
                self.assertTrue((PROBE_DIR / f"{probe[0]}.json").is_file())
                self.assertTrue((PROBE_REPORT_DIR / f"{probe[0]}.json").is_file())

    def test_the_reproduction_script_is_committed_beside_the_artifacts(self):
        # `klt yield` is unreachable from this repo's pin (klayout-tools#2466),
        # so the recipe that regenerates these outputs is the only thing
        # standing between them and an unreproducible artifact.
        self.assertTrue(ENV_SCRIPT.is_file(), f"{ENV_SCRIPT} is missing")

    def test_the_committed_probe_reports_carry_the_verdicts_claimed(self):
        for pid, _q, passing, failing, errored, nc_n, expected in ncr.PROBES:
            with self.subTest(probe=pid):
                m = json.loads((PROBE_REPORT_DIR / f"{pid}.json").read_text())
                m = m["measurements"][0]
                self.assertEqual(m["negative_control"]["verdict"], expected)
                self.assertEqual(m["n"], passing + failing)
                self.assertEqual(m["errored"], errored)
                self.assertEqual(m["negative_control"]["failed_unmeasurable"], nc_n)

    def test_the_probe_set_produces_both_verdicts(self):
        # Without a probe that reports `detected`, every `not_detected` row
        # could equally be a broken probe harness.
        verdicts = {p[6] for p in ncr.PROBES}
        self.assertEqual(verdicts, {"detected", "not_detected"})

    def test_the_committed_campaign_still_reports_a_zero_yield_on_both_mappings(self):
        for report in (ncr.NOMINAL_REPORT, ncr.CENSORED_REPORT):
            with self.subTest(report=report.name):
                empirical = json.loads(report.read_text())["measurements"][0]["yield"][
                    "empirical"
                ]
                self.assertEqual(empirical["estimate"], 0.0)
                self.assertEqual(empirical["confidence_interval"]["low"], 0.0)


class ReachabilityRuleTests(unittest.TestCase):
    """Driven from both sides, so the predicate reports rather than asserts."""

    def test_a_zero_yield_nominal_is_unreachable(self):
        ok, why = ncr.reachability(0.0, 0.0)
        self.assertFalse(ok)
        self.assertIn("unreachable", why)

    def test_a_nonzero_estimate_with_a_zero_lower_bound_is_still_unreachable(self):
        # The interval's lower bound is the binding half: a control's upper
        # bound cannot be below zero either.
        ok, _ = ncr.reachability(0.005464, 0.0)
        self.assertFalse(ok)

    def test_a_nominal_whose_interval_clears_zero_is_reachable(self):
        ok, why = ncr.reachability(0.049180, 0.022732)
        self.assertTrue(ok)
        self.assertIn("0.022732", why)

    def test_the_document_states_the_verdict_the_rule_derives(self):
        nominal = json.loads(ncr.NOMINAL_REPORT.read_text())
        empirical = nominal["measurements"][0]["yield"]["empirical"]
        ok, _ = ncr.reachability(
            empirical["estimate"], empirical["confidence_interval"]["low"]
        )
        expected = "REACHABLE" if ok else "UNREACHABLE"
        self.assertIn(f"`detected` is {expected} over this campaign", OUTPUT.read_text())


class ProbeDocumentTests(unittest.TestCase):
    def test_a_probe_document_uses_only_the_two_declared_sample_values(self):
        for probe in ncr.PROBES:
            with self.subTest(probe=probe[0]):
                doc = ncr.probe_document(probe)
                samples = set(doc["measurements"][0]["samples"])
                self.assertLessEqual(samples, {ncr.PASSING, ncr.FAILING})

    def test_every_control_is_the_strongest_degradation_the_schema_expresses(self):
        for probe in ncr.PROBES:
            with self.subTest(probe=probe[0]):
                nc = ncr.probe_document(probe)["measurements"][0]["negative_control"]
                self.assertEqual(nc["samples"], [])
                self.assertGreater(nc["failed_unmeasurable"], 0)

    def test_the_limit_every_probe_is_graded_against_is_ratified_row_9s(self):
        for probe in ncr.PROBES:
            with self.subTest(probe=probe[0]):
                limits = ncr.probe_document(probe)["measurements"][0]["limits"]
                self.assertEqual(limits, {"max": 1.0})

    def test_a_probe_report_over_a_different_population_is_refused(self):
        # The guard that keeps the document from describing one experiment
        # while quoting another's numbers.
        original = ncr.PROBES
        try:
            pid, q, passing, failing, errored, nc_n, verdict = original[0]
            ncr.PROBES = ((pid, q, passing + 1, failing, errored, nc_n, verdict),) + original[1:]
            self.assertEqual(ncr.main(["--check"]), 1)
        finally:
            ncr.PROBES = original


if __name__ == "__main__":
    unittest.main()
