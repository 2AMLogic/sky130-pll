"""`klt sim --backend batch` route for the divider Fmax campaign (issue #244).

The Fmax grid is thousands of transient runs and belongs on the Spot batch
fleet. `sim/harness/executor.py`'s `remote` backend needs the SSH fleet
(`klayout_tools.remote_fleet`), which a dispatch worker is not provisioned
for; the supported route there is the `klt sim` S3 job contract. This module
adapts the campaign to that route without touching the judge: every probe is
still classified by `fmax.classify_waveform` from the divider output trace.

Shape of the adaptation
-----------------------

`klt sim` owns the deck's single `.control` block, its process/temperature
axes and its waveform capture. It cannot `alter` a PULSE/PWL source, so a
probe's stimulus (period, pulse width, rail-tracking amplitude, reset) must be
fixed in the netlist body. One request ("group") therefore covers:

  * one modulus N and one supply (the supply sets V1 and the CLK/RESETB high
    level, exactly as `fmax.patch_stimulus` does in the per-unit route);
  * every requested probe frequency as its **own copy of the DUT** with its
    own `pulse(...)` CLK and `pwl(...)` RESETB sources (DUT `k` is probed at
    `freqs[k]`);
  * the process x temperature matrix as `klt sim` corners.

A group's transient runs to the longest probe window. Each probe's trace is
cut back to its own planned window (linear interpolation at the cut) before
`classify_waveform` judges it, so a probe sees the same window it would in a
dedicated run. The DUT copies share only the ideal VDD source; they do not
interact. This is a documented methodology difference from one-netlist-per-
probe, recorded in the evidence record.

Unrequested DUT copies (stage 2 groups the union of the frequencies that any
cell of the group wants) are simulated and logged but their verdicts are
discarded: only a probe the two-stage algorithm asked for is recorded.

Failure policy
--------------

A submit/poll/collect failure is **never** answered by simulating locally. A
group whose every corner failed at job level (`batch_*` diagnostics, a version
refusal, a missing report) aborts the campaign with the exact diagnostic so no
record full of non-evidence is minted. A single corner whose ngspice run
errored or timed out is an INCONCLUSIVE probe, never an electrical FAIL.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import fmax as fmax_mod
from . import runner as runner_mod

#: Executor name accepted by `run_fmax.py --executor`.
BATCH_EXECUTOR = "batch"

#: `klt sim` exit codes that still carry a usable report (0 pass, 3 a declared
#: limit failed; this campaign declares no limits, but 3 is harmless).
_USABLE_EXIT = (0, 3)

NET_NAME = "body.spice"
REQUEST_NAME = "request.json"


class KltBatchError(RuntimeError):
    """The batch route could not produce evidence. Aborts the campaign; the
    message carries the diagnostic verbatim for the PR/issue."""


@dataclass
class Group:
    n: int
    supply_v: float
    freqs: dict = field(default_factory=dict)  # freq_hz -> DUT index
    processes: list = field(default_factory=list)
    temps: list = field(default_factory=list)
    needed: set = field(default_factory=set)  # (process, temp_c) pairs a request wants
    chunk: int = 0

    @property
    def key(self) -> str:
        return f"n{self.n}_{self.supply_v:.2f}v_c{self.chunk}"

    @property
    def excluded(self) -> list:
        """Process x temperature pairs of the axes' product that nobody asked for."""
        return [{"process": p, "temperature_c": t}
                for p in self.processes for t in self.temps if (p, t) not in self.needed]


# --------------------------------------------------------------------------- #
# netlist body
# --------------------------------------------------------------------------- #

_LIB_RE = re.compile(r"^\.lib\s+\S*sky130\.lib\.spice\s+\w+\s*$", re.IGNORECASE)
_END_RE = re.compile(r"^\.end\s*$", re.IGNORECASE)


