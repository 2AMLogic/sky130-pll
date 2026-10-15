#!/usr/bin/env python3
"""PDK-free tests for the `klt sim` decks[] batch route of the `cp` campaign (issue #290).

A fake `klt` runner reads the generated deck-list request and "simulates" it
by writing the unit trees and report a real `klt sim --backend batch` would
return (stdout/stderr streams and declared `wrdata` dumps), so the request
shape, executor selection, failure policy and the unchanged reducer are
exercised without a PDK, ngspice, AWS or a fleet.

    python3 -m unittest discover -s sim/tests -p 'test_cp_klt.py' -v
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "tests"))

from harness import cp_klt as K  # noqa: E402
from harness import cpmeasure as cp_mod  # noqa: E402
from harness import executor as executor_mod  # noqa: E402
from harness import runner  # noqa: E402
from test_cpmeasure import MANIFEST, make_spec, synth_dump  # noqa: E402

LOCAL_ROOT = "/fake/pdk-root"
PDK = SimpleNamespace(pdk_root=Path(LOCAL_ROOT), variant="sky130A")
ENV = {"KLT_SIM_BACKEND": "batch"}


def netlist():
    return f"* tb\n.lib {LOCAL_ROOT}/sky130A/libs.tech/combined/sky130.lib.spice tt\n.end\n"


class FakeKlt:
    """A `subprocess.run` stand-in modelling `klt sim --backend batch` on a decks[] request."""

    def __init__(self, spec, mode=None):
        self.spec, self.mode, self.calls, self.requests = spec, mode, [], []

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.calls.append(cmd)
        if cmd[1] == "--version":
            return SimpleNamespace(returncode=0, stdout="klt 9.9.9\n", stderr="")
        req_path = Path(cmd[2])
        outdir = Path(cmd[cmd.index("-o") + 1])
        req = json.loads(req_path.read_text())
        self.requests.append((req, {d["id"]: (req_path.parent / d["deck"]).read_text()
                                    for d in req["decks"]}))
        if self.mode == "capacity":
            return SimpleNamespace(returncode=1, stdout="", stderr="batch_no_capacity: no capacity in any")
        if self.mode == "submit_failure":
            return SimpleNamespace(returncode=1, stdout="", stderr="batch backend failed: upload denied")
        if self.mode == "unsupported":
            return SimpleNamespace(returncode=1, stdout="", stderr="request.decks: unknown field; netlist is required")
        if self.mode == "corner_report":
            return SimpleNamespace(returncode=0, stdout=json.dumps({"corners": [], "mode": "corners"}), stderr="")
        units = []
        for d in req["decks"]:
            udir = outdir / d["id"]
            udir.mkdir(parents=True, exist_ok=True)
            (udir / "stdout.bin").write_bytes(f"{cp_mod.COMPLETION_MARKER}\n".encode())
            (udir / "stderr.bin").write_bytes(b"")
            missing = []
            for i, name in enumerate(d["outputs"]):
                if self.mode == "missing_output" and i == 3:
                    missing.append(name)
                    continue
                (udir / name).write_text(self._dump(name))
            units.append({
                "id": d["id"], "status": "ok", "exit_code": 0, "timed_out": False,
                "stdout": f"{d['id']}/stdout.bin", "stderr": f"{d['id']}/stderr.bin",
                "outputs": [n for n in d["outputs"] if n not in missing],
                "missing_outputs": missing, "diagnostics": [],
            })
        if self.mode == "job_error":
            for u in units:
                u["status"] = "error"
                u["diagnostics"] = [{"code": "batch_poll_timeout", "message": "poll timed out"}]
        report = {"mode": "decks", "status": "ok", "units": units, "outdir": str(outdir),
                  "environment": {"engine_version": "ngspice-44",
                                  "remote": {"job_id": "job-1", "instance_type": "c7i.large",
                                             "lifecycle": "spot"}}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr="")

    def _dump(self, name):
        if name.endswith("cp_op.raw"):
            return "0 0.7 0.8 1e-05\n"
        vi, pj = int(name.split("_v")[1][:2]), int(name.split("_p")[1][:2])
        return synth_dump(self.spec, self.spec.phase_offsets_s[pj])


def make_units(root: Path, spec, corner_ids=("tt_27C_1.80V",)):
    return [executor_mod.NgspiceUnit(corner_id=c, netlist_text=netlist(), work_dir=root,
                                     completion_marker=cp_mod.COMPLETION_MARKER, timeout_s=77)
            for c in corner_ids]


def make_backend(root, spec, klt, **kw):
    spiceinit = root / "spiceinit"
    spiceinit.write_text("set ngbehavior=hsa\n")
    environ = {"KLT_BATCH_PROVISION_SCRIPT": str(spiceinit), **ENV}
    return K.CpBatchBackend(pdk=PDK, spiceinit=spiceinit, cp_spec=spec, klt="klt", runner=klt,
                            log=lambda *_: None, sleep=lambda _s: None, environ=environ, **kw)


class RequestShapeTests(unittest.TestCase):
    def test_one_deck_per_point_with_declared_outputs_and_no_corner_fields(self):
        spec = make_spec()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            klt = FakeKlt(spec)
            ids = ("tt_27C_1.62V", "ss_125C_1.62V")
            make_backend(root, spec, klt).stage(make_units(root, spec, ids))
            (req, decks), = klt.requests
        self.assertEqual([x["id"] for x in req["decks"]], list(ids))
        for entry in req["decks"]:
            self.assertEqual(entry["deck"], f"{entry['id']}.spice")
            self.assertEqual(entry["timeout_s"], 77)
            self.assertEqual(entry["inputs"], [{"path": ".spiceinit", "name": ".spiceinit"}])
            self.assertEqual(entry["outputs"], cp_mod.waveform_names(spec, f"{entry['id']}-"))
        for field in ("netlist", "corners", "analysis", "measurements", "monte_carlo"):
            self.assertNotIn(field, req)
        self.assertEqual(req["backend"], "batch")
        self.assertEqual(req["models"], {"pdk": "sky130A"})

    def test_local_pdk_root_is_rerooted_in_the_shipped_deck_only(self):
        spec = make_spec()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            klt = FakeKlt(spec)
            units = make_units(root, spec)
            make_backend(root, spec, klt).stage(units)
            (_, decks), = klt.requests
        self.assertNotIn(LOCAL_ROOT, decks["tt_27C_1.80V"])
        self.assertIn(".lib $PDK_ROOT/sky130A/libs.tech", decks["tt_27C_1.80V"])
        self.assertIn(LOCAL_ROOT, units[0].netlist_text)  # the unit itself is untouched

    def test_submit_uses_batch_backend_and_never_local(self):
        spec = make_spec()
        with tempfile.TemporaryDirectory() as d:
            klt = FakeKlt(spec)
            make_backend(Path(d), spec, klt).stage(make_units(Path(d), spec))
        submit = [c for c in klt.calls if c[1] == "sim"][0]
        self.assertEqual(submit[submit.index("--backend") + 1], "batch")

    def test_provenance_records_klt_version_and_job(self):
        spec = make_spec()
        with tempfile.TemporaryDirectory() as d:
            be = make_backend(Path(d), spec, FakeKlt(spec))
            be.stage(make_units(Path(d), spec))
        prov = be.provenance()
        self.assertEqual(prov["executor"], "batch")
        self.assertEqual(prov["job"]["installed_klt_version"], "klt 9.9.9")
        self.assertEqual(prov["job"]["job_id"], "job-1")
        self.assertIn("job-1", K.execution_note(prov))


class ReductionTests(unittest.TestCase):
    def test_returned_dumps_reduce_through_cpmeasure_like_a_local_run(self):
        spec = make_spec()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            be = make_backend(root, spec, FakeKlt(spec))
            (unit,) = make_units(root, spec)
            be.stage([unit])
            outcome = be.execute(unit)
            passed, reason = runner.judge(outcome, unit.completion_marker, unit.timeout_s)
            self.assertTrue(passed, reason)
            (result,), ok, why = runner._reduce_cp_measurements(spec, 1.8, root, f"{unit.corner_id}-")
        self.assertTrue(ok, why)
        self.assertEqual(len(result.points), len(spec.vctrl_fractions) * len(spec.phase_offsets_s))
        self.assertTrue(result.op.available)


class FailurePathTests(unittest.TestCase):
    def stage(self, mode, **kw):
        spec = make_spec()
        with tempfile.TemporaryDirectory() as d:
            klt = FakeKlt(spec, mode=mode)
            be = make_backend(Path(d), spec, klt, **kw)
            be.stage(make_units(Path(d), spec))
            return be, klt

    def assert_no_local_ngspice(self, klt):
        for c in klt.calls:
            self.assertNotIn("ngspice", c[0])
            if len(c) > 1 and c[1] == "sim":
                self.assertEqual(c[c.index("--backend") + 1], "batch")

    def test_submit_failure_raises_with_the_error(self):
        spec = make_spec()
        with tempfile.TemporaryDirectory() as d:
            klt = FakeKlt(spec, mode="submit_failure")
            with self.assertRaises(K.CpBatchError) as cm:
                make_backend(Path(d), spec, klt).stage(make_units(Path(d), spec))
        self.assertIn("upload denied", str(cm.exception))
        self.assert_no_local_ngspice(klt)

    def test_capacity_refusal_retries_then_raises_without_local_fallback(self):
        spec = make_spec()
        with tempfile.TemporaryDirectory() as d:
            klt = FakeKlt(spec, mode="capacity")
            with self.assertRaises(K.CpBatchError) as cm:
                make_backend(Path(d), spec, klt, capacity_retries=2).stage(make_units(Path(d), spec))
        self.assertIn("capacity", str(cm.exception))
        self.assertEqual(len([c for c in klt.calls if c[1] == "sim"]), 3)  # 1 + 2 retries
        self.assert_no_local_ngspice(klt)

    def test_decks_unsupported_is_named_not_run_locally(self):
        spec = make_spec()
        for mode in ("unsupported", "corner_report"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                klt = FakeKlt(spec, mode=mode)
                with self.assertRaises(K.DecksUnsupported):
                    make_backend(Path(d), spec, klt).stage(make_units(Path(d), spec))
                self.assert_no_local_ngspice(klt)

    def test_missing_declared_output_fails_the_unit_explicitly(self):
        spec = make_spec()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            be = make_backend(root, spec, FakeKlt(spec, mode="missing_output"))
            (unit,) = make_units(root, spec)
            be.stage([unit])
            outcome = be.execute(unit)
            self.assertIn("missing_outputs", outcome.log_text)
            _, ok, why = runner._reduce_cp_measurements(spec, 1.8, root, f"{unit.corner_id}-")
        self.assertFalse(ok)
        self.assertIn("no CP waveform dump", why)

    def test_batch_level_unit_diagnostic_raises(self):
        with self.assertRaises(K.CpBatchError) as cm:
            self.stage("job_error")
        self.assertIn("batch_poll_timeout", str(cm.exception))

    def test_missing_provision_script_or_klt_raises_before_any_submit(self):
        spec = make_spec()
        with tempfile.TemporaryDirectory() as d:
            klt = FakeKlt(spec)
            be = make_backend(Path(d), spec, klt)
            be._environ = {}
            with self.assertRaises(K.CpBatchError):
                be.stage(make_units(Path(d), spec))
            self.assertEqual(klt.calls, [])

    def test_execute_never_runs_an_unstaged_unit_locally(self):
        spec = make_spec()
        with tempfile.TemporaryDirectory() as d:
            be = make_backend(Path(d), spec, FakeKlt(spec))
            (unit,) = make_units(Path(d), spec)
            with self.assertRaises(K.CpBatchError):
                be.execute(unit)


class SelectionTests(unittest.TestCase):
    CP = {"cp": {"x": 1}}

    def test_cp_on_batch_host_routes_to_batch_by_default(self):
        self.assertEqual(executor_mod.resolve_name(None, self.CP, ENV), "batch")

    def test_cp_off_batch_host_and_non_cp_stay_local(self):
        self.assertEqual(executor_mod.resolve_name(None, self.CP, {}), "local")
        self.assertEqual(executor_mod.resolve_name(None, {}, ENV), "local")

    def test_explicit_local_is_honoured(self):
        self.assertEqual(executor_mod.resolve_name("local", self.CP, ENV), "local")

    def test_remote_for_cp_on_batch_host_is_refused(self):
        with self.assertRaises(executor_mod.ExecutorRefused):
            executor_mod.resolve_name("remote", self.CP, ENV)
        with self.assertRaises(executor_mod.ExecutorRefused):
            executor_mod.resolve_name(None, {**self.CP, "executor": "remote"}, ENV)

    def test_batch_for_non_cp_manifest_is_refused(self):
        with self.assertRaises(executor_mod.ExecutorRefused):
            executor_mod.resolve_name("batch", {}, ENV)

    def test_build_batch_returns_the_cp_backend(self):
        be = executor_mod.build("batch", pdk=PDK, spiceinit=Path("x"), jobs=8, manifest=MANIFEST)
        self.assertIsInstance(be, K.CpBatchBackend)
        self.assertEqual(be.max_workers, 2)


if __name__ == "__main__":
    unittest.main()
