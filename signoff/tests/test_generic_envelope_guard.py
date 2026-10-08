#!/usr/bin/env python3
"""
Unit tests for run-signoff.sh guard 1's `"kind": "generic"` branch (T1 item 8,
issue #224).

`klt signoff` never re-hashes a generic envelope's input, so guard 1 is the
only thing that ties item 8's citation to the live bytes of the report it
names. These tests run the real `run-signoff.sh` against a scratch repository
with a stub `klt` on PATH, so they need no `klt` install and run in
`npm run test`. The stub answers `--version` with the pinned version and
`signoff` by echoing the committed `tier-report.json`, so `--check` passes
exactly when every guard passes, and a guard failure is the only way to get
a non-zero exit.

The last test checks the real repository: the committed envelope, the
manifest's pin and the live `measurements/report.md` must all agree.
"""

import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import unittest

SIGNOFF_DIR = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = SIGNOFF_DIR.parent

STUB_KLT = """#!/usr/bin/env bash
case "${1-}" in
  --version) echo "klt 0.6.0" ;;
  signoff) cat signoff/tier-report.json; exit 3 ;;
  *) echo "stub klt: unexpected arguments: $*" >&2; exit 64 ;;
esac
"""


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class GenericEnvelopeGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)
        (self.root / "signoff" / "evidence").mkdir(parents=True)
        (self.root / "measurements").mkdir()
        (self.root / "bin").mkdir()
        shutil.copy2(SIGNOFF_DIR / "run-signoff.sh", self.root / "signoff" / "run-signoff.sh")
        (self.root / "signoff" / "tier-report.json").write_text('{"stub": true}\n')
        stub = self.root / "bin" / "klt"
        stub.write_text(STUB_KLT)
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

        self.report = self.root / "measurements" / "report.md"
        self.report.write_text("# PLL characterization report\n\n| Row | ... |\n")
        self.pin = sha256(self.report.read_bytes())
        self.envelope = {
            "schema_version": 1,
            "kind": "generic",
            "status": "pass",
            "source": "measurements/report.md",
            "summary": "test envelope",
            "provenance": {
                "input": {
                    "content_hash": self.pin,
                    "path": {"path": "measurements/report.md", "scope": "repo"},
                }
            },
        }
        self._write()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, pin=None):
        (self.root / "signoff" / "evidence" / "characterization-report.json").write_text(
            json.dumps(self.envelope)
        )
        manifest = {
            "block": "test",
            "kind": "mixed-signal",
            "evidence": {
                "8.analog": {
                    "file": "signoff/evidence/characterization-report.json",
                    "content_hash": pin or self.pin,
                }
            },
        }
        (self.root / "signoff" / "block-manifest.json").write_text(json.dumps(manifest))

    def _check(self):
        env = dict(os.environ)
        env["PATH"] = f"{self.root / 'bin'}{os.pathsep}{env.get('PATH', '')}"
        result = subprocess.run(
            ["bash", str(self.root / "signoff" / "run-signoff.sh"), "--check"],
            capture_output=True,
            text=True,
            env=env,
        )
        return result.returncode, result.stderr

    def test_matching_pin_passes(self):
        code, stderr = self._check()
        self.assertEqual(code, 0, stderr)
        self.assertIn("is current", stderr)

    def test_one_byte_appended_fails(self):
        with self.report.open("ab") as handle:
            handle.write(b" ")
        code, stderr = self._check()
        self.assertEqual(code, 1, stderr)
        self.assertIn("item 8.analog: measurements/report.md hashes to", stderr)
        self.assertIn(f"but the manifest pins {self.pin}", stderr)

    def test_one_byte_overwritten_fails(self):
        data = bytearray(self.report.read_bytes())
        data[0] = ord("%")
        self.report.write_bytes(bytes(data))
        code, stderr = self._check()
        self.assertEqual(code, 1, stderr)
        self.assertIn("measurements/report.md hashes to", stderr)

    def test_missing_report_fails(self):
        self.report.unlink()
        code, stderr = self._check()
        self.assertEqual(code, 1, stderr)
        self.assertIn("measurements/report.md is missing", stderr)

    def test_envelope_without_input_path_fails(self):
        # `source` alone is informational (klt never reads it) and is not
        # accepted as the artifact to re-hash.
        del self.envelope["provenance"]["input"]["path"]
        self._write()
        code, stderr = self._check()
        self.assertEqual(code, 1, stderr)
        self.assertIn("names no repo-relative provenance.input.path artifact", stderr)

    def test_plain_string_input_path_is_accepted(self):
        self.envelope["provenance"]["input"]["path"] = "measurements/report.md"
        self._write()
        code, stderr = self._check()
        self.assertEqual(code, 0, stderr)

    def test_non_repo_scope_is_not_accepted(self):
        self.envelope["provenance"]["input"]["path"] = {"path": None, "scope": "external"}
        self._write()
        code, stderr = self._check()
        self.assertEqual(code, 1, stderr)
        self.assertIn("names no repo-relative provenance.input.path artifact", stderr)

    def test_absolute_input_path_fails(self):
        self.envelope["provenance"]["input"]["path"] = str(self.report)
        self._write()
        code, stderr = self._check()
        self.assertEqual(code, 1, stderr)
        self.assertIn("not a repo-relative path", stderr)

    def test_escaping_input_path_fails(self):
        self.envelope["provenance"]["input"]["path"] = {
            "path": "../outside/report.md",
            "scope": "repo",
        }
        self._write()
        code, stderr = self._check()
        self.assertEqual(code, 1, stderr)
        self.assertIn("not a repo-relative path", stderr)

    def test_envelope_claim_disagreeing_with_pin_fails(self):
        self.envelope["provenance"]["input"]["content_hash"] = "sha256:" + "0" * 64
        self._write()
        code, stderr = self._check()
        self.assertEqual(code, 1, stderr)
        self.assertIn("claims provenance.input.content_hash", stderr)

    def test_repinned_manifest_and_envelope_pass_again(self):
        with self.report.open("ab") as handle:
            handle.write(b" ")
        self.pin = sha256(self.report.read_bytes())
        self.envelope["provenance"]["input"]["content_hash"] = self.pin
        self._write()
        code, stderr = self._check()
        self.assertEqual(code, 0, stderr)


class CommittedItem8CitationTests(unittest.TestCase):
    def test_envelope_pin_and_live_report_agree(self):
        manifest = json.loads((SIGNOFF_DIR / "block-manifest.json").read_text())
        entry = manifest["evidence"]["8.analog"]
        envelope = json.loads((REPO_ROOT / entry["file"]).read_text())
        self.assertEqual(envelope["kind"], "generic")
        named = envelope["provenance"]["input"]["path"]
        self.assertEqual(named, {"path": "measurements/report.md", "scope": "repo"})
        live = sha256((REPO_ROOT / named["path"]).read_bytes())
        self.assertEqual(
            entry["content_hash"],
            live,
            "measurements/report.md changed under item 8's pin -- re-read it, "
            "update the envelope summary, then re-pin (signoff/README.md, 'Item 8')",
        )
        self.assertEqual(envelope["provenance"]["input"]["content_hash"], live)

    def test_digital_partition_not_cited(self):
        manifest = json.loads((SIGNOFF_DIR / "block-manifest.json").read_text())
        self.assertNotIn("8", manifest["evidence"])
        self.assertNotIn("8.digital", manifest["evidence"])


if __name__ == "__main__":
    unittest.main()
