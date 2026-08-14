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
from .pdk import ResolvedPdk

COMPLETION_MARKER = "Total analysis time"
ERROR_LINE_RE = re.compile(r"^\s*[Ee]rror[: ]")


class NetlistError(RuntimeError):
    pass


@dataclass(frozen=True)
class PointResult:
    point: PvtPoint
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


def patch_netlist(netlist_text: str, manifest: dict, point: PvtPoint) -> str:
    corner_re = re.compile(manifest["corner_pattern"])
    supply_re = re.compile(manifest["supply_pattern"])

    if not corner_re.search(netlist_text):
        raise NetlistError(f"corner_pattern {manifest['corner_pattern']!r} matched nothing")
    if not supply_re.search(netlist_text):
        raise NetlistError(f"supply_pattern {manifest['supply_pattern']!r} matched nothing")

    text = corner_re.sub(lambda m: f"{m.group(1)}{point.corner}", netlist_text)
    text = supply_re.sub(lambda m: f"{m.group(1)}{point.supply_v:g}", text)

    # Anchor on a line that is exactly `.end` (case-insensitive, optional
    # trailing whitespace) -- a naive substring match on ".end" also hits
    # "**.ends" (the subcircuit terminator xschem emits earlier in the file),
    # which corrupts the netlist into an unbalanced .subckt/.ends pair.
    end_re = re.compile(r"^(\s*\.end\s*)$", re.IGNORECASE | re.MULTILINE)
    if not end_re.search(text):
        raise NetlistError("patched netlist has no standalone .end card to anchor .temp before")
    text = end_re.sub(lambda m: f".temp {point.temp_c:g}\n{m.group(1)}", text, count=1)
    return text


def run_point(
    pdk: ResolvedPdk,
    spiceinit: Path,
    manifest: dict,
    netlist_text: str,
    point: PvtPoint,
    work_dir: Path,
) -> PointResult:
    work_dir.mkdir(parents=True, exist_ok=True)
    patched = patch_netlist(netlist_text, manifest, point)

    spice_path = work_dir / f"{point.corner_id}.spice"
    log_path = work_dir / f"{point.corner_id}.log"
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

    return PointResult(point=point, passed=passed, reason=reason, log_path=log_path, spice_path=spice_path)
