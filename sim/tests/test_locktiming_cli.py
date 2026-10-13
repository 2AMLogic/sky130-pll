#!/usr/bin/env python3
"""PDK-free tests for the LOCK timing batch runner (issue #274). A fake `klt`
writes the report and waveform artifacts `klt sim` returns, from the #273
fixture waveforms; no PDK, ngspice or fleet is touched.

    python3 -m unittest discover -s sim/tests -p 'test_locktiming_cli.py' -v
"""
import bisect
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from harness import locktiming as L  # noqa: E402
from harness import locktiming_cli as C  # noqa: E402
from test_locktiming import manifest, waves  # noqa: E402

NETLIST = "* f\nV1 VDD GND @VDD@\n.lib /x/sky130.lib.spice tt\n.end\n"


def wave_json(w, drop=(), nonuniform=False, truncate=False):
    """The #273 traces resampled onto one klt-style time column."""
    names = [n for n in w if n not in drop]
    grid = sorted({x for n in names for x in w[n]["t"] if not truncate or x < 1e-6})

    def at(n, x):
        t, v = w[n]["t"], w[n]["v"]
        i = min(max(bisect.bisect_right(t, x) - 1, 0), len(t) - 2)
        return v[i] + (v[i + 1] - v[i]) * (x - t[i]) / (t[i + 1] - t[i]) if x <= t[-1] else v[-1]
    pts = [[x] + [at(n, x) for n in names] for x in grid]
    if nonuniform:
        pts[2][0] = pts[1][0]
    return {"variables": [{"name": "time"}] + [{"name": f"v({n})"} for n in names], "points": pts}


class FakeKlt:
    def __init__(self, mode=None):
        self.mode, self.calls = mode, []

    def __call__(self, cmd, **_):
        self.calls.append(cmd)
        if self.mode == "boom":
            return NS(returncode=1, stdout="", stderr="no credentials")
        if self.mode == "capacity" or (self.mode == "capacity_once" and len(self.calls) == 1):
            return NS(returncode=1, stderr="", stdout='{"error": {"message": "batch_no_capacity"}}')
        req, out = json.loads(Path(cmd[2]).read_text()), Path(cmd[cmd.index("-o") + 1])
        kw = {"missing_trace": dict(drop=("tick",)), "nonuniform": dict(nonuniform=True),
              "truncated": dict(truncate=True)}.get(self.mode, {})
        corners = []
        for p in req["corners"]["process"]:
            for t in req["corners"]["temperature_c"]:
                d = out / f"{p}_{t:g}"
                d.mkdir(parents=True, exist_ok=True)
                c = {"process": p, "temperature_c": t, "status": "pass",
                     "artifacts": {"waveform": str(d / "w.json")}, "diagnostics": [
                         {"code": "batch_runner_version", "message": "skew"}] * (
                         self.mode == "refusal")}
                if self.mode == "corner_error" and p == "ss":
                    c.update(status="error", diagnostics=[{"code": "timeout", "message": "t/o"}])
                (d / "w.json").write_text(json.dumps(wave_json(waves(), **kw)))
                corners.append(c)
        rep = {"corners": corners[:-3] if self.mode == "partial" else corners,
               "environment": {"engine_version": "46", "remote": {
                   "job_id": f"job-{len(self.calls)}", "runner_klt_version": "0.5.0",
                   "client_klt_version": "0.7.0"}}}
        if self.mode == "unmeasured":  # real klt: exit 4 when no measurement is requested
            rep["coverage"] = {"nothing_checked": True,
                               "nothing_checked_reasons": ["no_requested_measurements"]}
        return NS(returncode=4 if self.mode in ("refusal", "exit4", "unmeasured") else 0,
                  stdout=json.dumps(rep), stderr="")


