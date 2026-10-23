"""Fixed-stimulus `klt sim --backend batch` runner for the LOCK timing
primitives (issue #274, part of #259).

Plans, runs and reduces declared candidates through the unchanged #273
reducer (`locktiming.py`). A candidate is a manifest plus a body netlist with
its stimulus fixed inside and one `@VDD@` supply placeholder. klt owns
`.control`, the process/temperature axes and waveform capture, so one request
("group") is one (product, candidate) x one supply, process x temperature as
klt corners. Every failure (submit, capacity, nonzero exit, version refusal,
missing report/corner/trace) becomes an explicit `SIM_FAILED` row with a
reason; nothing is simulated locally and nothing is invented. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from . import evidence_store as E
from . import fmax_klt as K
from . import locktiming as L

RECORD_SCHEMA = "sky130-pll.lockdet-timing.record/1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORDS = REPO_ROOT / "sim" / "lockdet-timing" / "records"
BENCH = "lockdet-timing"
EVIDENCE_FILES = (K.REQUEST_NAME, K.NET_NAME, "report.json", "stderr.log")
_NOT_RID = re.compile(r"[^A-Za-z0-9._-]")
_STRIP = re.compile(r"^\s*(\.lib\s.*|\.end|\.control|\.endc)\s*$", re.IGNORECASE)


class RunnerError(RuntimeError):
    pass


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def required_traces(m: dict) -> list:
    me = m["measurement"]
    return sorted({me[k][f] for k in ("acq", "rel") for f in ("input", "tap")}
                  | {me[k]["signal"] for k in ("tick", "raw", "startup")})


def load_candidate(spec: str) -> dict:
    mp, _, np_ = spec.partition("=")
    if not np_:
        raise RunnerError(f"--candidate must be MANIFEST=NETLIST, got {spec!r}")
    mtext, ntext = Path(mp).read_bytes(), Path(np_).read_bytes()
    try:
        m = L.validate_manifest(json.loads(mtext))
    except (ValueError, L.LockTimingError) as e:
        raise RunnerError(f"{mp}: {e}") from e
    if b"@VDD@" not in ntext:
        raise RunnerError(f"{np_}: netlist must contain the @VDD@ supply placeholder")
    return {"manifest": m, "uid": (m["product_id"], m["candidate_id"]), "manifest_path": mp,
            "netlist_path": np_, "netlist": ntext.decode(),
            "manifest_sha256": sha(mtext), "netlist_sha256": sha(ntext)}


def body_for(cand: dict, vdd: float) -> str:
    lines = [l for l in cand["netlist"].replace("@VDD@", f"{vdd:g}").splitlines()
             if not _STRIP.match(l)]
    return "\n".join(lines + [".save " + " ".join(
        f"v({t})" for t in required_traces(cand["manifest"]))]) + "\n"


def plan(cands: list, points: list, split_temps: bool = False) -> list:
    """One group per (product, candidate) x supply; process x temperature as klt corners.
    `split_temps` makes one group per supply x temperature (5 corners) so each fleet
    job stays under the whole-job ceiling."""
    groups = []
    for c in cands:
        for vdd in sorted({p[2] for p in points}):
            at = [p for p in points if p[2] == vdd]
            for tsel in (sorted({a[1] for a in at}) if split_temps else [None]):
                sub = [a for a in at if tsel is None or a[1] == tsel]
                g = K.Group(n=0, supply_v=vdd, needed={(a[0], a[1]) for a in sub},
                            processes=[p for p in L.PROCESSES if any(a[0] == p for a in sub)],
                            temps=[t for t in L.TEMPS_C if any(a[1] == t for a in sub)])
                suffix = "" if tsel is None else "_{:+g}c".format(tsel)
                groups.append({"cand": c, "group": g, "points": sub,
                               "key": "{}.{}_{:.2f}v{}".format(*c["uid"], vdd, suffix)})
    return groups


def build_group_request(cand: dict, g: K.Group) -> dict:
    w = cand["manifest"]["windows"]
    spec = SimpleNamespace(criterion=SimpleNamespace(tran_step_s=w["step_s"]))
    req = K.build_request(spec, g, w["window_stop_s"], timeout_s=int(w["timeout_s"]),
                          max_workers=2)
    req["measurements"] = []  # raw traces are the product; the reducer measures them
    # Save only the netlist's own `.save` vectors (RAW/TICK), not `save all`:
    # a full-node ASCII raw of a 29-stage ring + dividers is ~1.8 GB per corner.
    req["options"]["save_mode"] = "netlist"
    req["batch"]["poll_timeout_s"] = int(w["timeout_s"]) + 3600
    return req


def scope(points: list, which: str) -> str:
    return which if len(points) == len(L.GRID) else f"SUBSET_POINTS:{which}"


def read_waves(path, names) -> dict:
    """{name: {t, v}} from a klt waveform JSON; absent names are omitted so the
    reducer reports a missing trace, never an invented one."""
    wave = json.loads(Path(path).read_text())
    cols = {v["name"].lower(): i for i, v in enumerate(wave["variables"])}
    pts = wave["points"]
    return {n: {"t": [p[0] for p in pts], "v": [p[cols[f"v({n})"]] for p in pts]}
            for n in names if f"v({n})" in cols}


def waveform_only_exit(report: dict) -> bool:
    """klt exits 4 ("nothing checked") when a request declares no measurements,
    which is this runner's design: raw traces are the product. That exit is
    usable only if the report says exactly that and every corner passed."""
    cov, corners = report.get("coverage") or {}, report.get("corners") or []
    return (bool(corners) and all(c.get("status") == "pass" for c in corners)
            and cov.get("nothing_checked") is True
            and cov.get("nothing_checked_reasons") == ["no_requested_measurements"])


def run_group(item: dict, work: Path, klt: str, runner, *, retries, wait_s, sleep, log) -> dict:
    """Submit one group; -> {"job": provenance, "report": dict | None, "gdir": Path}.
    The capacity retry is the shared `submit_with_capacity_retry`, but a failure
    is recorded on the job instead of aborting the campaign."""
    cand, g, gdir = item["cand"], item["group"], work / item["key"]
    gdir.mkdir(parents=True, exist_ok=True)
    body = body_for(cand, g.supply_v)
    (gdir / K.NET_NAME).write_text(body)
    req = build_group_request(cand, g)
    (gdir / K.REQUEST_NAME).write_text(json.dumps(req, indent=1, sort_keys=True) + "\n")
    job = {"group": item["key"], "dir": item["key"], "supply_v": g.supply_v, "job_id": None,
           "netlist_sha256": sha(body.encode()), "pdk": req["models"], "failure": None,
           "request_sha256": sha((gdir / K.REQUEST_NAME).read_bytes())}
    out = {"job": job, "report": None, "gdir": gdir}
    cmd = [klt, "sim", str(gdir / K.REQUEST_NAME), "-o", str(gdir / "out"),
           "--backend", "batch", "--format", "json"]
    try:
        proc, _ = K.submit_with_capacity_retry(
            cmd, runner=runner, timeout=int(cand["manifest"]["windows"]["timeout_s"]) + 5400,
            usable_exit=K._USABLE_EXIT, retries=retries, wait_s=wait_s, sleep=sleep, log=log,
            label=f"  {item['key']}")
    except (OSError, subprocess.TimeoutExpired) as e:
        job["failure"] = f"klt sim did not complete: {e}"
        return out
    job["exit_code"] = proc.returncode
    (gdir / "stderr.log").write_text(proc.stderr or "")
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        job["failure"] = (f"klt sim exit {proc.returncode} with no JSON report: "
                          f"{(proc.stderr or proc.stdout or '').strip()[-500:]}")
        return out
    (gdir / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    env = report.get("environment") or {}
    rm = env.get("remote") or {}
    job.update(job_id=rm.get("job_id"), engine_version=env.get("engine_version"),
               runner_klt_version=rm.get("runner_klt_version"),
               client_klt_version=rm.get("client_klt_version"),
               version_skew=rm.get("runner_klt_version") != rm.get("client_klt_version"),
               instance_type=rm.get("instance_type"))
    job["failure"] = K.job_level_failure(report) or (
        None if proc.returncode in K._USABLE_EXIT or (
            proc.returncode == 4 and waveform_only_exit(report))
        else f"klt sim exit {proc.returncode}")
    if job["failure"] == "klt sim exit 4":  # say why, e.g. a simulator nonconvergence
        why = sorted({f"{d.get('code')}: {d.get('message', '')}" for c in report.get("corners") or []
                      for d in c.get("diagnostics") or [] if d.get("severity") == "error"})
        if why:
            job["failure"] += " (" + "; ".join(why) + ")"
    out["report"] = None if job["failure"] else report
    return out


def points_from_report(item: dict, res: dict) -> list:
    """Raw per-coordinate reducer inputs for one group; failures carry a reason."""
    names, rep, out = required_traces(item["cand"]["manifest"]), res["report"], []
    for proc, temp, vdd in item["points"]:
        pt = {"coord": {"process": proc, "temp_c": temp, "vdd_v": vdd}, "sim_ok": False,
              "waveforms": {}, "reason": res["job"]["failure"]}
        c = K.find_corner(rep, proc, temp) if rep else None
        if rep and c is None:
            pt["reason"] = "corner missing from the report"
        elif c is not None and c.get("status") in ("error", "inconclusive", "not_checked"):
            pt["reason"] = "simulator: " + ("; ".join(
                f"{d.get('code')}: {d.get('message', '')}" for d in c.get("diagnostics") or [])
                or c.get("status"))
        elif c is not None:
            wf = K.KltBatchBackend._artifact((c.get("artifacts") or {}).get("waveform"),
                                             res["gdir"])
            try:
                pt.update(waveforms=read_waves(wf, names), sim_ok=True, reason=None)
            except (OSError, ValueError, KeyError, TypeError) as e:
                pt["reason"] = f"unreadable or missing waveform: {e}"
        out.append(pt)
    return out


GROUP_SCHEMA = "sky130-pll.lockdet-timing.group/1"


def matrix_id(cands, points) -> str:
    return sha(json.dumps([[c["manifest_sha256"], c["netlist_sha256"]] for c in cands]
                          + [sorted(points)]).encode())[:16]


def load_group_records(gdir: Path) -> dict:
    """{group key: [records, oldest first]} from an append-only group-record directory."""
    out = {}
    for p in sorted(gdir.glob("*.json")) if gdir.is_dir() else []:
        r = json.loads(p.read_text())
        out.setdefault(r["group"], []).append(dict(r, _stem=p.stem))
    return out


def group_done(recs: list) -> dict | None:
    """Latest record of a group whose job succeeded, else None (failed groups are rerun)."""
    ok = [r for r in recs if not r["job"].get("failure")]
    return ok[-1] if ok else None


class GroupStore:
    """Stages one finished group's bytes under the git-ignored `sim/build/` and
    stores them with `klt artifact put` (DR-012, DR-013). `put=None` is the real
    `klt`; tests inject a fake. `repo_root` decides where manifests land."""

    def __init__(self, repo_root: Path = REPO_ROOT, put=None, preflight=E.preflight):
        self.repo_root, self.put, self._preflight = repo_root, put, preflight

    @property
    def stage_root(self) -> Path:
        return self.repo_root / "sim" / "build" / BENCH

    def preflight(self) -> None:
        self._preflight(self.repo_root)

    def store_group(self, mid: str, stem: str, src: Path) -> str:
        """Stage `src`'s evidence files, store them, install the group manifest;
        -> the manifest path relative to the repo. Raises `E.StoreError`, leaving
        the staged bytes in place and nothing in git."""
        rid = _NOT_RID.sub("_", stem)
        stage = self.stage_root / mid / rid
        stage.mkdir(parents=True, exist_ok=True)
        for name in EVIDENCE_FILES:
            if (src / name).is_file():
                shutil.copy2(src / name, stage / name)
        files = E.stage_files(stage, f"sim/{BENCH}/groups/{mid}/{rid}")
        mpath = E.manifest_path(self.repo_root, BENCH, rid)
        if mpath.exists():
            raise E.StoreError(f"{mpath.name} already exists; refusing to overwrite evidence")
        manifest, _empty = (self.put or E.put_files)(files, self.repo_root)
        E.install_manifest(manifest, mpath)
        return mpath.relative_to(self.repo_root).as_posix()


def write_group_record(gdir: Path, item: dict, res: dict, rows: list, supersedes,
                       store: GroupStore) -> Path:
    """Persist one finished group immediately; exclusive create, never overwrite.
    The group's bytes go to the artifact store first; only the small JSON record
    (the resume state) and the manifest reference land in git."""
    gdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    stem = f"{item['key']}.{stamp}"
    path = gdir / f"{stem}.json"
    if path.exists():
        raise FileExistsError(path)
    res["job"]["evidence_manifest"] = store.store_group(gdir.name, stem, res["gdir"])
    rec = {"schema": GROUP_SCHEMA, "group": item["key"], "job": res["job"], "rows": rows,
           "supersedes": supersedes}
    with open(path, "x") as f:  # raises FileExistsError rather than editing a record
        f.write(json.dumps(rec, indent=1, sort_keys=True, default=list) + "\n")
    return path


def execute(cands, points, *, klt, runner, work, retries=30, wait_s=120.0,
            sleep=time.sleep, log=print, split_temps=False, groups_dir=None,
            resume=False, max_groups=None, only=None, store=None) -> dict:
    """Run the plan. With `groups_dir`, every finished group is written there at once
    (append-only). `resume` skips groups that already have a successful record;
    `max_groups` bounds the jobs submitted in this invocation. `pending` lists the
    group keys still lacking a successful record. `store` (a `GroupStore`) is
    required with `groups_dir`: the group bytes never go to git."""
    if groups_dir and store is None:
        raise RunnerError("group records need an evidence store (DR-013)")
    by_uid, jobs, pending, submitted = {}, [], [], 0
    prior = load_group_records(groups_dir) if groups_dir else {}
    for item in plan(cands, points, split_temps):
        key, done = item["key"], group_done(prior.get(item["key"], []))
        if resume and done:
            log(f"  {key}: already recorded ({done['_stem']}); skipped")
            jobs.append(done["job"])
            by_uid.setdefault(item["cand"]["uid"], []).extend(done["rows"])
            continue
        if (only and not re.search(only, key)) or (
                max_groups is not None and submitted >= max_groups):
            pending.append(key)
            continue
        submitted += 1
        res = run_group(item, work, klt, runner, retries=retries, wait_s=wait_s,
                        sleep=sleep, log=log)
        pts = points_from_report(item, res)
        rows = [dict(L.reduce_point(item["cand"]["manifest"], p), reason=p["reason"])
                for p in pts]
        if groups_dir:
            hist = prior.get(key) or []
            write_group_record(groups_dir, item, res, rows,
                               hist[-1]["_stem"] if hist else None, store)
        if res["job"].get("failure"):
            pending.append(key)
        jobs.append(res["job"])
        by_uid.setdefault(item["cand"]["uid"], []).extend(rows)
    results, out = [], []
    for c in cands:
        rows = by_uid.get(c["uid"], [])
        r = L.grade_candidate(c["manifest"], rows)
        results.append(r)
        r = dict(r, failed=[{"coord": list(k), "status": v} for k, v in r["failed"].items()])
        out.append({k: c[k] for k in ("manifest_path", "netlist_path", "manifest_sha256",
                                      "netlist_sha256")}
                   | {"product_id": c["uid"][0], "candidate_id": c["uid"][1],
                      "result": r, "rows": rows})
    return {"jobs": jobs, "candidates": out, "results": results, "pending": pending}


def evidence_class(run: dict, fixture: bool) -> str:
    """`physical` only when every group came from a real batch job (job id, no
    failure) and the run was not declared a fixture; fixtures are never physical."""
    if fixture:
        return "fixture"
    ok = bool(run["jobs"]) and all(j.get("job_id") and not j.get("failure") for j in run["jobs"])
    return "physical" if ok else "incomplete-not-physical"


def write_record(rec: dict, records_dir: Path, supersedes: str | None) -> Path:
    records_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.stem: json.loads(p.read_text()) for p in records_dir.glob("*.json")}
    if supersedes is not None and supersedes not in existing:
        raise RunnerError(f"--supersedes {supersedes!r} names no record in {records_dir}")
    prior = sorted(k for k, v in existing.items() if v.get("matrix_id") == rec["matrix_id"])
    if prior and supersedes is None:
        raise RunnerError(f"same matrix already recorded ({', '.join(prior)}); "
                          "rerun with --supersedes <record-id>")
    path = records_dir / f"{rec['record_id']}.json"
    if path.exists():
        raise RunnerError(f"{path} exists; records are append-only")
    path.write_text(json.dumps(dict(rec, supersedes=supersedes), indent=1, sort_keys=True,
                               default=list) + "\n")
    return path


def main(argv=None, *, runner=subprocess.run, sleep=time.sleep, now=None,
         store=None) -> int:
    ap = argparse.ArgumentParser(prog="run_locktiming.py", description=__doc__.split("\n")[0])
    ap.add_argument("--candidate", action="append", required=True, metavar="MANIFEST=NETLIST")
    ap.add_argument("--points", default="nominal", choices=("nominal", "all"))
    ap.add_argument("--required-products", help="exactly three comma-separated product ids")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; no PDK, no job")
    ap.add_argument("--fixture", action="store_true",
                    help="label the record a fixture (requires --records-dir)")
    ap.add_argument("--records-dir", type=Path)
    ap.add_argument("--supersedes")
    ap.add_argument("--klt")
    ap.add_argument("--split-temps", action="store_true",
                    help="one fleet job per supply x temperature (keeps each job under the ceiling)")
    ap.add_argument("--resume", action="store_true",
                    help="skip groups already recorded under <records-dir>/groups/<matrix-id>/; "
                         "write the combined record only once every group has a good record "
                         "(or with --finalize-incomplete)")
    ap.add_argument("--max-groups", type=int, metavar="N",
                    help="submit at most N fleet jobs in this invocation (bounded run)")
    ap.add_argument("--only", metavar="REGEX",
                    help="submit only groups whose key matches (e.g. '1\\.80v'); others stay pending")
    ap.add_argument("--finalize-incomplete", action="store_true",
                    help="with --resume/--max-groups, write the combined record even though "
                         "groups are missing or failed (they grade SIM_FAILED/absent)")
    args = ap.parse_args(argv)
    store = store or GroupStore()
    try:
        cands = [load_candidate(s) for s in args.candidate]
        if len({c["uid"] for c in cands}) != len(cands):
            raise RunnerError("duplicate product/candidate id")
        required = args.required_products.split(",") if args.required_products else None
        if required is not None and (len(required) != L.REQUIRED_PRODUCT_COUNT
                                     or len(set(required)) != len(required)):
            raise RunnerError(f"--required-products must name "
                              f"{L.REQUIRED_PRODUCT_COUNT} distinct ids")
        points = [("tt", 27.0, 1.8)] if args.points == "nominal" else list(L.GRID)
        groups = plan(cands, points, args.split_temps)
        if args.dry_run:
            print(json.dumps({"points_label": scope(points, args.points),
                              "points_requested": len(points),
                              "candidates": sorted(c["uid"] for c in cands), "groups": [
                {"key": g["key"], "supply_v": g["group"].supply_v,
                 "corners": sorted(g["group"].needed), "excluded": g["group"].excluded,
                 "required_traces": required_traces(g["cand"]["manifest"]),
                 "outputs": [K.REQUEST_NAME, K.NET_NAME, "report.json", "<corner>/waveform"],
                 "manifest_sha256": g["cand"]["manifest_sha256"],
                 "netlist_sha256": g["cand"]["netlist_sha256"],
                 "request": build_group_request(g["cand"], g["group"])} for g in groups]},
                indent=1, default=list))
            return 0
        if args.fixture and not args.records_dir:
            raise RunnerError("--fixture needs an explicit --records-dir (never the default)")
        records_dir = args.records_dir or DEFAULT_RECORDS
        try:  # DR-013: refuse before spending fleet time on a run that cannot be stored
            store.preflight()
        except E.StoreError as e:
            raise RunnerError(f"cannot store evidence: {e}; no fallback to committing "
                              "the bytes (DR-012)") from e
        with tempfile.TemporaryDirectory(prefix="sky130-pll-locktiming-") as tmp:
            probe = K.KltBatchBackend(spec=None, manifest=None, work_dir=Path(tmp),
                                      cache_dir=Path(tmp), klt=args.klt)
            try:
                probe.preflight()
            except K.KltBatchError as e:
                raise RunnerError(f"{e}; no local fallback") from e
            mid = matrix_id(cands, points)
            run = execute(cands, points, klt=probe.klt, runner=runner, work=Path(tmp),
                          sleep=sleep, split_temps=args.split_temps,
                          groups_dir=records_dir / "groups" / mid, resume=args.resume,
                          max_groups=args.max_groups, only=args.only, store=store)
            if (args.resume or args.max_groups is not None or args.only) and run["pending"] \
                    and not args.finalize_incomplete:
                print(f"{len(run['pending'])} group(s) still lacking a good record "
                      f"({', '.join(run['pending'])}); group records are under "
                      f"{records_dir / 'groups' / mid}; no combined record written")
                return 0
            rec = {"schema": RECORD_SCHEMA,
                   "record_id": (now or (lambda: datetime.now(timezone.utc)))()
                   .strftime("lt-%Y%m%d-%H%M%S-%f"),
                   "matrix_id": mid,
                   "evidence_class": evidence_class(run, args.fixture),
                   "points_scope": scope(points, args.points), "points_requested": len(points),
                   "pdk_pin": json.loads((REPO_ROOT / "sim" / "pdk.json").read_text())
                   .get("open_pdks_commit"),
                   "grouping": "one klt request per (product, candidate) x supply; "
                               "process x temperature as klt corners",
                   "jobs": run["jobs"], "candidates": run["candidates"],
                   "handoff": L.handoff(run["results"], required) if required else
                   {"scope": "SUBSET", "products_absent": "required products not declared",
                    "handoff_ready": False}}
            path = write_record(rec, records_dir, args.supersedes)
        print(f"wrote {path} ({rec['evidence_class']})")
        return 0
    except E.StoreError as e:
        print(f"run_locktiming.py: evidence NOT stored, group record not written: {e}. "
              f"Staged bytes are kept under {store.stage_root}; nothing was committed "
              "(DR-012, no fallback to committing bytes)", file=sys.stderr)
        return 1
    except (RunnerError, L.LockTimingError, OSError) as e:
        print(f"run_locktiming.py: {e}", file=sys.stderr)
        return 1
