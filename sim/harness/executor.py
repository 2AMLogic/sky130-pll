"""Where one ngspice unit actually runs: the harness's execution backends.

This module is the seam issue #146 adds between "which units this campaign
runs" (`sim/harness/cli.py`) and "where each unit's `ngspice -b` process
executes". Everything else about a unit -- how its netlist was patched
(`runner.patch_netlist`), how its log is judged (`runner.judge`), how its
waveform dumps are reduced to measurements (`measure.py`/`acmeasure.py`) --
is deliberately **outside** this seam and identical for every backend, so a
remotely-executed unit is judged by exactly the same criterion as a local
one.

Backends
--------

- :class:`LocalBackend` (``--executor local``, the default) runs
  ``ngspice -b`` as a subprocess on this host. It is byte-for-byte the code
  path every record in `sim/` was minted by, and it is stdlib-only.
- :class:`RemoteBackend` (``--executor remote``) packages the campaign's
  units into a `klayout_tools.remote_transport.JobDescription` per shard and
  runs the shards on the `klayout-tools` Spot fleet
  (`klayout_tools.remote_fleet.run_fleet`), then pulls each unit's log and
  waveform dumps back into the run's own working directory so the unchanged
  judge/reducer read them exactly where a local run would have written them.

:class:`ExecutionBackend` is intentionally a small ABC over a single verb
(``execute(unit) -> outcome``) plus an optional batch ``stage(units)``.
A third backend (klayout-tools' newer ``batch`` backend, 2AMLogic/klayout-tools#2080,
which targets an unprovisioned batch fleet) can be added here later as one
more subclass without touching `runner.py` or `cli.py` at all.

Dependency discipline
---------------------

The harness is stdlib-only (see `sim/harness/README.md`). `klayout_tools` is
imported **lazily, inside :class:`RemoteBackend`**, never at module scope, so
a ``--executor local`` run -- and therefore every existing invocation, CI
included -- has no third-party dependency whatsoever. `runner` is likewise
imported lazily inside the method that needs it, so `runner` can import this
module at module scope without a cycle.

Fallback, never failure
-----------------------

A ``--executor remote`` request that this host cannot honour -- no
`klayout_tools` on the path, no configured region/key/profile, no ``aws``
CLI, a launcher quota refusal (`FleetQuotaError`) or cost-gate refusal, or a
transport failure -- is **not** an error. The backend logs exactly one line,
runs the unit set locally instead, and records why in the evidence record's
execution segment (`fallback_reason`). A sweep must not fail because the
host it landed on lacks cloud credentials: that is a fleet provisioning gap
(2AMLogic/2am#934), not a harness defect.
"""

from __future__ import annotations

import abc
import configparser
import os
import shlex
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

#: The `--executor` choices, in the order argparse should offer them.
EXECUTORS = ("local", "remote")
DEFAULT_EXECUTOR = "local"

#: `$PDK_ROOT` on the klayout-tools remote-sim AMI (its build script pins
#: this: `scripts/aws/build-remote-sim-ami.sh`). A netlist patched on this
#: host carries *this* host's absolute PDK paths, so the remote backend
#: rewrites that prefix to the AMI's before pushing -- see
#: `RemoteBackend._remote_netlist`.
DEFAULT_REMOTE_PDK_ROOT = "/opt/pdk"

#: Host-specific remote settings come from the environment, never from a
#: committed file: this repo is public, and an account id, key path or
#: profile name has no business in it. `tb.json`'s optional `remote` block
#: carries only the portable knobs (spot, cost ceiling, pdk_root).
_ENV_PREFIX = "SKY130_PLL_REMOTE_"

#: The remote shell that runs one shard's units. Written by
#: `RemoteBackend._shard_script`.
_SHARD_SCRIPT_NAME = "run-units.sh"
_ARTIFACTS_DIR = "artifacts"

#: `timeout(1)`'s "the command was killed at the deadline" exit code, which
#: the shard script passes through as the unit's return code. Mapped back to
#: the same TimeoutExpired verdict a local run produces.
_TIMEOUT_EXIT_CODE = 124


