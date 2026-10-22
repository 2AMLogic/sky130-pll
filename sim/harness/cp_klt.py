"""`klt sim` `decks[]` batch route for the `cp` campaign (issue #290) and the
transient `measure` campaigns, e.g. `pll-lock` / `loop-ripple` (issue #365).

A transient `measure` manifest takes the same route: its patched deck (the
manifest-owned `tran` window plus `wrdata` dumps) ships as one `decks[]` entry
and the `<corner_id>-pointNNN.raw` dumps come back beside the unit.

The `cp` analysis owns its own `.control` block (`cpmeasure.build_cp_control_block`):
an operating point plus one transient per VCTRL x phase-offset coordinate, each
preceded by an `alter` of the PULSE stimulus. `klt sim` corner requests own the
single `.control` block themselves and cannot express that, so this route does
not use corners. It uses a deck-list request: every PVT point's already-patched
netlist ships byte-for-byte as one `decks[]` entry, the fleet runs
`ngspice -b <deck>` on it, and the per-coordinate `wrdata` dumps come back as the
entry's declared `outputs`. The unchanged `cpmeasure` reducer reads them from the
unit's own working directory exactly where a local run would have written them,
and `runner.judge` reads the returned log, so nothing about judging or reducing
differs from the local path.

Two deliberate differences from the local netlist, both mechanical:

  * The patched netlist carries this host's absolute PDK root in its `.lib`
    line. A deck-list request ships the deck unmodified and leaves `$VAR` and
    PDK-rooted targets to the executing host, so the local root is rewritten to
    `$PDK_ROOT` (which the fleet exports from `models.pdk`) before the deck is
    written. The rewritten deck is what is hashed and recorded.
  * The unit's `.spiceinit` is shipped as a declared input, as the local
    backend writes it beside the netlist.

Failure policy
--------------

A failed or refused batch submit is **never** answered by simulating locally.
Every failure raises :class:`CpBatchError` (or one of its subclasses) carrying
the diagnostic verbatim; the CLI reports it and exits nonzero without writing a
record. A unit that ran and failed (a nonzero ngspice exit, a timeout, a declared
output that never appeared) is returned to the unchanged judge as a failed unit.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import executor as executor_mod
from .klt_submit import is_capacity_refusal, submit_with_capacity_retry  # noqa: F401

#: Executor name accepted by `run_corners.py --executor`.
BATCH_EXECUTOR = "batch"

#: Directory (under the unit set's work dir) holding the request, decks and
#: the collected `klt sim` output tree.
BATCH_DIR = "batch-cp"
REQUEST_NAME = "request.json"

#: `klt sim` exit codes that still carry a usable deck-list report: 0 every
#: unit passed, 3 a declared limit failed (none declared here), 4 at least one
#: unit errored or timed out. Any other exit with no report is a submit failure.
_USABLE_EXIT = (0, 3, 4)

_ENGINE_TIMEOUT_EXIT = -1


class CpBatchError(RuntimeError):
    """The batch route could not produce evidence. The message carries the
    diagnostic verbatim for the PR/issue; nothing ran locally."""


class DecksUnsupported(CpBatchError):
    """The installed `klt` does not accept a `decks[]` request."""


def batch_requested(environ: dict | None = None) -> bool:
    """True on a host whose daemon exports `KLT_SIM_BACKEND=batch`."""
    environ = os.environ if environ is None else environ
    return (environ.get("KLT_SIM_BACKEND") or "").strip().lower() == "batch"


# --------------------------------------------------------------------------- #
# deck + request
# --------------------------------------------------------------------------- #


def reroot_pdk(netlist_text: str, local_pdk_root: str) -> str:
    """Replace this host's PDK root with `$PDK_ROOT` so the executing host
    resolves the model library itself. Pure and reversible textually."""
    root = str(local_pdk_root).rstrip("/")
    if not root:
        return netlist_text
    return netlist_text.replace(root, "$PDK_ROOT")


def unit_outputs(spec, corner_id: str) -> list:
    """The dump files a unit's control block promises, as declared outputs.

    `spec` is a `cp` block (`cpmeasure.CpSpec`) or a transient `measure` block
    (`measure.MeasureSpec`, issue #365); both name their dumps
    `<corner_id>-<name>` through their own `waveform_names`."""
    from . import cpmeasure as cp_mod
    from . import measure as measure_mod

    names = cp_mod.waveform_names if isinstance(spec, cp_mod.CpSpec) else measure_mod.waveform_names
    return names(spec, f"{corner_id}-")


def batch_spec(manifest: dict):
    """The analysis spec the batch route submits for `manifest`, or `None` when
    the manifest carries neither a `cp` block nor a transient `measure` block
    (an `ac` or plumbing-only manifest has no deck-list route)."""
    from . import cpmeasure as cp_mod
    from . import measure as measure_mod

    return cp_mod.CpSpec.from_manifest(manifest) or measure_mod.MeasureSpec.from_manifest(manifest)


def build_request(units, *, pdk_variant: str, outputs_for, timeout_s: int,
                  max_workers: int, deck_name_for=lambda u: f"{u.corner_id}.spice",
                  spiceinit_name: str = ".spiceinit") -> dict:
    """The `klt sim` deck-list request: one `decks[]` entry per unit.

    Deck and input paths are relative to the request file. No corner fields
    are present (a deck-list request must not carry them)."""
    return {
        "engine": "ngspice",
        "backend": "batch",
        "models": {"pdk": pdk_variant},
        "decks": [
            {
                "id": u.corner_id,
                "deck": deck_name_for(u),
                "inputs": [{"path": spiceinit_name, "name": ".spiceinit"}],
                "outputs": list(outputs_for(u)),
                "timeout_s": u.timeout_s,
            }
            for u in units
        ],
        "options": {"timeout_s": timeout_s, "max_workers": max_workers},
        # The fleet runner image may pin an older klt than the client; the
        # request uses only the deck-list contract, so skew is warned, not enforced.
        "batch": {"runner_version_check": "warn"},
    }


# --------------------------------------------------------------------------- #
# the backend
# --------------------------------------------------------------------------- #


class CpBatchBackend(executor_mod.ExecutionBackend):
    """Runs the whole unit set (`cp` or transient `measure`) through one `klt sim`
    deck-list request."""

    name = BATCH_EXECUTOR
    requested = BATCH_EXECUTOR

    def __init__(self, *, pdk, spiceinit: Path, cp_spec=None, measure_spec=None, klt: str | None = None,
                 runner=None, log=print, capacity_retries: int = 30,
                 capacity_wait_s: float = 120.0, sleep=time.sleep,
                 max_workers: int = 2, environ: dict | None = None):
        self._pdk = pdk
        self._spiceinit = Path(spiceinit)
        # Exactly one analysis spec names the dumps a unit promises.
        self._spec = cp_spec if cp_spec is not None else measure_spec
        if self._spec is None:
            raise CpBatchError("the batch route needs a `cp` or transient `measure` block")
        self._environ = os.environ if environ is None else environ
        self.klt = klt or self._environ.get("SKY130_PLL_KLT") or shutil.which("klt")
        self.runner = runner or subprocess.run  # injectable for tests
        self._log = log
        self.capacity_retries, self.capacity_wait_s = capacity_retries, capacity_wait_s
        self._sleep = sleep
        self.max_workers = max(1, int(max_workers))
        self._collected: dict = {}
        self.job: dict = {}

    # -- preflight ------------------------------------------------------- #

    def preflight(self) -> None:
        if not self.klt:
            raise CpBatchError("`klt` is not on PATH (set SKY130_PLL_KLT to its path)")
        prov = self._environ.get("KLT_BATCH_PROVISION_SCRIPT")
        if not prov or not Path(prov).expanduser().is_file():
            raise CpBatchError(
                "KLT_BATCH_PROVISION_SCRIPT does not name an existing batch-fleet-provision.sh"
            )

    def klt_version(self) -> str | None:
        try:
            proc = self.runner([self.klt, "--version"], capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            return None
        out = ((getattr(proc, "stdout", "") or "") + (getattr(proc, "stderr", "") or "")).strip()
        return out.splitlines()[0] if out else None

    # -- lifecycle ------------------------------------------------------- #

    def stage(self, units) -> executor_mod.ExecutionBackend:
        """Submit the whole unit set as one deck-list job, or raise.

        Never falls back to a local run: provisioning and capacity problems are
        reported, not routed around."""
        units = list(units)
        if not units:
            return self
        from . import runner as runner_mod  # lazy: runner imports executor

        self.preflight()
        # Same clean-slate guard every backend applies before anything could
        # write a unit's artifacts (issue #150): "no dump" must mean no dump.
        for unit in units:
            runner_mod.purge_unit_artifacts(unit.work_dir, unit.corner_id)
        bdir = units[0].work_dir / BATCH_DIR
        shutil.rmtree(bdir, ignore_errors=True)
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / ".spiceinit").write_text(self._spiceinit.read_text())
        local_root = str(self._pdk.pdk_root)
        for unit in units:
            text = reroot_pdk(unit.netlist_text, local_root)
            (bdir / f"{unit.corner_id}.spice").write_text(text)
        timeout_s = max(u.timeout_s for u in units)
        req = build_request(
            units, pdk_variant=self._pdk.variant,
            outputs_for=lambda u: unit_outputs(self._spec, u.corner_id),
            timeout_s=timeout_s, max_workers=self.max_workers,
        )
        (bdir / REQUEST_NAME).write_text(json.dumps(req, indent=1, sort_keys=True) + "\n")
        version = self.klt_version()
        self._log(f"run_corners.py: submitting {len(units)} cp deck(s) to the batch fleet "
                  f"(klt {version or 'version unknown'})")
        report = self._submit(bdir, timeout_s * len(units) + 3600)
        self._ingest(report, units, bdir)
        # The dumps and logs now live beside each unit (where the reducer and
        # judge read them); the collected tree would only duplicate them.
        shutil.rmtree(bdir / "out", ignore_errors=True)
        env = report.get("environment") or {}
        remote = env.get("remote") or {}
        self.job = {
            "job_id": remote.get("job_id"),
            "instance_type": remote.get("instance_type"),
            "lifecycle": remote.get("lifecycle"),
            "runner_klt_version": remote.get("runner_klt_version"),
            "client_klt_version": remote.get("client_klt_version") or version,
            "installed_klt_version": version,
            "engine_version": env.get("engine_version"),
            "unit_count": len(units),
            "dir": BATCH_DIR,
        }
        return self

    def _submit(self, bdir: Path, wall_s: int) -> dict:
        cmd = [self.klt, "sim", str(bdir / REQUEST_NAME), "-o", str(bdir / "out"),
               "--backend", "batch", "--format", "json"]
        try:
            proc, attempt = submit_with_capacity_retry(
                cmd, runner=self.runner, timeout=wall_s + 1800, usable_exit=_USABLE_EXIT,
                retries=self.capacity_retries, wait_s=self.capacity_wait_s,
                sleep=self._sleep, log=self._log, label="run_corners.py")
        except (OSError, subprocess.TimeoutExpired) as e:
            raise CpBatchError(f"klt sim did not complete: {e}") from e
        text = (proc.stdout or "") + (proc.stderr or "")
        (bdir / "stderr.log").write_text(proc.stderr or "")
        try:
            report = json.loads(proc.stdout)
        except (ValueError, TypeError):
            report = None
        if not isinstance(report, dict):
            if proc.returncode not in _USABLE_EXIT and is_capacity_refusal(text):
                raise CpBatchError(
                    f"fleet refused the job for capacity after {attempt} retries: "
                    f"{text.strip()[-1500:]}")
            if _looks_like_decks_unsupported(text):
                raise DecksUnsupported(
                    "the installed klt does not accept a decks[] request: "
                    f"{text.strip()[-1500:]}")
            raise CpBatchError(
                f"klt sim exit {proc.returncode} with no JSON report: {text.strip()[-1500:]}")
        (bdir / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
        if report.get("mode") != "decks" or not isinstance(report.get("units"), list):
            # A klt that predates deck-list requests reads this as a corner
            # request and refuses (or reports corners); either way it is not a
            # deck-list report and must not be read as evidence.
            raise DecksUnsupported(
                "klt sim returned a report that is not a deck-list report "
                f"(mode={report.get('mode')!r}): {json.dumps(report.get('error', report))[:1500]}")
        if proc.returncode not in _USABLE_EXIT:
            raise CpBatchError(
                f"klt sim exit {proc.returncode}: {json.dumps(report.get('error', report))[:1500]}")
        return report

    def _ingest(self, report: dict, units, bdir: Path) -> None:
        """Turn each reported unit into the outcome the judge reads, copying its
        returned dumps into the unit's own work dir for the reducer."""
        by_id = {u.get("id"): u for u in report["units"]}
        out_root = Path(report.get("outdir") or (bdir / "out"))
        for unit in units:
            entry = by_id.get(unit.corner_id)
            if entry is None:
                raise CpBatchError(f"{unit.corner_id}: unit missing from the deck-list report")
            diags = entry.get("diagnostics") or []
            job_level = [d for d in diags if str(d.get("code", "")).startswith("batch_")]
            if any("missing required field: netlist" in str(d.get("message", "")) for d in job_level):
                # The client accepted the deck-list request, but the fleet runner's
                # own (older) klt read it as a corner request and refused it.
                raise DecksUnsupported(
                    f"{unit.corner_id}: the batch fleet runner's klt does not accept a decks[] "
                    "request (it asked for a corner `netlist`): "
                    + "; ".join(sorted({str(d.get("message", "")) for d in job_level})))
            if job_level:
                raise CpBatchError(
                    f"{unit.corner_id}: batch job produced no result: "
                    + "; ".join(sorted({f"{d.get('code')}: {d.get('message', '')}" for d in job_level})))
            udir = out_root / unit.corner_id
            log_text = _read_stream(udir, entry.get("stdout")) + _read_stream(udir, entry.get("stderr"))
            unit.log_path.write_text(log_text)
            unit.spice_path.write_text((bdir / f"{unit.corner_id}.spice").read_text())
            missing = set(entry.get("missing_outputs") or [])
            for name in unit_outputs(self._spec, unit.corner_id):
                src = udir / name
                if name not in missing and src.is_file():
                    shutil.copy2(src, unit.work_dir / name)
            if missing:
                # The reducer also fails the unit on an absent dump; naming the
                # report's own missing_outputs keeps the reason attributable.
                log_text += f"\nklt deck-list report: missing_outputs: {sorted(missing)}\n"
                unit.log_path.write_text(log_text)
            timed_out = bool(entry.get("timed_out"))
            exit_code = entry.get("exit_code")
            if timed_out:
                rc = _ENGINE_TIMEOUT_EXIT
            elif exit_code is None:
                rc = 1
            else:
                rc = int(exit_code)
            self._collected[unit.corner_id] = executor_mod.NgspiceOutcome(
                corner_id=unit.corner_id, returncode=rc, log_text=log_text,
                log_path=unit.log_path, spice_path=unit.spice_path, timed_out=timed_out,
            )

    def execute(self, unit: executor_mod.NgspiceUnit) -> executor_mod.NgspiceOutcome:
        outcome = self._collected.get(unit.corner_id)
        if outcome is None:
            # Never a local run: a unit the staged job did not cover is a bug
            # or a resumed set that was not staged, not something to simulate here.
            raise CpBatchError(
                f"{unit.corner_id}: no batch result was staged for this unit; "
                "refusing to run it locally")
        return outcome

    def provenance(self) -> dict:
        return {"executor": BATCH_EXECUTOR, "requested": BATCH_EXECUTOR, "job": dict(self.job)}


def _read_stream(udir: Path, rel) -> str:
    if not rel:
        return ""
    p = Path(rel)
    cand = p if p.is_absolute() else udir.parent / p
    try:
        return cand.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _looks_like_decks_unsupported(text: str) -> bool:
    low = text.lower()
    return "decks" in low and ("unknown" in low or "unsupported" in low or "unrecognized" in low
                               or "netlist" in low)


def execution_note(prov: dict) -> str:
    job = prov.get("job") or {}
    return (
        "executor: `batch` (`klt sim --backend batch`, `decks[]` deck-list request, S3 job "
        f"contract), {job.get('unit_count', '?')} deck(s) in one job, job_id: "
        f"`{job.get('job_id')}`, instance_type: `{job.get('instance_type')}`, "
        f"lifecycle: `{job.get('lifecycle')}`, ngspice {job.get('engine_version')}, "
        f"runner klt {job.get('runner_klt_version')} / client klt {job.get('client_klt_version')} "
        f"(installed `klt --version`: {job.get('installed_klt_version')}). Each PVT point is one "
        "caller-composed deck run byte-for-byte as `ngspice -b` on the fleet; the only difference "
        "from the local netlist is this host's absolute PDK root rewritten to `$PDK_ROOT`, which "
        "the fleet resolves from its own image (the model identity is the image's, not the local "
        "pinned install). The returned dump files are reduced and the returned log judged by "
        "exactly the code a local unit uses."
    )
