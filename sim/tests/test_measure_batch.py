#!/usr/bin/env python3
"""PDK-free tests for the `klt sim` decks[] batch route of the transient `measure`
campaigns (`sim/pll-lock`, `sim/loop-ripple`; issue #365).

The route is `harness/cp_klt.py`'s; these tests pin that a `measure` manifest is
accepted, submits its patched deck with the `<corner_id>-pointNNN.raw` dumps as
declared outputs, brings the dumps back beside the unit, and keeps the
no-local-fallback failure policy. `klt` is mocked.

    python3 -m unittest discover -s sim/tests -p 'test_measure_batch.py' -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "tests"))

from harness import cp_klt as K  # noqa: E402
from harness import executor as executor_mod  # noqa: E402
from harness import measure as measure_mod  # noqa: E402
from test_cp_klt import ENV, PDK, FakeKlt, netlist  # noqa: E402

CAMPAIGNS = ("pll-lock", "loop-ripple")


def manifest(name: str) -> dict:
    return json.loads((SIM_DIR / name / "testbench" / "tb.json").read_text())


class MeasureFakeKlt(FakeKlt):
    def _dump(self, name):
        return "0 0\n1e-9 1\n"


def units(root: Path, ids=("tt_27C_1.80V",)):
    return [executor_mod.NgspiceUnit(corner_id=c, netlist_text=netlist(), work_dir=root,
                                     completion_marker=measure_mod.COMPLETION_MARKER,
                                     timeout_s=4242) for c in ids]


def backend(root: Path, man: dict, klt):
    spiceinit = root / "spiceinit"
    spiceinit.write_text("set ngbehavior=hsa\n")
    environ = {"KLT_BATCH_PROVISION_SCRIPT": str(spiceinit), **ENV}
    return K.CpBatchBackend(pdk=PDK, spiceinit=spiceinit,
                            measure_spec=measure_mod.MeasureSpec.from_manifest(man), klt="klt",
                            runner=klt, log=lambda *_: None, sleep=lambda _s: None,
                            environ=environ)


class MeasureBatchTests(unittest.TestCase):
    def test_request_shape_and_dumps_returned_for_each_campaign(self):
        for name in CAMPAIGNS:
            man = manifest(name)
            spec = measure_mod.MeasureSpec.from_manifest(man)
            with self.subTest(campaign=name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                klt = MeasureFakeKlt(spec)
                ids = ("tt_27C_1.80V", "ss_125C_1.62V")
                be = backend(root, man, klt).stage(units(root, ids))
                (req, decks), = klt.requests
                self.assertEqual([x["id"] for x in req["decks"]], list(ids))
                for entry in req["decks"]:
                    want = measure_mod.waveform_names(spec, f"{entry['id']}-")
                    self.assertEqual(entry["outputs"], want)
                    self.assertEqual(entry["timeout_s"], 4242)
                    self.assertNotIn(LOCAL_PDK, decks[entry["id"]])
                    self.assertIn("$PDK_ROOT", decks[entry["id"]])
                    for out in want:  # returned beside the unit, where the reducer reads
                        self.assertTrue((root / out).is_file(), out)
                for field in ("netlist", "corners", "analysis", "measurements", "monte_carlo"):
                    self.assertNotIn(field, req)
                self.assertEqual(be.provenance()["job"]["job_id"], "job-1")

    def test_failed_submit_raises_and_never_runs_locally(self):
        man = manifest("pll-lock")
        spec = measure_mod.MeasureSpec.from_manifest(man)
        for mode in ("submit_failure", "capacity", "unsupported", "job_error"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                klt = MeasureFakeKlt(spec, mode=mode)
                be = backend(root, man, klt)
                be.capacity_retries = 1
                with self.assertRaises(K.CpBatchError):
                    be.stage(units(root))
                self.assertFalse(any("ngspice" in str(c[0]) for c in klt.calls))
                with self.assertRaises(K.CpBatchError):
                    be.execute(units(root)[0])

    def test_backend_without_any_spec_is_refused(self):
        with self.assertRaises(K.CpBatchError):
            K.CpBatchBackend(pdk=PDK, spiceinit=Path("x"))


class SelectionTests(unittest.TestCase):
    def test_batch_accepted_for_measure_manifests(self):
        for name in CAMPAIGNS:
            self.assertEqual(executor_mod.resolve_name("batch", manifest(name), ENV), "batch")

    def test_measure_manifest_does_not_auto_route(self):
        self.assertEqual(executor_mod.resolve_name(None, manifest("pll-lock"), ENV), "local")

    def test_non_cp_non_transient_manifest_still_refused(self):
        with self.assertRaisesRegex(executor_mod.ExecutorRefused, "transient `measure`"):
            executor_mod.resolve_name("batch", {"ac": {"x": 1}}, ENV)

    def test_build_batch_returns_the_backend_for_a_measure_manifest(self):
        be = executor_mod.build("batch", pdk=PDK, spiceinit=Path("x"), jobs=8,
                                manifest=manifest("loop-ripple"))
        self.assertIsInstance(be, K.CpBatchBackend)


LOCAL_PDK = str(PDK.pdk_root)

if __name__ == "__main__":
    unittest.main()
