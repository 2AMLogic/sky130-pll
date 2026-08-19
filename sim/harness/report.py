"""Render the append-only sim/<slug>/records/<record-id>.md evidence record.

Schema follows sim/README.md (adapted from 2AMLogic/gf180-pll's sim/README.md,
itself adapted from 2AMLogic/gf180-bandgap's convention).
"""

from __future__ import annotations

import hashlib
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import measure as measure_mod
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

from scripts.git_status import is_dirty, run_git  # noqa: E402


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def git_info(repo_root: Path, ignore_prefixes: tuple = ()) -> dict:
    """Resolve HEAD and whether the tree was dirty when the run started."""

    sha = run_git(repo_root, "rev-parse", "HEAD")
    # --untracked-files=all is load-bearing: git's default collapses a wholly
    # untracked tree to its parent directory ("?? sim/pdk-smoke/corners/"),
    # which no per-record prefix can match, so every record would read dirty
    # again.
    status = run_git(repo_root, "status", "--porcelain", "--untracked-files=all")
    return {"sha": sha, "dirty": is_dirty(status, ignore_prefixes)}


def make_record_id(repo_root: Path) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sha = git_info(repo_root)["sha"][:7]
    return f"{ts}-{sha}"


def _render_header(
    *,
    lines_append,
    record_id: str,
    slug: str,
    claim: str,
    pdk: ResolvedPdk,
    tool_versions: dict,
    git: dict,
    netlist_sha: str,
) -> None:
    """Append the `# Record` through `Host` lines shared by `render` (PVT)
    and `render_mc` (Monte Carlo) -- same schema, see sim/README.md.
    """
    a = lines_append
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


def _render_footer(
    *,
    lines_append,
    slug: str,
    record_id: str,
    supersedes: str | None,
) -> None:
    """Append the `Links` / `Timestamp / author` / `Supersedes` lines shared
    by `render` (PVT) and `render_mc` (Monte Carlo) -- same schema, see
    sim/README.md.
    """
    a = lines_append
    a("- **Links**:")
    a(f"  - Testbench: `sim/{slug}/testbench/`")
    a(f"  - Netlist snapshot: `sim/{slug}/netlist-snapshots/{record_id}.spice`")
    a(f"  - Raw logs: `sim/{slug}/corners/{record_id}/`")
    a(f"- **Timestamp / author**: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}, agent-builder")
    a(f"- **Supersedes**: {supersedes or '(none -- first record for this claim)'}")


def _render_measurement_criteria(a, spec, methodology_note: str) -> None:
    """The "Methodology / criteria / limitations" bullets for a record whose
    manifest carries a `measure` block.

    A measurement record's per-point criterion is deliberately *stricter* than
    the plumbing one the rest of this package uses: a point that ngspice ran
    to completion still FAILS if the DUT did not do what the manifest says it
    must. Both halves are stated so a reader can tell which one a FAIL came
    from.
    """
    a(
        "  - Per-point criterion, part 1 (plumbing): ngspice exits 0, prints "
        f"the harness's analysis-completion marker (`{measure_mod.COMPLETION_MARKER}`, "
        "echoed by the injected `.control` block -- ngspice does not print its "
        "own \"Total analysis time\" banner for a control-driven analysis), and "
        "emits no `Error:` line."
    )
    if spec.lock is not None:
        a(
            "  - Per-point criterion, part 2 (measurement): the loop **locks** "
            f"within the transient window. Lock criterion: {spec.lock.summary}. "
            "Time-to-lock is the earliest instant satisfying it. A point that "
            "never satisfies it is reported as **no lock** -- its final-window "
            "mean frequency is still shown, explicitly labelled as *not* a "
            "locked output frequency, so it can never be misread as one."
            + ("" if spec.require_lock else " (Reported, but not gated on, for this manifest.)")
        )
    else:
        a(
            "  - Per-point criterion, part 2 (measurement): the measured node "
            f"`v({spec.node})` oscillates -- at least {spec.min_edges} rising "
            f"crossings of {spec.threshold_frac:g}*VDD after "
            f"{measure_mod.format_s(spec.settle_from_s)} of settling. A swept "
            "point that does not is reported as **no oscillation**, with no "
            "frequency attributed to it."
            + (
                ""
                if spec.require_oscillation
                else (
                    " A characterization sweep deliberately runs past the edges "
                    "of the tuning range, so an individual dead swept value is "
                    "recorded as data rather than gating the point; this "
                    f"manifest instead requires at least {spec.min_oscillating_points} "
                    "of the swept values to oscillate."
                )
            )
        )
    a(
        "  - Measurement method: the harness injects the analysis itself (an "
        "ngspice `.control` block built by `sim/harness/measure.py`), "
        f"`linearize`s `v({spec.node})` onto the transient's own "
        f"{spec.tran_step} grid and `wrdata`-dumps it; the reducer then "
        "extracts hysteresis-guarded, linearly-interpolated threshold "
        f"crossings at {spec.threshold_frac:g}*VDD (the threshold tracks each "
        "point's own swept supply, not the nominal rail) and derives frequency, "
        "duty cycle and time-to-lock from them. The dumps themselves are "
        "**not** committed -- `sim/README.md`'s retention policy treats "
        "waveform data as regenerable from the frozen netlist plus the logged "
        "environment."
    )
    a(
        "  - Not measured here: loop bandwidth and phase margin are open-loop "
        "quantities and need their own AC/linearized-model testbench -- see "
        "`sim/harness/measure.py`'s module docstring for why they are "
        "deliberately out of this reducer's scope."
    )
    a(f"  - DUT / limitations: {methodology_note}")


