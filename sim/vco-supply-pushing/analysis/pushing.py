#!/usr/bin/env python3
"""Derive the frequency-vs-VDD supply-pushing figure from a sim/ evidence record.

The `sim/vco-supply-pushing` campaign holds `VCTRL` fixed and lets the corner
runner's own supply axis (1.62 / 1.80 / 1.98 V, `spec/target-spec.md` row 1's
ratified range) be the measured independent variable. The pushing figure is
therefore a **cross-point** quantity: it lives across the three PVT rows that
share a (corner, temperature, `VCTRL`) triple, so `sim/harness/report.py` --
which renders one row per point and a slope over each point's *own* swept axis
-- cannot express it. This script does, and only that: it reads a record's
committed **Swept-axis measurements** table and restates it as `%/V`.

It never simulates, never reads a checkpoint, and never invents a number:
every value it prints is derived from the record markdown handed to it, which
is what makes the derivation checkable long after the run (`--check`
regenerates the section and diffs it against what the record already carries).

Usage:

    # print the derived section to stdout
    python3 sim/vco-supply-pushing/analysis/pushing.py RECORD.md

    # append it to the record, once, at mint time (refuses if already present)
    python3 sim/vco-supply-pushing/analysis/pushing.py RECORD.md --append

    # re-derive and verify the section already in the record (exit 1 on drift)
    python3 sim/vco-supply-pushing/analysis/pushing.py RECORD.md --check

Standard library only, same convention as `sim/run_corners.py` and
`measurements/aggregate.py`. No PDK, ngspice or xschem required.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SECTION_MARKER = "- **Derived supply-pushing analysis**"

# DR-006's structural floor is `1/VDD` itself (55.6 %/V at 1.8 V), so it is
# evaluated at whatever rail a given slope is centred on rather than pinned to
# the nominal one -- see spec/decision-records/DR-006-statistical-rows-
# ratification.md, "Budget 1 (AC)".
_HZ_UNITS = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}

_ROW_RE = re.compile(
    r"^\s*\|\s*(?P<corner>\w+)\s*\|\s*(?P<temp>-?[\d.]+)\s*\|"
    r"\s*(?P<supply>[\d.]+)\s*\|\s*(?P<swept>[\d.]+)\s*\|"
    r"\s*(?P<freq>[^|]+?)\s*\|\s*(?P<duty>[^|]*?)\s*\|\s*(?P<note>[^|]*?)\s*\|\s*$"
)


class AnalysisError(RuntimeError):
    pass


def parse_hz(text: str) -> float | None:
    """`"318.1 MHz"` -> `3.181e8`. `"-"` (no measurement) -> `None`."""
    text = text.strip()
    if text in {"-", ""}:
        return None
    parts = text.split()
    if len(parts) != 2 or parts[1] not in _HZ_UNITS:
        raise AnalysisError(f"unparseable frequency cell: {text!r}")
    return float(parts[0]) * _HZ_UNITS[parts[1]]


def parse_swept_table(record_text: str) -> list[dict]:
    """Extract the record's `Swept-axis measurements` rows, in file order."""
    lines = record_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("- **Swept-axis measurements**"):
            start = i
            break
    if start is None:
        raise AnalysisError("record has no `Swept-axis measurements` table")

    rows: list[dict] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("- **") and rows:
            break  # next bullet section: the table is over
        m = _ROW_RE.match(line)
        if not m:
            continue
        rows.append(
            {
                "corner": m.group("corner"),
                "temp_c": float(m.group("temp")),
                "supply_v": float(m.group("supply")),
                "vctrl_v": float(m.group("swept")),
                "freq_hz": parse_hz(m.group("freq")),
                "oscillating": m.group("note").strip() != "no oscillation",
            }
        )
    if not rows:
        raise AnalysisError("`Swept-axis measurements` table parsed to zero rows")
    return rows


def floor_pct_per_v(rail_v: float) -> float:
    """DR-006's structural pushing floor `1/VDD`, in %/V, at `rail_v`."""
    return 100.0 / rail_v


def _fractional_slope(f_a: float, f_b: float, v_a: float, v_b: float) -> tuple[float, float]:
    """Centred secant estimate of `(1/f) df/dV` between two supply points.

    Returns `(slope_pct_per_v, rail_v)` -- the slope and the rail it is
    centred on, which is the rail DR-006's `1/VDD` floor is evaluated at for
    that slope.
    """
    rail = 0.5 * (v_a + v_b)
    f_ref = 0.5 * (f_a + f_b)
    return 100.0 * (f_b - f_a) / f_ref / (v_b - v_a), rail