class RemoteUnavailable(RuntimeError):
    """This host cannot run the request remotely. Always caught by
    :meth:`RemoteBackend.stage`, which falls back to local execution -- it
    never propagates to the caller."""


# --------------------------------------------------------------------------- #
# The unit / outcome pair every backend speaks
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class NgspiceUnit:
    """One patched netlist to run, plus the judge's own two inputs.

    `completion_marker` and `timeout_s` travel with the unit rather than
    being re-derived per backend, so a remote unit is judged against exactly
    the marker and budget its manifest declares.
    """

    corner_id: str
    netlist_text: str
    work_dir: Path
    completion_marker: str
    timeout_s: int

    @property
    def spice_path(self) -> Path:
        return self.work_dir / f"{self.corner_id}.spice"

    @property
    def log_path(self) -> Path:
        return self.work_dir / f"{self.corner_id}.log"


@dataclass(frozen=True)
class NgspiceOutcome:
    """What a backend hands back: the raw material the judge reads.

    Deliberately *not* a verdict -- `runner.judge` turns this into
    (passed, reason), identically for every backend.
    """

    corner_id: str
    returncode: int
    log_text: str
    log_path: Path
    spice_path: Path
    timed_out: bool = False


# --------------------------------------------------------------------------- #
# The backend ABC
# --------------------------------------------------------------------------- #


class ExecutionBackend(abc.ABC):
    """Run ngspice units somewhere. One verb, one optional batch hook."""

    #: What actually ran the units (`"local"`/`"remote"`); after a fallback
    #: this is `"local"` even on a `RemoteBackend`.
    name: str = "local"
    #: What the caller asked for. Differs from `name` only after a fallback.
    requested: str = "local"

    def stage(self, units: list[NgspiceUnit]) -> ExecutionBackend:
        """Prepare the whole unit set before any of it is judged.

        The local backend has nothing to do here (every unit is independent
        and runs on demand); the remote backend runs the entire set on the
        fleet in one shot, because provisioning is per-campaign, not
        per-unit. Returns the backend to use -- always `self`.
        """
        return self

    @abc.abstractmethod
    def execute(self, unit: NgspiceUnit) -> NgspiceOutcome:
        """Run (or serve an already-collected result for) one unit."""

    def provenance(self) -> dict | None:
        """The execution-model facts this backend contributes to the
        evidence record, or `None` to contribute nothing.

        `None` is what a plain `--executor local` run returns, which is why
        such a record is byte-for-byte what the same run produced before
        this seam existed.
        """
        return None


# --------------------------------------------------------------------------- #
# local
# --------------------------------------------------------------------------- #


class LocalBackend(ExecutionBackend):
    """`ngspice -b` as a subprocess on this host -- today's behaviour,
    unchanged, and the fallback target for every remote refusal."""

    name = "local"
    requested = "local"

    def __init__(self, *, pdk, spiceinit: Path):
        self._pdk = pdk
        self._spiceinit = spiceinit

    def execute(self, unit: NgspiceUnit) -> NgspiceOutcome:
        from . import runner as runner_mod  # lazy: runner imports this module

        return runner_mod.run_ngspice_locally(
            unit, pdk=self._pdk, spiceinit=self._spiceinit
        )


# --------------------------------------------------------------------------- #
# remote configuration (host-specific bits live in the environment)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RemoteConfig:
    """Everything `RemoteBackend` needs to reach the fleet.

    Portable knobs may come from the manifest's `remote` block; everything
    host- or account-specific (`region`, `key_name`, `ssh_key_path`,
    `aws_profile`, `launcher_cidr`, `security_group_id`, `subnet_id`) comes
    from `SKY130_PLL_REMOTE_*` environment variables only, so nothing
    account-identifying is ever committed. The fleet host inventory that
    records those values is `hosts.yml` in the fleet-compute repo; see
    `sim/harness/README.md`.
    """

    region: str | None = None
    key_name: str | None = None
    ssh_key_path: str | None = None
    ssh_user: str | None = None
    aws_profile: str | None = None
    launcher_cidr: str | None = None
    security_group_id: str | None = None
    subnet_id: str | None = None
    ami_manifest: str | None = None
    spot: bool = True
    max_hourly_cost_usd: float | None = None
    max_hosts: int | None = None
    pdk_root: str = DEFAULT_REMOTE_PDK_ROOT


