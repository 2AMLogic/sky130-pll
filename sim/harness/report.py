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
from .montecarlo import McTrial
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


def render_mc(
    *,
    record_id: str,
    slug: str,
    claim: str,
    pdk: ResolvedPdk,
    tool_versions: dict,
    repo_root: Path,
    netlist_snapshot: Path,
    trials: list[McTrial],
    results,  # list[McTrialResult]
    subset_reason: str | None,
    supersedes: str | None,
) -> str:
    """Render a Monte Carlo evidence record. Same append-only schema and
    directory conventions as `render` (PVT) -- see sim/README.md -- adapted
    for a statistical trial matrix instead of a PVT point matrix: trials
    share one (corner, temp, supply) point (see `montecarlo.McTrial`) and
    vary only by RNG seed, so the record states that point once instead of
    per row, and states the MC_MM_SWITCH/MC_PR_SWITCH sampling configuration
    that applied to every trial.
    """
    # Per-run artifacts for an MC record live under the same sim/<slug>/
    # corners/<record-id>/ tree a PVT record uses (sim/README.md's
    # <corner-id> convention just has two forms depending on run mode) -- so
    # the same ignore-prefixes shape applies here.
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

    first = trials[0]

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
    a("- **Statistical sampling point**:")
    a(f"  - Base process corner: {first.corner} (netlisted as `{first.lib_corner}`)")
    a(f"  - Temperature (deg C): {first.temp_c:g}")
    a(f"  - Supply (V): {first.supply_v:.2f}")
    a(f"  - Mismatch sampling (`MC_MM_SWITCH`): {'on' if first.mismatch else 'off'}")
    a(f"  - Process sampling (`MC_PR_SWITCH`): {'on' if first.process else 'off'}")
    a(f"  - Trials: {len(trials)} (seeds {trials[0].seed}..{trials[-1].seed}, "
      f"one ngspice `.options seed=<N>` per trial)")
    if subset_reason:
        a(f"  - **Subset/override of the manifest's default `monte_carlo` config**: {subset_reason}")
    a("- **Methodology / criteria / limitations**:")
    a(
        "  - Sampling mechanism: sky130's own `MC_MM_SWITCH` (within-die "
        "mismatch, via the corner's `*_mm` `.lib` section) and `MC_PR_SWITCH` "
        "(die-to-die process variation, every corner section) parameters, "
        "which gate `agauss()`/`gauss()` calls already present in the shipped "
        "device models. Each trial's draw is seeded by a distinct ngspice "
        "`.options seed=<N>` card -- reproducible per trial, independent "
        "across trials. See `sim/harness/montecarlo.py`'s module docstring."
    )
    a(
        "  - Per-trial criterion: ngspice exits 0, prints its analysis-"
        "completion marker, and emits no `Error:` line. This is a **harness "
        "plumbing check** (does the sky130 statistical-sampling mechanism "
        "run this DUT to completion, seed by seed?), not a statistical-spec "
        "measurement -- spec/target-spec.md's statistical-shaped rows (period "
        "jitter, reference spur, supply sensitivity) are DRAFT/unratified and "
        "there is no PLL netlist yet (issue #20 stands up this capability "
        "ahead of both)."
    )
    a("  - Analysis: DC operating point (`.op`).")
    a("- **Result**:")
    a("")
    a("  | Trial | Seed | Verdict | Detail |")
    a("  |---|---|---|---|")
    for r in results:
        t = r.trial
        verdict = "PASS" if r.passed else "FAIL"
        a(f"  | {t.trial} | {t.seed} | {verdict} | {r.reason} |")
    a("")
    overall = "PASS" if not failed else "FAIL"
    a(f"  - **Overall: {overall}** ({len(passed)}/{len(results)} trials passed)")
    a("- **Links**:")
    a(f"  - Testbench: `sim/{slug}/testbench/`")
    a(f"  - Netlist snapshot: `sim/{slug}/netlist-snapshots/{record_id}.spice`")
    a(f"  - Raw logs: `sim/{slug}/corners/{record_id}/`")
    a(f"- **Timestamp / author**: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}, agent-builder")
    a(f"- **Supersedes**: {supersedes or '(none -- first record for this claim)'}")
    a("")
    return "\n".join(lines)
