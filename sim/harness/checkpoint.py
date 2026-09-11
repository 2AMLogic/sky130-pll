"""Crash-safe per-unit progress for a campaign, and the resume path.

A PVT campaign is a list of independent units (points, or Monte Carlo
trials); a single unit of `sim/pll-lock`'s grid can take hours (see its
manifest's own `timeout_s`), so a 45-point grid is measured in days of wall
clock. Before this module the harness held every result in memory and wrote
the evidence record only after the last unit finished: a host restart, a
killed session, or a stopped dispatch at unit 44 threw away every completed
unit.

This module persists each unit's result the moment it completes, so a later
`--resume <record-id>` invocation re-runs only what is actually missing. Three
properties matter more than the file format:

1. **A checkpoint is never partially written.** Every save serializes the
   whole state to a sibling temp file, `fsync`s it, and `os.replace`s it over
   the real path -- an atomic rename on POSIX. A process killed mid-write
   therefore leaves either the previous complete checkpoint or the new
   complete one, never a torn one that a resume could misread as progress.
2. **A checkpoint that cannot be trusted is an error, never an empty
   start.** A malformed file, an unknown schema version, a result whose own
   unit id disagrees with the key it is filed under, a duplicate unit -- each
   raises `CheckpointError` and aborts the run. Silently treating an
   unreadable checkpoint as "no progress yet" would re-run points (merely
   wasteful); silently treating it as complete would mint an evidence record
   for simulations that never ran (a fabricated claim, which `CLAUDE.md`
   forbids outright).
3. **A resume must be the same campaign.** The checkpoint stores a
   fingerprint of everything that determines what a unit measures -- the
   manifest (canonicalized), the netlisted DUT text, the resolved PDK build,
   the run mode, and the ordered unit list. A resume whose fingerprint
   differs is refused with a message naming the field that moved, rather than
   mixing results from two different manifests/DUTs into one record.

The append-only evidence convention (`sim/README.md`) is preserved by the
caller, not here: the checkpoint lives *beside* the record
(`sim/<slug>/corners/<record-id>/checkpoint.json`) and is deleted once the
record is written, so a leftover checkpoint means exactly "this record-id's
run was interrupted and has no record" -- one complete record, or none.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import acmeasure as ac_mod
from . import measure as measure_mod
from .corners import PvtPoint
from .montecarlo import McTrial
from .runner import McTrialResult, PointResult

SCHEMA_VERSION = 1
CHECKPOINT_NAME = "checkpoint.json"

# The closed set of result-tree types a checkpoint may carry. Deliberately a
# whitelist: an unknown type in a checkpoint file is an error, not something
# to reconstruct by guessing.
_SERIALIZABLE = (
    PvtPoint,
    McTrial,
    measure_mod.Measurement,
    ac_mod.AcMeasurement,
    ac_mod.LoopGainPoint,
    PointResult,
    McTrialResult,
)
_BY_NAME = {cls.__name__: cls for cls in _SERIALIZABLE}


class CheckpointError(RuntimeError):
    """A checkpoint is missing, unreadable, or not this campaign's."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _encode(obj):
    if is_dataclass(obj) and not isinstance(obj, type):
        name = type(obj).__name__
        if name not in _BY_NAME:
            raise CheckpointError(f"cannot checkpoint an unregistered dataclass {name!r}")
        return {
            "__type__": name,
            "fields": {f.name: _encode(getattr(obj, f.name)) for f in fields(obj)},
        }
    if isinstance(obj, (list, tuple)):
        return {"__seq__": [_encode(v) for v in obj]}
    if obj is None or isinstance(obj, (str, bool, int, float)):
        return obj
    raise CheckpointError(f"cannot checkpoint a value of type {type(obj).__name__}")