def _env(name: str, environ: dict) -> str | None:
    value = environ.get(_ENV_PREFIX + name)
    return value.strip() if value and value.strip() else None


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def remote_config(manifest: dict, environ: dict | None = None) -> RemoteConfig:
    """Merge the manifest's portable `remote` block with the host's
    `SKY130_PLL_REMOTE_*` environment. Environment wins."""
    environ = os.environ if environ is None else environ
    block = manifest.get("remote") or {}

    spot = block.get("spot", True)
    env_spot = _env("SPOT", environ)
    if env_spot is not None:
        spot = env_spot

    max_cost = _as_float(_env("MAX_HOURLY_COST_USD", environ))
    if max_cost is None:
        max_cost = _as_float(block.get("max_hourly_cost_usd"))

    max_hosts = _as_int(_env("MAX_HOSTS", environ))
    if max_hosts is None:
        max_hosts = _as_int(block.get("max_hosts"))

    return RemoteConfig(
        region=_env("REGION", environ) or block.get("region"),
        key_name=_env("KEY_NAME", environ),
        ssh_key_path=_env("SSH_KEY", environ),
        ssh_user=_env("SSH_USER", environ),
        aws_profile=_env("AWS_PROFILE", environ),
        launcher_cidr=_env("LAUNCHER_CIDR", environ),
        security_group_id=_env("SECURITY_GROUP_ID", environ),
        subnet_id=_env("SUBNET_ID", environ),
        ami_manifest=_env("AMI_MANIFEST", environ),
        spot=_as_bool(spot),
        max_hourly_cost_usd=max_cost,
        max_hosts=max_hosts,
        pdk_root=(
            _env("PDK_ROOT", environ)
            or block.get("pdk_root")
            or DEFAULT_REMOTE_PDK_ROOT
        ),
    )


def _aws_profile_exists(profile: str, environ: dict) -> bool:
    """Is `profile` declared in this host's AWS config?

    Reads only *section headers* -- this never reads, logs, or transmits a
    credential value, and it makes no AWS API call. Its only job is to turn
    "this host was never provisioned for the fleet" into a fallback instead
    of a confusing failure deep inside the launcher.
    """
    config_path = Path(
        environ.get("AWS_CONFIG_FILE") or "~/.aws/config"
    ).expanduser()
    creds_path = Path(
        environ.get("AWS_SHARED_CREDENTIALS_FILE") or "~/.aws/credentials"
    ).expanduser()
    for path, section in (
        (config_path, f"profile {profile}"),
        (config_path, profile),
        (creds_path, profile),
    ):
        if not path.is_file():
            continue
        parser = configparser.RawConfigParser()
        try:
            parser.read(str(path))
        except (configparser.Error, OSError, UnicodeDecodeError):
            continue
        if parser.has_section(section):
            return True
    return False


# --------------------------------------------------------------------------- #
# remote
# --------------------------------------------------------------------------- #


