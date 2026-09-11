"""Command-line entry point. See sim/run_corners.py and sim/harness/README.md."""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import json
import sys
import tempfile
import threading
from pathlib import Path

from . import acmeasure as ac_mod
from . import checkpoint as checkpoint_mod
from . import corners as corners_mod
from . import measure as measure_mod
from . import montecarlo as mc_mod
from . import pdk as pdk_mod
from . import report as report_mod
from . import runner as runner_mod

REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_manifest(slug_or_path: str) -> Path:
    direct = Path(slug_or_path)
    if direct.is_dir() and (direct / "tb.json").is_file():
        return direct / "tb.json"
    candidate = REPO_ROOT / "sim" / slug_or_path / "testbench" / "tb.json"
    if candidate.is_file():
        return candidate
    raise SystemExit(f"no manifest found for {slug_or_path!r} (looked at {candidate})")


def _list_experiments() -> list[str]:
    sim_dir = REPO_ROOT / "sim"
    slugs = []
    for tb_json in sorted(sim_dir.glob("*/testbench/tb.json")):
        slugs.append(tb_json.parent.parent.name)
    return slugs


def cmd_check_env(args: argparse.Namespace) -> int:
    ok = True
    try:
        pdk = pdk_mod.resolve(REPO_ROOT)
        print(f"PDK: OK -- {pdk.variant} at {pdk.variant_dir}")
        if pdk.commit_mismatch:
            print(
                f"  WARNING: resolved commit {pdk.resolved_commit} != "
                f"pinned {pdk.pinned_commit}"
            )
    except pdk_mod.PdkNotFoundError as e:
        print(f"PDK: MISSING -- {e}")
        ok = False

    versions = pdk_mod.tool_versions()
    for tool, version in versions.items():
        if version:
            print(f"{tool}: {version}")
        else:
            print(f"{tool}: NOT FOUND")
            ok = False

    return 0 if ok else 1


def cmd_print_env(args: argparse.Namespace) -> int:
    try:
        pdk = pdk_mod.resolve(REPO_ROOT)
    except pdk_mod.PdkNotFoundError as e:
        print(f"echo 'run_corners.py --print-env: {e}' >&2", file=sys.stderr)
        return 1
    print(f"export PDK_ROOT={pdk.pdk_root}")
    print(f"export PDK={pdk.variant}")
    print(f"export SKY130_MODEL_LIB={pdk.ngspice_lib}")
    print(f"export XSCHEM_RCFILE={REPO_ROOT / 'sim' / 'xschemrc'}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    for slug in _list_experiments():
        print(slug)
    return 0


@contextlib.contextmanager
def _corners_dir(write: bool, exp_dir: Path, record_id: str):
    """Where per-corner .spice/.log artifacts go for this run.

    When writing evidence, this is the real, committed
    sim/<slug>/corners/<record-id>/ path. When --no-write (the default for
    sim/selftest.sh and a plain CI check:ci run), it is a real temp
    directory that is cleaned up on exit -- otherwise every non-recording
    run (which still has to netlist and simulate for real) would leave an
    orphaned, record-less sim/<slug>/corners/<id>/ directory behind, and
    neither *.spice nor the sim/README.md-mandated un-ignored *.log pattern
    excludes those from `git add -A` by accident.
    """
    if write:
        path = exp_dir / "corners" / record_id
        path.mkdir(parents=True, exist_ok=True)
        yield path
    else:
        with tempfile.TemporaryDirectory(prefix=f"sky130-pll-harness-{record_id}-") as tmp:
            yield Path(tmp)


def _parse_list(value: str | None, cast=str):
    if value is None:
        return None
    return [cast(v.strip()) for v in value.split(",") if v.strip()]


def _iter_unit_results(units, *, jobs: int, run_one, announce):
    """Yield `(unit, result)` pairs as they finish, at most `jobs` at a time.

    PVT points and Monte Carlo trials are embarrassingly parallel: each one
    patches its **own** copy of the netlist text, writes its own
    `<corner-id>.spice`, and runs its own `ngspice -b` process whose only
    shared state with its siblings is the work directory they each write
    disjoint, `corner-id`-named files into (see
    `runner.purge_unit_artifacts`). Nothing is mutated in common, so a worker
    pool changes only *when* a unit runs, never *what* it measures.

    Threads, not processes: the cost of a unit is one external simulator
    process, and `subprocess.run` releases the GIL for its whole duration, so
    a thread pool gets the same parallelism as a process pool without having
    to make the manifest/PDK/result objects picklable or fork a netlist copy
    per worker.

    `jobs == 1` runs inline with no pool at all -- the serial path stays
    exactly the code it was, so the default invocation cannot regress on a
    threading bug.

    Results are yielded in **completion** order (so the caller can checkpoint
    a unit the instant it lands); the caller re-orders by the manifest's unit
    list before rendering, which is what keeps a parallel record's row order
    identical to a serial one's.
    """
    if jobs == 1:
        for unit in units:
            announce(unit)
            yield unit, run_one(unit)
        return

    def _work(unit):
        announce(unit)
        return run_one(unit)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="sim-unit")
    futures = {pool.submit(_work, unit): unit for unit in units}
    handed_over = set()
    try:
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
            except BaseException:
                # A failure (or a caller that stops consuming) must not keep
                # dispatching the rest of the grid: cancel everything not yet
                # started. Units already *running* cannot be interrupted
                # (their ngspice processes are external) and are not waited
                # for -- but units that already finished successfully are
                # handed over before the failure propagates, so an
                # interrupted parallel run still checkpoints the work it
                # genuinely completed instead of throwing it away.
                pool.shutdown(wait=False, cancel_futures=True)
                for other in futures:
                    if other in handed_over or not other.done() or other.cancelled():
                        continue
                    if other.exception() is None:
                        handed_over.add(other)
                        yield futures[other], other.result()
                raise
            handed_over.add(future)
            yield futures[future], result
    finally:
        pool.shutdown(wait=False)


