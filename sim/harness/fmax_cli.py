"""Driver for the divider Fmax characterization campaign (issue #244).

    python3 sim/run_fmax.py divider-fmax --dry-run
    python3 sim/run_fmax.py divider-fmax --executor remote --subset-reason ... # subset
    python3 sim/run_fmax.py divider-fmax --executor batch                      # full grid
    python3 sim/run_fmax.py divider-fmax --executor remote                     # full grid (SSH fleet)

The full DR-003 grid x the declared modulus set is thousands of ngspice runs
and belongs on the Spot batch fleet. This driver therefore never silently runs
a grid on the host it was started on: if the requested remote executor falls
back to local, or `--executor local` is asked for more than
`--max-local-probes` units, it stops before simulating. `--probe-mhz F` runs
exactly one probe locally (a debug/validation aid; it writes no record).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import sys
import tempfile
from pathlib import Path

from . import corners as corners_mod
from . import executor as executor_mod
from . import fmax as fmax_mod
from . import fmax_klt
from . import fmax_report
from . import measure as measure_mod
from . import pdk as pdk_mod
from . import report as report_mod
from . import runner as runner_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_JOBS = 2  # shared host: never more than two local workers


def _find_manifest(arg: str) -> Path:
    direct = Path(arg)
    if direct.is_file():
        return direct
    cand = REPO_ROOT / "sim" / arg / "testbench" / "fmax.json"
    if cand.is_file():
        return cand
    raise SystemExit(f"no Fmax manifest found for {arg!r} (looked at {cand})")


def _csv(value, cast=str):
    return [cast(v) for v in value.split(",") if v.strip()] if value else None


class Cell:
    """One (modulus, PVT point): the unit a boundary is reported for."""

    def __init__(self, modulus, point):
        self.modulus = modulus
        self.point = point
        self.observed: dict = {}  # grid index -> status
        self.probes: list = []  # per-probe provenance dicts

    @property
    def key(self) -> str:
        return f"n{self.modulus.n}_{self.point.corner_id}"


def probe_id(cell: Cell, freq_hz: float) -> str:
    return f"{cell.key}_f{freq_hz / 1e6:g}M"


def build_probe_unit(manifest, spec, cell, freq_hz, netlist_text, work_dir):
    """One probe as a harness unit: corner/supply/temp patched exactly as a
    normal PVT point, then the stimulus and the measure block from this probe's
    single frequency."""
    plan = fmax_mod.stimulus_for(spec, cell.modulus.n, freq_hz, cell.point.supply_v)
    pid = probe_id(cell, freq_hz)
    text = runner_mod._substitute_corner_and_supply(
        netlist_text, manifest, cell.point.corner, cell.point.supply_v
    )
    text = fmax_mod.patch_stimulus(text, plan)
    mspec = measure_mod.MeasureSpec.from_manifest(fmax_mod.measure_manifest(spec, plan))
    if not runner_mod._END_CARD_RE.search(text):
        raise runner_mod.NetlistError("netlist has no standalone .end card")
    injected = f".temp {cell.point.temp_c:g}\n" + measure_mod.build_control_block(mspec, f"{pid}-")
    text = runner_mod._END_CARD_RE.sub(lambda m: f"{injected}{m.group(1)}", text, count=1)
    unit = executor_mod.NgspiceUnit(
        corner_id=pid,
        netlist_text=text,
        work_dir=work_dir,
        completion_marker=measure_mod.COMPLETION_MARKER,
        timeout_s=spec.criterion.timeout_s,
    )
    return unit, plan, mspec


def judge_probe(unit, outcome, plan, mspec, spec) -> fmax_mod.ProbeVerdict:
    """Simulator trouble -> INCONCLUSIVE; a completed waveform -> the criterion."""
    ok, reason = runner_mod.judge(outcome, unit.completion_marker, unit.timeout_s)
    if not ok:
        return fmax_mod.ProbeVerdict(fmax_mod.INCONCLUSIVE, f"simulator: {reason}")
    dump = unit.work_dir / measure_mod.waveform_names(mspec, f"{unit.corner_id}-")[0]
    if not dump.is_file():
        return fmax_mod.ProbeVerdict(fmax_mod.INCONCLUSIVE, f"no waveform dump {dump.name!r}")
    try:
        times, values = measure_mod.parse_wrdata(dump.read_text())
    except (measure_mod.MeasureError, OSError) as e:
        return fmax_mod.ProbeVerdict(fmax_mod.INCONCLUSIVE, f"unreadable waveform: {e}")
    return fmax_mod.classify_waveform(
        times, values, plan,
        threshold_frac=spec.criterion.threshold_frac,
        hysteresis_frac=spec.criterion.hysteresis_frac,
    )


def _sha_file(path: Path) -> str | None:
    try:
        return report_mod.sha256_file(path)
    except OSError:
        return None


def _probe_dict(pid, stage_no, cell, freq, plan, verdict, netlist_sha, log_file, log_sha):
    return {
        "probe_id": pid,
        "stage": stage_no,
        "modulus": cell.modulus.n,
        "corner": cell.point.corner,
        "temp_c": cell.point.temp_c,
        "supply_v": cell.point.supply_v,
        "freq_hz": freq,
        "clk_period_s": plan.clk_period_s,
        "clk_pulse_width_s": plan.clk_width_s,
        "expected_out_period_s": plan.expected_out_period_s,
        "tran_stop_s": plan.tran_stop_s,
        "status": verdict.status,
        "reason": verdict.reason,
        "edges": verdict.edges,
        "periods": verdict.periods,
        "worst_dev_frac": verdict.worst_dev_frac,
        "netlist_sha256": netlist_sha,
        "log_file": log_file,
        "log_sha256": log_sha,
    }


def run_batch(requests, *, manifest, spec, netlists, work_dir, backend, jobs, stage_no, log):
    """Run [(cell, grid_index, freq_hz)] as one staged unit set and record each
    probe's verdict and provenance on its cell."""
    if isinstance(backend, fmax_klt.KltBatchBackend):
        for r in backend.run(requests, netlists=netlists, stage_no=stage_no, probe_id=probe_id):
            r.cell.observed[r.idx] = r.verdict.status
            d = _probe_dict(r.probe_id, stage_no, r.cell, r.freq, r.plan, r.verdict,
                            r.netlist_sha256, r.log_file, r.log_sha256)
            d.update(r.extra)
            r.cell.probes.append(d)
            log(f"  {r.probe_id}: {r.verdict.status}: {r.verdict.reason}")
        return backend
    built = []
    for cell, idx, freq in requests:
        unit, plan, mspec = build_probe_unit(
            manifest, spec, cell, freq, netlists[cell.modulus.n], work_dir
        )
        built.append((cell, idx, freq, unit, plan, mspec))
    backend = backend.stage([b[3] for b in built])

    def work(item):
        cell, idx, freq, unit, plan, mspec = item
        outcome = backend.execute(unit)
        return item, outcome, judge_probe(unit, outcome, plan, mspec, spec)

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        for item, outcome, verdict in pool.map(work, built):
            cell, idx, freq, unit, plan, _ = item
            cell.observed[idx] = verdict.status
            cell.probes.append(_probe_dict(
                unit.corner_id, stage_no, cell, freq, plan, verdict,
                fmax_mod.sha256_text(unit.netlist_text), outcome.log_path.name,
                _sha_file(outcome.log_path),
            ))
            log(f"  {unit.corner_id}: {verdict.status}: {verdict.reason}")
    return backend