class RemoteBackend(ExecutionBackend):
    """Run the campaign's units on the klayout-tools Spot fleet.

    Entry point choice (issue #146): this drives
    `klayout_tools.remote_fleet.run_fleet` plus
    `klayout_tools.remote_transport`'s `JobDescription`/`JobInput` push-run-
    pull surface. Those are the *public*, documented contract
    (`docs/design/remote-job-description.md`: "the contract a future
    extract/lvs/DRC remote backend implements against") and they are job-type
    agnostic. `klayout_tools.sim_remote._run_remote_fleet` -- the other
    candidate -- is private, and hard-wired to `klt sim`'s own request
    document, corner-point schema and measurement reducer, none of which this
    harness speaks: our units are already-patched sky130 netlists judged by
    *this* repo's criterion.
    """

    name = "remote"
    requested = "remote"

    def __init__(
        self,
        *,
        pdk,
        spiceinit: Path,
        config: RemoteConfig,
        hosts: int = 1,
        log=print,
    ):
        self._pdk = pdk
        self._spiceinit = spiceinit
        self._config = config
        self._hosts = max(1, int(hosts))
        self._log = log
        self._local = LocalBackend(pdk=pdk, spiceinit=spiceinit)
        self._collected: dict[str, NgspiceOutcome] = {}
        self.fallback_reason: str | None = None
        self.fleet: list[dict] = []

    # -- lifecycle ---------------------------------------------------------

    def stage(self, units: list[NgspiceUnit]) -> ExecutionBackend:
        """Run the whole unit set on the fleet, or fall back to local.

        Exactly one line is logged on the fallback path, and `self.name`
        becomes `"local"` so the record says what actually ran. Never
        raises: a remote refusal is a provisioning gap, not a harness
        failure.
        """
        units = list(units)
        if not units:
            return self
        # Same "clean slate" guard `run_ngspice_locally` applies on the local
        # path (`runner.purge_unit_artifacts`) -- but done here, once per
        # pending unit, *before* `_run_fleet` ever calls `pull_artifacts`.
        # `pull_artifacts` lands the fleet's own dumps straight into each
        # unit's `work_dir` (see `_run_fleet`'s `shard_runner`), so purging
        # has to happen before that pull, never after: a resumed or retried
        # unit must never let the reducer read a previous attempt's
        # `<corner-id>-*` waveform dump back, on this path exactly as on the
        # local one (issue #150).
        from . import runner as runner_mod  # lazy: runner imports this module

        for unit in units:
            runner_mod.purge_unit_artifacts(unit.work_dir, unit.corner_id)
        try:
            self._run_fleet(units)
        except RemoteUnavailable as exc:
            self.fallback_reason = str(exc)
            self.name = "local"
            self._log(
                "run_corners.py: --executor remote unavailable "
                f"({exc}); running these {len(units)} unit(s) locally instead"
            )
        return self

    def execute(self, unit: NgspiceUnit) -> NgspiceOutcome:
        collected = self._collected.get(unit.corner_id)
        if collected is not None:
            return collected
        return self._local.execute(unit)

    def provenance(self) -> dict:
        info = {"executor": self.name, "requested": self.requested}
        if self.fallback_reason:
            info["fallback_reason"] = self.fallback_reason
            return info
        first = self.fleet[0] if self.fleet else {}
        info.update(
            {
                "hosts": len(self.fleet) or self._hosts,
                "region": first.get("region") or self._config.region,
                "instance_type": first.get("instance_type"),
                "spot": first.get("spot", self._config.spot),
                "estimated_hourly_cost_usd": first.get(
                    "estimated_hourly_cost_usd"
                ),
                "estimated_fleet_hourly_cost_usd": _fleet_cost(self.fleet),
            }
        )
        return info

    # -- fleet dispatch ----------------------------------------------------

    def _imports(self):
        """Import klayout-tools lazily; a missing install is a fallback."""
        try:
            from klayout_tools import remote_fleet, remote_transport
            from klayout_tools.remote_launcher import RemoteLaunchError
        except ImportError as exc:  # pragma: no cover - exercised via stubs
            raise RemoteUnavailable(
                f"klayout_tools is not importable here ({exc})"
            ) from exc
        return remote_fleet, remote_transport, RemoteLaunchError

    def _preflight(self) -> None:
        """Refuse before any billable call if this host is not provisioned.

        Existence checks only -- no AWS API call, and no credential value is
        ever read (see :func:`_aws_profile_exists`).
        """
        cfg = self._config
        if not cfg.region:
            raise RemoteUnavailable(
                f"no region configured (set {_ENV_PREFIX}REGION)"
            )
        if not cfg.key_name:
            raise RemoteUnavailable(
                f"no EC2 key pair configured (set {_ENV_PREFIX}KEY_NAME)"
            )
        if not cfg.ssh_key_path:
            raise RemoteUnavailable(
                f"no SSH private key configured (set {_ENV_PREFIX}SSH_KEY)"
            )
        if not Path(cfg.ssh_key_path).expanduser().is_file():
            raise RemoteUnavailable(
                f"the configured SSH private key is not present on this host "
                f"({_ENV_PREFIX}SSH_KEY)"
            )
        if not cfg.launcher_cidr and not cfg.security_group_id:
            raise RemoteUnavailable(
                f"no launcher CIDR or security group configured (set "
                f"{_ENV_PREFIX}LAUNCHER_CIDR or {_ENV_PREFIX}SECURITY_GROUP_ID)"
            )
        if cfg.aws_profile and not _aws_profile_exists(
            cfg.aws_profile, dict(os.environ)
        ):
            raise RemoteUnavailable(
                f"the AWS profile named by {_ENV_PREFIX}AWS_PROFILE is not "
                "configured on this host (see 2AMLogic/2am#934)"
            )
        if shutil.which("aws") is None:
            raise RemoteUnavailable("the 'aws' CLI is not on PATH")

    def _run_fleet(self, units: list[NgspiceUnit]) -> None:
        remote_fleet, remote_transport, RemoteLaunchError = self._imports()
        self._preflight()
        cfg = self._config

        hosts = min(self._hosts, len(units))
        if cfg.max_hosts:
            hosts = min(hosts, cfg.max_hosts)
        hosts = max(1, hosts)
        shards = _shard(units, hosts)

        ssh_user = cfg.ssh_user or getattr(
            remote_transport, "DEFAULT_SSH_USER", "ubuntu"
        )
        job_id_prefix = f"sky130-pll-sim-{uuid.uuid4().hex[:8]}"

        def _shard_runner(shard_index: int, launcher, public_ip: str):
            shard_units = shards[shard_index]
            remote_transport.wait_for_ssh(
                public_ip,
                user=ssh_user,
                identity_file=cfg.ssh_key_path,
            )
            job = self._job_description(remote_transport, shard_units)
            remote_job_dir = remote_transport.job_dir(
                ssh_user, f"{job_id_prefix}-{shard_index}"
            )
            remote_transport.push_job(
                host=public_ip,
                remote_job_dir=remote_job_dir,
                job=job,
                user=ssh_user,
                identity_file=cfg.ssh_key_path,
            )
            remote_transport.run_remote_job(
                host=public_ip,
                remote_job_dir=remote_job_dir,
                job=job,
                timeout_s=_shard_timeout_s(shard_units),
                user=ssh_user,
                identity_file=cfg.ssh_key_path,
            )
            # Straight into the run's own working directory: the judge and
            # the waveform reducer then read <corner-id>.log and
            # <corner-id>-*.raw exactly where a local run wrote them.
            remote_transport.pull_artifacts(
                host=public_ip,
                remote_job_dir=remote_job_dir,
                local_artifacts_dir=str(shard_units[0].work_dir),
                job=job,
                user=ssh_user,
                identity_file=cfg.ssh_key_path,
            )
            remote_transport.cleanup_job(
                host=public_ip,
                remote_job_dir=remote_job_dir,
                user=ssh_user,
                identity_file=cfg.ssh_key_path,
            )
            return [u.corner_id for u in shard_units]

        previous_profile = os.environ.get("AWS_PROFILE")
        if cfg.aws_profile:
            os.environ["AWS_PROFILE"] = cfg.aws_profile
        try:
            result = remote_fleet.run_fleet(
                region=cfg.region,
                pdk=self._pdk.variant,
                shard_unit_counts=[len(s) for s in shards],
                shard_runner=_shard_runner,
                job_id_prefix=job_id_prefix,
                spot=cfg.spot,
                max_hourly_cost_usd=cfg.max_hourly_cost_usd,
                launcher_cidr=cfg.launcher_cidr,
                security_group_id=cfg.security_group_id,
                key_name=cfg.key_name,
                subnet_id=cfg.subnet_id,
                manifest_path=cfg.ami_manifest,
            )
        except Exception as exc:
            # FleetQuotaError / FleetLaunchError / RemoteLaunchError /
            # RemoteTransportError all mean the same thing to this harness:
            # nothing ran remotely, so run it here. Anything else from the
            # launcher is treated identically rather than failing a sweep
            # over a cloud-side problem.
            raise RemoteUnavailable(f"{type(exc).__name__}: {exc}") from exc
        finally:
            if previous_profile is None:
                os.environ.pop("AWS_PROFILE", None)
            else:
                os.environ["AWS_PROFILE"] = previous_profile

        self.fleet = [
            dict(outcome.environment or {}) for outcome in result.shards
        ]
        lost = [o for o in result.shards if o.status != "ok"]
        if lost:
            # One lost shard would leave part of the matrix unjudged. Rather
            # than mint a record with a hole in it, re-run the whole set
            # locally -- correctness over the wasted shards.
            raise RemoteUnavailable(
                f"{len(lost)} of {len(result.shards)} fleet shard(s) were lost "
                f"({lost[0].error})"
            )

        for shard in shards:
            for unit in shard:
                self._collected[unit.corner_id] = _collect(unit)

    # -- job packaging -----------------------------------------------------

    def _remote_netlist(self, unit: NgspiceUnit) -> str:
        """Re-root this host's absolute PDK paths onto the AMI's `$PDK_ROOT`.

        xschem bakes the *local* model-library path into every netlist
        (`.lib /…/sky130A/libs.tech/combined/sky130.lib.spice tt`), which
        does not exist on the remote box. Substituting the resolved PDK root
        prefix fixes `.lib` and `.include` alike in one pure, reversible
        textual step -- nothing else about the patched netlist changes, so
        the remote run simulates the same deck the local one would have.
        """
        local_root = str(self._pdk.pdk_root).rstrip("/")
        if not local_root:
            return unit.netlist_text
        return unit.netlist_text.replace(
            local_root, self._config.pdk_root.rstrip("/")
        )

    def _job_description(self, remote_transport, shard_units):
        inputs = [
            remote_transport.JobInput(
                remote_name=".spiceinit",
                label="spiceinit",
                content=self._spiceinit.read_text(),
            ),
            remote_transport.JobInput(
                remote_name=_SHARD_SCRIPT_NAME,
                label="shard script",
                content=_shard_script(shard_units),
            ),
        ]
        inputs += [
            remote_transport.JobInput(
                remote_name=f"{unit.corner_id}.spice",
                label=f"netlist {unit.corner_id}",
                content=self._remote_netlist(unit),
            )
            for unit in shard_units
        ]
        return remote_transport.JobDescription(
            label="sky130-pll sim",
            inputs=tuple(inputs),
            command=f"sh {_SHARD_SCRIPT_NAME}",
            success_exit_codes=(0,),
            parse_json_stdout=False,
            artifacts_relative_dir=_ARTIFACTS_DIR,
        )


