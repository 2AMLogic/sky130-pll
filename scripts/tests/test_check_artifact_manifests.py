"""Tests for scripts/check_artifact_manifests.py (issue #370).

Runs ``check`` against throwaway git repositories. Stdlib only; no klt, no
broker.
"""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "check_artifact_manifests", ROOT / "scripts" / "check_artifact_manifests.py")
chk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chk)

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}
DATA = b"stored bytes\n"
SHA = hashlib.sha256(DATA).hexdigest()


def entry(data=DATA, name="sim/b/corners/r1/tt.log"):
    sha = hashlib.sha256(data).hexdigest()
    return {"sha256": sha, "size": len(data), "kind": "evidence", "name": name,
            "producer": {"tool": "klt", "version": "0.7.1", "loom.repo": "o/r", "commit": None},
            "uri": f"artifact:evidence/o__r/{sha[:2]}/{sha}"}


def manifest(*entries):
    return {"schema_version": 1, "entries": list(entries)}


class CheckTests(unittest.TestCase):
    def repo(self, files):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        for rel, content in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content if isinstance(content, bytes) else content.encode())
        for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "x"]):
            subprocess.run(["git", "-C", str(root), *cmd], check=True, env=ENV,
                           stdout=subprocess.DEVNULL)
        return str(root)

    def run_check(self, files):
        repo = self.repo(files)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = chk.main(["--repo", repo, "--tree", "HEAD"])
        return rc, err.getvalue()

    def mfile(self, m, name="b-r1"):
        return {f"manifests/artifacts/{name}.manifest.json": json.dumps(m)}

    def test_valid_manifest_passes(self):
        rc, err = self.run_check(self.mfile(manifest(entry())))
        self.assertEqual((rc, err), (0, ""))

    def test_no_manifests_passes(self):
        self.assertEqual(self.run_check({"README.md": "x"})[0], 0)

    def test_s3_uri_is_rejected(self):
        e = entry()
        e["uri"] = "s3://bucket/" + e["uri"][len("artifact:"):]
        rc, err = self.run_check(self.mfile(manifest(e)))
        self.assertEqual(rc, 1)
        self.assertIn("artifact:<key>", err)

    def test_uri_key_must_end_in_sha256(self):
        e = entry()
        e["uri"] = "artifact:evidence/o__r/00/" + "0" * 64
        self.assertEqual(self.run_check(self.mfile(manifest(e)))[0], 1)

    def test_tracked_file_matching_a_stored_sha256_fails(self):
        files = self.mfile(manifest(entry()))
        files["sim/b/corners/r2/copy.log"] = DATA  # same bytes, different path
        rc, err = self.run_check(files)
        self.assertEqual(rc, 1)
        self.assertIn("sim/b/corners/r2/copy.log", err)

    def test_layout_names_are_valid(self):
        name = "layout/pll/reports/r1/pll_top.gds"
        self.assertEqual(self.run_check(self.mfile(manifest(entry(name=name))))[0], 0)

    def test_layout_bytes_committed_under_reports_fail(self):
        name = "layout/pll/reports/r1/pll_top.gds"
        files = self.mfile(manifest(entry(name=name)))
        files[name] = DATA
        rc, err = self.run_check(files)
        self.assertEqual(rc, 1)
        self.assertIn(name, err)

    def test_same_size_different_bytes_is_not_a_match(self):
        files = self.mfile(manifest(entry()))
        files["sim/b/other.log"] = b"X" * len(DATA)
        self.assertEqual(self.run_check(files)[0], 0)

    def test_bad_names_and_duplicates_fail(self):
        for name in ("/abs/x", "sim/../x", "other/x", "sim/a//b", "sim\\x"):
            with self.subTest(name=name):
                self.assertEqual(self.run_check(self.mfile(manifest(entry(name=name))))[0], 1)
        self.assertEqual(self.run_check(self.mfile(manifest(entry(), entry())))[0], 1)

    def test_schema_problems_fail(self):
        bad = []
        e = entry(); e["extra"] = 1; bad.append(manifest(e))
        e = entry(); e["kind"] = "log"; bad.append(manifest(e))
        e = entry(); e["size"] = 0; bad.append(manifest(e))
        e = entry(); del e["producer"]; bad.append(manifest(e))
        bad.append({"schema_version": 2, "entries": [entry()]})
        bad.append(manifest())
        for m in bad:
            with self.subTest(m=copy.deepcopy(m)):
                self.assertEqual(self.run_check(self.mfile(m))[0], 1)

    def test_stray_file_in_manifest_dir_fails(self):
        rc, _ = self.run_check({"manifests/artifacts/notes.txt": "x"})
        self.assertEqual(rc, 1)

    def test_invalid_json_fails(self):
        rc, err = self.run_check({"manifests/artifacts/b-r1.manifest.json": "{"})
        self.assertEqual(rc, 1)
        self.assertIn("not valid JSON", err)

    def test_bad_revision_is_a_tool_error(self):
        repo = self.repo({"a": "x"})
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(chk.main(["--repo", repo, "--tree", "nope"]), 2)
            self.assertEqual(chk.main(["--repo", repo, "--tree=--x"]), 2)


class RepoTests(unittest.TestCase):
    def test_this_repository_passes(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(chk.main(["--repo", str(ROOT), "--tree", "HEAD"]), 0)


if __name__ == "__main__":
    unittest.main()