def run_campaign(cells, grid_hz, *, manifest, spec, netlists, work_dir, backend, jobs, log):
    """Two-stage search over all cells; returns the backend last used."""
    coarse = fmax_mod.coarse_indices(len(grid_hz), spec.search.coarse_stride)
    reqs = [(c, i, grid_hz[i]) for c in cells for i in coarse]
    log(f"fmax: stage 1: {len(reqs)} coarse probes over {len(cells)} cell(s)")
    backend = run_batch(reqs, manifest=manifest, spec=spec, netlists=netlists,
                        work_dir=work_dir, backend=backend, jobs=jobs, stage_no=1, log=log)
    reqs = [(c, i, grid_hz[i]) for c in cells for i in fmax_mod.refine_indices(c.observed)]
    if reqs:
        log(f"fmax: stage 2: {len(reqs)} refinement probes")
        backend = run_batch(reqs, manifest=manifest, spec=spec, netlists=netlists,
                            work_dir=work_dir, backend=backend, jobs=jobs, stage_no=2, log=log)
    return backend


def planned_stage1(cells, spec) -> int:
    return len(cells) * len(fmax_mod.coarse_indices(len(fmax_mod.grid(spec.search)), spec.search.coarse_stride))


def build_cells(spec, manifest, pdk, args):
    moduli = _csv(args.moduli, int)
    chosen = [m for m in spec.moduli if moduli is None or m.n in moduli]
    if moduli is not None and {m.n for m in chosen} != set(moduli):
        raise fmax_mod.FmaxError(f"--moduli {moduli} not all in the manifest's {[m.n for m in spec.moduli]}")
    points = corners_mod.build_matrix(
        manifest, pdk.process_corners if pdk else tuple(manifest["process_corners"]),
        corners_override=_csv(args.corners), temps_override=_csv(args.temps, float),
        supply_tol_override=args.supply_tol,
    )
    return [Cell(m, p) for m in chosen for p in points]


