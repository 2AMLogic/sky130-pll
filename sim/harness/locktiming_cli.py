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
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from . import fmax_klt as K
from . import locktiming as L

RECORD_SCHEMA = "sky130-pll.lockdet-timing.record/1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORDS = REPO_ROOT / "sim" / "lockdet-timing" / "records"
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
    The capacity retry mirrors `KltBatchBackend._run_group`, but a failure is
    recorded on the job instead of aborting the campaign."""
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
    for attempt in range(retries + 1):
        try:
            proc = runner(cmd, capture_output=True, text=True,
                          timeout=int(cand["manifest"]["windows"]["timeout_s"]) + 5400)
        except (OSError, subprocess.TimeoutExpired) as e:
            job["failure"] = f"klt sim did not complete: {e}"
            return out
        if (proc.returncode in K._USABLE_EXIT or attempt == retries
                or not K.is_capacity_refusal((proc.stdout or "") + (proc.stderr or ""))):
            break
        log(f"  {item['key']}: fleet at capacity; retry {attempt + 1}/{retries}")
        sleep(wait_s)
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


def execute(cands, points, *, klt, runner, work, retries=30, wait_s=120.0,
            sleep=time.sleep, log=print, split_temps=False) -> dict:
    by_uid, jobs = {}, []
    for item in plan(cands, points, split_temps):
        res = run_group(item, work, klt, runner, retries=retries, wait_s=wait_s,
                        sleep=sleep, log=log)
        jobs.append(res["job"])
        by_uid.setdefault(item["cand"]["uid"], []).extend(points_from_report(item, res))
    results, out = [], []
    for c in cands:
        rows = [dict(L.reduce_point(c["manifest"], p), reason=p["reason"])
                for p in by_uid[c["uid"]]]
        r = L.grade_candidate(c["manifest"], rows)
        results.append(r)
        r = dict(r, failed=[{"coord": list(k), "status": v} for k, v in r["failed"].items()])
        out.append({k: c[k] for k in ("manifest_path", "netlist_path", "manifest_sha256",
                                      "netlist_sha256")}
                   | {"product_id": c["uid"][0], "candidate_id": c["uid"][1],
                      "result": r, "rows": rows})
    return {"jobs": jobs, "candidates": out, "results": results}


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


def main(argv=None, *, runner=subprocess.run, sleep=time.sleep, now=None) -> int:
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
    args = ap.parse_args(argv)
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
        with tempfile.TemporaryDirectory(prefix="sky130-pll-locktiming-") as tmp:
            probe = K.KltBatchBackend(spec=None, manifest=None, work_dir=Path(tmp),
                                      cache_dir=Path(tmp), klt=args.klt)
            try:
                probe.preflight()
            except K.KltBatchError as e:
                raise RunnerError(f"{e}; no local fallback") from e
            run = execute(cands, points, klt=probe.klt, runner=runner, work=Path(tmp),
                          sleep=sleep, split_temps=args.split_temps)
            rec = {"schema": RECORD_SCHEMA,
                   "record_id": (now or (lambda: datetime.now(timezone.utc)))()
                   .strftime("lt-%Y%m%d-%H%M%S-%f"),
                   "matrix_id": sha(json.dumps([[c["manifest_sha256"], c["netlist_sha256"]]
                                                for c in cands] + [sorted(points)]).encode())[:16],
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
            probe.jobs = run["jobs"]  # retain request, body, report, stderr per group
            probe.export_jobs(records_dir / rec["record_id"])
        print(f"wrote {path} ({rec['evidence_class']})")
        return 0
    except (RunnerError, L.LockTimingError, OSError) as e:
        print(f"run_locktiming.py: {e}", file=sys.stderr)
        return 1
