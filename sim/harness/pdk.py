"""Resolve the sky130 PDK install this harness runs against.

Resolution order (mirrors 2AMLogic/sky130-bandgap's sim/bin/pdk-env.sh
convention, source commit a8c4147a6cdf7b7fad467417cbc7b83178ccc9c6):

    PDK_ROOT env  -> `volare path`        -> sim/pdk.json's default_pdk_root
    PDK env       -> sim/pdk.json's variant

The resolved install is checked against sim/pdk.json's pinned open_pdks
commit; a mismatch is reported (not silently ignored) so a record can note it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class PdkNotFoundError(RuntimeError):
    """Raised when the sky130 PDK cannot be resolved at all."""


@dataclass(frozen=True)
class ResolvedPdk:
    pdk_root: Path
    variant: str
    variant_dir: Path
    ngspice_lib: Path
    process_corners: tuple
    pinned_commit: str
    resolved_commit: str | None
    commit_mismatch: bool

    def as_env(self) -> dict:
        return {"PDK_ROOT": str(self.pdk_root), "PDK": self.variant}


def _load_pdk_json(repo_root: Path) -> dict:
    with (repo_root / "sim" / "pdk.json").open() as f:
        return json.load(f)


def _volare_path() -> Path | None:
    volare = shutil.which("volare")
    if volare is None:
        return None
    try:
        out = subprocess.run(
            [volare, "path"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    candidate = out.stdout.strip()
    return Path(candidate).expanduser() if candidate else None


def _commit_from_variant_dir(variant_dir: Path) -> str | None:
    """Extract the open_pdks commit hash from a volare-managed symlink target.

    volare lays out `<root>/volare/<family>/versions/<commit>/<variant>`, and
    `<root>/<variant>` is a symlink into it. Parse the real path rather than
    trusting the symlink name.
    """
    try:
        real = variant_dir.resolve()
    except OSError:
        return None
    m = re.search(r"/versions/([0-9a-fA-F]{7,40})/", str(real))
    return m.group(1) if m else None


def resolve(repo_root: Path) -> ResolvedPdk:
    pdk_json = _load_pdk_json(repo_root)
    variant = pdk_json["variant"]
    pinned_commit = pdk_json["open_pdks_commit"]

    pdk_root_env = os.environ.get("PDK_ROOT")
    pdk_env = os.environ.get("PDK")

    if pdk_root_env:
        pdk_root = Path(pdk_root_env).expanduser()
    else:
        pdk_root = _volare_path() or Path(pdk_json["default_pdk_root"]).expanduser()

    resolved_variant = pdk_env or variant
    variant_dir = pdk_root / resolved_variant

    if not variant_dir.is_dir():
        raise PdkNotFoundError(
            f"no sky130 PDK found at {variant_dir} -- "
            f"install it: {pdk_json['install_command']} "
            "(see docs/environment-setup.md)"
        )

    ngspice_lib = variant_dir / pdk_json["ngspice_lib"]
    xschem_rc = variant_dir / pdk_json["xschem_pdk_rc"]
    if not ngspice_lib.is_file():
        raise PdkNotFoundError(f"PDK found at {variant_dir} but no ngspice lib at {ngspice_lib}")
    if not xschem_rc.is_file():
        raise PdkNotFoundError(f"PDK found at {variant_dir} but no xschem rc at {xschem_rc}")

    resolved_commit = _commit_from_variant_dir(variant_dir)
    mismatch = resolved_commit is not None and resolved_commit != pinned_commit

    return ResolvedPdk(
        pdk_root=pdk_root,
        variant=resolved_variant,
        variant_dir=variant_dir,
        ngspice_lib=ngspice_lib,
        process_corners=tuple(pdk_json["process_corners"]),
        pinned_commit=pinned_commit,
        resolved_commit=resolved_commit,
        commit_mismatch=mismatch,
    )


def tool_versions() -> dict:
    """Best-effort tool version strings for the evidence record."""
    versions = {}
    for tool, args in (
        ("ngspice", ["ngspice", "--version"]),
        ("xschem", ["xschem", "-v"]),
    ):
        exe = shutil.which(tool)
        if exe is None:
            versions[tool] = None
            continue
        try:
            out = subprocess.run([exe, *args[1:]], capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            versions[tool] = None
            continue
        lines = [ln.strip() for ln in (out.stdout or out.stderr).splitlines()]
        # Skip decorative `******` banner lines; take the first line that
        # actually names the tool/version (ngspice's banner opens with one).
        versions[tool] = next((ln for ln in lines if ln and not set(ln) <= {"*"}), None)
    return versions