def _execution_note(*, segments, jobs: int, unit_noun: str, record_id: str) -> str | None:
    """The record's `**Execution**` bullet, or None for a plain serial run.

    Provenance a reader of the record cannot otherwise reconstruct: whether
    the campaign ran as one uninterrupted pass or was resumed across
    segments, whether points ran concurrently (and how many at a time), and
    which repo commit each segment ran at. Omitted entirely for the
    single-segment, `--jobs 1` case so existing records' shape is unchanged.
    """
    if len(segments) <= 1 and jobs == 1:
        return None
    parts = []
    for i, seg in enumerate(segments, 1):
        commit = (seg.get("repo_commit") or "unknown")[:7]
        parts.append(
            f"segment {i}: started {seg.get('started_utc', 'unknown')} at commit "
            f"`{commit}`, `--jobs {seg.get('jobs', 1)}`"
        )
    note = (
        f"run in {len(segments)} segment(s) ({'; '.join(parts)}). "
        if segments
        else f"run with `--jobs {jobs}`. "
    )
    if len(segments) > 1:
        note += (
            f"An interrupted run was resumed with `--resume {record_id}`: "
            f"{unit_noun} completed in an earlier segment were reloaded verbatim "
            "from this record's own `corners/<record-id>/checkpoint.json` rather "
            "than re-simulated. The resume is refused outright unless the "
            "testbench manifest, the netlisted DUT, the resolved PDK build and "
            "the requested point/trial list all match the first segment's, so no "
            "row below comes from a different campaign than any other. "
        )
    if max([seg.get("jobs", 1) for seg in segments] or [jobs]) > 1:
        note += (
            f"Concurrent execution runs several {unit_noun} at once, each in its "
            "own ngspice process against its own patched netlist copy (no shared "
            "mutable state), so verdicts are independent of the order they "
            "finish in. It does share the host between them: a point already "
            "close to its manifest's `timeout_s` budget can be pushed past it by "
            "contention, which is recorded as a failed point exactly as it would "
            "be in a serial run."
        )
    return note.strip()