# --------------------------------------------------------------------------- #
# helpers shared by the remote backend and its tests
# --------------------------------------------------------------------------- #


def _shard(units: list[NgspiceUnit], hosts: int) -> list[list[NgspiceUnit]]:
    """Contiguous, near-equal slices -- the same shape klayout-tools'
    `_shard_corner_points` produces, reimplemented here (four lines) rather
    than reaching into a private upstream helper."""
    hosts = max(1, min(hosts, len(units)))
    base, extra = divmod(len(units), hosts)
    shards: list[list[NgspiceUnit]] = []
    start = 0
    for i in range(hosts):
        size = base + (1 if i < extra else 0)
        shards.append(units[start : start + size])
        start += size
    return shards


def _shard_timeout_s(shard_units: list[NgspiceUnit]) -> float:
    """The SSH command timeout for one shard: the fully-serial worst case
    (every unit burns its own budget) plus slack, matching the reasoning in
    klayout-tools' `_default_remote_run_timeout_s`."""
    return float(sum(u.timeout_s for u in shard_units)) + 300.0


def _shard_script(shard_units: list[NgspiceUnit]) -> str:
    """The `sh` script one fleet member runs.

    Per unit: `ngspice -b <id>.spice` under `timeout <budget>`, its combined
    output captured to `artifacts/<id>.log` and its exit code to
    `artifacts/<id>.rc`, then every `<id>-*` waveform dump moved into
    `artifacts/`. The script itself always exits 0 -- a unit that fails is
    *data* for the judge, not a transport failure.
    """
    lines = [
        "#!/bin/sh",
        "# Generated by sim/harness/executor.py -- one shard of a sky130-pll",
        "# PVT/Monte-Carlo campaign. Per-unit failures are recorded, never fatal.",
        "set -u",
        f"mkdir -p {_ARTIFACTS_DIR}",
    ]
    for unit in shard_units:
        cid = shlex.quote(unit.corner_id)
        lines += [
            f"timeout {int(unit.timeout_s)} ngspice -b {cid}.spice "
            f"> {_ARTIFACTS_DIR}/{cid}.log 2>&1",
            f"echo $? > {_ARTIFACTS_DIR}/{cid}.rc",
            f"for f in {cid}-*; do",
            f'  [ -e "$f" ] && mv "$f" {_ARTIFACTS_DIR}/',
            "done",
        ]
    lines.append("exit 0")
    return "\n".join(lines) + "\n"


