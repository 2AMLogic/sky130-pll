#!/usr/bin/env python3
"""Executor-seam tests for sim/harness (issue #146): `--executor local`
(unchanged) vs. `--executor remote` (klayout-tools' Spot fleet), and every
way a remote request is allowed to degrade into a local one.

    python3 -m unittest discover -s sim/tests -v

Hermetic by construction: no PDK, no ngspice, no `klayout_tools` install, no
AWS CLI call, no network, no credential read. The remote path is exercised
against a **fake** `klayout_tools` package installed into `sys.modules` for
the duration of a test -- the same technique klayout-tools' own
`tests/test_remote_transport.py` uses with its `_FakeRunner`. The fake
implements the real push/run/pull contract (`JobDescription`/`JobInput`,
`push_job`, `run_remote_job`, `pull_artifacts`, `run_fleet`) closely enough
that the harness cannot tell the difference, and it writes the per-unit logs
a real fleet member would have left behind -- so what is under test is
exactly the seam: *which* netlist got packaged, *where* its log was read
from, and *that the judge never changed*.

The properties pinned here are the ones a plausible-looking but wrong
implementation would silently violate:

  - `--executor local` is not merely the default but the *same call* it
    always was -- no new keyword reaches `run_point`, and the record is
    byte-for-byte a pre-#146 record;
  - a remote unit is judged by the identical criterion a local one is, over
    the log the fleet actually produced;
  - every remote refusal (no klayout_tools, no region/key/profile, no aws
    CLI, a quota or cost-gate refusal, a lost shard) falls back to local with
    **exactly one** logged line and a `fallback_reason` in the record -- and
    the run's exit status and record shape are a local run's;
  - a remote run's record carries executor, region, instance type, spot flag
    and the launcher's cost estimate, so the spend is auditable;
  - this host's absolute PDK paths never reach the remote box unrewritten.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR))

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


class _FakeRemoteLaunchError(Exception):
    pass


class _FakeFleetLaunchError(_FakeRemoteLaunchError):
    pass


class _FakeFleetQuotaError(_FakeFleetLaunchError):
    pass


class _FakeTransportError(Exception):
    pass


@dataclass(frozen=True)
class _JobInput:
    remote_name: str
    label: str
    local_path: str | None = None
    content: str | None = None


@dataclass(frozen=True)
class _JobDescription:
    label: str
    inputs: tuple
    command: str
    success_exit_codes: tuple = (0,)
    parse_json_stdout: bool = True
    artifacts_relative_dir: str | None = None


@dataclass
class _ShardOutcome:
    shard_index: int
    status: str
    result: object = None
    error: str | None = None
    attempts: int = 1
    environment: dict | None = None


@dataclass
class _FleetResult:
    shards: list
    hosts_launched: int = 0
    terminated_instance_ids: list = field(default_factory=list)


class _FakeFleet:
    """Records every call the harness makes, and simulates one fleet member
    per shard: the pushed `<id>.spice` files are "run" (producing the log the
    caller seeded) and pulled back into the caller's own work directory."""

    def __init__(self, *, log_for=None, raise_on_run=None, lose_shard=None):
        self.calls: list = []
        self.jobs: dict = {}
        self.pushed: list = []
        self.run_fleet_kwargs: dict | None = None
        self._log_for = log_for or (lambda corner_id: (GOOD_LOG, 0))
        self._raise_on_run = raise_on_run
        self._lose_shard = lose_shard

    # -- transport ------------------------------------------------------- #

    def wait_for_ssh(self, host, **kw):
        self.calls.append(("wait_for_ssh", host))

    def job_dir(self, user, job_id):
        return f"/home/{user}/{job_id}"

    def push_job(self, *, host, remote_job_dir, job, **kw):
        self.calls.append(("push_job", remote_job_dir))
        self.jobs[remote_job_dir] = job
        self.pushed.append(job)

    def run_remote_job(self, *, host, remote_job_dir, job, timeout_s, **kw):
        self.calls.append(("run_remote_job", job.command, timeout_s))
        return ""

    def pull_artifacts(self, *, host, remote_job_dir, local_artifacts_dir, job, **kw):
        self.calls.append(("pull_artifacts", local_artifacts_dir))
        out = Path(local_artifacts_dir)
        out.mkdir(parents=True, exist_ok=True)
        for item in job.inputs:
            if not item.remote_name.endswith(".spice"):
                continue
            corner_id = item.remote_name[: -len(".spice")]
            log_text, rc = self._log_for(corner_id)
            (out / f"{corner_id}.log").write_text(log_text)
            (out / f"{corner_id}.rc").write_text(f"{rc}\n")

    def cleanup_job(self, **kw):
        self.calls.append(("cleanup_job",))

    # -- fleet ----------------------------------------------------------- #

    def run_fleet(self, **kwargs):
        self.run_fleet_kwargs = kwargs
        if self._raise_on_run is not None:
            raise self._raise_on_run
        shard_runner = kwargs["shard_runner"]
        outcomes = []
        for index, _count in enumerate(kwargs["shard_unit_counts"]):
            if self._lose_shard == index:
                outcomes.append(
                    _ShardOutcome(index, "error", error="spot reclaimed twice")
                )
                continue
            result = shard_runner(index, object(), f"198.51.100.{index}")
            outcomes.append(
                _ShardOutcome(
                    index,
                    "ok",
                    result=result,
                    environment={
                        "provider": "aws",
                        "region": kwargs["region"],
                        "instance_type": "c7i.8xlarge",
                        "instance_id": f"i-{index:08d}",
                        "spot": kwargs["spot"],
                        "estimated_hourly_cost_usd": 0.51,
                        "ami_id": "ami-00000000",
                    },
                )
            )
        return _FleetResult(shards=outcomes, hosts_launched=len(outcomes))