def _decode(obj):
    if isinstance(obj, dict):
        if "__type__" in obj:
            name = obj["__type__"]
            cls = _BY_NAME.get(name)
            if cls is None:
                raise CheckpointError(f"checkpoint names an unknown result type {name!r}")
            raw = obj.get("fields")
            if not isinstance(raw, dict):
                raise CheckpointError(f"checkpoint entry for {name!r} has no field map")
            expected = {f.name for f in fields(cls)}
            got = set(raw)
            if got != expected:
                # Harness source drifted under a live campaign (a result
                # dataclass gained or lost a field). Refuse rather than
                # default-fill: half the record's rows would then describe a
                # different measurement shape than the other half.
                missing = ", ".join(sorted(expected - got)) or "(none)"
                extra = ", ".join(sorted(got - expected)) or "(none)"
                raise CheckpointError(
                    f"checkpoint entry for {name!r} does not match this harness's "
                    f"definition (missing: {missing}; unexpected: {extra}) -- the "
                    "harness changed since the checkpoint was written; refusing to "
                    "resume"
                )
            return cls(**{k: _decode(v) for k, v in raw.items()})
        if "__seq__" in obj:
            seq = obj["__seq__"]
            if not isinstance(seq, list):
                raise CheckpointError("checkpoint sequence entry is not a list")
            # Every sequence in a result tree is a tuple (frozen dataclass
            # fields); decoding back to tuple keeps the reloaded object
            # `==`-comparable with a freshly computed one.
            return tuple(_decode(v) for v in seq)
        raise CheckpointError("checkpoint contains an untagged object")
    if obj is None or isinstance(obj, (str, bool, int, float)):
        return obj
    raise CheckpointError(f"checkpoint contains an undecodable value of type {type(obj).__name__}")


def unit_id_of(result) -> str:
    """The unit id a result belongs to, read off the result itself.

    Used to cross-check every reloaded entry against the key it was filed
    under -- the one check that catches a checkpoint whose rows were shuffled
    or hand-edited into naming the wrong point.
    """
    if isinstance(result, PointResult):
        return result.point.corner_id
    if isinstance(result, McTrialResult):
        return result.trial.corner_id
    raise CheckpointError(f"unrecognized result type {type(result).__name__}")


def fingerprint(*, mode: str, manifest: dict, netlist_text: str, pdk, units) -> dict:
    """Everything that must not change between segments of one campaign.

    Deliberately *not* included: `--subset-reason` prose, `--supersedes`, and
    the repo commit. The first two do not change what is measured (and the
    record states the values given at completion); the repo commit is recorded
    per segment instead, and surfaces in the record's execution note, so a
    reader can see the run spanned commits rather than having the resume
    refused over an unrelated commit landing on the branch.
    """
    return {
        "mode": mode,
        "manifest_sha256": _sha256_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        ),
        "netlist_sha256": _sha256_text(netlist_text),
        "pdk_variant": getattr(pdk, "variant", None),
        "pdk_commit": getattr(pdk, "resolved_commit", None),
        "units": [u.corner_id for u in units],
    }


_FINGERPRINT_LABELS = {
    "mode": "run mode (PVT vs. Monte Carlo)",
    "manifest_sha256": "testbench manifest (tb.json)",
    "netlist_sha256": "netlisted DUT",
    "pdk_variant": "PDK variant",
    "pdk_commit": "resolved PDK build",
    "units": "requested point/trial list",
}


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".checkpoint-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class Checkpoint:
    """Live, crash-safe progress for one record-id's campaign."""

    def __init__(self, path: Path, record_id: str, slug: str, fp: dict, *, segments=None, results=None):
        self.path = Path(path)
        self.record_id = record_id
        self.slug = slug
        self.fingerprint = fp
        self.segments = list(segments or [])
        # Insertion-ordered {unit_id: result}; insertion order is completion
        # order, which is NOT the record's row order -- the caller re-orders
        # by the manifest's unit list so a parallel run's record is
        # byte-identical in ordering to a serial one's.
        self.results = dict(results or {})

    # -- lifecycle -------------------------------------------------------

    def begin_segment(self, *, jobs: int, repo_commit: str | None) -> None:
        self.segments.append({"started_utc": _now(), "jobs": int(jobs), "repo_commit": repo_commit})
        self.save()

    def record(self, unit_id: str, result) -> None:
        """Persist one completed unit. Atomic: a kill during this call leaves
        either the previous state or this one."""
        if unit_id_of(result) != unit_id:
            raise CheckpointError(
                f"refusing to checkpoint a result for {unit_id_of(result)!r} under {unit_id!r}"
            )
        self.results[unit_id] = result
        self.save()

    def save(self) -> None:
        _atomic_write_json(self.path, self.as_payload())

    def discard(self) -> None:
        """Remove the checkpoint. Called only once the evidence record is on
        disk -- a surviving checkpoint means "interrupted, no record"."""
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()

    # -- serialization ---------------------------------------------------

    def as_payload(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "record_id": self.record_id,
            "slug": self.slug,
            "fingerprint": self.fingerprint,
            "segments": self.segments,
            "completed": [
                {"unit_id": unit_id, "result": _encode(result)}
                for unit_id, result in self.results.items()
            ],
        }