def _run_experiment(
    args: argparse.Namespace,
    *,
    unit_noun: str,
    mode: str,
    detect_subset,
    override_error: str,
    build_units,
    run_unit,
    render_record,
) -> int:
    """Shared shape behind `cmd_run` and `cmd_run_mc`: manifest load, PDK
    resolve + commit-mismatch guard, subset-reason gate, netlist-once setup,
    per-unit loop with try/except, and the evidence-record write. Mode
    (PVT points vs. Monte Carlo trials) is supplied entirely via the hook
    parameters below:

    - `unit_noun`: what to call one item of the matrix/trial list in the
      progress and summary lines (e.g. "points" / "trials").
    - `mode`: `"pvt"` or `"mc"` -- part of the checkpoint fingerprint, so a
      `--resume` can never splice Monte Carlo trials into a PVT record.
    - `detect_subset() -> bool`: whether the run's flags narrow the
      manifest's default matrix, derived from `args` alone. Deliberately
      separate from (and evaluated before) `build_units`, so the
      subset-reason gate runs *before* the matrix is built: a run that
      combines an invalid override with a missing `--subset-reason` must
      report the missing reason, not the invalid value. It is a callable
      rather than a precomputed bool so that any flag parsing it does still
      happens after the PDK-resolve guard above, which reports first.
    - `override_error`: the message printed when a subset override is used
      without `--subset-reason` (the two modes word this differently).
    - `build_units(manifest, pdk) -> units`: builds the point/trial list.
      May raise `corners_mod.CornerError` / `mc_mod.McConfigError`, which are
      reported and turned into exit 1.
    - `run_unit(pdk, spiceinit, manifest, netlist_text, unit, corners_dir)`:
      runs one point/trial (`runner_mod.run_point` / `run_mc_trial`).
    - `render_record(manifest, slug, record_id, pdk, netlist_snapshot, units,
      results, subset_reason, execution_note) -> str`: renders the
      evidence-record markdown (`report_mod.render` / `render_mc`), with
      claim/tool-versions/repo-root/supersedes already bound by the caller.

    Execution model (issue #133): units run `--jobs N` at a time and each
    completed unit is persisted to a checkpoint beside the record, so an
    interrupted campaign resumes with `--resume <record-id>` instead of
    restarting. Both are execution-only: the record is still written in one
    shot, from the full ordered result list, exactly once -- one complete
    record, or (if the run stops early) none at all.
    """
    manifest_path = _find_manifest(args.experiment)
    manifest = json.loads(manifest_path.read_text())
    slug = manifest_path.parent.parent.name
    testbench_dir = manifest_path.parent

    try:
        pdk = pdk_mod.resolve(REPO_ROOT)
    except pdk_mod.PdkNotFoundError as e:
        print(f"run_corners.py: {e}", file=sys.stderr)
        return 1
    if pdk.commit_mismatch and not args.allow_pdk_mismatch:
        print(
            f"run_corners.py: resolved PDK commit {pdk.resolved_commit} != "
            f"pinned {pdk.pinned_commit} -- pass --allow-pdk-mismatch to run "
            "anyway (the record will carry the mismatch)",
            file=sys.stderr,
        )
        return 1

    jobs = getattr(args, "jobs", 1)
    jobs = 1 if jobs is None else int(jobs)
    if jobs < 1:
        print("run_corners.py: --jobs must be at least 1", file=sys.stderr)
        return 1
    resume_id = getattr(args, "resume", None)
    if resume_id and not args.write:
        print(
            "run_corners.py: --resume needs this record's real "
            "sim/<slug>/corners/<record-id>/ directory, which --no-write does not "
            "create -- a run that writes no evidence has nothing to resume",
            file=sys.stderr,
        )
        return 1

    is_subset = detect_subset()
    if is_subset and not args.subset_reason and args.write:
        print(override_error, file=sys.stderr)
        return 1

    try:
        units = build_units(manifest, pdk)
    except (corners_mod.CornerError, mc_mod.McConfigError, measure_mod.MeasureError) as e:
        print(f"run_corners.py: {e}", file=sys.stderr)
        return 1

    schematic = testbench_dir / manifest["schematic"]
    xschemrc = REPO_ROOT / "sim" / "xschemrc"
    spiceinit = REPO_ROOT / "sim" / "spiceinit"

    record_id = resume_id or report_mod.make_record_id(REPO_ROOT)
    exp_dir = manifest_path.parent.parent
    snapshots_dir = exp_dir / "netlist-snapshots"
    records_dir = exp_dir / "records"
    record_path = records_dir / f"{record_id}.md"
    if args.write and record_path.exists():
        # Reachable via `--resume <id>` of an id that already finished (its
        # checkpoint would be gone, but say so before simulating anything),
        # and in principle via two runs minting the same record id in the
        # same second at the same commit.
        print(
            f"run_corners.py: {record_path} already exists -- sim/README.md's "
            "append-only rule forbids overwriting a record; a re-run mints a new "
            "record id and names this one with --supersedes",
            file=sys.stderr,
        )
        return 1

    with _corners_dir(args.write, exp_dir, record_id) as corners_dir:
        print(f"run_corners.py: netlisting {schematic} ...")
        try:
            netlist_text = runner_mod.netlist_schematic(
                pdk, xschemrc, schematic, corners_dir, REPO_ROOT
            )
        except runner_mod.NetlistError as e:
            print(f"run_corners.py: {e}", file=sys.stderr)
            return 1

        # Checkpointing is tied to evidence: a --no-write run produces no
        # record, so there is nothing for a resume to finish.
        ckpt = None
        if args.write:
            fingerprint = checkpoint_mod.fingerprint(
                mode=mode, manifest=manifest, netlist_text=netlist_text, pdk=pdk, units=units
            )
            ckpt_path = corners_dir / checkpoint_mod.CHECKPOINT_NAME
            try:
                if resume_id:
                    ckpt = checkpoint_mod.resume(
                        ckpt_path, record_id=record_id, slug=slug, fp=fingerprint
                    )
                else:
                    ckpt = checkpoint_mod.start(
                        ckpt_path, record_id=record_id, slug=slug, fp=fingerprint
                    )
            except checkpoint_mod.CheckpointError as e:
                print(f"run_corners.py: {e}", file=sys.stderr)
                return 1
            ckpt.begin_segment(jobs=jobs, repo_commit=report_mod.git_info(REPO_ROOT)["sha"])
            print(
                f"run_corners.py: record id {record_id} -- an interrupted run can be "
                f"resumed with --resume {record_id}"
            )

        collected = dict(ckpt.results) if ckpt is not None else {}
        pending = [u for u in units if u.corner_id not in collected]
        if collected:
            print(
                f"run_corners.py: resuming {record_id}: {len(collected)}/{len(units)} "
                f"{unit_noun} already complete, running the remaining {len(pending)}"
            )

        position = {u.corner_id: i for i, u in enumerate(units, 1)}
        console = threading.Lock()

        def announce(unit):
            with console:
                print(f"run_corners.py: [{position[unit.corner_id]}/{len(units)}] {unit.corner_id} ...", flush=True)

        def run_one(unit):
            try:
                return run_unit(pdk, spiceinit, manifest, netlist_text, unit, corners_dir)
            except runner_mod.NetlistError as e:
                # Keep today's "<corner-id>: <error>" wording even when the
                # failure surfaces from a worker thread.
                raise runner_mod.NetlistError(f"{unit.corner_id}: {e}") from e

        try:
            for unit, result in _iter_unit_results(
                pending, jobs=jobs, run_one=run_one, announce=announce
            ):
                collected[unit.corner_id] = result
                if ckpt is not None:
                    ckpt.record(unit.corner_id, result)
                with console:
                    print(
                        f"  {unit.corner_id}: {'PASS' if result.passed else 'FAIL'}: {result.reason}",
                        flush=True,
                    )
        except runner_mod.NetlistError as e:
            print(f"run_corners.py: {e}", file=sys.stderr)
            return 1

        missing = [u.corner_id for u in units if u.corner_id not in collected]
        if missing:
            print(
                "run_corners.py: internal error -- no result for "
                f"{', '.join(missing)}; refusing to write a record",
                file=sys.stderr,
            )
            return 1
        # Record row order is the manifest's unit order, never completion
        # order, so a `--jobs N` run's record reads exactly like a serial
        # run's.
        results = [collected[u.corner_id] for u in units]

        failed = [r for r in results if not r.passed]

        if args.write:
            snapshots_dir.mkdir(parents=True, exist_ok=True)
            records_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = snapshots_dir / f"{record_id}.spice"
            snapshot_path.write_text(netlist_text)

            subset_reason = args.subset_reason if is_subset else None
            record_md = render_record(
                manifest=manifest,
                slug=slug,
                record_id=record_id,
                pdk=pdk,
                netlist_snapshot=snapshot_path,
                units=units,
                results=results,
                subset_reason=subset_reason,
                execution_note=_execution_note(
                    segments=ckpt.segments if ckpt is not None else [],
                    jobs=jobs,
                    unit_noun=unit_noun,
                    record_id=record_id,
                ),
            )
            record_path.write_text(record_md)
            print(f"run_corners.py: wrote {record_path}")
            # Only now, with the record on disk, is the campaign finished --
            # so a surviving checkpoint always means "interrupted, no record".
            if ckpt is not None:
                ckpt.discard()
        else:
            print("run_corners.py: --no-write -- no evidence record written")

    print(f"run_corners.py: {len(results) - len(failed)}/{len(results)} {unit_noun} passed")
    return 0 if not failed else 1