@contextlib.contextmanager
def _fake_klayout_tools(fleet: _FakeFleet):
    """Install a fake `klayout_tools` package for the duration of a test."""
    pkg = types.ModuleType("klayout_tools")
    transport = types.ModuleType("klayout_tools.remote_transport")
    transport.DEFAULT_SSH_USER = "ubuntu"
    transport.JobInput = _JobInput
    transport.JobDescription = _JobDescription
    transport.RemoteTransportError = _FakeTransportError
    for name in (
        "wait_for_ssh",
        "job_dir",
        "push_job",
        "run_remote_job",
        "pull_artifacts",
        "cleanup_job",
    ):
        setattr(transport, name, getattr(fleet, name))

    fleet_mod = types.ModuleType("klayout_tools.remote_fleet")
    fleet_mod.run_fleet = fleet.run_fleet
    fleet_mod.FleetLaunchError = _FakeFleetLaunchError
    fleet_mod.FleetQuotaError = _FakeFleetQuotaError

    launcher = types.ModuleType("klayout_tools.remote_launcher")
    launcher.RemoteLaunchError = _FakeRemoteLaunchError

    pkg.remote_transport = transport
    pkg.remote_fleet = fleet_mod
    pkg.remote_launcher = launcher

    added = {
        "klayout_tools": pkg,
        "klayout_tools.remote_transport": transport,
        "klayout_tools.remote_fleet": fleet_mod,
        "klayout_tools.remote_launcher": launcher,
    }
    saved = {k: sys.modules.get(k) for k in added}
    sys.modules.update(added)
    try:
        yield
    finally:
        for key, previous in saved.items():
            if previous is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = previous


@contextlib.contextmanager
def _unimportable_klayout_tools():
    """`sys.modules[name] = None` makes `import name` raise ImportError."""
    saved = {
        k: sys.modules.get(k)
        for k in list(sys.modules)
        if k == "klayout_tools" or k.startswith("klayout_tools.")
    }
    for key in list(saved):
        sys.modules.pop(key, None)
    sys.modules["klayout_tools"] = None
    try:
        yield
    finally:
        sys.modules.pop("klayout_tools", None)
        sys.modules.update({k: v for k, v in saved.items() if v is not None})


