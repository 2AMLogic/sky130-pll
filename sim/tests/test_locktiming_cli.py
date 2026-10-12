#!/usr/bin/env python3
"""PDK-free tests for the LOCK timing batch runner (issue #274).

A fake `klt` writes the report and waveform artifacts `klt sim` would return
from the #273 fixture waveforms. No PDK, ngspice, AWS or fleet is touched.

    python3 -m unittest discover -s sim/tests -p 'test_locktiming_cli.py' -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "tests"))

from harness import locktiming as L  # noqa: E402
from harness import locktiming_cli as C  # noqa: E402
from test_locktiming import manifest, waves  # noqa: E402

NETLIST = "* fixture\nV1 VDD GND @VDD@\nV2 in GND pulse(0 1.8 3n 1p 1p 17n 40n)\n.lib /x/sky130.lib.spice tt\n.end\n"


def wave_json(w, drop=(), nonuniform=False, truncate=False):
    names = [n for n in w if n not in drop]
    grid = sorted({x for n in names for x in w[n]["t"]})
    if truncate:
        grid = [x for x in grid if x < 1e-6]

    def at(n, x):
        t, v = w[n]["t"], w[n]["v"]
        import bisect
        i = min(max(bisect.bisect_right(t, x) - 1, 0), len(t) - 2)
        return v[i] + (v[i + 1] - v[i]) * (x - t[i]) / (t[i + 1] - t[i]) if x <= t[-1] else v[-1]

    pts = [[x] + [at(n, x) for n in names] for x in grid]
    if nonuniform:
        pts[2][0] = pts[1][0]
    return {"variables": [{"index": 0, "name": "time"}] + [
        {"index": i + 1, "name": f"v({n})"} for i, n in enumerate(names)], "points": pts}


class FakeKlt:
    def __init__(self, mode=None, bad_proc="ss"):
        self.mode, self.bad_proc, self.calls = mode, bad_proc, []

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.calls.append(cmd)
        if self.mode == "boom":
            return SimpleNamespace(returncode=1, stdout="", stderr="no credentials")
        if self.mode == "capacity" or (self.mode == "capacity_once" and len(self.calls) == 1):
            return SimpleNamespace(returncode=1, stderr="", stdout=json.dumps(
                {"error": {"message": "batch_no_capacity"}}))
        req = json.loads(Path(cmd[2]).read_text())
        out = Path(cmd[cmd.index("-o") + 1])
        if self.mode == "refusal":
            cs = [{"process": p, "temperature_c": t, "status": "error",
                   "diagnostics": [{"code": "batch_runner_version", "message": "skew"}]}
                  for p in req["corners"]["process"] for t in req["corners"]["temperature_c"]]
            return SimpleNamespace(returncode=4, stdout=json.dumps({"corners": cs}), stderr="")
        corners = []
        for p in req["corners"]["process"]:
            for t in req["corners"]["temperature_c"]:
                if {"process": p, "temperature_c": t} in req.get("exclude", []):
                    continue
                d = out / f"{p}_{t:g}"
                d.mkdir(parents=True, exist_ok=True)
                c = {"process": p, "temperature_c": t, "status": "pass", "diagnostics": [],
                     "artifacts": {"waveform": str(d / "w.json")}}
                if self.mode == "corner_error" and p == self.bad_proc:
                    c.update(status="error", diagnostics=[{"code": "timeout", "message": "t/o"}],
                             artifacts={})
                else:
                    kw = {"missing_trace": dict(drop=("tick",)), "nonuniform": dict(nonuniform=True),
                          "truncated": dict(truncate=True)}.get(self.mode, {})
                    (d / "w.json").write_text(json.dumps(wave_json(waves(), **kw)))
                corners.append(c)
        if self.mode == "partial":
            corners = corners[:-3]
        rep = {"corners": corners, "environment": {"engine_version": "46", "remote": {
            "job_id": f"job-{len(self.calls)}", "runner_klt_version": "0.5.0",
            "client_klt_version": "0.7.0"}}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(rep), stderr="")


class Base(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.tmp = Path(self.td.name)
        os.environ["KLT_BATCH_PROVISION_SCRIPT"] = str(self.tmp / "prov.sh")
        (self.tmp / "prov.sh").write_text("")
        self.cands = []
        for i, prod in enumerate(("p1", "p2")):
            m = manifest(prod)
            m["candidate_id"] = f"c{i}"
            (self.tmp / f"m{i}.json").write_text(json.dumps(m))
            (self.tmp / f"n{i}.spice").write_text(NETLIST)
            self.cands.append(f"{self.tmp}/m{i}.json={self.tmp}/n{i}.spice")

    def cli(self, *extra, runner=None, cands=None):
        args = []
        for c in (cands or self.cands):
            args += ["--candidate", c]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = C.main(args + list(extra), runner=runner or FakeKlt(), sleep=lambda s: None)
        return rc, out.getvalue(), err.getvalue()

    def fix(self, *extra, **kw):
        return self.cli("--fixture", "--records-dir", str(self.tmp / "rec"), "--klt", "klt",
                        *extra, **kw)

    def records(self):
        return sorted((self.tmp / "rec").glob("*.json"))


class DryRun(Base):
    def test_nominal_plan_no_job(self):
        k = FakeKlt()
        rc, out, _ = self.cli("--dry-run", runner=k)
        plan = json.loads(out)
        self.assertEqual((rc, k.calls), (0, []))
        self.assertTrue(plan["points_label"].startswith("SUBSET_POINTS"))
        self.assertEqual(len(plan["groups"]), 2)  # 2 candidates x 1 supply
        g = plan["groups"][0]
        self.assertEqual(g["corners"], [["tt", 27.0]])
        self.assertEqual(g["required_traces"], ["in", "raw", "tap", "tick"])
        self.assertEqual(g["request"]["backend"], "batch")
        self.assertEqual(g["request"]["corners"], {"process": ["tt"], "temperature_c": [27.0]})

    def test_full_grid_plan(self):
        _, out, _ = self.cli("--dry-run", "--points", "all")
        plan = json.loads(out)
        self.assertEqual(plan["points_label"], "all")
        self.assertEqual(len(plan["groups"]), 6)  # 2 candidates x 3 supplies
        self.assertEqual(sum(len(g["corners"]) for g in plan["groups"]), 90)
        self.assertEqual(plan["groups"][0]["excluded"], [])

    def test_bad_inputs(self):
        (self.tmp / "n0.spice").write_text("no placeholder\n")
        rc, _, err = self.cli("--dry-run")
        self.assertEqual(rc, 1)
        self.assertIn("@VDD@", err)
        rc, _, err = self.cli("--dry-run", cands=[self.cands[1], self.cands[1]])
        self.assertEqual(rc, 1)


class Run(Base):
    def test_fixture_round_trip_and_provenance(self):
        k = FakeKlt()
        rc, out, err = self.fix("--points", "all", "--required-products", "p1,p2,p3", runner=k)
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(k.calls), 6)
        rec = json.loads(self.records()[0].read_text())
        self.assertEqual(rec["evidence_class"], "fixture")
        self.assertEqual(rec["points_scope"], "all")
        self.assertEqual(rec["handoff"]["scope"], "SUBSET")
        self.assertEqual(rec["handoff"]["products_absent"], ["p3"])
        self.assertFalse(rec["handoff"]["handoff_ready"])
        for c in rec["candidates"]:
            self.assertTrue(c["result"]["complete"], c["result"]["failed"])
            self.assertEqual(len(c["manifest_sha256"]), 64)
            self.assertEqual(c["result"]["verdict"], L.PASS)
        self.assertEqual({j["job_id"] for j in rec["jobs"]}, {f"job-{i}" for i in range(1, 7)})
        self.assertEqual(rec["jobs"][0]["runner_klt_version"], "0.5.0")
        self.assertEqual(rec["jobs"][0]["pdk"]["pdk"], "sky130A")
        # supply is applied to the netlist body, process lib card is klt's
        body = (self.tmp / "rec" / rec["record_id"] / rec["jobs"][0]["group"]
                / "body.spice").read_text()
        self.assertIn("V1 VDD GND 1.62", body)
        self.assertNotIn(".lib", body)
        self.assertIn(".save v(in)", body)

    def test_nominal_is_labelled_subset_and_inconclusive(self):
        rc, _, err = self.fix()
        self.assertEqual(rc, 0, err)
        rec = json.loads(self.records()[0].read_text())
        self.assertEqual(rec["points_scope"], "SUBSET_POINTS:nominal")
        for c in rec["candidates"]:
            self.assertEqual(len(c["result"]["missing"]), 44)
            self.assertEqual(c["result"]["verdict"], L.INCONCLUSIVE)

    def reset(self):
        import shutil
        shutil.rmtree(self.tmp / "rec", ignore_errors=True)

    def failing(self, mode, status, **kw):
        self.reset()
        rc, _, err = self.fix("--points", "all", runner=FakeKlt(mode, **kw))
        self.assertEqual(rc, 0, err)
        rec = json.loads(self.records()[0].read_text())
        for c in rec["candidates"]:
            self.assertFalse(c["result"]["complete"])
            self.assertEqual(c["result"]["verdict"], L.INCONCLUSIVE)
            sts = {r["status"] for r in c["rows"]}
            self.assertIn(status, sts)
        return rec

    def test_submission_failure_no_fallback(self):
        rec = self.failing("boom", L.SIM_FAILED)
        self.assertIn("no JSON report", rec["jobs"][0]["failure"])
        self.assertEqual(rec["evidence_class"], "fixture")

    def test_physical_class_needs_real_jobs(self):
        run = {"jobs": [{"job_id": None, "failure": "x"}]}
        self.assertEqual(C.evidence_class(run, False), "incomplete-not-physical")
        self.assertEqual(C.evidence_class({"jobs": [{"job_id": "j", "failure": None}]}, True),
                         "fixture")
        self.assertEqual(C.evidence_class({"jobs": [{"job_id": "j", "failure": None}]}, False),
                         "physical")

    def test_capacity_retry_then_fail(self):
        k = FakeKlt("capacity_once")
        rc, _, _ = self.fix(runner=k)
        self.assertEqual(rc, 0)
        self.assertEqual(len(k.calls), 3)  # one refusal retried, then 2 groups
        k2 = FakeKlt("capacity")
        self.reset()
        self.fix(runner=k2)
        self.assertGreater(len(k2.calls), 30)
        rec = json.loads(self.records()[0].read_text())
        self.assertIn("capacity", rec["jobs"][0]["failure"])

    def test_version_refusal(self):
        rec = self.failing("refusal", L.SIM_FAILED)
        self.assertTrue(rec["jobs"][0]["failure"].startswith("batch_runner_version"))

    def test_corner_error_and_partial(self):
        rec = self.failing("corner_error", L.SIM_FAILED)
        bad = [r for r in rec["candidates"][0]["rows"] if r["coord"]["process"] == "ss"]
        self.assertTrue(all("timeout" in r["reason"] for r in bad))
        rec = self.failing("partial", L.SIM_FAILED)
        self.assertTrue(any(r["reason"] == "corner missing from the report"
                            for c in rec["candidates"] for r in c["rows"]))

    def test_missing_trace_nonuniform_truncated(self):
        rec = self.failing("missing_trace", L.MALFORMED)
        self.assertTrue(all(r["w_acq_s"] is None for r in rec["candidates"][0]["rows"]
                            if r["status"] != L.OK))

    def test_nonuniform_and_truncated(self):
        self.failing("nonuniform", L.MALFORMED)

    def test_truncated(self):
        self.failing("truncated", L.INSUFFICIENT_SETTLING)


class Retention(Base):
    def test_fixture_requires_records_dir(self):
        rc, _, err = self.cli("--fixture", "--klt", "klt")
        self.assertEqual(rc, 1)
        self.assertIn("records-dir", err)

    def test_append_only_and_supersession(self):
        self.assertEqual(self.fix()[0], 0)
        first = self.records()[0]
        before = first.read_bytes()
        rc, _, err = self.fix()
        self.assertEqual(rc, 1)
        self.assertIn("--supersedes", err)
        rc, _, err = self.fix("--supersedes", "nope")
        self.assertEqual(rc, 1)
        # same-second ids collide: the existing record is never overwritten
        rc, _, err = self.fix("--supersedes", first.stem)
        self.assertEqual(first.read_bytes() if rc else before, before)
        if rc == 0:
            self.assertEqual(len(self.records()), 2)
            rec = json.loads(self.records()[-1].read_text())
            self.assertEqual(rec["supersedes"], first.stem)
        else:
            self.assertIn("append-only", err)
        self.assertEqual(first.read_bytes(), before)

    def test_missing_provisioning_is_refused(self):
        os.environ["KLT_BATCH_PROVISION_SCRIPT"] = str(self.tmp / "absent.sh")
        k = FakeKlt()
        rc, _, err = self.fix(runner=k)
        self.assertEqual((rc, k.calls), (1, []))
        self.assertIn("no local fallback", err)


if __name__ == "__main__":
    unittest.main()
