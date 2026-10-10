#!/usr/bin/env python3
"""Execution-model tests for sim/harness: worker-pool parallelism and the
checkpoint/resume path (issue #133). No PDK and no ngspice/xschem required --
every simulator call is stubbed, because what is under test here is *which
units run, exactly once, in which recorded order*, not what ngspice computes.

    python3 -m unittest discover -s sim/tests -v

The properties pinned here are the ones a plausible-looking but wrong
implementation would silently violate, minting an evidence record for
simulations that never ran:

  - a parallel run's record rows are in manifest order, not completion order,
    and every requested unit ran exactly once;
  - a parallel run's verdicts match a serial run's for the same inputs;
  - a resume re-runs exactly the units that had not completed;
  - an interrupted run writes **no** record (one complete record, or none);
  - a checkpoint that cannot be fully trusted -- corrupt, stale-schema,
    self-inconsistent, or from a different manifest/DUT/point list -- aborts
    the run loudly instead of being read as progress;
  - a retried unit cannot read a previous attempt's stale waveform dump.
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling test modules

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from harness import acmeasure as ac_mod  # noqa: E402
from harness import checkpoint as checkpoint_mod  # noqa: E402
from harness import cli  # noqa: E402
from harness import corners  # noqa: E402
from harness import cpmeasure as cp_mod  # noqa: E402
from harness import executor as executor_mod  # noqa: E402
from harness import measure as measure_mod  # noqa: E402
from harness import montecarlo as mc_mod  # noqa: E402
from harness import runner  # noqa: E402
import test_cpmeasure as cpt  # noqa: E402

RECORD_ID = "20260101-000000-abc1234"


class _StubPdk:
    variant = "sky130A"
    process_corners = ("tt", "ss", "ff")
    resolved_commit = "0" * 40
    pinned_commit = "0" * 40
    commit_mismatch = False
    ngspice_lib = Path("/fake/sky130.lib.spice")

    def as_env(self):
        return {}


MANIFEST = {
    "claim": "harness execution-model test fixture -- not a design claim",
    "spec_rows": [],
    "spec_rows_note": "none -- a fixture, not a DUT: it measures no spec/target-spec.md parameter.",
    "schematic": "tb_fake.sch",
    "process_corners": ["tt", "ss"],
    "temps_c": [-40, 27, 125],
    "supply_nominal": 1.8,
    "supply_tolerance": 0.0,
    "corner_pattern": r"(\.lib\s+\S*sky130\.lib\.spice\s+)(\w+)",
    "supply_pattern": r"(V1 VDD GND )([0-9.]+)",
    "methodology_note": "a fixture, not a DUT.",
    "analysis": "none (stubbed)",
}

NETLIST = (
    "**.subckt tb_fake\n"
    "V1 VDD GND 1.8\n"
    ".lib /fake/sky130.lib.spice tt\n"
    "**.ends\n"
    ".end\n"
)


def _point_result(point, reason="ok", passed=True):
    return runner.PointResult(point=point, passed=passed, reason=reason)


# --------------------------------------------------------------------------
# Charge-pump (`cp`) fixtures -- shared with test_executor.py / test_harness.py
# --------------------------------------------------------------------------

CP_LOG = "ngspice-46\n" + cp_mod.COMPLETION_MARKER + "\n"
CP_OP_TEXT = "0 0.62 1.1 2.5e-5\n"


def _cp_block() -> dict:
    """The test_cpmeasure `cp` block on a 3-point VCTRL grid (kept small)."""
    import copy

    block = copy.deepcopy(cpt.MANIFEST["cp"])
    block["vctrl_fractions"] = [0.3, 0.5, 0.7]
    return block


CP_MANIFEST = {
    **MANIFEST,
    "claim": "charge-pump integration fixture -- not a design claim",
    "spec_rows": [10],
    "spec_rows_note": (
        "partial mechanism evidence only (charge-asymmetry mechanism of "
        "the reference spur); row 10 stays DRAFT"
    ),
    "cp": _cp_block(),
}


def cp_spec() -> "cp_mod.CpSpec":
    return cp_mod.CpSpec.from_manifest(CP_MANIFEST)


def cp_dump_texts(spec, prefix: str, *, iup: float = 100e-6, drop=()) -> dict:
    """{filename: text} for every dump the control block promises."""
    out = {}
    for name in cp_mod.waveform_names(spec, prefix):
        if name in drop:
            continue
        if name == cp_mod.op_dump_name(prefix):
            out[name] = CP_OP_TEXT
            continue
        m = re.search(r"_v(\d\d)_p(\d\d)\.raw$", name)
        pj = int(m.group(2))
        out[name] = cpt.synth_dump(spec, spec.phase_offsets_s[pj], iup=iup, idn=100e-6)
    return out


def cp_execute(*, iup: float = 100e-6, drop=(), log: str = CP_LOG, rc: int = 0, timed_out: bool = False):
    """An executor-seam callable that "runs ngspice" by writing synthetic dumps."""
    spec = cp_spec()

    def execute(unit):
        unit.work_dir.mkdir(parents=True, exist_ok=True)
        runner.purge_unit_artifacts(unit.work_dir, unit.corner_id)
        if not timed_out:
            for name, text in cp_dump_texts(
                spec, f"{unit.corner_id}-", iup=iup, drop=drop
            ).items():
                (unit.work_dir / name).write_text(text)
        unit.spice_path.write_text(unit.netlist_text)
        unit.log_path.write_text(log)
        return executor_mod.NgspiceOutcome(
            corner_id=unit.corner_id,
            returncode=rc,
            log_text=log,
            log_path=unit.log_path,
            spice_path=unit.spice_path,
            timed_out=timed_out,
        )

    return execute



class _Harness:
    """A temp experiment directory plus the stubs that let `cli.main` run one
    end to end without a PDK."""

    def __init__(self, tmp: Path, slug: str = "fake-exp", manifest: dict | None = None):
        self.root = tmp
        self.slug = slug
        self.exp_dir = tmp / slug
        self.testbench = self.exp_dir / "testbench"
        self.testbench.mkdir(parents=True)
        self.write_manifest(manifest or MANIFEST)

    def write_manifest(self, manifest: dict) -> None:
        (self.testbench / "tb.json").write_text(json.dumps(manifest, indent=2))

    @property
    def checkpoint_path(self) -> Path:
        return self.exp_dir / "corners" / RECORD_ID / checkpoint_mod.CHECKPOINT_NAME

    @property
    def record_path(self) -> Path:
        return self.exp_dir / "records" / f"{RECORD_ID}.md"

    def run(self, argv, run_point, netlist: str = NETLIST):
        """Invoke the real CLI with a stubbed simulator. Returns (rc, stdout)."""
        import contextlib
        import io

        out = io.StringIO()
        with mock.patch.object(cli.pdk_mod, "resolve", return_value=_StubPdk()), \
             mock.patch.object(cli.pdk_mod, "tool_versions", return_value={"ngspice": "stub", "xschem": "stub"}), \
             mock.patch.object(cli.runner_mod, "netlist_schematic", return_value=netlist), \
             mock.patch.object(cli.runner_mod, "run_point", run_point), \
             mock.patch.object(cli.report_mod, "make_record_id", return_value=RECORD_ID):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                rc = cli.main([str(self.testbench)] + argv)
        return rc, out.getvalue()


def _table_rows(record_text: str) -> list:
    """The per-point result rows of a rendered record, in file order."""
    return [
        line.strip()
        for line in record_text.splitlines()
        if line.strip().startswith("| ") and ("PASS" in line or "FAIL" in line)
    ]


class ParallelExecutionTests(unittest.TestCase):
    """`--jobs N` may change *when* a point runs, never *what* the record
    says about it."""

    def _scrambling_run_point(self, seen):
        """A stub whose completion order is the reverse of submission order,
        so a record that accidentally used completion order is impossible to
        miss."""
        lock = threading.Lock()
        order = {}

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            with lock:
                idx = order.setdefault(point.corner_id, len(order))
            # Later-submitted points finish first.
            time.sleep(0.05 * max(0, 6 - idx))
            with lock:
                seen.append(point.corner_id)
            return _point_result(point, reason=f"ok ({point.corner_id})")

        return run_point

    def test_parallel_rows_are_in_manifest_order_not_completion_order(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            seen = []
            rc, _out = h.run(["--jobs", "4"], self._scrambling_run_point(seen))
            self.assertEqual(rc, 0)

            expected = [p.corner_id for p in corners.build_matrix(MANIFEST, _StubPdk.process_corners)]
            # Every requested point ran exactly once...
            self.assertEqual(sorted(seen), sorted(expected))
            self.assertEqual(len(seen), len(set(seen)))
            # ...and the record's rows are in the manifest's point order.
            rows = _table_rows(h.record_path.read_text())
            self.assertEqual(len(rows), len(expected))
            for corner_id, row in zip(expected, rows):
                corner, temp, supply = corner_id.split("_")
                self.assertIn(f"| {corner} |", row)
                self.assertIn(f"ok ({corner_id})", row)

    def test_parallel_and_serial_records_agree_row_for_row(self):
        import tempfile

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            # Deterministic per-point verdict, so any divergence between the
            # two runs is the execution model's fault, not the stub's.
            passed = point.corner != "ss" or point.temp_c != 125
            return _point_result(point, reason=f"{point.corner_id}: judged", passed=passed)

        with tempfile.TemporaryDirectory() as tmp:
            serial = _Harness(Path(tmp) / "a")
            rc_serial, _ = serial.run([], run_point)
            parallel = _Harness(Path(tmp) / "b")
            rc_parallel, _ = parallel.run(["-j", "3"], run_point)

            self.assertEqual(rc_serial, 1)  # the seeded ss/125C failure
            self.assertEqual(rc_parallel, rc_serial)
            self.assertEqual(
                _table_rows(serial.record_path.read_text()),
                _table_rows(parallel.record_path.read_text()),
            )

    def test_jobs_below_one_is_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            rc, out = h.run(["--jobs", "0"], self._scrambling_run_point([]))
            self.assertEqual(rc, 1)
            self.assertIn("--jobs must be at least 1", out)

    def test_serial_default_writes_no_execution_note(self):
        import tempfile

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            return _point_result(point)

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            rc, _out = h.run([], run_point)
            self.assertEqual(rc, 0)
            # An uninterrupted serial run is what every existing record was
            # produced by; its shape must not change.
            self.assertNotIn("**Execution**", h.record_path.read_text())

    def test_parallel_run_records_its_concurrency_in_the_record(self):
        import tempfile

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            return _point_result(point)

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            rc, _out = h.run(["-j", "2"], run_point)
            self.assertEqual(rc, 0)
            text = h.record_path.read_text()
            self.assertIn("**Execution**", text)
            self.assertIn("`--jobs 2`", text)


class IterUnitResultsTests(unittest.TestCase):
    """The pool primitive itself: nothing dropped, nothing duplicated, and
    `jobs == 1` still runs inline in submission order."""

    UNITS = [corners.PvtPoint(corner="tt", temp_c=float(t), supply_v=1.8) for t in range(8)]

    def _collect(self, jobs):
        announced = []
        lock = threading.Lock()

        def announce(unit):
            with lock:
                announced.append(unit.corner_id)

        def run_one(unit):
            time.sleep(0.01 * (8 - unit.temp_c))
            return unit.corner_id

        pairs = list(cli._iter_unit_results(self.UNITS, jobs=jobs, run_one=run_one, announce=announce))
        return announced, pairs

    def test_every_unit_runs_exactly_once_in_parallel(self):
        announced, pairs = self._collect(4)
        ids = [u.corner_id for u, _ in pairs]
        self.assertEqual(sorted(ids), sorted(u.corner_id for u in self.UNITS))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(announced), sorted(ids))
        for unit, result in pairs:
            self.assertEqual(unit.corner_id, result)

    def test_serial_path_preserves_submission_order(self):
        _announced, pairs = self._collect(1)
        self.assertEqual(
            [u.corner_id for u, _ in pairs], [u.corner_id for u in self.UNITS]
        )

    def test_failure_propagates_and_stops_dispatching(self):
        started = []
        lock = threading.Lock()

        def run_one(unit):
            with lock:
                started.append(unit.corner_id)
            raise runner.NetlistError("boom")

        with self.assertRaises(runner.NetlistError):
            list(cli._iter_unit_results(self.UNITS, jobs=2, run_one=run_one, announce=lambda u: None))
        # Not every unit got dispatched -- the pool was shut down on the
        # first failure rather than running the whole grid to a known-bad
        # netlist.
        self.assertLess(len(started), len(self.UNITS))


class CheckpointResumeTests(unittest.TestCase):
    """A killed campaign resumes from exactly where it stopped -- and a
    campaign that is not the same campaign does not resume at all."""

    def _kill_after(self, n, reason="first segment"):
        """A stub that completes `n` points and then dies the way a killed
        host does: mid-point, with no clean shutdown."""
        state = {"done": 0}

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            if state["done"] >= n:
                raise KeyboardInterrupt("simulated host kill, mid-point")
            state["done"] += 1
            return _point_result(point, reason=reason)

        return run_point

    def _recorder(self, reason="second segment"):
        seen = []

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            seen.append(point.corner_id)
            return _point_result(point, reason=reason)

        return seen, run_point

    def test_resume_runs_exactly_the_missing_points(self):
        import tempfile

        all_ids = [p.corner_id for p in corners.build_matrix(MANIFEST, _StubPdk.process_corners)]
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))

            with self.assertRaises(KeyboardInterrupt):
                h.run([], self._kill_after(2))

            # An interrupted run leaves no record at all: the append-only
            # evidence trail never shows a partial grid.
            self.assertFalse(h.record_path.exists())
            self.assertTrue(h.checkpoint_path.is_file())
            _header, done = checkpoint_mod.load(h.checkpoint_path)
            self.assertEqual(list(done), all_ids[:2])

            seen, run_point = self._recorder()
            rc, out = h.run(["--resume", RECORD_ID], run_point)
            self.assertEqual(rc, 0, out)
            # Exactly the four points the first segment never reached.
            self.assertEqual(seen, all_ids[2:])

            rows = _table_rows(h.record_path.read_text())
            self.assertEqual(len(rows), len(all_ids))
            self.assertEqual(sum("first segment" in r for r in rows), 2)
            self.assertEqual(sum("second segment" in r for r in rows), 4)
            # The first two rows are still the first two points, in order.
            self.assertIn("first segment", rows[0])
            self.assertIn("first segment", rows[1])
            self.assertIn("second segment", rows[2])

            # A completed record leaves no checkpoint behind: a surviving
            # checkpoint always means "interrupted, no record".
            self.assertFalse(h.checkpoint_path.exists())
            self.assertIn("**Execution**", h.record_path.read_text())
            self.assertIn("2 segment(s)", h.record_path.read_text())

    def test_resume_after_a_manifest_change_fails_loudly(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            with self.assertRaises(KeyboardInterrupt):
                h.run([], self._kill_after(2))

            changed = dict(MANIFEST, supply_nominal=1.62)
            h.write_manifest(changed)

            seen, run_point = self._recorder()
            rc, out = h.run(["--resume", RECORD_ID], run_point)
            self.assertEqual(rc, 1)
            self.assertIn("refusing to resume", out)
            self.assertIn("manifest", out)
            self.assertEqual(seen, [])
            self.assertFalse(h.record_path.exists())

    def test_resume_after_a_netlist_change_fails_loudly(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            with self.assertRaises(KeyboardInterrupt):
                h.run([], self._kill_after(2))

            seen, run_point = self._recorder()
            rc, out = h.run(
                ["--resume", RECORD_ID], run_point, netlist=NETLIST + "* edited DUT\n"
            )
            self.assertEqual(rc, 1)
            self.assertIn("netlisted DUT", out)
            self.assertEqual(seen, [])
            self.assertFalse(h.record_path.exists())

    def test_resume_with_a_different_point_list_fails_loudly(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            with self.assertRaises(KeyboardInterrupt):
                h.run([], self._kill_after(2))

            seen, run_point = self._recorder()
            rc, out = h.run(
                [
                    "--resume",
                    RECORD_ID,
                    "--corners",
                    "tt",
                    "--subset-reason",
                    "a narrower grid than the checkpoint's",
                ],
                run_point,
            )
            self.assertEqual(rc, 1)
            self.assertIn("point/trial list", out)
            self.assertEqual(seen, [])
            self.assertFalse(h.record_path.exists())

    def test_a_corrupted_checkpoint_aborts_instead_of_resuming(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            with self.assertRaises(KeyboardInterrupt):
                h.run([], self._kill_after(2))

            # The shape a torn write would have had, if the atomic save did
            # not rule it out: valid JSON prefix, truncated body.
            text = h.checkpoint_path.read_text()
            h.checkpoint_path.write_text(text[: len(text) // 2])

            seen, run_point = self._recorder()
            rc, out = h.run(["--resume", RECORD_ID], run_point)
            self.assertEqual(rc, 1)
            self.assertIn("not valid JSON", out)
            self.assertEqual(seen, [])
            self.assertFalse(h.record_path.exists())

    def test_resume_without_a_checkpoint_fails_loudly(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            seen, run_point = self._recorder()
            rc, out = h.run(["--resume", RECORD_ID], run_point)
            self.assertEqual(rc, 1)
            self.assertIn("no checkpoint", out)
            self.assertEqual(seen, [])

    def test_resume_is_rejected_with_no_write(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            seen, run_point = self._recorder()
            rc, out = h.run(["--resume", RECORD_ID, "--no-write"], run_point)
            self.assertEqual(rc, 1)
            self.assertIn("--resume", out)
            self.assertEqual(seen, [])

    def test_a_fresh_run_refuses_to_clobber_an_existing_checkpoint(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            with self.assertRaises(KeyboardInterrupt):
                h.run([], self._kill_after(2))

            # Same record id (same second, same commit) with no --resume: the
            # earlier campaign's progress must not be silently overwritten.
            seen, run_point = self._recorder()
            rc, out = h.run([], run_point)
            self.assertEqual(rc, 1)
            self.assertIn("already exists", out)
            self.assertEqual(seen, [])

    def test_an_existing_record_is_never_overwritten(self):
        import tempfile

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            return _point_result(point)

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            rc, _out = h.run([], run_point)
            self.assertEqual(rc, 0)
            original = h.record_path.read_text()

            seen, run_point_2 = self._recorder()
            rc, out = h.run([], run_point_2)
            self.assertEqual(rc, 1)
            self.assertIn("append-only", out)
            self.assertEqual(seen, [])
            self.assertEqual(h.record_path.read_text(), original)

    def test_resuming_an_already_completed_record_fails_loudly(self):
        import tempfile

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            return _point_result(point)

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            self.assertEqual(h.run([], run_point)[0], 0)
            seen, run_point_2 = self._recorder()
            rc, out = h.run(["--resume", RECORD_ID], run_point_2)
            self.assertEqual(rc, 1)
            self.assertIn("append-only", out)
            self.assertEqual(seen, [])

    def test_no_write_run_leaves_no_checkpoint(self):
        import tempfile

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            return _point_result(point)

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            rc, _out = h.run(["--no-write"], run_point)
            self.assertEqual(rc, 0)
            self.assertFalse((h.exp_dir / "corners").exists())

    def test_resume_of_a_parallel_run_still_completes_every_point(self):
        import tempfile

        all_ids = [p.corner_id for p in corners.build_matrix(MANIFEST, _StubPdk.process_corners)]
        lock = threading.Lock()
        first_seen = []

        def kill_after_two(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            with lock:
                if len(first_seen) >= 2:
                    raise KeyboardInterrupt("simulated host kill, mid-point")
                first_seen.append(point.corner_id)
            return _point_result(point, reason="first segment")

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            with self.assertRaises(KeyboardInterrupt):
                h.run(["-j", "2"], kill_after_two)

            _header, done = checkpoint_mod.load(h.checkpoint_path)
            self.assertTrue(0 < len(done) <= 2)

            seen, run_point = self._recorder()
            rc, out = h.run(["--resume", RECORD_ID, "-j", "3"], run_point)
            self.assertEqual(rc, 0, out)
            # Union of both segments is the whole grid, with no point run
            # twice across them.
            self.assertEqual(set(done) & set(seen), set())
            self.assertEqual(sorted(list(done) + seen), sorted(all_ids))
            rows = _table_rows(h.record_path.read_text())
            self.assertEqual(len(rows), len(all_ids))


class CheckpointFileTests(unittest.TestCase):
    """The checkpoint file's own contract, independent of the CLI."""

    POINT = corners.PvtPoint(corner="tt", temp_c=27.0, supply_v=1.8)
    FINGERPRINT = {
        "mode": "pvt",
        "manifest_sha256": "a" * 64,
        "netlist_sha256": "b" * 64,
        "pdk_variant": "sky130A",
        "pdk_commit": "c" * 40,
        "units": ["tt_27c_1.80v"],
    }

    def _tmp_path(self, tmp):
        return Path(tmp) / checkpoint_mod.CHECKPOINT_NAME

    def test_round_trips_a_measurement_bearing_result(self):
        import tempfile

        measurement = measure_mod.Measurement(
            label="vctrl=0.900",
            oscillating=True,
            freq_hz=2.5e8,
            duty_cycle=0.503,
            locked=True,
            lock_time_s=1.2e-6,
            final_freq_hz=2.5e8,
            note="locked",
            passed=True,
        )
        result = runner.PointResult(
            point=self.POINT, passed=True, reason="ok", measurements=(measurement,)
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._tmp_path(tmp)
            ckpt = checkpoint_mod.start(
                path, record_id=RECORD_ID, slug="fake", fp=self.FINGERPRINT
            )
            ckpt.record(self.POINT.corner_id, result)

            _header, loaded = checkpoint_mod.load(path)
            self.assertEqual(loaded[self.POINT.corner_id], result)
            self.assertIsInstance(loaded[self.POINT.corner_id].measurements, tuple)

    def test_round_trips_an_ac_result_with_a_nested_gain_point(self):
        import tempfile

        gain = ac_mod.LoopGainPoint(
            label="nominal", icp_a=1e-5, kvco_hz_per_v=3e8, n_divide=25.0, basis="sim/vco record"
        )
        measurement = ac_mod.AcMeasurement(
            label="nominal",
            gain_point=gain,
            crossed=True,
            crossing_count=1,
            crossover_hz=5.0e5,
            phase_at_crossover_deg=-120.0,
            phase_margin_deg=60.0,
            gain_margin_db=None,
            gain_margin_hz=None,
            meets_pm_floor=True,
            meets_fc_ceiling=True,
            note="ok",
            passed=True,
        )
        result = runner.PointResult(
            point=self.POINT, passed=True, reason="ok", measurements=(measurement,)
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._tmp_path(tmp)
            ckpt = checkpoint_mod.start(path, record_id=RECORD_ID, slug="fake", fp=self.FINGERPRINT)
            ckpt.record(self.POINT.corner_id, result)
            _header, loaded = checkpoint_mod.load(path)
            self.assertEqual(loaded[self.POINT.corner_id], result)
            self.assertEqual(loaded[self.POINT.corner_id].measurements[0].gain_point, gain)

    def test_round_trips_a_monte_carlo_trial_result(self):
        import tempfile

        trial = mc_mod.McTrial(
            trial=1, seed=1, corner="tt", temp_c=27.0, supply_v=1.8, mismatch=True, process=False
        )
        result = runner.McTrialResult(trial=trial, passed=True, reason="ok")
        fp = dict(self.FINGERPRINT, mode="mc", units=[trial.corner_id])
        with tempfile.TemporaryDirectory() as tmp:
            path = self._tmp_path(tmp)
            ckpt = checkpoint_mod.start(path, record_id=RECORD_ID, slug="fake", fp=fp)
            ckpt.record(trial.corner_id, result)
            _header, loaded = checkpoint_mod.load(path)
            self.assertEqual(loaded[trial.corner_id], result)

    def test_every_save_leaves_a_complete_parseable_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._tmp_path(tmp)
            fp = dict(self.FINGERPRINT, units=[f"tt_{t}c_1.80v" for t in range(5)])
            ckpt = checkpoint_mod.start(path, record_id=RECORD_ID, slug="fake", fp=fp)
            for t in range(5):
                point = corners.PvtPoint(corner="tt", temp_c=float(t), supply_v=1.8)
                ckpt.record(point.corner_id, _point_result(point))
                # After every single save the file on disk is complete and
                # self-consistent -- that is what makes a kill at an
                # arbitrary instant safe.
                _header, loaded = checkpoint_mod.load(path)
                self.assertEqual(len(loaded), t + 1)
            # No temp files left behind by the atomic-rename dance.
            self.assertEqual(
                sorted(p.name for p in Path(tmp).iterdir()), [checkpoint_mod.CHECKPOINT_NAME]
            )

    def test_refuses_a_stale_schema_version(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._tmp_path(tmp)
            checkpoint_mod.start(path, record_id=RECORD_ID, slug="fake", fp=self.FINGERPRINT)
            payload = json.loads(path.read_text())
            payload["schema_version"] = checkpoint_mod.SCHEMA_VERSION + 1
            path.write_text(json.dumps(payload))
            with self.assertRaises(checkpoint_mod.CheckpointError) as ctx:
                checkpoint_mod.load(path)
            self.assertIn("schema version", str(ctx.exception))

    def test_refuses_a_result_filed_under_the_wrong_unit(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._tmp_path(tmp)
            ckpt = checkpoint_mod.start(path, record_id=RECORD_ID, slug="fake", fp=self.FINGERPRINT)
            ckpt.record(self.POINT.corner_id, _point_result(self.POINT))
            payload = json.loads(path.read_text())
            payload["completed"][0]["unit_id"] = "ss_125c_1.62v"
            path.write_text(json.dumps(payload))
            with self.assertRaises(checkpoint_mod.CheckpointError) as ctx:
                checkpoint_mod.load(path)
            self.assertIn("files a result for", str(ctx.exception))

    def test_refuses_a_duplicated_unit(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._tmp_path(tmp)
            ckpt = checkpoint_mod.start(path, record_id=RECORD_ID, slug="fake", fp=self.FINGERPRINT)
            ckpt.record(self.POINT.corner_id, _point_result(self.POINT))
            payload = json.loads(path.read_text())
            payload["completed"].append(payload["completed"][0])
            path.write_text(json.dumps(payload))
            with self.assertRaises(checkpoint_mod.CheckpointError) as ctx:
                checkpoint_mod.load(path)
            self.assertIn("twice", str(ctx.exception))

    def test_refuses_a_result_dataclass_that_has_drifted(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._tmp_path(tmp)
            ckpt = checkpoint_mod.start(path, record_id=RECORD_ID, slug="fake", fp=self.FINGERPRINT)
            ckpt.record(self.POINT.corner_id, _point_result(self.POINT))
            payload = json.loads(path.read_text())
            payload["completed"][0]["result"]["fields"].pop("reason")
            path.write_text(json.dumps(payload))
            with self.assertRaises(checkpoint_mod.CheckpointError) as ctx:
                checkpoint_mod.load(path)
            self.assertIn("harness changed", str(ctx.exception))

    def test_refuses_a_checkpoint_from_another_record(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._tmp_path(tmp)
            checkpoint_mod.start(path, record_id=RECORD_ID, slug="fake", fp=self.FINGERPRINT)
            with self.assertRaises(checkpoint_mod.CheckpointError):
                checkpoint_mod.resume(
                    path, record_id="20991231-235959-fffffff", slug="fake", fp=self.FINGERPRINT
                )

    def test_refuses_a_result_for_a_unit_this_run_did_not_request(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._tmp_path(tmp)
            ckpt = checkpoint_mod.start(path, record_id=RECORD_ID, slug="fake", fp=self.FINGERPRINT)
            ckpt.record(self.POINT.corner_id, _point_result(self.POINT))
            narrowed = dict(self.FINGERPRINT, units=["ss_125c_1.62v"])
            with self.assertRaises(checkpoint_mod.CheckpointError):
                checkpoint_mod.resume(path, record_id=RECORD_ID, slug="fake", fp=narrowed)

    def test_fingerprint_separates_pvt_from_monte_carlo(self):
        point_fp = checkpoint_mod.fingerprint(
            mode="pvt", manifest=MANIFEST, netlist_text=NETLIST, pdk=_StubPdk(), units=[self.POINT]
        )
        mc_fp = checkpoint_mod.fingerprint(
            mode="mc", manifest=MANIFEST, netlist_text=NETLIST, pdk=_StubPdk(), units=[self.POINT]
        )
        self.assertNotEqual(point_fp, mc_fp)

    def test_fingerprint_ignores_manifest_key_order_only(self):
        reordered = dict(reversed(list(MANIFEST.items())))
        same = checkpoint_mod.fingerprint(
            mode="pvt", manifest=reordered, netlist_text=NETLIST, pdk=_StubPdk(), units=[self.POINT]
        )
        base = checkpoint_mod.fingerprint(
            mode="pvt", manifest=MANIFEST, netlist_text=NETLIST, pdk=_StubPdk(), units=[self.POINT]
        )
        self.assertEqual(base, same)
        edited = checkpoint_mod.fingerprint(
            mode="pvt",
            manifest=dict(MANIFEST, temps_c=[27]),
            netlist_text=NETLIST,
            pdk=_StubPdk(),
            units=[self.POINT],
        )
        self.assertNotEqual(base["manifest_sha256"], edited["manifest_sha256"])

    def test_record_refuses_a_mismatched_unit_id(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._tmp_path(tmp)
            ckpt = checkpoint_mod.start(path, record_id=RECORD_ID, slug="fake", fp=self.FINGERPRINT)
            with self.assertRaises(checkpoint_mod.CheckpointError):
                ckpt.record("ss_125c_1.62v", _point_result(self.POINT))


class StaleArtifactTests(unittest.TestCase):
    """A retried unit must never be able to read its previous attempt's
    waveform dump back -- that is how a resumed run could otherwise attribute
    an older simulation's measurements to a point that just timed out."""

    def test_purge_only_touches_the_named_units_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for name in (
                "tt_27c_1.80v.spice",
                "tt_27c_1.80v.log",
                "tt_27c_1.80v-v-clk.dat",
                "ss_27c_1.80v.log",
                "ss_27c_1.80v-v-clk.dat",
                ".spiceinit",
            ):
                (work / name).write_text("x")

            runner.purge_unit_artifacts(work, "tt_27c_1.80v")

            left = sorted(p.name for p in work.iterdir())
            self.assertEqual(
                left, [".spiceinit", "ss_27c_1.80v-v-clk.dat", "ss_27c_1.80v.log"]
            )

    def test_a_rerun_clears_the_previous_attempts_dump_before_running(self):
        import subprocess
        import tempfile

        class _StubPdkEnv:
            def as_env(self):
                return {}

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "spiceinit-src").write_text("* stub spiceinit\n")
            stale = work / "x-v-clk.dat"
            stale.write_text("0 1\n")

            exc = subprocess.TimeoutExpired(cmd=["ngspice"], timeout=1, output="", stderr="")
            with mock.patch.object(runner.subprocess, "run", side_effect=exc):
                passed, reason, _log, _spice = runner._run_ngspice_and_judge(
                    _StubPdkEnv(), work / "spiceinit-src", "* patched\n.end\n", "x", work, timeout_s=1
                )
            self.assertFalse(passed)
            self.assertIn("timeout", reason)
            self.assertFalse(stale.exists())


class CpDispatchTests(unittest.TestCase):
    """`cp` is a third, mutually exclusive analysis branch of prepare/run_point."""

    POINT = corners.PvtPoint(corner="tt", temp_c=27.0, supply_v=1.8)

    def _run(self, work, **kw):
        return runner.run_point(
            _StubPdk(), Path("/unused"), CP_MANIFEST, NETLIST, self.POINT, work,
            execute=cp_execute(**kw),
        )

    def test_prepare_point_injects_the_cp_control_block_with_the_unit_prefix(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            unit = runner.prepare_point(CP_MANIFEST, NETLIST, self.POINT, Path(tmp))
        spec = cp_spec()
        self.assertEqual(unit.completion_marker, cp_mod.COMPLETION_MARKER)
        self.assertEqual(unit.timeout_s, spec.timeout_s)
        self.assertIn(cp_mod.COMPLETION_MARKER, unit.netlist_text)
        for name in cp_mod.waveform_names(spec, f"{self.POINT.corner_id}-"):
            self.assertIn(name, unit.netlist_text)
        # supply is patched per point and the control block uses that supply
        self.assertIn(".temp 27", unit.netlist_text)
        self.assertTrue(unit.netlist_text.index(".endc") < unit.netlist_text.rindex(".end"))

    def test_prepare_point_is_pure(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            a = runner.prepare_point(CP_MANIFEST, NETLIST, self.POINT, Path(tmp))
            b = runner.prepare_point(CP_MANIFEST, NETLIST, self.POINT, Path(tmp))
        self.assertEqual(a, b)

    def test_conflicting_analysis_blocks_are_rejected_before_any_run(self):
        import copy
        import tempfile

        for other, block in (
            ("measure", {"node": "x", "tran_step": "1n", "tran_stop": "1u"}),
            ("ac", {"node": "x"}),
        ):
            m = copy.deepcopy(CP_MANIFEST)
            m[other] = block
            with self.subTest(other=other), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(cp_mod.CpError) as ctx:
                    runner.prepare_point(m, NETLIST, self.POINT, Path(tmp))
                self.assertIn("exactly one analysis block", str(ctx.exception))
                with self.assertRaises(cp_mod.CpError):
                    runner.run_point(
                        _StubPdk(), Path("/unused"), m, NETLIST, self.POINT, Path(tmp),
                        execute=cp_execute(),
                    )

    def test_a_cp_manifest_is_not_silently_run_as_a_monte_carlo_plumbing_check(self):
        import tempfile

        trial = mc_mod.McTrial(
            trial=1, seed=1, corner="tt", temp_c=27.0, supply_v=1.8,
            mismatch=True, process=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(cp_mod.CpError):
                runner.prepare_mc_trial(CP_MANIFEST, NETLIST, trial, Path(tmp))
            with self.assertRaises(cp_mod.CpError):
                runner.run_mc_trial(
                    _StubPdk(), Path("/unused"), CP_MANIFEST, NETLIST, trial, Path(tmp)
                )

    def test_complete_run_reduces_every_dump_through_the_seam(self):
        import tempfile

        spec = cp_spec()
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            res = self._run(work)
            self.assertTrue(res.passed, res.reason)
            self.assertEqual(res.reason, "ok")
            (sweep,) = res.measurements
            self.assertIsInstance(sweep, cp_mod.CpSweepResult)
            self.assertAlmostEqual(sweep.vdd, 1.8)
            # reduction == reducing the very same files directly
            prefix = f"{self.POINT.corner_id}-"
            dumps = {n: (work / n).read_text() for n in cp_mod.waveform_names(spec, prefix)}
            self.assertEqual(sweep, cp_mod.reduce_cp_sweep(spec, 1.8, dumps, prefix))
            self.assertTrue(sweep.op.available)
            self.assertEqual(len(sweep.points), 3 * 5)
            self.assertEqual(len(sweep.diagnostic_points), 3)
            self.assertEqual(len(sweep.resolution), 3)

    def test_missing_dump_fails_the_unit_and_keeps_coordinates(self):
        import tempfile

        spec = cp_spec()
        prefix = f"{self.POINT.corner_id}-"
        gone = cp_mod.sweep_dump_name(1, 3, prefix)
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(Path(tmp), drop={gone})
        self.assertFalse(res.passed)
        self.assertIn(gone, res.reason)
        (sweep,) = res.measurements
        bad = sweep.point(1, 3)
        self.assertFalse(bad.available)
        self.assertEqual(bad.coord.vctrl_fraction, 0.5)
        self.assertAlmostEqual(bad.coord.offset_s, spec.phase_offsets_s[3])
        self.assertTrue(sweep.point(1, 2).available)

    def test_missing_op_or_diagnostic_dump_also_fails_the_unit(self):
        import tempfile

        spec = cp_spec()
        prefix = f"{self.POINT.corner_id}-"
        vi, pj = spec.diagnostic_coordinates()[0]
        for gone in (
            cp_mod.op_dump_name(prefix),
            cp_mod.sweep_dump_name(vi, pj, prefix, diagnostic=True),
        ):
            with self.subTest(gone=gone), tempfile.TemporaryDirectory() as tmp:
                res = self._run(Path(tmp), drop={gone})
                self.assertFalse(res.passed)
                self.assertIn(gone, res.reason)

    def test_unparseable_dump_fails_with_its_reason(self):
        import tempfile

        spec = cp_spec()
        prefix = f"{self.POINT.corner_id}-"
        victim = cp_mod.sweep_dump_name(0, 0, prefix)
        base = cp_execute()

        def execute(unit):
            out = base(unit)
            (unit.work_dir / victim).write_text("0 nan 0 0\n1 2 3 4\n")
            return out

        with tempfile.TemporaryDirectory() as tmp:
            res = runner.run_point(
                _StubPdk(), Path("/unused"), CP_MANIFEST, NETLIST, self.POINT,
                Path(tmp), execute=execute,
            )
        self.assertFalse(res.passed)
        self.assertIn("incomplete", res.reason)
        self.assertFalse(res.measurements[0].point(0, 0).available)
        self.assertEqual(spec.vctrl_fractions[0], res.measurements[0].point(0, 0).coord.vctrl_fraction)

    def test_timeout_and_ngspice_errors_keep_the_shared_judge(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(Path(tmp), timed_out=True, rc=-1, log="")
            self.assertFalse(res.passed)
            self.assertIn(f"{cp_spec().timeout_s} s per-point timeout", res.reason)
            self.assertEqual(res.measurements, ())
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(Path(tmp), log="Error: singular matrix\n" + CP_LOG)
            self.assertFalse(res.passed)
            self.assertIn("singular matrix", res.reason)
            self.assertEqual(res.measurements, ())
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(Path(tmp), log="Total analysis time = 1\n")  # wrong marker
            self.assertFalse(res.passed)
            self.assertIn(cp_mod.COMPLETION_MARKER, res.reason)

    def test_unavailable_plateau_is_reported_but_is_not_an_execution_failure(self):
        import tempfile

        # A flat zero current never produces a valid plateau/compliance window,
        # yet the dumps are complete: execution passes, availability says no.
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(Path(tmp), iup=0.0)
            (sweep,) = res.measurements
            self.assertTrue(res.passed, res.reason)
            self.assertFalse(sweep.compliance.both.available)

    def test_stale_dumps_of_an_interrupted_attempt_cannot_satisfy_a_rerun(self):
        import subprocess
        import tempfile

        spec = cp_spec()
        prefix = f"{self.POINT.corner_id}-"
        gone = cp_mod.sweep_dump_name(2, 4, prefix)

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "spiceinit-src").write_text("* stub\n")
            # The interrupted attempt left a complete, different set behind.
            for name, text in cp_dump_texts(spec, prefix, iup=50e-6).items():
                (work / name).write_text(text)
            self.assertTrue((work / gone).is_file())

            def fake_ngspice(cmd, **kw):
                # the rerun writes everything except one dump
                for name, text in cp_dump_texts(spec, prefix, drop={gone}).items():
                    (Path(kw["cwd"]) / name).write_text(text)
                return subprocess.CompletedProcess(cmd, 0, stdout=CP_LOG, stderr="")

            backend = executor_mod.LocalBackend(pdk=_StubPdk(), spiceinit=work / "spiceinit-src")
            with mock.patch.object(runner.subprocess, "run", side_effect=fake_ngspice):
                res = runner.run_point(
                    _StubPdk(), work / "spiceinit-src", CP_MANIFEST, NETLIST, self.POINT,
                    work, execute=backend.execute,
                )
            self.assertFalse(res.passed)
            self.assertIn(gone, res.reason)
            (sweep,) = res.measurements
            self.assertFalse(sweep.point(2, 4).available)
            self.assertIn("dump missing", sweep.point(2, 4).reason)
            # the rest is the new attempt's data (100 uA), not the stale 50 uA
            pl = sweep.point(1, spec.offset_index(25e-9)).plateau
            self.assertAlmostEqual(pl.current_a, 100e-6, delta=1e-9)


class CpResumeTests(unittest.TestCase):
    """Interrupted CP campaign resumes to the same reduced output as an
    uninterrupted one, through the real checkpoint file."""

    def _stub(self, seen, kill_after=None, stale_first=False):
        real = runner.run_point
        state = {"done": 0}

        def run_point(pdk, spiceinit, manifest, netlist_text, point, work_dir):
            if kill_after is not None and state["done"] >= kill_after:
                if stale_first:
                    # a half-written attempt at the next unit: some dumps, no result
                    work_dir.mkdir(parents=True, exist_ok=True)
                    for name, text in list(
                        cp_dump_texts(cp_spec(), f"{point.corner_id}-", iup=50e-6).items()
                    )[:5]:
                        (work_dir / name).write_text(text)
                raise KeyboardInterrupt("simulated host kill, mid-unit")
            state["done"] += 1
            res = real(pdk, spiceinit, manifest, netlist_text, point, work_dir,
                       execute=cp_execute())
            seen[point.corner_id] = res
            return res

        return run_point

    def test_resumed_results_equal_uninterrupted_results(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            clean = {}
            ha = _Harness(Path(tmp_a), manifest=CP_MANIFEST)
            rc, out = ha.run([], self._stub(clean))
            self.assertEqual(rc, 0, out)
            self.assertEqual(len(clean), 6)

            hb = _Harness(Path(tmp_b), manifest=CP_MANIFEST)
            first = {}
            with self.assertRaises(KeyboardInterrupt):
                hb.run([], self._stub(first, kill_after=2, stale_first=True))
            self.assertFalse(hb.record_path.exists())
            _hdr, done = checkpoint_mod.load(hb.checkpoint_path)
            self.assertEqual(sorted(done), sorted(first))
            # nested CP dataclass types were restored, not flattened
            sweep = next(iter(done.values())).measurements[0]
            self.assertIsInstance(sweep, cp_mod.CpSweepResult)
            self.assertIsInstance(sweep.points[0].coord, cp_mod.CpCoordinate)
            self.assertIsInstance(sweep.compliance.up, cp_mod.ComplianceWindow)

            second = {}
            rc, out = hb.run(["--resume", RECORD_ID], self._stub(second))
            self.assertEqual(rc, 0, out)
            self.assertEqual(sorted(second), sorted(set(clean) - set(first)))

            merged = {**done, **second}
            self.assertEqual(merged, clean)
            text = hb.record_path.read_text()
            self.assertIn("2 segment(s)", text)
            self.assertIn("Resolution diagnostic", text)
            self.assertFalse(hb.checkpoint_path.exists())

    def test_cli_rejects_conflicting_blocks_before_any_unit_runs(self):
        import copy
        import tempfile

        m = copy.deepcopy(CP_MANIFEST)
        m["ac"] = {"node": "x"}
        called = []
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp), manifest=m)

            def run_point(*a, **k):
                called.append(a)

            rc, out = h.run([], run_point)
        self.assertEqual(rc, 1)
        self.assertIn("exactly one analysis block", out)
        self.assertEqual(called, [])

    def test_cli_rejects_cp_in_monte_carlo_mode(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp), manifest=CP_MANIFEST)
            rc, out = h.run(["--mc"], lambda *a, **k: None)
        self.assertEqual(rc, 1)
        self.assertIn("no Monte Carlo mode", out)


class CpCheckpointRoundTripTests(unittest.TestCase):
    POINT = corners.PvtPoint(corner="tt", temp_c=27.0, supply_v=1.8)

    def test_unavailable_entries_reasons_and_resolution_deltas_survive(self):
        import tempfile

        spec = cp_spec()
        prefix = f"{self.POINT.corner_id}-"
        gone = cp_mod.sweep_dump_name(0, 1, prefix)
        dumps = cp_dump_texts(spec, prefix, drop={gone, cp_mod.op_dump_name(prefix)})
        sweep = cp_mod.reduce_cp_sweep(spec, 1.8, dumps, prefix)
        result = runner.PointResult(self.POINT, False, "incomplete", (sweep,))
        fp = CheckpointFileTests.FINGERPRINT
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / checkpoint_mod.CHECKPOINT_NAME
            ckpt = checkpoint_mod.start(path, record_id=RECORD_ID, slug="fake", fp=fp)
            ckpt.record(self.POINT.corner_id, result)
            _h, loaded = checkpoint_mod.load(path)
        back = loaded[self.POINT.corner_id]
        self.assertEqual(back, result)
        got = back.measurements[0]
        self.assertFalse(got.op.available)
        self.assertIn("dump missing", got.op.reason)
        self.assertIn("dump missing", got.point(0, 1).reason)
        self.assertEqual(got.point(0, 1).coord, sweep.point(0, 1).coord)
        self.assertEqual(got.resolution, sweep.resolution)
        self.assertEqual(got.diagnostic_points, sweep.diagnostic_points)
        self.assertEqual(got.slopes, sweep.slopes)


if __name__ == "__main__":
    unittest.main()