def cmd_run(args: argparse.Namespace) -> int:
    def detect_subset():
        return bool(
            _parse_list(args.corners)
            or _parse_list(args.temps, cast=float)
            or args.supply_tol is not None
        )

    def build_units(manifest, pdk):
        # Fail fast on a malformed `measure` / `ac` block rather than at the
        # first point, so a typo in the manifest costs a second, not a corner
        # run.
        spec = measure_mod.MeasureSpec.from_manifest(manifest)
        ac_spec = ac_mod.AcSpec.from_manifest(manifest)
        if spec is not None and ac_spec is not None:
            raise measure_mod.MeasureError(
                "manifest declares both a `measure` block and an `ac` block -- a "
                "testbench runs one analysis mode per manifest (transient "
                "measurement or AC loop-dynamics), so split them into sibling "
                "experiment directories"
            )
        return corners_mod.build_matrix(
            manifest,
            pdk.process_corners,
            corners_override=_parse_list(args.corners),
            temps_override=_parse_list(args.temps, cast=float),
            supply_tol_override=args.supply_tol,
        )

    def render_record(
        *, manifest, slug, record_id, pdk, netlist_snapshot, units, results, subset_reason, execution_note
    ):
        return report_mod.render(
            spec=measure_mod.MeasureSpec.from_manifest(manifest),
            ac_spec=ac_mod.AcSpec.from_manifest(manifest),
            manifest_has_supply=manifest.get("supply_pattern") is not None,
            corner_note=manifest.get("corner_note"),
            record_id=record_id,
            slug=slug,
            claim=manifest.get("claim", "(no claim stated in manifest)"),
            pdk=pdk,
            tool_versions=pdk_mod.tool_versions(),
            repo_root=REPO_ROOT,
            netlist_snapshot=netlist_snapshot,
            points=units,
            results=results,
            subset_reason=subset_reason,
            execution_note=execution_note,
            supersedes=args.supersedes,
            methodology_note=manifest.get(
                "methodology_note", "(no methodology_note stated in manifest)"
            ),
            analysis=manifest.get("analysis", "(no analysis stated in manifest)"),
        )

    return _run_experiment(
        args,
        unit_noun="points",
        mode="pvt",
        detect_subset=detect_subset,
        override_error=(
            "run_corners.py: a corner/temp/supply override needs --subset-reason "
            "to be recorded as evidence (sim/README.md's subset-justification rule)"
        ),
        build_units=build_units,
        run_unit=runner_mod.run_point,
        render_record=render_record,
    )