def build_body(netlist_text: str, manifest: dict, spec, group: Group) -> tuple:
    """(body_text, {freq_hz: ProbePlan}) for one group.

    Starts from the unpatched testbench netlist, sets the supply with the
    manifest's `supply_pattern`, removes the testbench's single CLK/RESETB
    sources, the process `.lib` card (klt owns the process axis) and `.end`,
    and replaces the one DUT instance by one copy per probe frequency.
    """
    text = runner_mod._substitute_corner_and_supply(
        netlist_text, manifest, "tt", group.supply_v
    )
    lines = text.splitlines()
    dut_idx = [
        i for i, l in enumerate(lines)
        if l[:1] in "Xx" and {"CLK", "RESETB", "FBCLK"} <= set(l.split())
    ]
    if len(dut_idx) != 1:
        raise fmax_mod.FmaxError(
            f"expected exactly one DUT instance with CLK/RESETB/FBCLK, found {len(dut_idx)}"
        )
    dut_tokens = lines[dut_idx[0]].split()
    for net in ("CLK", "RESETB", "FBCLK"):
        if dut_tokens.count(net) != 1:
            raise fmax_mod.FmaxError(f"DUT instance must connect {net} exactly once")

    plans, block, saves = {}, [], []
    for freq, k in sorted(group.freqs.items(), key=lambda kv: kv[1]):
        plan = fmax_mod.stimulus_for(spec, group.n, freq, group.supply_v)
        plans[freq] = plan
        toks = [{"CLK": f"CLK_{k}", "RESETB": f"RESETB_{k}", "FBCLK": f"FBCLK_{k}"}.get(t, t)
                for t in dut_tokens]
        toks[0] = f"{dut_tokens[0]}_{k}"
        block += [
            " ".join(toks),
            f"VCLK_{k} CLK_{k} GND {plan.clk_card}",
            f"VRST_{k} RESETB_{k} GND {plan.reset_card}",
        ]
        saves.append(f"v(fbclk_{k})")

    out = []
    n_clk = n_rst = 0
    for i, l in enumerate(lines):
        if i == dut_idx[0]:
            out += block
        elif fmax_mod._CLK_SRC_RE.match(l):
            n_clk += 1
        elif fmax_mod._RST_SRC_RE.match(l):
            n_rst += 1
        elif _LIB_RE.match(l) or _END_RE.match(l.strip()):
            continue
        else:
            out.append(l)
    if n_clk != 1 or n_rst != 1:
        raise fmax_mod.FmaxError(
            f"expected one CLK pulse and one RESETB pwl source, found {n_clk} and {n_rst}"
        )
    out.append(".save " + " ".join(saves))
    return "\n".join(out) + "\n", plans


def build_request(spec, group: Group, stop_s: float, *, timeout_s: int,
                  max_workers: int) -> dict:
    """The `klt sim` request for one group (netlist referenced as NET_NAME)."""
    n_dut = len(group.freqs)
    req = {
        "netlist": NET_NAME,
        "engine": "ngspice",
        "backend": "batch",
        "models": {"pdk": "sky130A", "lib": "libs.tech/combined/sky130.lib.spice"},
        "corners": {
            "process": list(group.processes),
            "temperature_c": list(group.temps),
        },
        "analysis": {
            "kind": "tran",
            "args": f"{fmax_mod._si(spec.criterion.tran_step_s)} {stop_s * 1e9 * 1.000001:.7g}n",
        },
        "measurements": [
            {"name": f"fbclk_{k}_max", "spice": f".meas tran fbclk_{k}_max MAX v(fbclk_{k})",
             "unit": "V"}
            for k in range(n_dut)
        ],
        "options": {
            "timeout_s": timeout_s,
            "keep_artifacts": True,
            "waveforms": True,
            "max_workers": max_workers,
        },
        # The fleet runner image pins an older klt than a current client; the
        # request uses only options that older runner implements (corners,
        # tran, .meas, waveforms, artifacts), so skew is warned, not enforced.
        "batch": {"runner_version_check": "warn"},
    }
    if group.excluded:
        req["exclude"] = group.excluded
    return req


# --------------------------------------------------------------------------- #
# reduction (PDK-free, testable with a synthetic report)
# --------------------------------------------------------------------------- #


def clip_trace(times: list, values: list, stop_s: float) -> tuple:
    """Cut a trace to [0, stop_s], interpolating the value at stop_s."""
    if not times or times[-1] <= stop_s:
        return times, values
    t_out, v_out = [], []
    for i, t in enumerate(times):
        if t <= stop_s:
            t_out.append(t)
            v_out.append(values[i])
        else:
            t0, v0 = times[i - 1], values[i - 1]
            frac = (stop_s - t0) / (t - t0) if t > t0 else 0.0
            if t0 < stop_s:
                t_out.append(stop_s)
                v_out.append(v0 + frac * (values[i] - v0))
            break
    return t_out, v_out


_CAPACITY_MARKERS = ("BATCH_MAX_CONCURRENT_INSTANCES", "batch_no_capacity", "no capacity in any")


def is_capacity_refusal(text: str) -> bool:
    """True when a `klt sim` failure is the fleet refusing to launch for lack of
    capacity (the job never started), as opposed to a job that ran and failed."""
    return any(m in text for m in _CAPACITY_MARKERS)


def corner_dir_key(process: str, temp_c: float) -> str:
    return f"{process}_{temp_c:g}C"


