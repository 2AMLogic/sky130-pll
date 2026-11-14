#!/usr/bin/env python3
"""Executor-seam tests for sim/harness (issue #146): `--executor local`
(unchanged), the ABC every backend implements, and (issue #425) the refusal of
the retired `--executor remote`.

    python3 -m unittest discover -s sim/tests -v

Hermetic by construction: no PDK, no ngspice, no AWS CLI call, no network, no
credential read.

The properties pinned here are the ones a plausible-looking but wrong
implementation would silently violate:

  - `--executor local` is not merely the default but the *same call* it
    always was -- no new keyword reaches `run_point`, and the record is
    byte-for-byte a pre-#146 record;
  - `--executor remote` (retired in #425) is refused, never silently run
    locally.
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
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling test modules
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import cli  # noqa: E402
from harness import corners  # noqa: E402
from harness import executor as executor_mod  # noqa: E402
from harness import runner  # noqa: E402

RECORD_ID = "20260101-000000-abc1234"
LOCAL_PDK_ROOT = "/fake/pdk-root"


class _StubPdk:
    variant = "sky130A"
    process_corners = ("tt", "ss")
    resolved_commit = "0" * 40
    pinned_commit = "0" * 40
    commit_mismatch = False
    pdk_root = Path(LOCAL_PDK_ROOT)
    ngspice_lib = Path(f"{LOCAL_PDK_ROOT}/sky130A/libs.tech/combined/sky130.lib.spice")

    def as_env(self):
        return {}


# A plumbing-only manifest (no `measure` / `ac` block), so a unit's verdict
# is exactly the shared judge's -- no waveform reduction in the way.
MANIFEST = {
    "claim": "harness executor-seam test fixture -- not a design claim",
    "spec_rows": [],
    "spec_rows_note": "none -- a fixture, not a DUT: it measures no spec/target-spec.md parameter.",
    "schematic": "tb_fake.sch",
    "process_corners": ["tt"],
    "temps_c": [27],
    "supply_nominal": 1.8,
    "supply_tolerance": 0.1,
    "corner_pattern": r"(\.lib\s+\S*sky130\.lib\.spice\s+)(\w+)",
    "supply_pattern": r"(V1 VDD GND )([0-9.]+)",
    "methodology_note": "a fixture, not a DUT.",
    "analysis": "none (stubbed)",
}

NETLIST = (
    "**.subckt tb_fake\n"
    "V1 VDD GND 1.8\n"
    f".lib {LOCAL_PDK_ROOT}/sky130A/libs.tech/combined/sky130.lib.spice tt\n"
    f".include {LOCAL_PDK_ROOT}/sky130A/libs.ref/x/spice/x.spice\n"
    "**.ends\n"
    ".end\n"
)

GOOD_LOG = "ngspice-46\nTotal analysis time (seconds) = 0.5\n"
ERROR_LOG = "ngspice-46\nError: singular matrix\nTotal analysis time = 0.1\n"


# --------------------------------------------------------------------------- #
# A fake klayout_tools, faithful to the real push/run/pull contract
# --------------------------------------------------------------------------- #



# --------------------------------------------------------------------------- #


class _Harness:
    """A temp experiment directory plus the stubs that let `cli.main` run one
    campaign end to end with no PDK and no ngspice.

    Deliberately keeps the **real** `runner.run_point` in the loop (unlike
    `test_execution.py`, which stubs it): the executor seam lives underneath
    `run_point`, so stubbing it out would test nothing. What is stubbed is
    the one genuinely external thing -- `run_ngspice_locally`.
    """

    def __init__(self, tmp: Path, slug: str = "fake-exp", manifest: dict | None = None):
        self.root = tmp
        self.slug = slug
        self.exp_dir = tmp / slug
        self.testbench = self.exp_dir / "testbench"
        self.testbench.mkdir(parents=True)
        (self.testbench / "tb.json").write_text(
            json.dumps(manifest or MANIFEST, indent=2)
        )
        self.spiceinit = tmp / "spiceinit"
        self.spiceinit.write_text("set ngbehavior=hsa\n")
        self.local_calls: list = []
        self.run_point_kwargs: list = []

    @property
    def record_path(self) -> Path:
        return self.exp_dir / "records" / f"{RECORD_ID}.md"

    @property
    def work_dir(self) -> Path:
        # Work lives in the git-ignored scratch tree (DR-012), not corners/.
        return self.root / "build" / self.slug / RECORD_ID

    def _fake_store_files(self, files, **kw):
        from test_execution import _REAL_STORE_FILES, fake_put
        self.stored = [n for _, n in files]
        return _REAL_STORE_FILES(files, **dict(kw, repo_root=self.root, put=fake_put))

    def _fake_local(self, log_text=GOOD_LOG, returncode=0):
        def run_ngspice_locally(unit, *, pdk, spiceinit):
            self.local_calls.append(unit.corner_id)
            unit.work_dir.mkdir(parents=True, exist_ok=True)
            unit.spice_path.write_text(unit.netlist_text)
            unit.log_path.write_text(log_text)
            return executor_mod.NgspiceOutcome(
                corner_id=unit.corner_id,
                returncode=returncode,
                log_text=log_text,
                log_path=unit.log_path,
                spice_path=unit.spice_path,
            )

        return run_ngspice_locally

    def run(self, argv, *, local_log=GOOD_LOG, local_rc=0, env=None):
        """Invoke the real CLI. Returns (rc, combined stdout+stderr)."""
        real_run_point = runner.run_point

        def spy_run_point(*args, **kwargs):
            self.run_point_kwargs.append(dict(kwargs))
            return real_run_point(*args, **kwargs)

        out = io.StringIO()
        patches = [
            mock.patch.object(cli.pdk_mod, "resolve", return_value=_StubPdk()),
            mock.patch.object(
                cli.pdk_mod,
                "tool_versions",
                return_value={"ngspice": "stub", "xschem": "stub"},
            ),
            mock.patch.object(
                cli.runner_mod, "netlist_schematic", return_value=NETLIST
            ),
            mock.patch.object(cli.runner_mod, "run_point", spy_run_point),
            mock.patch.object(
                cli.runner_mod,
                "run_ngspice_locally",
                self._fake_local(local_log, local_rc),
            ),
            mock.patch.object(cli.report_mod, "make_record_id", return_value=RECORD_ID),
            mock.patch.object(cli.evidence_store_mod, "preflight", return_value=None),
            mock.patch.object(cli.evidence_store_mod, "store_files", self._fake_store_files),
            mock.patch.dict("os.environ", env or {}, clear=False),
        ]
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            # A batch dispatch host exports KLT_SIM_BACKEND=batch, which routes a
            # `cp` manifest to the batch executor (#290); these tests pin the seam.
            os.environ.pop("KLT_SIM_BACKEND", None)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                rc = cli.main([str(self.testbench)] + argv)
        return rc, out.getvalue()



# --------------------------------------------------------------------------- #


def _without_wall_clock(record_text: str) -> str:
    """Drop the one line that is a wall clock, not a property of the run.

    `report.render` stamps `**Timestamp / author**` with the second the
    record was written, so two runs that straddle a second boundary differ
    there and nowhere else. Comparing around it is the point: what must be
    identical is everything the *executor* could have influenced.
    """
    return "\n".join(
        line
        for line in record_text.splitlines()
        if not line.startswith("- **Timestamp / author**:")
    )


class LocalExecutorUnchangedTests(unittest.TestCase):
    def test_default_and_explicit_local_produce_identical_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            default = _Harness(Path(tmp) / "a")
            rc_default, _ = default.run([])
            explicit = _Harness(Path(tmp) / "b")
            rc_explicit, _ = explicit.run(["--executor", "local"])

            self.assertEqual(rc_default, 0)
            self.assertEqual(rc_explicit, rc_default)
            self.assertEqual(
                _without_wall_clock(default.record_path.read_text()),
                _without_wall_clock(explicit.record_path.read_text()),
            )
            # ...and the dropped line is genuinely the *only* difference the
            # two runs are allowed to have.
            for record in (default.record_path, explicit.record_path):
                self.assertIn("- **Timestamp / author**:", record.read_text())

    def test_local_record_carries_no_execution_segment_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            rc, _ = h.run(["--executor", "local"])
            self.assertEqual(rc, 0)
            text = h.record_path.read_text()
            # A serial local run is what every pre-#146 record was minted by;
            # its shape must not have changed by so much as a word.
            self.assertNotIn("**Execution**", text)
            # (the fixture's own claim string mentions the word "executor",
            # so pin the rendered `executor: ` field, not the bare word)
            self.assertNotIn("executor: ", text)

    def test_local_path_never_passes_an_execute_keyword_to_run_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            rc, _ = h.run([])
            self.assertEqual(rc, 0)
            self.assertTrue(h.run_point_kwargs)
            for kwargs in h.run_point_kwargs:
                self.assertNotIn("execute", kwargs)

    def test_local_runs_every_unit_through_ngspice_on_this_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            rc, _ = h.run([])
            self.assertEqual(rc, 0)
            expected = [
                p.corner_id
                for p in corners.build_matrix(MANIFEST, _StubPdk.process_corners)
            ]
            self.assertEqual(sorted(h.local_calls), sorted(expected))

    def test_the_retired_remote_executor_is_refused_not_run_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            # the flag: argparse no longer offers `remote` as a choice
            h = _Harness(Path(tmp) / "flag")
            with self.assertRaises(SystemExit) as cm:
                h.run(["--executor", "remote"])
            self.assertNotEqual(cm.exception.code, 0)
            self.assertEqual(h.local_calls, [])
            # the manifest key: refused with a message naming the retirement
            h = _Harness(Path(tmp) / "manifest", manifest=dict(MANIFEST, executor="remote"))
            rc, out = h.run([])
            self.assertEqual(rc, 1)
            self.assertIn("retired", out)
            self.assertEqual(h.local_calls, [])
            self.assertFalse(h.record_path.exists())

    def test_an_unknown_executor_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = dict(MANIFEST, executor="fleet")
            h = _Harness(Path(tmp), manifest=manifest)
            rc, out = h.run([])
            self.assertEqual(rc, 1)
            self.assertIn("unknown executor 'fleet'", out)


# --------------------------------------------------------------------------- #
# remote: success
# --------------------------------------------------------------------------- #



class BackendInterfaceTests(unittest.TestCase):
    """The seam is an ABC on purpose: a backend is one more subclass
    without any call site changing."""

    def test_the_shipped_backend_implements_the_abc_and_remote_is_gone(self):
        self.assertTrue(issubclass(executor_mod.LocalBackend, executor_mod.ExecutionBackend))
        self.assertFalse(hasattr(executor_mod, "RemoteBackend"))
        self.assertEqual(executor_mod.EXECUTORS, ("local", "batch"))

    def test_the_abc_cannot_be_instantiated_without_execute(self):
        with self.assertRaises(TypeError):
            executor_mod.ExecutionBackend()

    def test_a_third_backend_needs_only_execute(self):
        class BatchBackend(executor_mod.ExecutionBackend):
            name = "batch"
            requested = "batch"

            def execute(self, unit):
                return executor_mod.NgspiceOutcome(
                    corner_id=unit.corner_id,
                    returncode=0,
                    log_text="",
                    log_path=unit.log_path,
                    spice_path=unit.spice_path,
                )

        backend = BatchBackend()
        self.assertIs(backend.stage([]), backend)
        self.assertIsNone(backend.provenance())

    def test_build_rejects_an_unknown_backend_name(self):
        with self.assertRaises(ValueError):
            executor_mod.build("fleet", pdk=_StubPdk(), spiceinit=Path("/x"), jobs=1, manifest={})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
