"""Where one ngspice unit actually runs: the harness's execution backends.

This module is the seam issue #146 adds between "which units this campaign
runs" (`sim/harness/cli.py`) and "where each unit's `ngspice -b` process
executes". Everything else about a unit -- how its netlist was patched
(`runner.patch_netlist`), how its log is judged (`runner.judge`), how its
waveform dumps are reduced to measurements (`measure.py`/`acmeasure.py`) --
is deliberately **outside** this seam and identical for every backend, so a
unit run elsewhere is judged by exactly the same criterion as a local
one.

Backends
--------

- :class:`LocalBackend` (``--executor local``, the default) runs
  ``ngspice -b`` as a subprocess on this host. It is byte-for-byte the code
  path every record in `sim/` was minted by, and it is stdlib-only.
- The ``batch`` backend (``--executor batch``, `sim/harness/cp_klt.py`, issue
  #290) submits the unit set to the Spot batch fleet as one `klt sim`
  ``decks[]`` request. It exists for the charge-pump (`cp`) analysis only and
  **never falls back to local**: a refused or failed submit raises.

There is no ``remote`` backend. Issue #425 retired ``--executor remote`` (the
SSH-fleet ``RemoteBackend`` of issue #146, its ``SKY130_PLL_REMOTE_*``
credential variables, and its silent fallback to local); ``batch`` through
`klt sim` is the fleet route.

:class:`ExecutionBackend` is intentionally a small ABC over a single verb
(``execute(unit) -> outcome``) plus an optional batch ``stage(units)``.

Dependency discipline
---------------------

The harness is stdlib-only (see `sim/harness/README.md`), so a
``--executor local`` run -- and therefore every existing invocation, CI
included -- has no third-party dependency whatsoever. `runner` is likewise
imported lazily inside the method that needs it, so `runner` can import this
module at module scope without a cycle.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path

#: The `--executor` choices, in the order argparse should offer them.
EXECUTORS = ("local", "batch")
DEFAULT_EXECUTOR = "local"

# --------------------------------------------------------------------------- #
# The unit / outcome pair every backend speaks
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class NgspiceUnit:
    """One patched netlist to run, plus the judge's own two inputs.

    `completion_marker` and `timeout_s` travel with the unit rather than
    being re-derived per backend, so a unit run elsewhere is judged against exactly
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

    #: What actually ran the units (`"local"`/`"batch"`).
    name: str = "local"
    #: What the caller asked for. Differs from `name` only after a fallback.
    requested: str = "local"

    def stage(self, units: list[NgspiceUnit]) -> ExecutionBackend:
        """Prepare the whole unit set before any of it is judged.

        The local backend has nothing to do here (every unit is independent
        and runs on demand); the batch backend runs the entire set on the
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
    unchanged."""

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
# selection
# --------------------------------------------------------------------------- #


class ExecutorRefused(ValueError):
    """The requested executor cannot be used for this manifest on this host."""


def resolve_name(cli_value: str | None, manifest: dict, environ: dict | None = None) -> str:
    """`--executor` wins; otherwise the manifest's own `executor` key; else a
    `cp` manifest on a host that exports `KLT_SIM_BACKEND=batch` routes to
    `batch` (the dispatch-host rule: a grid never runs locally there); else
    `local`. An unknown name is rejected by the caller.

    Raises :class:`ExecutorRefused` for `remote` (retired, issue #425) and for
    `batch` on a manifest that has
    neither a `cp` nor a transient `measure` block (the batch route only knows
    how to submit those analyses). Only `cp` auto-routes to `batch`; a `measure`
    manifest uses it when asked for.
    """
    from . import cp_klt  # lazy: cp_klt imports this module

    explicit = cli_value or manifest.get("executor")
    on_batch_host = cp_klt.batch_requested(environ)
    is_cp = bool(manifest.get("cp"))
    if explicit:
        name = explicit.strip()
        if name == "remote":
            raise ExecutorRefused(
                "--executor remote was retired (issue #425); use --executor batch "
                "(klt sim --backend batch) or --executor local"
            )
        if name == "batch" and not (is_cp or manifest.get("measure")):
            raise ExecutorRefused(
                "--executor batch is implemented for `cp` and transient `measure` "
                "manifests only (it submits each patched deck as a klt sim decks[] request)"
            )
        return name
    if is_cp and on_batch_host:
        return "batch"
    return DEFAULT_EXECUTOR


def build(
    name: str, *, pdk, spiceinit: Path, jobs: int, manifest: dict, log=print
) -> ExecutionBackend:
    """Construct the backend `name` names. Never touches the network."""
    if name == "local":
        return LocalBackend(pdk=pdk, spiceinit=spiceinit)
    if name == "batch":
        from . import cp_klt  # lazy: cp_klt imports this module
        from . import cpmeasure as cp_mod
        from . import measure as measure_mod

        return cp_klt.CpBatchBackend(
            pdk=pdk,
            spiceinit=spiceinit,
            cp_spec=cp_mod.CpSpec.from_manifest(manifest),
            measure_spec=measure_mod.MeasureSpec.from_manifest(manifest),
            log=log,
            max_workers=min(max(1, int(jobs)), 2),
        )
    raise ValueError(f"unknown executor {name!r} (known: {', '.join(EXECUTORS)})")