def find_corner(report: dict, process: str, temp_c: float):
    for c in report.get("corners", []):
        if c.get("process") == process and abs(float(c.get("temperature_c")) - temp_c) < 1e-9:
            return c
    return None


def job_level_failure(report: dict) -> str | None:
    """A message when the report shows the job itself did not run (no usable
    simulator result for any corner), else None."""
    corners = report.get("corners") or []
    if not corners:
        err = (report.get("error") or {}).get("message", "no corners in report")
        return f"no usable report: {err}"
    job_codes = []
    for c in corners:
        for d in c.get("diagnostics") or []:
            if str(d.get("code", "")).startswith("batch_"):
                job_codes.append(d)
    if len(job_codes) >= len(corners):
        return "; ".join(sorted({f"{d['code']}: {d.get('message', '')}" for d in job_codes}))
    return None


def judge_corner_probe(corner, waveform_path, k: int, plan, spec) -> fmax_mod.ProbeVerdict:
    """Verdict for DUT `k` in one corner's waveform: simulator trouble ->
    INCONCLUSIVE; a completed trace -> the per-period criterion."""
    if corner is None:
        return fmax_mod.ProbeVerdict(fmax_mod.INCONCLUSIVE, "corner missing from the report")
    if corner.get("status") in ("error", "inconclusive", "not_checked"):
        diag = "; ".join(f"{d.get('code')}: {d.get('message', '')}"
                         for d in corner.get("diagnostics") or []) or corner.get("status")
        return fmax_mod.ProbeVerdict(fmax_mod.INCONCLUSIVE, f"simulator: {diag}")
    if not waveform_path or not Path(waveform_path).is_file():
        return fmax_mod.ProbeVerdict(fmax_mod.INCONCLUSIVE, "no waveform artifact for the corner")
    try:
        wave = json.loads(Path(waveform_path).read_text())
        names = [v["name"] for v in wave["variables"]]
        col = names.index(f"v(fbclk_{k})")
        times = [p[0] for p in wave["points"]]
        values = [p[col] for p in wave["points"]]
    except (OSError, ValueError, KeyError) as e:
        return fmax_mod.ProbeVerdict(fmax_mod.INCONCLUSIVE, f"unreadable waveform: {e}")
    times, values = clip_trace(times, values, plan.tran_stop_s)
    return fmax_mod.classify_waveform(
        times, values, plan,
        threshold_frac=spec.criterion.threshold_frac,
        hysteresis_frac=spec.criterion.hysteresis_frac,
    )


# --------------------------------------------------------------------------- #
# the backend
# --------------------------------------------------------------------------- #


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@dataclass
class ProbeResult:
    cell: object
    idx: int
    freq: float
    probe_id: str
    plan: object
    verdict: object
    netlist_sha256: str
    log_file: str
    log_sha256: str | None
    extra: dict