# --------------------------------------------------------------------------- #
# Harness
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
            mock.patch.dict("os.environ", env or {}, clear=False),
        ]
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                rc = cli.main([str(self.testbench)] + argv)
        return rc, out.getvalue()


def _table_rows(record_text: str) -> list:
    return [
        line.strip()
        for line in record_text.splitlines()
        if line.strip().startswith("| ") and ("PASS" in line or "FAIL" in line)
    ]


def _provisioned_env(tmp: Path, **overrides) -> dict:
    """A fully-provisioned-looking host, entirely inside `tmp`.

    Nothing here is a real credential: the "SSH key" is an empty temp file
    and the AWS config is a temp ini holding one section header and no keys.
    `AWS_CONFIG_FILE`/`AWS_SHARED_CREDENTIALS_FILE` are redirected so the
    machine's own `~/.aws` is never opened by a test.
    """
    key = tmp / "fleet-key.pem"
    key.write_text("")
    aws_config = tmp / "aws-config"
    aws_config.write_text("[profile fleet-sim]\nregion = us-west-2\n")
    env = {
        "SKY130_PLL_REMOTE_REGION": "us-west-2",
        "SKY130_PLL_REMOTE_KEY_NAME": "fleet-keypair",
        "SKY130_PLL_REMOTE_SSH_KEY": str(key),
        "SKY130_PLL_REMOTE_AWS_PROFILE": "fleet-sim",
        "SKY130_PLL_REMOTE_LAUNCHER_CIDR": "198.51.100.7/32",
        "AWS_CONFIG_FILE": str(aws_config),
        "AWS_SHARED_CREDENTIALS_FILE": str(tmp / "aws-credentials-absent"),
    }
    env.update(overrides)
    return env


@contextlib.contextmanager
def _aws_on_path(present: bool = True):
    with mock.patch.object(
        executor_mod.shutil, "which", lambda name: "/usr/bin/aws" if present else None
    ):
        yield


# --------------------------------------------------------------------------- #
# local: unchanged
# --------------------------------------------------------------------------- #


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
                default.record_path.read_text(), explicit.record_path.read_text()
            )

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

    def test_an_unknown_executor_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = dict(MANIFEST, executor="batch")
            h = _Harness(Path(tmp), manifest=manifest)
            rc, out = h.run([])
            self.assertEqual(rc, 1)
            self.assertIn("unknown executor 'batch'", out)


# --------------------------------------------------------------------------- #
# remote: success
# --------------------------------------------------------------------------- #