class Base(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.tmp = Path(td.name)
        os.environ["KLT_BATCH_PROVISION_SCRIPT"] = str(self.tmp / "prov.sh")
        (self.tmp / "prov.sh").write_text("")
        self.cands = self.make(("p1", "c0"), ("p2", "c1"))
        self.clock = (datetime(2026, 1, 1) + timedelta(seconds=i) for i in range(100))

    def make(self, *uids):
        out = []
        for i, (prod, cid) in enumerate(uids):
            m = dict(manifest(prod), candidate_id=cid)
            (self.tmp / f"m{i}.json").write_text(json.dumps(m))
            (self.tmp / f"n{i}.spice").write_text(NETLIST)
            out.append(f"{self.tmp}/m{i}.json={self.tmp}/n{i}.spice")
        return out

    def cli(self, *extra, runner=None, cands=None, now=None):
        args = [a for c in (cands or self.cands) for a in ("--candidate", c)] + list(extra)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = C.main(args, runner=runner or FakeKlt(), sleep=lambda s: None,
                        now=now or (lambda: next(self.clock)))
        return rc, out.getvalue(), err.getvalue()

    def fix(self, *extra, **kw):
        shutil.rmtree(self.tmp / "rec", ignore_errors=True) if kw.pop("fresh", False) else None
        return self.cli("--fixture", "--records-dir", str(self.tmp / "rec"), "--klt", "klt",
                        *extra, **kw)

    def rec(self, i=-1):
        return json.loads(sorted((self.tmp / "rec").glob("*.json"))[i].read_text())


class DryRun(Base):
    def test_plans_without_jobs(self):
        k = FakeKlt()
        rc, out, _ = self.cli("--dry-run", runner=k)
        plan = json.loads(out)
        self.assertEqual((rc, k.calls, plan["points_label"]), (0, [], "SUBSET_POINTS:nominal"))
        g = plan["groups"][0]
        self.assertEqual((len(plan["groups"]), g["key"], g["corners"]),
                         (2, "p1.c0_1.80v", [["tt", 27.0]]))
        self.assertEqual(g["required_traces"], ["in", "raw", "tap", "tick"])
        self.assertEqual(g["request"]["corners"], {"process": ["tt"], "temperature_c": [27.0]})
        plan = json.loads(self.cli("--dry-run", "--points", "all")[1])
        self.assertEqual((plan["points_label"], len(plan["groups"])), ("all", 6))
        self.assertEqual(sum(len(g["corners"]) for g in plan["groups"]), 90)
        plan = json.loads(self.cli("--dry-run", "--points", "all", "--split-temps")[1])
        self.assertEqual((len(plan["groups"]), sum(len(g["corners"]) for g in plan["groups"])),
                         (18, 90))
        self.assertIn("p1.c0_1.62v_-40c", [g["key"] for g in plan["groups"]])

    def test_bad_inputs_refused_before_submit(self):
        k = FakeKlt()
        for extra, cands, msg in ((["--required-products", "p1,p2"], None, "3 distinct"),
                                  (["--dry-run"], [self.cands[1]] * 2, "duplicate"),
                                  (["--fixture", "--klt", "k"], None, "records-dir")):
            rc, _, err = self.cli(*extra, cands=cands, runner=k)
            self.assertEqual((rc, k.calls), (1, []))
            self.assertIn(msg, err)
        (self.tmp / "n0.spice").write_text("no placeholder\n")
        self.assertIn("@VDD@", self.cli("--dry-run")[2])


class Run(Base):
    def test_round_trip_and_provenance(self):
        k = FakeKlt()
        rc, _, err = self.fix("--points", "all", "--required-products", "p1,p2,p3", runner=k)
        self.assertEqual((rc, len(k.calls)), (0, 6), err)
        rec = self.rec()
        self.assertEqual((rec["evidence_class"], rec["points_scope"]), ("fixture", "all"))
        self.assertEqual((rec["handoff"]["products_absent"], rec["handoff"]["handoff_ready"]),
                         (["p3"], False))
        for c in rec["candidates"]:
            self.assertEqual(c["result"]["verdict"], L.PASS, c["result"]["failed"])
            self.assertEqual(len(c["manifest_sha256"]), 64)
        j = rec["jobs"][0]
        self.assertEqual((j["job_id"], j["exit_code"], j["version_skew"], j["pdk"]["pdk"]),
                         ("job-1", 0, True, "sky130A"))
        body = (self.tmp / "rec" / rec["record_id"] / j["group"] / "body.spice").read_text()
        self.assertIn("V1 VDD GND 1.62", body)
        self.assertNotIn(".lib", body)
        self.assertIn(".save v(in)", body)

    def test_shared_candidate_id_across_products(self):
        self.cands = self.make(("p1", "c0"), ("p2", "c0"))
        self.assertEqual(self.fix()[0], 0)
        rec = self.rec()
        self.assertEqual([j["group"] for j in rec["jobs"]], ["p1.c0_1.80v", "p2.c0_1.80v"])
        self.assertEqual([len(c["rows"]) for c in rec["candidates"]], [1, 1])
        self.assertEqual(rec["points_scope"], "SUBSET_POINTS:nominal")
        self.assertEqual({c["result"]["verdict"] for c in rec["candidates"]}, {L.INCONCLUSIVE})
        for j in rec["jobs"]:
            report = self.tmp / "rec" / rec["record_id"] / j["group"] / "report.json"
            self.assertEqual(json.loads(report.read_text())["environment"]["remote"]["job_id"],
                             j["job_id"])

    def failing(self, mode, status):
        rc, _, err = self.fix("--points", "all", runner=FakeKlt(mode), fresh=True)
        self.assertEqual(rc, 0, err)
        rec = self.rec()
        for c in rec["candidates"]:
            self.assertEqual(c["result"]["verdict"], L.INCONCLUSIVE)
            self.assertIn(status, {r["status"] for r in c["rows"]})
        return rec

    def test_unmeasured_exit4_is_usable_only_with_the_exact_report(self):
        rc, _, err = self.fix("--points", "all", runner=FakeKlt("unmeasured"), fresh=True)
        self.assertEqual(rc, 0, err)
        rec = self.rec()
        self.assertTrue(all(j["failure"] is None and j["exit_code"] == 4 for j in rec["jobs"]))
        self.assertEqual(rec["evidence_class"], "fixture")
        self.assertIn(L.OK, {r["status"] for c in rec["candidates"] for r in c["rows"]})

    def test_failures_never_pass(self):
        self.assertIn("no JSON report", self.failing("boom", L.SIM_FAILED)["jobs"][0]["failure"])
        self.assertTrue(self.failing("refusal", L.SIM_FAILED)["jobs"][0]["failure"]
                        .startswith("batch_runner_version"))
        self.assertEqual(self.failing("exit4", L.SIM_FAILED)["jobs"][0]["failure"],
                         "klt sim exit 4")
        rows = self.failing("corner_error", L.SIM_FAILED)["candidates"][0]["rows"]
        self.assertTrue(all("timeout" in r["reason"] for r in rows if r["coord"]["process"] == "ss"))
        rows = [r for c in self.failing("partial", L.SIM_FAILED)["candidates"] for r in c["rows"]]
        self.assertIn("corner missing from the report", {r["reason"] for r in rows})
        self.failing("missing_trace", L.MALFORMED)
        self.failing("nonuniform", L.MALFORMED)
        self.failing("truncated", L.INSUFFICIENT_SETTLING)

    def test_capacity_retry_then_fail(self):
        k = FakeKlt("capacity_once")
        self.assertEqual((self.fix(runner=k)[0], len(k.calls)), (0, 3))
        k = FakeKlt("capacity")
        self.fix(runner=k, fresh=True)
        self.assertEqual(len(k.calls), 62)  # 31 attempts per group, then recorded failure
        self.assertIn("capacity", self.rec()["jobs"][0]["failure"])

    def test_physical_class_needs_real_jobs(self):
        ok = {"jobs": [{"job_id": "j", "failure": None}]}
        self.assertEqual(C.evidence_class(ok, False), "physical")
        self.assertEqual(C.evidence_class(ok, True), "fixture")
        self.assertEqual(C.evidence_class({"jobs": [{"job_id": None, "failure": "x"}]}, False),
                         "incomplete-not-physical")


class Retention(Base):
    def test_append_only_and_supersession(self):
        t0 = datetime(2026, 1, 1)
        self.assertEqual(self.fix(now=lambda: t0)[0], 0)
        first = sorted((self.tmp / "rec").glob("*.json"))[0]
        before = first.read_bytes()
        for extra, msg in (((), "--supersedes"), (("--supersedes", "nope"), "names no record"),
                           (("--supersedes", first.stem), "append-only")):
            rc, _, err = self.fix(*extra, now=lambda: t0)  # same id: collision is refused
            self.assertEqual(rc, 1)
            self.assertIn(msg, err)
        rc, _, err = self.fix("--supersedes", first.stem, now=lambda: t0 + timedelta(seconds=1))
        self.assertEqual(rc, 0, err)
        self.assertEqual((self.rec(0)["supersedes"], self.rec(1)["supersedes"]), (None, first.stem))
        self.assertEqual(first.read_bytes(), before)

    def test_missing_provisioning_is_refused(self):
        os.environ["KLT_BATCH_PROVISION_SCRIPT"] = str(self.tmp / "absent.sh")
        k = FakeKlt()
        rc, _, err = self.fix(runner=k)
        self.assertEqual((rc, k.calls), (1, []))
        self.assertIn("no local fallback", err)


if __name__ == "__main__":
    unittest.main()
