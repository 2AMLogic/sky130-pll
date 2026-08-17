"""Command-line entry point. See sim/run_corners.py and sim/harness/README.md."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import tempfile
from pathlib import Path

from . import corners as corners_mod
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


def cmd_run(args: argparse.Namespace) -> int:
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

    corners_override = _parse_list(args.corners)
    temps_override = _parse_list(args.temps, cast=float)
    is_subset = bool(corners_override or temps_override or args.supply_tol is not None)
    if is_subset and not args.subset_reason and args.write:
        print(
            "run_corners.py: a corner/temp/supply override needs --subset-reason "
            "to be recorded as evidence (sim/README.md's subset-justification rule)",
            file=sys.stderr,
        )
        return 1

    try:
        points = corners_mod.build_matrix(
            manifest,
            pdk.process_corners,
            corners_override=corners_override,
            temps_override=temps_override,
            supply_tol_override=args.supply_tol,
        )
    except corners_mod.CornerError as e:
        print(f"run_corners.py: {e}", file=sys.stderr)
        return 1

    schematic = testbench_dir / manifest["schematic"]
    xschemrc = REPO_ROOT / "sim" / "xschemrc"
    spiceinit = REPO_ROOT / "sim" / "spiceinit"

    record_id = report_mod.make_record_id(REPO_ROOT)
    exp_dir = manifest_path.parent.parent
    snapshots_dir = exp_dir / "netlist-snapshots"
    records_dir = exp_dir / "records"

    with _corners_dir(args.write, exp_dir, record_id) as corners_dir:
        print(f"run_corners.py: netlisting {schematic} ...")
        try:
            netlist_text = runner_mod.netlist_schematic(
                pdk, xschemrc, schematic, corners_dir, REPO_ROOT
            )
        except runner_mod.NetlistError as e:
            print(f"run_corners.py: {e}", file=sys.stderr)
            return 1

        results = []
        for i, point in enumerate(points, 1):
            print(f"run_corners.py: [{i}/{len(points)}] {point.corner_id} ...")
            try:
                result = runner_mod.run_point(pdk, spiceinit, manifest, netlist_text, point, corners_dir)
            except runner_mod.NetlistError as e:
                print(f"run_corners.py: {point.corner_id}: {e}", file=sys.stderr)
                return 1
            results.append(result)
            print(f"  {'PASS' if result.passed else 'FAIL'}: {result.reason}")

        failed = [r for r in results if not r.passed]

        if args.write:
            snapshots_dir.mkdir(parents=True, exist_ok=True)
            records_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = snapshots_dir / f"{record_id}.spice"
            snapshot_path.write_text(netlist_text)

            subset_reason = args.subset_reason if is_subset else None
            record_md = report_mod.render(
                record_id=record_id,
                slug=slug,
                claim=manifest.get("claim", "(no claim stated in manifest)"),
                pdk=pdk,
                tool_versions=pdk_mod.tool_versions(),
                repo_root=REPO_ROOT,
                netlist_snapshot=snapshot_path,
                points=points,
                results=results,
                subset_reason=subset_reason,
                supersedes=args.supersedes,
            )
            record_path = records_dir / f"{record_id}.md"
            record_path.write_text(record_md)
            print(f"run_corners.py: wrote {record_path}")
        else:
            print("run_corners.py: --no-write -- no evidence record written")

    print(f"run_corners.py: {len(results) - len(failed)}/{len(results)} points passed")
    return 0 if not failed else 1


def cmd_run_mc(args: argparse.Namespace) -> int:
    """Monte Carlo run mode -- see sim/harness/README.md's Monte Carlo
    section and sim/harness/montecarlo.py's module docstring for the
    sampling mechanism. Mirrors cmd_run's shape (env resolution, netlist
    once, per-point run, evidence record) with a trial matrix instead of a
    PVT point matrix.
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

    is_subset = any(
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
    if is_subset and not args.subset_reason and args.write:
        print(
            "run_corners.py: an --mc-* override needs --subset-reason to be "
            "recorded as evidence (sim/README.md's subset-justification rule)",
            file=sys.stderr,
        )
        return 1

    try:
        trials = mc_mod.build_trials(
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
    except mc_mod.McConfigError as e:
        print(f"run_corners.py: {e}", file=sys.stderr)
        return 1

    schematic = testbench_dir / manifest["schematic"]
    xschemrc = REPO_ROOT / "sim" / "xschemrc"
    spiceinit = REPO_ROOT / "sim" / "spiceinit"

    record_id = report_mod.make_record_id(REPO_ROOT)
    exp_dir = manifest_path.parent.parent
    snapshots_dir = exp_dir / "netlist-snapshots"
    records_dir = exp_dir / "records"

    with _corners_dir(args.write, exp_dir, record_id) as corners_dir:
        print(f"run_corners.py: netlisting {schematic} ...")
        try:
            netlist_text = runner_mod.netlist_schematic(
                pdk, xschemrc, schematic, corners_dir, REPO_ROOT
            )
        except runner_mod.NetlistError as e:
            print(f"run_corners.py: {e}", file=sys.stderr)
            return 1

        results = []
        for i, trial in enumerate(trials, 1):
            print(f"run_corners.py: [{i}/{len(trials)}] {trial.corner_id} ...")
            try:
                result = runner_mod.run_mc_trial(pdk, spiceinit, manifest, netlist_text, trial, corners_dir)
            except runner_mod.NetlistError as e:
                print(f"run_corners.py: {trial.corner_id}: {e}", file=sys.stderr)
                return 1
            results.append(result)
            print(f"  {'PASS' if result.passed else 'FAIL'}: {result.reason}")

        failed = [r for r in results if not r.passed]

        if args.write:
            snapshots_dir.mkdir(parents=True, exist_ok=True)
            records_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = snapshots_dir / f"{record_id}.spice"
            snapshot_path.write_text(netlist_text)

            subset_reason = args.subset_reason if is_subset else None
            mc_cfg = manifest.get("monte_carlo", {})
            claim = mc_cfg.get("claim", manifest.get("claim", "(no claim stated in manifest)"))
            record_md = report_mod.render_mc(
                record_id=record_id,
                slug=slug,
                claim=claim,
                pdk=pdk,
                tool_versions=pdk_mod.tool_versions(),
                repo_root=REPO_ROOT,
                netlist_snapshot=snapshot_path,
                trials=trials,
                results=results,
                subset_reason=subset_reason,
                supersedes=args.supersedes,
            )
            record_path = records_dir / f"{record_id}.md"
            record_path.write_text(record_md)
            print(f"run_corners.py: wrote {record_path}")
        else:
            print("run_corners.py: --no-write -- no evidence record written")

    print(f"run_corners.py: {len(results) - len(failed)}/{len(results)} trials passed")
    return 0 if not failed else 1


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