class RemoteExecutorTests(unittest.TestCase):
    def _run_remote(self, argv=None, *, fleet=None, manifest=None, tmp=None, **envkw):
        fleet = fleet or _FakeFleet()
        h = _Harness(Path(tmp), manifest=manifest)
        with _fake_klayout_tools(fleet), _aws_on_path():
            rc, out = h.run(
                (argv or []) + ["--executor", "remote"],
                env=_provisioned_env(Path(tmp), **envkw),
            )
        return h, fleet, rc, out

    def test_units_run_on_the_fleet_and_never_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            h, fleet, rc, out = self._run_remote(tmp=tmp)
            self.assertEqual(rc, 0, out)
            self.assertEqual(h.local_calls, [])
            self.assertIn("push_job", [c[0] for c in fleet.calls])
            self.assertIn("pull_artifacts", [c[0] for c in fleet.calls])

    def test_record_carries_executor_region_instance_spot_and_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            h, _fleet, rc, out = self._run_remote(tmp=tmp)
            self.assertEqual(rc, 0, out)
            text = h.record_path.read_text()
            self.assertIn("**Execution**", text)
            self.assertIn("executor: `remote`", text)
            self.assertIn("region: `us-west-2`", text)
            self.assertIn("instance_type: `c7i.8xlarge`", text)
            self.assertIn("spot: `true`", text)
            self.assertIn("estimated_fleet_hourly_cost_usd: 0.51", text)
            self.assertNotIn("fallback_reason", text)

    def test_the_judge_reads_the_log_the_fleet_produced(self):
        """A remote unit whose collected log carries an `Error:` line FAILs,
        by the same criterion (and with the same wording) a local one does."""
        fleet = _FakeFleet(log_for=lambda cid: (ERROR_LOG, 0))
        with tempfile.TemporaryDirectory() as tmp:
            h, _fleet, rc, out = self._run_remote(tmp=tmp, fleet=fleet)
            self.assertEqual(rc, 1, out)
            rows = _table_rows(h.record_path.read_text())
            self.assertTrue(rows)
            for row in rows:
                self.assertIn("FAIL", row)
                self.assertIn("ngspice reported: Error: singular matrix", row)

    def test_a_remote_timeout_is_judged_as_this_manifests_timeout(self):
        fleet = _FakeFleet(log_for=lambda cid: ("partial output\n", 124))
        with tempfile.TemporaryDirectory() as tmp:
            h, _fleet, rc, out = self._run_remote(tmp=tmp, fleet=fleet)
            self.assertEqual(rc, 1, out)
            text = h.record_path.read_text()
            self.assertIn("exceeded this manifest's 300 s per-point timeout", text)

    def test_jobs_becomes_the_shard_count(self):
        manifest = dict(MANIFEST, process_corners=["tt", "ss"], temps_c=[-40, 27, 125])
        with tempfile.TemporaryDirectory() as tmp:
            h, fleet, rc, out = self._run_remote(
                ["--jobs", "3"], tmp=tmp, manifest=manifest
            )
            self.assertEqual(rc, 0, out)
            counts = fleet.run_fleet_kwargs["shard_unit_counts"]
            self.assertEqual(len(counts), 3)
            self.assertEqual(sum(counts), len(h.run_point_kwargs))

    def test_shard_count_never_exceeds_the_unit_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            _h, fleet, rc, out = self._run_remote(["--jobs", "64"], tmp=tmp)
            self.assertEqual(rc, 0, out)
            counts = fleet.run_fleet_kwargs["shard_unit_counts"]
            self.assertEqual(sum(counts), 3)  # tt x 27C x 3 supplies
            self.assertEqual(len(counts), 3)
            self.assertTrue(all(c >= 1 for c in counts))

    def test_the_job_description_packages_netlist_spiceinit_and_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            _h, fleet, rc, out = self._run_remote(tmp=tmp)
            self.assertEqual(rc, 0, out)
            job = fleet.pushed[0]
            names = [i.remote_name for i in job.inputs]
            self.assertIn(".spiceinit", names)
            self.assertIn("run-units.sh", names)
            self.assertTrue([n for n in names if n.endswith(".spice")])
            self.assertEqual(job.command, "sh run-units.sh")
            self.assertFalse(job.parse_json_stdout)
            self.assertEqual(job.artifacts_relative_dir, "artifacts")
            self.assertEqual(job.success_exit_codes, (0,))

    def test_this_hosts_pdk_paths_are_rerooted_onto_the_ami(self):
        with tempfile.TemporaryDirectory() as tmp:
            _h, fleet, rc, out = self._run_remote(tmp=tmp)
            self.assertEqual(rc, 0, out)
            job = fleet.pushed[0]
            decks = [i for i in job.inputs if i.remote_name.endswith(".spice")]
            self.assertTrue(decks)
            for deck in decks:
                self.assertNotIn(LOCAL_PDK_ROOT, deck.content)
                self.assertIn(
                    "/opt/pdk/sky130A/libs.tech/combined/sky130.lib.spice",
                    deck.content,
                )
                self.assertIn("/opt/pdk/sky130A/libs.ref/", deck.content)

    def test_the_shard_script_records_a_return_code_per_unit(self):
        units = [
            executor_mod.NgspiceUnit(
                corner_id="tt_27_1.80",
                netlist_text="*",
                work_dir=Path("/tmp"),
                completion_marker="Total analysis time",
                timeout_s=1800,
            )
        ]
        script = executor_mod._shard_script(units)
        self.assertIn("timeout 1800 ngspice -b tt_27_1.80.spice", script)
        self.assertIn("artifacts/tt_27_1.80.log", script)
        self.assertIn("artifacts/tt_27_1.80.rc", script)
        # A failing unit is data for the judge, never a transport failure.
        self.assertTrue(script.rstrip().endswith("exit 0"))

    def test_a_manifest_can_opt_in_and_the_flag_still_overrides_it(self):
        manifest = dict(MANIFEST, executor="remote")
        with tempfile.TemporaryDirectory() as tmp:
            h, fleet, rc, out = self._run_remote([], tmp=tmp, manifest=manifest)
            self.assertEqual(rc, 0, out)
            self.assertIsNotNone(fleet.run_fleet_kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            fleet = _FakeFleet()
            h = _Harness(Path(tmp), manifest=manifest)
            with _fake_klayout_tools(fleet), _aws_on_path():
                rc, out = h.run(
                    ["--executor", "local"], env=_provisioned_env(Path(tmp))
                )
            self.assertEqual(rc, 0, out)
            self.assertIsNone(fleet.run_fleet_kwargs)
            self.assertTrue(h.local_calls)


# --------------------------------------------------------------------------- #
# remote: fallback, never failure
# --------------------------------------------------------------------------- #


class RemoteFallbackTests(unittest.TestCase):
    """Every refusal path: one logged line, a `fallback_reason` in the
    record, and a local run's exit status and record shape."""

    def _assert_single_fallback_line(self, out: str) -> str:
        lines = [
            ln
            for ln in out.splitlines()
            if "--executor remote unavailable" in ln
        ]
        self.assertEqual(len(lines), 1, f"expected exactly one line, got: {lines}")
        return lines[0]

    def _assert_local_shape(self, h: _Harness, rc: int, out: str, *, reason_re: str):
        self.assertEqual(rc, 0, out)
        line = self._assert_single_fallback_line(out)
        self.assertRegex(line, reason_re)
        # Every unit actually ran here.
        expected = [
            p.corner_id
            for p in corners.build_matrix(MANIFEST, _StubPdk.process_corners)
        ]
        self.assertEqual(sorted(h.local_calls), sorted(expected))
        text = h.record_path.read_text()
        self.assertIn("fallback_reason", text)
        self.assertIn("executor: `local` (requested `remote`)", text)
        # ...and the rows are a local run's rows.
        with tempfile.TemporaryDirectory() as tmp:
            baseline = _Harness(Path(tmp))
            rc_baseline, _ = baseline.run([])
            self.assertEqual(rc, rc_baseline)
            self.assertEqual(
                _table_rows(text), _table_rows(baseline.record_path.read_text())
            )

    def test_klayout_tools_not_importable(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            with _unimportable_klayout_tools(), _aws_on_path():
                rc, out = h.run(
                    ["--executor", "remote"], env=_provisioned_env(Path(tmp))
                )
            self._assert_local_shape(
                h, rc, out, reason_re=r"klayout_tools is not importable"
            )

    def test_no_region_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            env = _provisioned_env(Path(tmp))
            env["SKY130_PLL_REMOTE_REGION"] = ""
            with _fake_klayout_tools(_FakeFleet()), _aws_on_path():
                rc, out = h.run(["--executor", "remote"], env=env)
            self._assert_local_shape(h, rc, out, reason_re=r"no region configured")

    def test_ssh_private_key_absent_on_this_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            env = _provisioned_env(Path(tmp))
            env["SKY130_PLL_REMOTE_SSH_KEY"] = str(Path(tmp) / "not-here.pem")
            with _fake_klayout_tools(_FakeFleet()), _aws_on_path():
                rc, out = h.run(["--executor", "remote"], env=env)
            self._assert_local_shape(
                h, rc, out, reason_re=r"SSH private key is not present"
            )

    def test_aws_profile_absent_on_this_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            env = _provisioned_env(Path(tmp))
            env["SKY130_PLL_REMOTE_AWS_PROFILE"] = "never-provisioned"
            with _fake_klayout_tools(_FakeFleet()), _aws_on_path():
                rc, out = h.run(["--executor", "remote"], env=env)
            self._assert_local_shape(
                h, rc, out, reason_re=r"AWS profile .* is not\s+configured"
            )

    def test_aws_cli_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            with _fake_klayout_tools(_FakeFleet()), _aws_on_path(False):
                rc, out = h.run(
                    ["--executor", "remote"], env=_provisioned_env(Path(tmp))
                )
            self._assert_local_shape(h, rc, out, reason_re=r"'aws' CLI is not on PATH")

    def test_launcher_quota_refusal(self):
        quota = _FakeFleetQuotaError(
            "fleet needs 64 vCPU; the account's Standard Spot quota is 32"
        )
        fleet = _FakeFleet(raise_on_run=quota)
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            with _fake_klayout_tools(fleet), _aws_on_path():
                rc, out = h.run(
                    ["--executor", "remote"], env=_provisioned_env(Path(tmp))
                )
            self._assert_local_shape(h, rc, out, reason_re=r"_FakeFleetQuotaError")
            self.assertIn("Standard Spot quota is 32", h.record_path.read_text())

    def test_cost_gate_refusal(self):
        gate = _FakeFleetLaunchError(
            "estimated fleet cost exceeds max_hourly_cost_usd"
        )
        fleet = _FakeFleet(raise_on_run=gate)
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            with _fake_klayout_tools(fleet), _aws_on_path():
                rc, out = h.run(
                    ["--executor", "remote"], env=_provisioned_env(Path(tmp))
                )
            self._assert_local_shape(h, rc, out, reason_re=r"max_hourly_cost_usd")

    def test_a_lost_shard_reruns_the_set_locally_rather_than_holing_the_record(self):
        fleet = _FakeFleet(lose_shard=0)
        with tempfile.TemporaryDirectory() as tmp:
            h = _Harness(Path(tmp))
            with _fake_klayout_tools(fleet), _aws_on_path():
                rc, out = h.run(
                    ["--executor", "remote", "--jobs", "2"],
                    env=_provisioned_env(Path(tmp)),
                )
            self.assertEqual(rc, 0, out)
            line = self._assert_single_fallback_line(out)
            self.assertIn("fleet shard(s) were lost", line)
            text = h.record_path.read_text()
            self.assertIn("fallback_reason", text)
            # No hole: every unit has a row, and every row came from a real run.
            self.assertEqual(len(_table_rows(text)), 3)
            self.assertEqual(len(h.local_calls), 3)


# --------------------------------------------------------------------------- #
# unit-level helpers
# --------------------------------------------------------------------------- #


class ExecutorHelperTests(unittest.TestCase):
    def _units(self, n):
        return [
            executor_mod.NgspiceUnit(
                corner_id=f"u{i}",
                netlist_text="*",
                work_dir=Path("/tmp"),
                completion_marker="m",
                timeout_s=10,
            )
            for i in range(n)
        ]

    def test_shards_are_contiguous_and_near_equal(self):
        shards = executor_mod._shard(self._units(7), 3)
        self.assertEqual([len(s) for s in shards], [3, 2, 2])
        flat = [u.corner_id for s in shards for u in s]
        self.assertEqual(flat, [f"u{i}" for i in range(7)])

    def test_more_hosts_than_units_is_clamped(self):
        shards = executor_mod._shard(self._units(2), 9)
        self.assertEqual([len(s) for s in shards], [1, 1])

    def test_shard_timeout_is_the_serial_worst_case_plus_slack(self):
        self.assertEqual(executor_mod._shard_timeout_s(self._units(3)), 330.0)

    def test_collect_maps_a_missing_log_to_a_failing_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            unit = executor_mod.NgspiceUnit(
                corner_id="tt_27_1.80",
                netlist_text="* deck\n",
                work_dir=Path(tmp),
                completion_marker="Total analysis time",
                timeout_s=300,
            )
            outcome = executor_mod._collect(unit)
            self.assertNotEqual(outcome.returncode, 0)
            passed, reason = runner.judge(outcome, unit.completion_marker, 300)
            self.assertFalse(passed)
            self.assertIn("did not print", reason)

    def test_collect_reads_the_pulled_log_and_return_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "tt_27_1.80.log").write_text(GOOD_LOG)
            (work / "tt_27_1.80.rc").write_text("0\n")
            unit = executor_mod.NgspiceUnit(
                corner_id="tt_27_1.80",
                netlist_text="* deck\n",
                work_dir=work,
                completion_marker="Total analysis time",
                timeout_s=300,
            )
            outcome = executor_mod._collect(unit)
            self.assertEqual(outcome.returncode, 0)
            passed, reason = runner.judge(outcome, unit.completion_marker, 300)
            self.assertTrue(passed)
            self.assertEqual(reason, "ok")
            # The rc sidecar is consumed, never left in the committed
            # corners/<record-id>/ directory.
            self.assertFalse((work / "tt_27_1.80.rc").exists())
            self.assertTrue(unit.spice_path.is_file())

    def test_remote_config_prefers_the_environment_over_the_manifest(self):
        manifest = {"remote": {"region": "us-east-1", "spot": False, "pdk_root": "/x"}}
        cfg = executor_mod.remote_config(
            manifest,
            {
                "SKY130_PLL_REMOTE_REGION": "us-west-2",
                "SKY130_PLL_REMOTE_SPOT": "true",
            },
        )
        self.assertEqual(cfg.region, "us-west-2")
        self.assertTrue(cfg.spot)
        self.assertEqual(cfg.pdk_root, "/x")

    def test_remote_config_defaults_are_spot_on_and_the_ami_pdk_root(self):
        cfg = executor_mod.remote_config({}, {})
        self.assertTrue(cfg.spot)
        self.assertEqual(cfg.pdk_root, executor_mod.DEFAULT_REMOTE_PDK_ROOT)
        self.assertIsNone(cfg.region)

    def test_the_repo_never_ships_a_credential_shaped_default(self):
        """Public-repo hygiene, mechanised: nothing account-identifying may
        appear in the executor module's own defaults."""
        source = (SIM_DIR / "harness" / "executor.py").read_text()
        self.assertNotRegex(source, r"\b\d{12}\b")  # AWS account id
        self.assertNotRegex(source, r"\bAKIA[0-9A-Z]{16}\b")  # access key id
        self.assertNotRegex(source, r"arn:aws")
        self.assertNotRegex(source, r"/Users/|/home/[a-z]+/")


class BackendInterfaceTests(unittest.TestCase):
    """The seam is an ABC on purpose: klayout-tools' newer `batch` backend
    (2AMLogic/klayout-tools#2080) has to be addable as one more subclass
    without any call site changing."""

    def test_both_shipped_backends_implement_the_abc(self):
        self.assertTrue(issubclass(executor_mod.LocalBackend, executor_mod.ExecutionBackend))
        self.assertTrue(issubclass(executor_mod.RemoteBackend, executor_mod.ExecutionBackend))

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
            executor_mod.build("batch", pdk=_StubPdk(), spiceinit=Path("/x"), jobs=1, manifest={})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