def cmd_run_mc(args: argparse.Namespace) -> int:
    """Monte Carlo run mode -- see sim/harness/README.md's Monte Carlo
    section and sim/harness/montecarlo.py's module docstring for the
    sampling mechanism. Shares `_run_experiment`'s shape (env resolution,
    netlist once, per-unit run, evidence record) with `cmd_run`, supplying a
    trial matrix instead of a PVT point matrix.
    """

    def detect_subset():
        return any(
            v is not None
            for v in (
                args.mc_corner,
                args.mc_trials,
                args.mc_seed_base,
                args.mc_temp,
                args.mc_supply,
                args.mc_mismatch,
                args.mc_process,
            )
        )

    def build_units(manifest, pdk):
        return mc_mod.build_trials(
            manifest,
            pdk.process_corners,
            corner_override=args.mc_corner,
            trials_override=args.mc_trials,
            seed_base_override=args.mc_seed_base,
            temp_override=args.mc_temp,
            supply_override=args.mc_supply,
            mismatch_override=args.mc_mismatch,
            process_override=args.mc_process,
        )

    def render_record(
        *, manifest, slug, record_id, pdk, netlist_snapshot, units, results, subset_reason, execution_note
    ):
        mc_cfg = manifest.get("monte_carlo", {})
        claim = mc_cfg.get("claim", manifest.get("claim", "(no claim stated in manifest)"))
        methodology_note = mc_cfg.get(
            "methodology_note",
            manifest.get("methodology_note", "(no methodology_note stated in manifest)"),
        )
        analysis = mc_cfg.get(
            "analysis", manifest.get("analysis", "(no analysis stated in manifest)")
        )
        return report_mod.render_mc(
            record_id=record_id,
            slug=slug,
            claim=claim,
            pdk=pdk,
            tool_versions=pdk_mod.tool_versions(),
            repo_root=REPO_ROOT,
            netlist_snapshot=netlist_snapshot,
            trials=units,
            results=results,
            subset_reason=subset_reason,
            execution_note=execution_note,
            supersedes=args.supersedes,
            methodology_note=methodology_note,
            analysis=analysis,
        )

    return _run_experiment(
        args,
        unit_noun="trials",
        mode="mc",
        detect_subset=detect_subset,
        override_error=(
            "run_corners.py: an --mc-* override needs --subset-reason to be "
            "recorded as evidence (sim/README.md's subset-justification rule)"
        ),
        build_units=build_units,
        run_unit=runner_mod.run_mc_trial,
        render_record=render_record,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check-env", action="store_true", help="check PDK/ngspice/xschem availability and exit")
    p.add_argument("--print-env", action="store_true", help="print `export ...` lines for the resolved PDK")
    p.add_argument("--list", action="store_true", help="list known experiment slugs")
    p.add_argument("experiment", nargs="?", help="experiment slug (e.g. pdk-smoke) or manifest directory")
    p.add_argument("--no-write", dest="write", action="store_false", default=True, help="do not write an evidence record")
    p.add_argument("--corners", help="comma-separated process corner override, e.g. tt,ss")
    p.add_argument("--temps", help="comma-separated temperature override (deg C), e.g. 27")
    p.add_argument("--supply-tol", type=float, help="supply tolerance override (0 = nominal-only point)")
    p.add_argument("--subset-reason", help="required with any override, recorded in the evidence record")
    p.add_argument("--allow-pdk-mismatch", action="store_true", help="run even if the resolved PDK commit != sim/pdk.json's pin")
    p.add_argument("--supersedes", help="record-id this run's record supersedes")
    p.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help=(
            "run N PVT points (or Monte Carlo trials) concurrently, each in its own "
            "ngspice process; default 1 (serial, today's behaviour). Points are "
            "independent, so this only changes wall-clock time -- but it does share "
            "the host, so keep N at or below the free core count: contention can "
            "push a point past its manifest's own timeout_s budget"
        ),
    )
    p.add_argument(
        "--resume",
        metavar="RECORD_ID",
        help=(
            "resume the interrupted evidence run with this record id instead of "
            "starting a new one: points already recorded in "
            "sim/<slug>/corners/<RECORD_ID>/checkpoint.json are reloaded, the rest "
            "are run, and the record is written once the grid is complete. Refused "
            "if the manifest, DUT netlist, PDK build or requested point list have "
            "changed since the checkpoint was written"
        ),
    )
    p.add_argument(
        "--mc",
        action="store_true",
        help="run this experiment's `monte_carlo` trial matrix instead of its PVT matrix (see sim/harness/README.md)",
    )
    p.add_argument("--mc-corner", help="Monte Carlo base process corner override, e.g. tt")
    p.add_argument("--mc-trials", type=int, help="Monte Carlo trial-count override")
    p.add_argument("--mc-seed-base", type=int, help="Monte Carlo first-trial RNG seed override (seed = base + trial - 1)")
    p.add_argument("--mc-temp", type=float, help="Monte Carlo temperature override (deg C)")
    p.add_argument("--mc-supply", type=float, help="Monte Carlo supply override (V)")
    p.add_argument(
        "--mc-mismatch",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Monte Carlo within-die mismatch sampling override (MC_MM_SWITCH); default from the manifest",
    )
    p.add_argument(
        "--mc-process",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Monte Carlo die-to-die process sampling override (MC_PR_SWITCH); default from the manifest",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check_env:
        return cmd_check_env(args)
    if args.print_env:
        return cmd_print_env(args)
    if args.list:
        return cmd_list(args)
    if not args.experiment:
        build_parser().print_help()
        return 1
    if args.mc:
        return cmd_run_mc(args)
    return cmd_run(args)