def start(path: Path, *, record_id: str, slug: str, fp: dict) -> Checkpoint:
    """Begin a fresh campaign. Refuses to clobber an existing checkpoint."""
    path = Path(path)
    if path.exists():
        raise CheckpointError(
            f"a checkpoint already exists at {path} -- record id {record_id} names an "
            f"interrupted run; resume it with --resume {record_id}, or delete the "
            "checkpoint to start that record over"
        )
    ckpt = Checkpoint(path, record_id, slug, fp)
    ckpt.save()
    return ckpt


def load(path: Path) -> tuple[dict, dict]:
    """Read a checkpoint file into (header, {unit_id: result}).

    Raises `CheckpointError` for anything it cannot fully trust -- a missing
    file, invalid JSON (the shape a torn write would have, though the atomic
    save above makes that unreachable for writes this module made), an
    unknown schema version, a duplicate unit, or a result filed under a unit
    id that is not its own.
    """
    path = Path(path)
    try:
        text = path.read_text()
    except FileNotFoundError:
        raise CheckpointError(f"no checkpoint at {path}") from None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise CheckpointError(
            f"checkpoint {path} is not valid JSON ({e}) -- refusing to guess how much "
            "of the campaign completed; delete it to re-run this record from scratch"
        ) from None
    if not isinstance(payload, dict):
        raise CheckpointError(f"checkpoint {path} is not a JSON object")

    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise CheckpointError(
            f"checkpoint {path} declares schema version {version!r}, this harness "
            f"writes {SCHEMA_VERSION} -- refusing to resume"
        )
    for key in ("record_id", "slug", "fingerprint", "completed"):
        if key not in payload:
            raise CheckpointError(f"checkpoint {path} is missing its {key!r} field")
    if not isinstance(payload["fingerprint"], dict):
        raise CheckpointError(f"checkpoint {path} has a malformed fingerprint")
    if not isinstance(payload["completed"], list):
        raise CheckpointError(f"checkpoint {path} has a malformed completed list")

    results: dict = {}
    for entry in payload["completed"]:
        if not isinstance(entry, dict) or "unit_id" not in entry or "result" not in entry:
            raise CheckpointError(f"checkpoint {path} has a malformed completed entry")
        unit_id = entry["unit_id"]
        if unit_id in results:
            raise CheckpointError(
                f"checkpoint {path} records {unit_id!r} twice -- refusing to resume a "
                "campaign that would double-count a point"
            )
        result = _decode(entry["result"])
        if unit_id_of(result) != unit_id:
            raise CheckpointError(
                f"checkpoint {path} files a result for {unit_id_of(result)!r} under "
                f"{unit_id!r} -- refusing to resume"
            )
        results[unit_id] = result

    header = {
        "record_id": payload["record_id"],
        "slug": payload["slug"],
        "fingerprint": payload["fingerprint"],
        "segments": payload.get("segments") or [],
    }
    return header, results


def resume(path: Path, *, record_id: str, slug: str, fp: dict) -> Checkpoint:
    """Load a checkpoint and assert it belongs to this exact campaign."""
    header, results = load(path)

    if header["record_id"] != record_id:
        raise CheckpointError(
            f"checkpoint {path} belongs to record {header['record_id']!r}, not {record_id!r}"
        )
    if header["slug"] != slug:
        raise CheckpointError(
            f"checkpoint {path} belongs to experiment {header['slug']!r}, not {slug!r}"
        )

    old = header["fingerprint"]
    drift = [k for k in fp if old.get(k) != fp[k]]
    if drift:
        detail = "; ".join(
            f"{_FINGERPRINT_LABELS.get(k, k)}: checkpoint has {old.get(k)!r}, this run has {fp[k]!r}"
            for k in drift
        )
        raise CheckpointError(
            f"refusing to resume record {record_id}: the campaign changed since the "
            f"checkpoint was written ({detail}). Mixing results from two different "
            "campaigns into one evidence record is exactly what sim/README.md's "
            "append-only rule forbids -- mint a new record instead"
        )

    known = set(fp["units"])
    stray = [u for u in results if u not in known]
    if stray:
        raise CheckpointError(
            f"checkpoint {path} holds results for units this run does not request "
            f"({', '.join(sorted(stray))}) -- refusing to resume"
        )

    return Checkpoint(path, record_id, slug, fp, segments=header["segments"], results=results)
