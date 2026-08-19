"""Netlist a testbench schematic once, patch it per PVT point, and run ngspice.

Netlisting goes through xschem exactly once per run (the DUT does not change
across corner points); each point's process/supply/temperature is applied by
regex-patching the netlisted text per the manifest's own `corner_pattern` /
`supply_pattern`, plus a `.temp <T>` line inserted before `.end`. This keeps
the harness generic (it does not need to understand the DUT's topology) while
still driving real per-corner ngspice runs.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .corners import PvtPoint
from .montecarlo import McTrial
from .pdk import ResolvedPdk

COMPLETION_MARKER = "Total analysis time"
ERROR_LINE_RE = re.compile(r"^\s*[Ee]rror[: ]")
# Anchor on a line that is exactly `.end` (case-insensitive, optional
# trailing whitespace) -- a naive substring match on ".end" also hits
# "**.ends" (the subckt terminator xschem emits earlier in the file), which
# corrupts the netlist into an unbalanced .subckt/.ends pair. Shared by both
# the PVT and Monte Carlo patchers below.
_END_CARD_RE = re.compile(r"^(\s*\.end\s*)$", re.IGNORECASE | re.MULTILINE)


class NetlistError(RuntimeError):
    pass


@dataclass(frozen=True)
class PointResult:
    point: PvtPoint
    passed: bool
    reason: str
    log_path: Path
    spice_path: Path


@dataclass(frozen=True)
class McTrialResult:
    trial: McTrial
    passed: bool
    reason: str
    log_path: Path
    spice_path: Path


def netlist_schematic(
    pdk: ResolvedPdk, xschemrc: Path, schematic: Path, out_dir: Path, repo_root: Path
) -> str:
    """Netlist `schematic` with xschem, headless, against the resolved PDK.

    Returns the netlisted text. Raises NetlistError on any nonzero exit or
    missing output file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = schematic.stem
    cmd = [
        "xschem",
        "-x",
        "-n",
        "-s",
        "-q",
        "--rcfile",
        str(xschemrc),
        "-o",
        str(out_dir),
        str(schematic),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=_env_with_pdk(pdk),
        timeout=120,
    )
    netlist_path = out_dir / f"{stem}.spice"
    if proc.returncode != 0 or not netlist_path.is_file():
        raise NetlistError(
            f"xschem netlisting failed (exit {proc.returncode}):\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return netlist_path.read_text()


def _env_with_pdk(pdk: ResolvedPdk) -> dict:
    import os

    env = dict(os.environ)
    env.update(pdk.as_env())
    return env


def _substitute_corner_and_supply(netlist_text: str, manifest: dict, corner_label: str, supply_v: float) -> str:
    """Apply the manifest's `corner_pattern`/`supply_pattern` substitutions.

    Shared by `patch_netlist` (PVT) and `patch_netlist_mc` (Monte Carlo),
    which differ only in which corner label and supply value they select.
    """
    corner_re = re.compile(manifest["corner_pattern"])
    supply_re = re.compile(manifest["supply_pattern"])

    if not corner_re.search(netlist_text):
        raise NetlistError(f"corner_pattern {manifest['corner_pattern']!r} matched nothing")
    if not supply_re.search(netlist_text):
        raise NetlistError(f"supply_pattern {manifest['supply_pattern']!r} matched nothing")

    text = corner_re.sub(lambda m: f"{m.group(1)}{corner_label}", netlist_text)
    text = supply_re.sub(lambda m: f"{m.group(1)}{supply_v:g}", text)
    return text


def patch_netlist(netlist_text: str, manifest: dict, point: PvtPoint) -> str:
    text = _substitute_corner_and_supply(netlist_text, manifest, point.corner, point.supply_v)

    if not _END_CARD_RE.search(text):
        raise NetlistError("patched netlist has no standalone .end card to anchor .temp before")
    text = _END_CARD_RE.sub(lambda m: f".temp {point.temp_c:g}\n{m.group(1)}", text, count=1)
    return text


def patch_netlist_mc(netlist_text: str, manifest: dict, trial: McTrial) -> str:
    """Patch a netlisted DUT for one sky130 Monte Carlo trial.

    Reuses the manifest's `corner_pattern`/`supply_pattern` (same as
    `patch_netlist`) to select `trial.lib_corner` (the corner's `*_mm` `.lib`
    section when mismatch sampling is enabled -- see `montecarlo.McTrial`)
    and pin the supply, then injects the sky130 `MC_MM_SWITCH`/`MC_PR_SWITCH`
    `.param` overrides plus a per-trial `.options seed=<N>` card ahead of the
    netlist's `.end`. This is the same statistical-sampling mechanism the
    sky130 models wire up themselves (`agauss()`/`gauss()` calls gated on
    those two params, seeded via ngspice's global RNG seed option) -- see
    `sim/harness/README.md`'s Monte Carlo section and `montecarlo.py`'s
    module docstring for how this was verified against this repo's sky130
    install.
    """
    text = _substitute_corner_and_supply(netlist_text, manifest, trial.lib_corner, trial.supply_v)

    if not _END_CARD_RE.search(text):
        raise NetlistError("patched netlist has no standalone .end card to anchor MC cards before")
    mm_switch = 1 if trial.mismatch else 0
    pr_switch = 1 if trial.process else 0
    injected = (
        f".param MC_MM_SWITCH={mm_switch}\n"
        f".param MC_PR_SWITCH={pr_switch}\n"
        f".options seed={trial.seed}\n"
        f".temp {trial.temp_c:g}\n"
    )
    text = _END_CARD_RE.sub(lambda m: f"{injected}{m.group(1)}", text, count=1)
    return text


def _run_ngspice_and_judge(
    pdk: ResolvedPdk, spiceinit: Path, patched: str, corner_id: str, work_dir: Path
) -> tuple[bool, str, Path, Path]:
    """Write `patched` + a per-run `.spiceinit`, execute ngspice batch mode,
    and apply the shared plumbing pass/fail criterion. Returns (passed,
    reason, log_path, spice_path); shared by `run_point` and `run_mc_trial`
    since the run-and-judge step is identical for a PVT point and an MC
    trial -- only how the netlist got patched (`patch_netlist` vs.
    `patch_netlist_mc`) differs.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    spice_path = work_dir / f"{corner_id}.spice"
    log_path = work_dir / f"{corner_id}.log"
    spice_path.write_text(patched)

    spiceinit_dst = work_dir / ".spiceinit"
    spiceinit_dst.write_text(spiceinit.read_text())

    proc = subprocess.run(
        ["ngspice", "-b", spice_path.name],
        capture_output=True,
        text=True,
        cwd=work_dir,
        env=_env_with_pdk(pdk),
        timeout=300,
    )
    log_text = proc.stdout + proc.stderr
    log_path.write_text(log_text)

    error_lines = [ln for ln in log_text.splitlines() if ERROR_LINE_RE.match(ln)]
    completed = COMPLETION_MARKER in log_text
    passed = proc.returncode == 0 and completed and not error_lines

    if not passed:
        if error_lines:
            reason = "ngspice reported: " + "; ".join(error_lines[:3])
        elif not completed:
            reason = f"ngspice did not print {COMPLETION_MARKER!r} (run did not finish)"
        else:
            reason = f"ngspice exited {proc.returncode}"
    else:
        reason = "ok"

    return passed, reason, log_path, spice_path


def run_point(
    pdk: ResolvedPdk,
    spiceinit: Path,
    manifest: dict,
    netlist_text: str,
    point: PvtPoint,
    work_dir: Path,
) -> PointResult:
    patched = patch_netlist(netlist_text, manifest, point)
    passed, reason, log_path, spice_path = _run_ngspice_and_judge(
        pdk, spiceinit, patched, point.corner_id, work_dir
    )
    return PointResult(point=point, passed=passed, reason=reason, log_path=log_path, spice_path=spice_path)


def run_mc_trial(
    pdk: ResolvedPdk,
    spiceinit: Path,
    manifest: dict,
    netlist_text: str,
    trial: McTrial,
    work_dir: Path,
) -> McTrialResult:
    """Same run-and-judge shape as `run_point`, for one Monte Carlo trial.

    The pass/fail criterion is the same harness-plumbing check used
    everywhere else in this package (ngspice exits 0, prints its
    analysis-completion marker, emits no `Error:` line) -- it proves the
    sampling mechanism runs to completion, not that any particular circuit
    quantity landed inside a spec limit. See `sim/harness/README.md`.
    """
    patched = patch_netlist_mc(netlist_text, manifest, trial)
    passed, reason, log_path, spice_path = _run_ngspice_and_judge(
        pdk, spiceinit, patched, trial.corner_id, work_dir
    )
    return McTrialResult(trial=trial, passed=passed, reason=reason, log_path=log_path, spice_path=spice_path)
