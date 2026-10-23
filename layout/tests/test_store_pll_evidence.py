"""store_pll_evidence.py fails closed without an artifact store (issue #371)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / "bin"
spec = importlib.util.spec_from_file_location("store_pll_evidence", BIN / "store_pll_evidence.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FailClosedTests(unittest.TestCase):
    def run_main(self, argv):
        err = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != "KLT_ARTIFACT_BROKER"}
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stderr(err):
            return mod.main(argv), err.getvalue()

    def test_preflight_without_broker_fails(self):
        rc, err = self.run_main(["preflight"])
        self.assertEqual(rc, 1)
        self.assertIn("KLT_ARTIFACT_BROKER", err)

    def test_store_without_broker_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td)
            (stage / "record.md").write_text("# record\n")
            (stage / "pll_top.gds").write_bytes(b"gds")
            before = sorted(p.name for p in stage.iterdir())
            rc, err = self.run_main(["store", "--stage-dir", td, "--record-id", "r-1"])
            self.assertEqual(rc, 1)
            self.assertIn("nothing committed", err)
            self.assertEqual(sorted(p.name for p in stage.iterdir()), before)
        repo = mod.REPO_ROOT
        self.assertFalse((repo / "manifests/artifacts/layout-pll-r-1.manifest.json").exists())
        self.assertFalse((repo / "layout/pll/reports/r-1").exists())


if __name__ == "__main__":
    unittest.main()
