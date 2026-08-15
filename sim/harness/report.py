"""Render the append-only sim/<slug>/records/<record-id>.md evidence record.

Schema follows sim/README.md (adapted from 2AMLogic/gf180-pll's sim/README.md,
itself adapted from 2AMLogic/gf180-bandgap's convention).
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .corners import PvtPoint
from .pdk import ResolvedPdk

# scripts/git_status.py lives at the repo root (shared with
# layout/bin/render-record.py -- sim/ and layout/ are otherwise independent
# trees per CLAUDE.md's harness-bootstrap convention), so it isn't reachable
# via the package-relative imports above.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.git_status import is_dirty, porcelain_paths  # noqa: E402


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def git_info(repo_root: Path, ignore_prefixes: tuple = ()) -> dict:
    """Resolve HEAD and whether the tree was dirty when the run started."""

    def run(*args: str) -> str:
        out = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()

    sha = run("rev-parse", "HEAD")
    # --untracked-files=all is load-bearing: git's default collapses a wholly
    # untracked tree to its parent directory ("?? sim/pdk-smoke/corners/"),
    # which no per-record prefix can match, so every record would read dirty
    # again.
    status = run("status", "--porcelain", "--untracked-files=all")
    return {"sha": sha, "dirty": is_dirty(status, ignore_prefixes)}


def make_record_id(repo_root: Path) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sha = git_info(repo_root)["sha"][:7]
    return f"{ts}-{sha}"


def render(
    *,
    record_id: str,
    slug: str,
    claim: str,
    pdk: ResolvedPdk,
    tool_versions: dict,
    repo_root: Path,
    netlist_snapshot: Path,
    points: list[PvtPoint],
    results,  # list[PointResult]
    subset_reason: str | None,
    supersedes: str | None,
) -> str:
    # Only this run's own new artifacts are excluded from the dirty check --
    # an uncommitted edit to the testbench itself still marks the record
    # dirty, because that genuinely affects what the evidence means.
    git = git_info(
        repo_root,
        ignore_prefixes=(
            f"sim/{slug}/corners/{record_id}/",
            f"sim/{slug}/records/{record_id}.md",
            f"sim/{slug}/netlist-snapshots/{record_id}.spice",
        ),
    )
    netlist_sha = sha256_file(netlist_snapshot)

    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(f"- **Claim**: {claim}")
    a(
        f"- **Netlist provenance**: schematic (`sim/{slug}/testbench/`), "
        f"frozen at `sim/{slug}/netlist-snapshots/{record_id}.spice`, "
        f"SHA-256 `{netlist_sha}`"
    )
    a("- **Environment provenance**:")
    a(f"  - PDK: volare `{pdk.variant}`, open_pdks `{pdk.resolved_commit or 'unknown'}`"
      + (f" (**MISMATCH** vs. pinned `{pdk.pinned_commit}`)" if pdk.commit_mismatch else ""))
    a(f"  - Model library: `{pdk.ngspice_lib}`")
    a(f"  - Simulator: {tool_versions.get('ngspice') or 'unknown'}; "
      f"schematic capture: {tool_versions.get('xschem') or 'unknown'}")
    a(f"  - Repo commit: `{git['sha']}`" + (" (dirty)" if git["dirty"] else ""))
    a(f"  - Host: {platform.system()} {platform.machine()}")
    a("- **Corner matrix run**:")
    corners_used = sorted({p.corner for p in points})
    temps_used = sorted({p.temp_c for p in points})
    supplies_used = sorted({p.supply_v for p in points})
    a(f"  - Process corners: {', '.join(corners_used)}")
    a(f"  - Temperatures (deg C): {', '.join(str(t) for t in temps_used)}")
    a(f"  - Supplies (V): {', '.join(f'{v:.2f}' for v in supplies_used)}")
    a(f"  - Total points: {len(points)}")
    if subset_reason:
        a(f"  - **Subset of the manifest's default grid**: {subset_reason}")
    a("- **Methodology / criteria / limitations**:")
    a(
        "  - Per-point criterion: ngspice exits 0, prints its analysis-"
        "completion marker, and emits no `Error:` line. This is a **harness "
        "plumbing check** (does xschem+ngspice+sky130 run this DUT to "
        "completion at this PVT point?), not a PLL performance measurement -- "
        "there is no PLL netlist yet (issue #2 is unblocked of spec "
        "ratification per CLAUDE.md)."
    )
    a("  - Analysis: DC operating point (`.op`).")
    a("- **Result**:")
    a("")
    a("  | Corner | Temp (C) | Supply (V) | Verdict | Detail |")
    a("  |---|---|---|---|---|")
    for r in results:
        p = r.point
        verdict = "PASS" if r.passed else "FAIL"
        a(f"  | {p.corner} | {p.temp_c:g} | {p.supply_v:.2f} | {verdict} | {r.reason} |")
    a("")
    overall = "PASS" if not failed else "FAIL"
    a(f"  - **Overall: {overall}** ({len(passed)}/{len(results)} points passed)")
    a("- **Links**:")
    a(f"  - Testbench: `sim/{slug}/testbench/`")
    a(f"  - Netlist snapshot: `sim/{slug}/netlist-snapshots/{record_id}.spice`")
    a(f"  - Raw logs: `sim/{slug}/corners/{record_id}/`")
    a(f"- **Timestamp / author**: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}, agent-builder")
    a(f"- **Supersedes**: {supersedes or '(none -- first record for this claim)'}")
    a("")
    return "\n".join(lines)