def _render_measured_points_table(a, results, spec) -> None:
    """Per-point result table for an unswept measurement record."""
    lock_mode = spec.lock is not None
    if lock_mode:
        a("  | Corner | Temp (C) | Supply (V) | Verdict | Locked | Time-to-lock | f_out (post-lock) | Duty | Detail |")
        a("  |---|---|---|---|---|---|---|---|---|")
    else:
        a("  | Corner | Temp (C) | Supply (V) | Verdict | f_out | Duty | Detail |")
        a("  |---|---|---|---|---|---|---|")
    for r in results:
        p = r.point
        verdict = "PASS" if r.passed else "FAIL"
        m = r.measurements[0] if r.measurements else None
        duty = f"{m.duty_cycle * 100:.1f}%" if (m and m.duty_cycle is not None) else "-"
        if lock_mode:
            locked = "-" if m is None else ("yes" if m.locked else "**no**")
            t_lock = measure_mod.format_s(m.lock_time_s) if m else "-"
            fout = measure_mod.format_hz(m.freq_hz) if m else "-"
            a(
                f"  | {p.corner} | {p.temp_c:g} | {p.supply_v:.2f} | {verdict} | "
                f"{locked} | {t_lock} | {fout} | {duty} | {r.reason} |"
            )
        else:
            fout = measure_mod.format_hz(m.freq_hz) if m else "-"
            a(
                f"  | {p.corner} | {p.temp_c:g} | {p.supply_v:.2f} | {verdict} | "
                f"{fout} | {duty} | {r.reason} |"
            )


