#!/usr/bin/env python3
"""Unit tests for render_common.git_provenance -- the layout record's
repo-state resolution.

The shared dirty classification itself lives in scripts/git_status.py and is
tested directly by scripts/tests/test_git_status.py. What is layout-specific
-- and what only this test can pin -- is the plumbing `git_provenance` wraps
around it: `out_dir` becoming the repo-relative report prefix with a
trailing slash, the load-bearing `--untracked-files=all` status flag (see
the comment in render_common.py), and the `(sha, branch, dirty)` triple the
renderers emit. `run_git` is mocked, so no real repo state is needed.

`layout/bin/` is not an importable package, so the module is loaded by path.

    python3 -m unittest discover -s layout/tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.test_support import load_module  # noqa: E402

RENDER_COMMON_PY = Path(__file__).resolve().parents[1] / "bin" / "render_common.py"

# Deliberately not registered in sys.modules: loaded by file path only.
render_common = load_module("render_common", RENDER_COMMON_PY, register=False)

SHA = "0123456789abcdef0123456789abcdef01234567"
BRANCH = "feature/issue-448"
REPORT_DIR = "layout/trivial-cell/reports/20260101-000000-abc1234"


class GitProvenanceTests(unittest.TestCase):
    def provenance(self, status_text: str):
        """Run git_provenance against a throwaway repo/out_dir layout with
        run_git mocked to serve the canned sha/branch and the given status
        text; return the result triple plus the mock for call assertions."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo_root = Path(tmp.name).resolve()
        out_dir = repo_root / REPORT_DIR
        out_dir.mkdir(parents=True)
        with mock.patch.object(render_common, "run_git") as run_git:
            run_git.side_effect = [SHA, BRANCH, status_text]
            sha, branch, dirty = render_common.git_provenance(repo_root, out_dir)
        return sha, branch, dirty, run_git

    def test_resolves_sha_branch_and_pins_the_status_invocation(self):
        sha, branch, dirty, run_git = self.provenance("")
        self.assertEqual((sha, branch, dirty), (SHA, BRANCH, False))
        self.assertEqual(
            [call.args[1:] for call in run_git.call_args_list],
            [
                ("rev-parse", "HEAD"),
                ("rev-parse", "--abbrev-ref", "HEAD"),
                # --untracked-files=all is load-bearing: without it git
                # collapses a wholly untracked tree to its parent, which no
                # per-record prefix can match, so every record reads dirty.
                ("status", "--porcelain", "--untracked-files=all"),
            ],
        )

    def test_this_runs_report_dir_does_not_read_dirty(self):
        # Pins the report_rel derivation: out_dir (an absolute path under
        # the repo) must become the repo-relative prefix with its trailing
        # slash, so the run's own new files are ignored.
        status = (
            f"?? {REPORT_DIR}/drc.json\n"
            f"?? {REPORT_DIR}/record.md\n"
            f"?? {REPORT_DIR}/trivial_mos_array.gds\n"
        )
        _, _, dirty, _ = self.provenance(status)
        self.assertFalse(dirty)

    def test_a_sibling_report_directory_still_reads_dirty(self):
        # The prefix must not be broader than this run's own directory: a
        # sibling record from an earlier run is not this run's output.
        status = "?? layout/trivial-cell/reports/20251231-235959-def5678/record.md\n"
        _, _, dirty, _ = self.provenance(status)
        self.assertTrue(dirty)

    def test_a_similarly_named_directory_still_reads_dirty(self):
        # The trailing slash in the derived prefix is load-bearing: without
        # it, "...abc1234suffix/" would startswith-match "...abc1234" and a
        # wholly different directory would be silently ignored.
        status = f"?? {REPORT_DIR}suffix/record.md\n"
        _, _, dirty, _ = self.provenance(status)
        self.assertTrue(dirty)

    def test_a_modified_flow_script_reads_dirty(self):
        _, _, dirty, _ = self.provenance(" M layout/bin/run-trivial-cell-flow.sh\n")
        self.assertTrue(dirty)


if __name__ == "__main__":
    unittest.main()