def derive(rows: list[dict]) -> list[dict]:
    """One derived entry per (corner, temp, VCTRL) triple with >=2 supplies."""
    grouped: dict[tuple, dict[float, dict]] = {}
    order: list[tuple] = []
    for r in rows:
        key = (r["corner"], r["temp_c"], r["vctrl_v"])
        if key not in grouped:
            grouped[key] = {}
            order.append(key)
        grouped[key][r["supply_v"]] = r

    derived = []
    for key in order:
        corner, temp_c, vctrl = key
        by_supply = grouped[key]
        supplies = sorted(by_supply)
        usable = [
            v
            for v in supplies
            if by_supply[v]["oscillating"] and by_supply[v]["freq_hz"] is not None
        ]
        entry = {
            "corner": corner,
            "temp_c": temp_c,
            "vctrl_v": vctrl,
            "supplies": supplies,
            "freqs": {v: by_supply[v]["freq_hz"] for v in supplies},
            "usable": usable,
            "segments": [],
            "span": None,
        }
        for v_a, v_b in zip(usable, usable[1:]):
            slope, rail = _fractional_slope(
                by_supply[v_a]["freq_hz"], by_supply[v_b]["freq_hz"], v_a, v_b
            )
            entry["segments"].append({"v_a": v_a, "v_b": v_b, "slope": slope, "rail": rail})
        if len(usable) >= 2:
            v_a, v_b = usable[0], usable[-1]
            slope, rail = _fractional_slope(
                by_supply[v_a]["freq_hz"], by_supply[v_b]["freq_hz"], v_a, v_b
            )
            # The endpoint-to-endpoint slope is centred on the mid rail, which
            # for a symmetric +/-10 % axis is the nominal rail itself.
            entry["span"] = {"v_a": v_a, "v_b": v_b, "slope": slope, "rail": rail}
        derived.append(entry)
    return derived


def _fmt_hz(value: float | None) -> str:
    """Same 4-significant-digit convention `sim/harness/measure.py` renders with."""
    if value is None:
        return "-"
    if value >= 1e9:
        return f"{value / 1e9:.4g} GHz"
    if value >= 1e6:
        return f"{value / 1e6:.4g} MHz"
    if value >= 1e3:
        return f"{value / 1e3:.4g} kHz"
    return f"{value:.4g} Hz"


