#!/usr/bin/env python3
"""Derive per-corner VCTRL tables for the graded issue-#422 campaigns.

Reads a `sim/vco-2x-iq-scan/records/<id>.md` swept-axis table (VCTRL vs f_out
per PVT point) and, for each point and each target output frequency, estimates
the VCTRL that gives it by a local quadratic through ln(f) vs VCTRL on the
three oscillating scan samples nearest the target. It then emits a short
bracket (`estimate + offsets`) so the graded campaign *measures* a few
neighbouring VCTRL values and grades the one inside the frequency band: the
estimate only chooses where to look, it is never the evidence.

    python3 make_vctrl_tables.py RECORD.md --target-hz 25e6 --offsets=-0.006,0,0.006 \
        --apply sim/vco-2x-iq-25mhz/testbench/tb.json

Stdlib only. Without --apply it prints the table as JSON.
"""
import argparse
import json
import math
import re
import sys

ROW = re.compile(
    r"^\s*\|\s*(\w+)\s*\|\s*(-?[\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+) (k|M|G)?Hz\s*\|"
)
UNIT = {None: 1.0, "k": 1e3, "M": 1e6, "G": 1e9}


def parse_scan(text):
    """{corner_id: [(vctrl, f_hz), ...]} from the record's swept-axis table."""
    pts = {}
    for line in text.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        corner, temp, supply, v, f, unit = m.groups()
        cid = f"{corner}_{float(temp):g}c_{float(supply):.2f}v"
        pts.setdefault(cid, []).append((float(v), float(f) * UNIT[unit]))
    return {k: sorted(set(v)) for k, v in pts.items()}


def estimate_vctrl(samples, target_hz):
    """Local quadratic (Lagrange) through ln f over the 3 samples nearest the target."""
    if len(samples) < 3:
        return None
    lt = math.log(target_hz)
    ordered = sorted(samples, key=lambda s: abs(math.log(s[1]) - lt))[:3]
    xs = [math.log(f) for _, f in ordered]  # interpolate V as a function of ln f
    ys = [v for v, _ in ordered]
    total = 0.0
    for i in range(3):
        term = ys[i]
        for j in range(3):
            if i != j:
                term *= (lt - xs[j]) / (xs[i] - xs[j])
        total += term
    lo, hi = min(ys), max(ys)
    span = hi - lo
    return min(max(total, lo - span), hi + span)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("record")
    ap.add_argument("--target-hz", type=float, required=True)
    ap.add_argument("--offsets", default="-0.006,0,0.006")
    ap.add_argument("--apply", metavar="TB_JSON")
    a = ap.parse_args(argv)
    offsets = [float(x) for x in a.offsets.split(",")]
    scan = parse_scan(open(a.record).read())
    table, missing = {}, []
    for cid, samples in sorted(scan.items()):
        est = estimate_vctrl(samples, a.target_hz)
        if est is None:
            missing.append(cid)
            continue
        table[cid] = [round(est + o, 4) for o in offsets]
    if missing:
        print(f"no estimate (fewer than 3 oscillating samples): {missing}", file=sys.stderr)
    if a.apply:
        d = json.load(open(a.apply))
        d["measure"]["sweep"]["values"] = [round(0.8 + o, 4) for o in offsets]
        d["measure"]["sweep"]["per_point"] = table
        with open(a.apply, "w") as fh:
            json.dump(d, fh, indent=2)
            fh.write("\n")
    else:
        print(json.dumps(table, indent=1))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
