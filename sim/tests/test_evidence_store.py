"""Issue #370: the evidence writer stores bytes through ``klt artifact put``
and commits only a manifest and a summary. Every failure is fail closed.

Provenance: adapted from 2AMLogic/sg13g2-comparator,
``sim/harness/tests/test_evidence_store.py`` at b46d54af (its PR #319).

Stdlib only. ``klt`` is emulated by an injected ``run``; the broker probe runs
against a throwaway local HTTP server.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

from harness import evidence_store as es  # noqa: E402

REPO = "owner/repo"


def fake_klt(store: dict, *, fail=None, corrupt=False, fail_after=None):
    """Emulate ``klt artifact put FILE --name N --manifest M --format json``."""
    calls = {"n": 0}

    def run(cmd, **kw):
        assert cmd[:3] == ["klt", "artifact", "put"], cmd
        path, name, manifest = cmd[3], cmd[cmd.index("--name") + 1], cmd[cmd.index("--manifest") + 1]
        assert "--broker" not in cmd  # the broker URL never goes in argv
        calls["n"] += 1
        if fail is not None and (fail_after is None or calls["n"] > fail_after):
            err = {"schema_version": 1, "error": {"command": "artifact put",
                                                  "message": "cannot reach the artifact broker",
                                                  "code": fail}}
            return subprocess.CompletedProcess(cmd, 1, "", json.dumps(err))
        data = Path(path).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        store[sha] = data
        shown = "0" * 64 if corrupt else sha
        entry = {"sha256": shown, "size": len(data), "kind": "evidence", "name": name,
                 "producer": {"tool": "klt", "version": "t", "loom.repo": REPO, "commit": None},
                 "uri": f"artifact:evidence/owner__repo/{shown[:2]}/{shown}"}
        p = Path(manifest)
        m = json.loads(p.read_text()) if p.exists() else {"schema_version": 1, "entries": []}
        m["entries"].append(entry)
        p.write_text(json.dumps(m))
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"status": "stored"}), "")

    return run


class Base(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name).resolve()
        self.stage = self.root / "sim/build/b/r1"
        self.stage.mkdir(parents=True)
        (self.stage / "tt.log").write_text("log\n")
        (self.stage / "tt.spice").write_text("* net\n")
        self.summary = self.root / "sim/b/records/r1.md"
        self.files = es.stage_files(self.stage, "sim/b/corners/r1")

    def store(self, run, **kw):
        put = lambda files, root: es.put_files(files, root, run=run)  # noqa: E731
        return es.store_files(self.files, repo_root=self.root, bench="b", rid="r1",
                              summary_text="# record\n", summary_path=self.summary,
                              put=put, **kw)

    def committed(self):
        return sorted(p.relative_to(self.root).as_posix()
                      for p in self.root.rglob("*")
                      if p.is_file() and "sim/build" not in p.as_posix())


class PreflightTests(Base):
    def test_broker_unset_fails_closed(self):
        with self.assertRaisesRegex(es.StoreError, "KLT_ARTIFACT_BROKER"):
            es.preflight(self.root, env={}, which=lambda _: "/bin/klt")

    def test_klt_missing_fails_closed(self):
        with self.assertRaisesRegex(es.StoreError, "not on PATH"):
            es.preflight(self.root, env={es.ENV_BROKER: "http://x"}, which=lambda _: None)

    def test_old_klt_without_artifact_put_fails_closed(self):
        run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2, "", "invalid choice")  # noqa: E731
        with self.assertRaisesRegex(es.StoreError, "no `artifact put` verb"):
            es.preflight(self.root, env={es.ENV_BROKER: "http://x", es.ENV_REPO: REPO},
                         which=lambda _: "/bin/klt", run=run)

    def test_unreachable_broker_fails_closed(self):
        ok = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", "")  # noqa: E731
        with self.assertRaisesRegex(es.StoreError, "unreachable"):
            es.preflight(self.root, env={es.ENV_BROKER: "http://127.0.0.1:1", es.ENV_REPO: REPO},
                         which=lambda _: "/bin/klt", run=ok)

    def _serve(self, status):
        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self.send_response(status)
                self.end_headers()
                self.wfile.write(b'{"error": "forbidden"}')

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_port}"

    def test_broker_probe_accepts_200_and_404_refuses_other(self):
        es.probe_broker(self._serve(200), REPO)
        es.probe_broker(self._serve(404), REPO)
        with self.assertRaisesRegex(es.StoreError, "refused"):
            es.probe_broker(self._serve(403), REPO)

    def test_probe_rejects_credentials_in_url(self):
        with self.assertRaises(es.StoreError):
            es.probe_broker("http://user:pw@127.0.0.1:1", REPO)


class StoreTests(Base):
    def test_success_installs_only_manifest_and_summary(self):
        store = {}
        mpath = self.store(fake_klt(store))
        self.assertEqual(self.committed(), ["manifests/artifacts/b-r1.manifest.json",
                                            "sim/b/records/r1.md"])
        m = json.loads(mpath.read_text())
        self.assertEqual([e["name"] for e in m["entries"]],
                         ["sim/b/corners/r1/tt.log", "sim/b/corners/r1/tt.spice"])
        self.assertIn("klt artifact verify manifests/artifacts/b-r1.manifest.json",
                      self.summary.read_text())
        self.assertEqual(len(store), 2)

    def test_put_failure_commits_nothing_and_keeps_scratch(self):
        with self.assertRaisesRegex(es.StoreError, "broker_unreachable|failed"):
            self.store(fake_klt({}, fail="broker_unreachable"))
        self.assertEqual(self.committed(), [])
        self.assertTrue((self.stage / "tt.log").is_file())

    def test_partial_put_commits_nothing(self):
        with self.assertRaises(es.StoreError):
            self.store(fake_klt({}, fail="broker_unreachable", fail_after=1))
        self.assertEqual(self.committed(), [])

    def test_manifest_that_disagrees_with_local_hash_commits_nothing(self):
        with self.assertRaises(es.StoreError):
            self.store(fake_klt({}, corrupt=True))
        self.assertEqual(self.committed(), [])

    def test_existing_manifest_is_never_overwritten(self):
        self.store(fake_klt({}))
        with self.assertRaisesRegex(es.StoreError, "already exists"):
            self.store(fake_klt({}))

    def test_nothing_staged_or_all_empty_fails_closed(self):
        with self.assertRaises(es.StoreError):
            es.store_files([], repo_root=self.root, bench="b", rid="r1",
                           summary_text="x", summary_path=self.summary)
        (self.stage / "tt.log").write_text("")
        (self.stage / "tt.spice").write_text("")
        with self.assertRaisesRegex(es.StoreError, "every staged file is empty"):
            self.store(fake_klt({}))
        self.assertEqual(self.committed(), [])

    def test_empty_file_is_listed_not_stored(self):
        (self.stage / "tt.log").write_text("")
        mpath = self.store(fake_klt({}))
        self.assertEqual([e["name"] for e in json.loads(mpath.read_text())["entries"]],
                         ["sim/b/corners/r1/tt.spice"])
        self.assertIn("empty, not stored", self.summary.read_text())

    def test_s3_uri_from_an_old_klt_is_refused(self):
        def run(cmd, **kw):
            r = fake_klt({})(cmd, **kw)
            m = Path(cmd[cmd.index("--manifest") + 1])
            d = json.loads(m.read_text())
            for e in d["entries"]:
                e["uri"] = "s3://bucket/" + e["uri"][len("artifact:"):]
            m.write_text(json.dumps(d))
            return r
        with self.assertRaisesRegex(es.StoreError, "uri is not artifact"):
            self.store(run)
        self.assertEqual(self.committed(), [])

    def test_symlink_in_stage_is_refused(self):
        (self.stage / "link").symlink_to(self.stage / "tt.log")
        with self.assertRaisesRegex(es.StoreError, "symlink"):
            es.stage_files(self.stage, "sim/b/corners/r1")


if __name__ == "__main__":
    unittest.main()
