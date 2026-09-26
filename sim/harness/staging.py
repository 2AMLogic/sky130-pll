"""Where a campaign's *work* lives while it runs, as opposed to where its
evidence lands when it finishes.

The problem this module exists for (issue #212). Every artifact a running
campaign owns -- the netlisted DUT, each unit's patched `<corner-id>.spice`,
its `<corner-id>.log`, its `<corner-id>-*.raw` waveform dumps, and the
`checkpoint.json` that `--resume` needs -- used to be written straight into
`sim/<slug>/corners/<record-id>/`, i.e. *inside the checkout the harness was
invoked from*. A Loom-managed issue worktree is a checkout that another
process may delete at any moment (`git worktree remove --force`, an
orphan-recovery pass, a builder-phase timeout). When that happened under a
multi-hour Monte Carlo campaign, the working directory was unlinked beneath
five live `ngspice` processes: each one was going to fail at its next
`wrdata`, and -- worse -- the checkpoint that would have let the work be
resumed went with it. 4 h 26 min of simulator time produced nothing
resumable.

Note what was and was not lost. The *units that had completed* were all
recorded in `checkpoint.json`; the campaign was recoverable in principle and
irrecoverable only because the one file describing its progress lived in the
directory being deleted. So the fix is not to make the checkpoint more
durable in place -- it is to stop putting the campaign's only durable state
inside a directory whose lifetime is owned by something other than the
campaign.

What this module does
---------------------

`resolve()` decides one thing: the directory a run's units write into. Two
cases, and the first is deliberately the status quo:

- **A checkout nothing reaps** (the main clone) stages nothing. The work
  directory is `sim/<slug>/corners/<record-id>/` exactly as before, the
  artifacts are written where they are committed from, and no code path
  below this line runs. Every record in `sim/` was minted that way and a
  re-run of one still is.
- **A linked git worktree** (`.git` is a *file* pointing into the main
  clone's `.git/worktrees/<name>`, which is precisely the shape
  `git worktree remove` can delete) stages the work under a root outside
  every checkout -- `$XDG_CACHE_HOME/sky130-pll/sim-stage/<slug>/<record-id>/`
  by default. When the record is finally written, `promote()` copies the
  committed artifact classes into `sim/<slug>/corners/<record-id>/` in the
  checkout, so the evidence trail is byte-for-byte what an unstaged run
  would have committed.

`--stage-dir DIR` and `$SKY130_PLL_SIM_SCRATCH` name the root explicitly (for
a host whose home directory is small, or to stage a main-checkout run
deliberately); `--no-stage` forces the in-tree behaviour anywhere.

Why the default root is keyed on nothing but the slug and the record id: a
resume has to find the checkpoint *from a different checkout than the one
that wrote it* -- typically a worktree created after the original was reaped.
A root derived from the checkout path could not be recomputed there. One
derived from `(slug, record-id)` can, so
`python3 sim/run_corners.py <slug> --resume <record-id>` from a fresh
worktree finds the campaign with no extra flags, which is the whole point.

What this module deliberately does not do
-----------------------------------------

It does not touch the evidence record, its schema, or where it lands: the
record, the netlist snapshot and the promoted `corners/<record-id>/` tree are
the same paths with the same contents either way, and a staged run's record
is byte-for-byte an unstaged run's. Staging is where ngspice's scratch went,
not a fact about what was measured, so it is not recorded as provenance --
the same reasoning that keeps `--jobs 1 --executor local` records unchanged
by the executor seam.

It also does not promote waveform dumps (`*.raw`) or the checkpoint.
`sim/README.md`'s retention policy keeps dumps out of the committed trail,
and the checkpoint is transient run state that is deleted the moment the
record exists. Both stay in the staging directory, which is scratch: once the
record is committed, the staging directory can be deleted outright.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import checkpoint as checkpoint_mod

#: Names the staging root, for a host that wants it somewhere other than the
#: default cache directory. `--stage-dir` wins over this.
ENV_ROOT = "SKY130_PLL_SIM_SCRATCH"

#: Artifact classes that are *never* promoted into the committed evidence
#: tree: waveform dumps (regenerable, and `sim/README.md`'s retention policy
#: excludes them), the transient resume checkpoint, and the atomic-write temp
#: files `checkpoint.py`/`runner.py` create and rename.
_NO_PROMOTE_SUFFIXES = (".raw",)
_NO_PROMOTE_NAMES = (checkpoint_mod.CHECKPOINT_NAME,)


class StagingError(RuntimeError):
    """A staging root was named but cannot be used."""


@dataclass(frozen=True)
class Staging:
    """One campaign's staged work directory and its eventual home.

    `work_dir` is what every unit writes into while the campaign runs (and
    where its `checkpoint.json` lives); `final_dir` is the committed
    `sim/<slug>/corners/<record-id>/` the artifacts are promoted into once the
    record is written. `reason` is the one-line explanation the run prints, so
    an operator watching a campaign can see where its work went and why.
    """

    work_dir: Path
    final_dir: Path
    reason: str

    @property
    def checkpoint_path(self) -> Path:
        return self.work_dir / checkpoint_mod.CHECKPOINT_NAME


def default_root(environ: dict | None = None) -> Path:
    """The staging root used when nothing names one.

    `$XDG_CACHE_HOME/sky130-pll/sim-stage` (or `~/.cache/...`): outside every
    checkout, durable across a reboot -- a campaign may be resumed days later
    -- and identical from any worktree of any clone, which is what lets a
    resume recompute it (see the module docstring).
    """
    environ = os.environ if environ is None else environ
    cache = environ.get("XDG_CACHE_HOME")
    if cache and cache.strip():
        base = Path(cache.strip()).expanduser()
    else:
        home = environ.get("HOME")
        base = (Path(home) if home else Path.home()).expanduser() / ".cache"
    return base / "sky130-pll" / "sim-stage"


def linked_worktree_root(path: Path) -> Path | None:
    """The root of the linked git worktree containing `path`, or `None`.

    Reads the filesystem only, no `git` subprocess. The distinction it draws
    is exactly the one that matters here: in a linked worktree `.git` is a
    **file** (`gitdir: /…/.git/worktrees/<name>`), and that is the shape
    `git worktree remove` deletes; in a normal clone `.git` is a
    **directory**, and no worktree command removes it. Anything else (a
    directory that is in no checkout at all -- a temp dir under test, say) is
    also `None`: nothing reaps it, so nothing needs staging.
    """
    try:
        current = Path(path).resolve()
    except OSError:  # pragma: no cover - a vanished path is not a worktree
        return None
    for candidate in (current, *current.parents):
        dot_git = candidate / ".git"
        if dot_git.is_file():
            return candidate
        if dot_git.is_dir():
            return None
    return None


def resolve(
    *,
    exp_dir: Path,
    slug: str,
    record_id: str,
    explicit: str | None = None,
    disabled: bool = False,
    resuming: bool = False,
    environ: dict | None = None,
) -> Staging | None:
    """Where this run's units should write. `None` means "in the tree, as
    always" -- `sim/<slug>/corners/<record-id>/`.

    `resuming` makes one difference, and it is the difference between a
    working `--resume` and a confusing one: a resume **follows the
    checkpoint**. If the default/auto-detected staging root holds no
    checkpoint for this record id but the in-tree directory does, the run
    resumes in the tree (a campaign started before this seam existed, or
    started in the main clone); an explicitly named `--stage-dir` is always
    honoured as given, so a flag is never silently ignored.
    """
    environ = os.environ if environ is None else environ
    final_dir = Path(exp_dir) / "corners" / record_id
    if disabled:
        return None

    if explicit and explicit.strip():
        root, reason = Path(explicit.strip()).expanduser(), "--stage-dir was given"
        staging = _staging(root, slug, record_id, final_dir, reason)
        _check_usable(staging.work_dir)
        return staging

    env_root = environ.get(ENV_ROOT)
    if env_root and env_root.strip():
        staging = _staging(
            Path(env_root.strip()).expanduser(),
            slug,
            record_id,
            final_dir,
            f"${ENV_ROOT} is set",
        )
    elif linked_worktree_root(exp_dir) is not None:
        staging = _staging(
            default_root(environ),
            slug,
            record_id,
            final_dir,
            "this checkout is a linked git worktree, which another process can "
            "remove under a running campaign (issue #212)",
        )
    else:
        staging = None

    if resuming:
        in_tree_checkpoint = (final_dir / checkpoint_mod.CHECKPOINT_NAME).is_file()
        if staging is not None and not staging.checkpoint_path.is_file() and in_tree_checkpoint:
            # This record id was checkpointed in the tree. Resume it there
            # rather than reporting "no checkpoint" about a directory the
            # campaign never used.
            return None
        if staging is None and not in_tree_checkpoint:
            fallback = _staging(
                default_root(environ),
                slug,
                record_id,
                final_dir,
                "this record id's campaign is staged outside the checkout "
                f"(issue #212); resuming it from {default_root(environ)}",
            )
            if fallback.checkpoint_path.is_file():
                return fallback

    if staging is not None:
        _check_usable(staging.work_dir)
    return staging


def _staging(root: Path, slug: str, record_id: str, final_dir: Path, reason: str) -> Staging:
    return Staging(work_dir=root / slug / record_id, final_dir=final_dir, reason=reason)


def _check_usable(work_dir: Path) -> None:
    """Create the staging directory now, so a bad root fails before the first
    simulator process starts rather than hours in."""
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise StagingError(
            f"cannot use the staging directory {work_dir} ({e}) -- name a usable "
            f"one with --stage-dir/${ENV_ROOT}, or pass --no-stage to write this "
            "campaign's work into the checkout as before (see sim/harness/README.md)"
        ) from e


def promotable(work_dir: Path) -> list[Path]:
    """The staged files that belong in the committed evidence tree, as paths
    relative to `work_dir`.

    Inclusive by default and exclusive only about the two classes that are
    deliberately not evidence (waveform dumps and the resume checkpoint), so
    an artifact class the harness grows later is promoted without this
    function having to learn about it -- the failure mode of a whitelist here
    would be a record whose `corners/<record-id>/` is quietly missing a file
    an unstaged run would have committed.
    """
    work_dir = Path(work_dir)
    if not work_dir.is_dir():
        return []
    out = []
    for path in sorted(work_dir.rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        if name in _NO_PROMOTE_NAMES or path.suffix in _NO_PROMOTE_SUFFIXES:
            continue
        if name.startswith(".") and name.endswith(".tmp"):
            continue  # an in-flight atomic write, not an artifact
        out.append(path.relative_to(work_dir))
    return out


def promote(staging: Staging) -> list[Path]:
    """Copy the staged evidence artifacts into `sim/<slug>/corners/<id>/`.

    Called once, immediately before the record is rendered, so the record is
    written against a tree that already holds every artifact it cites -- and
    so a failure here (the checkout was removed after all) happens *before*
    the checkpoint is discarded, leaving the campaign resumable rather than
    half-landed.

    Overwrites: promoting twice (a mint that failed after the copy, resumed
    and re-minted) copies the same bytes to files that no record cites yet, so
    `sim/README.md`'s append-only rule -- which governs committed evidence --
    is untouched.
    """
    copied = []
    for rel in promotable(staging.work_dir):
        dest = staging.final_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staging.work_dir / rel, dest)
        copied.append(dest)
    return copied
