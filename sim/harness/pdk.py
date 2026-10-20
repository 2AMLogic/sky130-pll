"""Resolve the sky130 PDK install this harness runs against.

Resolution order (mirrors 2AMLogic/sky130-bandgap's sim/bin/pdk-env.sh
convention, source commit a8c4147a6cdf7b7fad467417cbc7b83178ccc9c6):

    PDK_ROOT env  -> `ciel path`          -> sim/pdk.json's default_pdk_root (~/.ciel)
                                          -> legacy ~/.volare (only if ~/.ciel has
                                             no variant; flagged as a mismatch unless
                                             its revision equals the pin)
    PDK env       -> sim/pdk.json's variant

The resolved install's open_pdks revision (the variant's `SOURCES` file, else
the `versions/<hash>` path component) is checked against sim/pdk.json's pinned
open_pdks commit; a mismatch is reported (not silently ignored) so a record
can note it, and the corner runner refuses it without --allow-pdk-mismatch.
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


# Retired PDK manager's default store. Historical: searched last, and only so a
# stray tree is *visibly* flagged as a revision mismatch instead of going unseen.
_LEGACY_PDK_ROOT = Path("~/.volare")  # historical (volare retired); see module docstring


def _ciel_path() -> Path | None:
    ciel = shutil.which("ciel")
    if ciel is None:
        return None
    try:
        out = subprocess.run(
            [ciel, "path"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    candidate = out.stdout.strip()
    return Path(candidate).expanduser() if candidate else None


def _commit_from_sources(variant_dir: Path) -> str | None:
    """Read the open_pdks revision from the variant's `SOURCES` file.

    open_pdks writes `<variant>/SOURCES` with an `open_pdks <hash>` line; this
    is the authoritative statement of what the tree was built from.
    """
    try:
        text = (variant_dir / "SOURCES").read_text()
    except OSError:
        return None
    m = re.search(r"^\s*open_pdks\s+([0-9a-fA-F]{7,40})\b", text, re.MULTILINE)
    return m.group(1).lower() if m else None


def _commit_from_variant_dir(variant_dir: Path) -> str | None:
    """Extract the open_pdks commit hash from a managed-store symlink target.

    The PDK manager lays out `<root>/<store>/<family>/versions/<commit>/<variant>`
    (ciel: `<store>` is `ciel`), and `<root>/<variant>` is a symlink into it.
    Parse the real path rather than trusting the symlink name. This is the
    fallback for `_commit_from_sources`.
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
    resolved_variant = pdk_env or variant

    if pdk_root_env:
        pdk_root = Path(pdk_root_env).expanduser()
    else:
        pdk_root = _ciel_path() or Path(pdk_json["default_pdk_root"]).expanduser()
        legacy_root = _LEGACY_PDK_ROOT.expanduser()
        if not (pdk_root / resolved_variant).is_dir() and (legacy_root / resolved_variant).is_dir():
            pdk_root = legacy_root  # surfaces as a mismatch below unless it is the pin

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

    resolved_commit = _commit_from_sources(variant_dir) or _commit_from_variant_dir(variant_dir)
    mismatch = resolved_commit is not None and resolved_commit.lower() != pinned_commit.lower()

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
