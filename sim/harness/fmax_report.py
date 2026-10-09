"""Render the append-only evidence record for an Fmax campaign (issue #244).

Same record schema as `report.py` (shared header/footer, `**Overall: ...**`
line, `**Spec row(s)**` citation), so `measurements/aggregate.py` discovers it
like any other `sim/<slug>/records/*.md`. The per-cell table under the
`FMAX_TABLE_HEADING` heading is the machine-read contract the aggregator's
Fmax rollup parses; change its columns only together with
`measurements/aggregate.py`.
"""

from __future__ import annotations

from pathlib import Path

from . import fmax as fmax_mod
from . import report as report_mod

FMAX_TABLE_HEADING = "### Fmax boundary per cell"
FMAX_TABLE_COLUMNS = (
    "Modulus N", "Corner", "Temp (C)", "Supply (V)", "Status",
    "Highest verified pass (MHz)", "Adjacent failing probe (MHz)", "Probes", "Detail",
)


def _mhz(hz) -> str:
    return "--" if hz is None else f"{hz / 1e6:g}"


def overall(cells) -> tuple:
    """(verdict, detail). PASS means every cell resolved to a bracket, a
    non-monotonic bracket, or an explicit above-range censor -- not that the
    divider meets any frequency target (none is ratified). A cell that is
    inconclusive or censored low is a recorded miss and fails the record."""
    counts: dict = {}
    for c in cells:
        counts[c["boundary"].status] = counts.get(c["boundary"].status, 0) + 1
    bad = counts.get(fmax_mod.CELL_INCONCLUSIVE, 0) + counts.get(fmax_mod.CENSORED_LOW, 0)
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    verdict = "FAIL" if bad else "PASS"
    return verdict, f"{len(cells) - bad}/{len(cells)} cells resolved; {summary}"


def render(
    *,
    record_id: str,
    slug: str,
    manifest: dict,
    spec: fmax_mod.FmaxSpec,
    pdk,
    tool_versions: dict,
    repo_root: Path,
    netlist_snapshot: Path,
    cells: list,  # dicts: n, corner, temp_c, supply_v, boundary
    probe_count: int,
    subset_reason: str | None,
    supersedes: str | None,
    execution_note: str | None,
) -> str:
    git = report_mod.git_info(
        repo_root,
        ignore_prefixes=(
            f"sim/{slug}/corners/{record_id}/",
            f"sim/{slug}/records/{record_id}.md",
            f"sim/{slug}/netlist-snapshots/{record_id}.spice",
        ),
    )
    lines: list = []
    a = lines.append
    report_mod._render_header(
        lines_append=a,
        record_id=record_id,
        slug=slug,
        claim=manifest["claim"],
        spec_rows_line=report_mod.format_spec_rows(*report_mod.spec_rows_from_manifest(manifest)),
        pdk=pdk,
        tool_versions=tool_versions,
        git=git,
        netlist_sha=report_mod.sha256_file(netlist_snapshot),
    )
    s, w, c = spec.search, spec.stimulus, spec.criterion
    a("- **Search / corner matrix run**:")
    a(f"  - Moduli: {', '.join(str(m) for m in sorted({x['n'] for x in cells}))}")
    a(f"  - Process corners: {', '.join(sorted({x['corner'] for x in cells}))}")
    a(f"  - Temperatures (deg C): {', '.join(f'{t:g}' for t in sorted({x['temp_c'] for x in cells}))}")
    a(f"  - Supplies (V): {', '.join(f'{v:.2f}' for v in sorted({x['supply_v'] for x in cells}))}")
    a(f"  - Cells (modulus x PVT point): {len(cells)}; probes run: {probe_count}")
    if subset_reason:
        a(f"  - **Subset of the manifest's default grid**: {subset_reason}")
    if execution_note:
        a(f"- **Execution**: {execution_note}")
    a("- **Methodology / criteria / limitations**:")
    a(
        f"  - Search: grid {s.f_min_hz / 1e6:g}-{s.f_max_hz / 1e6:g} MHz at "
        f"{s.resolution_hz / 1e6:g} MHz resolution; stage 1 probes every "
        f"{s.coarse_stride}th grid point plus the top, stage 2 probes every grid point inside "
        "the lowest coarse pass-to-fail transition. Monotonicity is observed, not assumed: "
        "a pass above a fail is reported as NON_MONOTONIC. A pass island between two coarse "
        "probes would not be seen -- a stated limitation."
    )
    a(
        f"  - Stimulus (declared waveform assumptions): ideal CLK, high level tracks the "
        f"point's supply, {w.rise_s * 1e12:g} ps rise/fall, {w.duty:.0%} duty at the 50% points; "
        f"RESETB low until {w.reset_low_until_s * 1e9:g} ns, at the supply by "
        f"{w.reset_high_at_s * 1e9:g} ns; NSEL static. Period, pulse width and the expected "
        "division period are all derived from the one probe frequency. The result "
        "characterizes this ideal input; it is not a guarantee for the real VCO waveform."
    )
    a(
        f"  - Per-probe criterion: ignore the first {c.skip_output_periods} expected output "
        f"periods after reset release; then {c.min_periods} consecutive output periods must "
        f"each be within +/-{c.tolerance_frac:.1%} of N/f_CLK, with no leading or trailing "
        "silence longer than one tolerated period. Averaging cannot hide a skipped or "
        "malformed cycle. Too few edges in a complete window is a measured FAIL."
    )
    a(
        "  - Inconclusive: a simulator timeout, `Error:` line, missing completion marker, or a "
        "missing/unparseable/truncated waveform is INCONCLUSIVE, never an electrical FAIL. A "
        "cell with an inconclusive probe between its highest pass and lowest failure has no "
        "established bracket and fails the record."
    )
    a(
        "  - Cell statuses: BRACKETED (highest verified pass + adjacent failing grid probe), "
        "NON_MONOTONIC (bracket of the lowest failure, with passes above it listed), "
        "CENSORED_HIGH (every probe passed through the top of the range; the boundary is above "
        "it and the figure is only a lower bound), CENSORED_LOW (the lowest searched frequency "
        "failed), INCONCLUSIVE. No unbracketed scalar is a maximum."
    )
    a(f"  - DUT / limitations: {manifest['methodology_note']}")
    a(f"  - Analysis: {manifest['analysis']}")
    a(
        "  - Scope: this record is the Fmax component only of the digital characterization "
        "signoff item 8 names. Power and area have no evidence here; item 8 stays unmet, and "
        "spec row 4 stays DRAFT."
    )
    a("- **Result**:")
    a("")
    a(FMAX_TABLE_HEADING)
    a("")
    a("| " + " | ".join(FMAX_TABLE_COLUMNS) + " |")
    a("|" + "---|" * len(FMAX_TABLE_COLUMNS))
    for x in cells:
        b = x["boundary"]
        a(
            f"| {x['n']} | {x['corner']} | {x['temp_c']:g} | {x['supply_v']:.2f} | {b.status} | "
            f"{_mhz(b.pass_hz)} | {_mhz(b.fail_hz)} | {b.probes} | {b.detail.replace('|', '/')} |"
        )
    a("")
    verdict, detail = overall(cells)
    a(f"  - **Overall: {verdict}** ({detail})")
    report_mod._render_footer(lines_append=a, slug=slug, record_id=record_id, supersedes=supersedes)
    a("")
    return "\n".join(lines)
