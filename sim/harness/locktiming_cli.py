"""Fixed-stimulus `klt sim --backend batch` runner for the LOCK timing
primitives (issue #274, part of #259).

Plans, runs and reduces declared candidates through `locktiming.py` (the
#273 reducer contract, unchanged). Each candidate is a manifest plus a body
netlist with its stimulus fixed inside; the single placeholder `@VDD@` is the
supply value. klt owns `.control`, the process/temperature axes and waveform
capture, so one request ("group") is one candidate x one supply, with the
process x temperature matrix as klt corners. No per-coordinate sweep engine.

Failure policy: a failed group (submit, capacity, version refusal, missing
report) turns every coordinate it covered into an explicit `SIM_FAILED` row
carrying the reason. Nothing is simulated locally and nothing is invented.
Stdlib only; PDK-free.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from . import fmax_klt as K
from . import locktiming as L

RECORD_SCHEMA = "sky130-pll.lockdet-timing.record/1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORDS = REPO_ROOT / "sim" / "lockdet-timing" / "records"
NOMINAL = ("tt", 27.0, 1.8)
_STRIP = re.compile(r"^\s*(\.lib\s.*|\.end|\.control|\.endc)\s*$", re.IGNORECASE)
_BAD_CORNER = ("error", "inconclusive", "not_checked")


class RunnerError(RuntimeError):
    pass


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def required_traces(m: dict) -> list:
    me = m["measurement"]
    names = [me[k][f] for k in ("acq", "rel") for f in ("input", "tap")]
    names += [me[k]["signal"] for k in ("tick", "raw", "startup")]
    return sorted(set(names))


def load_candidate(spec: str) -> dict:
    mp, _, np_ = spec.partition("=")
    if not np_:
        raise RunnerError(f"--candidate must be MANIFEST=NETLIST, got {spec!r}")
    mtext = Path(mp).read_bytes()
    ntext = Path(np_).read_bytes()
    try:
        m = L.validate_manifest(json.loads(mtext))
    except (ValueError, L.LockTimingError) as e:
        raise RunnerError(f"{mp}: {e}") from e
    if b"@VDD@" not in ntext:
        raise RunnerError(f"{np_}: netlist must contain the @VDD@ supply placeholder")
    return {"manifest": m, "manifest_path": mp, "netlist_path": np_, "netlist": ntext.decode(),
            "manifest_sha256": sha(mtext), "netlist_sha256": sha(ntext)}


def select_points(which: str) -> list:
    if which == "all":
        return list(L.GRID)
    if which == "nominal":
        return [NOMINAL]
    raise RunnerError("--points must be 'nominal' or 'all'")


def body_for(cand: dict, vdd: float) -> str:
    lines = [l for l in cand["netlist"].replace("@VDD@", f"{vdd:g}").splitlines()
             if not _STRIP.match(l)]
    saves = " ".join(f"v({t})" for t in required_traces(cand["manifest"]))
    return "\n".join(lines + [f".save {saves}"]) + "\n"


def plan(cands: list, points: list) -> list:
    """One group per candidate x supply (process x temperature as klt corners)."""
    groups = []
    for c in cands:
        for vdd in sorted({p[2] for p in points}):
            at = [p for p in points if p[2] == vdd]
            g = K.Group(n=0, supply_v=vdd, freqs={0.0: 0})
            g.processes = [p for p in L.PROCESSES if any(a[0] == p for a in at)]
            g.temps = [t for t in L.TEMPS_C if any(a[1] == t for a in at)]
            g.needed = {(a[0], a[1]) for a in at}
            groups.append({"cand": c, "group": g,
                           "key": f"{c['manifest']['candidate_id']}_{vdd:.2f}v"})
    return groups


def build_group_request(cand: dict, g: K.Group, *, max_workers: int = 2) -> dict:
    w = cand["manifest"]["windows"]
    spec = SimpleNamespace(criterion=SimpleNamespace(tran_step_s=w["step_s"]))
    req = K.build_request(spec, g, w["window_stop_s"], timeout_s=int(w["timeout_s"]),
                          max_workers=max_workers)
    req["measurements"] = []  # raw traces are the product; the reducer measures them
    req["batch"]["poll_timeout_s"] = int(w["timeout_s"]) + 3600
    return req


def plan_report(groups: list, points: list, which: str) -> dict:
    return {"points_label": which if len(points) == 45 else f"SUBSET_POINTS:{which}",
            "points_requested": len(points),
            "candidates": sorted({(g["cand"]["manifest"]["product_id"],
                                   g["cand"]["manifest"]["candidate_id"]) for g in groups}),
            "groups": [{"key": g["key"], "supply_v": g["group"].supply_v,
                        "corners": sorted(g["group"].needed),
                        "excluded": g["group"].excluded,
                        "required_traces": required_traces(g["cand"]["manifest"]),
                        "outputs": ["request.json", "body.spice", "report.json",
                                    "<corner>/waveform"],
                        "manifest_sha256": g["cand"]["manifest_sha256"],
                        "netlist_sha256": g["cand"]["netlist_sha256"],
                        "request": build_group_request(g["cand"], g["group"])}
                       for g in groups]}


def read_waves(path, names) -> dict:
    """{name: {t, v}} from a klt waveform JSON; names not present are omitted
    (the reducer then reports a missing trace, never an invented one)."""
    wave = json.loads(Path(path).read_text())
    cols = {v["name"].lower(): i for i, v in enumerate(wave["variables"])}
    pts = wave["points"]
    out = {}
    for n in names:
        i = cols.get(f"v({n})".lower())
        if i is not None:
            out[n] = {"t": [p[0] for p in pts], "v": [p[i] for p in pts]}
    return out


def run_group(item: dict, work: Path, klt: str, runner, *, retries: int, wait_s: float,
              sleep, log) -> dict:
    """-> {"job": provenance, "points": {coord: point-dict}} ; failure -> reason."""
    cand, g = item["cand"], item["group"]
    gdir = work / item["key"]
    gdir.mkdir(parents=True, exist_ok=True)
    body = body_for(cand, g.supply_v)
    req = build_group_request(cand, g)
    (gdir / K.NET_NAME).write_text(body)
    (gdir / K.REQUEST_NAME).write_text(json.dumps(req, indent=1, sort_keys=True) + "\n")
    job = {"group": item["key"], "supply_v": g.supply_v, "job_id": None,
           "netlist_sha256": sha(body.encode()),
           "request_sha256": sha((gdir / K.REQUEST_NAME).read_bytes()), "failure": None}

    def fail(msg):
        job["failure"] = msg
        return {"job": job, "report": None}

    cmd = [klt, "sim", str(gdir / K.REQUEST_NAME), "-o", str(gdir / "out"),
           "--backend", "batch", "--format", "json"]
    attempt = 0
    while True:
        try:
            proc = runner(cmd, capture_output=True, text=True,
                          timeout=int(cand["manifest"]["windows"]["timeout_s"]) + 5400)
        except (OSError, subprocess.TimeoutExpired) as e:
            return fail(f"klt sim did not complete: {e}")
        if (proc.returncode not in K._USABLE_EXIT and attempt < retries
                and K.is_capacity_refusal((proc.stdout or "") + (proc.stderr or ""))):
            attempt += 1
            log(f"  {item['key']}: fleet at capacity; retry {attempt}/{retries}")
            sleep(wait_s)
            continue
        break
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        return fail(f"klt sim exit {proc.returncode} with no JSON report: "
                    f"{(proc.stderr or proc.stdout or '').strip()[-500:]}")
    (gdir / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    env = report.get("environment") or {}
    remote = env.get("remote") or {}
    job.update(job_id=remote.get("job_id"), engine_version=env.get("engine_version"),
               runner_klt_version=remote.get("runner_klt_version"),
               client_klt_version=remote.get("client_klt_version"),
               instance_type=remote.get("instance_type"), pdk=req["models"])
    bad = K.job_level_failure(report)
    if bad:
        return fail(bad)
    return {"job": job, "report": report, "gdir": gdir}


def points_from_report(item: dict, res: dict, wanted: list) -> list:
    """Raw per-coordinate points for one group; failures carry a reason."""
    g, names = item["group"], required_traces(item["cand"]["manifest"])
    out = []
    for proc, temp, vdd in wanted:
        coord = {"process": proc, "temp_c": temp, "vdd_v": vdd}
        pt = {"coord": coord, "sim_ok": False, "waveforms": {}, "reason": res["job"]["failure"]}
        c = K.find_corner(res["report"], proc, temp) if res["report"] else None
        if res["report"] and c is None:
            pt["reason"] = "corner missing from the report"
        elif c is not None and c.get("status") in _BAD_CORNER:
            diag = "; ".join(f"{d.get('code')}: {d.get('message', '')}"
                             for d in c.get("diagnostics") or [])
            pt["reason"] = "simulator: " + (diag or c.get("status"))
        elif c is not None:
            wf = K.KltBatchBackend._artifact((c.get("artifacts") or {}).get("waveform"),
                                             res["gdir"])
            try:
                pt.update(waveforms=read_waves(wf, names), sim_ok=True, reason=None)
            except (OSError, ValueError, KeyError, TypeError) as e:
                pt["reason"] = f"unreadable or missing waveform: {e}"
        out.append(pt)
    return out


def matrix_id(cands, points) -> str:
    key = json.dumps([[c["manifest_sha256"], c["netlist_sha256"]] for c in cands]
                     + [sorted(points)], sort_keys=True)
    return sha(key.encode())[:16]


def execute(cands, points, which, *, klt, runner, work, retries=30, wait_s=120.0,
            sleep=None, log=print) -> dict:
    import time
    sleep = sleep or time.sleep
    groups = plan(cands, points)
    by_cand: dict = {}
    jobs = []
    for item in groups:
        res = run_group(item, work, klt, runner, retries=retries, wait_s=wait_s,
                        sleep=sleep, log=log)
        jobs.append(res["job"])
        wanted = [p for p in points if p[2] == item["group"].supply_v]
        by_cand.setdefault(item["cand"]["manifest"]["candidate_id"], []).extend(
            points_from_report(item, res, wanted))
    results, cand_out = [], []
    for c in cands:
        m, cid = c["manifest"], c["manifest"]["candidate_id"]
        raw = by_cand[cid]
        rows = []
        for p in raw:
            r = L.reduce_point(m, p)
            r["reason"] = p.get("reason")
            rows.append(r)
        res = L.grade_candidate(m, rows)
        results.append(res)
        res = dict(res, failed=[{"coord": list(k), "status": v} for k, v in res["failed"].items()])
        cand_out.append({"product_id": m["product_id"], "candidate_id": cid,
                         "manifest_path": c["manifest_path"], "netlist_path": c["netlist_path"],
                         "manifest_sha256": c["manifest_sha256"],
                         "netlist_sha256": c["netlist_sha256"], "result": res, "rows": rows})
    return {"jobs": jobs, "candidates": cand_out, "results": results}


def evidence_class(run: dict, fixture: bool) -> str:
    """`physical` only when every group came from a real batch job (job id) and
    the run was not declared a fixture; fixtures can never be physical."""
    if fixture:
        return "fixture"
    ok = bool(run["jobs"]) and all(j.get("job_id") and not j.get("failure") for j in run["jobs"])
    return "physical" if ok else "incomplete-not-physical"


def write_record(rec: dict, records_dir: Path, supersedes: str | None) -> Path:
    records_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.stem: json.loads(p.read_text()) for p in records_dir.glob("*.json")}
    if supersedes is not None and supersedes not in existing:
        raise RunnerError(f"--supersedes {supersedes!r} names no record in {records_dir}")
    prior = [k for k, v in existing.items() if v.get("matrix_id") == rec["matrix_id"]]
    if prior and supersedes is None:
        raise RunnerError(f"same matrix already recorded ({', '.join(sorted(prior))}); "
                          "rerun with --supersedes <record-id>")
    rec["supersedes"] = supersedes
    path = records_dir / f"{rec['record_id']}.json"
    if path.exists():
        raise RunnerError(f"{path} exists; records are append-only")
    path.write_text(json.dumps(rec, indent=1, sort_keys=True, default=list) + "\n")
    return path


def main(argv=None, *, runner=subprocess.run, sleep=None) -> int:
    ap = argparse.ArgumentParser(prog="run_locktiming.py", description=__doc__.split("\n")[0])
    ap.add_argument("--candidate", action="append", required=True, metavar="MANIFEST=NETLIST")
    ap.add_argument("--points", default="nominal", choices=("nominal", "all"))
    ap.add_argument("--required-products", help="three comma-separated product ids")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; no PDK, no job")
    ap.add_argument("--fixture", action="store_true",
                    help="label the record a fixture (requires --records-dir)")
    ap.add_argument("--records-dir", type=Path)
    ap.add_argument("--supersedes")
    ap.add_argument("--klt")
    args = ap.parse_args(argv)
    try:
        cands = [load_candidate(s) for s in args.candidate]
        ids = [(c["manifest"]["product_id"], c["manifest"]["candidate_id"]) for c in cands]
        if len(set(ids)) != len(ids):
            raise RunnerError("duplicate product/candidate id")
        points = select_points(args.points)
        if args.dry_run:
            print(json.dumps(plan_report(plan(cands, points), points, args.points),
                             indent=1, default=list))
            return 0
        if args.fixture and not args.records_dir:
            raise RunnerError("--fixture needs an explicit --records-dir (never the default)")
        records_dir = args.records_dir or DEFAULT_RECORDS
        probe = K.KltBatchBackend(spec=None, manifest=None, work_dir=Path("."), klt=args.klt)
        try:
            probe.preflight()
        except K.KltBatchError as e:
            raise RunnerError(f"{e}; no local fallback") from e
        with tempfile.TemporaryDirectory(prefix="sky130-pll-locktiming-") as tmp:
            run = execute(cands, points, args.points, klt=probe.klt, runner=runner,
                          work=Path(tmp), sleep=sleep)
            required = args.required_products.split(",") if args.required_products else None
            rec = {
                "schema": RECORD_SCHEMA,
                "record_id": datetime.now(timezone.utc).strftime("lt-%Y%m%d-%H%M%S"),
                "matrix_id": matrix_id(cands, points),
                "evidence_class": evidence_class(run, args.fixture),
                "points_scope": args.points if len(points) == 45 else f"SUBSET_POINTS:{args.points}",
                "points_requested": len(points),
                "pdk_pin": json.loads((REPO_ROOT / "sim" / "pdk.json").read_text())
                .get("open_pdks_commit"),
                "grouping": "one klt request per candidate x supply; process x temperature "
                            "as klt corners",
                "jobs": run["jobs"], "candidates": run["candidates"],
                "handoff": L.handoff(run["results"], required) if required else
                {"scope": "SUBSET", "products_absent": "required products not declared",
                 "handoff_ready": False},
            }
            path = write_record(rec, records_dir, args.supersedes)
            # retain each group's request, body netlist and report beside the record
            for j in run["jobs"]:
                dst = records_dir / rec["record_id"] / j["group"]
                dst.mkdir(parents=True, exist_ok=True)
                for name in (K.REQUEST_NAME, K.NET_NAME, "report.json"):
                    if (Path(tmp) / j["group"] / name).is_file():
                        (dst / name).write_bytes((Path(tmp) / j["group"] / name).read_bytes())
        print(f"wrote {path} ({rec['evidence_class']})")
        return 0
    except (RunnerError, L.LockTimingError, OSError) as e:
        print(f"run_locktiming.py: {e}", file=sys.stderr)
        return 1
