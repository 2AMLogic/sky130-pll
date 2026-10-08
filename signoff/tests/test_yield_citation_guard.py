#!/usr/bin/env python3
"""
Tests for run-signoff.sh guard 3 (a cited `klt yield` report) after the grader
moved to klayout-tools 0.7.0 (issue #200).

Up to 0.6.0 the grader ignored a yield report's own self-report, so guard 3
refused any report that was undersized or whose control had not fired. 0.7.0
(klayout-tools#2467) grades both itself, so guard 3 is narrowed to the two
things the grader still passes through as `met`:

  * a measurement that declares no `negative_control` at all;
  * a malformed `sample_size` (absent, or a verdict other than
    `sufficient`/`insufficient`).

Two layers:

  * GuardPolicyTests run the real `run-signoff.sh` against a scratch repo with
    a stub `klt` (no install needed, runs in `npm run test`) and check which
    citations the guard lets through to the grader.
  * Release0_7_0RenderTests run the *real* `klt signoff` over the same
    disposable citations and assert the status and reason each renders, so the
    table in run-signoff.sh and signoff/README.md case 4b is measured rather
    than assumed. They are skipped unless `klt` 0.7.0 is on PATH (CI installs it).
"""

import copy
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
YIELD_DIR = REPO_ROOT / "sim" / "pll-lock-mc" / "analysis" / "yield-evidence"

STUB_KLT = """#!/usr/bin/env bash
case "${1-}" in
  --version) echo "klt 0.7.0" ;;
  signoff) cat signoff/tier-report.json; exit 3 ;;
  *) echo "stub klt: unexpected arguments: $*" >&2; exit 64 ;;
esac
"""

# name -> (sample_size.verdict or "<absent>", negative_control)
CASES = {
    "sufficient_detected": ("sufficient", {"verdict": "detected"}),
    "insufficient_declared": ("insufficient", {"verdict": "detected"}),
    "sufficient_not_detected": ("sufficient", {"verdict": "not_detected"}),
    "insufficient_not_detected": ("insufficient", {"verdict": "not_detected"}),
    "insufficient_undeclared": ("insufficient", None),
    "sufficient_undeclared": ("sufficient", None),
    "sufficient_control_not_a_block": ("sufficient", "detected"),
    "size_absent": ("<absent>", {"verdict": "detected"}),
    "size_bogus": ("bogus", {"verdict": "detected"}),
}


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_case(root: pathlib.Path, name: str):
    """Write report + sample document + manifest for one case under `root`."""
    verdict, control = CASES[name]
    report = json.loads((YIELD_DIR / "klt-yield-report.json").read_text())
    case_dir = root / name
    case_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(YIELD_DIR / "mc-samples.json", case_dir / "mc-samples.json")
    report["samples"] = f"{name}/mc-samples.json"
    measurement = report["measurements"][0]
    if verdict == "<absent>":
        del measurement["sample_size"]
    else:
        measurement["sample_size"] = copy.deepcopy(measurement["sample_size"])
        measurement["sample_size"]["verdict"] = verdict
    measurement["negative_control"] = control
    (case_dir / "report.json").write_text(json.dumps(report))
    pin = sha256((case_dir / "mc-samples.json").read_bytes())
    manifest = {
        "block": "test",
        "kind": "mixed-signal",
        "evidence": {"6": {"file": f"{name}/report.json", "content_hash": pin}},
    }
    manifest_path = root / f"{name}.manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


class GuardPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)
        (self.root / "signoff").mkdir()
        (self.root / "bin").mkdir()
        shutil.copy2(SIGNOFF_DIR / "run-signoff.sh", self.root / "signoff" / "run-signoff.sh")
        (self.root / "signoff" / "tier-report.json").write_text('{"stub": true}\n')
        stub = self.root / "bin" / "klt"
        stub.write_text(STUB_KLT)
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _check(self, name):
        manifest = build_case(self.root, name)
        shutil.copy2(manifest, self.root / "signoff" / "block-manifest.json")
        env = dict(os.environ)
        env["PATH"] = f"{self.root / 'bin'}{os.pathsep}{env.get('PATH', '')}"
        result = subprocess.run(
            ["bash", str(self.root / "signoff" / "run-signoff.sh"), "--check"],
            capture_output=True,
            text=True,
            env=env,
        )
        return result.returncode, result.stderr

    def assertPasses(self, name):
        code, stderr = self._check(name)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("does not support the row", stderr)

    def assertRefused(self, name, needle):
        code, stderr = self._check(name)
        self.assertEqual(code, 1, stderr)
        self.assertIn("does not support the row it would grade", stderr)
        self.assertIn(needle, stderr)

    # Handed to the grader (which renders an honest `unmet` or `met`).
    def test_sufficient_detected_passes(self):
        self.assertPasses("sufficient_detected")

    def test_undersized_sample_is_left_to_the_grader(self):
        self.assertPasses("insufficient_declared")

    def test_declared_control_that_did_not_fire_is_left_to_the_grader(self):
        self.assertPasses("sufficient_not_detected")
        self.assertPasses("insufficient_not_detected")

    # Still refused here: the grader passes these through as `met`.
    def test_undeclared_control_is_refused_even_when_sized(self):
        self.assertRefused("sufficient_undeclared", "no negative_control is declared")

    def test_undeclared_control_is_refused_when_undersized(self):
        self.assertRefused("insufficient_undeclared", "no negative_control is declared")

    def test_control_that_is_not_a_block_is_refused(self):
        self.assertRefused("sufficient_control_not_a_block", "no negative_control is declared")

    def test_absent_sample_size_is_refused(self):
        self.assertRefused("size_absent", "sample_size.verdict is None")

    def test_unknown_sample_size_verdict_is_refused(self):
        self.assertRefused("size_bogus", "sample_size.verdict is 'bogus'")

    def test_committed_report_is_still_refused(self):
        """The real campaign report declares no control, so it is still not citable."""
        code, stderr = self._check_committed_report()
        self.assertEqual(code, 1, stderr)
        self.assertIn("no negative_control is declared", stderr)
        self.assertNotIn("sample_size.verdict is 'insufficient'", stderr)

    def _check_committed_report(self):
        dest = self.root / "sim" / "pll-lock-mc" / "analysis" / "yield-evidence"
        dest.mkdir(parents=True)
        for name in ("klt-yield-report.json", "mc-samples.json"):
            shutil.copy2(YIELD_DIR / name, dest / name)
        pin = sha256((dest / "mc-samples.json").read_bytes())
        manifest = {
            "block": "test",
            "kind": "mixed-signal",
            "evidence": {
                "6": {
                    "file": "sim/pll-lock-mc/analysis/yield-evidence/klt-yield-report.json",
                    "content_hash": pin,
                }
            },
        }
        (self.root / "signoff" / "block-manifest.json").write_text(json.dumps(manifest))
        env = dict(os.environ)
        env["PATH"] = f"{self.root / 'bin'}{os.pathsep}{env.get('PATH', '')}"
        result = subprocess.run(
            ["bash", str(self.root / "signoff" / "run-signoff.sh"), "--check"],
            capture_output=True,
            text=True,
            env=env,
        )
        return result.returncode, result.stderr


def _real_klt_is_0_7_0():
    try:
        out = subprocess.run(["klt", "--version"], capture_output=True, text=True)
    except OSError:
        return False
    return out.returncode == 0 and "0.7.0" in out.stdout


@unittest.skipUnless(_real_klt_is_0_7_0(), "needs klt 0.7.0 on PATH")
class Release0_7_0RenderTests(unittest.TestCase):
    """What the real 0.7.0 grader renders for item 6 (analog column)."""

    EXPECTED = {
        "sufficient_detected": ("met", None, "detected"),
        "insufficient_declared": ("unmet", "undersized_sample", None),
        "sufficient_not_detected": ("unmet", "negative_control_not_detected", None),
        "insufficient_not_detected": ("unmet", "undersized_sample", None),
        "insufficient_undeclared": ("unmet", "undersized_sample", None),
        # Guard 3 exists for these two: the grader renders them `met`.
        "sufficient_undeclared": ("met", None, "not_declared"),
        "size_absent": ("met", None, "detected"),
    }

    def test_rendered_status_and_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for name, (status, reason, control) in self.EXPECTED.items():
                manifest = build_case(root, name)
                result = subprocess.run(
                    ["klt", "signoff", "--manifest", manifest.name, "--format", "json"],
                    capture_output=True,
                    text=True,
                    cwd=root,
                )
                self.assertIn(result.returncode, (0, 3), result.stderr)
                rows = [
                    item
                    for item in json.loads(result.stdout)["items"]
                    if item["id"] == 6 and item["partition"] == "analog"
                ]
                self.assertEqual(len(rows), 1, name)
                row = rows[0]
                self.assertEqual(row["status"], status, name)
                self.assertEqual(row.get("reason"), reason, name)
                if control is not None:
                    campaign = row["citation"]["yield_campaign"]
                    self.assertEqual(campaign["negative_control"], control, name)


if __name__ == "__main__":
    unittest.main()