def cmd(args) -> int:
    manifest_path = _find_manifest(args.experiment)
    manifest = json.loads(manifest_path.read_text())
    slug = manifest_path.parent.parent.name
    try:
        spec = fmax_mod.FmaxSpec.from_manifest(manifest)
        report_mod.spec_rows_from_manifest(manifest)
    except (fmax_mod.FmaxError, report_mod.SpecRowsError) as e:
        print(f"run_fmax.py: {manifest_path}: {e}", file=sys.stderr)
        return 1
    jobs = max(1, min(int(args.jobs), MAX_JOBS))
    subset = bool(args.moduli or args.corners or args.temps or args.supply_tol is not None)
    if subset and args.write and not args.subset_reason and not args.dry_run:
        print("run_fmax.py: a modulus/corner/temp/supply override needs --subset-reason "
              "to be recorded as evidence", file=sys.stderr)
        return 1

    pdk = None
    if not args.dry_run:
        try:
            pdk = pdk_mod.resolve(REPO_ROOT)
        except pdk_mod.PdkNotFoundError as e:
            print(f"run_fmax.py: {e}", file=sys.stderr)
            return 1
        if pdk.commit_mismatch and not args.allow_pdk_mismatch:
            print("run_fmax.py: resolved PDK commit differs from the pin; "
                  "pass --allow-pdk-mismatch to run anyway", file=sys.stderr)
            return 1
    try:
        cells = build_cells(spec, manifest, pdk, args)
    except (fmax_mod.FmaxError, corners_mod.CornerError) as e:
        print(f"run_fmax.py: {e}", file=sys.stderr)
        return 1

    grid_hz = fmax_mod.grid(spec.search)
    if args.probe_mhz is not None:
        if len(cells) != 1:
            print("run_fmax.py: --probe-mhz needs exactly one cell (one --moduli, "
                  "--corners, --temps and --supply-tol 0)", file=sys.stderr)
            return 1
        if args.write:
            print("run_fmax.py: --probe-mhz writes no record; pass --no-write", file=sys.stderr)
            return 1
    n_stage1 = planned_stage1(cells, spec)
    print(f"fmax: {len(cells)} cell(s), grid {len(grid_hz)} points "
          f"({grid_hz[0] / 1e6:g}-{grid_hz[-1] / 1e6:g} MHz @ {spec.search.resolution_hz / 1e6:g}), "
          f"stage-1 probes {n_stage1}, stage-2 up to {len(cells) * (spec.search.coarse_stride - 1)}")
    if args.dry_run:
        return 0

    n_requested = 1 if args.probe_mhz is not None else n_stage1
    name = executor_mod.resolve_name(args.executor, manifest)
    if name not in executor_mod.EXECUTORS and name != fmax_klt.BATCH_EXECUTOR:
        print(f"run_fmax.py: unknown executor {name!r}", file=sys.stderr)
        return 1
    if name == "local" and n_requested > args.max_local_probes:
        print(f"run_fmax.py: refusing to run {n_requested} probes on this host "
              f"(--max-local-probes {args.max_local_probes}); use --executor remote "
              "(Spot batch fleet) or narrow to one cell with --probe-mhz", file=sys.stderr)
        return 1

    spiceinit = REPO_ROOT / "sim" / "spiceinit"
    record_id = report_mod.make_record_id(REPO_ROOT)
    exp_dir = manifest_path.parent.parent
    record_path = exp_dir / "records" / f"{record_id}.md"
    if args.write and record_path.exists():
        print(f"run_fmax.py: {record_path} exists; records are append-only", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix=f"sky130-pll-fmax-{record_id}-") as tmp:
        work_dir = Path(tmp)
        netlists = {}
        for m in spec.moduli:
            if m.n not in {c.modulus.n for c in cells}:
                continue
            sch = (manifest_path.parent / m.schematic).resolve()
            try:
                netlists[m.n] = runner_mod.netlist_schematic(
                    pdk, REPO_ROOT / "sim" / "xschemrc", sch, work_dir / f"net{m.n}", REPO_ROOT
                )
            except runner_mod.NetlistError as e:
                print(f"run_fmax.py: {e}", file=sys.stderr)
                return 1

        if name == fmax_klt.BATCH_EXECUTOR:
            backend = fmax_klt.KltBatchBackend(
                spec=spec, manifest=manifest, work_dir=work_dir,
                cache_dir=Path(args.klt_cache) if args.klt_cache else None, log=print,
                max_jobs=args.klt_jobs,
            )
            try:
                backend.preflight()
            except fmax_klt.KltBatchError as e:
                print(f"run_fmax.py: {e}", file=sys.stderr)
                return 1
        else:
            backend = executor_mod.build(name, pdk=pdk, spiceinit=spiceinit, jobs=jobs,
                                         manifest=manifest, log=print)
        if name == "remote":
            # A fleet-backed stage may silently fall back to local execution;
            # for a grid that is exactly what this host must not do.
            backend = _GuardedRemote(backend, args.max_local_probes)

        try:
            if args.probe_mhz is not None:
                freq = args.probe_mhz * 1e6
                cell = cells[0]
                backend = run_batch([(cell, 0, freq)], manifest=manifest, spec=spec,
                                    netlists=netlists, work_dir=work_dir, backend=backend,
                                    jobs=1, stage_no=0, log=print)
                return 0
            backend = run_campaign(cells, grid_hz, manifest=manifest, spec=spec,
                                   netlists=netlists, work_dir=work_dir, backend=backend,
                                   jobs=jobs, log=print)
        except (_LocalFallbackRefused, fmax_klt.KltBatchError) as e:
            print(f"run_fmax.py: {e}", file=sys.stderr)
            return 1

        results = []
        for c in cells:
            b = fmax_mod.fmax_bracket(c.observed, grid_hz)
            results.append({"n": c.modulus.n, "corner": c.point.corner,
                            "temp_c": c.point.temp_c, "supply_v": c.point.supply_v,
                            "boundary": b})
            print(f"fmax: {c.key}: {b.status}: {b.detail}")
        probes = [p for c in cells for p in c.probes]
        if not args.write:
            return 0

        snap_dir = exp_dir / "netlist-snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        snapshot = snap_dir / f"{record_id}.spice"
        snapshot.write_text("".join(
            f"* ---- unpatched netlist for N={n} ----\n{netlists[n]}\n" for n in sorted(netlists)
        ))
        corners_dir = exp_dir / "corners" / record_id
        corners_dir.mkdir(parents=True, exist_ok=True)
        for p in probes:
            src = work_dir / p["log_file"]
            if src.is_file():
                shutil.copy2(src, corners_dir / p["log_file"])
        (corners_dir / "probes.json").write_text(json.dumps(probes, indent=1, sort_keys=True) + "\n")
        prov = backend.provenance() if hasattr(backend, "provenance") else None
        if name == fmax_klt.BATCH_EXECUTOR:
            backend.export_jobs(corners_dir / "jobs")
            note = fmax_klt.execution_note(prov)
        else:
            note = _note(prov)
        text = fmax_report.render(
            record_id=record_id, slug=slug, manifest=manifest, spec=spec, pdk=pdk,
            tool_versions=pdk_mod.tool_versions(), repo_root=REPO_ROOT,
            netlist_snapshot=snapshot, cells=results, probe_count=len(probes),
            subset_reason=args.subset_reason, supersedes=args.supersedes,
            execution_note=note,
        )
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(text)
        print(f"run_fmax.py: wrote {record_path}")
        verdict, detail = fmax_report.overall(results)
        print(f"run_fmax.py: overall {verdict} ({detail})")
        return 0 if verdict == "PASS" else 2