def _collect(unit: NgspiceUnit) -> NgspiceOutcome:
    """Turn one unit's pulled `<id>.log`/`<id>.rc` into an outcome.

    A missing log or return code means the fleet member never produced one
    for this unit; that is reported as a nonzero return code with an empty
    log, which the unchanged judge reads as a failed unit -- never as a
    pass.
    """
    log_path = unit.log_path
    rc_path = unit.work_dir / f"{unit.corner_id}.rc"
    log_text = log_path.read_text() if log_path.is_file() else ""
    if not log_path.is_file():
        log_path.write_text(log_text)
    try:
        returncode = int(rc_path.read_text().strip())
    except (OSError, ValueError):
        returncode = 1
    if rc_path.is_file():
        rc_path.unlink()
    unit.spice_path.write_text(unit.netlist_text)
    return NgspiceOutcome(
        corner_id=unit.corner_id,
        returncode=returncode,
        log_text=log_text,
        log_path=log_path,
        spice_path=unit.spice_path,
        timed_out=returncode == _TIMEOUT_EXIT_CODE,
    )


def _fleet_cost(fleet: list[dict]) -> float | None:
    rates = [
        m.get("estimated_hourly_cost_usd")
        for m in fleet
        if m.get("estimated_hourly_cost_usd") is not None
    ]
    return round(sum(rates), 4) if rates else None


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #


def resolve_name(cli_value: str | None, manifest: dict) -> str:
    """`--executor` wins; otherwise the manifest's own `executor` key; else
    `local`. An unknown name is rejected by the caller."""
    return (cli_value or manifest.get("executor") or DEFAULT_EXECUTOR).strip()


def build(
    name: str, *, pdk, spiceinit: Path, jobs: int, manifest: dict, log=print
) -> ExecutionBackend:
    """Construct the backend `name` names. Never touches the network."""
    if name == "local":
        return LocalBackend(pdk=pdk, spiceinit=spiceinit)
    if name == "remote":
        return RemoteBackend(
            pdk=pdk,
            spiceinit=spiceinit,
            config=remote_config(manifest),
            hosts=jobs,
            log=log,
        )
    raise ValueError(f"unknown executor {name!r} (known: {', '.join(EXECUTORS)})")