def _render_sweep_tables(a, results, spec) -> None:
    """Full swept-axis measurement table plus a per-point slope summary.

    This is the characterization data itself, not a summary of it: one row per
    (PVT point, swept value), so a later decision record can cite individual
    numbers rather than a verdict.
    """
    quantity = spec.sweep[0].label.split("=")[0] if spec.sweep else "sweep"
    a("")
    a(f"- **Swept-axis measurements** ({quantity} vs. output frequency, per PVT point):")
    a("")
    a(f"  | Corner | Temp (C) | Supply (V) | {quantity} (V) | f_out | Duty | Note |")
    a("  |---|---|---|---|---|---|---|")
    for r in results:
        p = r.point
        for sweep_point, m in zip(spec.sweep, r.measurements):
            duty = f"{m.duty_cycle * 100:.1f}%" if m.duty_cycle is not None else "-"
            note = "-" if m.oscillating else "no oscillation"
            a(
                f"  | {p.corner} | {p.temp_c:g} | {p.supply_v:.2f} | "
                f"{sweep_point.value:.3f} | {measure_mod.format_hz(m.freq_hz)} | "
                f"{duty} | {note} |"
            )
        if len(r.measurements) < len(spec.sweep):
            a(
                f"  | {p.corner} | {p.temp_c:g} | {p.supply_v:.2f} | (remaining) | - | - | "
                "point aborted before this swept value |"
            )
    a("")
    a(f"- **Per-point tuning summary** (endpoint-to-endpoint slope over the swept {quantity} range):")
    a("")
    a(f"  | Corner | Temp (C) | Supply (V) | Oscillating {quantity} range (V) | f_min | f_max | Mean slope |")
    a("  |---|---|---|---|---|---|---|")
    for r in results:
        p = r.point
        live = [
            (sp, m)
            for sp, m in zip(spec.sweep, r.measurements)
            if m.oscillating and m.freq_hz is not None
        ]
        if len(live) < 2:
            a(
                f"  | {p.corner} | {p.temp_c:g} | {p.supply_v:.2f} | "
                "(fewer than 2 oscillating points) | - | - | - |"
            )
            continue
        v_lo, v_hi = live[0][0].value, live[-1][0].value
        f_lo, f_hi = live[0][1].freq_hz, live[-1][1].freq_hz
        slope = (f_hi - f_lo) / (v_hi - v_lo) if v_hi != v_lo else float("nan")
        a(
            f"  | {p.corner} | {p.temp_c:g} | {p.supply_v:.2f} | "
            f"{v_lo:.3f}-{v_hi:.3f} | {measure_mod.format_hz(f_lo)} | "
            f"{measure_mod.format_hz(f_hi)} | {slope / 1e6:.4g} MHz/V |"
        )
    a("")
    a(
        "  The slope column is an **endpoint-to-endpoint mean over the whole "
        "swept range**, not a local small-signal gain, and the underlying "
        "curve is strongly non-linear -- read the per-swept-value table above "
        "for the shape. It is reported as characterization data; nothing here "
        "ratifies a spec row."
    )


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
    methodology_note: str,
    analysis: str,
    spec=None,
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
    _render_header(
        lines_append=a,
        record_id=record_id,
        slug=slug,
        claim=claim,
        pdk=pdk,
        tool_versions=tool_versions,
        git=git,
        netlist_sha=netlist_sha,
    )
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
    if spec is None:
        a(
            "  - Per-point criterion: ngspice exits 0, prints its analysis-"
            "completion marker, and emits no `Error:` line. This is a **harness "
            "plumbing check** (does xschem+ngspice+sky130 run this DUT to "
            f"completion at this PVT point?), not a design measurement -- {methodology_note}"
        )
    else:
        _render_measurement_criteria(a, spec, methodology_note)
    a(f"  - Analysis: {analysis}.")
    a("- **Result**:")
    a("")
    if spec is None or spec.sweep:
        a("  | Corner | Temp (C) | Supply (V) | Verdict | Detail |")
        a("  |---|---|---|---|---|")
        for r in results:
            p = r.point
            verdict = "PASS" if r.passed else "FAIL"
            a(f"  | {p.corner} | {p.temp_c:g} | {p.supply_v:.2f} | {verdict} | {r.reason} |")
    else:
        _render_measured_points_table(a, results, spec)
    a("")
    overall = "PASS" if not failed else "FAIL"
    a(f"  - **Overall: {overall}** ({len(passed)}/{len(results)} points passed)")
    if spec is not None and spec.sweep:
        _render_sweep_tables(a, results, spec)
    _render_footer(lines_append=a, slug=slug, record_id=record_id, supersedes=supersedes)
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
    methodology_note: str,
    analysis: str,
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
    _render_header(
        lines_append=a,
        record_id=record_id,
        slug=slug,
        claim=claim,
        pdk=pdk,
        tool_versions=tool_versions,
        git=git,
        netlist_sha=netlist_sha,
    )
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
        f"run this DUT to completion, seed by seed?), not a statistical-spec "
        f"measurement -- {methodology_note}"
    )
    a(f"  - Analysis: {analysis}.")
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
    _render_footer(lines_append=a, slug=slug, record_id=record_id, supersedes=supersedes)
    a("")
    return "\n".join(lines)