class _LocalFallbackRefused(RuntimeError):
    pass


class _GuardedRemote:
    """Wrap a RemoteBackend so a fallback to local execution of more than
    `max_local` units aborts instead of running a grid on this host."""

    def __init__(self, inner, max_local: int):
        self._inner, self._max_local = inner, max_local

    def stage(self, units):
        self._inner.stage(units)
        if self._inner.name != "remote" and len(units) > self._max_local:
            raise _LocalFallbackRefused(
                f"remote executor unavailable ({self._inner.fallback_reason}); refusing to "
                f"run {len(units)} probes locally (--max-local-probes {self._max_local}). "
                "Fix the fleet configuration, or narrow the request."
            )
        return self

    def execute(self, unit):
        return self._inner.execute(unit)

    def provenance(self):
        return self._inner.provenance()


def _note(prov) -> str | None:
    from . import cli as cli_mod

    return cli_mod._executor_note(prov)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("experiment", help="experiment slug (e.g. divider-fmax) or manifest path")
    p.add_argument("--dry-run", action="store_true", help="print the plan; no PDK, no simulation")
    p.add_argument("--no-write", dest="write", action="store_false", default=True)
    p.add_argument("--moduli", help="comma-separated N subset")
    p.add_argument("--corners")
    p.add_argument("--temps")
    p.add_argument("--supply-tol", type=float)
    p.add_argument("--subset-reason")
    p.add_argument("--supersedes", help="record-id this run's record supersedes")
    p.add_argument("--executor", choices=executor_mod.EXECUTORS + (fmax_klt.BATCH_EXECUTOR,),
                   help="default: the manifest's, else local. `batch` submits through "
                        "`klt sim --backend batch` (S3 job contract); `remote` needs the SSH fleet")
    p.add_argument("--klt-jobs", type=int, default=2,
                   help="concurrent `klt sim` submissions for the batch executor (default 2)")
    p.add_argument("--klt-cache", help="directory for per-job requests/reports of the batch "
                   "executor; re-running with the same directory reuses collected reports")
    p.add_argument("-j", "--jobs", type=int, default=1, help=f"local workers (capped at {MAX_JOBS})")
    p.add_argument("--max-local-probes", type=int, default=1,
                   help="most probes this host may simulate itself (default 1)")
    p.add_argument("--probe-mhz", type=float, help="run ONE probe at this CLK frequency locally; no record")
    p.add_argument("--allow-pdk-mismatch", action="store_true")
    return p


def main(argv=None) -> int:
    return cmd(build_parser().parse_args(argv))
