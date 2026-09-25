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

from . import acmeasure as ac_mod
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


class SpecRowsError(ValueError):
    """A manifest's `spec_rows` declaration is missing or malformed.

    Raised before any point is simulated (see `sim/harness/cli.py`) so a
    forgotten declaration costs a second, not a corner run.
    """


def spec_rows_from_manifest(
    manifest: dict, *, section: dict | None = None
) -> tuple[list[int], str]:
    """Resolve the `(rows, note)` behind a record's `**Spec row(s)**:` line.

    `spec_rows` is a **required** manifest key, not an optional one: the
    citation convention `measurements/README.md` documents decayed precisely
    because it depended on an author remembering it per record (issue #152).
    Making it mandatory at the manifest -- the one mutable file per
    experiment, per `sim/README.md`'s append-only rule -- means every record
    this harness ever mints carries the line by construction.

    - `"spec_rows": [6, 7]` -- this experiment measures spec/target-spec.md
      rows 6 and 7. `spec_rows_note` is optional context.
    - `"spec_rows": []` -- this experiment deliberately measures **no** spec
      row (harness plumbing, a negative control, ...). `spec_rows_note` is
      then **required**: an empty list is an explicit claim and has to say
      why, so "measures none" is never confusable with "nobody thought about
      it".

    `section` is an optional per-mode override block (today: the manifest's
    `monte_carlo` block), consulted only when it carries its own `spec_rows`
    key -- the same fall-back shape `claim`/`methodology_note`/`analysis`
    already use in `sim/harness/cli.py`.
    """
    source = section if (section and "spec_rows" in section) else manifest
    if "spec_rows" not in source:
        raise SpecRowsError(
            "manifest declares no `spec_rows` -- every testbench must state "
            "which spec/target-spec.md row(s) it measures (e.g. "
            '`"spec_rows": [6, 7]`), or declare `"spec_rows": []` with a '
            '`"spec_rows_note"` saying why it measures none. See '
            "measurements/README.md's citation convention."
        )
    raw = source["spec_rows"]
    if not isinstance(raw, list):
        raise SpecRowsError(
            f"manifest's `spec_rows` must be a list of row numbers, got {type(raw).__name__}"
        )
    rows: list[int] = []
    for entry in raw:
        if isinstance(entry, bool) or not isinstance(entry, int) or entry < 0:
            raise SpecRowsError(
                f"manifest's `spec_rows` entry {entry!r} is not a non-negative "
                "spec/target-spec.md row number"
            )
        rows.append(entry)

    note = str(source.get("spec_rows_note", "") or "").strip()
    if not rows and not note:
        raise SpecRowsError(
            'manifest declares `"spec_rows": []` (this testbench measures no '
            "spec/target-spec.md row) without a `spec_rows_note` saying why -- "
            "an explicit 'measures none' is a claim and must be argued, not "
            "left blank"
        )
    return rows, note


def format_spec_rows(rows: list[int], note: str) -> str:
    """Render the value half of the `- **Spec row(s)**: ...` record line.

    The row numbers come first and are comma-separated, so
    `measurements/aggregate.py`'s `**Spec row(s)**: <digits>` match reads them
    without having to understand the prose that may follow.
    """
    body = ", ".join(str(n) for n in rows) if rows else "none"
    return f"{body} -- {note}" if note else body


