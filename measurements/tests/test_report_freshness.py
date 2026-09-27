#!/usr/bin/env python3
"""Regression guard: the committed `measurements/report.md` matches what
`measurements/aggregate.py` produces from the real, checked-in evidence tree
right now (issue #22).

`measurements/README.md` already says report.md is a *derived* artifact that
must be regenerated and recommitted whenever new evidence lands -- but until
this test existed, nothing enforced that: a new `sim/*/records/*.md` (or a
newly-ratified spec row) could land on `main` for days without anyone
re-running `python3 measurements/aggregate.py --out measurements/report.md`,
leaving the checked-in report silently understating what evidence actually
exists (observed in practice: issue #22's own re-curation history shows
`measurements/report.md` sitting three days stale after the row-9 Monte Carlo
evidence record that this exact report exists to surface).

This test does not re-derive whether any evidence is "enough" -- that
judgment call belongs to the issue thread and a human/agent's own reading of
`spec/target-spec.md`. It only asserts that the committed file is what the
aggregator would emit today, so drift is caught the same push it lands on
rather than discovered by hand later.

No PDK, ngspice, xschem, or klt required.

    python3 -m unittest discover -s measurements/tests -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

MEASUREMENTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MEASUREMENTS_DIR))

import aggregate  # noqa: E402

REPO_ROOT = MEASUREMENTS_DIR.parent
REPORT_PATH = MEASUREMENTS_DIR / "report.md"

# The `Generated: <timestamp> by ...` line is expected to differ on every
# regeneration -- it is not itself evidence of drift, so it is normalized out
# of both sides before comparing.
_GENERATED_LINE_RE = re.compile(r"^Generated: .*$", re.MULTILINE)


def _normalize(text: str) -> str:
    return _GENERATED_LINE_RE.sub("Generated: <normalized>", text, count=1)


class ReportFreshnessTests(unittest.TestCase):
    def test_committed_report_matches_a_fresh_regeneration(self):
        self.assertTrue(
            REPORT_PATH.is_file(),
            f"{REPORT_PATH} does not exist -- run `python3 measurements/"
            "aggregate.py --out measurements/report.md`",
        )
        spec_rows = aggregate.parse_spec_rows(REPO_ROOT / "spec" / "target-spec.md")
        records = aggregate.discover_evidence(REPO_ROOT)
        data = aggregate.build_report(spec_rows, records, repo_root=REPO_ROOT)
        fresh = _normalize(aggregate.render_markdown(data))
        committed = _normalize(REPORT_PATH.read_text())
        self.assertEqual(
            committed,
            fresh,
            f"{REPORT_PATH} is stale -- new or changed evidence exists that "
            "it does not reflect. Re-run `python3 measurements/aggregate.py "
            "--out measurements/report.md` and commit the result "
            "(measurements/README.md).",
        )


if __name__ == "__main__":
    unittest.main()