def render_section(derived: list[dict], record_id: str) -> str:
    if not derived:
        raise AnalysisError("nothing to derive: no (corner, temp, VCTRL) triple found")

    supplies = sorted({v for e in derived for v in e["supplies"]})
    out: list[str] = []
    a = out.append
    a("")
    a(
        f"{SECTION_MARKER} (frequency-vs-`VDD` pushing at fixed `VCTRL`, derived "
        f"from this record's own **Swept-axis measurements** table):"
    )
    a("")
    a(
        "  Generated, not hand-entered. Every number below is derived by "
        "`sim/vco-supply-pushing/analysis/pushing.py` from the table above and "
        "from nothing else -- no re-simulation, no checkpoint, no external "
        "input. Re-derive and verify with:"
    )
    a("")
    a(
        f"      python3 sim/vco-supply-pushing/analysis/pushing.py "
        f"sim/vco-supply-pushing/records/{record_id}.md --check"
    )
    a("")
    a(
        "  **Definitions.** `S` is fractional-frequency supply pushing, "
        "`(1/f) df/dVDD`, in %/V. Each `S` is a centred secant between two "
        "supply points: the frequency difference over the supply difference, "
        "normalised by the mean of the two frequencies, so it estimates the "
        "slope at the rail midway between them (the `rail` each column names). "
        "`S_span` is the same estimator across the whole ratified "
        f"{supplies[0]:.2f}-{supplies[-1]:.2f} V range, centred on "
        f"{0.5 * (supplies[0] + supplies[-1]):.2f} V."
    )
    a("")
    a(
        "  **Floor.** `spec/decision-records/DR-006-statistical-rows-"
        "ratification.md` (Budget 1, AC) argues a current-starved single-ended "
        "ring's pushing *magnitude* has a structural floor of `1/VDD` -- "
        f"{floor_pct_per_v(1.8):.1f} %/V at 1.80 V -- because the supply is "
        "also the ring's own `V_swing`. The floor is `1/VDD` itself, so it is "
        "evaluated at the rail each slope is centred on, not pinned to 1.80 V. "
        "The `vs floor` column compares `|S_span|` against the floor at "
        "`S_span`'s own rail."
    )
    a("")

    seg_pairs: list[tuple[float, float]] = []
    for e in derived:
        for s in e["segments"]:
            pair = (s["v_a"], s["v_b"])
            if pair not in seg_pairs:
                seg_pairs.append(pair)
    seg_pairs.sort()

    header = "  | Corner | Temp (C) | VCTRL (V) |"
    for v in supplies:
        header += f" f @ {v:.2f} V |"
    for v_a, v_b in seg_pairs:
        header += f" S {v_a:.2f}->{v_b:.2f} V (%/V) |"
    header += " S_span (%/V) | floor @ S_span rail (%/V) | vs floor |"
    a(header)
    a("  |" + "---|" * (3 + len(supplies) + len(seg_pairs) + 3))

    for e in derived:
        row = f"  | {e['corner']} | {e['temp_c']:g} | {e['vctrl_v']:.3f} |"
        for v in supplies:
            row += f" {_fmt_hz(e['freqs'].get(v))} |"
        for v_a, v_b in seg_pairs:
            match = next(
                (s for s in e["segments"] if (s["v_a"], s["v_b"]) == (v_a, v_b)), None
            )
            row += f" {match['slope']:+.1f} |" if match else " - |"
        if e["span"] is None:
            row += " - | - | not derivable (fewer than 2 oscillating supply points) |"
        else:
            span = e["span"]
            floor = floor_pct_per_v(span["rail"])
            verdict = "ABOVE floor" if abs(span["slope"]) >= floor else "BELOW floor"
            row += f" {span['slope']:+.1f} | {floor:.1f} | {verdict} |"
        a(row)

    a("")
    spans = [e for e in derived if e["span"] is not None]
    above = [
        e for e in spans if abs(e["span"]["slope"]) >= floor_pct_per_v(e["span"]["rail"])
    ]
    below = [e for e in spans if e not in above]
    a(
        f"  **Summary**: {len(spans)} (corner, temperature, VCTRL) triples yield a "
        f"pushing figure; {len(above)} are at or above DR-006's structural floor at "
        f"their own rail, {len(below)} are below it."
    )
    if spans:
        worst = max(spans, key=lambda e: abs(e["span"]["slope"]))
        mildest = min(spans, key=lambda e: abs(e["span"]["slope"]))
        a("")
        a(
            f"  - Largest magnitude: **{worst['span']['slope']:+.1f} %/V** at "
            f"{worst['corner']}/{worst['temp_c']:g} degC/VCTRL="
            f"{worst['vctrl_v']:.3f} V "
            f"({abs(worst['span']['slope']) / floor_pct_per_v(worst['span']['rail']):.2f}x "
            "the floor at that rail)."
        )
        a(
            f"  - Smallest magnitude: **{mildest['span']['slope']:+.1f} %/V** at "
            f"{mildest['corner']}/{mildest['temp_c']:g} degC/VCTRL="
            f"{mildest['vctrl_v']:.3f} V "
            f"({abs(mildest['span']['slope']) / floor_pct_per_v(mildest['span']['rail']):.2f}x "
            "the floor at that rail)."
        )
        by_vctrl: dict[float, list[float]] = {}
        for e in spans:
            by_vctrl.setdefault(e["vctrl_v"], []).append(e["span"]["slope"])
        a("")
        a("  - Per-VCTRL spread of `S_span` across the PVT points measured:")
        a("")
        a("    | VCTRL (V) | points | min (%/V) | max (%/V) | mean (%/V) |")
        a("    |---|---|---|---|---|")
        for v in sorted(by_vctrl):
            vals = by_vctrl[v]
            a(
                f"    | {v:.3f} | {len(vals)} | {min(vals):+.1f} | {max(vals):+.1f} | "
                f"{sum(vals) / len(vals):+.1f} |"
            )
    a("")
    a(
        "  This section is derived characterization data. It ratifies nothing: "
        "row 13 stays DRAFT until a decision record argues it on its own "
        "merits, and `DR-006` itself is not edited by the campaign that "
        "produced this record."
    )
    return "\n".join(out) + "\n"


def _record_id(path: Path) -> str:
    return path.stem


def _split_existing(text: str) -> tuple[str, str | None]:
    """Return `(body_before_section, existing_section_or_None)`."""
    idx = text.find(SECTION_MARKER)
    if idx == -1:
        return text, None
    # Back up over the blank line the section opens with.
    start = text.rfind("\n", 0, idx)
    start = 0 if start == -1 else start
    return text[:start], text[start:]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("record", type=Path, help="path to sim/vco-supply-pushing/records/<record-id>.md")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--append", action="store_true", help="append the derived section to the record (once)")
    mode.add_argument("--check", action="store_true", help="re-derive and verify the section already in the record")
    args = p.parse_args(argv)

    text = args.record.read_text()
    body, existing = _split_existing(text)
    try:
        section = render_section(derive(parse_swept_table(body)), _record_id(args.record))
    except AnalysisError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.append:
        if existing is not None:
            print(
                f"error: {args.record} already carries a derived section; records are "
                "append-only -- mint a new record rather than re-appending",
                file=sys.stderr,
            )
            return 1
        args.record.write_text(body.rstrip("\n") + "\n" + section)
        print(f"appended derived supply-pushing analysis to {args.record}")
        return 0

    if args.check:
        if existing is None:
            print(f"error: {args.record} carries no derived section to check", file=sys.stderr)
            return 1
        if existing.strip() != section.strip():
            print(
                f"error: the derived section in {args.record} does not match a fresh "
                "re-derivation from its own swept-axis table",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {args.record}'s derived supply-pushing analysis re-derives exactly")
        return 0

    sys.stdout.write(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