class KltBatchBackend:
    """Runs [(cell, grid_index, freq)] request lists through `klt sim`."""

    name = BATCH_EXECUTOR

    def __init__(self, *, spec, manifest, work_dir: Path, cache_dir: Path | None = None,
                 klt: str | None = None, runner=None, log=print, max_jobs: int = 2,
                 chunk_size: int = 4, capacity_retries: int = 30,
                 capacity_wait_s: float = 120.0, sleep=time.sleep):
        self.spec, self.manifest = spec, manifest
        self.work_dir = Path(work_dir)
        self.cache_dir = Path(cache_dir) if cache_dir else self.work_dir / "klt"
        self.klt = klt or os.environ.get("SKY130_PLL_KLT") or shutil.which("klt")
        self.runner = runner or subprocess.run  # injectable for tests
        self.log = log
        self.max_jobs = max(1, max_jobs)
        self.chunk_size = max(1, chunk_size)
        self.capacity_retries, self.capacity_wait_s, self.sleep = capacity_retries, capacity_wait_s, sleep
        self._lock = threading.Lock()
        self.jobs: list = []  # per-group provenance

    # -- preflight ------------------------------------------------------- #

    def preflight(self) -> None:
        if not self.klt:
            raise KltBatchError("`klt` is not on PATH (set SKY130_PLL_KLT to its path)")
        prov = os.environ.get("KLT_BATCH_PROVISION_SCRIPT")
        if not prov or not Path(prov).expanduser().is_file():
            raise KltBatchError(
                "KLT_BATCH_PROVISION_SCRIPT does not name an existing batch-fleet-provision.sh"
            )

    # -- grouping -------------------------------------------------------- #

    def _groups(self, requests) -> list:
        """Group requests into jobs: per (N, supply), the requested frequencies
        sorted ascending and cut into chunks of at most `chunk_size` DUT copies
        (a chunk's transient runs to its slowest probe's window, so neighbours
        in frequency waste the least simulated time)."""
        by_key: dict = {}
        for cell, _idx, freq in requests:
            by_key.setdefault((cell.modulus.n, cell.point.supply_v), set()).add(freq)
        groups = []
        for (n, supply), freqs in sorted(by_key.items()):
            ordered = sorted(freqs)
            for c, lo in enumerate(range(0, len(ordered), self.chunk_size)):
                g = Group(n=n, supply_v=supply, chunk=c)
                for k, f in enumerate(ordered[lo:lo + self.chunk_size]):
                    g.freqs[f] = k
                groups.append(g)
        index = {}
        for g in groups:
            for f in g.freqs:
                index[(g.n, g.supply_v, f)] = g
        for cell, _idx, freq in requests:
            g = index[(cell.modulus.n, cell.point.supply_v, freq)]
            g.needed.add((cell.point.corner, cell.point.temp_c))
            if cell.point.corner not in g.processes:
                g.processes.append(cell.point.corner)
            if cell.point.temp_c not in g.temps:
                g.temps.append(cell.point.temp_c)
        return groups, index

    # -- one group ------------------------------------------------------- #

    def _run_group(self, group: Group, netlist_text: str, stage_no: int) -> dict:
        gkey = f"s{stage_no}_{group.key}"
        gdir = self.cache_dir / gkey
        gdir.mkdir(parents=True, exist_ok=True)
        body, plans = build_body(netlist_text, self.manifest, self.spec, group)
        (gdir / NET_NAME).write_text(body)
        stop = max(p.tran_stop_s for p in plans.values())
        crit = self.spec.criterion
        n_dut = len(group.freqs)
        # Fleet ngspice measured ~1.3 s of wall per simulated ns per DUT copy;
        # budget 3x that (and never less than the manifest's per-probe timeout).
        timeout_s = min(max(crit.timeout_s, int(4.0 * stop * 1e9 * n_dut)), 8 * 3600)
        req = build_request(
            self.spec, group, stop, timeout_s=timeout_s,
            max_workers=max(1, len(group.needed)),
        )
        req["batch"]["poll_timeout_s"] = timeout_s + 3600
        (gdir / REQUEST_NAME).write_text(json.dumps(req, indent=1, sort_keys=True) + "\n")
        report_path = gdir / "report.json"
        report = None
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text())
                if job_level_failure(report):
                    report = None
            except ValueError:
                report = None
        if report is not None:
            self.log(f"  {gkey}: reusing collected report {report_path}")
        else:
            self.log(f"  {gkey}: submitting {n_dut} DUT(s) x {len(group.needed)} corner(s) "
                     f"to the batch fleet")
            cmd = [self.klt, "sim", str(gdir / REQUEST_NAME), "-o", str(gdir / "out"),
                   "--backend", "batch", "--format", "json"]
            attempt = 0
            while True:
                try:
                    proc = self.runner(cmd, capture_output=True, text=True,
                                       timeout=timeout_s + 3600 + 1800)
                except (OSError, subprocess.TimeoutExpired) as e:
                    raise KltBatchError(f"{gkey}: klt sim did not complete: {e}") from e
                # The fleet is shared and capped; a launch refused for capacity
                # ran nothing, so waiting and resubmitting the same job is safe
                # (never a local fallback). Any other failure aborts below.
                if (proc.returncode not in _USABLE_EXIT and attempt < self.capacity_retries
                        and is_capacity_refusal((proc.stdout or "") + (proc.stderr or ""))):
                    attempt += 1
                    self.log(f"  {gkey}: fleet at capacity; retry {attempt}/"
                             f"{self.capacity_retries} in {self.capacity_wait_s:g}s")
                    self.sleep(self.capacity_wait_s)
                    continue
                break
            (gdir / "stderr.log").write_text(proc.stderr or "")
            try:
                report = json.loads(proc.stdout)
            except ValueError:
                raise KltBatchError(
                    f"{gkey}: klt sim exit {proc.returncode} with no JSON report: "
                    f"{(proc.stderr or proc.stdout or '').strip()[-1500:]}"
                ) from None
            report_path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
            if proc.returncode not in _USABLE_EXIT and not report.get("corners"):
                raise KltBatchError(
                    f"{gkey}: klt sim exit {proc.returncode}: "
                    f"{json.dumps(report.get('error', report))[:1500]}"
                )
        failure = job_level_failure(report)
        if failure:
            raise KltBatchError(f"{gkey}: batch job produced no usable corner results: {failure}")
        remote = (report.get("environment") or {}).get("remote") or {}
        with self._lock:
            self.jobs.append({
                "group": gkey, "stage": stage_no, "modulus": group.n, "supply_v": group.supply_v,
                "dut_count": n_dut, "job_id": remote.get("job_id"),
                "instance_type": remote.get("instance_type"),
                "lifecycle": remote.get("lifecycle"),
                "runner_klt_version": remote.get("runner_klt_version"),
                "client_klt_version": remote.get("client_klt_version"),
                "engine_version": (report.get("environment") or {}).get("engine_version"),
                "netlist_sha256": _sha256_bytes(body.encode()),
                "dir": gkey,
            })
        return {"report": report, "plans": plans, "body": body, "gdir": gdir,
                "job_id": remote.get("job_id")}

    # -- public ---------------------------------------------------------- #

    def run(self, requests, *, netlists, stage_no: int, probe_id) -> list:
        """Run requests -> [ProbeResult]. `netlists` maps N -> unpatched text."""
        import concurrent.futures

        self.preflight()
        groups, index = self._groups(requests)
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_jobs) as pool:
            runs = list(pool.map(lambda g: self._run_group(g, netlists[g.n], stage_no), groups))
        run_of = {id(g): r for g, r in zip(groups, runs)}
        results = []
        for cell, idx, freq in requests:
            group = index[(cell.modulus.n, cell.point.supply_v, freq)]
            run = run_of[id(group)]
            report, plans, gdir = run["report"], run["plans"], run["gdir"]
            body_sha = _sha256_bytes(run["body"].encode())
            corner = find_corner(report, cell.point.corner, cell.point.temp_c)
            wave = None
            log_name, log_sha = "", None
            if corner is not None:
                arts = corner.get("artifacts") or {}
                wave = self._artifact(arts.get("waveform"), gdir)
                lg = self._artifact(arts.get("log"), gdir)
                if lg and lg.is_file():
                    log_name = f"{gdir.name}_{corner_dir_key(cell.point.corner, cell.point.temp_c)}.log"
                    shutil.copy2(lg, self.work_dir / log_name)
                    log_sha = hashlib.sha256(lg.read_bytes()).hexdigest()
            plan = plans[freq]
            verdict = judge_corner_probe(corner, wave, group.freqs[freq], plan, self.spec)
            results.append(ProbeResult(
                cell=cell, idx=idx, freq=freq, probe_id=probe_id(cell, freq), plan=plan,
                verdict=verdict, netlist_sha256=body_sha, log_file=log_name,
                log_sha256=log_sha,
                extra={"batch_job_id": run["job_id"], "batch_group": gdir.name,
                       "dut_index": group.freqs[freq]},
            ))
        return results

    @staticmethod
    def _artifact(path, gdir: Path):
        if not path:
            return None
        p = Path(path)
        if p.is_absolute() and p.is_file():
            return p
        for base in (Path.cwd(), gdir, gdir / "out"):
            cand = base / p
            if cand.is_file():
                return cand
        return p if p.is_file() else None

    def provenance(self) -> dict:
        return {"executor": BATCH_EXECUTOR, "jobs": list(self.jobs)}

    def export_jobs(self, dest: Path) -> None:
        """Copy each group's request, body, report and stderr next to the record."""
        for j in self.jobs:
            src = self.cache_dir / j["dir"]
            dst = dest / j["dir"]
            dst.mkdir(parents=True, exist_ok=True)
            for name in (REQUEST_NAME, NET_NAME, "report.json", "stderr.log"):
                if (src / name).is_file():
                    shutil.copy2(src / name, dst / name)


def execution_note(prov: dict) -> str:
    jobs = prov.get("jobs") or []
    types = sorted({j.get("instance_type") or "?" for j in jobs})
    runners = sorted({str(j.get("runner_klt_version")) for j in jobs})
    clients = sorted({str(j.get("client_klt_version")) for j in jobs})
    engines = sorted({str(j.get("engine_version")) for j in jobs})
    return (
        f"executor: `batch` (`klt sim --backend batch`, S3 job contract), {len(jobs)} job(s), "
        f"instance_type: {', '.join('`%s`' % t for t in types)}, ngspice {', '.join(engines)}, "
        f"runner klt {', '.join(runners)} / client klt {', '.join(clients)}. Job ids and "
        "per-job requests/netlists are under this record's corners directory (`jobs/`). "
        "Each group runs one DUT copy per probe frequency in a single deck and each probe's "
        "trace is cut to its own planned window before the unchanged per-period criterion "
        "judges it; the process model library is the one baked into the fleet image "
        "(not the local pinned install), so the model identity is the image's."
    )