def _render_header(
    *,
    lines_append,
    record_id: str,
    slug: str,
    claim: str,
    spec_rows_line: str,
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
    a(f"- **Spec row(s)**: {spec_rows_line}")
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
    if spec.ripple is not None:
        a(
            f"  - Ripple (reported, not gated on): {spec.ripple.summary}. The "
            "ripple nodes are `linearize`d onto the same "
            f"{spec.tran_step} grid and dumped alongside the clock, and "
            "`sim/harness/measure.py`'s `ripple_pp` takes min/max/peak-to-peak "
            "over the window's samples -- so any excursion narrower than that "
            "grid step is attenuated by the resampling, and the figure is the "
            "ripple at that grid's bandwidth. The window is marked **in lock** "
            "only if the lock criterion above was already met at the window's "
            "start; otherwise the figure is shown but labelled as not "
            "ripple-in-lock evidence."
        )
    if spec.transition is not None:
        a(
            f"  - Transition time (reported, not gated on; issue #186): "
            f"{spec.transition.summary}, from the same "
            f"`v({spec.node})` samples the frequency/duty/jitter reduction "
            f"above already extracted edges from -- rise and fall are reported "
            f"separately (a single-ended current-starved ring's PMOS/NMOS "
            f"tail legs are not assumed symmetric) as the mean over every "
            f"edge that completes a monotonic crossing of both levels at or "
            f"after the same population start instant (the lock instant, or "
            f"`settle_from` when the manifest declares no lock criterion)."
        )
    a(
        "  - Not measured here: loop bandwidth and phase margin are open-loop "
        "quantities and need their own AC/linearized-model testbench -- see "
        "`sim/harness/measure.py`'s module docstring for why they are "
        "deliberately out of this reducer's scope, and `sim/loop-ac/` for the "
        "campaign that does measure them."
    )
    a(f"  - DUT / limitations: {methodology_note}")


def _render_ac_criteria(a, ac_spec, methodology_note: str) -> None:
    """The "Methodology / criteria / limitations" bullets for an AC record.

    An AC record's evidentiary weight rests entirely on *which half of the
    loop is simulated and which half is a parameter*, so that split is stated
    before any number is shown.
    """
    a(
        "  - Per-point criterion, part 1 (plumbing): ngspice exits 0, prints "
        f"the harness's analysis-completion marker (`{ac_mod.COMPLETION_MARKER}`, "
        "echoed by the injected `.control` block -- ngspice does not print its "
        'own "Total analysis time" banner for a control-driven analysis), and '
        "emits no `Error:` line."
    )
    a(
        "  - Per-point criterion, part 2 (measurement): the open-loop gain "
        f"`v({ac_spec.node})` falls through unity somewhere inside the swept "
        f"band ({measure_mod.format_hz(ac_spec.f_start_hz)} to "
        f"{measure_mod.format_hz(ac_spec.f_stop_hz)}), for every swept "
        "loop-gain point, so a crossover frequency and a phase margin exist to "
        "report. A swept point with no crossing is reported as **no "
        "crossover**, with no loop bandwidth or phase margin attributed to it."
        + ("" if ac_spec.require_crossover else " (Reported, but not gated on, for this manifest.)")
    )
    a(
        "  - Linearized model: the open-loop transfer function of a type-II "
        "charge-pump PLL is `T(s) = (Icp/2pi) * Z(s) * (2pi*Kvco/s) / N = "
        "(Icp*Kvco/N) * Z(s)/s`. `Z(s)` -- the loop filter's transimpedance -- "
        "is **simulated for real** from `design/loop-filter`'s own sky130 R/C "
        "network, so process corner and temperature move its poles and zero "
        "exactly as the device models say. Everything else collapses into the "
        "single scalar `A = Icp*Kvco/N`, applied as the AC magnitude of the "
        "injected current source and **swept parametrically** over the design "
        "points listed below. The `1/s` VCO phase integrator is an ideal VCCS "
        "into a 1 F capacitor in the testbench, not a device model."
    )
    a(
        "  - What that means for this evidence: this record measures how "
        "`f_c` and phase margin respond to the **filter's** PVT variation and "
        "to a stated range of loop-gain design points. It does **not** "
        "simulate the charge pump's or VCO's own small-signal behaviour, "
        "their per-corner gain variation (that is `sim/vco`'s record, cited in "
        "the loop-gain table's basis column), charge-pump non-idealities "
        "(finite output impedance, `UP`/`DN` mismatch, dead-zone), or any "
        "sampled-loop correction beyond the continuous-time approximation."
    )
    a(
        "  - Measurement method: the harness injects the analysis itself (an "
        "ngspice `.control` block built by `sim/harness/acmeasure.py`) -- one "
        f"`alter @{ac_spec.source.lower()}[acmag]` + one `ac dec "
        f"{ac_spec.dec_points} {ac_spec.f_start} {ac_spec.f_stop}` + one "
        "`wrdata` per swept loop-gain point, all inside a single ngspice "
        "invocation per PVT point. The reducer unwraps the phase across the "
        "sweep (so a crossover past a -180 deg wrap is not read off the wrong "
        "branch), interpolates the unity-gain crossing in log-magnitude vs. "
        "log-frequency, and reports phase margin as `180 deg + arg T` there. "
        "The dumps themselves are **not** committed -- `sim/README.md`'s "
        "retention policy treats waveform data as regenerable from the frozen "
        "netlist plus the logged environment."
    )
    bounds = []
    if ac_spec.phase_margin_floor_deg is not None:
        bounds.append(
            f"phase margin >= {ac_spec.phase_margin_floor_deg:g} deg "
            "(`spec/target-spec.md` row 7, DRAFT)"
        )
    if ac_spec.f_c_ceiling_hz is not None:
        bounds.append(
            f"f_c < {measure_mod.format_hz(ac_spec.f_c_ceiling_hz)} "
            f"(row 6's `f_c < f_ref/10` at f_ref = "
            f"{measure_mod.format_hz(ac_spec.f_ref_hz)}, DRAFT)"
        )
    if bounds:
        a(
            "  - DRAFT bounds shown alongside each measurement: "
            + "; ".join(bounds)
            + ". These are **reported, not enforced**"
            + (
                " -- this manifest does not gate its verdict on them, because "
                "rows 6 and 7 are DRAFT, not ratified, and a harness PASS must "
                "never read as a ratification (nor a FAIL as a demand to relax "
                "a target). A measurement that misses a DRAFT bound is recorded "
                "as a miss."
                if not ac_spec.gate_on_bounds
                else " by the reducer, but this manifest opts in to gating on them."
            )
        )
    a(f"  - DUT / limitations: {methodology_note}")


def _render_ac_tables(a, results, ac_spec) -> None:
    """Loop-gain design-point provenance, then the full per-point AC table."""
    a("")
    a("- **Swept loop-gain design points** (`A = Icp * Kvco / N`, applied as the "
      "injected AC magnitude):")
    a("")
    a("  | Label | Icp | Kvco | N | A | Basis |")
    a("  |---|---|---|---|---|---|")
    for g in ac_spec.loop_gain:
        a(
            f"  | `{g.label}` | {g.icp_a * 1e6:g} uA | {g.kvco_hz_per_v / 1e6:g} MHz/V | "
            f"{g.n_divide:g} | {g.scalar:.4g} | {g.basis} |"
        )
    a("")
    a("- **Loop-dynamics measurements** (one row per PVT point x loop-gain point):")
    a("")
    a("  | Corner | Temp (C) | Loop-gain point | f_c | Phase margin | Gain margin | Row 6 | Row 7 |")
    a("  |---|---|---|---|---|---|---|---|")
    for r in results:
        p = r.point
        for m in r.measurements:
            gm = "-" if m.gain_margin_db is None else f"{m.gain_margin_db:.1f} dB"
            row6 = "-" if m.meets_fc_ceiling is None else ("meets" if m.meets_fc_ceiling else "**miss**")
            row7 = "-" if m.meets_pm_floor is None else ("meets" if m.meets_pm_floor else "**miss**")
            a(
                f"  | {p.corner} | {p.temp_c:g} | `{m.label}` | "
                f"{measure_mod.format_hz(m.crossover_hz)} | "
                f"{ac_mod.format_deg(m.phase_margin_deg)} | {gm} | {row6} | {row7} |"
            )
        if len(r.measurements) < len(ac_spec.loop_gain):
            a(
                f"  | {p.corner} | {p.temp_c:g} | (remaining) | - | - | - | - | - | "
            )
    a("")
    a(
        "  The `Row 6` / `Row 7` columns compare each measurement against "
        "`spec/target-spec.md`'s **DRAFT** bounds for loop bandwidth and phase "
        "margin. They are annotations on the data, not a verdict: no row here "
        "is ratified, and per `CLAUDE.md` ratification is a separate "
        "decision-record act argued on its own merits."
    )
    _render_ac_extremes(a, results, ac_spec)


def _render_ac_extremes(a, results, ac_spec) -> None:
    """Per-loop-gain-point worst case across the PVT matrix.

    This is the shape a row-6/row-7 decision record actually needs to cite:
    not "it was fine at nominal" but "across the corner matrix this campaign
    ran, the margin was never worse than X".
    """
    a("")
    a("- **Worst case across the PVT matrix, per loop-gain point**:")
    a("")
    a("  | Loop-gain point | Min phase margin (corner) | Max f_c (corner) | Points with no crossover |")
    a("  |---|---|---|---|")
    for i, g in enumerate(ac_spec.loop_gain):
        pm_worst = None
        fc_worst = None
        no_cross = 0
        for r in results:
            if i >= len(r.measurements):
                continue
            m = r.measurements[i]
            if not m.crossed:
                no_cross += 1
                continue
            tag = f"{r.point.corner}/{r.point.temp_c:g}C"
            if pm_worst is None or m.phase_margin_deg < pm_worst[0]:
                pm_worst = (m.phase_margin_deg, tag)
            if fc_worst is None or m.crossover_hz > fc_worst[0]:
                fc_worst = (m.crossover_hz, tag)
        pm_txt = "-" if pm_worst is None else f"{pm_worst[0]:.1f} deg ({pm_worst[1]})"
        fc_txt = "-" if fc_worst is None else f"{measure_mod.format_hz(fc_worst[0])} ({fc_worst[1]})"
        a(f"  | `{g.label}` | {pm_txt} | {fc_txt} | {no_cross} |")
    a("")


def _format_transition(m) -> str:
    """`Transition (rise/fall)` cell text -- `-` when the manifest carries no
    `measure.transition` block, or when neither edge direction measured a
    figure for this point (`m` itself is still non-`None` in that case)."""
    if m is None or (m.rise_time_s is None and m.fall_time_s is None):
        return "-"
    rise = measure_mod.format_s(m.rise_time_s) if m.rise_time_s is not None else "-"
    fall = measure_mod.format_s(m.fall_time_s) if m.fall_time_s is not None else "-"
    return f"{rise} / {fall}"


def _render_measured_points_table(a, results, spec) -> None:
    """Per-point result table for an unswept measurement record."""
    lock_mode = spec.lock is not None
    transition_mode = spec.transition is not None
    transition_col = " Transition (rise/fall) |" if transition_mode else ""
    transition_sep = "---|" if transition_mode else ""
    if lock_mode:
        a(
            "  | Corner | Temp (C) | Supply (V) | Verdict | Locked | "
            f"Time-to-lock | f_out (post-lock) | Duty |{transition_col} Detail |"
        )
        a(f"  |---|---|---|---|---|---|---|---|{transition_sep}---|")
    else:
        a(f"  | Corner | Temp (C) | Supply (V) | Verdict | f_out | Duty |{transition_col} Detail |")
        a(f"  |---|---|---|---|---|---|{transition_sep}---|")
    for r in results:
        p = r.point
        verdict = "PASS" if r.passed else "FAIL"
        m = r.measurements[0] if r.measurements else None
        duty = f"{m.duty_cycle * 100:.1f}%" if (m and m.duty_cycle is not None) else "-"
        transition_cell = f" {_format_transition(m)} |" if transition_mode else ""
        if lock_mode:
            locked = "-" if m is None else ("yes" if m.locked else "**no**")
            t_lock = measure_mod.format_s(m.lock_time_s) if m else "-"
            fout = measure_mod.format_hz(m.freq_hz) if m else "-"
            a(
                f"  | {p.corner} | {p.temp_c:g} | {p.supply_v:.2f} | {verdict} | "
                f"{locked} | {t_lock} | {fout} | {duty} |{transition_cell} {r.reason} |"
            )
        else:
            fout = measure_mod.format_hz(m.freq_hz) if m else "-"
            a(
                f"  | {p.corner} | {p.temp_c:g} | {p.supply_v:.2f} | {verdict} | "
                f"{fout} | {duty} |{transition_cell} {r.reason} |"
            )


def _render_mc_trials_table(a, results, spec) -> None:
    """Per-trial result table for a Monte Carlo campaign against a
    measurement manifest -- `_render_measured_points_table`'s Monte Carlo
    twin, keyed by (trial, seed) instead of (corner, temp, supply), with a
    Period jitter column called out explicitly rather than left to the
    Detail note alone, since row 9 is this campaign's usual reason to exist.
    """
    lock_mode = spec.lock is not None
    jitter_mode = spec.jitter is not None
    header = ["Trial", "Seed", "Verdict"]
    if lock_mode:
        header += ["Locked", "Time-to-lock", "f_out (post-lock)", "Duty"]
    else:
        header += ["f_out", "Duty"]
    if jitter_mode:
        header.append("Period jitter")
    header.append("Detail")
    a("  | " + " | ".join(header) + " |")
    a("  |" + "---|" * len(header))
    for r in results:
        t = r.trial
        verdict = "PASS" if r.passed else "FAIL"
        m = r.measurements[0] if r.measurements else None
        duty = f"{m.duty_cycle * 100:.1f}%" if (m and m.duty_cycle is not None) else "-"
        row = [str(t.trial), str(t.seed), verdict]
        if lock_mode:
            locked = "-" if m is None else ("yes" if m.locked else "**no**")
            t_lock = measure_mod.format_s(m.lock_time_s) if m else "-"
            fout = measure_mod.format_hz(m.freq_hz) if m else "-"
            row += [locked, t_lock, fout, duty]
        else:
            fout = measure_mod.format_hz(m.freq_hz) if m else "-"
            row += [fout, duty]
        if jitter_mode:
            if m is None or m.period_jitter_frac is None:
                row.append("-")
            else:
                row.append(f"{m.period_jitter_frac * 100:.3f}% ({m.jitter_cycles} cycles)")
        row.append(r.reason)
        a("  | " + " | ".join(row) + " |")


def _render_ripple_table(a, results, spec) -> None:
    """Per-point ripple table for a manifest with a `measure.ripple` block.

    One column pair (pp, [min..max]) per ripple node, plus whether the window
    was in lock -- a ripple figure from a point that never locked is still
    shown (it is what the rail/control node did), but is explicitly marked as
    not ripple-in-lock evidence.
    """
    nodes = spec.ripple.nodes
    a("")
    a(f"- **Ripple** ({spec.ripple.summary}; reported, not gated on):")
    a("")
    head = " | ".join(f"v({n}) pp | v({n}) min..max" for n in nodes)
    a(f"  | Corner | Temp (C) | Supply (V) | Window in lock | {head} |")
    a("  |---|---|---|---|" + "---|---|" * len(nodes))
    for r in results:
        p = r.point
        m = r.measurements[0] if r.measurements else None
        by_node = {x.node: x for x in (m.ripple if m else ())}
        if not by_node:
            in_lock = "-"
        else:
            flag = next(iter(by_node.values())).in_lock
            in_lock = "n/a" if flag is None else ("yes" if flag else "**no**")
        cells = []
        for n in nodes:
            x = by_node.get(n)
            if x is None or x.pp is None:
                cells.append("- | -")
            else:
                cells.append(f"{measure_mod.format_v(x.pp)} | {x.v_min:.5g}..{x.v_max:.5g} V")
        a(
            f"  | {p.corner} | {p.temp_c:g} | {p.supply_v:.2f} | {in_lock} | "
            + " | ".join(cells)
            + " |"
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
    spec_rows_line: str,
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
    ac_spec=None,
    manifest_has_supply: bool = True,
    corner_note: str | None = None,
    execution_note: str | None = None,
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
        spec_rows_line=spec_rows_line,
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
    if manifest_has_supply:
        a(f"  - Supplies (V): {', '.join(f'{v:.2f}' for v in supplies_used)}")
    else:
        a(
            "  - Supplies (V): **not applicable** -- this manifest declares a "
            "`null` `supply_pattern` because its DUT has no supply terminal, so "
            "there is nothing in the netlist a supply substitution could patch. "
            "The supply axis of the ratified PVT grid (`spec/target-spec.md` "
            "row 1 x `DR-003`) is not exercised here; see the DUT / limitations "
            "note for where supply dependence enters this claim instead."
        )
    a(f"  - Total points: {len(points)}")
    if corner_note:
        a(f"  - Corner-set note: {corner_note}")
    if subset_reason:
        a(f"  - **Subset of the manifest's default grid**: {subset_reason}")
    if execution_note:
        a(f"- **Execution**: {execution_note}")
    a("- **Methodology / criteria / limitations**:")
    if spec is not None:
        _render_measurement_criteria(a, spec, methodology_note)
    elif ac_spec is not None:
        _render_ac_criteria(a, ac_spec, methodology_note)
    else:
        a(
            "  - Per-point criterion: ngspice exits 0, prints its analysis-"
            "completion marker, and emits no `Error:` line. This is a **harness "
            "plumbing check** (does xschem+ngspice+sky130 run this DUT to "
            f"completion at this PVT point?), not a design measurement -- {methodology_note}"
        )
    a(f"  - Analysis: {analysis}.")
    a("- **Result**:")
    a("")
    if spec is not None and not spec.sweep:
        _render_measured_points_table(a, results, spec)
        if spec.ripple is not None:
            _render_ripple_table(a, results, spec)
    else:
        a("  | Corner | Temp (C) | Supply (V) | Verdict | Detail |")
        a("  |---|---|---|---|---|")
        for r in results:
            p = r.point
            verdict = "PASS" if r.passed else "FAIL"
            supply = f"{p.supply_v:.2f}" if manifest_has_supply else "n/a"
            a(f"  | {p.corner} | {p.temp_c:g} | {supply} | {verdict} | {r.reason} |")
    a("")
    overall = "PASS" if not failed else "FAIL"
    a(f"  - **Overall: {overall}** ({len(passed)}/{len(results)} points passed)")
    if spec is not None and spec.sweep:
        _render_sweep_tables(a, results, spec)
    if ac_spec is not None:
        _render_ac_tables(a, results, ac_spec)
    _render_footer(lines_append=a, slug=slug, record_id=record_id, supersedes=supersedes)
    a("")
    return "\n".join(lines)


def render_mc(
    *,
    record_id: str,
    slug: str,
    claim: str,
    spec_rows_line: str,
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
    execution_note: str | None = None,
    spec=None,
) -> str:
    """Render a Monte Carlo evidence record. Same append-only schema and
    directory conventions as `render` (PVT) -- see sim/README.md -- adapted
    for a statistical trial matrix instead of a PVT point matrix: trials
    share one (corner, temp, supply) point (see `montecarlo.McTrial`) and
    vary only by RNG seed, so the record states that point once instead of
    per row, and states the MC_MM_SWITCH/MC_PR_SWITCH sampling configuration
    that applied to every trial.

    `spec` is the manifest's parsed `measure` block, `None` for a
    plumbing-only manifest (e.g. `sim/pdk-smoke`'s) -- the same argument
    `render`'s PVT path takes, threaded through so a statistical campaign
    against a measurement manifest (e.g. `sim/pll-lock`'s `measure.lock` /
    `measure.jitter`) states the same per-trial criterion and result columns
    a PVT record of that manifest would, instead of only the harness-plumbing
    check every Monte Carlo record used to be limited to.
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
        spec_rows_line=spec_rows_line,
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
    if execution_note:
        a(f"- **Execution**: {execution_note}")
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
    if spec is None:
        a(
            "  - Per-trial criterion: ngspice exits 0, prints its analysis-"
            "completion marker, and emits no `Error:` line. This is a **harness "
            "plumbing check** (does the sky130 statistical-sampling mechanism "
            f"run this DUT to completion, seed by seed?), not a statistical-spec "
            f"measurement -- {methodology_note}"
        )
    else:
        a(
            "  - Per-trial criterion, part 1 (plumbing): ngspice exits 0, prints "
            f"the harness's analysis-completion marker (`{measure_mod.COMPLETION_MARKER}`, "
            "echoed by the injected `.control` block), and emits no `Error:` "
            "line -- the same check every other unit in this package uses."
        )
        if spec.lock is not None:
            a(
                "  - Per-trial criterion, part 2 (measurement): the loop "
                f"**locks** within the transient window. Lock criterion: "
                f"{spec.lock.summary}. A trial that never satisfies it is "
                "reported as **no lock**, exactly as a PVT point would be, "
                "and (per row 9's own wording) contributes no period-jitter "
                "figure either -- it is not charged as a jitter failure, "
                "because a design that has not converged has no post-lock "
                "population to measure jitter over."
                + ("" if spec.require_lock else " (Reported, but not gated on, for this manifest.)")
            )
        if spec.jitter is not None:
            a(f"  - Period jitter (row 9): {spec.jitter.summary}.")
        a(
            "  - Measurement method: the same manifest-owned `.control` block "
            "a PVT point's `measure` block injects (`sim/harness/measure.py`'s "
            "`build_control_block`) is appended after this trial's "
            "`MC_MM_SWITCH`/`MC_PR_SWITCH`/seed cards, so each trial runs the "
            "manifest's transient window against its own sampled device draw "
            "and is reduced by the same threshold-crossing extractor a PVT "
            "point's dump is. The waveform dumps themselves are **not** "
            "committed -- `sim/README.md`'s retention policy treats them as "
            "regenerable from the frozen netlist plus the logged environment."
        )
        a(f"  - {methodology_note}")
    a(f"  - Analysis: {analysis}.")
    a("- **Result**:")
    a("")
    if spec is None:
        a("  | Trial | Seed | Verdict | Detail |")
        a("  |---|---|---|---|")
        for r in results:
            t = r.trial
            verdict = "PASS" if r.passed else "FAIL"
            a(f"  | {t.trial} | {t.seed} | {verdict} | {r.reason} |")
    else:
        _render_mc_trials_table(a, results, spec)
    a("")
    overall = "PASS" if not failed else "FAIL"
    a(f"  - **Overall: {overall}** ({len(passed)}/{len(results)} trials passed)")
    _render_footer(lines_append=a, slug=slug, record_id=record_id, supersedes=supersedes)
    a("")
    return "\n".join(lines)
